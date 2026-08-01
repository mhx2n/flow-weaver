# ──────────────────────────────────────────────────────────────────────────────
# Section 83 (2026-08-02) — Safe math rich cards + rich text for every user
#
# Fixes reported problems (owner flows untouched, only rendering/delivery):
#
#   1) Math rich cards showed INCOMPLETE formulas ("² −√2x+1)/(x²+√2x+1)|+C").
#      Cause: section 79 promoted arbitrary ASCII runs to native
#      `mathematical_expression` blocks.  Its character class excluded "−", "²",
#      Bengali text etc., so one formula was chopped into unbalanced pieces and
#      Telegram rendered the broken tail only.
#      → Now math is promoted only as a WHOLE, balanced expression.  Anything
#        that is not provably complete is rendered as clean Unicode math text,
#        so nothing is ever truncated or lost.
#
#   2) Truncated stems: the poll question that reaches the card is already cut
#      to Telegram's poll limit.  The full LaTeX stem is recovered from the raw
#      item registry (exact → prefix → containment match).
#
#   3) Math items were always produced in English.  The language directive now
#      also locks the *prose* of math questions to the active language.
#
#   4) Users now receive native rich-text answers (real LaTeX math, tables,
#      headings) for every AI / OCR reply, with the classic HTML path kept as a
#      silent fallback so a user can never see an error.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx83
import hashlib as _hs83
import re as _re83


def _log83(msg: str) -> None:
    with _cx83.suppress(Exception):
        logger.info("[S83] %s", msg)  # type: ignore[name-defined]


def _mathify_83(text) -> str:
    fn = globals().get("mathify_79")
    if callable(fn):
        with _cx83.suppress(Exception):
            return str(fn(text) or "")
    return str(text or "")


# ══════════════════════════════════════════════════════════════════════════
# 1) BALANCED, NEVER-TRUNCATED MATH DETECTION
# ══════════════════════════════════════════════════════════════════════════

_BN_RX_83 = _re83.compile(r"[\u0980-\u09FF]")
_MACRO_RX_83 = _re83.compile(
    r"\\(?:d?frac|sqrt|int|iint|oint|sum|prod|lim|log|ln|exp|sin|cos|tan|cot|sec|csc|"
    r"vec|hat|bar|overline|left|right|cdot|times|div|pm|mp|leq|geq|neq|approx|infty|"
    r"partial|nabla|alpha|beta|gamma|delta|theta|lambda|mu|pi|rho|sigma|phi|psi|omega|"
    r"Rightarrow|rightarrow|to|text|mathrm|mathbf|begin|end)\b"
)
_FORMULA_LINE_RX_83 = _re83.compile(
    r"^[\sA-Za-z0-9\\{}\[\]()^_=+\-*/|,.:;<>!'\"&%~?"
    r"\u00b0\u00b2\u00b3\u00b9\u2070-\u209f\u2202\u221a\u222b\u2211\u220f"
    r"\u2264\u2265\u2260\u00b1\u2212\u00d7\u00f7\u21d2\u2192\u03b1-\u03c9\u0391-\u03a9]+$"
)
_PAIRS_83 = {"{": "}", "(": ")", "[": "]"}


def _balanced_83(expr: str) -> bool:
    """True when every bracket, \\left/\\right and $ fence is closed."""
    s = str(expr or "")
    if s.count("$") % 2:
        return False
    if len(_re83.findall(r"\\left\b", s)) != len(_re83.findall(r"\\right\b", s)):
        return False
    if len(_re83.findall(r"\\begin\b", s)) != len(_re83.findall(r"\\end\b", s)):
        return False
    stack = []
    for ch in s:
        if ch in _PAIRS_83:
            stack.append(_PAIRS_83[ch])
        elif ch in ("}", ")", "]"):
            if not stack or stack.pop() != ch:
                return False
    return not stack


def _repair_83(expr: str) -> str:
    fn = globals().get("_repair_latex_source_79")
    if callable(fn):
        with _cx83.suppress(Exception):
            return str(fn(expr) or "").strip()
    return str(expr or "").strip()


def _math_ok_83(expr: str) -> bool:
    """Only accept a native math block when it is complete and self-contained."""
    s = str(expr or "").strip()
    if len(s) < 2 or len(s) > 900:
        return False
    if _BN_RX_83.search(s):
        return False
    if not _balanced_83(s):
        return False
    # obvious fragments: a formula never starts with a closing/binary token
    if _re83.match(r"^[)\]}\u00b2\u00b3\u00b9|,;+*/=]", s):
        return False
    if _re83.search(r"[+\-*/=^_]$", s):
        return False
    return bool(_MACRO_RX_83.search(s) or _re83.search(r"[=^_/]|\\", s))


def _looks_formula_line_83(line: str) -> bool:
    s = str(line or "").strip()
    if not s or _BN_RX_83.search(s):
        return False
    if not _FORMULA_LINE_RX_83.match(s):
        return False
    return bool(_MACRO_RX_83.search(s) or _re83.search(r"[=^_\u221a\u222b\u2211\u220f]", s))


def _normalise_fences_83(text: str) -> str:
    s = str(text or "")
    s = _re83.sub(r"\\\[([\s\S]+?)\\\]", r"$$\1$$", s)
    s = _re83.sub(r"\\\((.+?)\\\)", r"$\1$", s, flags=_re83.S)
    return s


def _plain_or_math_83(chunk: str):
    """Un-fenced text: whole formula lines become math, prose stays text."""
    out = []
    text = str(chunk or "")
    if not text:
        return out
    buffer = []
    for line in text.split("\n"):
        expr = _repair_83(line)
        if _looks_formula_line_83(line) and _math_ok_83(expr):
            if buffer:
                out.append(_mathify_83("\n".join(buffer)))
                buffer = []
            out.append({"type": "mathematical_expression", "expression": expr})
        else:
            buffer.append(line)
    if buffer:
        out.append(_mathify_83("\n".join(buffer)))
    return [p for p in out if p != "" and p is not None]


_FENCE_RX_83 = _re83.compile(r"\$\$([\s\S]+?)\$\$|(?<!\$)\$([^$\n]+?)\$(?!\$)")


def _rich_text_parts_83(text):
    """Safe replacement for section 79's splitter — never emits partial math."""
    source = _normalise_fences_83(text)
    parts = []
    pos = 0
    for match in _FENCE_RX_83.finditer(source):
        if match.start() > pos:
            parts.extend(_plain_or_math_83(source[pos:match.start()]))
        expr = _repair_83(match.group(1) or match.group(2) or "")
        if expr:
            if _math_ok_83(expr):
                parts.append({"type": "mathematical_expression", "expression": expr})
            else:
                parts.append(_mathify_83(expr))
        pos = match.end()
    if pos < len(source):
        parts.extend(_plain_or_math_83(source[pos:]))

    # merge neighbouring strings, drop empties
    merged = []
    for part in parts:
        if isinstance(part, str):
            if not part.strip():
                continue
            if merged and isinstance(merged[-1], str):
                merged[-1] = merged[-1] + " " + part
                continue
        merged.append(part)
    if not merged:
        flat = _mathify_83(text)
        merged = [flat] if flat else []
    return merged


globals()["_rich_text_parts_79"] = _rich_text_parts_83
globals()["_rich_text_parts_83"] = _rich_text_parts_83


# ══════════════════════════════════════════════════════════════════════════
# 2) FULL-STEM RECOVERY (no more half questions on the card)
# ══════════════════════════════════════════════════════════════════════════

def _norm83(s: str) -> str:
    return _re83.sub(r"\s+", " ", _re83.sub(r"<[^>]+>", "", str(s or ""))).strip().lower()


def _full_question_83(question: str) -> str:
    """Recover the complete raw stem for a (possibly truncated) poll question."""
    q = str(question or "").strip()
    registry = globals().get("_RAW_ITEMS_78") or {}
    if not q or not isinstance(registry, dict) or not registry:
        return q
    key = _norm83(q)
    best = q
    with _cx83.suppress(Exception):
        exact = registry.get(key[:160])
        if isinstance(exact, dict):
            cand = str(exact.get("questions") or "").strip()
            if len(cand) > len(best):
                best = cand
        probe = key[:60]
        if probe and len(best) <= len(q):
            for payload in registry.values():
                if not isinstance(payload, dict):
                    continue
                cand = str(payload.get("questions") or "").strip()
                if not cand or len(cand) <= len(best):
                    continue
                nc = _norm83(cand)
                if probe in nc or nc[:60] == probe or key[-60:] in nc:
                    best = cand
    return best


def _stem_looks_cut_83(question: str) -> bool:
    s = str(question or "").strip()
    if not s:
        return True
    if _re83.match(r"^[)\]}\u00b2\u00b3\u00b9|,;+*/=]", s):
        return True
    return not _balanced_83(s)


def _repair_stem_83(question: str) -> str:
    """Never post a stem that begins mid-formula: prefer the complete raw one."""
    q = str(question or "").strip()
    full = _full_question_83(q)
    if full and (len(full) > len(q) or (_stem_looks_cut_83(q) and not _stem_looks_cut_83(full))):
        q = full
    if _stem_looks_cut_83(q):
        # 1) drop the mid-formula prefix a truncated stem starts with
        q = _re83.sub(r"^[)\]}|,;+*/=\s\u00b2\u00b3\u00b9\u2212\-]+", "", q)
        for _ in range(6):
            if q.count(")") <= q.count("(") and q.count("}") <= q.count("{"):
                break
            cut = min([p for p in (q.find(")"), q.find("}")) if p >= 0] or [-1])
            if cut < 0:
                break
            q = _re83.sub(r"^[^A-Za-z\u0980-\u09FF]+", "", q[cut + 1:])
        # 2) close whatever the source left open so the renderer stays valid
        opens = q.count("(") - q.count(")")
        if opens > 0:
            q = q + (")" * opens)
        braces = q.count("{") - q.count("}")
        if braces > 0:
            q = q + ("}" * braces)
        if q.count("$") % 2:
            q = q + "$"
    return q.strip()


_LABELS_BN_83 = ["ক", "খ", "গ", "ঘ", "ঙ", "চ", "ছ", "জ", "ঝ", "ঞ"]
_LABELS_EN_83 = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]


def _rich_math_blocks_83(question, options, lang="bn"):
    """Rich blocks with guaranteed stem + every option present, nicely spaced."""
    labels = _LABELS_EN_83 if lang == "en" else _LABELS_BN_83
    stem = _repair_stem_83(question)
    stem_parts = _rich_text_parts_83(stem) or [_mathify_83(stem) or "—"]
    blocks = [{"type": "paragraph", "text": stem_parts}, {"type": "divider"}]
    for index, option in enumerate(options or []):
        raw = str(option or "").strip()
        if not raw:
            continue
        label = labels[index] if index < len(labels) else str(index + 1)
        parts = _rich_text_parts_83(raw) or [_mathify_83(raw)]
        if not parts:
            continue
        blocks.append({"type": "paragraph", "text": ["(%s)  " % label] + parts})
    return blocks


def _rich_math_card_83(question, options, explanation="", lang="bn") -> str:
    labels = _LABELS_EN_83 if lang == "en" else _LABELS_BN_83
    stem = _mathify_83(_repair_stem_83(question))
    lines = ["**" + stem + "**", ""]
    for index, option in enumerate(options or []):
        opt = _mathify_83(option)
        if not opt.strip():
            continue
        label = labels[index] if index < len(labels) else str(index + 1)
        lines.append("**(" + label + ")**  " + opt)
        lines.append("")
    return "\n".join(lines).strip()


globals()["_rich_math_blocks_79"] = _rich_math_blocks_83
globals()["_rich_math_blocks_83"] = _rich_math_blocks_83
globals()["_rich_math_card_78"] = _rich_math_card_83
globals()["_rich_math_card_79"] = _rich_math_card_83
globals()["_rich_math_card_83"] = _rich_math_card_83


# ══════════════════════════════════════════════════════════════════════════
# 3) MATH ITEMS FOLLOW THE SELECTED LANGUAGE (not always English)
# ══════════════════════════════════════════════════════════════════════════

_prev_lang_directive_83 = globals().get("_lang_directive_81")

_MATH_LANG_RULE_BN_83 = (
    "\n\nMATH ITEM RULE (বাংলা):\n"
    "- ম্যাথ/ফিজিক্স প্রশ্নের নির্দেশনা-অংশ (stem prose) অবশ্যই বাংলায় লিখবে, "
    "যেমন: “নিচের ইন্টিগ্রালের মান কত?”।\n"
    "- শুধু সূত্র/রাশিমালা LaTeX-এ `$...$` বা `$$...$$` এর ভেতরে থাকবে; "
    "সূত্রের বাইরে কোনো ইংরেজি বাক্য থাকবে না।\n"
    "- প্রতিটি LaTeX সূত্র সম্পূর্ণ ও ব্যালান্সড হবে (সব বন্ধনী/ব্রেস বন্ধ থাকবে)।"
)

_MATH_LANG_RULE_EN_83 = (
    "\n\nMATH ITEM RULE (English):\n"
    "- Write the stem prose in English; keep every formula inside `$...$` or `$$...$$`.\n"
    "- Each LaTeX formula must be complete and balanced (all braces/parens closed)."
)

_MATH_LANG_RULE_MIX_83 = (
    "\n\nMATH ITEM RULE:\n"
    "- A math item's prose must be in the SAME language as its options and explanation; "
    "if the source is Bangla, write the math prose in Bangla too.\n"
    "- Keep every formula inside `$...$` / `$$...$$` and always complete and balanced — "
    "never emit a half formula or a bare `frac{`/`sqrt{` without its closing brace."
)


def _lang_directive_83(lang):
    base = ""
    if callable(_prev_lang_directive_83):
        with _cx83.suppress(Exception):
            base = str(_prev_lang_directive_83(lang) or "")
    if lang == "bn":
        return base + _MATH_LANG_RULE_BN_83
    if lang == "en":
        return base + _MATH_LANG_RULE_EN_83
    return base + _MATH_LANG_RULE_MIX_83


if callable(_prev_lang_directive_83):
    globals()["_lang_directive_81"] = _lang_directive_83
globals()["_lang_directive_83"] = _lang_directive_83


# ══════════════════════════════════════════════════════════════════════════
# 4) RICH TEXT FOR EVERY USER RESPONSE
# ══════════════════════════════════════════════════════════════════════════

_RICH_SRC_83: dict = {}


def _key83(html_text) -> str:
    return _hs83.sha1(str(html_text or "").encode("utf-8", "ignore")).hexdigest()


def _fence_bare_math_83(text: str) -> str:
    """Wrap complete un-fenced formula lines in $$ so rich rendering kicks in."""
    out = []
    for line in str(text or "").split("\n"):
        stripped = line.strip()
        if stripped and "$" not in stripped and _looks_formula_line_83(stripped):
            expr = _repair_83(stripped)
            if _math_ok_83(expr):
                out.append("$$" + expr + "$$")
                continue
        out.append(line)
    return "\n".join(out)


def _rich_markdown_83(answer, model_name="") -> str:
    sanitize = globals().get("_sanitize_rich_answer_66")
    body = str(answer or "")
    if callable(sanitize):
        with _cx83.suppress(Exception):
            body = str(sanitize(answer) or body)
    body = _normalise_fences_83(body)
    body = _fence_bare_math_83(body)
    body = _re83.sub(r"\n{3,}", "\n\n", body).strip()
    if not body:
        return ""
    if model_name:
        body = "**" + str(model_name) + "**\n\n" + body
    return body[:3900]


def _rich_ready_83() -> bool:
    state = globals().get("_RICH77")
    if state is None:
        return False
    with _cx83.suppress(Exception):
        return bool(state.ready())
    return False


async def rich_deliver_83(bot, chat_id, markdown, *, reply_to=None, thread_id=None,
                          reply_markup=None):
    """Send one native rich message. Returns the shim message or None."""
    sender = globals().get("rich_send_77")
    if not (callable(sender) and _rich_ready_83() and str(markdown or "").strip()):
        return None
    sent = None
    with _cx83.suppress(Exception):
        sent = await sender(bot, chat_id, markdown, parse_mode=None,
                            reply_to=reply_to, thread_id=thread_id)
    if not sent:
        return None
    if reply_markup is not None:
        attach = globals().get("_attach_markup_77")
        if callable(attach):
            with _cx83.suppress(Exception):
                await attach(bot, chat_id, sent.message_id, reply_markup)
    return sent


globals()["rich_deliver_83"] = rich_deliver_83


# ── remember the markdown source behind each rendered HTML answer ───────────
_prev_answer_to_html_83 = globals().get("_answer_to_tg_html_66") or globals().get("_answer_to_tg_html")


def _answer_to_tg_html_83(answer, *, model_name="", preserve_code=False):
    html_text = ""
    if callable(_prev_answer_to_html_83):
        html_text = _prev_answer_to_html_83(answer, model_name=model_name,
                                            preserve_code=preserve_code)
    if not preserve_code:
        with _cx83.suppress(Exception):
            markdown = _rich_markdown_83(answer, model_name)
            if markdown:
                _RICH_SRC_83[_key83(html_text)] = markdown
                if len(_RICH_SRC_83) > 400:
                    for stale in list(_RICH_SRC_83.keys())[:200]:
                        _RICH_SRC_83.pop(stale, None)
    return html_text


if callable(_prev_answer_to_html_83):
    globals()["_answer_to_tg_html_66"] = _answer_to_tg_html_83
    globals()["_answer_to_tg_html"] = _answer_to_tg_html_83
    globals()["_answer_to_tg_html_83"] = _answer_to_tg_html_83


# ── final answer delivery: native rich first, classic HTML fallback ─────────
_prev_edit_final_83 = globals().get("_edit_query_final_66")


async def _edit_query_final_83(q, html_text, *, reply_markup=None, plain_fallback=""):
    markdown = _RICH_SRC_83.get(_key83(html_text)) or ""
    message = getattr(q, "message", None)
    if markdown and message is not None:
        bot = None
        with _cx83.suppress(Exception):
            bot = q.get_bot()
        if bot is None:
            with _cx83.suppress(Exception):
                bot = message.get_bot()
        chat_id = getattr(message, "chat_id", None)
        if bot is not None and chat_id is not None:
            sent = await rich_deliver_83(
                bot, chat_id, markdown,
                thread_id=getattr(message, "message_thread_id", None),
                reply_markup=reply_markup,
            )
            if sent:
                with _cx83.suppress(Exception):
                    await message.delete()
                return sent
    if callable(_prev_edit_final_83):
        return await _prev_edit_final_83(q, html_text, reply_markup=reply_markup,
                                         plain_fallback=plain_fallback)
    return None


if callable(_prev_edit_final_83):
    globals()["_edit_query_final_66"] = _edit_query_final_83
globals()["_edit_query_final_83"] = _edit_query_final_83


_prev_extra_chunks_83 = globals().get("_reply_extra_chunks_66")


async def _reply_extra_chunks_83(message, chunks):
    if not message or not chunks:
        return
    pending = []
    bot = None
    with _cx83.suppress(Exception):
        bot = message.get_bot()
    for chunk in chunks:
        markdown = _rich_markdown_83(chunk, "")
        sent = None
        if bot is not None and markdown:
            sent = await rich_deliver_83(
                bot, getattr(message, "chat_id", None), markdown,
                reply_to=getattr(message, "message_id", None),
                thread_id=getattr(message, "message_thread_id", None),
            )
        if not sent:
            pending.append(chunk)
    if pending and callable(_prev_extra_chunks_83):
        with _cx83.suppress(Exception):
            await _prev_extra_chunks_83(message, pending)


if callable(_prev_extra_chunks_83):
    globals()["_reply_extra_chunks_66"] = _reply_extra_chunks_83
globals()["_reply_extra_chunks_83"] = _reply_extra_chunks_83


# ── widen the transport gate so ordinary user answers also go native rich ──
_prev_looks_rich_83 = globals().get("_looks_rich_77")


def _looks_rich_83(text):
    s = str(text or "")
    body = s.strip()
    if len(body) < 12:
        return False
    # status/progress pings must stay on the editable classic path
    if _re83.search(r"[\u25b0\u25b1]|Processing|Scanning|Reading the question|"
                    r"Analyzing|Finalizing", body) and len(body) < 200:
        return False
    if callable(_prev_looks_rich_83):
        with _cx83.suppress(Exception):
            if bool(_prev_looks_rich_83(text)):
                return True
    if _MACRO_RX_83.search(body) or "$" in body:
        return True
    return len(body) >= 220 and "\n" in body


if callable(_prev_looks_rich_83):
    globals()["_looks_rich_77"] = _looks_rich_83
globals()["_looks_rich_83"] = _looks_rich_83


_log83("section 83 ready: balanced math blocks, full stems, math language lock, "
       "native rich delivery for all users")
