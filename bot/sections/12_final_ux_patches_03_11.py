# ──────────────────────────────────────────────────────────────────────────────
# Section: 12_final_ux_patches_03_11
# Original lines: 7804..7943
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===========================
# FINAL UX PATCHES (2026-03-11)
# ===========================

def _profile_link_keyboard(user_id: int, username: Optional[str] = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("👤 Open Profile", url=f"tg://user?id={int(user_id)}")]]
    un = str(username or "").lstrip("@").strip()
    if un:
        rows.append([InlineKeyboardButton(f"🌐 @{un}", url=f"https://t.me/{un}")])
    return InlineKeyboardMarkup(rows)


@require_admin
async def cmd_usersd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not str(context.args[0]).lstrip("-").isdigit():
        await safe_reply(update, usage_box("usersd", "<user_id>", "Show a clickable profile button for a user ID"))
        return
    target = int(context.args[0])
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT first_name, username, role, is_banned, created_at, last_seen_at FROM users WHERE user_id=?", (target,))
    row = cur.fetchone(); conn.close()
    if row:
        name = row["first_name"] or str(target)
        username = row["username"] or ""
        uname = ("@" + username) if username else "(none)"
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
    else:
        body = (
            f"Profile: {mention_user(target, str(target))}\n"
            f"User ID: <code>{h(target)}</code>\n"
            f"Stored info: <code>Not found in local users table</code>"
        )
        kb = _profile_link_keyboard(target, None)
    await update.message.reply_text(
        ui_box_html("User Profile Link", body, emoji="🔎"),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
        disable_web_page_preview=True,
    )


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
        lines.append("\n<b>Explanation (Solved):</b>")
        lines.append(h(model_expl))
    if official_expl:
        lines.append("\n<b>Explanation (From Quiz):</b>")
        lines.append(h(official_expl))
    if why_not:
        wn = []
        for k in ["A", "B", "C", "D", "E"]:
            v = (why_not or {}).get(k)
            if v:
                wn.append(f"• <b>{h(k)}</b>: {h(v)}")
        if wn:
            lines.append("\n<b>Why other options are wrong:</b>\n" + "\n".join(wn))
    return "\n".join(lines).strip()


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
            # Bot API callback answers only support text/alert/url/cache; no native quiz-confetti trigger.
            toast = "🎉🎊 Congratulations! Tap the same reaction again for explanation & stats."
            await q.answer(toast[:190], show_alert=False)
        else:
            first_msg = f"❌ Wrong answer\n✅ Correct: {corr_label}\nYour reaction: {sel_label}\n\nTap the same reaction again for explanation & stats."
            await q.answer(first_msg[:190], show_alert=True)
        return

    counts = emoji_quiz_counts(quiz_id)
    sel_label = EMOJI_BUTTONS[saved_choice - 1] if 0 < saved_choice <= len(EMOJI_BUTTONS) else str(saved_choice)
    stats_text = " | ".join([f"{EMOJI_BUTTONS[i-1]}={counts.get(i, 0)}" for i in range(1, len(opts) + 1)])
    if saved_choice == correct and correct > 0:
        msg = f"🎉🎊 Congratulations!\nYour reaction: {sel_label}"
    else:
        msg = f"❌ Wrong\nYour reaction: {sel_label}\n✅ Correct: {corr_label}"
    if stats_text:
        msg += f"\n{stats_text}"
    if expl:
        msg += f"\n\n{expl}"
    await q.answer(msg[:190], show_alert=True)

