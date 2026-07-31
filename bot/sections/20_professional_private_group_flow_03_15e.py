# ──────────────────────────────────────────────────────────────────────────────
# Section: 20_professional_private_group_flow_03_15e
# Original lines: 10701..11081
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== PROFESSIONAL PRIVATE/GROUP FLOW PATCH (2026-03-15e) =====

_PRIVATE_INFO_HINT_RE = re.compile(
    r"(?is)(?:\b(?:news|headline|headlines|latest|latest news|today(?:'s)? news|current affairs?|event|events|schedule|routine|exam date|result|results|notice|weather|temperature|time|date|day|calendar|today|tomorrow|holiday|festival|ramadan|eid|iftar|sehri|namaz|prayer time|match|score|update|updates|what day|which day|important date|meaning|what is called|what is known as|define|term)\b|"
    r"খবর|দিনের খবর|আজকের খবর|সর্বশেষ|সাম্প্রতিক|নতুন আপডেট|ইভেন্ট|আজ|আগামীকাল|তারিখ|সময়|সময়|আজকে কি বার|আজ কী বার|কয়টা বাজে|কটা বাজে|এখন কয়টা|এখন কটা|কত দিন বাকি|রোজার কয়দিন|রোজার কদিন|ঈদ কবে|এই তারিখটা কেন গুরুত্বপূর্ণ|আবহাওয়া|তাপমাত্রা|নোটিশ|রুটিন|ফলাফল|রেজাল্ট|পরীক্ষার তারিখ|ছুটি|উৎসব|রমজান|রোজা|ঈদ|ইফতার|সেহরি|নামাজের সময়|নামাজের সময়|ম্যাচ|স্কোর|আপডেট|কে কি বলে|কাকে কি বলে|মানে কী|মানে কি|অর্থ কী|অর্থ কি|সংজ্ঞা|কাকে বলে|কি বলে|কী বলে|কি বলা হয়|কী বলা হয়|"
    r"\b(?:aj|ajke|aaj|aajke|ekhon|koyta|kota|koita|kobe|rojar|eid|tarikh|somoy|shomoy|weather|temperature|notice|routine|result|meaning|mane ki|ki bole|kake bole|define|what day|which day)\b)"
)

_PRIVATE_HARD_OFFTOPIC_RE = re.compile(
    r"(?is)(?:\b(?:hi|hello|hey|yo|sup|how are you|what are you doing|do you love me|love me|girlfriend|boyfriend|crush|romantic|date|dating|marry me|marriage|wedding|relationship|relationship advice|future partner|love life|flirt|owner|developer|about bot|who are you|biye|bhalobasi|valobasi|gf|bf|relation|prem|premika|premik)\b|"
    r"কেমন আছ|কি করছ|কী করছ|আমাকে ভালোবাস|গার্লফ্রেন্ড|বয়ফ্রেন্ড|বয়ফ্রেন্ড|ক্রাশ|রিলেশন|সম্পর্ক|ডেটিং|বিয়ে|বিয়ে|বউ|স্বামী|ভবিষ্যৎ সঙ্গী|ফ্লার্ট|ডেভেলপার|ওনার|এই বটটা কি|তুমি কে)"
)

_PRIVATE_GREETING_ONLY_RE = re.compile(
    r"(?is)^\s*(?:hi|hello|hey|assalamualaikum|as-salamu alaikum|salam|ok|okay|thanks|thank you|আসসালামু আলাইকুম|সালাম|হ্যালো|হাই|ধন্যবাদ|ওকে)\s*[!.?]*\s*$"
)

_PRIVATE_GENERIC_QUESTION_RE = re.compile(
    r"(?is)(?:\?|\b(?:what|who|when|where|why|how|which|whom|whose|can|could|should|is|are|do|does|did|meaning|define|explain|solve|answer)\b|"
    r"\b(?:ki|kobe|koyta|kota|koita|keno|kivabe|kibhabe|kothay|mane|bole|bola hoy|kake bole|ki bole|what day|which day)\b|"
    r"(?:কি|কী|কে|কখন|কোথায়|কোথায়|কেন|কিভাবে|কীভাবে|কত|কয়টা|কয়টা|কবে|মানে|বলে|কাকে বলে|কি বলে|কী বলে|কাকে কি বলে))"
)

_PRIVATE_REPLY_CONTEXT_RE = re.compile(
    r"(?is)(?:^|\n)(?:question|options|user follow-?up|context)\s*:|(?:^|\n)[A-E][\).]\s+|(?:^|\n)[(]?[A-E][)]\s+"
)

_ROMANIZED_BANGLA_HINT_RE = re.compile(
    r"(?is)\b(?:ki|kobe|koyta|kota|koita|keno|kivabe|kibhabe|kothay|ajke|aajke|aj|aaj|ekhon|mane|bole|prodaho|roja|rojar|eid|somoy|shomoy)\b"
)

_PRIVATE_INFO_SYSTEM_PROMPT = """
YOU ARE A SAFE AND USEFUL TELEGRAM PRIVATE-CHAT ASSISTANT.

RULES:
- Answer useful, factual, and non-personal questions only.
- Allowed: study questions, general knowledge, news/event summaries, time/date/day, notices, schedules, results, weather, and similar practical questions.
- Not allowed: personal chit-chat, flirting, romance, relationship advice, marriage prediction, roleplay, or 18+ content.
- If the message is only a greeting or casual/off-topic personal talk, reply only with:
  Bangla: দয়া করে আপনার প্রশ্ন পাঠান।
  English: Please send your question.
- If the question is in Bangla, answer mainly in Bangla.
- If the question looks like Bangla written in English letters, answer in Bangla script when natural.
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
- Answer normal safe questions clearly and briefly.
- Never provide 18+, sexual, pornographic, or explicit content.
- If the request is adult/explicit, politely refuse.
- If the question is in Bangla, answer mainly in Bangla.
- If the question looks like Bangla written in English letters, answer in Bangla script when natural.
- If the question is in English, answer in English.
- Keep responses practical, readable, and Telegram-friendly.
- No Markdown headings like # or ##.
- No LaTeX or ugly raw formula formatting.
- Use short paragraphs and simple bullets when helpful.
- Be natural, but do not become romantic, explicit, or creepy.
""".strip()


def _looks_like_private_quiz_context(text: str) -> bool:
    s = str(text or "")
    if not s:
        return False
    if _PRIVATE_REPLY_CONTEXT_RE.search(s):
        return True
    if re.search(r"(?im)^\s*(?:[A-E][\).]|\(?[a-e]\))\s+", s):
        return True
    if re.search(r"(?is)(question\s*:.*options\s*:|প্রশ্ন\s*:.*অপশন)", s):
        return True
    return False


def _looks_like_useful_private_question(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    if _PRIVATE_INFO_HINT_RE.search(s):
        return True
    if _PRIVATE_GENERIC_QUESTION_RE.search(s):
        return True
    if re.search(r"(?is)\b(?:ki bole|kake bole|mane ki|meaning of|what is called|what is known as|define|explain|solve(?: please)?|answer(?: please)?|kobe|koyta|kota|koita|koto|keno|kivabe|kibhabe|kothay|ajke|aajke|ekhon|rojar|eid)\b", s):
        return True
    return False


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
    if _looks_like_private_quiz_context(s):
        return "private_academic"
    if _STUDY_HINT_RE.search(s):
        return "private_academic"
    if re.search(r"(?is)[=+\-*/^]|\d+\s*(?:cm|mm|m|km|kg|g|mg|mol|°C|K|Hz|V|A|N|J|W|Pa|mmHg|ohm|Ω)", s):
        return "private_academic"
    if _looks_like_useful_private_question(s):
        return "private_info"
    return ""


def _build_solver_prompt(problem_text: str, scope: str = "private_academic") -> str:
    scope = str(scope or "private_academic").lower()
    body = (problem_text or "").strip()
    common_extra = (
        "\n\nEXTRA TELEGRAM OUTPUT RULES:\n"
        "- No Markdown headings like # or ##.\n"
        "- No raw LaTeX, no dollar signs.\n"
        "- Keep the answer readable in Telegram.\n"
        "- Use short paragraphs.\n"
        "- Avoid unnecessary extra talk.\n"
        "- If the user message looks like Bangla written in English letters, answer in Bangla script when natural.\n"
    )
    if scope == "group_general":
        return (_GROUP_GENERAL_SYSTEM_PROMPT + common_extra + "\n\nUser Message:\n" + body).strip()
    if scope == "private_info":
        return (_PRIVATE_INFO_SYSTEM_PROMPT + common_extra + "\n\nUser Message:\n" + body).strip()
    return (STRICT_SYSTEM_PROMPT + common_extra + "\n\nUser Message:\n" + body).strip()


_original_handle_user_poll_solver = handle_user_poll_solver
async def handle_user_poll_solver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return
    return await _original_handle_user_poll_solver(update, context)


_original_handle_user_text_unusual = handle_user_text_unusual
async def handle_user_text_unusual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return
    return await _original_handle_user_text_unusual(update, context)


async def cmd_probaho_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    uid = update.effective_user.id if update.effective_user else 0
    if not chat or chat.type not in ("group", "supergroup"):
        if update.message:
            await warn(update, "Group Only", "Use this command inside a group/supergroup.")
        return
    if not await _is_group_admin_user(context, chat.id, uid):
        await _dm_text(context, uid, ui_box_html("Unauthorized", "Only a group admin or the bot owner can use this command.", emoji="⚠️"))
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    set_group_ai_enabled(chat.id, True)
    with contextlib.suppress(Exception):
        await update.message.delete()
    await _dm_text(
        context,
        uid,
        ui_box_html(
            "Group AI Enabled",
            f"Group: <code>{h(chat.id)}</code>\nMode: members can use <code>/sh</code> or <code>.sh</code> only. Reply to any message/quiz and send <code>/sh</code> or <code>.sh</code> to open model selection.",
            emoji="✅",
        ),
    )


async def cmd_probaho_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    uid = update.effective_user.id if update.effective_user else 0
    if not chat or chat.type not in ("group", "supergroup"):
        if update.message:
            await warn(update, "Group Only", "Use this command inside a group/supergroup.")
        return
    if not await _is_group_admin_user(context, chat.id, uid):
        await _dm_text(context, uid, ui_box_html("Unauthorized", "Only a group admin or the bot owner can use this command.", emoji="⚠️"))
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    set_group_ai_enabled(chat.id, False)
    with contextlib.suppress(Exception):
        await update.message.delete()
    await _dm_text(context, uid, ui_box_html("Group AI Disabled", f"Group: <code>{h(chat.id)}</code>\nThe <code>/sh</code> and <code>.sh</code> AI commands are now off in this group.", emoji="✅"))


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
        "2) Group members will get AI reply only with /sh or .sh.\n"
        "3) To use reply mode, reply to any message or poll and send /sh or .sh.\n"
        "4) Bot replies in group auto-delete after 10 minutes.\n"
        "5) Inbox/private shows model selection for allowed questions. Personal/off-topic chat and 18+ topics are filtered there."
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
        actor_name = actor.first_name if actor else "Admin"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📘 Tutorial", callback_data="tutorial:show")]])
        with contextlib.suppress(Exception):
            msg = await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"ধন্যবাদ {h(actor_name)}, {h(BOT_BRAND)} বটটি group-এ add করার জন্য। "
                    f"এই group-এ AI ব্যবহার করতে <code>/sh</code> বা <code>.sh</code> ব্যবহার করুন। "
                    f"কোনো message বা poll-এর reply দিয়েও <code>/sh</code> / <code>.sh</code> পাঠানো যাবে।"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            asyncio.create_task(_auto_delete_after(context.bot, chat.id, [msg.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


async def on_tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.message or not q.message.chat:
        return
    uid = q.from_user.id if q.from_user else 0
    if not await _is_group_admin_user(context, q.message.chat.id, uid):
        await q.answer("Only group admins can view the tutorial.", show_alert=True)
        return
    await q.answer()
    text = (
        "Group rules:\n"
        "1) Use /probaho_on or .probaho_on to enable group AI.\n"
        "2) Group members will get AI reply only with /sh or .sh.\n"
        "3) To use reply mode, reply to any message or poll and send /sh or .sh.\n"
        "4) Bot replies in group auto-delete after 10 minutes.\n"
        "5) Inbox/private shows model selection for allowed questions. Personal/off-topic chat and 18+ topics are filtered there."
    )
    with contextlib.suppress(Exception):
        await q.message.reply_text(text)


# Final app builder: private auto-solver only in inbox, group AI only through /sh or .sh.
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

    app.add_handler(MessageHandler(filters.ALL, global_maintenance_guard), group=-100)
    app.add_handler(MessageHandler(_group_filter(filters.COMMAND), group_command_guard), group=-90)

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

    # Private/inbox handlers only
    app.add_handler(MessageHandler(_private_filter(filters.POLL), handle_poll))
    app.add_handler(MessageHandler(_private_filter(filters.POLL), handle_user_poll_solver), group=1)
    app.add_handler(MessageHandler(_private_filter(filters.PHOTO), handle_image))
    app.add_handler(MessageHandler(_private_filter(filters.Document.IMAGE), handle_image))
    app.add_handler(MessageHandler(_private_filter(non_dot_text), handle_text))
    app.add_handler(MessageHandler(_private_filter(non_dot_text), handle_user_text_unusual), group=1)

    # Group side: command-only AI access
    app.add_handler(ChatMemberHandler(on_my_chat_member, chat_member_types=ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_error_handler(on_error)
    return app

# ===== END PROFESSIONAL PRIVATE/GROUP FLOW PATCH =====


