# ──────────────────────────────────────────────────────────────────────────────
# Section 87 (2026-08-02) — final, provider-independent language lock.
#
# Section 86 added prompt hints, but two gaps remained:
#   • language detection inspected the whole composed prompt/history, so English
#     labels and an older English answer could outweigh the current Bangla turn;
#   • a fallback provider could ignore the hint and its English output was sent
#     without validation.
#
# This overlay fixes both without changing quiz/OCR/rich-delivery behaviour:
#   1) extract the latest/current user turn before detecting language;
#   2) recognise practical Banglish ("shajiye daw ... tar jonno ... akare");
#   3) put an unambiguous lock at BOTH ends of every solver input;
#   4) validate the returned answer and make one bounded rewrite attempt when a
#      provider answered in the wrong language.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx87
import re as _re87


def _log87(msg: str) -> None:
    with _cx87.suppress(Exception):
        logger.info("[S87] %s", msg)  # type: ignore[name-defined]


_BN_CHAR_RX_87 = _re87.compile(r"[\u0980-\u09FF]")
_LATIN_WORD_RX_87 = _re87.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

# Explicit instructions always beat automatic mirroring.
_EXPLICIT_EN_87 = _re87.compile(
    r"(?:\bin\s+english\b|\benglish\s+(?:only|e|a|language|version|translation|answer)\b|"
    r"\b(?:write|reply|answer|explain|say|tell)\s+(?:it\s+)?in\s+english\b|"
    r"ইংরেজি(?:তে|য়|য়)?\s*(?:বল|বলো|লিখ|লিখো|দাও|উত্তর|ব্যাখ্যা|অনুবাদ))",
    _re87.I,
)
_EXPLICIT_BN_87 = _re87.compile(
    r"(?:\bin\s+(?:bangla|bengali)\b|\b(?:bangla|bengali)\s+(?:only|te|e|language|version|translation|answer)\b|"
    r"\b(?:write|reply|answer|explain|say|tell|bolo|bol|lekho|likho|dao|daw)\s+(?:it\s+)?in\s+(?:bangla|bengali)\b|"
    r"বাংলা(?:তে|য়|য়)?\s*(?:বল|বলো|লিখ|লিখো|দাও|উত্তর|ব্যাখ্যা|অনুবাদ))",
    _re87.I,
)

# Common high-signal Banglish vocabulary and inflections.  A score is used
# instead of one huge permissive regex so ordinary English does not flip to BN.
_BANGLISH_87 = {
    "ami", "amake", "amar", "amader", "amra", "apni", "apnar", "tumi", "tumi", "tomar",
    "ki", "kivabe", "kibhabe", "kemon", "keno", "kano", "kn", "kothay", "kokhon", "kon",
    "eta", "eita", "ota", "oita", "egulo", "eigulo", "gulo", "gula", "sob", "shob", "kisu",
    "bolo", "bolen", "bol", "dao", "daw", "den", "dewa", "diye", "dibo", "diben",
    "koro", "kor", "kore", "korbo", "korte", "korben", "banaw", "banao", "banate",
    "bujhao", "bujhiye", "bujhte", "shikhao", "sajao", "shajiye", "guchiye",
    "hobe", "hoy", "hoise", "hoye", "ache", "ase", "nai", "nei", "na", "lagbe",
    "tar", "jonno", "sathe", "theke", "moddhe", "kache", "pore", "age", "abar",
    "akare", "vabe", "bhabe", "moto", "mot", "ektu", "onek", "aro", "shudhu", "sudhu",
    "proshno", "prosno", "uttor", "somadhan", "shomadhan", "onko", "ongko", "porikkha",
    "porashona", "routine", "bishoy", "bisoy", "bisleshon", "chobi", "lekha", "table", "admission",
}
_BANGLISH_STRONG_87 = {
    "amake", "kivabe", "kibhabe", "bujhiye", "shajiye", "guchiye", "jonno", "akare",
    "proshno", "prosno", "uttor", "somadhan", "shomadhan", "porikkha", "porashona",
}

_CURRENT_MARKERS_87 = (
    "current user message:",
    "user's follow-up question:",
    "user follow-up question:",
    "user's request about this page:",
    "user's request:",
    "original user message:",
    "student question:",
    "user message:",
)


def _latest_user_turn_87(text: str) -> str:
    """Pull the latest real user turn out of solver/OCR/history wrappers."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    best_pos = -1
    best_marker = ""
    for marker in _CURRENT_MARKERS_87:
        pos = low.rfind(marker)
        if pos > best_pos:
            best_pos, best_marker = pos, marker
    if best_pos >= 0:
        current = raw[best_pos + len(best_marker):].strip()
        # OCR prompts append English context after the request.  Only the first
        # request paragraph should decide the response language.
        for boundary in ("\n\nprevious answer", "\n\n---", "\n\nfull ocr", "\n\nconversation history"):
            cut = current.lower().find(boundary)
            if cut > 0:
                current = current[:cut].strip()
        if current:
            return current[:3000]
    return raw[-3000:]


def _detect_language_87(text: str) -> str:
    current = _latest_user_turn_87(text)
    if not current:
        return "bn"
    if _EXPLICIT_EN_87.search(current):
        return "en"
    if _EXPLICIT_BN_87.search(current):
        return "bn"

    bn_count = len(_BN_CHAR_RX_87.findall(current))
    if bn_count >= 1:
        return "bn"

    words = [w.lower() for w in _LATIN_WORD_RX_87.findall(current)]
    if not words:
        return "bn"
    hits = [w for w in words if w in _BANGLISH_87]
    strong = sum(1 for w in words if w in _BANGLISH_STRONG_87)
    # Two ordinary Banglish markers, or one unmistakable marker plus another
    # colloquial inflection, is enough. This intentionally catches mixed text
    # containing English subject names such as "admission Exam".
    if strong >= 1 and len(hits) >= 2:
        return "bn"
    if len(hits) >= 3:
        return "bn"
    if len(words) <= 5 and len(hits) >= 2:
        return "bn"
    return "en"


_LOCK_BN_87 = (
    "MANDATORY RESPONSE LANGUAGE: BANGLA. "
    "Write every explanatory sentence in natural Bengali script (বাংলা). "
    "English is allowed only for unavoidable technical terms, symbols, formulas, code, and proper nouns. "
    "Do not translate or discuss this instruction."
)
_LOCK_EN_87 = (
    "MANDATORY RESPONSE LANGUAGE: ENGLISH. "
    "Write the complete answer in English; do not switch to Bengali unless the current user explicitly requests it. "
    "Do not translate or discuss this instruction."
)


def _lock_input_87(text: str, lang: str) -> str:
    raw = str(text or "").strip()
    rule = _LOCK_BN_87 if lang == "bn" else _LOCK_EN_87
    # Repeating the lock after the content makes it the last instruction seen by
    # providers that underweight long system prompts/history.
    return f"{rule}\n\n{raw}\n\nFINAL REMINDER — {rule}".strip()


def _answer_matches_87(answer: str, lang: str) -> bool:
    body = str(answer or "").strip()
    if len(body) < 12:
        return True
    # Ignore markdown syntax, URLs, code/math and model headings while measuring.
    probe = _re87.sub(r"https?://\S+|```.*?```|`[^`]*`|\$.*?\$", " ", body, flags=_re87.S)
    bn = len(_BN_CHAR_RX_87.findall(probe))
    latin = len(_re87.findall(r"[A-Za-z]", probe))
    if lang == "bn":
        # Technical answers may contain many Latin symbols, but a Bangla answer
        # still needs a meaningful Bengali sentence rather than a token heading.
        return bn >= 12 and (bn >= 28 or bn / max(1, bn + latin) >= 0.10)
    # Symbols/proper nouns are fine; a substantial Bengali paragraph is not.
    return bn < 12 or bn / max(1, bn + latin) < 0.08


def _repair_prompt_87(source: str, bad_answer: str, lang: str) -> str:
    target = "natural Bengali script (বাংলা)" if lang == "bn" else "English"
    rule = _LOCK_BN_87 if lang == "bn" else _LOCK_EN_87
    return (
        f"{rule}\n\n"
        f"Rewrite the draft below entirely in {target}. Preserve every fact, formula, table, "
        "blockquote, spoiler, list, and code block. Do not shorten it and do not add a preface.\n\n"
        f"CURRENT USER MESSAGE:\n{_latest_user_turn_87(source)}\n\n"
        f"DRAFT TO REWRITE:\n{str(bad_answer or '')[:14000]}\n\n"
        f"FINAL REMINDER — {rule}"
    )


# Export the improved detector so later/runtime callers and Section 86 helpers
# use the same decision everywhere.
globals()["_latest_user_turn_87"] = _latest_user_turn_87
globals()["_detect_language_87"] = _detect_language_87
globals()["_detect_lang_86"] = _detect_language_87

# Older quiz/MCQ builders use `_is_bangla_text()` and previously recognised
# Bengali Unicode only. Route them through the same Banglish-aware decision so
# generated questions, poll explanations and verification explanations all use
# the seed/user language. English is English-only (the legacy bilingual rule is
# deliberately removed because it violated language mirroring).
def _is_bangla_text_87(text: str) -> bool:
    return _detect_language_87(text) == "bn"


def _quiz_language_rule_block_87(is_bn: bool) -> str:
    if is_bn:
        return (
            "The question/seed is Bangla or Banglish. Write every question, option, and "
            "explanatory sentence in natural Bangla script only; retain only technical terms, "
            "symbols, formulas, code, and proper nouns in English."
        )
    return (
        "The question/seed is English. Write every question, option, and explanation in "
        "English only; do not add a Bangla translation."
    )


def _quiz_schema_example_explanation_87(is_bn: bool) -> str:
    return "বাংলায় সংক্ষিপ্ত ব্যাখ্যা..." if is_bn else "Short explanation in English..."


globals()["_is_bangla_text"] = _is_bangla_text_87
globals()["_quiz_language_rule_block"] = _quiz_language_rule_block_87
globals()["_quiz_schema_example_explanation"] = _quiz_schema_example_explanation_87


_prev_solver_87 = globals().get("_solve_text_with_preference")
_prev_prompt_backend_87 = globals().get("_try_gemini_text_backends")


def _solve_text_with_preference(model: str, problem_text: str,
                                scope: str = "private_academic"):  # noqa: F811
    """Enforce and verify language around the complete provider cascade."""
    if not callable(_prev_solver_87):
        raise RuntimeError("text solver unavailable")
    lang = _detect_language_87(problem_text)
    locked = _lock_input_87(problem_text, lang)
    answer, used_model = _prev_solver_87(model, locked, scope)
    answer = str(answer or "").strip()
    if answer and not _answer_matches_87(answer, lang) and callable(_prev_prompt_backend_87):
        with _cx87.suppress(Exception):
            repaired, repair_model = _prev_prompt_backend_87(
                _repair_prompt_87(problem_text, answer, lang), timeout_seconds=28,
            )
            repaired = str(repaired or "").strip()
            if repaired and _answer_matches_87(repaired, lang):
                return repaired, str(repair_model or used_model or "AI")
    return answer, used_model


if callable(_prev_solver_87):
    globals()["_solve_text_with_preference"] = _solve_text_with_preference


# Prompt builders are also wrapped at the final load position. This covers OCR
# and rescue paths even if an older function retained a builder reference.
for _builder_name87 in ("_build_solver_prompt", "_build_academic_rescue_prompt"):
    _old_builder87 = globals().get(_builder_name87)
    if not callable(_old_builder87):
        continue

    def _make_builder87(old_fn):
        def _wrapped(problem_text, scope="private_academic"):
            base = old_fn(problem_text, scope)
            return _lock_input_87(base, _detect_language_87(problem_text))
        return _wrapped

    globals()[_builder_name87] = _make_builder87(_old_builder87)

_old_ocr_builder87 = globals().get("_build_master_ocr_prompt")
if callable(_old_ocr_builder87):
    def _build_master_ocr_prompt(ocr_ctx, user_question: str,
                                 previous_answer: str = ""):  # noqa: F811
        base = _old_ocr_builder87(ocr_ctx, user_question, previous_answer)
        probe = str(user_question or "").strip()
        if not probe:
            with _cx87.suppress(Exception):
                probe = str((ocr_ctx or {}).get("clean_text") or "")[:2000]
        return _lock_input_87(base, _detect_language_87(probe))

    globals()["_build_master_ocr_prompt"] = _build_master_ocr_prompt


_log87("final language lock active: latest-turn detection + Banglish + output validation/repair "
       "+ MCQ/quiz language mirror")

# ===== END SECTION 87 =====