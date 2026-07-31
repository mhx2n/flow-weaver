# ──────────────────────────────────────────────────────────────────────────────
# Section: 17_ultra_group_maintenance_v6
# Original lines: 8980..9507
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== ULTRA GROUP/MAINTENANCE PATCH v6 =====
from telegram.ext import ApplicationHandlerStop

# Registry refresh
try:
    COMMANDS_REGISTRY.setdefault("public", {}).setdefault("commands", {}).update({
        "start": "Welcome / membership check (private only)",
        "help": "Show command guide (private only)",
        "commands": "Show available commands (private only)",
        "ask": "Contact support from inbox",
        "solve_on": "Enable private user AI solving",
        "solve_off": "Disable private user AI solving",
    })
    COMMANDS_REGISTRY.setdefault("admin", {}).setdefault("commands", {}).update({
        "buffercount": "Show total buffered quizzes",
        "postemoji": "Post buffered emoji quizzes to channel",
        "emojipost": "Alias of /postemoji",
        "imgreact": "Post image reaction quiz (reply to image)",
        "usersd": "Show stored user details",
        "probaho_on": "Enable /sh AI in current group",
        "probaho_off": "Disable /sh AI in current group",
        "porag": "Delete a replied message range in group",
        "tutorial": "Show group usage tutorial",
    })
    COMMANDS_REGISTRY.setdefault("owner", {}).setdefault("commands", {}).update({
        "maintenance_on": "Enable maintenance mode and notify users",
        "maintenance_off": "Disable maintenance mode and notify users",
    })
    if "workflow" in COMMANDS_REGISTRY:
        COMMANDS_REGISTRY["workflow"]["items"] = [
            "Private inbox only -> parse text / polls / images into buffer",
            "/done -> Export CSV and clear buffer",
            "/post <DB-ID> -> Publish normal quizzes to channel",
            "/postemoji <DB-ID> -> Publish emoji quizzes to channel",
            "Group mode: /probaho_on then members use /sh to ask AI",
        ]
except Exception:
    pass


def maintenance_mode_on() -> bool:
    return get_setting("maintenance_mode", "0") == "1"


def maintenance_message() -> str:
    return get_setting("maintenance_message", "Bot is under maintenance. Please try again later.")


def set_maintenance_mode(value: bool, message: str = "") -> None:
    set_setting("maintenance_mode", "1" if value else "0")
    if message is not None:
        set_setting("maintenance_message", message or "Bot is under maintenance. Please try again later.")


async def _dm_text(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str, reply_markup=None) -> bool:
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        return True
    except Exception:
        return False


async def _broadcast_private(context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    ids = [int(r[0]) for r in cur.fetchall()]
    conn.close()
    sent = 0
    for uid in ids:
        if await _dm_text(context, uid, text):
            sent += 1
        await asyncio.sleep(0.03)
    return sent


async def _auto_delete_after(bot, chat_id: int, message_ids: list[int], delay_seconds: int = 300) -> None:
    await asyncio.sleep(delay_seconds)
    for mid in message_ids:
        with contextlib.suppress(Exception):
            await bot.delete_message(chat_id=chat_id, message_id=mid)


async def _is_group_admin_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    if is_owner(user_id) or is_admin(user_id):
        return True
    try:
        cm = await context.bot.get_chat_member(chat_id, user_id)
        st = str(getattr(cm, "status", ""))
        return st in ("administrator", "creator")
    except Exception:
        return False


def _extract_command_name(text: str) -> str:
    t = (text or "").strip().split()[0] if (text or "").strip() else ""
    t = t.split("@")[0]
    return t.lstrip("/").lower()


async def global_maintenance_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not maintenance_mode_on():
        return
    uid = update.effective_user.id if update.effective_user else 0
    if not uid or is_owner(uid):
        return
    msg = ui_box_html("Maintenance Mode", h(maintenance_message()), emoji="🛠")
    if update.effective_chat and update.effective_chat.type == "private":
        with contextlib.suppress(Exception):
            await safe_reply(update, msg)
    else:
        await _dm_text(context, uid, msg)
    raise ApplicationHandlerStop


async def group_command_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    cmd = _extract_command_name(update.message.text or "")
    allowed = {"probaho_on", "probaho_off", "sh", "porag", "tutorial"}
    if cmd and cmd not in allowed:
        raise ApplicationHandlerStop


@require_owner
async def cmd_maintenance_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = " ".join(context.args).strip() or "Bot maintenance চলছে। কিছুক্ষণ পরে আবার চেষ্টা করুন।"
    set_maintenance_mode(True, msg)
    sent = await _broadcast_private(context, ui_box_html("Maintenance Mode", h(msg), emoji="🛠"))
    await ok(update, "Maintenance Enabled", f"Message sent to: {sent}")


@require_owner
async def cmd_maintenance_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_maintenance_mode(False, "")
    sent = await _broadcast_private(context, ui_box_html("Service Resumed", "Bot is now active again.", emoji="✅"))
    await ok(update, "Maintenance Disabled", f"Resume message sent to: {sent}")


@require_admin
async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    items = buffer_list(uid, limit=99999)
    if not items:
        await warn(update, "Buffer Empty", "No questions to export. Use /add or send quizzes first.")
        return
    rows = []
    for _id, payload in items:
        q = str(payload.get("questions", "") or "")
        e = str(payload.get("explanation", "") or "")
        q2, expl2 = split_inline_explain(q)
        if expl2 and not e.strip():
            e = expl2
        rr = dict(payload)
        rr["questions"] = q2.strip()
        rr["explanation"] = (e.strip() if explain_mode_on(uid) else "")
        rows.append(rr)
    df = pd.DataFrame(rows)
    cols = ["questions", "option1", "option2", "option3", "option4", "option5", "answer", "explanation", "type", "section"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    with tempfile.NamedTemporaryFile("w+b", suffix=".csv", delete=False) as tf:
        csv_path = tf.name
    try:
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        with open(csv_path, "rb") as rf:
            await context.bot.send_document(
                chat_id=uid,
                document=rf,
                filename="probaho_export.csv",
                caption=f"Exported {len(df)} question(s)",
            )
        buffer_clear(uid)
        await ok(update, "Export Complete", f"CSV exported successfully.\n\nExported: {len(df)}\nBuffer cleared.")
    finally:
        with contextlib.suppress(Exception):
            os.unlink(csv_path)


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
    await refresh_group_command_menu(context, chat.id)
    with contextlib.suppress(Exception):
        await update.message.delete()
    await _dm_text(context, uid, ui_box_html("Group AI Enabled", f"Group: <code>{h(chat.id)}</code>\nMode: members can use <code>/sh</code> in this group.", emoji="✅"))


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
    await refresh_group_command_menu(context, chat.id)
    with contextlib.suppress(Exception):
        await update.message.delete()
    await _dm_text(context, uid, ui_box_html("Group AI Disabled", f"Group: <code>{h(chat.id)}</code>\nThe <code>/sh</code> AI command is now off in this group.", emoji="✅"))


def _poll_text_for_sh(poll) -> tuple[str, list[str], str]:
    qtext = str(getattr(poll, 'question', '') or '').strip()
    options = [str(o.text).strip() for o in getattr(poll, 'options', [])]
    expl = str(getattr(poll, 'explanation', '') or '').strip()
    return qtext, options, expl


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

    token = _make_token()
    store = _pending_store(context)
    preview = inline or "Solve this message/quiz"

    if reply and getattr(reply, 'poll', None):
        qtext, options, qexpl = _poll_text_for_sh(reply.poll)
        official_ans = 0
        with contextlib.suppress(Exception):
            if getattr(reply.poll, 'type', '') == 'quiz' and getattr(reply.poll, 'correct_option_id', None) is not None:
                official_ans = int(reply.poll.correct_option_id) + 1
        store[token] = {
            "uid": uid,
            "chat_id": chat_id,
            "kind": "poll",
            "payload": {
                "question": qtext,
                "options": options,
                "official_ans": official_ans,
                "official_expl": qexpl,
            },
        }
        preview = qtext or preview
    else:
        prompt = inline
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
        store[token] = {
            "uid": uid,
            "chat_id": chat_id,
            "kind": "text",
            "payload": {"text": prompt},
        }
        preview = prompt

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
    asyncio.create_task(_auto_delete_after(context.bot, chat_id, [sent.message_id], 300))


async def cmd_porag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    uid = update.effective_user.id if update.effective_user else 0
    if not await _is_group_admin_user(context, update.effective_chat.id, uid):
        await _dm_text(context, uid, ui_box_html("Unauthorized", "Only a group admin or the bot owner can use /porag.", emoji="⚠️"))
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    if not update.message.reply_to_message:
        await _dm_text(context, uid, ui_box_html("Usage", "Reply to the first message you want to delete, then send <code>/porag</code>.", emoji="ℹ️"))
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    start_id = int(update.message.reply_to_message.message_id)
    end_id = int(update.message.message_id)
    total = end_id - start_id + 1
    if total > 150:
        await _dm_text(context, uid, ui_box_html("Too Many Messages", "Please delete at most 150 messages at a time.", emoji="⚠️"))
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    deleted = 0
    for mid in range(start_id, end_id + 1):
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=mid)
            deleted += 1
        except Exception:
            pass
    await _dm_text(context, uid, ui_box_html("Messages Deleted", f"Deleted: <code>{deleted}</code>", emoji="🧹"))


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
        "1) Use /probaho_on to enable group AI.\n"
        "2) Members ask only with /sh.\n"
        "3) AI replies auto-delete after 5 minutes.\n"
        "4) Other bot commands work only in inbox.\n"
        "5) Reply to a start message with /porag to delete a range."
    )
    with contextlib.suppress(Exception):
        await update.message.reply_text(text)
    with contextlib.suppress(Exception):
        await update.message.delete()


async def on_tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.callback_query:
        return
    q = update.callback_query
    uid = q.from_user.id if q.from_user else 0
    chat_id = q.message.chat_id if q.message else 0
    if not await _is_group_admin_user(context, chat_id, uid):
        with contextlib.suppress(Exception):
            await q.answer("Admins only.", show_alert=True)
        return
    text = (
        "Use /probaho_on in this group.\n"
        "Members can then ask AI using /sh text অথবা reply + /sh.\n"
        "All other bot tools stay in inbox/private.\n"
        "Use /probaho_off to stop group AI."
    )
    with contextlib.suppress(Exception):
        await q.answer(text, show_alert=True)


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
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"ধন্যবাদ {h(actor_name)}, {h(BOT_BRAND)} বটটি group-এ add করার জন্য। Admin guide দেখতে নিচের button ব্যবহার করুন.",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )


@require_admin
async def cmd_buffercount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    await info_html(update, "Buffer Status", f"Total buffered: <code>{buffer_count(uid)}</code>", emoji="ℹ️")


def _private_filter(base_filter):
    return filters.ChatType.PRIVATE & base_filter


def _group_filter(base_filter):
    return (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & base_filter


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

    # Private public commands
    app.add_handler(_cmdh("start", cmd_start, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("help", cmd_help, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("commands", cmd_commands, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("features", cmd_features, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("ask", cmd_ask, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("scanhelp", cmd_scanhelp, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("vision_on", cmd_vision_on, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("vision_off", cmd_vision_off, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("solve_on", cmd_solve_on, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("solve_off", cmd_solve_off, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("explain_on", cmd_explain_on, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("explain_off", cmd_explain_off, filters=filters.ChatType.PRIVATE))

    # Owner/private
    app.add_handler(_cmdh("quizprefix", cmd_quizprefix, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("quizlink", cmd_quizlink, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("addadmin", cmd_addadmin, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("removeadmin", cmd_removeadmin, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("grantall", cmd_grantall, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("revokeall", cmd_revokeall, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("grantvision", cmd_grantvision, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("revokevision", cmd_revokevision, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("ownerstats", cmd_ownerstats, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("users", cmd_users, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("maintenance_on", cmd_maintenance_on, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("maintenance_off", cmd_maintenance_off, filters=filters.ChatType.PRIVATE))

    # Admin/private
    app.add_handler(_cmdh("filter", cmd_filter, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("done", cmd_done, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("clear", cmd_clear, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("buffercount", cmd_buffercount, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("addchannel", cmd_addchannel, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("listchannels", cmd_listchannels, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("removechannel", cmd_removechannel, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("setprefix", cmd_setprefix, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("setexplink", cmd_setexplink, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("post", cmd_post, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("postemoji", cmd_postemoji, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("emojipost", cmd_postemoji, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("imgreact", cmd_imgreact, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("broadcast", cmd_broadcast, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("adminpanel", cmd_adminpanel, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("reply", cmd_reply, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("close", cmd_close, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("ban", cmd_ban, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("unban", cmd_unban, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("banned", cmd_banned, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("private_send", cmd_private_send, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("send_private", cmd_private_send, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("usersd", cmd_usersd, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("addrequired", cmd_addrequired, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("delrequired", cmd_delrequired, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("listrequired", cmd_listrequired, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("himusai_on", cmd_himusai_on, filters=filters.ChatType.PRIVATE))
    app.add_handler(_cmdh("himusai_off", cmd_himusai_off, filters=filters.ChatType.PRIVATE))

    # Private message handlers only
    app.add_handler(MessageHandler(_private_filter(filters.POLL), handle_poll))
    app.add_handler(MessageHandler(_private_filter(filters.POLL), handle_user_poll_solver), group=1)
    app.add_handler(MessageHandler(_private_filter(filters.PHOTO), handle_image))
    app.add_handler(MessageHandler(_private_filter(filters.Document.IMAGE), handle_image))
    app.add_handler(MessageHandler(_private_filter(filters.TEXT & (~filters.COMMAND)), handle_text))
    app.add_handler(MessageHandler(_private_filter(filters.TEXT & (~filters.COMMAND)), handle_user_text_unusual), group=1)

    # Group-only handlers
    app.add_handler(_cmdh("probaho_on", cmd_probaho_on, filters=(filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)))
    app.add_handler(_cmdh("probaho_off", cmd_probaho_off, filters=(filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)))
    app.add_handler(_cmdh("sh", cmd_sh, filters=(filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)))
    app.add_handler(_cmdh("porag", cmd_porag, filters=(filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)))
    app.add_handler(_cmdh("tutorial", cmd_tutorial, filters=(filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)))
    app.add_handler(ChatMemberHandler(on_my_chat_member, chat_member_types=ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_error_handler(on_error)
    return app

# ===== END ULTRA GROUP/MAINTENANCE PATCH v6 =====



