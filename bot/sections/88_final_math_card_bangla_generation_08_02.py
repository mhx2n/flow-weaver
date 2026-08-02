# ──────────────────────────────────────────────────────────────────────────────
# Section 88 (2026-08-02) — final math-card quality + quiz-language authority.
#
# This is deliberately a last-load overlay.  It leaves commands, buffers and
# owner workflows intact while correcting two runtime defects that survived the
# earlier patches:
#   • /qver selected only poll labels; OCR generation still followed English OCR;
#   • mixed prose such as "Divide numerator ... by x^2" was promoted wholesale
#     to TextMath, causing Telegram to concatenate words and clip long formulas.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx88
import re as _re88


def _log88(message: str, level: str = "info") -> None:
    with _cx88.suppress(Exception):
        getattr(logger, level)("[S88] %s", message)  # type: ignore[name-defined]


_BN_88 = _re88.compile(r"[\u0980-\u09FF]")
_WORD_88 = _re88.compile(r"[A-Za-z]{3,}")
_FENCE_88 = _re88.compile(r"\$\$([\s\S]+?)\$\$|(?<!\$)\$([^$\n]+?)\$(?!\$)")


def _generation_lang_88(source: str = "") -> str:
    """One authoritative language for stems, options, explanations and polls."""
    active = str(globals().get("_active_lang_81") or "").lower()
    if active in ("bn", "en"):
        return active
    # /qver is the persistent owner-facing language choice and must control the
    # generated content too, not merely the ক/খ or A/B labels.
    chooser = globals().get("_quiz_lang_78")
    if callable(chooser):
        with _cx88.suppress(Exception):
            chosen = str(chooser() or "").lower()
            if chosen in ("bn", "en"):
                return chosen
    detector = globals().get("_detect_language_87")
    if callable(detector):
        with _cx88.suppress(Exception):
            return "bn" if detector(source) == "bn" else "en"
    return "bn"


def _quiz_rule_88(lang: str) -> str:
    if lang == "en":
        return (
            "\n\nFINAL QUIZ LANGUAGE: ENGLISH ONLY. Every stem, option prose, and "
            "explanation must be English. Keep mathematics as complete valid LaTeX inside "
            "single $...$ fences. Give a concise, factually verified explanation showing "
            "the decisive calculation; verify that `answer` points to the exact result."
        )
    return (
        "\n\nFINAL QUIZ LANGUAGE: বাংলা ONLY (অবশ্যই মানতে হবে)। প্রতিটি প্রশ্নের নির্দেশনা, "
        "প্রতিটি অপশনের কথার অংশ এবং সম্পূর্ণ ব্যাখ্যা স্বাভাবিক বাংলা লিপিতে লিখবে। "
        "শুধু গাণিতিক চলক/সূত্র/প্রচলিত technical symbol ইংরেজি হতে পারে। সব সূত্র সম্পূর্ণ "
        "valid LaTeX হিসেবে এক জোড়া $...$-এর মধ্যে লিখবে; formula-এর ভেতরে prose লিখবে না। "
        "ব্যাখ্যায় সংক্ষেপে সঠিক substitution/ধাপ ও সিদ্ধান্ত দেখাবে এবং `answer` যে ঠিক সেই "
        "option-এর ফল—JSON দেওয়ার আগে পুনরায় হিসাব করে নিশ্চিত করবে।"
    )


# Apply the language at the real provider prompt, after every older prompt patch.
_old_fast_prompt_88 = globals().get("_make_fast_new_mcq_prompt_74")
if callable(_old_fast_prompt_88):
    def _make_fast_new_mcq_prompt_74(source_text, n, *, easy=0, medium=0, hard=0,
                                     avoid_text=""):  # noqa: F811
        base = _old_fast_prompt_88(
            source_text, n, easy=easy, medium=medium, hard=hard,
            avoid_text=avoid_text,
        )
        lang = _generation_lang_88(str(source_text or ""))
        return str(base or "") + _quiz_rule_88(lang) + (
            "\nNever output a broken fraction, an unmatched brace/parenthesis, a truncated "
            "stem, or an option that merely describes a method without being mathematically "
            "valid. Return all requested fields in compact JSON."
        )

    globals()["_make_fast_new_mcq_prompt_74"] = _make_fast_new_mcq_prompt_74


_old_normalise_88 = globals().get("_normalise_mcq_74")
if callable(_old_normalise_88):
    def _normalise_mcq_74(item):  # noqa: F811
        row = _old_normalise_88(item)
        if not isinstance(row, dict):
            return None
        lang = _generation_lang_88(str((item or {}).get("question") or ""))
        question = str(row.get("question") or "")
        explanation = str(row.get("explanation") or "")
        if lang == "bn":
            # Formula-only options are valid, but the stem and explanation must
            # carry real Bengali prose. Rejecting here makes the provider loop
            # continue instead of storing an English item despite the prompt.
            if len(_BN_88.findall(question)) < 5:
                return None
            if explanation and len(_BN_88.findall(explanation)) < 5:
                return None
        elif _BN_88.search(question + " " + explanation):
            return None
        return row

    globals()["_normalise_mcq_74"] = _normalise_mcq_74


_old_generate_sync_88 = globals().get("_generate_quizzes_from_ocr_sync")
if callable(_old_generate_sync_88):
    def _generate_quizzes_from_ocr_sync(ocr_ctx, desired, user_id):  # noqa: F811
        ctx = dict(ocr_ctx or {})
        source = str(ctx.get("clean_text") or ctx.get("raw_markdown") or "")
        lang = _generation_lang_88(source)
        previous = globals().get("_active_lang_81")
        globals()["_active_lang_81"] = lang
        # Put the lock in OCR text as well because several legacy provider paths
        # build their own prompt without calling the shared fast prompt builder.
        lock = _quiz_rule_88(lang)
        for key in ("clean_text", "raw_markdown"):
            if str(ctx.get(key) or "").strip():
                ctx[key] = str(ctx[key]) + lock
        try:
            return _old_generate_sync_88(ctx, desired, user_id)
        finally:
            globals()["_active_lang_81"] = previous

    globals()["_generate_quizzes_from_ocr_sync"] = _generate_quizzes_from_ocr_sync


# ── Strict rich math segmentation ─────────────────────────────────────────────

def _repair_math_88(value: str) -> str:
    repair = globals().get("_repair_latex_source_79")
    if callable(repair):
        with _cx88.suppress(Exception):
            return str(repair(value) or "").strip()
    return str(value or "").strip()


def _math_valid_88(value: str) -> bool:
    validator = globals().get("_math_ok_83")
    if callable(validator):
        with _cx88.suppress(Exception):
            return bool(validator(value))
    return bool(str(value or "").strip())


def _pure_bare_formula_88(line: str) -> bool:
    """Conservative fallback for unfenced OCR equations; never swallow prose."""
    text = str(line or "").strip()
    if not text or _BN_88.search(text):
        return False
    words = _WORD_88.findall(_re88.sub(r"\\[A-Za-z]+", "", text))
    # The old parser accepted arbitrary English sentences merely because x² or
    # '=' appeared. More than one ordinary word is prose, not a formula.
    if len(words) > 1:
        return False
    if not _re88.search(r"\\(?:frac|sqrt|int|sum|lim|sin|cos|tan|ln|log)\b|[=^_√∫]", text):
        return False
    return _math_valid_88(_repair_math_88(text))


def _rich_text_parts_88(text):
    """Only fenced or genuinely pure equations become native TextMath blocks."""
    normalise = globals().get("_normalise_fences_83")
    source = str(text or "")
    if callable(normalise):
        with _cx88.suppress(Exception):
            source = str(normalise(source) or source)
    parts = []
    cursor = 0
    for match in _FENCE_88.finditer(source):
        if match.start() > cursor:
            parts.append(source[cursor:match.start()])
        expr = _repair_math_88(match.group(1) or match.group(2) or "")
        if expr and _math_valid_88(expr):
            parts.append({"type": "mathematical_expression", "expression": expr})
        elif expr:
            parts.append(expr)
        cursor = match.end()
    if cursor < len(source):
        parts.append(source[cursor:])
    if not parts:
        parts = [source]

    final = []
    for part in parts:
        if not isinstance(part, str):
            final.append(part)
            continue
        lines = part.splitlines(keepends=True)
        for line in lines:
            stripped = line.strip()
            if stripped and _pure_bare_formula_88(stripped):
                expr = _repair_math_88(stripped)
                final.append({"type": "mathematical_expression", "expression": expr})
                if line.endswith("\n"):
                    final.append("\n")
            elif line:
                final.append(line)
    merged = []
    for part in final:
        if isinstance(part, str) and merged and isinstance(merged[-1], str):
            merged[-1] += part
        elif part != "":
            merged.append(part)
    return merged or [str(text or "")]


globals()["_rich_text_parts_79"] = _rich_text_parts_88
globals()["_rich_text_parts_83"] = _rich_text_parts_88
globals()["_rich_text_parts_88"] = _rich_text_parts_88


_BN_LABELS_88 = ["ক", "খ", "গ", "ঘ", "ঙ", "চ", "ছ", "জ", "ঝ", "ঞ"]
_EN_LABELS_88 = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]


def _rich_math_blocks_88(question, options, lang="bn"):
    """XeneX-style clean hierarchy: heading, stem, divider, spaced options."""
    active = "en" if str(lang).lower() == "en" else "bn"
    labels = _EN_LABELS_88 if active == "en" else _BN_LABELS_88
    stem_repair = globals().get("_repair_stem_83")
    stem = str(question or "").strip()
    if callable(stem_repair):
        with _cx88.suppress(Exception):
            stem = str(stem_repair(stem) or stem)
    title = "Question" if active == "en" else "প্রশ্ন"
    blocks = [
        {"type": "paragraph", "text": [title]},
        {"type": "paragraph", "text": _rich_text_parts_88(stem) or [stem]},
        {"type": "divider"},
    ]
    for index, option in enumerate(options or []):
        raw = str(option or "").strip()
        if not raw:
            continue
        label = labels[index] if index < len(labels) else str(index + 1)
        blocks.append({
            "type": "paragraph",
            "text": ["(" + label + ")  "] + (_rich_text_parts_88(raw) or [raw]),
        })
    return blocks


globals()["_rich_math_blocks_79"] = _rich_math_blocks_88
globals()["_rich_math_blocks_83"] = _rich_math_blocks_88
globals()["_rich_math_blocks_88"] = _rich_math_blocks_88


_log88("final math card active: quiz language follows /qver; mixed prose is never TextMath")

# ===== END SECTION 88 =====