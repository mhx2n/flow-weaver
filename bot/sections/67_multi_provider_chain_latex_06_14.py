# ──────────────────────────────────────────────────────────────────────────────
# Section: 67_multi_provider_chain_latex_06_14
#
# Goals (additive — does NOT break any prior behavior):
#  1) Owner can register MANY AI providers (OpenAI-compatible: Mistral, Groq,
#     OpenRouter, Together, DeepSeek-compat, etc.). When the default Gemini /
#     Perplexity chain fails (quota / 429 / 5xx / empty), automatically fall
#     over to those providers — for BOTH user text replies and quiz flows.
#     Reuses the existing `_adv_*` registry from section 51, just extends
#     `_solve_text_with_preference` / `_try_gemini_text_backends`.
#  2) New convenience aliases: /addprovider, /providers, /delprovider so the
#     owner can manage providers with friendly names (kept compatible with
#     the existing /advadd, /advmode, /advrm commands).
#  3) Render matrix / advanced LaTeX nicely: \begin{bmatrix}…\end{bmatrix},
#     \vdots, \ddots, \Rightarrow, A^T, \\ row breaks, & column separators.
#     Used by the AI HTML renderer so answers about matrices stop showing
#     raw `begin{bmatrix}` etc.
#  4) Bandwidth saver on Render: health endpoint returns a tiny constant body
#     with long-lived cache headers, head requests answered cheaply, and
#     non-GET/HEAD pinger paths short-circuited so the 5 GB / 31-day budget
#     lasts longer.
# ──────────────────────────────────────────────────────────────────────────────

import re as _re67
import contextlib as _ctx67


# ───────────────────────── 1) Provider cascade ───────────────────────────────

_prev_try_gemini_text_backends_67 = globals().get("_try_gemini_text_backends")
_prev_solve_text_with_preference_67 = globals().get("_solve_text_with_preference")
_prev_try_gemini_mcq_backends_67 = globals().get("_try_gemini_mcq_backends")


def _adv_cascade_available_67() -> bool:
    try:
        rows = (globals().get("_ADV_MEM_CACHE") or {}).get("rows") or []
    except Exception:
        rows = []
    # We only care about *extra* providers beyond the built-in gemini/perplexity
    # that are also queried by the legacy chain.
    for r in rows or []:
        if not r.get("enabled"):
            continue
        kind = str(r.get("kind") or "").lower()
        if kind in ("openai_compat", "groq", "openrouter", "mistral_chat",
                    "together", "deepseek", "fireworks", "anyscale"):
            return True
    return False


def _adv_text_fallback_67(prompt: str, *, timeout_seconds: int = 18):
    """Try the owner's advanced provider registry as a final fallback."""
    fn = globals().get("_adv_call_text")
    if not callable(fn):
        raise RuntimeError("advanced provider cascade unavailable")
    out, name = fn(prompt, force_json=False, timeout=max(10, int(timeout_seconds or 18)))
    if not out or not str(out).strip():
        raise RuntimeError("advanced cascade returned empty")
    return str(out).strip(), str(name or "Provider")


def _try_gemini_text_backends(prompt: str, *, timeout_seconds: int = 18):  # noqa: F811
    """Wrap previous Gemini/Perplexity cascade with an extra provider fallback."""
    try:
        if callable(_prev_try_gemini_text_backends_67):
            return _prev_try_gemini_text_backends_67(prompt, timeout_seconds=timeout_seconds)
    except Exception as e:
        if not _adv_cascade_available_67():
            raise
        try:
            return _adv_text_fallback_67(prompt, timeout_seconds=timeout_seconds)
        except Exception:
            raise e
    # If previous returned but with empty text, also try cascade
    raise RuntimeError("primary chain returned nothing")


def _solve_text_with_preference(model: str, problem_text: str, scope: str = "private_academic"):  # noqa: F811
    """Preserve the user's chosen model; if everything in the prior chain
    fails, fall back to the owner's registered providers."""
    try:
        if callable(_prev_solve_text_with_preference_67):
            return _prev_solve_text_with_preference_67(model, problem_text, scope)
    except Exception as primary_err:
        if not _adv_cascade_available_67():
            raise
        try:
            base = globals().get("STRICT_SYSTEM_PROMPT") or ""
            prompt = (base + "\n\nStudent question:\n" + str(problem_text or "")).strip()
            return _adv_text_fallback_67(prompt, timeout_seconds=20)
        except Exception:
            raise primary_err
    raise RuntimeError("solver returned empty")


def _try_gemini_mcq_backends(question, options):  # noqa: F811
    """Wrap MCQ backend with provider-cascade JSON fallback."""
    try:
        if callable(_prev_try_gemini_mcq_backends_67):
            return _prev_try_gemini_mcq_backends_67(question, options)
    except Exception as primary_err:
        fn = globals().get("_adv_call_text")
        build = globals().get("_build_mcq_json_prompt")
        coerce = globals().get("_coerce_mcq_result") or globals().get("_extract_json_strict")
        if not (callable(fn) and callable(build) and callable(coerce) and _adv_cascade_available_67()):
            raise
        try:
            prompt, opts = build(question, options)
            raw, name = fn(prompt, force_json=True, timeout=14)
            try:
                data = coerce(raw, len(opts))  # _coerce_mcq_result signature
            except TypeError:
                data = coerce(raw)
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, str(name or "Provider")
        except Exception:
            pass
        raise primary_err
    raise RuntimeError("MCQ chain returned empty")


globals()["_try_gemini_text_backends"] = _try_gemini_text_backends
globals()["_solve_text_with_preference"] = _solve_text_with_preference
globals()["_try_gemini_mcq_backends"] = _try_gemini_mcq_backends


# ───────────────────────── 2) Owner alias commands ───────────────────────────

async def cmd_addprovider_67(update, context):
    if not update.effective_user or not is_owner(update.effective_user.id):  # noqa: F821
        return
    fn = globals().get("cmd_advadd")
    if callable(fn):
        return await fn(update, context)


async def cmd_providers_67(update, context):
    if not update.effective_user or not is_owner(update.effective_user.id):  # noqa: F821
        return
    fn = globals().get("cmd_advmode")
    if callable(fn):
        return await fn(update, context)


async def cmd_delprovider_67(update, context):
    if not update.effective_user or not is_owner(update.effective_user.id):  # noqa: F821
        return
    fn = globals().get("cmd_advrm")
    if callable(fn):
        return await fn(update, context)


_prev_build_app_67 = globals().get("build_app")


def build_app():  # noqa: F811
    app = _prev_build_app_67() if callable(_prev_build_app_67) else None
    if app is None:
        return app
    with _ctx67.suppress(Exception):
        app.add_handler(CommandHandler("addprovider", cmd_addprovider_67))  # noqa: F821
        app.add_handler(CommandHandler("providers", cmd_providers_67))  # noqa: F821
        app.add_handler(CommandHandler("delprovider", cmd_delprovider_67))  # noqa: F821
    return app


globals()["build_app"] = build_app


# ───────────────────────── 3) Matrix / advanced LaTeX ────────────────────────

_BMATRIX_RE_67 = _re67.compile(
    r"\\?begin\s*\{?(b|p|v|V|B)?matrix\}?(.*?)\\?end\s*\{?(?:b|p|v|V|B)?matrix\}?",
    _re67.S | _re67.I,
)


def _render_matrix_block_67(_kind: str, body: str) -> str:
    # Rows separated by \\, columns by &; rows may also be on separate physical lines.
    text = str(body or "").strip()
    text = _re67.sub(r"\\\\", "\n", text)
    rows = []
    for line in text.split("\n"):
        line = line.strip().strip("&").strip()
        if not line:
            continue
        cells = [c.strip() for c in line.split("&")]
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    col_w = [max(len(r[c]) for r in rows) for c in range(width)]
    lines = []
    for r in rows:
        cells = [r[c].rjust(col_w[c]) for c in range(width)]
        lines.append("│ " + "  ".join(cells) + " │")
    top = "┌" + "─" * (len(lines[0]) - 2) + "┐"
    bot = "└" + "─" * (len(lines[0]) - 2) + "┘"
    return "\n" + "\n".join([top, *lines, bot]) + "\n"


def _advanced_latex_to_visible_67(text):
    s = str(text or "")
    # Matrices first
    s = _BMATRIX_RE_67.sub(lambda m: _render_matrix_block_67(m.group(1) or "b", m.group(2) or ""), s)
    # Common standalone words that previous pass missed
    replacements = {
        r"\\vdots\b": "⋮", r"\bvdots\b": "⋮",
        r"\\ddots\b": "⋱", r"\bddots\b": "⋱",
        r"\\cdots\b": "⋯", r"\bcdots\b": "⋯",
        r"\\ldots\b": "…", r"\bldots\b": "…",
        r"\\Rightarrow\b": "⇒", r"\bRightarrow\b": "⇒",
        r"\\Leftarrow\b": "⇐", r"\bLeftarrow\b": "⇐",
        r"\\Leftrightarrow\b": "⇔",
        r"\\rightarrow\b": "→", r"\brightarrow\b": "→",
        r"\\leftarrow\b": "←", r"\bleftarrow\b": "←",
        r"\\mapsto\b": "↦",
        r"\\therefore\b": "∴", r"\\because\b": "∵",
        r"\\forall\b": "∀", r"\\exists\b": "∃",
        r"\\implies\b": "⇒", r"\\iff\b": "⇔",
    }
    for pat, repl in replacements.items():
        s = _re67.sub(pat, repl, s)
    # A^T  /  A^{T}  /  A_{ij}^{T}
    s = _re67.sub(r"\^\{T\}", "ᵀ", s)
    s = _re67.sub(r"(?<=[A-Za-z\)\]])\^T\b", "ᵀ", s)
    s = _re67.sub(r"\^\{-1\}", "⁻¹", s)
    s = _re67.sub(r"\^\{-2\}", "⁻²", s)
    # leftover \begin/\end blocks (non-matrix) — strip braces
    s = _re67.sub(r"\\?(begin|end)\s*\{[^}]*\}", "", s, flags=_re67.I)
    # Stray & at end-of-cell when matrix not detected
    s = _re67.sub(r"\s&\s", "  ", s)
    return s


_prev_light_latex_to_visible_67 = globals().get("_light_latex_to_visible_66")


def _light_latex_to_visible_66(text):  # noqa: F811 — replace section 66's pass
    s = _advanced_latex_to_visible_67(text)
    if callable(_prev_light_latex_to_visible_67):
        try:
            s = _prev_light_latex_to_visible_67(s)
        except Exception:
            pass
    return s


globals()["_light_latex_to_visible_66"] = _light_latex_to_visible_66


# ───────────────────────── 4) Render bandwidth saver ─────────────────────────
# Replaces the health server with a tighter one — same external behavior
# (200 OK on GET /) but smaller response, cache headers, and silent HEAD.

def _run_render_health_server():  # noqa: F811
    try:
        port = int(os.getenv("PORT", "10000"))  # noqa: F821
    except Exception:
        port = 10000

    class _LiteHealthHandler(BaseHTTPRequestHandler):  # noqa: F821
        _BODY = b"ok"

        def _send(self, with_body: bool):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(self._BODY)))
            self.send_header("Cache-Control", "public, max-age=300, immutable")
            self.send_header("Connection", "close")
            self.end_headers()
            if with_body:
                try:
                    self.wfile.write(self._BODY)
                except Exception:
                    pass

        def do_GET(self):
            self._send(True)

        def do_HEAD(self):
            self._send(False)

        def do_POST(self):
            # Most pingers use GET; reject POST cheaply to save bytes.
            self.send_response(405); self.send_header("Content-Length", "0"); self.end_headers()

        def log_message(self, fmt, *args):
            return

    try:
        server = HTTPServer(("0.0.0.0", port), _LiteHealthHandler)  # noqa: F821
        server.serve_forever()
    except Exception as e:
        try:
            logger.exception("Health server failed: %s", e)  # noqa: F821
        except Exception:
            pass


globals()["_run_render_health_server"] = _run_render_health_server


try:
    logger.info("[multi-provider 67] cascade + matrix LaTeX + lite health server active.")  # noqa: F821
except Exception:
    pass
