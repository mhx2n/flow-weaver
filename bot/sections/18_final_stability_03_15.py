# ──────────────────────────────────────────────────────────────────────────────
# Section: 18_final_stability_03_15
# Original lines: 9508..10204
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL STABILITY PATCH (2026-03-15) =====
GROUP_BOT_MESSAGE_TTL_SECONDS = 600

_DOT_COMMAND_LIKE_RE = re.compile(r"(?is)^\.[A-Za-z_][A-Za-z0-9_]*(?:@\w+)?(?:\s|$)")
_LEADING_SERIAL_RE = re.compile(r"^\s*\(?[0-9\u09E6-\u09EF]{1,4}\)?\s*[\.)।:\-]\s+(?=\S)")

_ADULT_CONTENT_RE = re.compile(
    r"(?is)(?:\b(?:18\+|xxx|nsfw|porn|porno|pornography|nude|naked|erotic|fetish|bdsm|blowjob|handjob|anal|oral sex|cum|dick|penis|vagina|boob|breast|nipples?|sex chat|send nudes?)\b|"
    r"সেক্স|পর্ন|পর্নো|নিউড|নগ্ন|অশ্লীল|যৌন|চুমু খাও|বেডরুম|ব্লোজব|ওরাল সেক্স|১৮\+)")

_SOCIAL_OFFTOPIC_RE = re.compile(
    r"(?is)(?:\b(?:hi|hello|hey|how are you|what are you doing|do you love me|girlfriend|boyfriend|crush|romantic|date|dating|marry me|relationship advice|movie recommendation|song recommendation)\b|"
    r"কেমন আছ|কি করছ|আমাকে ভালোবাস|গার্লফ্রেন্ড|বয়ফ্রেন্ড|ক্রাশ|রিলেশন|ডেটিং|বিয়ে করবে|মুভি সাজেস্ট|গান সাজেস্ট)")

_STUDY_HINT_RE = re.compile(
    r"(?is)(?:\b(?:math|mathematics|physics|chemistry|biology|botany|zoology|english|bangla|grammar|paragraph|essay|composition|translation|synonym|antonym|tense|noun|verb|adjective|preposition|"
    r"gk|general knowledge|ict|computer|programming|code|python|java|c\+\+|algorithm|mcq|quiz|exam|admission|board|class|chapter|homework|assignment|model test|"
    r"solve|solution|explain|explanation|definition|formula|theorem|derivative|integration|probability|matrix|vector|entropy|thermodynamics|iupac|mole|stoichiometry|organic|inorganic|"
    r"sentence correction|essay writing|translation|meaning|summarize|summary|proof)\b|"
    r"গণিত|ম্যাথ|পদার্থ|রসায়ন|কেমিস্ট্রি|জীববিজ্ঞান|বায়োলজি|বাংলা|ইংরেজি|ব্যাকরণ|অনুবাদ|রচনা|প্যারাগ্রাফ|সারাংশ|সাধারণ জ্ঞান|আইসিটি|কম্পিউটার|প্রোগ্রামিং|কোড|এমসিকিউ|কুইজ|পরীক্ষা|ভর্তি|বোর্ড|ক্লাস|অধ্যায়|হোমওয়ার্ক|অ্যাসাইনমেন্ট|মডেল টেস্ট|"
    r"সমাধান|ব্যাখ্যা|সংজ্ঞা|সূত্র|উপপাদ্য|ডেরিভেটিভ|ইন্টিগ্রাল|সম্ভাবনা|ম্যাট্রিক্স|ভেক্টর|এন্ট্রপি|তাপগতিবিদ্যা|মোল|আইইউপিএসি|সেন্টেন্স কারেকশন|meaning|explain)")

_GROUP_GENERAL_SYSTEM_PROMPT = """
YOU ARE A HELPFUL TELEGRAM GROUP ASSISTANT.

CORE RULES:
- Be friendly, clear, and concise.
- Safe for all ages.
- Never provide 18+, sexual, pornographic, or explicit content.
- If the request is adult/explicit, politely refuse.
- No hate, harassment, or dangerous illegal guidance.
- If the question is in Bangla, answer mainly in Bangla.
- If the question is in English, answer in English.
- Keep answers practical and readable for group chat.
- Academic questions should be answered carefully and clearly.
- Casual safe questions are allowed.
""".strip()


def _strip_leading_serial_once(text: str) -> str:
    return _LEADING_SERIAL_RE.sub("", text or "", count=1)


def _strip_leading_serials(text: str) -> str:
    s = str(text or "")
    while True:
        new_s = _strip_leading_serial_once(s)
        if new_s == s:
            return s
        s = new_s.lstrip()


def clean_common(text: str, user_id: int) -> str:
    if not text:
        return ""
    for phrase in get_user_filters(user_id):
        if phrase:
            text = text.replace(phrase, "")
    text = BRACKET_ANY_RE.sub("", text)
    text = _strip_leading_serials(text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def _strip_leading_quiz_noise(q: str) -> str:
    s = str(q or "").strip()
    while True:
        new_s = re.sub(r"^\s*\[[^\]]{1,80}\]\s*", "", s)
        if new_s == s:
            break
        s = new_s.strip()
    s = _strip_leading_serials(s)
    return s.strip()


def _contains_adult_content(text: str) -> bool:
    return bool(_ADULT_CONTENT_RE.search(str(text or "")))


def _looks_like_study_query(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    if _contains_adult_content(s):
        return False
    if _STUDY_HINT_RE.search(s):
        return True
    if re.search(r"[=+\-*/^]|\d+\s*(?:cm|mm|m|kg|g|mol|°C|K|Hz|V|A|N|J|W|Pa|mmHg|ohm|Ω)", s, re.IGNORECASE):
        return True
    if re.search(r"(?is)\b(?:what is|who is|why|how|explain|define|derive|prove|solve|find|calculate|translate|correct)\b", s):
        return not bool(_SOCIAL_OFFTOPIC_RE.search(s))
    if re.search(r"(?is)(কি|কী|কে|কেন|কিভাবে|কত|ব্যাখ্যা|সমাধান|সংজ্ঞা|সূত্র|অনুবাদ|শুদ্ধ কর|সংশোধন)", s):
        return not bool(_SOCIAL_OFFTOPIC_RE.search(s))
    return False


def _adult_refusal_text(src_text: str) -> str:
    if _is_bangla_text(src_text):
        return "দুঃখিত, ১৮+ বা explicit বিষয়ে এই বট কোনো উত্তর দেয় না।"
    return "Sorry, this bot does not provide 18+ or explicit responses."


def _private_study_only_text(src_text: str) -> str:
    if _is_bangla_text(src_text):
        return "ইনবক্সে শুধু পড়াশোনা বা একাডেমিক প্রশ্ন করা যাবে। সাধারণ/অফ-টপিক প্রশ্ন গ্রুপে করুন।"
    return "In inbox/private chat, only study or academic questions are allowed. Please ask general/off-topic questions in the group."


def _build_solver_prompt(problem_text: str, scope: str = "private_academic") -> str:
    scope = str(scope or "private_academic").lower()
    body = (problem_text or "").strip()
    if scope == "group_general":
        return (_GROUP_GENERAL_SYSTEM_PROMPT + "\n\nUser Message:\n" + body).strip()
    return (STRICT_SYSTEM_PROMPT + "\n\nUser Message:\n" + body).strip()


def _solve_text_via_prompt(prompt: str, preferred: str = "G") -> Tuple[str, str]:
    model = (preferred or "G").upper()
    if model == "P":
        try:
            out = query_ai(prompt)
            if out and str(out).strip():
                return str(out).strip(), "Perplexity"
        except Exception:
            pass
        model = "G"
    if model == "D":
        model = "G"
    try:
        out = gemini3_solve(prompt)
        if out and str(out).strip():
            return str(out).strip(), "Gemini"
    except Exception:
        pass
    if USE_PERPLEXITY_FALLBACK:
        try:
            alt = query_ai(prompt)
            if alt and str(alt).strip():
                return str(alt).strip(), "Perplexity"
        except Exception:
            pass
    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEY:
        try:
            return call_gemini_text_rest(prompt, timeout_seconds=18).strip(), "Gemini REST"
        except Exception:
            pass
    raise RuntimeError("AI backend is temporarily unavailable. Please try again.")


def _solve_text_with_preference(model: str, problem_text: str, scope: str = "private_academic") -> Tuple[str, str]:
    return _solve_text_via_prompt(_build_solver_prompt(problem_text, scope), preferred=model)


def _extract_command_name(text: str) -> str:
    t = (text or "").strip().split()[0] if (text or "").strip() else ""
    t = t.split("@")[0]
    return t.lstrip("/.").lower()


async def _reply_group_temporary(update: Update, context: ContextTypes.DEFAULT_TYPE, text_html: str) -> None:
    if not update.message or not update.effective_chat:
        return
    msg = await update.message.reply_text(text_html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if update.effective_chat.type in ("group", "supergroup"):
        asyncio.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [msg.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


async def _reply_group_ai_direct(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_text: str, scope: str = "group_general") -> None:
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    spinner = await update.message.reply_text("🤖 ভাবছি...")
    try:
        uid = update.effective_user.id if update.effective_user else 0
        answer, used_model = await _run_blocking(_role_of(uid), _solve_text_with_preference, "G", prompt_text, scope)
        if _contains_adult_content(answer):
            answer = _adult_refusal_text(prompt_text)
        if looks_like_programming_request(prompt_text) or looks_like_programming_request(answer):
            body_html = f"<pre>{h(answer[:3500])}</pre>"
        else:
            trimmed = answer[:3500] + ("..." if len(answer) > 3500 else "")
            body_html = h(trimmed)
        html = ui_box_html(f"AI Reply ({used_model})", body_html, emoji="🤖")
        await spinner.edit_text(html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        db_log("ERROR", "group_text_ai_failed", {"user_id": update.effective_user.id if update.effective_user else 0, "error": str(e)})
        fail_html = ui_box_html("Reply Failed", h("AI backend is temporarily unavailable. Please try again."), emoji="❌")
        with contextlib.suppress(Exception):
            await spinner.edit_text(fail_html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    finally:
        asyncio.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [spinner.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


async def _auto_delete_after(bot, chat_id: int, message_ids: list[int], delay_seconds: int = GROUP_BOT_MESSAGE_TTL_SECONDS) -> None:
    await asyncio.sleep(delay_seconds)
    for mid in message_ids:
        with contextlib.suppress(Exception):
            await bot.delete_message(chat_id=chat_id, message_id=mid)


async def send_solver_picker(update: Update, context: ContextTypes.DEFAULT_TYPE, problem_text: str, scope: Optional[str] = None) -> None:
    if not update.message or not update.effective_user:
        return
    problem_text = (problem_text or "").strip()
    if not problem_text:
        return
    scope = str(scope or ("group_general" if update.effective_chat and update.effective_chat.type in ("group", "supergroup") else "private_academic"))
    if _contains_adult_content(problem_text):
        await _reply_group_temporary(update, context, ui_box_html("Not Allowed", h(_adult_refusal_text(problem_text)), emoji="🚫"))
        return
    token = _make_token()
    store = _pending_store(context)
    uid = update.effective_user.id
    store[token] = {
        "uid": uid,
        "chat_id": update.effective_chat.id if update.effective_chat else uid,
        "kind": "text",
        "scope": scope,
        "payload": {"text": problem_text},
    }
    kb = _solver_picker_kb(token)
    msg = ui_box_html("Which AI model?", f"<code>{h(problem_text[:100])}</code>", emoji="🧠")
    sent = await update.message.reply_text(msg, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        asyncio.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [sent.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


async def send_poll_verify_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE, poll_payload: Dict[str, Any], msg_html: str) -> None:
    token = _make_token()
    store = _pending_store(context)
    uid = update.effective_user.id
    store[token] = {
        "uid": uid,
        "chat_id": update.effective_chat.id if update.effective_chat else uid,
        "kind": "poll",
        "scope": "academic_poll",
        "payload": poll_payload,
    }
    kb = _verify_kb(token, "G", "poll")
    sent = await update.message.reply_text(msg_html, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        asyncio.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [sent.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


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
        await _reply_group_temporary(update, context, ui_box_html("Not Allowed", h(_adult_refusal_text(user_text)), emoji="🚫"))
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
        if not _looks_like_study_query(prompt):
            await safe_reply(update, ui_box_html("Study Only", h(_private_study_only_text(prompt)), emoji="📚"))
            return
        await send_solver_picker(update, context, prompt, scope="private_academic")
        return

    await _reply_group_ai_direct(update, context, prompt, scope="group_general")


async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    uid = update.effective_user.id if update.effective_user else 0
    chat_id = int(update.effective_chat.id)
    if not is_group_ai_enabled(chat_id):
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    if is_banned(uid):
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    ok, missing = await user_meets_required_memberships(context, uid)
    if not ok and not (is_owner(uid) or is_admin(uid) or await _is_group_admin_user(context, chat_id, uid)):
        names = ", ".join(missing[:10]) if missing else "required channel/group"
        await _dm_text(context, uid, ui_box_html("Join Required", f"Please join: {h(names)}", emoji="⚠️"), reply_markup=_required_join_kb())
        with contextlib.suppress(Exception):
            await update.message.delete()
        return

    reply = update.message.reply_to_message
    inline = " ".join(context.args).strip()
    prompt = inline
    preview = inline or "Ask anything safe"
    kind = "text"
    payload = {}
    scope = "group_general"

    if reply and getattr(reply, 'poll', None):
        qtext, options, qexpl = _poll_text_for_sh(reply.poll)
        official_ans = 0
        with contextlib.suppress(Exception):
            if getattr(reply.poll, 'type', '') == 'quiz' and getattr(reply.poll, 'correct_option_id', None) is not None:
                official_ans = int(reply.poll.correct_option_id) + 1
        kind = "poll"
        scope = "academic_poll"
        payload = {
            "question": qtext,
            "options": options,
            "official_ans": official_ans,
            "official_expl": qexpl,
        }
        preview = qtext or preview
    else:
        if reply:
            base = (reply.text or reply.caption or "").strip()
            if inline and base:
                prompt = f"Context:\n{base}\n\nQuestion:\n{inline}"
            elif base:
                prompt = base
        if not (prompt or "").strip():
            await _dm_text(context, uid, ui_box_html("Usage", "Use <code>/sh your question</code> or reply to a message/quiz with <code>/sh</code>.", emoji="ℹ️"))
            with contextlib.suppress(Exception):
                await update.message.delete()
            return
        if _contains_adult_content(prompt):
            await _reply_group_temporary(update, context, ui_box_html("Not Allowed", h(_adult_refusal_text(prompt)), emoji="🚫"))
            return
        payload = {"text": prompt}
        preview = prompt

    token = _make_token()
    store = _pending_store(context)
    store[token] = {
        "uid": uid,
        "chat_id": chat_id,
        "kind": kind,
        "scope": scope,
        "payload": payload,
    }

    kb = _solver_picker_kb(token)
    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=ui_box_html("Which AI model?", f"<code>{h(preview[:100])}</code>", emoji="🧠"),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=kb,
        reply_to_message_id=(reply.message_id if reply else update.message.message_id),
        allow_sending_without_reply=True,
    )
    asyncio.create_task(_auto_delete_after(context.bot, chat_id, [sent.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


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
            raw_expl = str(result.get('explanation', '') or "")
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
            else:
                answer, _used = await _run_blocking(_role_of(uid), _solve_text_with_preference, model, problem_text, scope)
                if _contains_adult_content(answer):
                    answer = _adult_refusal_text(problem_text)
            if (is_admin(uid) or is_owner(uid)) and (looks_like_programming_request(problem_text) or looks_like_programming_request(answer)):
                msg_html = f"<pre>{h(answer)}</pre>"
            else:
                msg_html = h(answer)
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
            await q.edit_message_text(ui_box_text("Solve Failed", "AI backend is temporarily unavailable. Please try again.", emoji="❌"), parse_mode=ParseMode.HTML)
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
    await ok_html(update, "Solver Enabled", "Now send only study/academic questions in inbox. Off-topic or 18+ messages will not be answered here.\n\nTurn off anytime using <code>/solve_off</code>.", emoji="🧠")


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
        "4) Inbox/private is study-only.\n"
        "5) 18+ / explicit responses are always blocked."
    )
    msg = await update.message.reply_text(text)
    asyncio.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [msg.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))
    with contextlib.suppress(Exception):
        await update.message.delete()


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = getattr(update, 'my_chat_member', None)
    if not cmu:
        return
    try:
        old_status = cmu.old_chat_member.status
        new_status = cmu.new_chat_member.status
        chat = cmu.chat
        actor = cmu.from_user
    except Exception:
        return
    if new_status in ("member", "administrator") and old_status in ("left", "kicked") and chat.type in ("group", "supergroup"):
        await refresh_group_command_menu(context, chat.id)
        actor_name = actor.first_name if actor else "Admin"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📘 Tutorial", callback_data="tutorial:show")]])
        with contextlib.suppress(Exception):
            msg = await context.bot.send_message(
                chat_id=chat.id,
                text=f"ধন্যবাদ {h(actor_name)}, {h(BOT_BRAND)} বটটি group-এ add করার জন্য। Normal text, /sh বা .sh দিয়ে safe AI reply পাওয়া যাবে। Admin guide দেখতে নিচের button ব্যবহার করুন.",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            asyncio.create_task(_auto_delete_after(context.bot, chat.id, [msg.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


def _dot_command_pattern(command: str) -> str:
    return rf"(?is)^\.{re.escape(command)}(?:@\w+)?(?:\s|$)"


def _build_dot_command_handler(command: str, callback, base_filter=None):
    base = base_filter if base_filter is not None else filters.ALL
    pattern = _dot_command_pattern(command)

    async def _runner(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = getattr(update.message, 'text', '') or ''
        parts = text.strip()[1:].split() if text.strip().startswith('.') else []
        if not parts:
            return
        cmd = parts[0].split('@')[0].lower()
        if cmd != command.lower():
            return
        try:
            context.args = parts[1:]
        except Exception:
            setattr(context, 'args', parts[1:])
        await callback(update, context)
        raise ApplicationHandlerStop

    return MessageHandler(base & filters.Regex(pattern), _runner)


def _register_dual_command(app: Application, command: str, callback, base_filter=None, group: int = 0) -> None:
    try:
        app.add_handler(CommandHandler(command, callback, filters=base_filter), group=group)
    except TypeError:
        app.add_handler(CommandHandler(command, callback), group=group)
    app.add_handler(_build_dot_command_handler(command, callback, base_filter=base_filter), group=group)


async def group_command_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    cmd = _extract_command_name(update.message.text or "")
    allowed = {"probaho_on", "probaho_off", "sh", "porag", "tutorial"}
    if cmd and (update.message.text or "").strip().startswith("/") and cmd not in allowed:
        raise ApplicationHandlerStop


def build_app() -> Application:
    db_init()
    with contextlib.suppress(Exception):
        extra_db_init()
    from telegram.ext import ChatMemberHandler
    builder = ApplicationBuilder().token(BOT_TOKEN)
    try:
        builder = builder.concurrent_updates(64)
    except Exception:
        pass
    app = builder.build()

    private_filter = filters.ChatType.PRIVATE
    group_filter = (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
    non_dot_text = filters.TEXT & (~filters.COMMAND) & (~filters.Regex(_DOT_COMMAND_LIKE_RE.pattern))

    # Global guards
    app.add_handler(MessageHandler(filters.ALL, global_maintenance_guard), group=-100)
    app.add_handler(MessageHandler(_group_filter(filters.COMMAND), group_command_guard), group=-90)

    # Callbacks
    app.add_handler(CallbackQueryHandler(on_solver_callback, pattern=r"^solve:"))
    app.add_handler(CallbackQueryHandler(on_genquiz_callback, pattern=r"^genquiz:"))
    app.add_handler(CallbackQueryHandler(on_required_verify_callback, pattern=r"^req:verify$"))
    app.add_handler(CallbackQueryHandler(on_emoji_quiz_callback, pattern=r"^eq:"))
    app.add_handler(CallbackQueryHandler(on_image_react_callback, pattern=r"^imgreact:"))
    app.add_handler(CallbackQueryHandler(on_tutorial_callback, pattern=r"^tutorial:show$"))

    for cmd, cb in [
        ("start", cmd_start),
        ("help", cmd_help),
        ("commands", cmd_commands),
        ("features", cmd_features),
        ("ask", cmd_ask),
        ("scanhelp", cmd_scanhelp),
        ("vision_on", cmd_vision_on),
        ("vision_off", cmd_vision_off),
        ("solve_on", cmd_solve_on),
        ("solve_off", cmd_solve_off),
        ("explain_on", cmd_explain_on),
        ("explain_off", cmd_explain_off),
    ]:
        _register_dual_command(app, cmd, cb, private_filter)

    for cmd, cb in [
        ("quizprefix", cmd_quizprefix),
        ("quizlink", cmd_quizlink),
        ("addadmin", cmd_addadmin),
        ("removeadmin", cmd_removeadmin),
        ("grantall", cmd_grantall),
        ("revokeall", cmd_revokeall),
        ("grantvision", cmd_grantvision),
        ("revokevision", cmd_revokevision),
        ("ownerstats", cmd_ownerstats),
        ("users", cmd_users),
        ("maintenance_on", cmd_maintenance_on),
        ("maintenance_off", cmd_maintenance_off),
    ]:
        _register_dual_command(app, cmd, cb, private_filter)

    for cmd, cb in [
        ("filter", cmd_filter),
        ("done", cmd_done),
        ("clear", cmd_clear),
        ("buffercount", cmd_buffercount),
        ("addchannel", cmd_addchannel),
        ("listchannels", cmd_listchannels),
        ("removechannel", cmd_removechannel),
        ("setprefix", cmd_setprefix),
        ("setexplink", cmd_setexplink),
        ("post", cmd_post),
        ("postemoji", cmd_postemoji),
        ("emojipost", cmd_postemoji),
        ("imgreact", cmd_imgreact),
        ("broadcast", cmd_broadcast),
        ("adminpanel", cmd_adminpanel),
        ("reply", cmd_reply),
        ("close", cmd_close),
        ("ban", cmd_ban),
        ("unban", cmd_unban),
        ("banned", cmd_banned),
        ("private_send", cmd_private_send),
        ("send_private", cmd_private_send),
        ("usersd", cmd_usersd),
        ("addrequired", cmd_addrequired),
        ("delrequired", cmd_delrequired),
        ("listrequired", cmd_listrequired),
        ("himusai_on", cmd_himusai_on),
        ("himusai_off", cmd_himusai_off),
    ]:
        _register_dual_command(app, cmd, cb, private_filter)

    for cmd, cb in [
        ("probaho_on", cmd_probaho_on),
        ("probaho_off", cmd_probaho_off),
        ("sh", cmd_sh),
        ("porag", cmd_porag),
        ("tutorial", cmd_tutorial),
    ]:
        _register_dual_command(app, cmd, cb, group_filter)

    # Private message handlers
    app.add_handler(MessageHandler(_private_filter(filters.POLL), handle_poll))
    app.add_handler(MessageHandler(_private_filter(filters.POLL), handle_user_poll_solver), group=1)
    app.add_handler(MessageHandler(_private_filter(filters.PHOTO), handle_image))
    app.add_handler(MessageHandler(_private_filter(filters.Document.IMAGE), handle_image))
    app.add_handler(MessageHandler(_private_filter(non_dot_text), handle_text))
    app.add_handler(MessageHandler(_private_filter(non_dot_text), handle_user_text_unusual), group=1)

    # Group AI handlers
    app.add_handler(MessageHandler(_group_filter(filters.POLL), handle_user_poll_solver), group=1)
    app.add_handler(MessageHandler(_group_filter(non_dot_text), handle_user_text_unusual), group=1)
    app.add_handler(ChatMemberHandler(on_my_chat_member, chat_member_types=ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_error_handler(on_error)
    return app

# ===== END FINAL STABILITY PATCH =====


