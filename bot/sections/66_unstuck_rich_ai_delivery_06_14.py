# ──────────────────────────────────────────────────────────────────────────────
# Section: 66_unstuck_rich_ai_delivery_06_14
#
# Goal: fix AI replies getting stuck on the animated "thinking" message and
# make study answers render as rich Telegram text with safe math/formula blocks.
# Scope: AI text replies only. Quiz / poll solving/export flows are preserved.
# ──────────────────────────────────────────────────────────────────────────────

import asyncio as _asyncio66
import contextlib as _contextlib66
import html as _html66
import re as _re66


# ── 1) Prompt override: remove old "plain/no markdown/no latex" rule ──────

_RICH_TELEGRAM_STUDY_PROMPT_66 = """
You are প্রবাহ — a premium academic study assistant for admission, HSC,
BUET, Medical, Varsity, IBA and BCS students.

Answer like a real expert tutor: clear, exam-focused, structured and concise.

LANGUAGE
• If the student writes Bangla, answer mainly in Bangla.
• If the student writes English, answer in English.
• Keep subject terms in English where students normally use them.

TELEGRAM RICH RESPONSE FORMAT
• Use Telegram-friendly Markdown: ## headings, **bold**, *italic*, `inline code`,
  ```code blocks```, bullets, numbered steps, blockquotes and compact tables.
• For long solutions, use: Given → Solution → Final Answer.
• For concept questions, use short sections and bullets.
• For generating practice questions, output only the requested questions unless
  the student asks for answers too.

MATH / FORMULA STYLE
• Telegram can show rich formatted text; write formulas cleanly and visibly.
• Use display formulas on separate lines with $$...$$ for complex math.
• Use simple readable math for short expressions: x², x₁, √, π, θ, Δ, ≥, ≤, →.
• Do not hide formulas inside long paragraphs.

QUALITY RULES
• No robotic intro like “As an AI”.
• No unnecessary motivation paragraph unless the student asks.
• If the answer is large, prioritize the main solution and final answer first.
""".strip()

try:
    globals()["STRICT_SYSTEM_PROMPT"] = _RICH_TELEGRAM_STUDY_PROMPT_66
except Exception:
    pass


def _build_solver_prompt(problem_text: str, scope: str = "private_academic") -> str:  # noqa: F811
    body = str(problem_text or "").strip()
    scope = str(scope or "private_academic").lower()
    base = globals().get("STRICT_SYSTEM_PROMPT", _RICH_TELEGRAM_STUDY_PROMPT_66)
    if scope == "group_general":
        base = globals().get("_GROUP_GENERAL_SYSTEM_PROMPT", base)
    elif scope == "private_info":
        base = globals().get("_PRIVATE_INFO_SYSTEM_PROMPT", base)
    extra = (
        "\n\nOUTPUT RULES FOR THIS BOT:\n"
        "- Use rich Telegram-friendly formatting, not plain wall text.\n"
        "- Use display formula blocks for important math.\n"
        "- Keep the first response useful even if Telegram needs multiple messages.\n"
        "- Do not mention formatting rules to the user.\n"
    )
    return f"{base}{extra}\n\nStudent question:\n{body}".strip()


# ── 2) Increase Gemini output budget for complete study answers ────────────

def _build_gemini_text_payload(prompt: str, *, force_json: bool = False):  # noqa: F811
    payload = {
        "contents": [{"role": "user", "parts": [{"text": str(prompt or "")}]}],
        "generationConfig": {
            "temperature": 0.18 if force_json else 0.35,
            "topP": 0.9,
            "maxOutputTokens": 4096 if force_json else 8192,
        },
    }
    if force_json:
        payload.setdefault("generationConfig", {})["responseMimeType"] = "application/json"
    return payload


# ── 3) Safer rich renderer: preserves markdown/math, avoids broken HTML ────

_SUP_66 = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUB_66 = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")

_LATEX_WORDS_66 = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "theta": "θ", "lambda": "λ", "mu": "μ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "phi": "φ", "omega": "ω", "Delta": "Δ", "Omega": "Ω",
    "infty": "∞", "pm": "±", "mp": "∓", "times": "×", "cdot": "·",
    "div": "÷", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
    "neq": "≠", "approx": "≈", "to": "→", "rightarrow": "→",
    "Rightarrow": "⇒", "leftrightarrow": "↔", "in": "∈", "notin": "∉",
    "subset": "⊂", "cup": "∪", "cap": "∩", "angle": "∠", "perp": "⊥",
    "parallel": "∥", "int": "∫", "sum": "∑", "prod": "∏", "partial": "∂",
    "sqrt": "√", "degree": "°", "circ": "°",
}


def _h66(value):
    try:
        return h(str(value))  # noqa: F821
    except Exception:
        return _html66.escape(str(value), quote=False)


def _light_latex_to_visible_66(text):
    s = str(text or "")
    s = _re66.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", s)
    s = _re66.sub(r"\\sqrt\s*\{([^{}]+)\}", r"√(\1)", s)
    s = _re66.sub(r"\\text\s*\{([^{}]+)\}", r"\1", s)
    for word, symbol in _LATEX_WORDS_66.items():
        s = _re66.sub(r"\\" + _re66.escape(word) + r"(?![A-Za-z])", symbol, s)
    s = _re66.sub(r"\^\{([0-9n+\-=()]{1,8})\}", lambda m: m.group(1).translate(_SUP_66), s)
    s = _re66.sub(r"\^([0-9n])", lambda m: m.group(1).translate(_SUP_66), s)
    s = _re66.sub(r"_\{([0-9+\-=()]{1,8})\}", lambda m: m.group(1).translate(_SUB_66), s)
    s = _re66.sub(r"(?<=[A-Za-zα-ωΑ-Ω0-9])_([0-9])", lambda m: m.group(1).translate(_SUB_66), s)
    s = _re66.sub(r"\\[,;!:]", " ", s)
    return s


def _sanitize_rich_answer_66(answer):
    raw = str(answer or "").strip()
    if not raw:
        return ""
    if raw.startswith("```") and raw.endswith("```") and "\n" in raw:
        return raw
    try:
        if globals().get("_looks_like_json_blob", lambda _x: False)(raw):
            data = globals().get("_extract_json_strict", lambda _x: None)(raw)
            if isinstance(data, dict):
                for key in ("explanation", "answer_text", "response", "text", "answer"):
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        raw = val.strip()
                        break
    except Exception:
        pass
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = _re66.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", raw)
    raw = _re66.sub(r"(?i)^as an ai[^\n]*\n+", "", raw).strip()
    raw = _re66.sub(r"\n{4,}", "\n\n", raw)
    return raw


def _answer_to_tg_html_66(answer, *, model_name="", preserve_code=False):
    raw = _sanitize_rich_answer_66(answer)
    if preserve_code:
        title = f"<b>{_h66(model_name)}</b>\n\n" if model_name else ""
        return title + f"<pre>{_h66(raw[:3600])}</pre>"

    raw = _light_latex_to_visible_66(raw)
    if len(raw) > 3600:
        raw = raw[:3550].rstrip() + "\n\n…"

    try:
        tokenised, store = _placeholder_tokens_64(raw)  # noqa: F821
        body_html = _render_blocks_64(tokenised)  # noqa: F821
        body_html = _restore_tokens_64(body_html, store)  # noqa: F821
    except Exception:
        body_html = _h66(raw)

    body_html = _re66.sub(r"\n{3,}", "\n\n", str(body_html or "")).strip()
    if model_name:
        body_html = f"<b>{_h66(model_name)}</b>\n\n{body_html}"
    return body_html or _h66(raw)


try:
    globals()["_answer_to_tg_html"] = _answer_to_tg_html_66
except Exception:
    pass


def _plain_from_html_66(html_text):
    plain = _re66.sub(r"<br\s*/?>", "\n", str(html_text or ""), flags=_re66.I)
    plain = _re66.sub(r"<[^>]+>", "", plain)
    return _html66.unescape(plain).strip()


def _split_answer_chunks_66(text, *, limit=2800, max_chunks=4):
    s = _sanitize_rich_answer_66(text)
    if not s:
        return [""]
    chunks = []
    while s and len(chunks) < max_chunks:
        if len(s) <= limit:
            chunks.append(s.strip())
            break
        cut = max(s.rfind("\n\n", 0, limit), s.rfind("\n", 0, limit), s.rfind("।", 0, limit), s.rfind(". ", 0, limit))
        if cut < int(limit * 0.55):
            cut = limit
        chunks.append(s[:cut].strip())
        s = s[cut:].strip()
    if s and chunks:
        chunks[-1] = chunks[-1].rstrip() + "\n\n…"
    return [c for c in chunks if c.strip()] or [""]


async def _edit_query_final_66(q, html_text, *, reply_markup=None, plain_fallback=""):
    try:
        return await q.edit_message_text(
            html_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,  # noqa: F821
            disable_web_page_preview=True,
        )
    except Exception as e:
        try:
            db_log("WARN", "rich_ai_html_edit_failed", {"error": str(e)[:220]})  # noqa: F821
        except Exception:
            pass
    plain = str(plain_fallback or _plain_from_html_66(html_text) or "উত্তর তৈরি হয়েছে, কিন্তু ফরম্যাটিং দেখাতে সমস্যা হয়েছে।").strip()
    if len(plain) > 3900:
        plain = plain[:3850].rstrip() + "\n…"
    try:
        return await q.edit_message_text(plain, reply_markup=reply_markup, disable_web_page_preview=True)
    except Exception:
        if getattr(q, "message", None):
            return await q.message.reply_text(plain, reply_markup=reply_markup, disable_web_page_preview=True)
        raise


async def _reply_extra_chunks_66(message, chunks):
    if not message:
        return
    for chunk in chunks:
        html_chunk = _answer_to_tg_html_66(chunk, model_name="", preserve_code=False)
        try:
            await message.reply_text(html_chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            await message.reply_text(_plain_from_html_66(html_chunk)[:3900], disable_web_page_preview=True)


# ── 4) Non-sticking streaming spinner + guaranteed final delivery ──────────

_STREAM_FRAMES_66 = [
    ("🔎", "Reading the question"),
    ("🧠", "Analyzing concepts"),
    ("📐", "Arranging formulas"),
    ("✍️", "Writing the solution"),
    ("✨", "Finalizing response"),
]


async def _stream_spinner_66(q, model_name, stop_event):
    i = 0
    while not stop_event.is_set():
        icon, label = _STREAM_FRAMES_66[i % len(_STREAM_FRAMES_66)]
        bar = "▰" * ((i % 5) + 1) + "▱" * (4 - (i % 5))
        text = f"<b>{_h66(model_name)}</b>\n{icon} <i>{_h66(label)}…</i>\n<code>{bar}</code>"
        with _contextlib66.suppress(Exception):
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        try:
            await _asyncio66.wait_for(stop_event.wait(), timeout=1.2)
        except _asyncio66.TimeoutError:
            pass
        i += 1


_previous_on_solver_callback_66 = globals().get("on_solver_callback")


async def on_solver_callback(update, context):  # noqa: F811
    q = getattr(update, "callback_query", None)
    if not q:
        if _previous_on_solver_callback_66:
            return await _previous_on_solver_callback_66(update, context)
        return
    data = (getattr(q, "data", "") or "").strip()
    m = _re66.match(r"^solve:([GPD]):([0-9a-f]{6,16})$", data)
    if not m:
        if _previous_on_solver_callback_66:
            return await _previous_on_solver_callback_66(update, context)
        return

    model, token = m.group(1), m.group(2)
    store = _pending_store(context)  # noqa: F821
    req = store.get(token)
    kind = str((req or {}).get("kind") or "text").lower() if isinstance(req, dict) else "text"

    # Preserve existing quiz / poll answer flow exactly.
    if kind != "text":
        if _previous_on_solver_callback_66:
            return await _previous_on_solver_callback_66(update, context)
        return

    await q.answer("Processing…", show_alert=False)
    if not isinstance(req, dict):
        return await _edit_query_final_66(q, "⚠️ This request has expired. Please send your question again.")

    uid = int(req.get("uid") or 0)
    if getattr(q, "from_user", None) and q.from_user.id != uid:
        return await q.answer("This is not your request.", show_alert=True)

    payload = req.get("payload") or {}
    problem_text = str(payload.get("text") or "").strip()
    scope = str(req.get("scope") or "private_academic")
    model_name = globals().get("_MODEL_NAMES", {}).get(model, globals().get("_model_display_name", lambda c: "AI")(model))

    stop_event = _asyncio66.Event()
    spinner_task = _asyncio66.create_task(_stream_spinner_66(q, model_name, stop_event))
    try:
        if _contains_adult_content(problem_text):  # noqa: F821
            answer = _adult_refusal_text(problem_text)  # noqa: F821
            used_model_name = globals().get("_model_display_name", lambda c: "AI")(model)
        else:
            answer, used_model_name = await _run_blocking(  # noqa: F821
                _role_of(uid),  # noqa: F821
                _solve_text_with_preference,  # noqa: F821
                model,
                problem_text,
                scope,
                timeout=95,
            )
            if _contains_adult_content(answer) and not _is_academic_safe_override(problem_text):  # noqa: F821
                answer = _adult_refusal_text(problem_text)  # noqa: F821
        # Always show the model the user picked, regardless of internal fallback
        used_model_name = model_name
        preserve_code = (is_admin(uid) or is_owner(uid)) and (looks_like_programming_request(problem_text) or looks_like_programming_request(answer))  # noqa: F821
        chunks = _split_answer_chunks_66(answer)
        first_html = _answer_to_tg_html_66(chunks[0], model_name=used_model_name, preserve_code=preserve_code)
        kb = _verify_kb(token, model, "text")  # noqa: F821
    except Exception as e:
        try:
            db_log("ERROR", "solver_callback_failed_66", {"user_id": uid, "model": model, "error": str(e)[:300]})  # noqa: F821
        except Exception:
            pass
        stop_event.set()
        with _contextlib66.suppress(Exception):
            await _asyncio66.wait_for(spinner_task, timeout=2.0)
        return await _edit_query_final_66(
            q,
            "<b>Reply Failed</b>\n\nThe AI backend is temporarily busy. Please try again shortly.",
            plain_fallback="Reply Failed\n\nThe AI backend is temporarily busy. Please try again shortly.",
        )
    finally:
        stop_event.set()
        with _contextlib66.suppress(Exception):
            await _asyncio66.wait_for(spinner_task, timeout=2.0)

    await _edit_query_final_66(q, first_html, reply_markup=kb, plain_fallback=chunks[0])
    await _reply_extra_chunks_66(getattr(q, "message", None), chunks[1:])

    with _contextlib66.suppress(Exception):
        if getattr(q, "message", None) and q.message.chat and q.message.chat.type == "private":
            thread_id = str(payload.get("thread_id") or "").strip()
            if not thread_id:
                thread_id = ai_thread_create(uid, q.message.chat.id, scope if str(scope).startswith("private") else "private_academic", origin="private")  # noqa: F821
                payload["thread_id"] = thread_id
                req["payload"] = payload
            source_user_text = str(payload.get("source_user_text") or problem_text or "").strip()
            source_message_id = int(payload.get("source_message_id") or (q.message.reply_to_message.message_id if q.message.reply_to_message else 0) or 0)
            source_reply_message_id = int(payload.get("source_reply_message_id") or 0)
            ai_thread_append_user_if_missing(thread_id, source_user_text, q.message.chat.id, source_message_id, source_reply_message_id)  # noqa: F821
            ai_thread_upsert_bot_answer(thread_id, answer, q.message.chat.id, q.message.message_id, source_message_id, model_code=model, model_name=used_model_name)  # noqa: F821
            upload_db_to_github(force=False)  # noqa: F821
        if getattr(q, "message", None) and q.message.chat and q.message.chat.type in ("group", "supergroup"):
            _asyncio66.create_task(_auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))  # noqa: F821


globals()["on_solver_callback"] = on_solver_callback


# ── 5) Group direct AI replies also use rich renderer and safe fallback ─────

async def _reply_group_ai_direct(update, context, prompt_text: str, scope: str = "group_general") -> None:  # noqa: F811
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    spinner = await update.message.reply_text("🧠 Thinking…")
    try:
        uid = update.effective_user.id if update.effective_user else 0
        answer, used_model = await _run_blocking(_role_of(uid), _solve_text_with_preference, "G", prompt_text, scope, timeout=95)  # noqa: F821
        if _contains_adult_content(answer):  # noqa: F821
            answer = _adult_refusal_text(prompt_text)  # noqa: F821
        chunks = _split_answer_chunks_66(answer, max_chunks=3)
        first_html = _answer_to_tg_html_66(chunks[0], model_name="Gemini", preserve_code=False)
        try:
            await spinner.edit_text(first_html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)  # noqa: F821
        except Exception:
            await spinner.edit_text(_plain_from_html_66(first_html)[:3900], disable_web_page_preview=True)
        await _reply_extra_chunks_66(spinner, chunks[1:])
    except Exception as e:
        try:
            db_log("ERROR", "group_text_ai_failed_66", {"user_id": update.effective_user.id if update.effective_user else 0, "error": str(e)[:300]})  # noqa: F821
        except Exception:
            pass
        with _contextlib66.suppress(Exception):
            await spinner.edit_text("Reply Failed\n\nThe AI backend is temporarily busy. Please try again shortly.")
    finally:
        _asyncio66.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [spinner.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))  # noqa: F821


try:
    logger.info("[Rich AI 66] Unstuck final delivery + rich Telegram study formatting active.")  # noqa: F821
except Exception:
    pass