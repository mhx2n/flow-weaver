# ──────────────────────────────────────────────────────────────────────────────
# Section: 11_final_stable_overrides
# Original lines: 6887..7803
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===========================
# FINAL STABLE OVERRIDES
# ===========================
USE_OFFICIAL_GEMINI_REST_FALLBACK = False
USE_GEMINI_REST_FOR_GENQUIZ = True
REQUIRED_DEFAULT_JOIN_URL = "https://t.me/FX_Ur_Target"
REQUIRED_DEFAULT_CHAT_USERNAME = "@FX_Ur_Target"
REQUIRED_DEFAULT_CHAT_TITLE = "✨TARGET🎯"


def _effective_required_targets() -> List[Dict[str, Any]]:
    rows = required_chat_list()
    targets: List[Dict[str, Any]] = []
    seen = set()
    for r in rows:
        try:
            cid = int(r["chat_id"])
        except Exception:
            cid = r["chat_id"]
        title = str(r["title"] or cid)
        if title.startswith("@"):
            url = f"https://t.me/{title.lstrip('@')}"
        elif "t.me/" in title:
            url = title if title.startswith("http") else ("https://" + title.lstrip("/"))
        else:
            url = REQUIRED_DEFAULT_JOIN_URL
        targets.append({"chat_id": cid, "title": title, "url": url})
        seen.add(str(cid))
        seen.add(title.lower())
    if REQUIRED_DEFAULT_CHAT_USERNAME.lower() not in seen:
        targets.insert(0, {
            "chat_id": REQUIRED_DEFAULT_CHAT_USERNAME,
            "title": REQUIRED_DEFAULT_CHAT_TITLE,
            "url": REQUIRED_DEFAULT_JOIN_URL,
        })
    return targets


def _required_join_kb() -> InlineKeyboardMarkup:
    rows = []
    targets = _effective_required_targets()
    primary = targets[0] if targets else {"url": REQUIRED_DEFAULT_JOIN_URL, "title": REQUIRED_DEFAULT_CHAT_TITLE}
    rows.append([InlineKeyboardButton("📢 Join Channel", url=str(primary.get("url") or REQUIRED_DEFAULT_JOIN_URL))])
    if len(targets) > 1:
        for t in targets[1:8]:
            rows.append([InlineKeyboardButton(f"Join {str(t.get('title') or 'Chat')}", url=str(t.get("url") or REQUIRED_DEFAULT_JOIN_URL))])
    rows.append([InlineKeyboardButton("✅ I Joined", callback_data="req:verify")])
    return InlineKeyboardMarkup(rows)


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


async def _send_join_required_message(update: Update, context: ContextTypes.DEFAULT_TYPE, missing: List[str]) -> None:
    names = ", ".join(missing[:3]) if missing else REQUIRED_DEFAULT_CHAT_TITLE
    body_html = (
        f"You must join <b>{h(names)}</b> before using this bot."
        f"\n\nTap <b>Join Channel</b>, then press <b>I Joined</b>."
    )
    msg = ui_box_html("Join Required", body_html, emoji="⚠️")
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
            sent = await update.message.reply_text(
                msg,
                parse_mode=ParseMode.HTML,
                reply_markup=_required_join_kb(),
                disable_web_page_preview=True,
            )
            try:
                context.user_data["_req_prompt_mid"] = sent.message_id
            except Exception:
                pass
            return
        except Exception:
            pass
    if update.callback_query and update.callback_query.message:
        with contextlib.suppress(Exception):
            await update.callback_query.message.edit_text(
                msg,
                parse_mode=ParseMode.HTML,
                reply_markup=_required_join_kb(),
                disable_web_page_preview=True,
            )
            return
    if update.effective_user:
        await safe_send_text(context.bot, update.effective_user.id, msg, reply_markup=_required_join_kb())


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
            await safe_send_text(context.bot, uid, f"🚫 You are banned from <b>{h(BOT_BRAND)}</b>. Contact: {h(OWNER_CONTACT)}")
        return False
    await _send_join_required_message(update, context, missing)
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
        role = get_role(uid)
        body_html = (
            f"<b>Your Role:</b> <code>{h(role)}</code>"
            f"\n\nUse <code>/help</code> for commands or <code>/commands</code> for a quick list."
        )
        msg = ui_box_html(f"Welcome to {BOT_BRAND}", body_html, emoji="👋")
        await safe_send_text(context.bot, uid, msg)
        return
    count = _warn_count_or_increment(uid)
    with contextlib.suppress(Exception):
        await q.answer("Join the required channel first.", show_alert=True)
    if count >= 5:
        set_ban(uid, True)
        audit_ban(OWNER_ID, uid, "BAN")
        with contextlib.suppress(Exception):
            if q.message:
                await q.message.edit_text(f"🚫 You are banned from {BOT_BRAND}. Contact: {OWNER_CONTACT}")
        return
    await _send_join_required_message(update, context, missing)


@require_admin
async def cmd_setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args or not str(context.args[0]).isdigit():
        await safe_reply(update, usage_box("setprefix", "<DB-ID> [text]", "Set or clear the prefix for a channel"))
        return
    cid = int(context.args[0])
    new_prefix = " ".join(context.args[1:]).strip() if len(context.args) > 1 else ""
    ch = channel_get_by_id_for_user(uid, cid)
    if not ch:
        await warn(update, "Not Found", "Channel not found or you don't have access.")
        return
    old_prefix = getattr(ch, "prefix", "") or "(empty)"
    ok2 = channel_set_prefix(cid, new_prefix)
    if ok2:
        shown = new_prefix if new_prefix else "(empty)"
        body = (
            f"Channel: {h(getattr(ch, 'title', cid))}\n"
            f"DB-ID: {h(cid)}\n"
            f"Old Prefix: {h(old_prefix)}\n"
            f"New Prefix: {h(shown)}"
        )
        await ok(update, "Prefix Updated", body)
    else:
        await err(update, "Update Failed", "Could not update the prefix.")


@require_admin
async def cmd_setexplink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args or not str(context.args[0]).isdigit():
        await safe_reply(update, usage_box("setexplink", "<DB-ID> [link]", "Set or clear the explanation link for a channel"))
        return
    cid = int(context.args[0])
    new_link = " ".join(context.args[1:]).strip() if len(context.args) > 1 else ""
    ch = channel_get_by_id_for_user(uid, cid)
    if not ch:
        await warn(update, "Not Found", "Channel not found or you don't have access.")
        return
    old_link = getattr(ch, "expl_link", "") or "(empty)"
    ok2 = channel_set_expl_link(cid, new_link)
    if ok2:
        shown = new_link if new_link else "(empty)"
        body = (
            f"Channel: {h(getattr(ch, 'title', cid))}\n"
            f"DB-ID: {h(cid)}\n"
            f"Old Link: {h(old_link)}\n"
            f"New Link: {h(shown)}"
        )
        await ok(update, "Link Updated", body)
    else:
        await err(update, "Update Failed", "Could not update the link.")


@require_owner
async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT user_id, role, first_name, username, is_banned, created_at, last_seen_at FROM users ORDER BY created_at ASC")
    rows = cur.fetchall(); conn.close()
    if not rows:
        await warn(update, "No Users", "No users found.")
        return
    data = []
    for i, r in enumerate(rows, start=1):
        item = dict(r)
        item["serial"] = i
        data.append(item)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        path = f.name
    try:
        with open(path, "rb") as rf:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=rf,
                filename="probaho_users.json",
                caption=f"All started users • Total: {len(data)}",
            )
    finally:
        with contextlib.suppress(Exception):
            os.unlink(path)


@require_admin
async def cmd_usersd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not str(context.args[0]).lstrip("-").isdigit():
        await safe_reply(update, usage_box("usersd", "<user_id>", "Show a clickable profile link for a user ID"))
        return
    target = int(context.args[0])
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT first_name, username, role, is_banned, created_at, last_seen_at FROM users WHERE user_id=?", (target,))
    row = cur.fetchone(); conn.close()
    if row:
        name = row["first_name"] or str(target)
        uname = ("@" + row["username"]) if row["username"] else "(none)"
        body = (
            f"Profile: {mention_user(target, name)}\n"
            f"User ID: <code>{h(target)}</code>\n"
            f"Username: {h(uname)}\n"
            f"Role: <code>{h(row['role'] or 'USER')}</code>\n"
            f"Banned: <code>{'Yes' if int(row['is_banned'] or 0) else 'No'}</code>\n"
            f"Created: <code>{h(row['created_at'] or '')}</code>\n"
            f"Last Seen: <code>{h(row['last_seen_at'] or '')}</code>"
        )
    else:
        body = f"Profile: {mention_user(target, str(target))}\nUser ID: <code>{h(target)}</code>"
    await ok_html(update, "User Profile Link", body, emoji="🔎")


def _all_commands_for(uid: int) -> List[Tuple[str, List[Tuple[str, str]]]]:
    role = get_role(uid)
    sections: List[Tuple[str, List[Tuple[str, str]]]] = []
    user_cmds = [
        ("/start", "Start / membership check"),
        ("/help", "Detailed command guide"),
        ("/commands", "All commands list"),
        ("/ask", "Contact support"),
        ("/solve_on", "Enable private AI solving"),
        ("/solve_off", "Disable private AI solving"),
    ]
    if can_use_vision(uid):
        user_cmds += [
            ("/scanhelp", "Image-to-quiz guide"),
            ("/vision_on", "Enable image extraction"),
            ("/vision_off", "Disable image extraction"),
        ]
    sections.append(("👤 User Commands", user_cmds))
    if role in (ROLE_ADMIN, ROLE_OWNER):
        staff_cmds = [
            ("/filter", "Add parser filter text"),
            ("/done", "Export CSV + JSON, then clear buffer"),
            ("/clear", "Clear buffer"),
            ("/addchannel", "Add target channel"),
            ("/listchannels", "List available channels"),
            ("/removechannel", "Remove a channel"),
            ("/setprefix", "Set or clear channel prefix"),
            ("/setexplink", "Set or clear explanation link"),
            ("/post", "Post normal quizzes"),
            ("/postemoji", "Post emoji quizzes"),
            ("/reply", "Reply to support ticket"),
            ("/close", "Close support ticket"),
            ("/ban", "Ban a user"),
            ("/unban", "Unban a user"),
            ("/banned", "View banned users"),
            ("/broadcast", "Broadcast message to users"),
            ("/private_send", "Send private message"),
            ("/send_private", "Alias of /private_send"),
            ("/adminpanel", "Posting stats"),
            ("/himusai_on", "Enable inbox AI-only mode"),
            ("/himusai_off", "Disable inbox AI-only mode"),
            ("/probaho_on", "Enable user AI in this group"),
            ("/probaho_off", "Disable user AI in this group"),
            ("/explain_on", "Enable explanation in quiz + export"),
            ("/explain_off", "Disable explanation in quiz + export"),
            ("/quizprefix", "Set generated quiz prefix"),
            ("/quizlink", "Set generated quiz link"),
            ("/usersd", "Open a user profile by ID"),
        ]
        sections.append(("🛠 Staff Commands", staff_cmds))
    if role == ROLE_OWNER:
        owner_cmds = [
            ("/addadmin", "Add admin"),
            ("/removeadmin", "Remove admin"),
            ("/grantall", "Grant all-channels access"),
            ("/revokeall", "Revoke all-channels access"),
            ("/grantvision", "Grant image extraction"),
            ("/revokevision", "Revoke image extraction"),
            ("/addrequired", "Add required channel/group"),
            ("/delrequired", "Remove required channel/group"),
            ("/listrequired", "List required memberships"),
            ("/ownerstats", "Owner dashboard"),
            ("/users", "Export started users JSON"),
        ]
        sections.append(("👑 Owner Commands", owner_cmds))
    return sections


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if not uid or is_banned(uid):
        return
    role = get_role(uid)
    if role not in (ROLE_ADMIN, ROLE_OWNER):
        return
    if is_private_chat(update) and solver_mode_on(uid):
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
        await ok_html(update, "Added to Buffer", f"<code>{h(added)}</code> question(s) added.\n\nTotal buffered: <code>{h(buffer_count(uid))}</code>", footer_html="Use <code>/done</code> to export")
    else:
        await warn(update, "No Questions Found", "No valid quiz blocks detected. Check formatting.")


async def handle_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if not uid or is_banned(uid):
        return
    role = get_role(uid)
    if role not in (ROLE_ADMIN, ROLE_OWNER):
        return
    if is_private_chat(update) and solver_mode_on(uid):
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
        note = "\n\n⚠️ Telegram may hide the correct answer in forwarded quizzes. CSV will store <code>answer=0</code>."
    body = f"Total buffered: <code>{buffer_count(uid)}</code>{note}"
    await ok_html(update, "Poll Saved", body)


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if uid and get_role(uid) in (ROLE_ADMIN, ROLE_OWNER) and is_private_chat(update) and solver_mode_on(uid):
        return
    # fall through to existing image extraction logic
    return await globals()["_original_handle_image"](update, context)


def gemini_solve_text(problem_text: str) -> str:
    prompt = (
        STRICT_SYSTEM_PROMPT
        + "\n\nUser Message:\n"
        + (problem_text or "").strip()
    )
    try:
        out = gemini3_solve(prompt)
        if out and str(out).strip():
            return str(out).strip()
    except Exception:
        pass
    if USE_PERPLEXITY_FALLBACK:
        try:
            alt = query_ai(prompt)
            if alt:
                return alt.strip()
        except Exception:
            pass
    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEY:
        try:
            return call_gemini_text_rest(prompt, timeout_seconds=18).strip()
        except Exception:
            pass
    raise RuntimeError("AI backend is temporarily unavailable. Please try again.")


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
    try:
        raw = gemini3_solve(prompt)
        data = _extract_json_strict(raw)
        if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
            return data
    except Exception:
        pass
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
        except Exception:
            pass
    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEY:
        try:
            raw2 = call_gemini_text_rest(prompt, timeout_seconds=18, force_json=True)
            data2 = _extract_json_strict(raw2)
            if isinstance(data2, dict):
                return data2
        except Exception:
            pass
    raise RuntimeError("AI backend is temporarily unavailable. Please try again.")


def _solve_text_with_preference(model: str, problem_text: str) -> Tuple[str, str]:
    model = (model or "G").upper()
    if model == "P":
        try:
            return perplexity_solve_text(problem_text), "Perplexity"
        except Exception:
            return gemini_solve_text(problem_text), "Gemini"
    if model == "D":
        try:
            return deepseek_solve_text(problem_text), "DeepSeek"
        except Exception:
            return gemini_solve_text(problem_text), "Gemini"
    return gemini_solve_text(problem_text), "Gemini"


def _solve_mcq_with_preference(model: str, question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:
    model = (model or "G").upper()
    if model == "P":
        try:
            return perplexity_solve_mcq_json(question, options), "Perplexity"
        except Exception:
            return gemini_solve_mcq_json(question, options), "Gemini"
    if model == "D":
        try:
            return deepseek_solve_mcq_json(question, options), "DeepSeek"
        except Exception:
            return gemini_solve_mcq_json(question, options), "Gemini"
    return gemini_solve_mcq_json(question, options), "Gemini"


async def handle_user_poll_solver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.effective_user or not update.message or not update.message.poll:
        return
    uid = update.effective_user.id
    if is_banned(uid):
        return
    role = get_role(uid)
    private = is_private_chat(update)
    if role == ROLE_USER:
        if private:
            if not solver_mode_on(uid):
                return
        else:
            if not is_group_ai_enabled(update.effective_chat.id):
                return
        if not await enforce_required_memberships(update, context):
            return
    elif role in (ROLE_ADMIN, ROLE_OWNER):
        if not private or not solver_mode_on(uid):
            return
    else:
        return

    poll = update.message.poll
    qtext = (poll.question or "").strip()
    options = [str(o.text).strip() for o in (poll.options or []) if str(o.text or '').strip()]
    official_expl = str(getattr(poll, "explanation", "") or "").strip()
    official_ans = _poll_official_answer(poll)

    spinner_msg = None
    spinner_task = None
    try:
        spinner_msg = await update.message.reply_text("🔎 Searching")
        spinner_task = asyncio.create_task(_spinner_task(context.bot, spinner_msg.chat_id, spinner_msg.message_id))
        data = await _run_blocking(_role_of(uid), gemini_solve_mcq_json, qtext, options)
        model_ans = int(data.get("answer", 0) or 0)
        conf = int(data.get("confidence", 0) or 0)
        raw_expl = str(data.get("explanation", "") or "").strip()
        model_expl = clean_latex(raw_expl)
        raw_why_not = data.get("why_not", {}) or {}
        why_not = {k: clean_latex(v) for k, v in raw_why_not.items()}
        if spinner_task:
            spinner_task.cancel()
        if spinner_msg:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(chat_id=spinner_msg.chat_id, message_id=spinner_msg.message_id)
        msg_html = _format_user_poll_solution(
            question=qtext,
            options=options,
            model_ans=model_ans,
            official_ans=official_ans,
            model_expl=f"[Gemini 3 Flash]\n{model_expl}".strip(),
            official_expl=official_expl,
            why_not=why_not if isinstance(why_not, dict) else {},
            conf=conf,
        )
        poll_payload = {
            "question": qtext,
            "options": options,
            "official_ans": official_ans,
            "official_expl": official_expl,
        }
        await send_poll_verify_buttons(update, context, poll_payload, msg_html)
    except Exception as e:
        if spinner_task:
            spinner_task.cancel()
        if spinner_msg:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(chat_id=spinner_msg.chat_id, message_id=spinner_msg.message_id)
        db_log("ERROR", "poll_solver_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Solve Failed", "AI backend is temporarily unavailable. Please try again.")


async def handle_user_text_unusual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
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


def _emoji_quiz_text(question: str, options: List[str], title: str) -> str:
    lines = [str(title or BOT_BRAND).strip(), "", str(question or "").strip(), ""]
    labels = EMOJI_BUTTONS[:len(options)]
    for i, opt in enumerate(options):
        label = labels[i] if i < len(labels) else f"{_safe_letter(i+1)})"
        lines.append(f"{label} {opt}")
    return "\n".join([x for x in lines if x is not None]).strip()


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
    prefix = str(getattr(ch, "prefix", "") or "").strip()
    title = prefix if prefix else BOT_BRAND
    sent = 0
    sent_ids = []
    for bid, payload in items:
        qtext, opts, corr_idx0, explanation = quiz_to_poll_parts(payload)
        if not opts:
            continue
        msg_text = _emoji_quiz_text(qtext, opts, title)
        quiz_id = uuid.uuid4().hex[:10]
        try:
            m = await context.bot.send_message(
                chat_id=ch.channel_chat_id,
                text=msg_text,
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
            db_log("ERROR", "postemoji_failed", {"admin_id": admin_id, "channel": getattr(ch, 'channel_chat_id', 0), "error": str(e)})
    if sent and not keep:
        buffer_remove_ids(admin_id, sent_ids)
    await ok_html(update, "Emoji Quiz Posted", f"Sent: <code>{h(sent)}</code>\nChannel: <code>{h(getattr(ch, 'title', cid))}</code>")


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
    ok_member, _missing = await user_meets_required_memberships(context, uid)
    if not ok_member:
        await q.answer("⚠️ Join the required channel first, then press I Joined.", show_alert=True)
        return
    quiz = emoji_quiz_get(quiz_id)
    if not quiz:
        await q.answer("Quiz expired or not found.", show_alert=True)
        return
    saved_choice = emoji_quiz_user_choice(quiz_id, uid)
    correct = int(quiz.get("correct_answer", 0) or 0)
    opts = quiz.get("options", []) or []
    expl = clean_latex(str(quiz.get("explanation", "") or "").strip())
    expl = re.sub(r"\s+", " ", expl).strip()
    if len(expl) > 150:
        expl = expl[:147] + "..."
    corr_label = EMOJI_BUTTONS[correct - 1] if 0 < correct <= len(EMOJI_BUTTONS) else str(correct)

    if saved_choice and int(saved_choice) != int(selected):
        saved_label = EMOJI_BUTTONS[saved_choice - 1] if 0 < saved_choice <= len(EMOJI_BUTTONS) else str(saved_choice)
        await q.answer(f"⚠️ You already answered with {saved_label}. Tap the same reaction to view your result.", show_alert=True)
        return

    if not saved_choice:
        emoji_quiz_record_answer(quiz_id, uid, selected, (selected == correct and correct > 0))
        sel_label = EMOJI_BUTTONS[selected - 1] if 0 < selected <= len(EMOJI_BUTTONS) else str(selected)
        if selected == correct and correct > 0:
            first_msg = f"🎉🎊 Congratulations!\n✅ Correct: {corr_label}\nYour reaction: {sel_label}\n\nTap the same reaction again for explanation & stats."
        else:
            first_msg = f"❌ Wrong answer\n✅ Correct: {corr_label}\nYour reaction: {sel_label}\n\nTap the same reaction again for explanation & stats."
        await q.answer(first_msg[:190], show_alert=True)
        return

    counts = emoji_quiz_counts(quiz_id)
    sel_label = EMOJI_BUTTONS[saved_choice - 1] if 0 < saved_choice <= len(EMOJI_BUTTONS) else str(saved_choice)
    stats_text = " | ".join([f"{EMOJI_BUTTONS[i-1]}={counts.get(i, 0)}" for i in range(1, len(opts) + 1)])
    if saved_choice == correct and correct > 0:
        msg = f"🎉🎊 Correct\nYour reaction: {sel_label}\n✅ Correct: {corr_label}"
    else:
        msg = f"❌ Wrong\nYour reaction: {sel_label}\n✅ Correct: {corr_label}"
    if stats_text:
        msg += f"\n{stats_text}"
    if expl:
        msg += f"\n\n{expl}"
    await q.answer(msg[:190], show_alert=True)


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
            answer, _used = await _run_blocking(_role_of(uid), _solve_text_with_preference, model, problem_text)
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
            await q.edit_message_text(ui_box_text("Solve Failed", "AI backend is temporarily unavailable. Please try again.", emoji="❌"), parse_mode=ParseMode.HTML)




