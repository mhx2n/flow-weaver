# ──────────────────────────────────────────────────────────────────────────────
# Section: 13_final_patches_03_13_a
# Original lines: 7944..8297
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===========================
# FINAL PATCHES (2026-03-13)
# ===========================

def _strip_leading_quiz_noise(q: str) -> str:
    s = str(q or '').strip()
    # Drop repeated source tags like [White Apron 🩺] at the beginning.
    while True:
        new_s = re.sub(r'^\s*\[[^\]]{1,80}\]\s*', '', s)
        if new_s == s:
            break
        s = new_s.strip()
    # Drop serials such as "124.", "১২৪।", "238)", repeated if needed.
    s = re.sub(r'^\s*(?:(?:\d+|[০-৯]+)\s*[\.)।:\-]+\s*)+', '', s).strip()
    return s


def _shuffle_quiz_payload(question: str, options: List[str], correct_option_id0: int) -> Tuple[str, List[str], int]:
    import random
    q = _strip_leading_quiz_noise(question)
    opts = [str(o).strip() for o in (options or []) if str(o).strip()]
    if len(opts) < 2:
        return q, opts, correct_option_id0
    order = list(range(len(opts)))
    random.shuffle(order)
    shuffled = [opts[i] for i in order]
    new_correct = -1
    if 0 <= int(correct_option_id0) < len(opts):
        try:
            new_correct = order.index(int(correct_option_id0))
        except Exception:
            new_correct = -1
    return q, shuffled, new_correct


def _score_reply_text(total_posted: int) -> str:
    return f"📝 Your score: ____ / {int(total_posted or 0)}"


def quiz_to_poll_parts(payload: Dict[str, Any]) -> Tuple[str, List[str], int, str]:
    q = str(payload.get("questions", "")).strip()
    q2, expl2 = split_inline_explain(q)
    if expl2 and not str(payload.get("explanation", "")).strip():
        q = q2.strip()
        payload = dict(payload)
        payload["explanation"] = expl2.strip()
    else:
        q = q2.strip()
    opts = [
        str(payload.get("option1", "")).strip(),
        str(payload.get("option2", "")).strip(),
        str(payload.get("option3", "")).strip(),
        str(payload.get("option4", "")).strip(),
        str(payload.get("option5", "")).strip(),
    ]
    opts = [o for o in opts if o]
    if len(opts) < 2:
        if len(opts) == 0:
            opts = ["Option A", "Option B"]
        else:
            opts = opts + ["Option B"]
    if len(opts) > 10:
        opts = opts[:10]
    ans = int(payload.get("answer", 0) or 0)
    correct_option_id = ans - 1 if 1 <= ans <= len(opts) else -1
    explanation = str(payload.get("explanation", "")).strip()
    q, opts, correct_option_id = _shuffle_quiz_payload(q, opts, correct_option_id)
    return q, opts, correct_option_id, explanation


@require_admin
async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await safe_reply(update, usage_box("post", "<DB-ID> [keep]", "Post buffered quizzes to a channel. Use 'keep' to keep buffer."))
        return

    cid = int(context.args[0])
    keep = (len(context.args) > 1 and context.args[1].strip().lower() == "keep")
    ch = channel_get_by_id_for_user(admin_id, cid)
    if not ch:
        await warn_html(update, "Channel Not Found", f"No access to that channel. Use <code>/listchannels</code> to view yours.")
        return

    items = buffer_list(admin_id, limit=MAX_BUFFERED_QUESTIONS)
    if not items:
        await warn(update, "Buffer Empty", "No quizzes to post. Send text or forward polls first.")
        return

    await info_html(update, "Posting to Channel", f"<code>{h(ch.title)}</code> — <code>{h(str(ch.channel_chat_id))}</code>\n\nPosting <code>{h(len(items))}</code> question(s)...")

    posted_ids: List[int] = []
    ok_count, fail_count = 0, 0
    first_post_message_id = None

    for (row_id, payload) in items:
        try:
            q, opts, correct_option_id, expl = quiz_to_poll_parts(payload)
            prefix = (ch.prefix or "").strip(" ")
            expl_link = (ch.expl_link or "").strip()
            SEP = "\n\u200b"
            q_final = f"{prefix}{SEP}{q}".strip() if prefix else q
            if len(q_final) > 300:
                q_final = q_final[:297] + "..."

            expl_final = expl.strip()
            if not explain_mode_on(admin_id):
                expl_final = ""
            if expl_link:
                expl_final = (expl_final + "\n\n" if expl_final else "") + f"🔗 {expl_link}"
            expl_final = expl_final.strip()
            if len(expl_final) > 200:
                expl_final = expl_final[:197] + "..."

            if correct_option_id >= 0:
                m = await context.bot.send_poll(
                    chat_id=ch.channel_chat_id,
                    question=q_final,
                    options=opts,
                    is_anonymous=True,
                    type=Poll.QUIZ,
                    correct_option_id=correct_option_id,
                    explanation=expl_final if expl_final else None,
                )
            else:
                m = await context.bot.send_poll(
                    chat_id=ch.channel_chat_id,
                    question=q_final,
                    options=opts,
                    is_anonymous=True,
                    type=Poll.REGULAR,
                )
                if expl_final:
                    await context.bot.send_message(chat_id=ch.channel_chat_id, text=f"📖 {expl_final}", disable_web_page_preview=True)

            if first_post_message_id is None and getattr(m, 'message_id', None):
                first_post_message_id = m.message_id
            ok_count += 1
            posted_ids.append(row_id)
            await asyncio.sleep(POST_DELAY_SECONDS)
        except RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
            fail_count += 1
        except TelegramError as e:
            fail_count += 1
            db_log("ERROR", "post_failed", {"admin_id": admin_id, "channel": ch.channel_chat_id, "error": str(e)})
        except Exception as e:
            fail_count += 1
            db_log("ERROR", "post_failed_unknown", {"admin_id": admin_id, "error": str(e)})

    if ok_count > 0:
        # FIXED: Robust score reply with fallback
        score_text = _score_reply_text(ok_count)
        score_sent = False
        if first_post_message_id:
            try:
                await context.bot.send_message(
                    chat_id=ch.channel_chat_id,
                    text=score_text,
                    reply_to_message_id=first_post_message_id,
                    allow_sending_without_reply=True,
                )
                score_sent = True
            except Exception as score_err:
                db_log("WARN", "score_reply_failed", {"admin_id": admin_id, "error": str(score_err)})
        if not score_sent:
            with contextlib.suppress(Exception):
                await context.bot.send_message(
                    chat_id=ch.channel_chat_id,
                    text=score_text,
                )

    inc_admin_post(admin_id, ok_count)
    if posted_ids and not keep:
        buffer_remove_ids(admin_id, posted_ids)
    body = f"Posted: {ok_count}\nFailed: {fail_count}\nRemaining in Buffer: {buffer_count(admin_id)}"
    await ok(update, "Posting Complete", body)


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
    first_post_message_id = None
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
            if first_post_message_id is None:
                first_post_message_id = m.message_id
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
    if sent > 0:
        # FIXED: Robust score reply with fallback
        score_text = _score_reply_text(sent)
        score_sent = False
        if first_post_message_id:
            try:
                await context.bot.send_message(
                    chat_id=ch.channel_chat_id,
                    text=score_text,
                    reply_to_message_id=first_post_message_id,
                    allow_sending_without_reply=True,
                )
                score_sent = True
            except Exception as se:
                db_log("WARN", "postemoji_score_reply_failed", {"admin_id": admin_id, "error": str(se)})
        if not score_sent:
            with contextlib.suppress(Exception):
                await context.bot.send_message(
                    chat_id=ch.channel_chat_id,
                    text=score_text,
                )
    if sent and not keep:
        buffer_remove_ids(admin_id, sent_ids)
    await ok_html(update, "Emoji Quiz Posted", f"Sent: <code>{h(sent)}</code>\nChannel: <code>{h(getattr(ch, 'title', cid))}</code>")

def build_app() -> Application:
    db_init(); extra_db_init()
    # keep original image extraction around for override wrapper
    globals().setdefault("_original_handle_image", globals().get("handle_image"))
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
    app.add_handler(_cmdh("usersd", cmd_usersd))
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

def main():
    # Render free web service port binding: start ASAP so Render sees an open port quickly.
    try:
        threading.Thread(target=_run_render_health_server, daemon=True).start()
    except Exception:
        logging.exception("Failed to start Render health server")

    app = build_app()

    try:
        # Attempt to reconfigure stdout to UTF-8 encoding for Windows compatibility
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        print(f"🤖 {BOT_BRAND} started. OWNER_ID={OWNER_ID} DB={DB_PATH}")
    except (UnicodeEncodeError, AttributeError, TypeError):
        # Fallback to ASCII-only message if encoding fails
        try:
            print("[BOT] Started. OWNER_ID={} DB={}".format(OWNER_ID, DB_PATH))
        except:
            # Final fallback - use logging instead
            logging.info(f"Bot started. OWNER_ID={OWNER_ID} DB={DB_PATH}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


