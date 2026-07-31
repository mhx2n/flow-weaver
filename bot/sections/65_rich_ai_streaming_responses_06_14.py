# ──────────────────────────────────────────────────────────────────────────────
# Section: 65_rich_ai_streaming_responses_06_14
#
# Goal: Make AI text replies look like a real, modern AI assistant — rich
# Telegram Bot API 10.1 markup (headings, lists, blockquotes, bold/italic,
# tables, code), Unicode math, varied/natural structure, plus a streaming-
# style spinner that animates while the backend is solving.
#
# Scope: AI text answers ONLY. Quiz / MCQ / poll answering is left untouched.
# All previous behavior (verify keyboard, OCR quota footer, group/private
# routing, dedup) is preserved.
# ──────────────────────────────────────────────────────────────────────────────

import re as _re65
import asyncio as _asyncio65
import contextlib as _contextlib65


# ── 1. Rich, modern academic system prompt ────────────────────────────────
# Replaces the old "no markdown / no symbols / fixed 3-section" template
# with a far more natural, study-assistant style. Still strictly academic.

_RICH_PROMPT_65 = """
You are প্রবাহ — a senior, friendly academic tutor for admission &
exam students (HSC, BUET, Medical, Varsity, IBA, BCS). Behave like a top
private tutor: confident, clear, structured, and exam-focused.

LANGUAGE
• If the question is in Bangla → reply primarily in Bangla (≥70%), keep
  technical terms in English inside brackets where useful.
• If the question is in English → reply fully in English.
• Never mix Bangla into a purely English answer.

FORMAT — Telegram-rich Markdown (REQUIRED, looks great in this bot)
• Use **bold** for key terms, *italic* for emphasis, `code` for short
  formulas / variables, ```lang fenced code``` for programs/snippets.
• Use ## Heading and ### Subheading for sections when the answer has
  multiple parts. Short answers don't need headings.
• Use "- " bullets and "1. " numbered steps freely.
• Use > blockquote for a key insight, definition, or final takeaway.
• Use tables (| a | b |) when comparing 2+ items.
• Use --- on its own line to separate big sections only when it helps.
• Use ||spoiler|| only for "reveal the answer" prompts (optional).

MATH — Unicode, NOT LaTeX
• NEVER use `$`, `\\(`, `\\[`, `\\frac`, `^{}`, `_{}` or any LaTeX.
• Use real Unicode: x², x³, xⁿ, x₁, x₂, √, ∛, π, θ, α, β, Δ, ∑, ∏,
  ∫, ∂, ∞, ±, ×, ÷, ≈, ≠, ≤, ≥, →, ⇒, ⇔, ∈, ∉, ⊂, ∪, ∩, ∠, ⊥, ∥.
• Fractions: write as "a/b" or "(a)/(b)"; for big ones use a new line.
• Chemistry: H₂O, CO₂, Ag⁺ + Cl⁻ → AgCl↓, ΔH = −285 kJ/mol.

STRUCTURE — adapt to the question, don't force a template
• Direct/short factual question → 1–3 sentences, no headings.
• Concept question → short intro, then bullets / short sections.
• Numerical / proof problem → "Given", "Solution" (numbered steps),
  then a bold **Answer:** line at the end.
• MCQ-style → bold the correct option, then a short *why* explanation.
• "প্রশ্ন বানাও" / "generate questions" → ONLY questions, no answers.
• Routine / study-plan → a clean table or numbered schedule.

TONE
• Warm, encouraging, never robotic. Address the student naturally
  ("চলো ধাপে ধাপে দেখি", "Let's break this down").
• Never say "As an AI…", never introduce yourself unless explicitly
  asked who you are.
• No greetings unless the user greets first. If the user sends only
  "hi" / "hello", reply only:  অনুগ্রহ করে আপনার প্রশ্নটি পাঠান।

SAFETY
• Refuse only explicit illegal or 18+ content. Academic biology /
  medical / Islamic-history questions are allowed.
• Never output "بِسْمِ اللهِ…" or auto-religious phrases.

CONSISTENCY
• Don't contradict yourself in the same reply. If you correct an earlier
  step, say so briefly and give the corrected result.
""".strip()

try:
    globals()["STRICT_SYSTEM_PROMPT"] = _RICH_PROMPT_65  # noqa: F821
    logger.info("[Rich AI 65] STRICT_SYSTEM_PROMPT upgraded → rich markdown + Unicode math.")  # noqa: F821
except Exception:
    pass


# ── 2. Unicode math post-pass ────────────────────────────────────────────
# Converts any stray LaTeX or ASCII math the model emits into Unicode
# so the rendered Telegram message looks clean.

_SUP_65 = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUB_65 = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")

_GREEK_65 = {
    r"\\alpha": "α", r"\\beta": "β", r"\\gamma": "γ", r"\\delta": "δ",
    r"\\epsilon": "ε", r"\\theta": "θ", r"\\lambda": "λ", r"\\mu": "μ",
    r"\\pi": "π", r"\\rho": "ρ", r"\\sigma": "σ", r"\\tau": "τ",
    r"\\phi": "φ", r"\\omega": "ω", r"\\Delta": "Δ", r"\\Omega": "Ω",
    r"\\Sigma": "Σ", r"\\Pi": "Π", r"\\Theta": "Θ",
    r"\\infty": "∞", r"\\pm": "±", r"\\mp": "∓",
    r"\\times": "×", r"\\cdot": "·", r"\\div": "÷",
    r"\\leq": "≤", r"\\geq": "≥", r"\\neq": "≠", r"\\approx": "≈",
    r"\\to": "→", r"\\rightarrow": "→", r"\\Rightarrow": "⇒",
    r"\\leftrightarrow": "↔", r"\\in": "∈", r"\\notin": "∉",
    r"\\subset": "⊂", r"\\cup": "∪", r"\\cap": "∩",
    r"\\angle": "∠", r"\\perp": "⊥", r"\\parallel": "∥",
    r"\\int": "∫", r"\\sum": "∑", r"\\prod": "∏", r"\\partial": "∂",
    r"\\sqrt": "√", r"\\degree": "°", r"\\circ": "°",
}


def _unicode_math_65(text):
    if not text:
        return text
    s = str(text)
    # Strip inline / display LaTeX delimiters but keep the inside
    s = _re65.sub(r"\\\((.+?)\\\)", r"\1", s)
    s = _re65.sub(r"\\\[(.+?)\\\]", r"\1", s, flags=_re65.S)
    s = _re65.sub(r"\$\$(.+?)\$\$", r"\1", s, flags=_re65.S)
    s = _re65.sub(r"(?<!\\)\$([^\$\n]{1,200}?)\$", r"\1", s)

    # \frac{a}{b} → (a)/(b)
    s = _re65.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", s)
    # \sqrt{x} → √(x)
    s = _re65.sub(r"\\sqrt\s*\{([^{}]+)\}", r"√(\1)", s)
    # \text{...} → ...
    s = _re65.sub(r"\\text\s*\{([^{}]+)\}", r"\1", s)
    # Greek / operators
    for k, v in _GREEK_65.items():
        s = _re65.sub(k + r"(?![A-Za-z])", v, s)

    # x^{abc} / x^2  → superscripts
    def _sup_brace(m):
        return m.group(1).translate(_SUP_65)
    s = _re65.sub(r"\^\{([0-9n+\-=()]{1,8})\}", _sup_brace, s)
    s = _re65.sub(r"\^([0-9n])", lambda m: m.group(1).translate(_SUP_65), s)
    # x_{abc} / x_2 → subscripts
    s = _re65.sub(r"_\{([0-9+\-=()]{1,8})\}", lambda m: m.group(1).translate(_SUB_65), s)
    s = _re65.sub(r"(?<=[A-Za-zα-ωΑ-Ω0-9])_([0-9])", lambda m: m.group(1).translate(_SUB_65), s)

    # Tidy any leftover backslashes that were noise
    s = _re65.sub(r"\\,|\\;|\\!|\\:", " ", s)
    s = _re65.sub(r"\\\\", "\n", s)
    return s


# Wrap the existing renderer so every AI reply gets the math pass.
try:
    _orig_answer_html_65 = globals().get("_answer_to_tg_html")  # noqa: F821
except Exception:
    _orig_answer_html_65 = None


def _answer_to_tg_html_65(answer, *, model_name="", preserve_code=False):
    try:
        cleaned = _unicode_math_65(answer)
    except Exception:
        cleaned = answer
    if _orig_answer_html_65 is None:
        return str(cleaned)
    return _orig_answer_html_65(cleaned, model_name=model_name, preserve_code=preserve_code)


try:
    globals()["_answer_to_tg_html"] = _answer_to_tg_html_65
    logger.info("[Rich AI 65] Unicode-math post-pass wrapped renderer.")  # noqa: F821
except Exception:
    pass


# ── 3. Streaming-style spinner during solver run ─────────────────────────
# Wraps on_solver_callback so the user sees the message progressively
# update (analyzing → thinking → composing → finalizing) while the
# blocking backend call runs, then gets the final formatted answer.

_STREAM_FRAMES_65 = [
    ("🔍", "analyzing your question"),
    ("🧠", "thinking through the concept"),
    ("📚", "gathering the relevant theory"),
    ("✍️", "composing a clear explanation"),
    ("✨", "polishing the final answer"),
]


async def _stream_spinner_65(q, model_name, stop_event):
    """Edit the callback message every ~1.4s with a new 'thinking' frame
    until stop_event is set. Silently ignores all edit failures."""
    i = 0
    while not stop_event.is_set():
        emoji, label = _STREAM_FRAMES_65[i % len(_STREAM_FRAMES_65)]
        bar_len = (i % 5) + 1
        bar = "▰" * bar_len + "▱" * (5 - bar_len)
        text = (
            f"<b>{model_name}</b>\n"
            f"{emoji} <i>{label}…</i>\n"
            f"<code>{bar}</code>"
        )
        with _contextlib65.suppress(Exception):
            await q.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,  # noqa: F821
                disable_web_page_preview=True,
            )
        try:
            await _asyncio65.wait_for(stop_event.wait(), timeout=1.4)
        except _asyncio65.TimeoutError:
            pass
        i += 1


try:
    _orig_on_solver_cb_65 = globals().get("on_solver_callback")  # noqa: F821
except Exception:
    _orig_on_solver_cb_65 = None


if _orig_on_solver_cb_65 is not None:

    async def on_solver_callback(update, context):  # noqa: F811
        """Run the original solver with a live streaming spinner overlay."""
        q = getattr(update, "callback_query", None)
        if q is None:
            return await _orig_on_solver_cb_65(update, context)

        data_str = (q.data or "").strip()
        m = _re65.match(r"^solve:([GPD]):([0-9a-f]{6,16})$", data_str)
        if not m:
            return await _orig_on_solver_cb_65(update, context)

        # For poll/MCQ requests we keep the original UX (no spinner overlap)
        try:
            store = _pending_store(context)  # noqa: F821
            req = store.get(m.group(2)) or {}
            kind = str(req.get("kind") or "text").lower()
        except Exception:
            kind = "text"

        if kind != "text":
            return await _orig_on_solver_cb_65(update, context)

        model_name = _MODEL_NAMES.get(m.group(1), "AI")  # noqa: F821
        stop_event = _asyncio65.Event()
        spinner_task = _asyncio65.create_task(_stream_spinner_65(q, model_name, stop_event))
        try:
            return await _orig_on_solver_cb_65(update, context)
        finally:
            stop_event.set()
            with _contextlib65.suppress(Exception):
                await _asyncio65.wait_for(spinner_task, timeout=2.0)

    try:
        globals()["on_solver_callback"] = on_solver_callback
        logger.info("[Rich AI 65] Streaming spinner active around on_solver_callback.")  # noqa: F821
    except Exception:
        pass
