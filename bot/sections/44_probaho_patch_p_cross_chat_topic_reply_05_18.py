# ──────────────────────────────────────────────────────────────────────────────
# Section: 44_probaho_patch_p_cross_chat_topic_reply_05_18
# Original lines: 23658..24263
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════
# END PROBAHO PATCH-O
# ═══════════════════════════════════════════════════════════════════════


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  PROBAHO PATCH-P — True Cross-Chat Topic Reply (ReplyParameters)    ║
# ║  Added : 2026-05-18  |  Previous features NOT modified              ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# HOW IT WORKS:
#  • .topic <text> c<serial>  /  .topic <text> g<serial>
#    → Sends topic header to that channel/group, saves anchor (chat_id + msg_id).
#    → The topic message STAYS in its original chat — NOTHING is ever copied.
#
#  SAME-CHAT (unchanged):
#    Posting to the SAME chat as the anchor → quizzes reply to the original
#    topic message via reply_parameters (same as before).
#
#  CROSS-CHAT (NEW — Telegram Bot API 7.0 / PTB v21 ReplyParameters):
#    Posting to a DIFFERENT channel/group while anchor is active →
#    each quiz is sent with:
#      ReplyParameters(message_id=anchor_msg, chat_id=anchor_chat,
#                      allow_sending_without_reply=True)
#    Telegram renders a reply header in the quiz pointing to the ORIGINAL
#    topic message in the ORIGINAL chat. Tapping the header navigates
#    the reader directly there — no copy, no forward, original untouched.
#
#  FALLBACK (PTB < v21):
#    ReplyParameters unavailable → same-chat reply still works via
#    reply_to_message_id. Cross-chat posts without reply header (silent).
#
# DB CHANGES:
#  • users.topic_anchor_text  TEXT   — stores topic text (for .mytopics display)
#  • users.topic_anchor_photo TEXT   — stores photo file_id (for .mytopics display)
#  • saved_topic_anchors.topic_text  TEXT
#  • saved_topic_anchors.topic_photo TEXT

# ── 1. Import ReplyParameters (Bot API 7.0 / PTB v21+) ────────────────

_ReplyParameters = None
try:
    from telegram import ReplyParameters as _ReplyParameters
    logger.info("[PATCH-P] ReplyParameters imported — cross-chat reply enabled.")
except ImportError:
    logger.warning("[PATCH-P] ReplyParameters not available (PTB < v21). "
                   "Cross-chat reply will be silent (no reply header). Same-chat reply still works.")

def _make_reply_params(message_id: int, chat_id: Optional[int] = None):
    """
    Build reply kwargs for send_poll / send_message.
    Returns a dict ready to be unpacked into the send call.
    Uses ReplyParameters if available (supports cross-chat), else falls back to
    reply_to_message_id (same-chat only).
    """
    if _ReplyParameters is not None:
        kw: Dict[str, Any] = {"reply_parameters": _ReplyParameters(
            message_id=message_id,
            allow_sending_without_reply=True,
        )}
        # chat_id in ReplyParameters enables cross-chat reply
        if chat_id is not None:
            kw["reply_parameters"] = _ReplyParameters(
                message_id=message_id,
                chat_id=chat_id,
                allow_sending_without_reply=True,
            )
        return kw
    else:
        # Fallback: old API — only works if message is in the SAME chat
        return {
            "reply_to_message_id": message_id,
            "allow_sending_without_reply": True,
        }

# ── 2. DB migrations ───────────────────────────────────────────────────

def _patch_p_db_init() -> None:
    _new_cols = [
        ("users", "topic_anchor_text",
         "ALTER TABLE users ADD COLUMN topic_anchor_text TEXT"),
        ("users", "topic_anchor_photo",
         "ALTER TABLE users ADD COLUMN topic_anchor_photo TEXT"),
        ("saved_topic_anchors", "topic_text",
         "ALTER TABLE saved_topic_anchors ADD COLUMN topic_text TEXT"),
        ("saved_topic_anchors", "topic_photo",
         "ALTER TABLE saved_topic_anchors ADD COLUMN topic_photo TEXT"),
    ]
    for table, col, sql in _new_cols:
        try:
            conn = db_connect()
            if not _table_has_column(conn, table, col):
                conn.execute(sql)
                conn.commit()
            conn.close()
        except Exception as _pe:
            logger.warning("[PATCH-P] Migration warning (%s.%s): %s", table, col, _pe)

with contextlib.suppress(Exception):
    _patch_p_db_init()

# ── 3. Extended anchor helpers ─────────────────────────────────────────

def _set_topic_anchor(  # noqa: F811
    admin_id: int,
    chat_id: int,
    msg_id: int,
    topic_text: str = "",
    topic_photo: str = "",
) -> None:
    """Save active topic anchor. Stores text/photo for .mytopics display."""
    try:
        conn = db_connect()
        conn.execute(
            "UPDATE users SET topic_anchor_chat=?, topic_anchor_msg=?, "
            "topic_anchor_text=?, topic_anchor_photo=? WHERE user_id=?",
            (chat_id, msg_id,
             (topic_text or "").strip(),
             (topic_photo or "").strip(),
             admin_id),
        )
        conn.commit()
        conn.close()
    except Exception as _e:
        logger.warning("[PATCH-P] _set_topic_anchor error: %s", _e)


def _get_topic_anchor(admin_id: int) -> Tuple[Optional[int], Optional[int]]:  # noqa: F811
    """Return (anchor_chat_id, anchor_msg_id). Unchanged interface."""
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT topic_anchor_chat, topic_anchor_msg FROM users WHERE user_id=?",
            (admin_id,),
        )
        r = cur.fetchone()
        conn.close()
        if not r:
            return None, None
        return r["topic_anchor_chat"], r["topic_anchor_msg"]
    except Exception:
        return None, None


def _clear_topic_anchor(admin_id: int) -> None:  # noqa: F811
    """Clear the active topic anchor."""
    try:
        conn = db_connect()
        conn.execute(
            "UPDATE users SET topic_anchor_chat=NULL, topic_anchor_msg=NULL, "
            "topic_anchor_text=NULL, topic_anchor_photo=NULL WHERE user_id=?",
            (admin_id,),
        )
        conn.commit()
        conn.close()
    except Exception as _e:
        logger.warning("[PATCH-P] _clear_topic_anchor error: %s", _e)


# ── 4. Extended _sta_save with content storage ────────────────────────

def _sta_save(  # noqa: F811
    admin_id: int,
    name: str,
    chat_id: int,
    msg_id: int,
    topic_text: str = "",
    topic_photo: str = "",
) -> int:
    """Save a named topic anchor with optional content. Returns new row id."""
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO saved_topic_anchors "
            "(admin_id, name, chat_id, msg_id, topic_text, topic_photo, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (admin_id, (name or "Topic")[:60], chat_id, msg_id,
             (topic_text or "").strip(), (topic_photo or "").strip(),
             dt.datetime.utcnow().isoformat()),
        )
        conn.commit()
        rid = cur.lastrowid or 0
        conn.close()
        return rid
    except Exception as _e:
        logger.warning("[PATCH-P] _sta_save error: %s", _e)
        return 0


# ── 5. _post_buffer_to_chat: true cross-chat reply via ReplyParameters ─

async def _post_buffer_to_chat(  # noqa: F811 — PATCH-P final override
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
    chat_id: int,
    items: List[Tuple[int, Dict[str, Any]]],
    thread_id: Optional[int] = None,
    group_prefix: str = "",
    group_expl_link: str = "",
) -> Tuple[int, int, Optional[int]]:
    """
    Post buffered quizzes to any chat.
    Returns (ok_count, fail_count, first_post_msg_id).

    Topic anchor / cross-chat reply logic (PATCH-P):

      anchor_chat == chat_id (same chat):
        → reply_parameters points to anchor_msg in the same chat.
          Renders as a normal in-chat reply.

      anchor_chat != chat_id (cross-chat):
        → reply_parameters includes BOTH message_id AND chat_id of the anchor.
          Telegram renders a reply header in each quiz linking back to the
          ORIGINAL topic message in the ORIGINAL channel/group.
          Tapping the header opens that original chat at that message.
          The topic is NEVER copied or forwarded — it stays where it was.

      No anchor set:
        → posts without any reply_to (unchanged behaviour).
    """
    anchor_chat, anchor_msg = _get_topic_anchor(admin_id)

    # Build reply kwargs once — reused for every quiz in this batch
    reply_kwargs: Dict[str, Any] = {}
    if anchor_msg:
        if anchor_chat == chat_id:
            # Same-chat reply (ReplyParameters without explicit chat_id)
            reply_kwargs = _make_reply_params(anchor_msg)
            logger.debug("[PATCH-P] Same-chat reply to msg=%s in chat=%s", anchor_msg, chat_id)
        else:
            # Cross-chat reply (ReplyParameters with chat_id = source channel)
            reply_kwargs = _make_reply_params(anchor_msg, chat_id=anchor_chat)
            logger.info(
                "[PATCH-P] Cross-chat reply: quizzes in chat=%s will link back to "
                "topic msg=%s in chat=%s",
                chat_id, anchor_msg, anchor_chat,
            )

    prefix = (group_prefix or "").strip()
    expl_tail = (group_expl_link or "").strip()
    SEP = "\n\u200b"

    ok_count = 0
    fail_count = 0
    first_post_msg_id: Optional[int] = None

    for (row_id, payload) in items:
        try:
            q, opts, correct_option_id, expl = quiz_to_poll_parts(payload)

            q_final = f"{prefix}{SEP}{q}".strip() if prefix else q.strip()
            if len(q_final) > 300:
                q_final = q_final[:297] + "..."

            expl_final = expl.strip() if explain_mode_on(admin_id) else ""
            if expl_tail:
                expl_final = (expl_final + "\n\n" if expl_final else "") + expl_tail
            expl_final = expl_final.strip()
            if expl_final and len(expl_final) > 200:
                expl_final = expl_final[:197] + "..."

            send_kwargs: Dict[str, Any] = dict(
                chat_id=chat_id,
                question=q_final,
                options=opts,
                is_anonymous=True,
                type=Poll.QUIZ if correct_option_id >= 0 else Poll.REGULAR,
            )
            if correct_option_id >= 0:
                send_kwargs['correct_option_id'] = correct_option_id
            if expl_final:
                send_kwargs['explanation'] = expl_final
            if thread_id is not None:
                send_kwargs['message_thread_id'] = thread_id

            # Merge reply kwargs (ReplyParameters or reply_to_message_id)
            send_kwargs.update(reply_kwargs)

            m = await context.bot.send_poll(**send_kwargs)
            if first_post_msg_id is None:
                first_post_msg_id = getattr(m, 'message_id', None)
            ok_count += 1
            await asyncio.sleep(POST_DELAY_SECONDS)

        except RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
            fail_count += 1
        except TelegramError as e:
            fail_count += 1
            db_log("ERROR", "patch_p_post_failed",
                   {"admin_id": admin_id, "chat_id": chat_id, "error": str(e)})
        except Exception as e:
            fail_count += 1
            db_log("ERROR", "patch_p_post_ex",
                   {"admin_id": admin_id, "error": str(e)})

    return ok_count, fail_count, first_post_msg_id


# ── 6. _send_score_msg: cross-chat anchor aware ────────────────────────

async def _send_score_msg(  # noqa: F811
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
    chat_id: int,
    ok_count: int,
    first_post_msg_id: Optional[int],
    thread_id: Optional[int] = None,
) -> None:
    """Send score reply after posting. For cross-chat anchor, replies to first quiz."""
    if not _score_reply_enabled(admin_id):
        return
    score_text = _score_reply_text(ok_count)

    anchor_chat, anchor_msg = _get_topic_anchor(admin_id)

    # Score always replies within the same target chat:
    # • same-chat anchor → reply to anchor msg
    # • cross-chat anchor → reply to first quiz posted (score stays in target chat)
    # • no anchor → reply to first quiz
    if anchor_msg and anchor_chat == chat_id:
        reply_to = anchor_msg
    else:
        reply_to = first_post_msg_id

    try:
        kwargs: Dict[str, Any] = dict(
            chat_id=chat_id,
            text=score_text,
            allow_sending_without_reply=True,
        )
        if reply_to:
            kwargs['reply_to_message_id'] = reply_to
        if thread_id is not None:
            kwargs['message_thread_id'] = thread_id
        await context.bot.send_message(**kwargs)
    except Exception:
        pass


# ── 7. Override _cmd_topic_m to save content alongside anchor ──────────

@require_admin
async def _cmd_topic_m(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
    """
    .topic <text> c<serial> [pin]            — channel
    .topic <text> g<serial> [pin]            — group (general)
    .topic <text> g<serial> <topic_id> [pin] — group specific topic thread
    (Reply to any message, then .topic c/g<serial> [pin])

    PATCH-P: anchor stored with text/photo so .mytopics can show previews,
    and .usetopic restores content. The topic itself is NEVER copied.
    """
    admin_id = update.effective_user.id
    msg = update.message
    if not msg:
        return

    full_text = msg.text or msg.caption or ""
    reply_msg = msg.reply_to_message

    topic_text, target_type, serial, do_pin, sub_topic_id = _parse_topic_cmd(full_text)

    if not target_type or serial is None:
        await warn_html(update, "Usage: .topic",
            "<code>.topic &lt;text&gt; c&lt;serial&gt; [pin]</code> — channel\n"
            "<code>.topic &lt;text&gt; g&lt;serial&gt; [pin]</code> — group\n"
            "<code>.topic &lt;text&gt; g&lt;serial&gt; &lt;topic_id&gt; [pin]</code> — group topic\n\n"
            "Or reply to any message, then:\n"
            "<code>.topic c&lt;serial&gt; [pin]</code>\n"
            "<code>.topic g&lt;serial&gt; [&lt;topic_id&gt;] [pin]</code>\n\n"
            "After setting, quizzes posted to ANY channel/group will show a reply\n"
            "header linking back to this topic — tapping it opens this chat.\n"
            "Use <code>.cleartopic</code> to remove the anchor.")
        return

    # Resolve target
    target_chat_id: Optional[int] = None
    target_title = ""
    send_thread_id: Optional[int] = None

    if target_type == 'c':
        ch = channel_get_by_id_for_user(admin_id, serial)
        if not ch:
            await warn_html(update, "Channel Not Found",
                f"Channel #{serial} not found. Use <code>/listchannels</code>.")
            return
        target_chat_id = ch.channel_chat_id
        target_title = ch.title or str(ch.channel_chat_id)
    else:
        grp = _sg_get(serial, admin_id)
        if not grp:
            await warn_html(update, "Group Not Found",
                f"Group #{serial} not found. Use <code>.listgroups</code>.")
            return
        target_chat_id = grp.group_chat_id
        target_title = grp.title or str(grp.group_chat_id)
        if sub_topic_id is not None:
            saved_topic = _gt_get(sub_topic_id)
            if not saved_topic or saved_topic.group_id != grp.id:
                await warn_html(update, "Topic Not Found",
                    f"Topic #{sub_topic_id} not found under group #{serial}.\n"
                    f"Use <code>.listtopics {serial}</code> to see available topics.")
                return
            send_thread_id = saved_topic.thread_id
            target_title = f"{grp.title} › {saved_topic.topic_name}"

    # Track content for storage
    _save_text: str = ""
    _save_photo: str = ""

    sent = None
    try:
        if reply_msg:
            if reply_msg.photo:
                caption = topic_text if topic_text else (reply_msg.caption or None)
                kw: Dict[str, Any] = dict(chat_id=target_chat_id,
                                          photo=reply_msg.photo[-1].file_id, caption=caption,
                                          has_spoiler=True)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_photo(**kw)
                _save_photo = reply_msg.photo[-1].file_id
                _save_text = caption or ""

            elif reply_msg.document:
                caption = topic_text if topic_text else (reply_msg.caption or None)
                kw = dict(chat_id=target_chat_id,
                          document=reply_msg.document.file_id, caption=caption)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_document(**kw)
                _save_text = caption or topic_text or ""

            elif reply_msg.video:
                caption = topic_text if topic_text else (reply_msg.caption or None)
                kw = dict(chat_id=target_chat_id,
                          video=reply_msg.video.file_id, caption=caption,
                          has_spoiler=True)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_video(**kw)
                _save_text = caption or topic_text or ""

            elif reply_msg.audio:
                caption = topic_text if topic_text else (reply_msg.caption or None)
                kw = dict(chat_id=target_chat_id,
                          audio=reply_msg.audio.file_id, caption=caption)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_audio(**kw)
                _save_text = caption or topic_text or ""

            elif reply_msg.voice:
                caption = topic_text if topic_text else (reply_msg.caption or None)
                kw = dict(chat_id=target_chat_id,
                          voice=reply_msg.voice.file_id, caption=caption)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_voice(**kw)
                _save_text = caption or topic_text or ""

            elif reply_msg.sticker:
                kw = dict(chat_id=target_chat_id, sticker=reply_msg.sticker.file_id)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_sticker(**kw)
                _save_text = topic_text or ""

            else:
                text_to_send = (topic_text or "").strip() or (reply_msg.text or "").strip()
                if not text_to_send:
                    await warn(update, "Empty Content", "No text found to send as topic.")
                    return
                kw = dict(chat_id=target_chat_id, text=text_to_send)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_message(**kw)
                _save_text = text_to_send

        else:
            if not topic_text:
                await warn(update, "No Content",
                    "Provide topic text after the command, or reply to a message.")
                return
            kw = dict(chat_id=target_chat_id, text=topic_text)
            if send_thread_id is not None:
                kw['message_thread_id'] = send_thread_id
            sent = await context.bot.send_message(**kw)
            _save_text = topic_text

        topic_msg_id = sent.message_id

        # Pin if requested
        pin_note = ""
        if do_pin:
            with contextlib.suppress(Exception):
                await context.bot.pin_chat_message(
                    chat_id=target_chat_id,
                    message_id=topic_msg_id,
                    disable_notification=True,
                )
            pin_note = "\n📌 Message pinned."

        # Save anchor WITH content metadata
        _set_topic_anchor(admin_id, target_chat_id, topic_msg_id,
                          topic_text=_save_text, topic_photo=_save_photo)

        _auto_name = (_save_text[:30].strip() if _save_text else "") or "Topic"
        _sta_id = _sta_save(admin_id, _auto_name, target_chat_id, topic_msg_id,
                            topic_text=_save_text, topic_photo=_save_photo)

        cross_note = (
            "\n\n🔀 <b>Cross-chat reply active:</b> Quizzes posted to ANY "
            "other channel/group will show a reply header linking back to "
            "this topic message. Tapping it opens this chat directly."
        )

        await ok_html(update, "✅ Topic Sent",
            f"Topic header sent to <b>{h(target_title)}</b>.{pin_note}\n\n"
            f"Saved as <b>#{_sta_id} — {h(_auto_name)}</b>\n\n"
            f"All upcoming posts will reply to this topic.\n"
            f"Reuse later: <code>.usetopic {_sta_id}</code>\n"
            f"See all saved: <code>.mytopics</code>\n"
            f"Remove anchor: <code>.cleartopic</code>"
            f"{cross_note}")

    except TelegramError as e:
        await err(update, "Failed to Send Topic", str(e)[:220])
    except Exception as e:
        await err(update, "Error", str(e)[:220])


# ── 8. Override _cmd_usetopic_m ───────────────────────────────────────

@require_admin
async def _cmd_usetopic_m(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
    """Set a saved topic anchor as active. Usage: .usetopic <id>"""
    admin_id = update.effective_user.id
    args = list(context.args or [])
    if not args or not args[0].isdigit():
        await safe_reply(update, usage_box("usetopic", "<id>",
            "Set a saved topic as active anchor.\nGet IDs from .mytopics"))
        return
    row_id = int(args[0])
    row = _sta_get(row_id, admin_id)
    if not row:
        await warn_html(update, "Not Found",
            f"Topic #{row_id} not found. Use <code>.mytopics</code>.")
        return

    _t_text = getattr(row, 'topic_text', '') or ''
    _t_photo = getattr(row, 'topic_photo', '') or ''
    _set_topic_anchor(admin_id, row.chat_id, row.msg_id,
                      topic_text=_t_text, topic_photo=_t_photo)

    cross_status = (
        "\n🔀 Cross-chat reply enabled — quizzes posted anywhere will link "
        "back to this topic."
    )
    await ok_html(update, "✅ Topic Anchor Set",
        f"Now using: <b>#{row.id} — {h(row.name)}</b>\n"
        f"Chat: <code>{row.chat_id}</code>  Msg: <code>{row.msg_id}</code>\n\n"
        f"All upcoming posts will reply to this topic message.\n"
        f"Remove: <code>.cleartopic</code>"
        f"{cross_status}")


# ── 9. Re-register overridden commands ────────────────────────────────

_prev_build_app_patch_p = build_app

def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_patch_p()
    with contextlib.suppress(Exception):
        _patch_p_db_init()

    private_filter = filters.ChatType.PRIVATE

    _p_overrides = [
        ("topic",      _cmd_topic_m),
        ("cleartopic", _cmd_cleartopic_m),
        ("ct",         _cmd_cleartopic_m),
        ("usetopic",   _cmd_usetopic_m),
        ("ut",         _cmd_usetopic_m),
    ]
    for alias, callback in _p_overrides:
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
            _register_dual_command(app, alias, callback, private_filter)

    logger.info("[PATCH-P] Registered overrides: .topic .cleartopic .usetopic "
                "(true cross-chat reply via ReplyParameters).")
    return app


logger.info("[PATCH-P 2026-05-18] True cross-chat topic reply via Bot API 7.0 ReplyParameters loaded.")
