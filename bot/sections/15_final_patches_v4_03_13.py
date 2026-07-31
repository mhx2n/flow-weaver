# ──────────────────────────────────────────────────────────────────────────────
# Section: 15_final_patches_v4_03_13
# Original lines: 8556..8717
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===========================
# FINAL PATCHES V4 (2026-03-13)
# ===========================

def _final_user_command_set() -> set[str]:
    return {"/start", "/help", "/commands", "/ask", "/solve_on", "/solve_off"}


def _all_commands_for(user_id: int):
    role = get_role(user_id)
    sections = []
    user_cmds = [
        ("/start", "Welcome / membership check"),
        ("/help", "Show detailed command guide"),
        ("/commands", "Show all available commands"),
        ("/ask", "Contact support (text or reply to file/photo)"),
        ("/solve_on", "Enable user AI solving"),
        ("/solve_off", "Disable user AI solving"),
    ]
    sections.append(("👤 User Commands", user_cmds))
    if role in (ROLE_ADMIN, ROLE_OWNER):
        admin_cmds = [
            ("/himusai_on", "Enable admin/owner inbox AI mode"),
            ("/himusai_off", "Disable admin/owner inbox AI mode"),
            ("/probaho_on", "Enable AI in current group (group admin)"),
            ("/probaho_off", "Disable AI in current group (group admin)"),
            ("/filter", "Add parsing filter phrase"),
            ("/clear", "Clear your buffer"),
            ("/done", "Export your buffered quizzes"),
            ("/buffercount", "Show total buffered quizzes"),
            ("/addchannel", "Add a channel/group for posting"),
            ("/listchannels", "List your channels/groups"),
            ("/removechannel", "Remove a channel/group"),
            ("/setprefix", "Set or clear channel prefix"),
            ("/setexplink", "Set or clear explanation link"),
            ("/post", "Post buffered quizzes to a channel"),
            ("/postemoji", "Post buffered emoji quizzes to a channel"),
            ("/emojipost", "Alias of /postemoji"),
            ("/imgreact", "Post image-based reaction quiz by replying to a photo"),
            ("/broadcast", "Broadcast a message"),
            ("/adminpanel", "View posting/admin stats"),
            ("/reply", "Reply to a support ticket"),
            ("/close", "Close a support ticket"),
            ("/ban", "Ban a user"),
            ("/unban", "Unban a user"),
            ("/banned", "View banned users"),
            ("/private_send", "Send a private message to a user"),
            ("/usersd", "Show user details / open profile if public"),
            ("/vision_on", "Enable image extraction mode"),
            ("/vision_off", "Disable image extraction mode"),
            ("/scanhelp", "Show image extraction help"),
            ("/explain_on", "Enable explanation in quiz + export"),
            ("/explain_off", "Disable explanation in quiz + export"),
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
            ("/quizprefix", "Set generated quiz prefix"),
            ("/quizlink", "Set generated quiz link"),
        ]
        sections.append(("👑 Owner Commands", owner_cmds))
    return sections


@require_admin
async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
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
    for idx, r in enumerate(rows, start=1):
        opts_map = {"A": r.get("option1", ""), "B": r.get("option2", ""), "C": r.get("option3", ""), "D": r.get("option4", "")}
        if str(r.get("option5", "")).strip():
            opts_map["E"] = r.get("option5", "")
        quiz_json.append({
            "serial": idx,
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


@require_owner
async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not str(context.args[0]).lstrip('-').isdigit():
        await safe_reply(update, usage_box("addadmin", "<user_id>", "Promote a user to admin"))
        return
    target = int(context.args[0])
    if _is_owner_id(target):
        await warn(update, "Not Needed", "Owner already has full access.")
        return
    conn = db_connect(); cur = conn.cursor()
    cur.execute("UPDATE users SET role=? WHERE user_id=?", (ROLE_ADMIN, target))
    if cur.rowcount == 0:
        cur.execute(
            "INSERT OR REPLACE INTO users(user_id, role, first_name, username, is_banned, created_at, can_view_all, can_use_vision, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (target, ROLE_ADMIN, "", None, 0, now_iso(), 0, 0, now_iso()),
        )
    conn.commit(); conn.close()
    await ok(update, "Admin Added", f"User <code>{h(target)}</code> promoted to ADMIN.")


_prev_build_app_v4 = build_app

def build_app() -> Application:
    app = _prev_build_app_v4()
    return app



