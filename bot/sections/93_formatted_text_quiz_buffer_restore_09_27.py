# ──────────────────────────────────────────────────────────────────────────────
# Section 93 (2026-09-27) — formatted text → quiz-buffer reliability layer.
#
# Restores owner/admin plain-text MCQ imports while preserving LaTeX and square
# bracket content. Loaded last so older auto-buffer and parser patches continue
# to work through this stricter compatibility layer.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx93
import re as _re93


_BN_DIGITS_93 = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_OPTION_TO_ANSWER_93 = {
    "a": 1, "b": 2, "c": 3, "d": 4, "e": 5,
    "ক": 1, "খ": 2, "গ": 3, "ঘ": 4, "ঙ": 5,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
}
_QUESTION_START_93 = _re93.compile(r"(?m)^\s*([0-9০-৯]{1,4})\s*[.)।:-]\s+")
_OPTION_LINE_93 = _re93.compile(
    r"^\s*[\(\[]?\s*([a-eA-Eকখগঘঙ1-5১-৫])\s*[\)\]]\s*(?:[.)।:-]\s*)?(.*?)\s*$"
)
_EXPLANATION_LINE_93 = _re93.compile(
    r"^\s*(?:ব্যাখ্যা|সমাধান|explanation|solution|reason|note)\s*[:ঃ\-–—]?\s*(.*)$",
    _re93.I,
)
_ANSWER_LINE_93 = _re93.compile(
    r"^\s*(?:সঠিক\s*উত্তর|উত্তর|answer|ans|correct\s*(?:answer|option)?)\s*[:ঃ=\-]?\s*"
    r"[\(\[]?\s*([a-eA-Eকখগঘঙ1-5১-৫])\s*[\)\]]?\s*$",
    _re93.I,
)


def _log93(message: str, level: str = "info") -> None:
    with _cx93.suppress(Exception):
        getattr(logger, level)("[S93] %s", message)  # type: ignore[name-defined]


def _normalise_newlines_93(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")


def _formatted_mcq_blocks_93(text: str):
    """Split numbered MCQs without treating LaTeX/brackets as syntax."""
    raw = _normalise_newlines_93(text)
    # Several exported/generated lists use a literal line containing only `n`.
    raw = _re93.sub(r"(?im)^\s*n\s*$", "\n", raw)
    starts = list(_QUESTION_START_93.finditer(raw))
    if starts:
        return [raw[m.start(): starts[i + 1].start() if i + 1 < len(starts) else len(raw)].strip()
                for i, m in enumerate(starts)]
    return [part.strip() for part in _re93.split(r"\n\s*\n+", raw) if part.strip()]


def _option_answer_93(token: str) -> int:
    value = str(token or "").strip().lower().translate(_BN_DIGITS_93)
    return int(_OPTION_TO_ANSWER_93.get(value, 0))


def _parse_formatted_mcq_93(block: str, user_id: int = 0):
    """Parse one MCQ and preserve all user-authored content inside [] and LaTeX."""
    lines = [line.strip() for line in _normalise_newlines_93(block).split("\n") if line.strip()]
    if not lines:
        return None

    source_no = ""
    first = _QUESTION_START_93.match(lines[0])
    if first:
        source_no = first.group(1).translate(_BN_DIGITS_93)
        lines[0] = lines[0][first.end():].strip()

    question_lines = []
    options = []
    explanation_lines = []
    answer = 0
    in_explanation = False

    for line in lines:
        explanation_match = _EXPLANATION_LINE_93.match(line)
        if explanation_match:
            in_explanation = True
            initial = (explanation_match.group(1) or "").strip()
            if initial:
                explanation_lines.append(initial)
            continue
        if in_explanation:
            explanation_lines.append(line)
            continue

        answer_match = _ANSWER_LINE_93.match(line)
        if answer_match:
            answer = _option_answer_93(answer_match.group(1)) or answer
            continue

        option_match = _OPTION_LINE_93.match(line)
        if option_match:
            option_text = (option_match.group(2) or "").strip()
            marked = bool(_re93.search(r"\*\s*$", option_text))
            if marked:
                option_text = _re93.sub(r"\*\s*$", "", option_text).rstrip()
            if option_text:
                options.append(option_text)
                if marked:
                    answer = len(options)
            continue

        if options:
            # Wrapped option lines are appended to the preceding option. This
            # preserves long formulas instead of silently moving them to stem.
            options[-1] = (options[-1] + "\n" + line).strip()
        else:
            question_lines.append(line)

    question = "\n".join(question_lines).strip()
    explanation = "\n".join(explanation_lines).strip()
    if not question or len(options) < 2 or not (1 <= answer <= len(options)):
        return None

    padded = options[:5] + [""] * max(0, 5 - len(options))
    return {
        "questions": question,
        "option1": padded[0], "option2": padded[1], "option3": padded[2],
        "option4": padded[3], "option5": padded[4],
        "answer": answer,
        "explanation": explanation,
        "type": 1,
        "section": 1,
        "source": "manual_text",
        "source_no": source_no,
    }


def _looks_like_formatted_mcq_93(text: str) -> bool:
    blocks = _formatted_mcq_blocks_93(text)
    return any(_parse_formatted_mcq_93(block) is not None for block in blocks)


# Keep the owner's explicit /autobuf off choice, but restore ON as the default.
def _autobuf_on() -> bool:  # noqa: F811
    try:
        value = str(get_setting("text_autobuf_on", "1") or "1").strip().lower()  # type: ignore[name-defined]
        return value in ("1", "on", "true", "yes")
    except Exception:
        return True


def _restore_autobuf_once_93() -> None:
    """Turn the feature back on once; later /autobuf choices still persist."""
    try:
        marker = str(get_setting("text_autobuf_restored_93", "") or "").strip()  # type: ignore[name-defined]
        if marker != "1":
            set_setting("text_autobuf_on", "1")  # type: ignore[name-defined]
            set_setting("text_autobuf_restored_93", "1")  # type: ignore[name-defined]
    except Exception as exc:
        _log93("could not persist one-time auto-buffer restore: %s" % type(exc).__name__, "warning")


def split_blocks(text: str):  # noqa: F811
    return _formatted_mcq_blocks_93(text)


def parse_text_block(block: str, user_id: int):  # noqa: F811
    return _parse_formatted_mcq_93(block, user_id)


_prev_handle_text_93 = globals().get("handle_text")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
    message = getattr(update, "message", None)
    text = str(getattr(message, "text", "") or "")
    # Avoid stealing normal AI conversations even when auto-buffer is enabled.
    if not _looks_like_formatted_mcq_93(text):
        return None
    if not callable(_prev_handle_text_93):
        return None
    return await _prev_handle_text_93(update, context)


globals()["_autobuf_on"] = _autobuf_on
globals()["split_blocks"] = split_blocks
globals()["parse_text_block"] = parse_text_block
globals()["handle_text"] = handle_text

_restore_autobuf_once_93()
_log93("formatted text quiz auto-buffer restored with bracket-safe parsing")

# ===== END SECTION 93 =====