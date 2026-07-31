# ──────────────────────────────────────────────────────────────────────────────
# Section: 16_final_overrides_v5
# Original lines: 8718..8979
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL OVERRIDES v5 =====

def _normalize_emoji_quiz_parts(payload: Dict[str, Any]) -> Tuple[str, List[str], int, str]:
    q, opts, correct_option_id, explanation = quiz_to_poll_parts(payload)
    opts = [str(o).strip() for o in (opts or []) if str(o).strip()]
    if len(opts) > len(EMOJI_BUTTONS):
        opts = opts[:len(EMOJI_BUTTONS)]
        if correct_option_id >= len(opts):
            correct_option_id = -1
    if len(opts) < 2:
        return q, [], -1, explanation
    return q, opts, correct_option_id, explanation


@require_admin
async def cmd_setexplink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args or not str(context.args[0]).isdigit():
        await safe_reply(update, usage_box("setexplink", "<DB-ID> [text]", "Set or clear the explanation tail text for a channel"))
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
            f"Old Text: {h(old_link)}\n"
            f"New Text: {h(shown)}"
        )
        await ok(update, "Explanation Text Updated", body)
    else:
        await err(update, "Update Failed", "Could not update the explanation text.")


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

    # Use topic anchor if set for this channel
    _anchor_chat, _anchor_msg = _get_topic_anchor(admin_id)
    # FIX: anchor applies globally regardless of which channel we are posting to
    _reply_anchor: Optional[int] = _anchor_msg if _anchor_msg else None

    for (row_id, payload) in items:
        try:
            q, opts, correct_option_id, expl = quiz_to_poll_parts(payload)
            if len(opts) < 2:
                continue
            prefix = (ch.prefix or "").strip(" ")
            expl_tail = (ch.expl_link or "").strip()
            SEP = "\n\u200b"
            q_final = f"{prefix}{SEP}{q}".strip() if prefix else q
            if len(q_final) > 300:
                q_final = q_final[:297] + "..."

            expl_final = expl.strip()
            if not explain_mode_on(admin_id):
                expl_final = ""
            if expl_tail:
                expl_final = (expl_final + "\n\n" if expl_final else "") + expl_tail
            expl_final = expl_final.strip()
            if len(expl_final) > 200:
                expl_final = expl_final[:197] + "..."

            _poll_kw: Dict[str, Any] = dict(
                chat_id=ch.channel_chat_id,
                question=q_final,
                options=opts,
                is_anonymous=True,
            )
            if _reply_anchor is not None:
                _poll_kw['reply_to_message_id'] = _reply_anchor
                _poll_kw['allow_sending_without_reply'] = True

            if correct_option_id >= 0:
                _poll_kw['type'] = Poll.QUIZ
                _poll_kw['correct_option_id'] = correct_option_id
                if expl_final:
                    _poll_kw['explanation'] = expl_final
                m = await context.bot.send_poll(**_poll_kw)
            else:
                _poll_kw['type'] = Poll.REGULAR
                m = await context.bot.send_poll(**_poll_kw)
                if expl_final:
                    await context.bot.send_message(chat_id=ch.channel_chat_id, text=expl_final, disable_web_page_preview=True)

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
        # Score reply — prefer topic anchor, fallback to first posted message
        score_text = _score_reply_text(ok_count)
        score_sent = False
        _score_reply_to = _reply_anchor if _reply_anchor else first_post_message_id
        if _score_reply_to:
            try:
                await context.bot.send_message(
                    chat_id=ch.channel_chat_id,
                    text=score_text,
                    reply_to_message_id=_score_reply_to,
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
    sent_ids: List[int] = []
    first_post_message_id = None
    fail_count = 0
    for bid, payload in items:
        qtext, opts, corr_idx0, explanation = _normalize_emoji_quiz_parts(payload)
        if len(opts) < 2:
            fail_count += 1
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
            await asyncio.sleep(0.30)
        except RetryAfter as e:
            await asyncio.sleep(float(getattr(e, 'retry_after', 1.0)) + 0.5)
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
            except Exception as e2:
                fail_count += 1
                db_log("ERROR", "postemoji_failed_retry", {"admin_id": admin_id, "channel": getattr(ch, 'channel_chat_id', 0), "error": str(e2), "buffer_id": bid})
        except Exception as e:
            fail_count += 1
            db_log("ERROR", "postemoji_failed", {"admin_id": admin_id, "channel": getattr(ch, 'channel_chat_id', 0), "error": str(e), "buffer_id": bid})

    if sent > 0 and first_post_message_id:
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                chat_id=ch.channel_chat_id,
                text=_score_reply_text(sent),
                reply_to_message_id=first_post_message_id,
                allow_sending_without_reply=True,
            )
    if sent_ids and not keep:
        buffer_remove_ids(admin_id, sent_ids)
    await ok_html(update, "Emoji Quiz Posted", f"Sent: <code>{h(sent)}</code>\nFailed: <code>{h(fail_count)}</code>\nChannel: <code>{h(getattr(ch, 'title', cid))}</code>")

# ===== END FINAL OVERRIDES v5 =====



