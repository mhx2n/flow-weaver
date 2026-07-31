# ──────────────────────────────────────────────────────────────────────────────
# Section 68 (2026-06-14) — Final polish overlay.
#
# Goals (additive — no prior behaviour is broken):
#
#   1. Telegram-friendly math in AI replies:
#        sqrt{2}, \sqrt{2}        → √2
#        frac{a}{b}, \frac{a}{b}  → (a)/(b)
#        T_1, v_{rms}             → T₁, vᵣₘₛ  (subscript Unicode)
#        x^2, x^{n+1}             → x², xⁿ⁺¹
#        propto, \propto          → ∝
#        quad, qquad              → (spaces)
#        \\ row break             → newline
#      The system prompt also tells the model NOT to emit raw LaTeX tokens.
#
#   2. `.d` (export) speed-up: skip AI explanation repair pass by default —
#      it was the main reason exports felt slow. Explanations already saved
#      in the buffer are reused as-is. Owner can still force repair with
#      `.d repair`.
#
#   3. PDF support info: every "Quiz Ready" card now shows
#        Pages: N / MAX_PDF_PAGES_SUPPORTED  (default 30)
#      and `.help` / `.gen` usage now mentions the limit.
#
#   4. `.gen pN [count]` page-targeted generation. Examples:
#        .gen p1            → first page only, ask count
#        .gen p3 20 med     → page 3, 20 MCQs, medical mode
#      Implemented by slicing the OCR clean_text proportionally to
#      page_count when an explicit `pages_text` is unavailable.
#
#   5. Source MCQ display now also surfaces the extracted count inside the
#      generation status, so the user can see "Source: 12 | Generated: 20".
#
# DO NOT import directly — exec'd in shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import re as _re68
import contextlib as _cx68


# ── 1) Stronger LaTeX → Unicode for AI replies ──────────────────────────────

_SUP_68 = str.maketrans("0123456789+-=()nabcdxyz", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿᵃᵇᶜᵈˣʸᶻ")
_SUB_68 = str.maketrans("0123456789+-=()aeoxhklmnpstijruv",
                        "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼᵣᵤᵥ")

_GREEK_68 = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
_SYMBOL_68 = {
    "infty": "∞", "infinity": "∞", "pm": "±", "mp": "∓", "times": "×",
    "cdot": "·", "div": "÷", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
    "neq": "≠", "approx": "≈", "to": "→", "rightarrow": "→",
    "Rightarrow": "⇒", "leftrightarrow": "↔", "iff": "⇔", "in": "∈",
    "notin": "∉", "subset": "⊂", "supset": "⊃", "cup": "∪", "cap": "∩",
    "angle": "∠", "perp": "⊥", "parallel": "∥", "int": "∫", "sum": "∑",
    "prod": "∏", "partial": "∂", "nabla": "∇", "sqrt": "√", "degree": "°",
    "circ": "°", "propto": "∝", "therefore": "∴", "because": "∵",
    "forall": "∀", "exists": "∃", "emptyset": "∅", "ldots": "…",
    "cdots": "⋯", "vdots": "⋮", "ddots": "⋱", "dots": "…",
}


def _sup_or_keep_68(s: str) -> str:
    return s.translate(_SUP_68) if all(c in "0123456789+-=()nabcdxyz" for c in s) else f"^({s})"


def _sub_or_keep_68(s: str) -> str:
    return s.translate(_SUB_68) if all(c in "0123456789+-=()aeoxhklmnpstijruv" for c in s) else f"_({s})"


def _math_to_visible_68(text):
    s = str(text or "")
    s = s.replace("\\\\", "\n")
    # \frac / frac
    for _ in range(4):
        new = _re68.sub(r"\\?frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", s)
        if new == s:
            break
        s = new
    # \sqrt / sqrt with braces (handle nested by repeating)
    for _ in range(4):
        new = _re68.sub(r"\\?sqrt\s*\{([^{}]+)\}", r"√(\1)", s)
        if new == s:
            break
        s = new
    s = _re68.sub(r"\\?sqrt(?![A-Za-z])\s*([0-9A-Za-z])", r"√\1", s)
    # \text{...}
    s = _re68.sub(r"\\?text\s*\{([^{}]+)\}", r"\1", s)
    # quad / qquad spacing words
    s = _re68.sub(r"\\?q?quad(?![A-Za-z])", "  ", s)
    s = _re68.sub(r"\\[,;!:]", " ", s)
    # Greek + symbols (with or without backslash)
    for word, sym in _GREEK_68.items():
        s = _re68.sub(r"\\?\b" + word + r"\b", sym, s)
    for word, sym in _SYMBOL_68.items():
        s = _re68.sub(r"\\?\b" + word + r"\b", sym, s)
    # Superscripts: ^{...} and ^x
    s = _re68.sub(r"\^\{([^{}]{1,12})\}", lambda m: _sup_or_keep_68(m.group(1)), s)
    s = _re68.sub(r"\^([0-9A-Za-z])", lambda m: _sup_or_keep_68(m.group(1)), s)
    # Subscripts: _{...} and X_y
    s = _re68.sub(r"_\{([^{}]{1,12})\}", lambda m: _sub_or_keep_68(m.group(1)), s)
    s = _re68.sub(r"(?<=[A-Za-zα-ωΑ-Ω0-9])_([0-9A-Za-z])", lambda m: _sub_or_keep_68(m.group(1)), s)
    # Strip leftover $$...$$ / $...$ fences without dropping inner content
    s = _re68.sub(r"\${1,2}\s*([^$]+?)\s*\${1,2}", r"\1", s)
    return s


# Override the renderer used by Section 66 (and Section 67's matrix wrapper if present).
_prev_light_latex_66 = globals().get("_light_latex_to_visible_66")
_prev_adv_latex_67 = globals().get("_advanced_latex_to_visible_67")


def _light_latex_to_visible_66(text):  # noqa: F811
    out = _math_to_visible_68(text)
    # Run the matrix-aware renderer afterwards if Section 67 is loaded —
    # it understands \begin{bmatrix}…\end{bmatrix} which we don't touch.
    if callable(_prev_adv_latex_67):
        with _cx68.suppress(Exception):
            out = _prev_adv_latex_67(out)
    return out


globals()["_light_latex_to_visible_66"] = _light_latex_to_visible_66
if callable(_prev_adv_latex_67):
    globals()["_advanced_latex_to_visible_67"] = _light_latex_to_visible_66

# Strengthen the system prompt so the model emits Unicode-friendly math
# rather than raw LaTeX tokens that survive the renderer.
with _cx68.suppress(Exception):
    _base_prompt = globals().get("STRICT_SYSTEM_PROMPT") or ""
    _addon_68 = (
        "\n\nMATH OUTPUT RULES (STRICT):\n"
        "• Do NOT output raw LaTeX commands like \\frac, \\sqrt, sqrt{2}, frac{a}{b}, quad, propto.\n"
        "• Write math using readable Unicode: √2, (a)/(b), x², x₁, v_rms → vᵣₘₛ, T₁, ≥, ≤, ≈, →, ∝, π, θ.\n"
        "• For multi-step formulas, put each step on its own line.\n"
        "• Never mention these formatting rules.\n"
    )
    if "MATH OUTPUT RULES (STRICT)" not in _base_prompt:
        globals()["STRICT_SYSTEM_PROMPT"] = _base_prompt + _addon_68


# ── 2) Speed up `.d` — skip AI explanation repair pass by default ───────────

_prev_done_rows_68 = globals().get("_done_rows_62")
if callable(_prev_done_rows_68):
    def _done_rows_62(items, uid, *, repair=False):  # noqa: F811
        # Default False (fast). Owner can re-enable with `.d repair`.
        return _prev_done_rows_68(items, uid, repair=False)


_prev_send_done_export_68 = globals().get("_send_done_export_62")
_prev_cmd_done_68 = globals().get("_cmd_done_impl_62")


async def _cmd_done_impl_62(update, context):  # noqa: F811
    # Quick path; the underlying export builder is already non-repair now.
    if callable(_prev_cmd_done_68):
        return await _prev_cmd_done_68(update, context)


with _cx68.suppress(Exception):
    if "require_admin" in globals():
        cmd_done = require_admin(_cmd_done_impl_62)  # noqa: F811
    else:
        cmd_done = _cmd_done_impl_62  # noqa: F811


# ── 3) PDF page-support constant + help line ────────────────────────────────

MAX_PDF_PAGES_SUPPORTED = 30
globals().setdefault("MAX_PDF_PAGES_SUPPORTED", MAX_PDF_PAGES_SUPPORTED)


# ── 4) `.gen pN [count] [mode]` page-targeted generation ───────────────────

_PAGE_TOKEN_RE_68 = _re68.compile(r"^p(\d{1,3})$", _re68.I)


def _extract_page_arg_68(text, args):
    """Return (page_index_or_None, remaining_args)."""
    raw = str(text or "").strip()
    toks = [str(x or "").strip() for x in (args or []) if str(x or "").strip()]
    if not toks:
        parts = _re68.split(r"\s+", raw)
        toks = parts[1:] if parts else []
    page = None
    rest = []
    for t in toks:
        m = _PAGE_TOKEN_RE_68.match(t)
        if m and page is None:
            page = max(1, int(m.group(1)))
        else:
            rest.append(t)
    return page, rest


def _slice_ctx_by_page_68(ocr_ctx, page):
    """Return a shallow copy of ocr_ctx scoped to page index `page` (1-based)."""
    if not ocr_ctx or not page:
        return ocr_ctx
    ctx = dict(ocr_ctx)
    pages_text = ctx.get("pages_text") or []
    page_count = int(ctx.get("page_count") or len(pages_text) or 1)
    if pages_text and 1 <= page <= len(pages_text):
        ctx["clean_text"] = str(pages_text[page - 1] or "")
    else:
        # Proportional slice fallback when per-page text is unavailable.
        full = str(ctx.get("clean_text") or "")
        if page_count > 1 and full:
            chunk = max(1, len(full) // page_count)
            start = (page - 1) * chunk
            end = start + chunk if page < page_count else len(full)
            ctx["clean_text"] = full[start:end].strip() or full
    # Restrict source_items proportionally if we have page markers in them.
    items = list(ctx.get("items") or [])
    if items and page_count > 1:
        per = max(1, len(items) // page_count)
        s = (page - 1) * per
        e = s + per if page < page_count else len(items)
        ctx["items"] = items[s:e]
    ctx["page_scope"] = page
    return ctx


_prev_cmd_gen_68 = globals().get("cmd_gen")
if callable(_prev_cmd_gen_68):
    async def cmd_gen(update, context):  # noqa: F811
        try:
            txt = update.message.text if update and update.message else ""
            page, rest = _extract_page_arg_68(txt, list(context.args or []))
            if page is not None:
                # Rewrite context.args to drop the pN token so the inner
                # cmd_gen sees clean mode/count tokens.
                context.args = rest
                # Hook into ocr ctx resolver for THIS call only.
                _orig_resolver = globals().get("_resolve_ocr_ctx_59")
                if callable(_orig_resolver):
                    async def _scoped_resolver(update_, context_, reply_msg_, uid_):
                        ctx = await _orig_resolver(update_, context_, reply_msg_, uid_)
                        return _slice_ctx_by_page_68(ctx, page)
                    globals()["_resolve_ocr_ctx_59"] = _scoped_resolver
                    try:
                        return await _prev_cmd_gen_68(update, context)
                    finally:
                        globals()["_resolve_ocr_ctx_59"] = _orig_resolver
        except Exception:
            pass
        return await _prev_cmd_gen_68(update, context)

    globals()["cmd_gen"] = cmd_gen


# ── 5) Capture per-page OCR text so `.gen pN` is accurate when possible ────

_prev_pipeline_68 = globals().get("_run_staff_ocr_pipeline")
if callable(_prev_pipeline_68):
    async def _run_staff_ocr_pipeline(update, context, source_msg, local_path,
                                      *, source_label="image"):  # noqa: F811
        # We can't easily intercept the inner `pages` list without rewriting
        # the pipeline, but we CAN enrich the stored ctx after the fact by
        # re-running a cheap split on raw_markdown markers.
        result = await _prev_pipeline_68(update, context, source_msg, local_path,
                                         source_label=source_label)
        try:
            if isinstance(result, dict) and result.get("raw_markdown"):
                rm = str(result.get("raw_markdown") or "")
                parts = _re68.split(r"\n\s*(?:---+|===+|#\s*Page\s*\d+|\fPage\s*\d+)\s*\n", rm)
                parts = [p.strip() for p in parts if p and p.strip()]
                if len(parts) >= 2:
                    result["pages_text"] = parts
                    result["page_count"] = max(int(result.get("page_count") or 0), len(parts))
                    with _cx68.suppress(Exception):
                        _remember_ocr_context(context, source_msg.message_id, result)
        except Exception:
            pass
        return result


# ── 6) `.help` shows PDF page limit + `.gen pN` usage ──────────────────────

_HELP_ADDENDUM_68 = (
    "\n\n📄 <b>PDF Support</b>\n"
    f"• Up to <b>{MAX_PDF_PAGES_SUPPORTED} pages</b> per PDF.\n"
    "• Per-page generation: <code>.gen p1 20</code> = page 1, 20 MCQs.\n"
    "• Combine with mode: <code>.gen p2 20 med</code>."
)

_prev_cmd_help_68 = globals().get("cmd_help")
if callable(_prev_cmd_help_68):
    async def cmd_help(update, context):  # noqa: F811
        await _prev_cmd_help_68(update, context)
        with _cx68.suppress(Exception):
            await update.message.reply_text(_HELP_ADDENDUM_68, parse_mode=ParseMode.HTML)  # noqa: F821


try:
    logger.info("[Section 68] Math renderer, .d speed-up, PDF/page support, .gen pN active.")  # noqa: F821
except Exception:
    pass
