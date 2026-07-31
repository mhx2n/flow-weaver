# ──────────────────────────────────────────────────────────────────────────────
# Section: 19_private_group_ai_format_03_15c
# Original lines: 10205..10700
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL PRIVATE/GROUP AI FORMAT PATCH (2026-03-15c) =====

_PRIVATE_INFO_HINT_RE = re.compile(
    r"(?is)(?:\b(?:news|headline|headlines|latest|latest news|today(?:'s)? news|current affairs?|current affair|event|events|schedule|routine|exam date|result|results|notice|weather|temperature|time|date|calendar|today|tomorrow|holiday|festival|ramadan|eid|iftar|sehri|namaz|prayer time|match|score|update|updates)\b|"
    r"খবর|দিনের খবর|আজকের খবর|সর্বশেষ|সাম্প্রতিক|নতুন আপডেট|ইভেন্ট|আজ|আগামীকাল|তারিখ|সময়|সময়|কয়টা বাজে|কটা বাজে|এখন কয়টা|এখন কটা|আবহাওয়া|তাপমাত্রা|নোটিশ|রুটিন|ফলাফল|রেজাল্ট|পরীক্ষার তারিখ|ছুটি|উৎসব|রমজান|রোজা|ঈদ|ইফতার|সেহরি|নামাজের সময়|নামাজের সময়|ম্যাচ|স্কোর|আপডেট)")

_PRIVATE_HARD_OFFTOPIC_RE = re.compile(
    r"(?is)(?:\b(?:hi|hello|hey|yo|sup|how are you|what are you doing|do you love me|love me|girlfriend|boyfriend|crush|romantic|date|dating|marry me|marriage|wedding|relationship|relationship advice|future partner|love life|joke|funny|meme|story|poem|song|movie|roast|flirt|developer|owner|about bot|who are you)\b|"
    r"কেমন আছ|কি করছ|কী করছ|আমাকে ভালোবাস|গার্লফ্রেন্ড|বয়ফ্রেন্ড|বয়ফ্রেন্ড|ক্রাশ|রিলেশন|সম্পর্ক|ডেটিং|বিয়ে|বিয়ে|বউ|স্বামী|ভবিষ্যৎ সঙ্গী|জোকস|মজা|গল্প|কবিতা|গান|মুভি|ফ্লার্ট|ডেভেলপার|ওনার|এই বটটা কি|তুমি কে)")

_PRIVATE_GREETING_ONLY_RE = re.compile(
    r"(?is)^\s*(?:hi|hello|hey|assalamualaikum|as-salamu alaikum|salam|ok|okay|thanks|thank you|আসসালামু আলাইকুম|সালাম|হ্যালো|হাই|ধন্যবাদ|ওকে)\s*[!.?]*\s*$"
)

_PRIVATE_INFO_SYSTEM_PROMPT = """
YOU ARE A SAFE AND USEFUL TELEGRAM PRIVATE-CHAT ASSISTANT.

RULES:
- Answer useful, factual, and non-personal questions only.
- Allowed: study questions, general knowledge, news/event summaries, time/date/weather, notices, schedules, and similar practical information.
- Not allowed: personal chit-chat, flirting, romance, relationship advice, marriage prediction, roleplay, or 18+ content.
- If the message is only a greeting or casual/off-topic personal talk, reply only with:
  Bangla: অনুগ্রহ করে আপনার প্রশ্নটি পাঠান।
  English: Please send your question.
- If the question is in Bangla, answer mainly in Bangla.
- If the question is in English, answer in English.
- Keep answers concise, clean, and Telegram-friendly.
- No Markdown headings like # or ##.
- No LaTeX or ugly raw formula formatting.
- Use short paragraphs. Use simple bullets only when needed.
- Do not mention that you are an AI unless the user explicitly asks.
""".strip()

_GROUP_GENERAL_SYSTEM_PROMPT = """
YOU ARE A SAFE TELEGRAM GROUP ASSISTANT.

RULES:
- Answer normal safe questions from any common topic.
- Never provide 18+, sexual, pornographic, or explicit content.
- If the request is adult/explicit, politely refuse.
- If the question is in Bangla, answer mainly in Bangla.
- If the question is in English, answer in English.
- Keep responses practical, readable, and Telegram-friendly.
- No Markdown headings like # or ##.
- No LaTeX or ugly raw formula formatting.
- Use short paragraphs and simple bullets when helpful.
- Be natural, but do not become romantic, explicit, or creepy.
""".strip()


def clean_latex(text: str) -> str:
    """Clean LaTeX-ish output while preserving readable Telegram line breaks."""
    if not text:
        return ""

    s = str(text).replace("\r\n", "\n").replace("\r", "\n")

    # Unwrap common LaTeX text commands.
    for _ in range(3):
        new_s = re.sub(r"\\(?:text|mathrm|mathbf|mathit|operatorname|textrm)\{([^{}]+)\}", r"\1", s)
        if new_s == s:
            break
        s = new_s

    # Fractions.
    for _ in range(3):
        new_s = re.sub(r"\\?frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1/\2)", s)
        if new_s == s:
            break
        s = new_s

    replacements = {
        r"\times": "×",
        r"\cdot": "·",
        r"\approx": "≈",
        r"\neq": "≠",
        r"\leq": "≤",
        r"\geq": "≥",
        r"\pm": "±",
        r"\mp": "∓",
        r"\rightarrow": "→",
        r"\leftarrow": "←",
        r"\infty": "∞",
        r"\degree": "°",
        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\theta": "θ",
        r"\pi": "π",
        r"\sigma": "σ",
        r"\Delta": "Δ",
        r"\omega": "ω",
        r"\lambda": "λ",
        r"\mu": "μ",
        r"\rho": "ρ",
    }
    for k, v in replacements.items():
        s = s.replace(k, v)

    s = s.replace("\\(", "").replace("\\)", "")
    s = s.replace("\\[", "").replace("\\]", "")
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("$", "")

    superscripts = {
        "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
        "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
        "+": "⁺", "-": "⁻", "(": "⁽", ")": "⁾",
        "n": "ⁿ", "i": "ⁱ",
    }
    subscripts = {
        "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
        "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
        "+": "₊", "-": "₋", "(": "₍", ")": "₎",
        "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ",
        "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ",
        "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
        "v": "ᵥ", "x": "ₓ",
    }

    def replace_sup(match):
        content = (match.group(1) or "").replace("{", "").replace("}", "")
        return "".join(superscripts.get(c, c) for c in content)

    def replace_sub(match):
        content = (match.group(1) or "").replace("{", "").replace("}", "")
        return "".join(subscripts.get(c, c) for c in content)

    s = re.sub(r"\^\{?([0-9A-Za-z+\-()]+)\}?", replace_sup, s)
    s = re.sub(r"_\{?([0-9A-Za-z+\-()]+)\}?", replace_sub, s)

    # Remove leftover escapes/backslashes.
    s = s.replace("\\", "")

    # Keep lines readable.
    lines = []
    for raw in s.split("\n"):
        line = raw.rstrip()
        line = re.sub(r"[ \t]+", " ", line)
        lines.append(line.strip())
    s = "\n".join(lines)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def _private_prompt_request_text(src_text: str) -> str:
    if _is_bangla_text(src_text):
        return "দয়া করে আপনার প্রশ্ন পাঠান।"
    return "Please send your question."


def _private_study_only_text(src_text: str) -> str:
    return _private_prompt_request_text(src_text)


def _classify_private_query_scope(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    if _contains_adult_content(s):
        return ""
    if _PRIVATE_GREETING_ONLY_RE.match(s):
        return ""
    if _PRIVATE_HARD_OFFTOPIC_RE.search(s):
        return ""

    if _STUDY_HINT_RE.search(s):
        return "private_academic"
    if re.search(r"[=+\-*/^]|\d+\s*(?:cm|mm|m|km|kg|g|mg|mol|°C|K|Hz|V|A|N|J|W|Pa|mmHg|ohm|Ω)", s, re.IGNORECASE):
        return "private_academic"

    if _PRIVATE_INFO_HINT_RE.search(s):
        return "private_info"

    if re.search(r"(?is)\b(?:what|who|when|where|which|current|today|latest|news|event|update|time|date|weather|notice|result|schedule)\b", s):
        return "private_info"
    if re.search(r"(?is)(কি|কী|কে|কখন|কোথায়|কোথায়|কোন|আজ|এখন|সাম্প্রতিক|সর্বশেষ|খবর|ইভেন্ট|আপডেট|সময়|সময়|তারিখ|আবহাওয়া|নোটিশ|রেজাল্ট|ফলাফল|রুটিন)", s):
        return "private_info"

    return ""


def _build_solver_prompt(problem_text: str, scope: str = "private_academic") -> str:
    scope = str(scope or "private_academic").lower()
    body = (problem_text or "").strip()
    if scope == "group_general":
        return (_GROUP_GENERAL_SYSTEM_PROMPT + "\n\nUser Message:\n" + body).strip()
    if scope == "private_info":
        return (_PRIVATE_INFO_SYSTEM_PROMPT + "\n\nUser Message:\n" + body).strip()
    extra = (
        "\n\nEXTRA TELEGRAM OUTPUT RULES:\n"
        "- No Markdown headings like # or ##.\n"
        "- No raw LaTeX, no dollar signs.\n"
        "- Keep the answer readable in Telegram.\n"
        "- Use short paragraphs.\n"
        "- Avoid unnecessary extra talk.\n"
    )
    return (STRICT_SYSTEM_PROMPT + extra + "\n\nUser Message:\n" + body).strip()


def _trim_for_telegram(text: str, max_chars: int = 3200) -> str:
    s = str(text or "").strip()
    if len(s) <= max_chars:
        return s
    cut = s[:max_chars]
    if "\n" in cut:
        cut = cut.rsplit("\n", 1)[0].rstrip()
    return cut.rstrip() + "\n..."


_SECTION_LINE_RE = re.compile(
    r"(?is)^(?:\d+[\).]\s*)?(answer|final answer|explanation|question|options|solution|summary|correct answer|"
    r"উত্তর|চূড়ান্ত উত্তর|চূড়ান্ত উত্তর|ব্যাখ্যা|প্রশ্ন|অপশন|সমাধান|সারাংশ|সঠিক উত্তর)\s*:?[\s]*$"
)


def _line_to_tg_html(raw_line: str) -> str:
    s = str(raw_line or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"[-–—]{3,}", s):
        return ""

    m = re.match(r"^#{1,6}\s*(.+)$", s)
    if m:
        return f"<b>{h(m.group(1).strip())}</b>"

    if _SECTION_LINE_RE.match(s):
        title = s.rstrip(": ")
        return f"<b>{h(title)}:</b>"

    bullet_prefix = ""
    bullet_match = re.match(r"^[*•\-]\s+(.*)$", s)
    if bullet_match:
        bullet_prefix = "• "
        s = bullet_match.group(1).strip()

    escaped = h(s)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return bullet_prefix + escaped


def _answer_to_tg_html(answer: str, *, model_name: str = "", preserve_code: bool = False) -> str:
    raw = _trim_for_telegram(str(answer or ""), 3200)
    if preserve_code:
        title = f"<b>{h(model_name)}</b>\n\n" if model_name else ""
        return title + f"<pre>{h(raw)}</pre>"

    cleaned = clean_latex(raw)
    cleaned = re.sub(r"```(?:[A-Za-z0-9_+-]+)?", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*>{1,3}\s?", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    out_lines = []
    if model_name:
        out_lines.append(f"<b>{h(model_name)}</b>")
        out_lines.append("")

    for raw_line in cleaned.split("\n"):
        html_line = _line_to_tg_html(raw_line)
        if html_line == "":
            if out_lines and out_lines[-1] != "":
                out_lines.append("")
            continue
        out_lines.append(html_line)

    html = "\n".join(out_lines).strip()
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html or h(raw)


def _model_display_name(model_code: str, fallback: str = "AI") -> str:
    code = str(model_code or "").upper()
    if code == "G":
        return "✨ Gemini"
    if code == "P":
        return "⚛ Perplexity"
    if code == "D":
        return "🔷 DeepSeek"
    return fallback


async def _reply_group_ai_direct(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_text: str, scope: str = "group_general") -> None:
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    spinner = await update.message.reply_text("🤖 ভাবছি...")
    try:
        uid = update.effective_user.id if update.effective_user else 0
        answer, used_model = await _run_blocking(_role_of(uid), _solve_text_with_preference, "G", prompt_text, scope)
        if _contains_adult_content(answer):
            answer = _adult_refusal_text(prompt_text)
        preserve_code = looks_like_programming_request(prompt_text) or looks_like_programming_request(answer)
        html = _answer_to_tg_html(answer, model_name=used_model or "AI", preserve_code=preserve_code)
        await spinner.edit_text(html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        db_log("ERROR", "group_text_ai_failed", {"user_id": update.effective_user.id if update.effective_user else 0, "error": str(e)})
        fail_html = h("AI backend is temporarily unavailable. Please try again.")
        with contextlib.suppress(Exception):
            await spinner.edit_text(fail_html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    finally:
        asyncio.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [spinner.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


async def handle_user_text_unusual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = update.effective_user.id
    if is_banned(uid):
        return
    role = get_role(uid)
    private = is_private_chat(update)

    if role == ROLE_USER:
        if private:
            if not solver_mode_on(uid):
                await warn_unauthorized(update, "This bot is currently restricted for staff operations. Please use /ask [message] for support.")
                return
            if not await enforce_required_memberships(update, context):
                return
        else:
            if not is_group_ai_enabled(update.effective_chat.id):
                return
            if not await enforce_required_memberships(update, context):
                return
    elif role in (ROLE_ADMIN, ROLE_OWNER):
        if private:
            if not solver_mode_on(uid):
                return
        else:
            if not is_group_ai_enabled(update.effective_chat.id):
                return
    else:
        return

    user_text = (update.message.text or "").strip()
    if not user_text:
        return

    if _contains_adult_content(user_text):
        if private:
            await safe_reply(update, h(_adult_refusal_text(user_text)))
        else:
            await _reply_group_temporary(update, context, h(_adult_refusal_text(user_text)))
        return

    reply_msg = update.message.reply_to_message
    prompt = user_text
    if reply_msg:
        ctx = _get_quiz_context(context, reply_msg.message_id)
        if not ctx and getattr(reply_msg, 'poll', None):
            poll = reply_msg.poll
            ctx = {
                "question": str(poll.question or "").strip(),
                "options": [str(o.text).strip() for o in (poll.options or []) if str(o.text or '').strip()],
                "official_ans": _poll_official_answer(poll),
                "official_expl": str(getattr(poll, 'explanation', '') or '').strip(),
            }
        if ctx:
            qtext = str(ctx.get("question", "") or "").strip()
            opts = ctx.get("options", []) or []
            prompt = f"Question:\n{qtext}\n\nOptions:\n" + "\n".join([f"{_safe_letter(i+1)}. {o}" for i, o in enumerate(opts)]) + f"\n\nUser follow-up:\n{user_text}"
        elif reply_msg.text or reply_msg.caption:
            base = (reply_msg.text or reply_msg.caption or "").strip()
            if base:
                prompt = f"Context:\n{base}\n\nUser message:\n{user_text}"

    if private:
        scope = _classify_private_query_scope(prompt)
        if not scope:
            await safe_reply(update, h(_private_prompt_request_text(prompt)))
            return
        await send_solver_picker(update, context, prompt, scope=scope)
        return

    await _reply_group_ai_direct(update, context, prompt, scope="group_general")


async def on_solver_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return
    q = update.callback_query
    await q.answer("Processing…", show_alert=False)
    data = (q.data or "").strip()
    m = re.match(r"^solve:([GPD]):([0-9a-f]{6,16})$", data)
    if not m:
        return
    model = m.group(1)
    token = m.group(2)
    store = _pending_store(context)
    req = store.get(token)
    if not isinstance(req, dict):
        with contextlib.suppress(Exception):
            await q.edit_message_text("⚠️ This request has expired. Please send your question again.")
        return
    uid = int(req.get("uid") or 0)
    if q.from_user and q.from_user.id != uid:
        with contextlib.suppress(Exception):
            await q.answer("This is not your request.", show_alert=True)
        return

    payload = req.get("payload") or {}
    problem_text = str(payload.get("text") or "").strip()
    kind = str(req.get("kind") or "text").lower()
    scope = str(req.get("scope") or ("group_general" if q.message and q.message.chat and q.message.chat.type in ("group", "supergroup") else "private_academic"))

    with contextlib.suppress(Exception):
        await q.edit_message_text(ui_box_text("Solving", "Please wait… Processing your request.", emoji="⏳"), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    try:
        if kind == "poll" and payload.get("question"):
            question = str(payload.get("question", "")).strip()
            options = payload.get("options", [])
            result, model_name = await _run_blocking(_role_of(uid), _solve_mcq_with_preference, model, question, options)
            raw_expl = str(result.get("explanation", "") or "")
            clean_expl = clean_latex(raw_expl)
            raw_why_not = result.get("why_not", {}) or {}
            clean_why_not = {k: clean_latex(v) for k, v in raw_why_not.items()}
            msg_html = _format_user_poll_solution(
                question=question,
                options=options,
                model_ans=int(result.get("answer", 0) or 0),
                official_ans=int(payload.get("official_ans", 0) or 0),
                model_expl=f"[{model_name}]\n{clean_expl}".strip(),
                official_expl=str(payload.get("official_expl", "")).strip(),
                why_not=clean_why_not,
                conf=int(result.get("confidence", 0) or 0),
            )
            kb = _verify_kb(token, model, "poll")
        else:
            if _contains_adult_content(problem_text):
                answer = _adult_refusal_text(problem_text)
                model_name = _model_display_name(model)
            else:
                answer, used_model = await _run_blocking(_role_of(uid), _solve_text_with_preference, model, problem_text, scope)
                if _contains_adult_content(answer):
                    answer = _adult_refusal_text(problem_text)
                model_name = used_model or _model_display_name(model)
            preserve_code = (is_admin(uid) or is_owner(uid)) and (looks_like_programming_request(problem_text) or looks_like_programming_request(answer))
            msg_html = _answer_to_tg_html(answer, model_name=model_name, preserve_code=preserve_code)
            kb = _verify_kb(token, model, "text")

        with contextlib.suppress(Exception):
            await q.edit_message_text(msg_html, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            if q.message and kind == "poll":
                _remember_quiz_context(context, q.message.message_id, payload)
            if q.message and q.message.chat and q.message.chat.type in ("group", "supergroup"):
                asyncio.create_task(_auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))
    except Exception as e:
        db_log("ERROR", "solver_callback_failed", {"user_id": uid, "model": model, "error": str(e)})
        with contextlib.suppress(Exception):
            await q.edit_message_text(h("AI backend is temporarily unavailable. Please try again."), parse_mode=ParseMode.HTML)
            if q.message and q.message.chat and q.message.chat.type in ("group", "supergroup"):
                asyncio.create_task(_auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


async def cmd_solve_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\n\nContact: {OWNER_CONTACT}")
        return
    if get_role(uid) != ROLE_USER:
        await warn(update, "Not Available", "Problem-solving chat is intended for normal users. Admin/Owner workflow should remain unchanged.")
        return
    set_solver_mode_on(uid, True)
    await ok_html(update, "Solver Enabled", "Now send your question in inbox. Academic and useful factual questions are allowed. Personal/off-topic chat and 18+ topics will not be answered.\n\nTurn off anytime using <code>/solve_off</code>.", emoji="🧠")


async def cmd_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    uid = update.effective_user.id if update.effective_user else 0
    if not await _is_group_admin_user(context, update.effective_chat.id, uid):
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    text = (
        "Group rules:\n"
        "1) Use /probaho_on or .probaho_on to enable group AI.\n"
        "2) Members can ask by normal text, reply, /sh, or .sh.\n"
        "3) Bot replies in group auto-delete after 10 minutes.\n"
        "4) Inbox/private keeps question-focused; personal/off-topic chat is filtered.\n"
        "5) 18+ / explicit responses are always blocked."
    )
    msg = await update.message.reply_text(text)
    asyncio.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [msg.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))
    with contextlib.suppress(Exception):
        await update.message.delete()

# ===== END FINAL PRIVATE/GROUP AI FORMAT PATCH =====


