# ──────────────────────────────────────────────────────────────────────────────
# Section: 45_probaho_patch_q_cmd_post_override_05_18
# Original lines: 24264..24479
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════
# END PROBAHO PATCH-P
# ═══════════════════════════════════════════════════════════════════════

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  PROBAHO PATCH-Q — Cross-Chat Topic Reply for Channel Posting (.p)  ║
# ║  Added : 2026-05-18  |  Previous features NOT modified              ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# PROBLEM FIXED:
#   cmd_post (.p <serial>) used plain reply_to_message_id.
#   This only works when the topic anchor is in the SAME channel.
#   When anchor is in Channel A and user posts to Channel B → no cross-chat reply.
#
# FIX:
#   Override cmd_post to call _make_reply_params() instead.
#   _make_reply_params() (from PATCH-P) uses Bot API 7.0 ReplyParameters
#   with chat_id when anchor_chat != target_chat → true cross-chat reply header.
#
# RESULT:
#   Topic in Channel A → post to Channel B with .p <serial_B>
#   → Each quiz in Channel B shows a reply header linking to Channel A's topic.
#   → Tapping the header navigates to Channel A at that exact message.
#   → The topic is NEVER copied or forwarded. Nothing moves. Nothing duplicates.
#
# SAME-CHAT behaviour (unchanged):
#   Topic and quizzes in the same channel → reply_parameters points to same chat.
#   Renders as a normal in-channel reply (identical to before).

@require_admin
async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
    """
    .p <DB-ID> [keep]
    Post buffered quizzes to a channel.
    PATCH-Q: Uses ReplyParameters for both same-chat and cross-chat topic reply.
    """
    admin_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await safe_reply(update, usage_box(
            "post", "<DB-ID> [keep]",
            "Post buffered quizzes to a channel. Use 'keep' to keep buffer."
        ))
        return

    cid = int(context.args[0])
    keep = (len(context.args) > 1 and context.args[1].strip().lower() == "keep")
    ch = channel_get_by_id_for_user(admin_id, cid)
    if not ch:
        await warn_html(update, "Channel Not Found",
            "No access to that channel. Use <code>/listchannels</code> to view yours.")
        return

    items = buffer_list(admin_id, limit=MAX_BUFFERED_QUESTIONS)
    if not items:
        await warn(update, "Buffer Empty",
            "No quizzes to post. Send text or forward polls first.")
        return

    await info_html(update, "Posting to Channel",
        f"<code>{h(ch.title)}</code> — <code>{h(str(ch.channel_chat_id))}</code>\n\n"
        f"Posting <code>{h(len(items))}</code> question(s)...")

    target_chat_id: int = ch.channel_chat_id

    # ── Resolve topic anchor and build reply kwargs (PATCH-Q) ──────────
    _anchor_chat, _anchor_msg = _get_topic_anchor(admin_id)
    _reply_kw: Dict[str, Any] = {}

    if _anchor_msg:
        if _anchor_chat == target_chat_id:
            # Same-channel: classic reply
            _reply_kw = _make_reply_params(_anchor_msg)
            logger.debug("[PATCH-Q] Same-channel reply to msg=%s in chat=%s",
                         _anchor_msg, target_chat_id)
        else:
            # Cross-channel: ReplyParameters with source chat_id
            _reply_kw = _make_reply_params(_anchor_msg, chat_id=_anchor_chat)
            logger.info(
                "[PATCH-Q] Cross-channel reply: quizzes in channel=%s link back "
                "to topic msg=%s in channel=%s",
                target_chat_id, _anchor_msg, _anchor_chat,
            )

    posted_ids: List[int] = []
    ok_count = 0
    fail_count = 0
    first_post_message_id: Optional[int] = None

    for (row_id, payload) in items:
        try:
            q, opts, correct_option_id, expl = quiz_to_poll_parts(payload)
            if len(opts) < 2:
                continue

            prefix    = (ch.prefix    or "").strip()
            expl_tail = (ch.expl_link or "").strip()
            SEP = "\n\u200b"
            q_final = f"{prefix}{SEP}{q}".strip() if prefix else q
            if len(q_final) > 300:
                q_final = q_final[:297] + "..."

            expl_final = expl.strip() if explain_mode_on(admin_id) else ""
            if expl_tail:
                expl_final = (expl_final + "\n\n" if expl_final else "") + expl_tail
            expl_final = expl_final.strip()
            if expl_final and len(expl_final) > 200:
                expl_final = expl_final[:197] + "..."

            _poll_kw: Dict[str, Any] = dict(
                chat_id=target_chat_id,
                question=q_final,
                options=opts,
                is_anonymous=True,
            )

            # Merge cross-chat-aware reply kwargs
            _poll_kw.update(_reply_kw)

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
                    await context.bot.send_message(
                        chat_id=target_chat_id,
                        text=expl_final,
                        disable_web_page_preview=True,
                    )

            if first_post_message_id is None:
                first_post_message_id = getattr(m, 'message_id', None)
            ok_count += 1
            posted_ids.append(row_id)
            await asyncio.sleep(POST_DELAY_SECONDS)

        except RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
            fail_count += 1
        except TelegramError as e:
            fail_count += 1
            db_log("ERROR", "patch_q_post_failed",
                   {"admin_id": admin_id, "channel": target_chat_id, "error": str(e)})
        except Exception as e:
            fail_count += 1
            db_log("ERROR", "patch_q_post_ex",
                   {"admin_id": admin_id, "error": str(e)})

    if ok_count > 0 and _score_reply_enabled(admin_id):
        score_text = _score_reply_text(ok_count)
        # Score always replies within the target channel:
        # same-channel anchor → reply to anchor, cross-channel → reply to first quiz
        if _anchor_msg and _anchor_chat == target_chat_id:
            _score_reply_to = _anchor_msg
        else:
            _score_reply_to = first_post_message_id

        try:
            _score_kw: Dict[str, Any] = dict(
                chat_id=target_chat_id,
                text=score_text,
                allow_sending_without_reply=True,
            )
            if _score_reply_to:
                _score_kw['reply_to_message_id'] = _score_reply_to
            await context.bot.send_message(**_score_kw)
        except Exception as _se:
            with contextlib.suppress(Exception):
                await context.bot.send_message(chat_id=target_chat_id, text=score_text)

    inc_admin_post(admin_id, ok_count)
    if posted_ids and not keep:
        buffer_remove_ids(admin_id, posted_ids)

    body = (
        f"Posted: {ok_count}\n"
        f"Failed: {fail_count}\n"
        f"Remaining in Buffer: {buffer_count(admin_id)}"
    )
    await ok(update, "Posting Complete", body)


# ── Register PATCH-Q override ──────────────────────────────────────────

_prev_build_app_patch_q = build_app

def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_patch_q()

    private_filter = filters.ChatType.PRIVATE

    # Remove any previously registered "post" / "p" handlers and re-register
    # with the PATCH-Q cmd_post that uses ReplyParameters for cross-channel.
    for alias in ("post", "p"):
        for gid, handler_list in list(app.handlers.items()):
            to_del = [
                hh for hh in list(handler_list)
                if isinstance(hh, (CommandHandler, MessageHandler))
                and hasattr(hh, 'commands')
                and alias in (hh.commands or set())
            ]
            for hh in to_del:
                with contextlib.suppress(Exception):
                    app.remove_handler(hh, group=gid)
        with contextlib.suppress(Exception):
            _register_dual_command(app, alias, cmd_post, private_filter)

    logger.info("[PATCH-Q] Overrode .post/.p with cross-channel ReplyParameters support.")
    return app


logger.info("[PATCH-Q 2026-05-18] cmd_post overridden: channel cross-chat topic reply via ReplyParameters.")
