# ──────────────────────────────────────────────────────────────────────────────
# Section: 10_strong_fix_overrides_gpt
# Original lines: 6105..6886
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===========================
# STRONG FIX OVERRIDES (GPT)
# ===========================
USE_OFFICIAL_GEMINI_REST_FALLBACK = False
USE_GEMINI_REST_FOR_GENQUIZ = False
REQUIRED_DEFAULT_JOIN_URL = "https://t.me/FX_Ur_Target"
REQUIRED_DEFAULT_CHAT_USERNAME = "@FX_Ur_Target"
REQUIRED_DEFAULT_CHAT_TITLE = "✨TARGET🎯"


def _effective_required_targets() -> List[Dict[str, Any]]:
    rows = required_chat_list()
    targets: List[Dict[str, Any]] = []
    has_default = False
    for r in rows:
        try:
            cid = int(r["chat_id"])
        except Exception:
            continue
        title = str(r["title"] or cid)
        tl = title.lower()
        if "fx_ur_target" in tl:
            has_default = True
        if title.startswith("@"):
            url = f"https://t.me/{title.lstrip('@')}"
        elif "t.me/" in title:
            url = title if title.startswith("http") else ("https://" + title.lstrip("/"))
        else:
            url = REQUIRED_DEFAULT_JOIN_URL
        targets.append({"chat_id": cid, "title": title, "url": url})
    if not has_default:
        targets.insert(0, {
            "chat_id": REQUIRED_DEFAULT_CHAT_USERNAME,
            "title": REQUIRED_DEFAULT_CHAT_TITLE,
            "url": REQUIRED_DEFAULT_JOIN_URL,
        })
    return targets


def _required_join_kb() -> InlineKeyboardMarkup:
    rows = []
    targets = _effective_required_targets()
    for i, t in enumerate(targets[:8]):
        title = str(t.get("title") or "Channel")
        label = "Join Channel" if i == 0 else f"Join {title}"
        rows.append([InlineKeyboardButton(label, url=str(t.get("url") or REQUIRED_DEFAULT_JOIN_URL))])
    rows.append([InlineKeyboardButton("✅ Verify", callback_data="req:verify")])
    return InlineKeyboardMarkup(rows)


def _warn_count_or_increment(user_id: int, *, throttle_seconds: int = 45) -> int:
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT warn_count, last_warn_at FROM user_warnings WHERE user_id=?", (int(user_id),))
    row = cur.fetchone(); conn.close()
    if row and row["last_warn_at"]:
        try:
            last = dt.datetime.fromisoformat(str(row["last_warn_at"]))
            now = dt.datetime.now(last.tzinfo or dt.timezone.utc)
            if abs((now - last).total_seconds()) <= throttle_seconds:
                return int(row["warn_count"] or 0)
        except Exception:
            pass
    return inc_warn_count(user_id)


async def _send_join_required_message(update: Update, context: ContextTypes.DEFAULT_TYPE, missing: List[str], count: int) -> None:
    names = ", ".join(missing[:10]) if missing else REQUIRED_DEFAULT_CHAT_TITLE
    msg = ui_box_text("Join Required", f"Please join: {names}\nWarning: {count}/5", emoji="⚠️")
    if update.message:
        old_mid = None
        try:
            old_mid = context.user_data.get("_req_prompt_mid")
        except Exception:
            old_mid = None
        if old_mid:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=int(old_mid))
        try:
            sent = await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=_required_join_kb(), disable_web_page_preview=True)
            try:
                context.user_data["_req_prompt_mid"] = sent.message_id
            except Exception:
                pass
            return
        except Exception:
            pass
    if update.callback_query and update.callback_query.message:
        with contextlib.suppress(Exception):
            await update.callback_query.message.edit_text(msg, parse_mode=ParseMode.HTML, reply_markup=_required_join_kb(), disable_web_page_preview=True)
            return
    if update.effective_user:
        await safe_send_text(context.bot, update.effective_user.id, msg, reply_markup=_required_join_kb())


async def user_meets_required_memberships(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Tuple[bool, List[str]]:
    targets = _effective_required_targets()
    if not targets:
        return True, []
    missing: List[str] = []
    for t in targets:
        cid = t.get("chat_id")
        title = str(t.get("title") or cid)
        try:
            member = await context.bot.get_chat_member(cid, int(user_id))
            status = str(getattr(member, "status", "")).lower()
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
    count = _warn_count_or_increment(uid)
    if count >= 5:
        set_ban(uid, True)
        audit_ban(OWNER_ID, uid, "BAN")
        with contextlib.suppress(Exception):
            await safe_send_text(context.bot, uid, f"🚫 You are banned from <b>{h(BOT_BRAND)}</b> for leaving required channel/group. Contact: {h(OWNER_CONTACT)}")
        return False
    await _send_join_required_message(update, context, missing, count)
    return False


async def on_required_verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return
    q = update.callback_query
    uid = q.from_user.id if q.from_user else 0
    if not uid:
        with contextlib.suppress(Exception):
            await q.answer("User not found.", show_alert=True)
        return
    if is_owner(uid) or is_admin(uid):
        with contextlib.suppress(Exception):
            await q.answer("Verified.", show_alert=False)
        return
    ok, missing = await user_meets_required_memberships(context, uid)
    if ok:
        reset_warn_count(uid)
        with contextlib.suppress(Exception):
            await q.answer("Verification successful.", show_alert=True)
        with contextlib.suppress(Exception):
            if q.message:
                await q.message.delete()
        try:
            body_html = (
                f"<b>Your Role:</b> <code>{h(get_role(uid))}</code>"
                f"\n\nUse <code>/help</code> for commands or <code>/commands</code> for a quick list."
            )
            msg = ui_box_html(f"Welcome to {BOT_BRAND}", body_html, emoji="👋")
            await safe_send_text(context.bot, uid, msg)
        except Exception:
            pass
        return
    count = _warn_count_or_increment(uid)
    with contextlib.suppress(Exception):
        await q.answer("Still not joined. Please join first.", show_alert=True)
    if count >= 5:
        set_ban(uid, True)
        audit_ban(OWNER_ID, uid, "BAN")
        with contextlib.suppress(Exception):
            if q.message:
                await q.message.edit_text(f"🚫 You are banned from {BOT_BRAND}. Contact: {OWNER_CONTACT}")
        return
    await _send_join_required_message(update, context, missing, count)


def _all_commands_for(uid: int) -> List[Tuple[str, List[Tuple[str, str]]]]:
    role = get_role(uid)
    sections: List[Tuple[str, List[Tuple[str, str]]]] = []
    user_cmds = [
        ("/start", "Welcome / membership check"),
        ("/help", "Detailed guide"),
        ("/commands", "All commands list"),
        ("/ask", "Contact support"),
        ("/solve_on", "Enable AI solving"),
        ("/solve_off", "Disable AI solving"),
    ]
    if can_use_vision(uid):
        user_cmds += [
            ("/scanhelp", "Image-to-quiz guide"),
            ("/vision_on", "Enable image extraction"),
            ("/vision_off", "Disable image extraction"),
        ]
    sections.append(("👤 User Commands", user_cmds))
    if role in (ROLE_ADMIN, ROLE_OWNER):
        admin_cmds = [
            ("/filter", "Add parser filter text"),
            ("/done", "Export CSV + JSON, then clear buffer"),
            ("/clear", "Clear buffer"),
            ("/addchannel", "Add target channel"),
            ("/listchannels", "List available channels"),
            ("/removechannel", "Remove a channel"),
            ("/setprefix", "Set channel prefix"),
            ("/setexplink", "Set explanation link"),
            ("/post", "Post normal quizzes"),
            ("/postemoji", "Post emoji quizzes"),
            ("/broadcast", "Broadcast message to users"),
            ("/adminpanel", "Posting stats"),
            ("/reply", "Reply to support ticket"),
            ("/close", "Close support ticket"),
            ("/ban", "Ban a user"),
            ("/unban", "Unban a user"),
            ("/banned", "View bans"),
            ("/private_send", "Send private message to a user"),
            ("/send_private", "Alias of /private_send"),
            ("/himusai_on", "Enable admin inbox AI-only mode"),
            ("/himusai_off", "Disable admin inbox AI-only mode"),
            ("/probaho_on", "Enable group user AI"),
            ("/probaho_off", "Disable group user AI"),
            ("/explain_on", "Enable explanation in quiz + export"),
            ("/explain_off", "Disable explanation in quiz + export"),
            ("/quizprefix", "Set generated quiz prefix"),
            ("/quizlink", "Set generated quiz link"),
        ]
        sections.append(("🛠 Staff Commands", admin_cmds))
    if role == ROLE_OWNER:
        owner_cmds = [
            ("/addadmin", "Promote a user to admin"),
            ("/removeadmin", "Remove admin role"),
            ("/grantall", "Grant admin all-channel access"),
            ("/revokeall", "Revoke all-channel access"),
            ("/grantvision", "Grant image extraction access"),
            ("/revokevision", "Revoke image extraction access"),
            ("/addrequired", "Add required channel/group"),
            ("/delrequired", "Remove required channel/group"),
            ("/listrequired", "List required channels/groups"),
            ("/ownerstats", "Owner dashboard"),
            ("/users", "Export started users JSON"),
        ]
        sections.append(("👑 Owner Commands", owner_cmds))
    return sections


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\n\nContact: {OWNER_CONTACT}")
        return
    sections = _all_commands_for(uid)
    blocks = [ui_box_html(f"{BOT_BRAND} — Command Guide", f"Owner: {h(OWNER_CONTACT)}\nUse only the commands available for your role.", emoji="📚")]
    for title, items in sections:
        body = "\n".join([f"<code>{h(cmd)}</code> — {h(desc)}" for cmd, desc in items])
        blocks.append(ui_box_html(title, body, emoji="•"))
    await safe_reply(update, "\n\n".join(blocks))


async def cmd_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\n\nContact: {OWNER_CONTACT}")
        return
    sections = _all_commands_for(uid)
    parts = [ui_box_html("All Available Commands", "Choose a command below.", emoji="📋")]
    for title, items in sections:
        body = "\n".join([f"<code>{h(cmd)}</code> — {h(desc)}" for cmd, desc in items])
        parts.append(ui_box_html(title, body, emoji="👤" if "User" in title else ("🛠" if "Staff" in title else "👑")))
    await safe_reply(update, "\n\n".join(parts))


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\n\nContact: {OWNER_CONTACT}")
        return
    role = get_role(uid)
    await refresh_private_command_menu(context, uid)
    body_html = (
        f"<b>Your Role:</b> <code>{h(role)}</code>"
        f"\n\nUse <code>/help</code> for commands or <code>/commands</code> for a quick list."
    )
    msg = ui_box_html(f"Welcome to {BOT_BRAND}", body_html, emoji="👋")
    await safe_reply(update, msg)


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
    await ok_html(update, "Solver Enabled", "Now just send your question as text and the bot will reply with a solved explanation.\n\nTurn off anytime using <code>/solve_off</code>.", emoji="🧠")


async def cmd_solve_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\n\nContact: {OWNER_CONTACT}")
        return
    if get_role(uid) != ROLE_USER:
        await warn(update, "Not Available", "Problem-solving chat is intended for normal users.")
        return
    set_solver_mode_on(uid, False)
    await ok_html(update, "Solver Disabled", "The bot will no longer auto-solve your text messages.", emoji="🧠")


def _extract_ticket_id_from_message(msg) -> Optional[int]:
    if not msg:
        return None
    texts = []
    for attr in ("text", "caption"):
        val = getattr(msg, attr, None)
        if val:
            texts.append(str(val))
    if not texts:
        return None
    blob = "\n".join(texts)
    m = re.search(r"Ticket\s*:?\s*(\d+)", blob, re.I)
    if not m:
        m = re.search(r"Ticket\s*ID\s*:?\s*(\d+)", blob, re.I)
    return int(m.group(1)) if m else None


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\nContact: {OWNER_CONTACT}")
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
    header = f"📩 New Support Message\nTicket: {tid}\nFrom: {profile} | <code>{uid}</code> {h(uname)}"
    if text:
        for sid in staff_ids:
            body = f"{header}\n\n{h(text)}"
            await safe_send_text(context.bot, sid, body)
    else:
        for sid in staff_ids:
            await safe_send_text(context.bot, sid, f"{header}\n\n[MEDIA MESSAGE RECEIVED]")
    if replied:
        for sid in staff_ids:
            await safe_copy_message(context.bot, chat_id=sid, from_chat_id=replied.chat_id, message_id=replied.message_id, protect=False)
    await ok(update, "Message Received", "A staff member will respond soon.")


@require_admin
async def cmd_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    replied = update.message.reply_to_message if update.message else None
    tid = None
    if context.args and str(context.args[0]).isdigit():
        tid = int(context.args[0])
        text = " ".join(context.args[1:]).strip()
    else:
        tid = _extract_ticket_id_from_message(replied)
        text = " ".join(context.args).strip()
    if tid is None:
        await safe_reply(update, usage_box("reply", "<ticket_id> [message]", "Reply to support ticket, or reply to the support card and use /reply [message]"))
        return
    if not text:
        text = reply_text_or_caption(update)
    tr = ticket_get(int(tid))
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
        ticket_add_msg(int(tid), "STAFF", update.effective_user.id, text)
        if looks_like_programming_request(text):
            await safe_send_text(context.bot, student_id, f"💬 Support Reply\n\n<pre>{h(text)}</pre>")
        else:
            await safe_send_text(context.bot, student_id, f"💬 Support Reply\n\n{h(text)}")
        sent_any = True
    if replied and getattr(replied, 'message_id', None):
        okc = await safe_copy_message(context.bot, chat_id=student_id, from_chat_id=replied.chat_id, message_id=replied.message_id, protect=False)
        if okc:
            ticket_add_msg(int(tid), "STAFF", update.effective_user.id, "[MEDIA MESSAGE]")
            sent_any = True
    if sent_any:
        await ok_html(update, "Reply Sent", f"<b>Ticket:</b> <code>{h(tid)}</code>\nMessage(s) sent to user.")
    else:
        await warn(update, "No Content", "Reply to a message/file/photo or provide text inline")


@require_owner
async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT user_id, role, first_name, username, is_banned, created_at, last_seen_at FROM users ORDER BY created_at ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    if not rows:
        await warn(update, "No Users", "No users found.")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        path = f.name
    try:
        with open(path, "rb") as rf:
            await context.bot.send_document(chat_id=update.effective_user.id, document=rf, filename="probaho_users.json", caption="All started users")
    finally:
        with contextlib.suppress(Exception):
            os.unlink(path)


def gemini_solve_text(problem_text: str) -> str:
    prompt = (STRICT_SYSTEM_PROMPT + "\n\nUser Message:\n" + (problem_text or "").strip()).strip()
    last_err = None
    try:
        out = gemini3_solve(prompt)
        if out and str(out).strip():
            return str(out).strip()
    except Exception as e:
        last_err = e
    if USE_PERPLEXITY_FALLBACK:
        try:
            alt = query_ai(prompt)
            if alt:
                return alt.strip()
        except Exception as e:
            last_err = e
    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEY:
        try:
            return call_gemini_text_rest(prompt, timeout_seconds=18).strip()
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Solver failed: {str(last_err)[:120] if last_err else 'all backends unavailable'}")


def _infer_option_from_text(text: str, n: int) -> int:
    s = (text or "").upper()
    patterns = [
        r"FINAL ANSWER\s*[:\-]\s*([A-E])",
        r"CORRECT ANSWER\s*[:\-]\s*([A-E])",
        r"ANSWER\s*[:\-]\s*([A-E])",
        r"OPTION\s*([A-E])",
        r"\(([A-E])\)",
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            idx = ord(m.group(1)) - 64
            if 1 <= idx <= n:
                return idx
    return 0


def gemini_solve_mcq_json(question: str, options: List[str]) -> Dict[str, Any]:
    q = (question or "").strip()
    opts = [(o or "").strip() for o in (options or []) if (o or "").strip()][:5]
    if len(opts) < 2:
        raise ValueError("Not enough options to solve.")
    opt_lines = "\n".join([f"{_safe_letter(i+1)}. {opts[i]}" for i in range(len(opts))])
    prompt = (
        "Return STRICT JSON only. No markdown. No extra text.\n\n"
        "Task: Solve the following MCQ and pick the correct option.\n"
        "Rules:\n"
        "- answer must be 1-5 (A=1,B=2,C=3,D=4,E=5). If unsure, pick the best option.\n"
        "- explanation: clear exam-style explanation.\n"
        "- why_not: short reason for wrong options.\n"
        "- confidence: 0-100 integer.\n\n"
        f"Question:\n{q}\n\nOptions:\n{opt_lines}\n\n"
        "JSON format:\n"
        "{\"answer\":1,\"confidence\":0,\"explanation\":\"...\",\"why_not\":{\"A\":\"..\",\"B\":\"..\",\"C\":\"..\",\"D\":\"..\",\"E\":\"..\"}}"
    )
    last_err = None
    try:
        raw = gemini3_solve(prompt)
        data = _extract_json_strict(raw)
        if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
            return data
    except Exception as e:
        last_err = e
    if USE_PERPLEXITY_FALLBACK:
        try:
            alt = query_ai(prompt)
            if alt:
                try:
                    data = _extract_json_strict(alt)
                    if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                        return data
                except Exception:
                    pass
                inferred = _infer_option_from_text(alt, len(opts))
                return {
                    "answer": inferred,
                    "confidence": 0,
                    "explanation": (alt[:1800] if isinstance(alt, str) else str(alt)[:1800]),
                    "why_not": {},
                }
        except Exception as e:
            last_err = e
    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEY:
        try:
            raw2 = call_gemini_text_rest(prompt, timeout_seconds=18, force_json=True)
            data2 = _extract_json_strict(raw2)
            if isinstance(data2, dict):
                return data2
        except Exception as e:
            last_err = e
    raise RuntimeError(f"MCQ solver failed: {str(last_err)[:120] if last_err else 'all backends unavailable'}")


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
    with contextlib.suppress(Exception):
        await q.edit_message_text(ui_box_text("Solving", "Please wait… Processing your request.", emoji="⏳"), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    try:
        if kind == "poll" and payload.get("question"):
            question = str(payload.get("question", "")).strip()
            options = payload.get("options", [])
            if model == "G":
                result = await _run_blocking(_role_of(uid), gemini_solve_mcq_json, question, options)
                model_name = "Gemini"
            elif model == "P":
                result = await _run_blocking(_role_of(uid), perplexity_solve_mcq_json, question, options)
                model_name = "Perplexity"
            else:
                result = await _run_blocking(_role_of(uid), deepseek_solve_mcq_json, question, options)
                model_name = "DeepSeek"
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
            if model == "G":
                answer = await _run_blocking(_role_of(uid), gemini_solve_text, problem_text)
            elif model == "P":
                answer = await _run_blocking(_role_of(uid), perplexity_solve_text, problem_text)
            else:
                answer = await _run_blocking(_role_of(uid), deepseek_solve_text, problem_text)
            if (is_admin(uid) or is_owner(uid)) and (looks_like_programming_request(problem_text) or looks_like_programming_request(answer)):
                msg_html = f"<pre>{h(answer)}</pre>"
            else:
                msg_html = h(answer)
            kb = _verify_kb(token, model, "text")
        with contextlib.suppress(Exception):
            await q.edit_message_text(msg_html, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            if q.message and kind == "poll":
                _remember_quiz_context(context, q.message.message_id, payload)
    except Exception as e:
        db_log("ERROR", "solver_callback_failed", {"user_id": uid, "model": model, "error": str(e)})
        with contextlib.suppress(Exception):
            await q.edit_message_text(ui_box_text("Solve Failed", str(e)[:180], emoji="❌"), parse_mode=ParseMode.HTML)


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
    reply_msg = update.message.reply_to_message
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
            await send_solver_picker(update, context, prompt)
            return
    await send_solver_picker(update, context, user_text)


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
    sent = 0
    sent_ids = []
    prefix = str(getattr(ch, "prefix", "") or "").strip()
    title = prefix if prefix else BOT_BRAND
    for bid, payload in items:
        qtext, opts, corr_idx0, explanation = quiz_to_poll_parts(payload)
        labels = EMOJI_BUTTONS[:len(opts)]
        block = _copyable_quiz_block(qtext, opts, labels=labels)
        msg_html = f"<b>{h(title)}</b>\n\n{block}"
        quiz_id = uuid.uuid4().hex[:10]
        try:
            m = await context.bot.send_message(
                chat_id=ch.channel_chat_id,
                text=msg_html,
                parse_mode=ParseMode.HTML,
                reply_markup=emoji_quiz_keyboard(len(opts), quiz_id),
                disable_web_page_preview=True,
            )
            sent += 1
            sent_ids.append(bid)
            emoji_quiz_save(
                quiz_id,
                ch.channel_chat_id,
                m.message_id,
                {
                    "question": qtext,
                    "options": opts,
                    "correct_answer": corr_idx0 + 1 if corr_idx0 >= 0 else 0,
                    "explanation": explanation,
                    "prefix": title,
                },
                admin_id,
            )
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
        await q.answer("⚠️ আগে required channel-এ join করো, তারপর Verify দাও।", show_alert=True)
        return
    quiz = emoji_quiz_get(quiz_id)
    if not quiz:
        await q.answer("Quiz expired or not found.", show_alert=True)
        return
    saved_choice = emoji_quiz_user_choice(quiz_id, uid)
    if saved_choice and int(saved_choice) != int(selected):
        saved_label = EMOJI_BUTTONS[saved_choice - 1] if 0 < saved_choice <= len(EMOJI_BUTTONS) else str(saved_choice)
        await q.answer(f"⚠️ তুমি আগে {saved_label} দিয়ে answer দিয়েছো। Result দেখতে একই reaction-এ tap করো।", show_alert=True)
        return
    correct = int(quiz.get("correct_answer", 0) or 0)
    if not saved_choice:
        emoji_quiz_record_answer(quiz_id, uid, selected, (selected == correct and correct > 0))
        saved_choice = selected
    counts = emoji_quiz_counts(quiz_id)
    opts = quiz.get("options", []) or []
    stats_text = " | ".join([f"{EMOJI_BUTTONS[i-1]}={counts.get(i, 0)}" for i in range(1, len(opts) + 1)])
    expl = clean_latex(str(quiz.get("explanation", "") or "").strip())
    expl = re.sub(r"\s+", " ", expl).strip()
    if len(expl) > 90:
        expl = expl[:87] + "..."
    sel_label = EMOJI_BUTTONS[saved_choice - 1] if 0 < saved_choice <= len(EMOJI_BUTTONS) else str(saved_choice)
    corr_label = EMOJI_BUTTONS[correct - 1] if 0 < correct <= len(EMOJI_BUTTONS) else str(correct)
    if saved_choice == correct and correct > 0:
        msg = f"✅ Correct\nYour reaction: {sel_label}\n{stats_text}"
    else:
        msg = f"❌ Wrong\nYour reaction: {sel_label}\n✅ Correct: {corr_label}\n{stats_text}"
    if expl:
        msg += f"\n\n{expl}"
    await q.answer(msg[:190], show_alert=True)


_original_handle_image = handle_image


