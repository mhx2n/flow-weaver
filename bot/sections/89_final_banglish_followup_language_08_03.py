# ──────────────────────────────────────────────────────────────────────────────
# Section 89 (2026-08-03) — Banglish follow-up language guarantee.
#
# Section 87 correctly locked ordinary Bangla/Banglish prompts, but reply-thread
# prompts use the marker ``User follow-up:``.  That marker was not extracted, so
# a long English question/history could outweigh short current turns such as
# ``Kivabe holo``, ``Tai daw`` or ``Eita ami bujhinai``.  Exact word matching
# also missed natural inflections (bujhinai, bujhlam, holo, korona, etc.).
#
# This final-load overlay changes only language selection/repair.  Commands,
# provider priority, rich delivery, OCR, quiz generation and owner flows remain
# untouched.
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx89
import re as _re89


def _log89(message: str) -> None:
    with _cx89.suppress(Exception):
        logger.info("[S89] %s", message)  # type: ignore[name-defined]


_BN_CHAR_89 = _re89.compile(r"[\u0980-\u09FF]")
_WORD_89 = _re89.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

# Explicit language requests always have priority over automatic mirroring.
_ASK_EN_89 = _re89.compile(
    r"(?:\bin\s+english\b|\benglish\s+(?:only|e|a|language|version|translation|answer)\b|"
    r"\b(?:write|reply|answer|explain|say|tell)\s+(?:it\s+)?in\s+english\b|"
    r"ইংরেজি(?:তে|য়|য়)?\s*(?:বল|বলো|লিখ|লিখো|দাও|উত্তর|ব্যাখ্যা|অনুবাদ))",
    _re89.I,
)
_ASK_BN_89 = _re89.compile(
    r"(?:\bin\s+(?:bangla|bengali)\b|\b(?:bangla|bengali)\s+(?:only|te|e|language|version|translation|answer)\b|"
    r"\b(?:write|reply|answer|explain|say|tell|bolo|bol|lekho|likho|dao|daw)\s+(?:it\s+)?in\s+(?:bangla|bengali)\b|"
    r"বাংলা(?:তে|য়|য়)?\s*(?:বল|বলো|লিখ|লিখো|দাও|উত্তর|ব্যাখ্যা|অনুবাদ))",
    _re89.I,
)

# Markers emitted by every known direct, OCR and conversation-history path.
# The right-most marker wins, which makes the current turn authoritative.
_TURN_MARKERS_89 = (
    "current user message:",
    "current message:",
    "user's follow-up question:",
    "user follow-up question:",
    "user's follow-up:",
    "user follow-up:",
    "follow-up question:",
    "follow up question:",
    "latest user message:",
    "new user message:",
    "user's request about this page:",
    "user's request:",
    "original user message:",
    "student question:",
    "user message:",
)
_TURN_BOUNDARIES_89 = (
    "\n\nprevious answer",
    "\n\nassistant answer",
    "\n\nfull ocr",
    "\n\nocr text",
    "\n\nconversation history",
    "\n\n---",
    "\n\nfinal reminder",
    "\n\nmandatory response language",
)


def _latest_user_turn_89(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    best_pos = -1
    best_marker = ""
    for marker in _TURN_MARKERS_89:
        pos = low.rfind(marker)
        if pos > best_pos:
            best_pos, best_marker = pos, marker
    current = raw[best_pos + len(best_marker):].strip() if best_pos >= 0 else raw
    current_low = current.lower()
    cuts = [current_low.find(boundary) for boundary in _TURN_BOUNDARIES_89]
    cuts = [cut for cut in cuts if cut > 0]
    if cuts:
        current = current[:min(cuts)].strip()
    return current[:3000] if current else raw[-3000:]


# Exact function words are intentionally conservative.  English technical terms
# can occur beside them without changing the language away from Bangla.
_BN_EXACT_89 = {
    "ami", "amake", "amar", "amader", "amra", "apni", "apnar", "apnake",
    "tumi", "tomar", "tomake", "tui", "tor", "se", "she", "tara",
    "ki", "kivabe", "kibhabe", "kemne", "kemon", "keno", "kano", "kn",
    "kothay", "kokhon", "kon", "konta", "konti", "kar", "kader",
    "eta", "eita", "aita", "ata", "ota", "oita", "egulo", "eigulo",
    "gulo", "gula", "sob", "shob", "kisu", "kichu", "ei", "oi",
    "dao", "daw", "den", "dewa", "diye", "diyo", "dibay", "diben",
    "bolo", "bolen", "bol", "likho", "lekho", "dekhao", "dekhaw",
    "hobe", "hoy", "holo", "hoilo", "hoise", "hoye", "hocche", "ache",
    "ase", "chilo", "nai", "nei", "na", "lagbe", "lagena", "parina",
    "tai", "tahole", "tobe", "kintu", "ar", "aro", "abar", "ektu",
    "onek", "shudhu", "sudhu", "tar", "jonno", "sathe", "theke",
    "moddhe", "majhe", "kache", "pore", "age", "akare", "vabe", "bhabe",
    "moto", "mot", "thik", "vul", "bhul", "naki", "ebong",
    "proshno", "prosno", "uttor", "somadhan", "shomadhan", "onko", "ongko",
    "porikkha", "porashona", "bishoy", "bisoy", "bisleshon", "chobi", "lekha",
}

# Productive Banglish stems catch spelling/tense variants without requiring an
# endless dictionary.  Stems are long enough to avoid ordinary English words.
_BN_STEMS_89 = (
    "bujh", "buj", "bujhi", "bujhla", "bujhini", "bujhinai",
    "kor", "koro", "kore", "korte", "korbo", "korben", "korona",
    "bol", "bolo", "bolen", "bolte", "bolbo",
    "likh", "lekh", "lekho", "likho",
    "dekh", "dekha", "dekhao", "dekhaw",
    "ban", "bana", "banaw", "banao", "banate",
    "saj", "shaj", "sajiye", "shajiye", "guch",
    "shikh", "sikh", "jan", "jano", "jani", "janina",
    "par", "pari", "parbo", "parina", "lag", "chai", "chao",
)
_BN_STRONG_89 = {
    "amake", "apnake", "tomake", "kivabe", "kibhabe", "kemne", "bujhinai",
    "bujhini", "jonno", "akare", "proshno", "prosno", "uttor", "somadhan",
    "shomadhan", "porikkha", "porashona", "tahole", "korona", "janina",
}


def _banglish_word_89(word: str) -> bool:
    value = str(word or "").lower()
    if value in _BN_EXACT_89:
        return True
    return len(value) >= 4 and any(value.startswith(stem) for stem in _BN_STEMS_89)


def _detect_language_89(text: str) -> str:
    current = _latest_user_turn_89(text)
    if not current:
        return "bn"
    if _ASK_EN_89.search(current):
        return "en"
    if _ASK_BN_89.search(current):
        return "bn"
    if _BN_CHAR_89.search(current):
        return "bn"

    words = [word.lower() for word in _WORD_89.findall(current)]
    if not words:
        return "bn"
    hits = [word for word in words if _banglish_word_89(word)]
    strong = sum(1 for word in words if word in _BN_STRONG_89 or word.startswith("bujh"))

    # Short conversational replies are common in Telegram. Two Banglish tokens
    # are decisive; one strong inflected token is enough in a very short turn.
    if len(hits) >= 2:
        return "bn"
    if strong >= 1 and len(words) <= 6:
        return "bn"
    if len(hits) >= 1 and len(words) <= 3:
        return "bn"
    # Longer mixed prompts need either multiple Banglish signals or a useful
    # signal density, protecting ordinary English prose from false positives.
    if len(hits) >= 3 or (len(hits) >= 2 and len(hits) / len(words) >= 0.12):
        return "bn"
    return "en"


# Replace every detector alias that older wrappers still resolve at call time.
globals()["_latest_user_turn_87"] = _latest_user_turn_89
globals()["_latest_user_turn_89"] = _latest_user_turn_89
globals()["_detect_language_87"] = _detect_language_89
globals()["_detect_language_89"] = _detect_language_89
globals()["_detect_lang_86"] = _detect_language_89
globals()["_detect_lang_81"] = _detect_language_89


def _is_bangla_text_89(text: str) -> bool:
    return _detect_language_89(text) == "bn"


globals()["_is_bangla_text"] = _is_bangla_text_89


# Section 87 already validates and repairs output.  Strengthen its matching rule
# so a provider cannot pass with an English paragraph plus a tiny Bangla label.
def _answer_matches_89(answer: str, lang: str) -> bool:
    body = str(answer or "").strip()
    if not body:
        return False
    if len(body) < 12:
        return True
    probe = _re89.sub(r"https?://\S+|```.*?```|`[^`]*`|\$.*?\$", " ", body, flags=_re89.S)
    bn = len(_BN_CHAR_89.findall(probe))
    latin = len(_re89.findall(r"[A-Za-z]", probe))
    if lang == "bn":
        return bn >= 12 and (bn >= 32 or bn / max(1, bn + latin) >= 0.18)
    return bn < 12 or bn / max(1, bn + latin) < 0.08


globals()["_answer_matches_87"] = _answer_matches_89
globals()["_answer_matches_89"] = _answer_matches_89


_log89("Banglish follow-up guarantee active: latest-turn extraction + inflection-aware detection")

# ===== END SECTION 89 =====