# ──────────────────────────────────────────────────────────────────────────────
# Section: 09_final_patch_overrides
# Original lines: 5908..6104
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===========================
# FINAL PATCH OVERRIDES
# ===========================
REQUIRED_DEFAULT_JOIN_URL = "https://t.me/FX_Ur_Target"

async def _is_group_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return str(getattr(member, "status", "")) in ("administrator", "creator")
    except Exception:
        return False

async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT user_id, role, first_name, username, is_banned, created_at, last_seen_at FROM users ORDER BY created_at ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    if not rows:
        await warn(update, "No Users", "No users found.")
        return
    import tempfile, json
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        path = f.name
    with open(path, "rb") as rf:
        await context.bot.send_document(chat_id=update.effective_user.id, document=rf, filename="probaho_users.json", caption="All started users")
    with contextlib.suppress(Exception):
        os.unlink(path)

def _required_join_kb() -> InlineKeyboardMarkup:
    rows = []
    for r in required_chat_list():
        title = str(r["title"] or r["chat_id"])
        if title.startswith("@"):
            url = f"https://t.me/{title.lstrip('@')}"
        elif "t.me/" in title:
            url = title if title.startswith("http") else ("https://" + title.lstrip("/"))
        else:
            url = REQUIRED_DEFAULT_JOIN_URL
        rows.append([InlineKeyboardButton(f"Join {title}", url=url)])
    rows.append([InlineKeyboardButton("Verify", callback_data="req:verify")])
    return InlineKeyboardMarkup(rows)

async def enforce_required_memberships(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if not uid or is_owner(uid) or is_admin(uid):
        return True
    ok, missing = await user_meets_required_memberships(context, uid)
    if ok:
        reset_warn_count(uid)
        return True
    count = inc_warn_count(uid)
    if count >= 5:
        set_ban(uid, True)
        audit_ban(OWNER_ID, uid, "BAN")
        with contextlib.suppress(Exception):
            await safe_send_text(context.bot, uid, f"🚫 You are banned from <b>{h(BOT_BRAND)}</b> for leaving required channel/group. Contact: {h(OWNER_CONTACT)}")
        return False
    names = ", ".join(missing[:10]) if missing else "required channel/group"
    if update.message:
        try:
            await update.message.reply_text(f"⚠️ Join Required\nPlease join: {names}\nWarning: {count}/5", reply_markup=_required_join_kb())
        except Exception:
            await warn(update, "Join Required", f"Please join: {names}\n\nWarning: {count}/5")
    return False

@require_owner
async def cmd_addrequired(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await safe_reply(update, usage_box("addrequired", "<@channel|group|-100...>", "Add required channel/group for all normal users"))
        return
    ref = context.args[0].strip()
    try:
        chat = await context.bot.get_chat(int(ref) if ref.lstrip("-").isdigit() else ref)
        title = ("@" + chat.username) if getattr(chat, "username", None) else (chat.title or str(chat.id))
        required_chat_add(chat.id, title, getattr(chat, "type", ""), update.effective_user.id)
        await ok_html(update, "Required Chat Added", f"{h(title)}\n<code>{h(chat.id)}</code>")
    except Exception as e:
        await err(update, "Failed", str(e)[:180])

async def cmd_probaho_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    uid = update.effective_user.id if update.effective_user else 0
    if not chat or chat.type not in ("group", "supergroup"):
        await warn(update, "Group Only", "Use this command inside a group/supergroup.")
        return
    if not await _is_group_admin(context, chat.id, uid):
        await warn(update, "Unauthorized", "Only a group admin can use this command.")
        return
    set_group_ai_enabled(chat.id, True)
    await ok(update, "Group AI Enabled", f"Users can now get AI responses in this group: {chat.id}")

async def cmd_probaho_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    uid = update.effective_user.id if update.effective_user else 0
    if not chat or chat.type not in ("group", "supergroup"):
        await warn(update, "Group Only", "Use this command inside a group/supergroup.")
        return
    if not await _is_group_admin(context, chat.id, uid):
        await warn(update, "Unauthorized", "Only a group admin can use this command.")
        return
    set_group_ai_enabled(chat.id, False)
    await ok(update, "Group AI Disabled", f"Users will no longer get AI responses in this group: {chat.id}")

def _copyable_quiz_block(question: str, options: List[str], labels: Optional[List[str]] = None) -> str:
    parts = [question.strip(), ""]
    labs = labels or []
    for i, o in enumerate(options, start=1):
        label = labs[i-1] if i-1 < len(labs) else f"{_safe_letter(i)})"
        parts.append(f"{label} {o}")
    raw = "\n".join(parts).strip()
    return f"<pre>{h(raw)}</pre>"

@require_admin
async def cmd_postemoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await safe_reply(update, usage_box("postemoji", "<DB-ID> [keep]", "Post buffered questions as emoji quiz to a channel"))
        return
    cid = int(context.args[0])
    keep = (len(context.args) > 1 and context.args[1].strip().lower() == "keep")
    ch = channel_get_by_id_for_user(admin_id, cid)
    if not ch:
        await warn(update, "Not Found", "Channel not found or no access.")
        return
    items = buffer_list(admin_id, limit=MAX_BUFFERED_QUESTIONS)
    if not items:
        await warn(update, "Buffer Empty", "No buffered questions found.")
        return
    sent = 0; sent_ids = []
    try:
        prefix = str(ch["prefix"] or "").strip()
    except Exception:
        prefix = ""
    for bid, payload in items:
        q, opts, corr_idx0, explanation = quiz_to_poll_parts(payload)
        labels = EMOJI_BUTTONS[:len(opts)]
        block = _copyable_quiz_block(q, opts, labels=labels)
        title = prefix if prefix else "Emoji Quiz"
        msg_html = f"<b>{h(title)}</b>\n\n{block}"
        quiz_id = uuid.uuid4().hex[:10]
        try:
            m = await context.bot.send_message(chat_id=ch.channel_chat_id, text=msg_html, parse_mode=ParseMode.HTML, reply_markup=emoji_quiz_keyboard(len(opts), quiz_id), disable_web_page_preview=True)
            sent += 1; sent_ids.append(bid)
            emoji_quiz_save(quiz_id, ch.channel_chat_id, m.message_id, {"question": q, "options": opts, "correct_answer": corr_idx0 + 1 if corr_idx0 >= 0 else 0, "explanation": explanation, "prefix": title}, admin_id)
            await asyncio.sleep(0.25)
        except Exception as e:
            db_log("ERROR", "postemoji_failed", {"admin_id": admin_id, "channel": ch.channel_chat_id, "error": str(e)})
    if sent and not keep:
        buffer_remove_ids(admin_id, sent_ids)
    await ok_html(update, "Emoji Quiz Posted", f"Sent: <code>{h(sent)}</code>\nChannel: <code>{h(ch.title)}</code>")

async def on_emoji_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return
    q = update.callback_query
    data = (q.data or "").strip()
    m = re.match(r"^eq:([0-9a-f]{6,16}):(\d+)$", data)
    if not m:
        return
    quiz_id = m.group(1)
    selected = int(m.group(2))
    uid = q.from_user.id if q.from_user else 0
    if not uid:
        return
    ok, _missing = await user_meets_required_memberships(context, uid)
    if not ok:
        await q.answer("Join required channel first.", show_alert=True)
        return
    quiz = emoji_quiz_get(quiz_id)
    if not quiz:
        await q.answer("Quiz expired or not found.", show_alert=True)
        return
    if not emoji_quiz_has_answered(quiz_id, uid):
        correct = int(quiz.get("correct_answer", 0) or 0)
        emoji_quiz_record_answer(quiz_id, uid, selected, (selected == correct and correct > 0))
    selected = emoji_quiz_user_choice(quiz_id, uid) or selected
    correct = int(quiz.get("correct_answer", 0) or 0)
    counts = emoji_quiz_counts(quiz_id)
    opts = quiz.get("options", []) or []
    stats = []
    for i, opt in enumerate(opts, start=1):
        label = EMOJI_BUTTONS[i-1] if i-1 < len(EMOJI_BUTTONS) else _safe_letter(i)
        stats.append(f"{label} {opt} — {counts.get(i,0)}")
    stats_text = "\n".join(stats)
    expl = clean_latex(str(quiz.get("explanation", "") or "").strip())
    if selected == correct and correct > 0:
        msg = f"✅ Correct\n{expl}\n\nStats:\n{stats_text}".strip()
    else:
        corr_label = EMOJI_BUTTONS[correct-1] if 0 < correct <= len(EMOJI_BUTTONS) else _safe_letter(correct)
        msg = f"❌ Wrong\n✅ Correct: {corr_label}\n{expl}\n\nStats:\n{stats_text}".strip()
    await q.answer(msg[:190], show_alert=True)


