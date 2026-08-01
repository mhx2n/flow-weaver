# ──────────────────────────────────────────────────────────────────────────────
# Section 85 (2026-08-02) — Clean answer polish (everything else untouched)
#
#   1) No non-Islamic greetings.  Models sometimes opened with "নমস্কার",
#      "Namaste", "Namaskar", "Vanakkam", "Greetings" etc.  Such openings are
#      removed; if the answer really needs a greeting, "আসসালামু আলাইকুম" is
#      used instead.  Existing Islamic salaam is always preserved.
#
#   2) No trailing "…" in the corner.  Section 66 appended "\n\n…" when it
#      trimmed a long answer, and that ellipsis line showed up at the end of
#      every long reply.  It is stripped from the sanitised text, from the rich
#      markdown source and from the final HTML.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx85
import re as _re85


def _log85(msg: str) -> None:
    with _cx85.suppress(Exception):
        logger.info("[S85] %s", msg)  # type: ignore[name-defined]


_SALAAM_85 = "আসসালামু আলাইকুম"

# Greetings that must never appear (transliterations + native spellings).
_BAD_GREETING_RX_85 = _re85.compile(
    r"(?:নমস্কার|নমস্তে|প্রণাম|নমষ্কার|শুভেচ্ছা|"
    r"namaste|namaskar|namaskaar|namaskram|pranam|vanakkam|sat\s*sri\s*akal|"
    r"greetings|good\s+(?:morning|afternoon|evening)|hello\s+there)",
    _re85.I,
)

_HAS_SALAAM_RX_85 = _re85.compile(
    r"(আসসালামু\s*আলাইকুম|assalamu?\s*alaikum|salam(?:un)?\s*alaikum)", _re85.I
)


def _strip_greeting_85(text: str) -> str:
    """Remove non-Islamic greeting openings without touching the real answer."""
    s = str(text or "")
    if not s.strip():
        return s
    had_salaam = bool(_HAS_SALAAM_RX_85.search(s))
    lines = s.split("\n")
    # only inspect the first few lines — greetings live at the top
    for idx in range(min(3, len(lines))):
        line = lines[idx]
        if not line.strip():
            continue
        if not _BAD_GREETING_RX_85.search(line):
            continue
        cleaned = _BAD_GREETING_RX_85.sub("", line)
        # drop the leftover punctuation of the greeting clause
        cleaned = _re85.sub(r"^[\s!,\.।;:\-–—…\u0964]+", "", cleaned)
        cleaned = _re85.sub(r"\s{2,}", " ", cleaned).strip()
        if cleaned in {"!", ".", "।", ","}:
            cleaned = ""
        lines[idx] = cleaned
    out = "\n".join(lines)
    out = _re85.sub(r"\n{3,}", "\n\n", out).strip()
    if had_salaam and not _HAS_SALAAM_RX_85.search(out):
        out = _SALAAM_85 + "\n\n" + out
    return out or str(text or "")


_TRAIL_ELLIPSIS_RX_85 = _re85.compile(r"(?:\s*(?:…|\.\.\.)\s*)+\Z")
_ELLIPSIS_LINE_RX_85 = _re85.compile(r"\n[ \t]*(?:…|\.\.\.)[ \t]*(?=\n|\Z)")
_HTML_ELLIPSIS_RX_85 = _re85.compile(
    r"(?:\s|<br\s*/?>|&nbsp;)*(?:…|&#8230;|\.\.\.)(?:\s|<br\s*/?>|&nbsp;)*\Z", _re85.I
)


def _drop_trailing_ellipsis_85(text: str) -> str:
    s = str(text or "")
    if not s:
        return s
    s = _ELLIPSIS_LINE_RX_85.sub("", s)
    s = _TRAIL_ELLIPSIS_RX_85.sub("", s)
    return s.rstrip()


def _polish_answer_85(text: str) -> str:
    return _drop_trailing_ellipsis_85(_strip_greeting_85(text))


globals()["_strip_greeting_85"] = _strip_greeting_85
globals()["_drop_trailing_ellipsis_85"] = _drop_trailing_ellipsis_85
globals()["_polish_answer_85"] = _polish_answer_85


# ══════════════════════════════════════════════════════════════════════════
# 1) sanitiser: every answer path (HTML, rich markdown, chunking) uses it
# ══════════════════════════════════════════════════════════════════════════

_prev_sanitize_85 = globals().get("_sanitize_rich_answer_66")


def _sanitize_rich_answer_85(answer):
    raw = str(answer or "")
    if callable(_prev_sanitize_85):
        with _cx85.suppress(Exception):
            raw = str(_prev_sanitize_85(answer) or "")
    if raw.startswith("```") and raw.endswith("```"):
        return raw
    with _cx85.suppress(Exception):
        return _polish_answer_85(raw)
    return raw


if callable(_prev_sanitize_85):
    globals()["_sanitize_rich_answer_66"] = _sanitize_rich_answer_85
globals()["_sanitize_rich_answer_85"] = _sanitize_rich_answer_85


# ══════════════════════════════════════════════════════════════════════════
# 2) final HTML: remove the trailing "…" marker section 66 adds when trimming
# ══════════════════════════════════════════════════════════════════════════

_prev_html_85 = globals().get("_answer_to_tg_html_66") or globals().get("_answer_to_tg_html")


def _answer_to_tg_html_85(answer, *, model_name="", preserve_code=False):
    out = ""
    if callable(_prev_html_85):
        out = _prev_html_85(answer, model_name=model_name, preserve_code=preserve_code)
    if preserve_code:
        return out
    with _cx85.suppress(Exception):
        cleaned = _HTML_ELLIPSIS_RX_85.sub("", str(out or "")).rstrip()
        return cleaned or out
    return out


if callable(_prev_html_85):
    globals()["_answer_to_tg_html_66"] = _answer_to_tg_html_85
    globals()["_answer_to_tg_html"] = _answer_to_tg_html_85
    globals()["_answer_to_tg_html_83"] = _answer_to_tg_html_85
globals()["_answer_to_tg_html_85"] = _answer_to_tg_html_85


# ══════════════════════════════════════════════════════════════════════════
# 3) rich markdown source: same polish before it reaches MTProto
# ══════════════════════════════════════════════════════════════════════════

_prev_rich_md_85 = globals().get("_rich_markdown_83")


def _rich_markdown_85(answer, model_name=""):
    md = ""
    if callable(_prev_rich_md_85):
        with _cx85.suppress(Exception):
            md = str(_prev_rich_md_85(answer, model_name=model_name) or "")
    if not md:
        return md
    with _cx85.suppress(Exception):
        return _polish_answer_85(md)
    return md


if callable(_prev_rich_md_85):
    globals()["_rich_markdown_83"] = _rich_markdown_85
globals()["_rich_markdown_85"] = _rich_markdown_85


_prev_rich_deliver_85 = globals().get("rich_deliver_84") or globals().get("rich_deliver_83")


async def rich_deliver_85(bot, chat_id, markdown, *, reply_to=None, thread_id=None,
                          reply_markup=None):
    if not callable(_prev_rich_deliver_85):
        return None
    body = str(markdown or "")
    with _cx85.suppress(Exception):
        body = _polish_answer_85(body)
    if not body.strip():
        return None
    return await _prev_rich_deliver_85(
        bot, chat_id, body,
        reply_to=reply_to, thread_id=thread_id, reply_markup=reply_markup,
    )


if callable(_prev_rich_deliver_85):
    globals()["rich_deliver_83"] = rich_deliver_85
    globals()["rich_deliver_84"] = rich_deliver_85
globals()["rich_deliver_85"] = rich_deliver_85


# ══════════════════════════════════════════════════════════════════════════
# 4) prompt-level rule so models stop producing those greetings at all
# ══════════════════════════════════════════════════════════════════════════

_GREET_RULE_85 = (
    "\n\nSTYLE RULES (MANDATORY)\n"
    "• Never open with a non-Islamic greeting (no নমস্কার / Namaste / Namaskar / "
    "Pranam / Vanakkam / Greetings / Good morning).\n"
    "• Usually start directly with the answer. If a greeting is truly needed, "
    "use only \"আসসালামু আলাইকুম\".\n"
    "• Never end the answer with \"...\" or \"…\"; finish with real content.\n"
)

with _cx85.suppress(Exception):
    _sp85 = globals().get("STRICT_SYSTEM_PROMPT")
    if isinstance(_sp85, str) and "STYLE RULES (MANDATORY)" not in _sp85:
        globals()["STRICT_SYSTEM_PROMPT"] = _sp85 + _GREET_RULE_85

with _cx85.suppress(Exception):
    for _name85 in ("RICH_SYSTEM_PROMPT_65", "RICH_AI_SYSTEM_PROMPT", "RICH_PROMPT_65",
                    "_RICH_SYSTEM_65", "AI_SYSTEM_PROMPT"):
        _val85 = globals().get(_name85)
        if isinstance(_val85, str) and _val85.strip() and "STYLE RULES (MANDATORY)" not in _val85:
            globals()[_name85] = _val85 + _GREET_RULE_85


_log85("section 85 ready: non-Islamic greetings removed, trailing '…' marker dropped "
       "from HTML + rich markdown, style rules appended to system prompts")