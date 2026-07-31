# ──────────────────────────────────────────────────────────────────────────────
# Section: 14_final_patches_03_13_b
# Original lines: 8298..8555
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===========================
# FINAL PATCHES (2026-03-13)
# ===========================

def _profile_link_keyboard(user_id: int, username: Optional[str] = None) -> Optional[InlineKeyboardMarkup]:
    """Safer profile keyboard: only public username links are used.
    tg://user buttons can fail with Button_user_privacy_restricted.
    """
    un = str(username or '').lstrip('@').strip()
    if not un:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"👤 Open @{un}", url=f"https://t.me/{un}")]])


@require_admin
async def cmd_usersd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not str(context.args[0]).lstrip('-').isdigit():
        await safe_reply(update, usage_box("usersd", "<user_id>", "Show user details and a public profile button if available"))
        return
    target = int(context.args[0])
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT first_name, username, role, is_banned, created_at, last_seen_at FROM users WHERE user_id=?", (target,))
    row = cur.fetchone(); conn.close()
    if row:
        name = row["first_name"] or str(target)
        username = row["username"] or ""
        uname = ("@" + username) if username else "(no public username)"
        body = (
            f"Profile: {mention_user(target, name)}\n"
            f"User ID: <code>{h(target)}</code>\n"
            f"Username: {h(uname)}\n"
            f"Role: <code>{h(row['role'] or 'USER')}</code>\n"
            f"Banned: <code>{'Yes' if int(row['is_banned'] or 0) else 'No'}</code>\n"
            f"Created: <code>{h(row['created_at'] or '')}</code>\n"
            f"Last Seen: <code>{h(row['last_seen_at'] or '')}</code>"
        )
        kb = _profile_link_keyboard(target, username)
        if not kb:
            body += "\n\n⚠️ Public profile button unavailable for this user."
    else:
        body = (
            f"Profile: {mention_user(target, str(target))}\n"
            f"User ID: <code>{h(target)}</code>\n"
            f"Stored info: <code>Not found in local users table</code>\n\n"
            f"⚠️ Public profile button unavailable unless the user has a username."
        )
        kb = None
    await update.message.reply_text(
        ui_box_html("User Details", body, emoji="🔎"),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
        disable_web_page_preview=True,
    )


def _buffer_feedback_key(chat_id: int, user_id: int) -> str:
    return f"_buffer_feedback:{int(chat_id)}:{int(user_id)}"


async def _show_buffer_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE, title: str, body_html: str, emoji: str = "✅") -> None:
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    chat_id = int(update.effective_chat.id)
    uid = int(update.effective_user.id)
    lock = _get_chat_lock(context, chat_id)
    async with lock:
        key = _buffer_feedback_key(chat_id, uid)
        prev_mid = context.application.bot_data.get(key)
        if isinstance(prev_mid, int):
            with contextlib.suppress(Exception):
                await context.bot.delete_message(chat_id=chat_id, message_id=prev_mid)
        msg = await update.message.reply_text(
            ui_box_html(title, body_html, emoji=emoji),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        context.application.bot_data[key] = int(msg.message_id)


@require_admin_silent
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if not uid or is_banned(uid):
        return
    role = get_role(uid)
    if role not in (ROLE_ADMIN, ROLE_OWNER):
        return
    if is_private_chat(update) and (solver_mode_on(uid) or himusai_mode_on(uid)):
        return
    text = update.message.text or ""
    if not text.strip():
        return
    if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
        await warn(update, "Buffer Limit Reached", f"You have {MAX_BUFFERED_QUESTIONS} questions buffered.\n\nUse /done to export or /clear to reset.")
        return
    blocks = split_blocks(text)
    added = 0
    for b in blocks:
        if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
            break
        try:
            payload = parse_text_block(b, uid)
            if payload:
                buffer_add(uid, payload)
                added += 1
        except Exception as e:
            db_log("ERROR", "parse_text_failed", {"admin_id": uid, "error": str(e)})
    if added:
        await _show_buffer_feedback(
            update,
            context,
            "Added to Buffer",
            f"<code>{h(added)}</code> question(s) added.\n\nTotal buffered: <code>{h(buffer_count(uid))}</code>",
        )
    else:
        await warn(update, "No Questions Found", "No valid quiz blocks detected. Check formatting.")


@require_admin_silent
async def handle_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if not uid or is_banned(uid):
        return
    role = get_role(uid)
    if role not in (ROLE_ADMIN, ROLE_OWNER):
        return
    if is_private_chat(update) and (solver_mode_on(uid) or himusai_mode_on(uid)):
        return
    poll = update.message.poll
    question = clean_common(poll.question or "", uid)
    options = [o.text for o in poll.options]
    opts = options + [""] * (5 - len(options))
    explanation = ""
    if hasattr(poll, "explanation") and poll.explanation:
        explanation = clean_explanation(poll.explanation, uid)
    correct_answer_id = 0
    if poll.type == "quiz" and poll.correct_option_id is not None:
        correct_answer_id = int(poll.correct_option_id) + 1
    payload = {
        "questions": question,
        "option1": (opts[0] or "").strip(),
        "option2": (opts[1] or "").strip(),
        "option3": (opts[2] or "").strip(),
        "option4": (opts[3] or "").strip(),
        "option5": (opts[4] or "").strip(),
        "answer": correct_answer_id,
        "explanation": explanation,
        "type": 1,
        "section": 1,
    }
    if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
        await warn_html(update, "Buffer Limit Reached", f"You have <code>{h(MAX_BUFFERED_QUESTIONS)}</code> questions buffered.\n\nUse <code>/done</code> to export or <code>/clear</code> to reset.")
        return
    buffer_add(uid, payload)
    note = ""
    if correct_answer_id == 0 and poll.type == "quiz":
        note = "<br><br>⚠️ Telegram may hide the correct answer in forwarded quizzes. Export will store <code>answer=0</code>."
    await _show_buffer_feedback(
        update,
        context,
        "Poll Saved",
        f"Total buffered: <code>{buffer_count(uid)}</code>{note}",
    )


@require_admin
async def cmd_buffercount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    cnt = buffer_count(uid)
    items = buffer_list(uid, limit=3)
    preview = []
    for rid, payload in items:
        q = str(payload.get('questions', '') or '').strip()
        if q:
            preview.append(f"• <code>{rid}</code> — {h(q[:70])}{'...' if len(q) > 70 else ''}")
    body = f"Total buffered: <code>{cnt}</code>"
    if preview:
        body += "\n\nLatest items:\n" + "\n".join(preview)
    await info_html(update, "Buffer Status", body)


@require_admin
async def cmd_imgreact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id if update.effective_user else 0
    if not context.args or len(context.args) < 2 or not str(context.args[0]).isdigit() or not str(context.args[1]).isdigit():
        await safe_reply(update, usage_box("imgreact", "<DB-ID> <correct_emoji_no 1-4> [explanation]", "Reply to a photo/image and post it as an image reaction quiz"))
        return
    cid = int(context.args[0])
    corr = int(context.args[1])
    if corr < 1 or corr > 4:
        await warn(update, "Invalid Answer", "correct_emoji_no must be between 1 and 4.")
        return
    ch = channel_get_by_id_for_user(admin_id, cid)
    if not ch:
        await warn(update, "Not Found", "Channel not found or no access.")
        return
    if not update.message or not update.message.reply_to_message:
        await warn(update, "Reply Required", "Reply to a photo/image message with /imgreact <DB-ID> <correct_emoji_no> [explanation]")
        return
    src = update.message.reply_to_message
    photo_file_id = None
    if getattr(src, 'photo', None):
        photo_file_id = src.photo[-1].file_id
    elif getattr(src, 'document', None) and str(getattr(src.document, 'mime_type', '')).startswith('image/'):
        photo_file_id = src.document.file_id
    if not photo_file_id:
        await warn(update, "Image Required", "Reply to a photo or image document.")
        return
    explanation = " ".join(context.args[2:]).strip()
    prefix = str(getattr(ch, 'prefix', '') or '').strip() or BOT_BRAND
    caption_parts = [prefix]
    src_caption = str(getattr(src, 'caption', '') or '').strip()
    if src_caption:
        caption_parts.append(src_caption)
    caption = "\n".join([p for p in caption_parts if p]).strip()
    quiz_id = uuid.uuid4().hex[:10]
    try:
        m = await context.bot.send_photo(
            chat_id=ch.channel_chat_id,
            photo=photo_file_id,
            caption=caption[:1024] if caption else None,
            reply_markup=emoji_quiz_keyboard(4, quiz_id),
        )
        emoji_quiz_save(
            quiz_id,
            ch.channel_chat_id,
            m.message_id,
            {
                "question": src_caption,
                "options": EMOJI_BUTTONS[:4],
                "correct_answer": corr,
                "explanation": explanation,
                "prefix": prefix,
                "image_file_id": photo_file_id,
                "image_mode": 1,
            },
            admin_id,
        )
        await ok_html(update, "Image Reaction Quiz Posted", f"Channel: <code>{h(getattr(ch, 'title', cid))}</code>")
    except Exception as e:
        db_log("ERROR", "imgreact_failed", {"admin_id": admin_id, "channel": getattr(ch, 'channel_chat_id', 0), "error": str(e)})
        await err(update, "Post Failed", str(e)[:180])


_old_build_app = build_app

def build_app() -> Application:
    app = _old_build_app()
    app.add_handler(_cmdh("emojipost", cmd_postemoji))
    app.add_handler(_cmdh("buffercount", cmd_buffercount))
    app.add_handler(_cmdh("imgreact", cmd_imgreact))
    return app




