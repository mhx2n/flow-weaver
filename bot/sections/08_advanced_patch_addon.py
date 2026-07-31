# ──────────────────────────────────────────────────────────────────────────────
# Section: 08_advanced_patch_addon
# Original lines: 5126..5907
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===========================
# ADVANCED PATCH ADDON
# ===========================

def mention_user(uid: int, name: str = "User") -> str:
    return f'<a href="tg://user?id={int(uid)}">{h(name or "User")}</a>'

EMOJI_BUTTONS = ["❤️", "😮", "😢", "🥳", "🔥"]


def extra_db_init() -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS required_memberships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL UNIQUE,
        title TEXT,
        chat_type TEXT,
        added_by INTEGER,
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_warnings (
        user_id INTEGER PRIMARY KEY,
        warn_count INTEGER NOT NULL DEFAULT 0,
        last_warn_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS emoji_quizzes (
        quiz_id TEXT PRIMARY KEY,
        channel_chat_id INTEGER NOT NULL,
        message_id INTEGER,
        payload_json TEXT NOT NULL,
        created_by INTEGER,
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS emoji_quiz_responses (
        quiz_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        selected_option INTEGER NOT NULL,
        is_correct INTEGER NOT NULL DEFAULT 0,
        clicked_at TEXT NOT NULL,
        PRIMARY KEY (quiz_id, user_id)
    )
    """)
    conn.commit()
    conn.close()


def required_chat_add(chat_id: int, title: str, chat_type: str, added_by: int) -> None:
    conn = db_connect(); cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO required_memberships(chat_id,title,chat_type,added_by,created_at) VALUES (?,?,?,?,?)",
        (int(chat_id), title or "", chat_type or "", int(added_by), now_iso()),
    )
    conn.commit(); conn.close()


def required_chat_remove(chat_id: int) -> bool:
    conn = db_connect(); cur = conn.cursor()
    cur.execute("DELETE FROM required_memberships WHERE chat_id=?", (int(chat_id),))
    ok = cur.rowcount > 0
    conn.commit(); conn.close()
    return ok


def required_chat_list() -> List[sqlite3.Row]:
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT * FROM required_memberships ORDER BY id ASC")
    rows = cur.fetchall(); conn.close()
    return rows


def get_warn_count(user_id: int) -> int:
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT warn_count FROM user_warnings WHERE user_id=?", (int(user_id),))
    row = cur.fetchone(); conn.close()
    return int(row["warn_count"] or 0) if row else 0


def inc_warn_count(user_id: int) -> int:
    conn = db_connect(); cur = conn.cursor()
    current = get_warn_count(user_id)
    new_count = current + 1
    cur.execute(
        "INSERT INTO user_warnings(user_id,warn_count,last_warn_at) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET warn_count=excluded.warn_count,last_warn_at=excluded.last_warn_at",
        (int(user_id), new_count, now_iso()),
    )
    conn.commit(); conn.close()
    return new_count


def reset_warn_count(user_id: int) -> None:
    conn = db_connect(); cur = conn.cursor()
    cur.execute("DELETE FROM user_warnings WHERE user_id=?", (int(user_id),))
    conn.commit(); conn.close()


def set_group_ai_enabled(chat_id: int, value: bool) -> None:
    set_setting(f"group_ai_enabled:{int(chat_id)}", "1" if value else "0")


def is_group_ai_enabled(chat_id: int) -> bool:
    return get_setting(f"group_ai_enabled:{int(chat_id)}", "0") == "1"


def is_private_chat(update: Update) -> bool:
    try:
        return (update.effective_chat.type == "private")
    except Exception:
        return False


async def user_meets_required_memberships(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Tuple[bool, List[str]]:
    rows = required_chat_list()
    if not rows:
        return True, []
    missing = []
    for r in rows:
        cid = int(r["chat_id"])
        title = str(r["title"] or cid)
        try:
            member = await context.bot.get_chat_member(cid, user_id)
            status = str(getattr(member, "status", ""))
            if status in ("left", "kicked"):
                missing.append(title)
        except Exception:
            missing.append(title)
    return (len(missing) == 0), missing


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
        await warn(update, "Join Required", f"Please join: {names}\n\nWarning: {count}/5")
    return False


def _copyable_quiz_block(question: str, options: List[str]) -> str:
    parts = [question.strip(), ""]
    for i, o in enumerate(options, start=1):
        parts.append(f"{_safe_letter(i)}) {o}")
    raw = "\n".join(parts).strip()
    return f"<pre>{h(raw)}</pre>"


def _remember_quiz_context(context: ContextTypes.DEFAULT_TYPE, message_id: int, payload: Dict[str, Any]) -> None:
    store = context.application.bot_data.get("_quiz_context")
    if not isinstance(store, dict):
        store = {}
        context.application.bot_data["_quiz_context"] = store
    store[int(message_id)] = dict(payload)
    if len(store) > 2000:
        for k in list(store.keys())[:500]:
            store.pop(k, None)


def _get_quiz_context(context: ContextTypes.DEFAULT_TYPE, message_id: int) -> Optional[Dict[str, Any]]:
    store = context.application.bot_data.get("_quiz_context")
    if not isinstance(store, dict):
        return None
    item = store.get(int(message_id))
    return item if isinstance(item, dict) else None


def emoji_quiz_save(quiz_id: str, channel_chat_id: int, message_id: int, payload: Dict[str, Any], created_by: int) -> None:
    conn = db_connect(); cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO emoji_quizzes(quiz_id,channel_chat_id,message_id,payload_json,created_by,created_at) VALUES (?,?,?,?,?,?)",
        (quiz_id, int(channel_chat_id), int(message_id), json.dumps(payload, ensure_ascii=False), int(created_by), now_iso()),
    )
    conn.commit(); conn.close()


def emoji_quiz_get(quiz_id: str) -> Optional[Dict[str, Any]]:
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT * FROM emoji_quizzes WHERE quiz_id=?", (str(quiz_id),))
    row = cur.fetchone(); conn.close()
    if not row:
        return None
    data = json.loads(row["payload_json"])
    data["quiz_id"] = quiz_id
    data["channel_chat_id"] = int(row["channel_chat_id"])
    data["message_id"] = int(row["message_id"] or 0)
    return data


def emoji_quiz_has_answered(quiz_id: str, user_id: int) -> bool:
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM emoji_quiz_responses WHERE quiz_id=? AND user_id=?", (str(quiz_id), int(user_id)))
    row = cur.fetchone(); conn.close()
    return bool(row)


def emoji_quiz_user_choice(quiz_id: str, user_id: int) -> int:
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT selected_option FROM emoji_quiz_responses WHERE quiz_id=? AND user_id=?", (str(quiz_id), int(user_id)))
    row = cur.fetchone(); conn.close()
    return int(row["selected_option"] or 0) if row else 0


def emoji_quiz_record_answer(quiz_id: str, user_id: int, selected_option: int, is_correct: bool) -> None:
    conn = db_connect(); cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO emoji_quiz_responses(quiz_id,user_id,selected_option,is_correct,clicked_at) VALUES (?,?,?,?,?)",
        (str(quiz_id), int(user_id), int(selected_option), 1 if is_correct else 0, now_iso()),
    )
    conn.commit(); conn.close()


def emoji_quiz_counts(quiz_id: str) -> Dict[int, int]:
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT selected_option, COUNT(*) AS c FROM emoji_quiz_responses WHERE quiz_id=? GROUP BY selected_option", (str(quiz_id),))
    rows = cur.fetchall(); conn.close()
    return {int(r["selected_option"]): int(r["c"]) for r in rows}


def emoji_quiz_keyboard(num_options: int, quiz_id: str) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i in range(num_options):
        row.append(InlineKeyboardButton(EMOJI_BUTTONS[i], callback_data=f"eq:{quiz_id}:{i+1}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


@require_owner
async def cmd_addrequired(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await safe_reply(update, usage_box("addrequired", "<@channel|group|-100...>", "Add required channel/group for all normal users"))
        return
    ref = context.args[0].strip()
    try:
        chat = await context.bot.get_chat(int(ref) if ref.lstrip('-').isdigit() else ref)
        required_chat_add(chat.id, chat.title or chat.username or str(chat.id), getattr(chat, "type", ""), update.effective_user.id)
        await ok_html(update, "Required Chat Added", f"{h(chat.title or chat.username or chat.id)}\n<code>{h(chat.id)}</code>")
    except Exception as e:
        await err(update, "Failed", str(e)[:180])


@require_owner
async def cmd_delrequired(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await safe_reply(update, usage_box("delrequired", "<chat_id>", "Remove required channel/group"))
        return
    cid = to_int(context.args[0])
    if not cid:
        await err(update, "Invalid Input", "Invalid chat id")
        return
    if required_chat_remove(cid):
        await ok(update, "Removed", f"Required chat removed: {cid}")
    else:
        await warn(update, "Not Found", f"Required chat not found: {cid}")


@require_owner
async def cmd_listrequired(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = required_chat_list()
    if not rows:
        await warn(update, "No Required Chats", "No required membership configured.")
        return
    body = "\n\n".join([f"<b>{h(r['title'] or '')}</b>\n<code>{h(r['chat_id'])}</code>\nType: {h(r['chat_type'] or '')}" for r in rows])
    await ok_html(update, "Required Memberships", body, emoji="📌")


@require_admin
async def cmd_himusai_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        await warn(update, "Private Only", "This command works in inbox/private chat only.")
        return
    set_himusai_mode_on(update.effective_user.id, True)
    await ok_html(update, "HimusAI Enabled", "Admin/Owner inbox auto-response enabled.", emoji="🧠")


@require_admin
async def cmd_himusai_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        await warn(update, "Private Only", "This command works in inbox/private chat only.")
        return
    set_himusai_mode_on(update.effective_user.id, False)
    await ok_html(update, "HimusAI Disabled", "Admin/Owner inbox auto-response disabled.", emoji="🧠")


@require_admin
async def cmd_probaho_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await warn(update, "Group Only", "Use this command inside a group/supergroup.")
        return
    set_group_ai_enabled(chat.id, True)
    await refresh_group_command_menu(context, chat.id)
    await ok(update, "Group AI Enabled", f"Users can now get AI responses in this group: {chat.id}")


@require_admin
async def cmd_probaho_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await warn(update, "Group Only", "Use this command inside a group/supergroup.")
        return
    set_group_ai_enabled(chat.id, False)
    await refresh_group_command_menu(context, chat.id)
    await ok(update, "Group AI Disabled", f"Users will no longer get AI responses in this group: {chat.id}")


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
    sent = 0
    sent_ids = []
    for bid, payload in items:
        q, opts, corr_idx0, explanation = quiz_to_poll_parts(payload)
        block = _copyable_quiz_block(q, opts)
        msg_html = f"<b>📚 Emoji Quiz</b>\n\n{block}"
        try:
            m = await context.bot.send_message(chat_id=ch.channel_chat_id, text=msg_html, parse_mode=ParseMode.HTML, reply_markup=emoji_quiz_keyboard(len(opts), uuid.uuid4().hex[:10]), disable_web_page_preview=True)
            sent += 1
            sent_ids.append(bid)
            # fix quiz_id from keyboard callback data
            quiz_id = None
            try:
                quiz_id = m.reply_markup.inline_keyboard[0][0].callback_data.split(":")[1]
            except Exception:
                quiz_id = uuid.uuid4().hex[:10]
            emoji_quiz_save(quiz_id, ch.channel_chat_id, m.message_id, {"question": q, "options": opts, "correct_answer": corr_idx0 + 1 if corr_idx0 >= 0 else 0, "explanation": explanation}, admin_id)
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
    if emoji_quiz_has_answered(quiz_id, uid):
        await q.answer("আপনি ইতোমধ্যে উত্তর দিয়েছেন।", show_alert=True)
        return
    quiz = emoji_quiz_get(quiz_id)
    if not quiz:
        await q.answer("Quiz expired or not found.", show_alert=True)
        return
    correct = int(quiz.get("correct_answer", 0) or 0)
    is_correct = (selected == correct and correct > 0)
    emoji_quiz_record_answer(quiz_id, uid, selected, is_correct)
    counts = emoji_quiz_counts(quiz_id)
    opts = quiz.get("options", []) or []
    stats = []
    for i, opt in enumerate(opts, start=1):
        stats.append(f"{_safe_letter(i)}) {opt} — {counts.get(i,0)}")
    stats_text = "\n".join(stats)
    expl = str(quiz.get("explanation", "") or "").strip()
    if expl:
        expl = clean_latex(expl)
    if is_correct:
        msg = f"🎉 Congratulations!\n\n✅ Correct answer: {_safe_letter(correct)}\n\n{expl}\n\nStats:\n{stats_text}".strip()
    else:
        msg = f"❌ Wrong answer\n✅ Correct: {_safe_letter(correct)}\n\n{expl}\n\nStats:\n{stats_text}".strip()
    await q.answer("Answer recorded.", show_alert=False)
    # Try DM first so only that user sees analysis
    delivered = False
    with contextlib.suppress(Exception):
        await context.bot.send_message(chat_id=uid, text=msg)
        delivered = True
    if not delivered:
        with contextlib.suppress(Exception):
            await q.answer(msg[:180], show_alert=True)


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    items = buffer_list(uid, limit=99999)
    if not items:
        await warn(update, "Buffer Empty", "No questions to export. Use /add or send quizzes first.")
        return
    rows = [payload for (_id, payload) in items]
    norm_rows = []
    explanations_enabled = explain_mode_on(uid)
    for r in rows:
        q = str(r.get("questions", "") or "")
        e = str(r.get("explanation", "") or "")
        q2, expl2 = split_inline_explain(q)
        if expl2 and not e.strip():
            e = expl2
        rr = dict(r)
        rr["questions"] = q2.strip()
        rr["explanation"] = e.strip() if explanations_enabled else ""
        norm_rows.append(rr)
    rows = norm_rows
    df = pd.DataFrame(rows)
    cols = ["questions", "option1", "option2", "option3", "option4", "option5", "answer", "explanation", "type", "section"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    with tempfile.NamedTemporaryFile("w+b", suffix=".csv", delete=False) as f:
        path = f.name
    df.to_csv(path, index=False, encoding="utf-8-sig")
    def _ans_to_letter(n: int) -> str:
        return {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}.get(int(n or 0), "")
    quiz_json = []
    for r in rows:
        opts_map = {"A": r.get("option1", ""), "B": r.get("option2", ""), "C": r.get("option3", ""), "D": r.get("option4", "")}
        if str(r.get("option5", "")).strip():
            opts_map["E"] = r.get("option5", "")
        quiz_json.append({
            "question": r.get("questions", ""),
            "options": opts_map,
            "correct_answer": _ans_to_letter(r.get("answer", 0)),
            "explanation": r.get("explanation", "") if explanations_enabled else "",
        })
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as jf:
        json_path = jf.name
        json.dump(quiz_json, jf, ensure_ascii=False, indent=2)
    try:
        await update.message.reply_document(document=open(path, "rb"), caption=f"<b>✅ CSV Export</b>\n<i>{len(df)} questions exported</i>", parse_mode=ParseMode.HTML)
        await update.message.reply_document(document=open(json_path, "rb"), caption="<b>✅ JSON Export</b>", parse_mode=ParseMode.HTML)
        await ok_html(update, "Export Complete", f"CSV + JSON ready. <code>{h(len(df))}</code> questions exported.")
    finally:
        with contextlib.suppress(Exception): os.remove(path)
        with contextlib.suppress(Exception): os.remove(json_path)
    buffer_clear(uid)


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\nContact: {OWNER_CONTACT}")
        return
    if not await enforce_required_memberships(update, context):
        return
    replied = update.message.reply_to_message if update.message else None
    text = " ".join(context.args).strip()
    if not text:
        text = reply_text_or_caption(update)
    if not text and not replied:
        await safe_reply(update, usage_box("ask", "<message>", "Ask a support question (or reply to message/file/photo)"))
        return
    tid = ticket_find_open_by_student(uid)
    if tid is None:
        tid = ticket_open(uid, update.effective_user.first_name or "")
        db_log("INFO", "ticket_open", {"ticket_id": tid, "student_id": uid})
    if text:
        ticket_add_msg(tid, "STUDENT", uid, text)
    elif replied:
        ticket_add_msg(tid, "STUDENT", uid, "[MEDIA MESSAGE]")
    staff_ids = list_staff_ids()
    profile = mention_user(uid, update.effective_user.first_name or str(uid))
    uname = f"@{update.effective_user.username}" if getattr(update.effective_user, 'username', None) else ""
    header = f"📩 New Support Message\nTicket: <code>{tid}</code>\nFrom: {profile} <code>{uid}</code> {h(uname)}"
    if text:
        for sid in staff_ids:
            await safe_send_text(context.bot, sid, f"{header}\n\n<pre>{h(text)}</pre>")
    else:
        for sid in staff_ids:
            await safe_send_text(context.bot, sid, f"{header}\n\n[MEDIA MESSAGE RECEIVED]")
    if replied:
        for sid in staff_ids:
            await safe_copy_message(context.bot, chat_id=sid, from_chat_id=replied.chat_id, message_id=replied.message_id, protect=False)
    await ok(update, "Message Received", f"Ticket ID: {tid}\nA staff member will respond soon.")


@require_admin
async def cmd_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await safe_reply(update, usage_box("reply", "<ticket_id> [message]", "Reply to support ticket (or reply to message/file/photo)"))
        return
    tid = int(context.args[0]); text = " ".join(context.args[1:]).strip(); replied = update.message.reply_to_message if update.message else None
    if not text:
        text = reply_text_or_caption(update)
    tr = ticket_get(tid)
    if not tr:
        await warn_html(update, "Ticket Not Found", f"No ticket with ID <code>{h(tid)}</code> found")
        return
    if tr["status"] != "OPEN":
        await err_html(update, "Ticket Closed", f"Ticket <code>{h(tid)}</code> is already <b>CLOSED</b>")
        return
    student_id = int(tr["student_id"])
    if is_banned(student_id):
        await warn(update, "User Banned", "The user is currently banned.")
        return
    sent_any = False
    if text:
        ticket_add_msg(tid, "STAFF", update.effective_user.id, text)
        await safe_send_text(context.bot, student_id, f"💬 Support Reply (Ticket <code>{tid}</code>)\n\n<pre>{h(text)}</pre>")
        sent_any = True
    if replied:
        okc = await safe_copy_message(context.bot, chat_id=student_id, from_chat_id=replied.chat_id, message_id=replied.message_id, protect=False)
        if okc:
            ticket_add_msg(tid, "STAFF", update.effective_user.id, "[MEDIA MESSAGE]")
            sent_any = True
    if sent_any:
        await ok_html(update, "Reply Sent", f"<b>Ticket:</b> <code>{h(tid)}</code>\nMessage(s) sent to user.")
    else:
        await warn(update, "No Content", "Reply to a message/file/photo or provide text inline")


def _format_user_poll_solution(question: str, options: List[str], model_ans: int, official_ans: int, model_expl: str, official_expl: str, why_not: Dict[str, str], conf: int) -> str:
    opts = [(o or "").strip() for o in (options or []) if (o or "").strip()][:5]
    copy_block = _copyable_quiz_block(question or "", opts)
    lines = ["<b>📊 Quiz Solution</b>", "", "<b>Question + Options (copyable):</b>", copy_block]
    if 1 <= int(model_ans or 0) <= len(opts):
        lines.append(f"\n<b>✅ AI Response:</b> <b>{_safe_letter(model_ans)}</b>) {h(opts[model_ans-1])}")
    if official_ans > 0 and official_ans <= len(opts):
        tag = "✅ Match" if official_ans == model_ans else "❌ Mismatch"
        lines.append(f"<b>📌 Given Answer:</b> <b>{_safe_letter(official_ans)}</b>) {h(opts[official_ans-1])} <i>({tag})</i>")
    if model_expl:
        lines.append(f"\n<b>Explanation (Solved):</b>\n<pre>{h(model_expl)}</pre>")
    if official_expl:
        lines.append(f"\n<b>Explanation (From Quiz):</b>\n<pre>{h(official_expl)}</pre>")
    if why_not:
        wn = []
        for k in ["A","B","C","D","E"]:
            v = (why_not or {}).get(k)
            if v:
                wn.append(f"• <b>{h(k)}</b>: {h(v)}")
        if wn:
            lines.append("\n<b>Why other options are wrong:</b>\n" + "\n".join(wn))
    return "\n".join(lines).strip()


async def on_solver_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return
    q = update.callback_query
    await q.answer("Processing…", show_alert=False)
    data = (q.data or "").strip()
    m = re.match(r"^solve:([GPD]):([0-9a-f]{6,16})$", data)
    if not m:
        return
    model = m.group(1); token = m.group(2)
    store = _pending_store(context); req = store.get(token)
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
    problem_text = str(payload.get("text") or "").strip(); kind = str(req.get("kind") or "text").lower()
    with contextlib.suppress(Exception):
        await q.edit_message_text(ui_box_text("Solving", "Please wait… Processing your request.", emoji="⏳"), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    try:
        if kind == "poll" and payload.get("question"):
            question = str(payload.get("question", "")).strip(); options = payload.get("options", [])
            if model == "G": result = await _run_blocking(_role_of(uid), gemini_solve_mcq_json, question, options)
            elif model == "P": result = await _run_blocking(_role_of(uid), perplexity_solve_mcq_json, question, options)
            else: result = await _run_blocking(_role_of(uid), deepseek_solve_mcq_json, question, options)
            raw_expl = str(result.get('explanation', '') or ""); clean_expl = clean_latex(raw_expl)
            raw_why_not = result.get("why_not", {}) or {}; clean_why_not = {k: clean_latex(v) for k, v in raw_why_not.items()}
            msg_html = _format_user_poll_solution(question=question, options=options, model_ans=int(result.get("answer", 0) or 0), official_ans=int(payload.get("official_ans", 0) or 0), model_expl=f"[{['Gemini', 'Perplexity', 'DeepSeek'][['G','P','D'].index(model)]}]\n{clean_expl}".strip(), official_expl=str(payload.get("official_expl", "")).strip(), why_not=clean_why_not, conf=int(result.get("confidence", 0) or 0))
            kb = _verify_kb(token, model, "poll")
        else:
            if model == "G": answer = await _run_blocking(_role_of(uid), gemini_solve_text, problem_text)
            elif model == "P": answer = await _run_blocking(_role_of(uid), perplexity_solve_text, problem_text)
            else: answer = await _run_blocking(_role_of(uid), deepseek_solve_text, problem_text)
            msg_html = f"<pre>{h(answer)}</pre>"
            kb = _verify_kb(token, model, "text")
        with contextlib.suppress(Exception):
            await q.edit_message_text(msg_html, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            if q.message and kind == "poll":
                _remember_quiz_context(context, q.message.message_id, payload)
    except Exception as e:
        db_log("ERROR", "solver_callback_failed", {"user_id": uid, "model": model, "error": str(e)})
        with contextlib.suppress(Exception):
            await q.edit_message_text(ui_box_text("Solve Failed", str(e)[:180], emoji="❌"), parse_mode=ParseMode.HTML)


async def send_poll_verify_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE, poll_payload: Dict[str, Any], msg_html: str) -> None:
    token = _make_token(); store = _pending_store(context); uid = update.effective_user.id
    store[token] = {"uid": uid, "chat_id": update.effective_chat.id if update.effective_chat else uid, "kind": "poll", "payload": poll_payload}
    kb = _verify_kb(token, "G", "poll")
    sent = await update.message.reply_text(msg_html, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    _remember_quiz_context(context, sent.message_id, poll_payload)


async def handle_user_poll_solver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.effective_user or not update.message or not update.message.poll:
        return
    uid = update.effective_user.id
    if is_banned(uid):
        return
    if not await enforce_required_memberships(update, context):
        return
    role = get_role(uid)
    private = is_private_chat(update)
    if role == ROLE_USER:
        if not solver_mode_on(uid):
            return
        if not private and not is_group_ai_enabled(update.effective_chat.id):
            return
    elif role in (ROLE_ADMIN, ROLE_OWNER):
        if not private or not solver_mode_on(uid):
            return
    else:
        return
    poll = update.message.poll
    qtext = (poll.question or "").strip(); options = [o.text for o in (poll.options or [])]; options = [x.strip() for x in options if (x or "").strip()]
    official_expl = str(getattr(poll, "explanation", "") or "").strip(); official_ans = _poll_official_answer(poll)
    spinner_msg = None; spinner_task = None
    try:
        spinner_msg = await update.message.reply_text("🔎 Searching")
        spinner_task = asyncio.create_task(_spinner_task(context.bot, spinner_msg.chat_id, spinner_msg.message_id))
        data = await _run_blocking('user', gemini_solve_mcq_json, qtext, options)
        model_ans = int(data.get("answer", 0) or 0); conf = int(data.get("confidence", 0) or 0)
        raw_expl = str(data.get("explanation", "") or "").strip(); model_expl = clean_latex(raw_expl)
        raw_why_not = data.get("why_not", {}) or {}; why_not = {k: clean_latex(v) for k, v in raw_why_not.items()}
        spinner_task.cancel()
        with contextlib.suppress(Exception): await context.bot.delete_message(chat_id=spinner_msg.chat_id, message_id=spinner_msg.message_id)
        msg_html = _format_user_poll_solution(question=qtext, options=options, model_ans=model_ans, official_ans=official_ans, model_expl=f"[Gemini 3 Flash]\n{model_expl}".strip(), official_expl=official_expl, why_not=why_not if isinstance(why_not, dict) else {}, conf=conf)
        poll_payload = {"question": qtext, "options": options, "official_ans": official_ans, "official_expl": official_expl}
        await send_poll_verify_buttons(update, context, poll_payload, msg_html)
    except Exception as e:
        if spinner_task: spinner_task.cancel()
        if spinner_msg:
            with contextlib.suppress(Exception): await context.bot.delete_message(chat_id=spinner_msg.chat_id, message_id=spinner_msg.message_id)
        db_log("ERROR", "poll_solver_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Solve Failed", f"{h(str(e)[:160])}")


async def handle_user_text_unusual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id
    if is_banned(uid):
        return
    if not await enforce_required_memberships(update, context):
        return
    role = get_role(uid)
    private = is_private_chat(update)
    if role == ROLE_USER:
        if not solver_mode_on(uid):
            if private:
                await warn_unauthorized(update, "This bot is currently restricted for staff operations. Please use /ask [message] for support.")
            return
        if not private and not is_group_ai_enabled(update.effective_chat.id):
            return
    elif role in (ROLE_ADMIN, ROLE_OWNER):
        if not private or not solver_mode_on(uid):
            return
    else:
        return
    user_text = (update.message.text or "").strip()
    if not user_text:
        return
    # If user replied to a previous quiz solution, ask with that quiz context
    reply_msg = update.message.reply_to_message
    if reply_msg:
        ctx = _get_quiz_context(context, reply_msg.message_id)
        if ctx:
            qtext = str(ctx.get("question", "") or "").strip()
            opts = ctx.get("options", []) or []
            prompt = f"Question:\n{qtext}\n\nOptions:\n" + "\n".join([f"{_safe_letter(i+1)}. {o}" for i,o in enumerate(opts)]) + f"\n\nUser follow-up:\n{user_text}"
            await send_solver_picker(update, context, prompt)
            return
    await send_solver_picker(update, context, user_text)


def build_app() -> Application:
    db_init(); extra_db_init()
    builder = ApplicationBuilder().token(BOT_TOKEN)
    try:
        builder = builder.concurrent_updates(64)
    except Exception:
        pass
    app = builder.build()
    app.add_handler(_cmdh("start", cmd_start))
    app.add_handler(_cmdh("help", cmd_help))
    app.add_handler(_cmdh("commands", cmd_commands))
    app.add_handler(_cmdh("features", cmd_features))
    app.add_handler(CallbackQueryHandler(on_solver_callback, pattern=r"^solve:"))
    app.add_handler(CallbackQueryHandler(on_genquiz_callback, pattern=r"^genquiz:"))
    app.add_handler(CallbackQueryHandler(on_emoji_quiz_callback, pattern=r"^eq:"))
    app.add_handler(CallbackQueryHandler(on_required_verify_callback, pattern=r"^req:verify$"))
    app.add_handler(_cmdh("ask", cmd_ask))
    app.add_handler(_cmdh("scanhelp", cmd_scanhelp))
    app.add_handler(_cmdh("vision_on", cmd_vision_on))
    app.add_handler(_cmdh("vision_off", cmd_vision_off))
    app.add_handler(_cmdh("solve_on", cmd_solve_on))
    app.add_handler(_cmdh("solve_off", cmd_solve_off))
    app.add_handler(_cmdh("himusai_on", cmd_himusai_on))
    app.add_handler(_cmdh("himusai_off", cmd_himusai_off))
    app.add_handler(_cmdh("probaho_on", cmd_probaho_on))
    app.add_handler(_cmdh("probaho_off", cmd_probaho_off))
    app.add_handler(_cmdh("explain_on", cmd_explain_on))
    app.add_handler(_cmdh("explain_off", cmd_explain_off))
    app.add_handler(_cmdh("quizprefix", cmd_quizprefix))
    app.add_handler(_cmdh("quizlink", cmd_quizlink))
    app.add_handler(_cmdh("addadmin", cmd_addadmin))
    app.add_handler(_cmdh("removeadmin", cmd_removeadmin))
    app.add_handler(_cmdh("grantall", cmd_grantall))
    app.add_handler(_cmdh("revokeall", cmd_revokeall))
    app.add_handler(_cmdh("grantvision", cmd_grantvision))
    app.add_handler(_cmdh("revokevision", cmd_revokevision))
    app.add_handler(_cmdh("addrequired", cmd_addrequired))
    app.add_handler(_cmdh("delrequired", cmd_delrequired))
    app.add_handler(_cmdh("listrequired", cmd_listrequired))
    app.add_handler(_cmdh("ownerstats", cmd_ownerstats))
    app.add_handler(_cmdh("users", cmd_users))
    app.add_handler(_cmdh("filter", cmd_filter))
    app.add_handler(_cmdh("done", cmd_done))
    app.add_handler(_cmdh("clear", cmd_clear))
    app.add_handler(_cmdh("addchannel", cmd_addchannel))
    app.add_handler(_cmdh("listchannels", cmd_listchannels))
    app.add_handler(_cmdh("removechannel", cmd_removechannel))
    app.add_handler(_cmdh("setprefix", cmd_setprefix))
    app.add_handler(_cmdh("setexplink", cmd_setexplink))
    app.add_handler(_cmdh("post", cmd_post))
    app.add_handler(_cmdh("postemoji", cmd_postemoji))
    app.add_handler(_cmdh("broadcast", cmd_broadcast))
    app.add_handler(_cmdh("adminpanel", cmd_adminpanel))
    app.add_handler(_cmdh("reply", cmd_reply))
    app.add_handler(_cmdh("close", cmd_close))
    app.add_handler(_cmdh("ban", cmd_ban))
    app.add_handler(_cmdh("unban", cmd_unban))
    app.add_handler(_cmdh("banned", cmd_banned))
    app.add_handler(_cmdh("private_send", cmd_private_send))
    app.add_handler(_cmdh("send_private", cmd_private_send))
    app.add_handler(MessageHandler(filters.POLL, handle_poll))
    app.add_handler(MessageHandler(filters.POLL, handle_user_poll_solver), group=1)
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_user_text_unusual), group=1)
    app.add_error_handler(on_error)
    return app


