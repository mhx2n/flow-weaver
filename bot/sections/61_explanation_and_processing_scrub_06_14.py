# ──────────────────────────────────────────────────────────────────────────────
# Section 61 (2026-06-14) — Two focused polish fixes, no behaviour change.
#
# 1) Scrub user-visible "Mistral / Mistral OCR / Scanning Page / Reading the
#    image with Mistral OCR..." technical phrasing from processing cards. The
#    OCR engine is still Mistral — we just don't expose the brand name to the
#    chat UI for owner OR users. They see neutral wording like "Scanning Image"
#    / "Reading the image...".
#
# 2) Strip junk prefixes from every quiz explanation BEFORE it is sent as the
#    poll's explanation text. Removes things like:
#       • "Option 4 is correct because ..."
#       • "সঠিক উত্তর হলো ৪ নম্বর অপশন। ..."
#       • "এটাই সঠিক অপশন কারণ ..."
#       • "উদ্দীপক থেকে ..." / "উদ্দিপক থেকে ..."
#       • "প্রমাণ: ..." / "প্রমাণ —"
#    The actual reasoning that follows is preserved; only the boilerplate lead
#    is removed. Applies to both owner and user-visible polls.
# ──────────────────────────────────────────────────────────────────────────────

import re as _re61


# ── 1) Neutralise processing-card wording ───────────────────────────────────

def _neutralize_proc_text_61(s: str) -> str:
    if not s:
        return s
    t = str(s)
    # Drop the brand entirely from user-facing chat copy
    t = _re61.sub(r"\s*with\s+Mistral\s+OCR\b", "", t, flags=_re61.IGNORECASE)
    t = _re61.sub(r"\s*via\s+Mistral\s+OCR\b", "", t, flags=_re61.IGNORECASE)
    t = _re61.sub(r"\bMistral\s+OCR\b", "OCR", t, flags=_re61.IGNORECASE)
    t = _re61.sub(r"\bMistral\b", "", t, flags=_re61.IGNORECASE)
    t = _re61.sub(r"\s{2,}", " ", t).strip()
    # "Scanning Page" → "Scanning Image" reads cleaner for users
    t = t.replace("Scanning Page", "Scanning Image")
    return t


try:
    _prev_processing_start_61 = _processing_start  # type: ignore[name-defined]
    _prev_processing_update_61 = _processing_update  # type: ignore[name-defined]
except Exception:
    _prev_processing_start_61 = None
    _prev_processing_update_61 = None


if _prev_processing_start_61 is not None:
    async def _processing_start(msg, title: str, detail: str):  # noqa: F811
        return await _prev_processing_start_61(
            msg, _neutralize_proc_text_61(title), _neutralize_proc_text_61(detail)
        )

if _prev_processing_update_61 is not None:
    async def _processing_update(proc_msg, title: str, detail: str):  # noqa: F811
        return await _prev_processing_update_61(
            proc_msg, _neutralize_proc_text_61(title), _neutralize_proc_text_61(detail)
        )


# ── 2) Strip explanation boilerplate prefixes ───────────────────────────────

# Patterns ordered: most specific first. Each removes a leading "tag" only.
_EXPL_PREFIX_PATTERNS_61 = [
    # English: "Option 4 is correct because", "Option B is correct because"
    _re61.compile(r"^\s*Option\s*[\w০-৯]+\s*(is|:)\s*correct(\s+because)?[\s:,.\-—–]*", _re61.IGNORECASE),
    _re61.compile(r"^\s*The\s+correct\s+(answer|option)\s+is\s*[\w০-৯]+[\s:,.\-—–]*", _re61.IGNORECASE),
    _re61.compile(r"^\s*Answer\s*[:=\-–—]\s*[\w০-৯]+[\s:,.\-—–]*", _re61.IGNORECASE),
    # Bangla: "সঠিক উত্তর হলো ৪ নম্বর অপশন।" / "সঠিক উত্তর: ক।"
    _re61.compile(r"^\s*সঠিক\s*উত্তর\s*(হলো|হল|হচ্ছে)?\s*[^।:\-—–\s]{0,8}\s*(নম্বর\s*অপশন|অপশন)?[।:,.\-—–\s]*"),
    _re61.compile(r"^\s*এটাই\s*সঠিক\s*(অপশন|উত্তর)\s*(কারণ)?[।:,.\-—–\s]*"),
    _re61.compile(r"^\s*[\w০-৯]{1,4}\s*নম্বর\s*অপশন\s*(সঠিক)?[।:,.\-—–\s]*"),
    _re61.compile(r"^\s*উত্তর\s*[:\-–—]\s*[^।\s]{0,8}[।:,.\-—–\s]*"),
    # "উদ্দীপক থেকে …" / "উদ্দিপক থেকে …" — drop the lead, keep the reason
    _re61.compile(r"^\s*উদ্দ[ীি]পক\s*(থেকে|হতে|অনুযায়ী|এর\s*আলোকে)?[।:,.\-—–\s]*"),
    _re61.compile(r"^\s*(উপরের|নিচের)\s*(আলোকে|তথ্য|চিত্র|উদ্দ[ীি]পক)[^।]{0,40}[।:,.\-—–\s]*"),
    # "প্রমাণ: …" / "প্রমাণ —"
    _re61.compile(r"^\s*প্রমাণ\s*[:\-–—]?\s*"),
]


def _strip_expl_prefix_61(text: str) -> str:
    if not text:
        return text
    t = str(text)
    for _ in range(4):  # remove stacked prefixes
        before = t
        for pat in _EXPL_PREFIX_PATTERNS_61:
            t = pat.sub("", t, count=1)
        t = t.strip()
        if t == before:
            break
    return t.strip(" ।,:;-–—") or text.strip()


# Wrap _hard_trim_expl (section 52) so every poll/buffer path benefits
try:
    _prev_hard_trim_expl_61 = _hard_trim_expl  # type: ignore[name-defined]
except Exception:
    _prev_hard_trim_expl_61 = None

if _prev_hard_trim_expl_61 is not None:
    def _hard_trim_expl(text: str) -> str:  # noqa: F811
        return _prev_hard_trim_expl_61(_strip_expl_prefix_61(str(text or "")))


# Also wrap _trim_expl_for_poll for any direct callers
try:
    _prev_trim_expl_for_poll_61 = _trim_expl_for_poll  # type: ignore[name-defined]
except Exception:
    _prev_trim_expl_for_poll_61 = None

if _prev_trim_expl_for_poll_61 is not None:
    def _trim_expl_for_poll(expl: str, link: str = "") -> str:  # noqa: F811
        return _prev_trim_expl_for_poll_61(_strip_expl_prefix_61(str(expl or "")), link)

# ===== END SECTION 61 =====