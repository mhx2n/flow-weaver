# ──────────────────────────────────────────────────────────────────────────────
# Section 79 (2026-08-02) — Advanced math rendering + posting pacing + option
# order control.  Fixes reported issues:
#
#   1) Raw / half-stripped LaTeX leaking into posts and explanations
#      ("vec{A} = 2hat{i}", "frac{5}{sqrt{2}}", "90^circ", "Rightarrow")
#      → repaired and converted to clean professional Unicode math.
#   2) Rich text card for math questions now always renders nicely:
#      native MTProto rich first, high-fidelity HTML fallback second.
#   3) Every quiz post is paced (default 3 s) so Telegram never rate-limits /
#      freezes the bot.  Owner: /postdelay <seconds>
#   4) Option shuffle can be turned off so options stay ক খ গ ঘ in order.
#      Owner: /shuffle on|off   (default: OFF → natural order)
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import asyncio as _a79
import contextlib as _cx79
import re as _re79
import time as _t79

import telegram as _tg79


def _log79(msg: str) -> None:
    with _cx79.suppress(Exception):
        logger.info("[S79] %s", msg)  # type: ignore[name-defined]


# ── settings store (reuse section 78 table) ─────────────────────────────────

def _s79_get(key: str, default: str = "") -> str:
    fn = globals().get("_m78_get")
    if callable(fn):
        with _cx79.suppress(Exception):
            return fn(key, default)
    return default


def _s79_set(key: str, value: str) -> None:
    fn = globals().get("_m78_set")
    if callable(fn):
        with _cx79.suppress(Exception):
            fn(key, value)


def shuffle_on_79() -> bool:
    return _s79_get("opt_shuffle", "off").strip().lower() in ("1", "on", "true", "yes")


def post_delay_79() -> float:
    try:
        v = float(_s79_get("post_delay", "3.0") or 3.0)
    except Exception:
        v = 3.0
    return max(0.0, min(30.0, v))


# ══════════════════════════════════════════════════════════════════════════
# 1) MATH REPAIR + UNICODE ENGINE
# ══════════════════════════════════════════════════════════════════════════

_SUP_79 = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶",
           "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻", "−": "⁻", "=": "⁼",
           "(": "⁽", ")": "⁾", "n": "ⁿ", "i": "ⁱ", "x": "ˣ", "y": "ʸ", "a": "ᵃ",
           "b": "ᵇ", "c": "ᶜ", "T": "ᵀ"}
_SUB_79 = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆",
           "7": "₇", "8": "₈", "9": "₉", "+": "₊", "-": "₋", "=": "₌",
           "(": "₍", ")": "₎", "a": "ₐ", "e": "ₑ", "i": "ᵢ", "n": "ₙ",
           "o": "ₒ", "x": "ₓ", "t": "ₜ", "p": "ₚ", "r": "ᵣ", "s": "ₛ"}

# macro → symbol (backslash optional because upstream scrubbers drop it)
_SYM_79 = {
    "circ": "°", "degree": "°", "deg": "°",
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "equiv": "≡", "propto": "∝", "sim": "∼",
    "infty": "∞", "partial": "∂", "nabla": "∇",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔",
    "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔", "to": "→",
    "therefore": "∴", "because": "∵",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "θ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "pi": "π",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "int": "∫", "iint": "∬", "oint": "∮", "sum": "∑", "prod": "∏",
    "in": "∈", "notin": "∉", "subset": "⊂", "supset": "⊃",
    "cup": "∪", "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃",
    "angle": "∠", "perp": "⊥", "parallel": "∥", "triangle": "△",
    "ell": "ℓ", "hbar": "ℏ", "prime": "′", "ldots": "…", "cdots": "⋯",
    "quad": " ", "qquad": "  ", "ast": "∗", "star": "⋆",
}

_ACCENT_HAT_79 = {
    "i": "î", "j": "ĵ", "a": "â", "e": "ê", "o": "ô", "u": "û", "n": "n̂",
    "k": "k̂", "r": "r̂", "x": "x̂", "y": "ŷ", "z": "ẑ",
    "A": "Â", "B": "B̂", "C": "Ĉ", "I": "Î", "J": "Ĵ", "K": "K̂",
    "L": "L̂", "N": "N̂", "P": "P̂", "R": "R̂", "T": "T̂",
}

_VEC_MARK_79 = "\u20d7"   # combining right arrow above
_BAR_MARK_79 = "\u0304"
_DOT_MARK_79 = "\u0307"


def _sup_79(body: str) -> str:
    out = []
    for ch in body:
        if ch in _SUP_79:
            out.append(_SUP_79[ch])
        elif ch.isspace():
            continue
        else:
            return "^(" + body + ")" if len(body) > 1 else "^" + body
    return "".join(out)


def _sub_79(body: str) -> str:
    out = []
    for ch in body:
        if ch in _SUB_79:
            out.append(_SUB_79[ch])
        elif ch.isspace():
            continue
        else:
            return "_(" + body + ")" if len(body) > 1 else "_" + body
    return "".join(out)


def _needs_paren_79(s: str) -> bool:
    t = s.strip()
    if len(t) <= 1:
        return False
    return bool(_re79.search(r"[+\-\s×·/]", t))


def _wrap_79(s: str) -> str:
    t = s.strip()
    if not t:
        return t
    if _needs_paren_79(t) and not (t.startswith("(") and t.endswith(")")):
        return "(" + t + ")"
    return t


_MACRO_RE_79 = _re79.compile(r"(?:\\|(?<![A-Za-z]))([A-Za-z]{2,12})(?![A-Za-z])")


def _accent_79(s: str) -> str:
    """vec{A}/vec A → A⃗ , hat{i} → î , bar{x} → x̄ , dot{v} → v̇ ."""
    def one(name, mark_fn):
        nonlocal s
        pat_brace = _re79.compile(r"\\?" + name + r"\s*\{([^{}]{1,20})\}")
        pat_bare = _re79.compile(r"(?:\\|(?<![A-Za-z]))" + name + r"\s*([A-Za-z0-9])(?![A-Za-z])")
        for _ in range(6):
            new = pat_brace.sub(lambda m: mark_fn((m.group(1) or "").strip()), s)
            new = pat_bare.sub(lambda m: mark_fn((m.group(1) or "").strip()), new)
            if new == s:
                break
            s = new

    one("vec", lambda b: "".join(c + _VEC_MARK_79 for c in b) if len(b) <= 3 else b + _VEC_MARK_79)
    one("hat", lambda b: _ACCENT_HAT_79.get(b, b + "\u0302") if len(b) == 1 else b + "\u0302")
    one("widehat", lambda b: b + "\u0302")
    one("bar", lambda b: b + _BAR_MARK_79)
    one("overline", lambda b: b + _BAR_MARK_79)
    one("dot", lambda b: b + _DOT_MARK_79)
    one("tilde", lambda b: b + "\u0303")
    return s


def mathify_79(text: str) -> str:
    """Repair stripped/broken LaTeX and render it as clean Unicode math.

    Safe for plain Bengali/English text: anything that is not a recognised
    math construct is returned unchanged.
    """
    s = str(text or "")
    if not s:
        return s
    s = s.replace("\r", "")
    s = _re79.sub(r"\\{2,}(?=[A-Za-z])", lambda _m: "\\", s)

    # delimiters
    s = _re79.sub(r"\\\((.+?)\\\)", r"\1", s, flags=_re79.S)
    s = _re79.sub(r"\\\[(.+?)\\\]", r"\1", s, flags=_re79.S)
    s = _re79.sub(r"\$\$(.+?)\$\$", r"\1", s, flags=_re79.S)
    s = _re79.sub(r"\$([^$\n]+?)\$", r"\1", s)
    s = _re79.sub(r"(?:\\|(?<![A-Za-z]))(?:displaystyle|limits|nolimits)\b", "", s)
    s = _re79.sub(r"(?:\\|(?<![A-Za-z]))(?:left|right)\s*(?=[\(\)\[\]\|\.\{\}])", "", s)
    s = _re79.sub(r"(?:\\|(?<![A-Za-z]))(?:text|mathrm|mathbf|textbf|textit|mathit|operatorname)\s*\{([^{}]*)\}", r"\1", s)

    # accents (vec / hat / bar / dot)
    s = _accent_79(s)

    # degree written as ^circ / ^{\circ}
    s = _re79.sub(r"\^\s*\{?\s*\\?(?:circ|degree|deg)\s*\}?", "°", s)

    # roots + fractions, innermost first (they nest inside each other)
    frac_re = _re79.compile(r"(?:\\|(?<![A-Za-z]))(?:d|t)?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
    root_re = _re79.compile(r"(?:\\|(?<![A-Za-z]))sqrt\s*(?:\[([^\]]*)\])?\s*\{([^{}]*)\}")
    for _ in range(10):
        new = root_re.sub(
            lambda m: ("∛" if (m.group(1) or "").strip() == "3" else "√") + _wrap_79(m.group(2)), s)
        new = frac_re.sub(lambda m: _wrap_79(m.group(1)) + "/" + _wrap_79(m.group(2)), new)
        if new == s:
            break
        s = new
    s = _re79.sub(r"(?:\\|(?<![A-Za-z]))sqrt\s*([A-Za-z0-9])", r"√\1", s)
    s = _re79.sub(r"(?:\\|(?<![A-Za-z]))(?:d|t)?frac\s+([A-Za-z0-9])\s*([A-Za-z0-9])", r"\1/\2", s)

    # trig / log function names keep their name, drop the backslash
    s = _re79.sub(r"\\(sin|cos|tan|cot|sec|csc|log|ln|exp|lim|max|min|arcsin|arccos|arctan)\b", r"\1", s)

    # greek / operator names glued to a preceding word (e.g. "tantheta")
    _GLUED_79 = ("theta", "alpha", "beta", "gamma", "delta", "lambda", "omega",
                 "sigma", "phi", "psi", "mu", "pi", "rho", "tau", "circ",
                 "times", "cdot", "pm", "infty")
    for _w in _GLUED_79:
        s = _re79.sub(r"(?<=[a-z])" + _w + r"(?![A-Za-z])", _SYM_79.get(_w, _w), s)

    # symbol macros
    def _macro_sub(m):
        name = m.group(1)
        return _SYM_79.get(name, m.group(0))
    s = _MACRO_RE_79.sub(_macro_sub, s)

    # names glued directly to an uppercase symbol / bracket (e.g. "cdotB")
    _GLUE2_79 = sorted(_SYM_79.keys(), key=len, reverse=True)
    _glue2_re = _re79.compile(r"(?<![A-Za-z])(" + "|".join(_GLUE2_79) + r")(?=[A-Z0-9\(\[])")
    s = _glue2_re.sub(lambda m: _SYM_79.get(m.group(1), m.group(0)), s)

    # ^{...} / ^x  and _{...} / _x
    sup_re = _re79.compile(r"\^\s*\{([^{}]{1,12})\}")
    for _ in range(4):
        new = sup_re.sub(lambda m: _sup_79(m.group(1)), s)
        if new == s:
            break
        s = new
    s = _re79.sub(r"\^\s*([0-9A-Za-z°⁻+\-])", lambda m: _sup_79(m.group(1)), s)
    sub_re = _re79.compile(r"_\s*\{([^{}]{1,12})\}")
    for _ in range(4):
        new = sub_re.sub(lambda m: _sub_79(m.group(1)), s)
        if new == s:
            break
        s = new
    s = _re79.sub(r"(?<=[A-Za-z0-9\)\]])_\s*([0-9A-Za-z])", lambda m: _sub_79(m.group(1)), s)

    # degree written as "45°" after ^circ conversion may become "45 °"
    s = s.replace(" °", "°")
    # leftover single-token braces
    for _ in range(4):
        new = _re79.sub(r"\{\s*([^{}]{0,40}?)\s*\}", r"\1", s)
        if new == s:
            break
        s = new
    s = _re79.sub(r"\\([%$&#_{}])", r"\1", s)
    s = _re79.sub(r"\\[,;:!]", " ", s)
    s = _re79.sub(r"\\\\", "\n", s)
    s = _re79.sub(r"\\(?=[A-Za-z])", "", s)
    s = _re79.sub(r"\\(?=[^A-Za-z\s])", "", s)
    s = _re79.sub(r"[ \t]{2,}", " ", s)
    s = _re79.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


globals()["mathify_79"] = mathify_79


# ══════════════════════════════════════════════════════════════════════════
# 2) RICH MATH CARD (overrides section 78 renderer)
# ══════════════════════════════════════════════════════════════════════════

_LABELS_BN_79 = ["ক", "খ", "গ", "ঘ", "ঙ", "চ", "ছ", "জ", "ঝ", "ঞ"]
_LABELS_EN_79 = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]


def _rich_math_card_79(question: str, options, explanation: str = "", lang: str = "bn") -> str:
    labels = _LABELS_EN_79 if lang == "en" else _LABELS_BN_79
    q = mathify_79(question)
    lines = ["**" + q + "**", ""]
    for i, opt in enumerate(options or []):
        o = mathify_79(opt)
        if not o:
            continue
        lines.append("**(" + (labels[i] if i < len(labels) else str(i + 1)) + ")**  " + o)
    return "\n".join(lines).strip()


globals()["_rich_math_card_78"] = _rich_math_card_79
globals()["_rich_math_card_79"] = _rich_math_card_79

# also make section 78's LaTeX tidier use the full engine
globals()["_tidy_latex_78"] = mathify_79


async def _send_math_card_79(bot, chat_id, markdown, *, reply_to=None, thread_id=None) -> bool:
    """Native MTProto rich first, then a clean HTML card. Never raises."""
    sender = globals().get("rich_send_77")
    if callable(sender):
        with _cx79.suppress(Exception):
            msg = await sender(bot, chat_id, markdown, reply_to=reply_to, thread_id=thread_id)
            if msg:
                return True
    try:
        esc = globals().get("h")
        body = markdown
        parts = []
        for line in body.split("\n"):
            m = _re79.match(r"^\*\*(.+?)\*\*(.*)$", line)
            if m:
                head = esc(m.group(1)) if callable(esc) else m.group(1)
                tail = esc(m.group(2)) if callable(esc) else m.group(2)
                parts.append("<b>" + head + "</b>" + tail)
            else:
                parts.append(esc(line) if callable(esc) else line)
        html_body = "\n".join(parts)
        kw = {
            "chat_id": chat_id,
            "text": html_body[:4000],
            "parse_mode": ParseMode.HTML,  # type: ignore[name-defined]
            "disable_web_page_preview": True,
        }
        if thread_id:
            kw["message_thread_id"] = thread_id
        if reply_to:
            kw["reply_to_message_id"] = reply_to
        await bot.send_message(**kw)
        return True
    except Exception as e:
        _log79("math card failed: %s" % e)
        return False


globals()["_send_math_card_78"] = _send_math_card_79
globals()["_send_math_card_79"] = _send_math_card_79


# ══════════════════════════════════════════════════════════════════════════
# 3) OPTION ORDER CONTROL (shuffle on/off — default OFF)
# ══════════════════════════════════════════════════════════════════════════

_prev_shuffle_with_answer_79 = globals().get("_shuffle_with_answer")
_prev_shuffle_payload_79 = globals().get("_shuffle_quiz_payload")


def _shuffle_with_answer(options, correct_idx):  # noqa: F811
    if not shuffle_on_79():
        try:
            return list(options or []), int(correct_idx or 0)
        except Exception:
            return list(options or []), 0
    if callable(_prev_shuffle_with_answer_79):
        return _prev_shuffle_with_answer_79(options, correct_idx)
    return list(options or []), int(correct_idx or 0)


globals()["_shuffle_with_answer"] = _shuffle_with_answer


def _shuffle_quiz_payload(question, options, correct_option_id0):  # noqa: F811
    if not shuffle_on_79():
        return question, list(options or []), int(correct_option_id0 or 0)
    if callable(_prev_shuffle_payload_79):
        return _prev_shuffle_payload_79(question, options, correct_option_id0)
    return question, list(options or []), int(correct_option_id0 or 0)


globals()["_shuffle_quiz_payload"] = _shuffle_quiz_payload


# ══════════════════════════════════════════════════════════════════════════
# 4) PACED + MATH-CLEAN send_poll  (global throttle, default 3 s)
# ══════════════════════════════════════════════════════════════════════════

with _cx79.suppress(Exception):
    POST_DELAY_SECONDS = max(float(globals().get("POST_DELAY_SECONDS", 0.8) or 0.8), 3.0)  # type: ignore[name-defined]
    globals()["POST_DELAY_SECONDS"] = POST_DELAY_SECONDS

_POLL_GATE_79 = {"last": 0.0, "lock": None}


async def _pace_79() -> None:
    """Ensure at least `post_delay_79()` seconds between two quiz posts."""
    delay = post_delay_79()
    if delay <= 0:
        return
    if _POLL_GATE_79["lock"] is None:
        _POLL_GATE_79["lock"] = _a79.Lock()
    async with _POLL_GATE_79["lock"]:
        now = _t79.monotonic()
        wait = _POLL_GATE_79["last"] + delay - now
        if wait > 0:
            await _a79.sleep(min(wait, delay))
        _POLL_GATE_79["last"] = _t79.monotonic()


_PREV_SEND_POLL_79 = getattr(_tg79.Bot, "_s79_prev_send_poll", None) or _tg79.Bot.send_poll


async def _send_poll_79(self, chat_id=None, question=None, options=None, *args, **kwargs):
    q = kwargs.pop("question", question)
    opts = kwargs.pop("options", options)
    cid = kwargs.pop("chat_id", chat_id)
    with _cx79.suppress(Exception):
        q = mathify_79(q) if q else q
    with _cx79.suppress(Exception):
        opts = [mathify_79(str(getattr(o, "text", o) or "")) for o in (opts or [])]
    with _cx79.suppress(Exception):
        if kwargs.get("explanation"):
            kwargs["explanation"] = mathify_79(str(kwargs["explanation"]))
            # explanation is plain Unicode now — HTML parse mode would break on <>
            if kwargs.get("explanation_parse_mode") is not None and "<" not in kwargs["explanation"]:
                kwargs["explanation_parse_mode"] = None
    await _pace_79()
    return await _PREV_SEND_POLL_79(self, cid, q, opts, *args, **kwargs)


with _cx79.suppress(Exception):
    if not getattr(_tg79.Bot, "_s79_patched", False):
        _tg79.Bot._s79_prev_send_poll = _PREV_SEND_POLL_79
        _tg79.Bot.send_poll = _send_poll_79
        _tg79.Bot._s79_patched = True
        _log79("send_poll paced (%.1fs) + math-normalised" % post_delay_79())


# ══════════════════════════════════════════════════════════════════════════
# 5) AI / OCR answer text also gets the math engine
# ══════════════════════════════════════════════════════════════════════════

for _name79 in ("clean_latex_for_telegram", "latex_to_unicode_65", "_latex_to_unicode_67",
                "_unicode_math_66", "prettify_math_for_telegram"):
    _fn79 = globals().get(_name79)
    if callable(_fn79):
        def _wrap_math_79(prev=_fn79):
            def inner(text, *a, **k):
                out = text
                with _cx79.suppress(Exception):
                    out = prev(text, *a, **k)
                with _cx79.suppress(Exception):
                    out = mathify_79(out)
                return out
            return inner
        globals()[_name79] = _wrap_math_79()
        _log79("math engine chained into %s" % _name79)


# ══════════════════════════════════════════════════════════════════════════
# 6) OWNER COMMANDS: /shuffle on|off , /postdelay <sec>
# ══════════════════════════════════════════════════════════════════════════

def _is_owner_79(uid) -> bool:
    try:
        return bool(is_owner(int(uid)))  # type: ignore[name-defined]
    except Exception:
        return False


async def cmd_shuffle_79(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    if not update.message or not update.effective_user or not _is_owner_79(update.effective_user.id):
        return
    arg = (list(context.args or []) or [""])[0].strip().lower()
    if arg in ("on", "1", "true", "yes"):
        _s79_set("opt_shuffle", "on")
    elif arg in ("off", "0", "false", "no"):
        _s79_set("opt_shuffle", "off")
    on = shuffle_on_79()
    with _cx79.suppress(Exception):
        await update.message.reply_text(
            ui_box_html(  # type: ignore[name-defined]
                "Option Shuffle",
                "Status: <b>%s</b>\n" % ("ON (এলোমেলো)" if on else "OFF (ক খ গ ঘ ক্রমে)") +
                "OFF থাকলে অপশন প্রশ্নের মূল ক্রমেই যাবে.\n\n"
                "Change: <code>/shuffle on</code> | <code>/shuffle off</code>",
                emoji="🔀",
            ),
            parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
        )


async def cmd_postdelay_79(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    if not update.message or not update.effective_user or not _is_owner_79(update.effective_user.id):
        return
    arg = (list(context.args or []) or [""])[0].strip()
    if arg:
        with _cx79.suppress(Exception):
            val = max(0.0, min(30.0, float(_re79.sub(r"[^0-9.]", "", arg) or 3.0)))
            _s79_set("post_delay", str(val))
            globals()["POST_DELAY_SECONDS"] = val
    with _cx79.suppress(Exception):
        await update.message.reply_text(
            ui_box_html(  # type: ignore[name-defined]
                "Quiz Post Delay",
                "Current: <b>%.1f s</b> per quiz\n" % post_delay_79() +
                "প্রতিটি কুইজের মাঝে এই বিরতি থাকবে — rate-limit / আটকে যাওয়া বন্ধ হবে.\n\n"
                "Change: <code>/postdelay 3</code> | <code>/postdelay 5</code>",
                emoji="⏱️",
            ),
            parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
        )


if "build_app" in globals():
    _prev_build_app_79 = build_app  # type: ignore[name-defined]

    def build_app():  # noqa: F811  # type: ignore[name-defined]
        app = _prev_build_app_79()
        with _cx79.suppress(Exception):
            if "_register_dual_command" in globals():
                _register_dual_command(app, "shuffle", cmd_shuffle_79, group=-490)  # type: ignore[name-defined]
                _register_dual_command(app, "postdelay", cmd_postdelay_79, group=-490)  # type: ignore[name-defined]
            else:
                app.add_handler(CommandHandler("shuffle", cmd_shuffle_79), group=-490)  # type: ignore[name-defined]
                app.add_handler(CommandHandler("postdelay", cmd_postdelay_79), group=-490)  # type: ignore[name-defined]
        return app

_log79("section 79 ready: unicode math, 3s pacing, shuffle toggle")

# ===== END SECTION 79 =====
