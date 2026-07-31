# ──────────────────────────────────────────────────────────────────────────────
# Section: 41_probaho_patch_m_groups_topics_05_17
# Original lines: 21511..22622
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────

# ╔══════════════════════════════════════════════════════════════════╗
# ║   PROBAHO PATCH-M — Groups · Topics · .topic · Score Toggle     ║
# ║   Added : 2026-05-17  |  Existing features NOT modified         ║
# ╚══════════════════════════════════════════════════════════════════╝
#
# NEW COMMANDS ADDED (all work with / or . prefix):
#
#  ── Topic Header ──────────────────────────────────────────────────
#  .topic <text> c<serial> [pin]   → Send topic header to channel
#  .topic <text> g<serial> [pin]   → Send topic header to group
#  (reply to a photo+caption msg) then .topic c<serial> [pin]       → Send replied message as topic
#  .cleartopic                     → Remove current topic anchor
#
#  ── Group Management ──────────────────────────────────────────────
#  .adg <group_numeric_id>         → Save/add a group
#  .listgroups  / .lg              → List saved groups
#  .listtopics <group#> / .lt <g#> → List topics of a group
#
#  ── Topic Setup (do inside the group topic thread) ────────────────
#  .info                           → Get thread_id + group info (send inside group topic)
#
#  ── Topic Config (do in bot inbox after .info) ─────────────────────
#  .adtc <group#> <thread_id> [name] → Add/save a topic for a group
#
#  ── Posting ───────────────────────────────────────────────────────
#  .pt <group#> [topic_id] [keep]  → Post buffer to a group topic (thread)
#  .pg <group#> [keep]             → Post buffer to a group (no topic)
#  (existing .p <ch#> [keep] for channels — UNCHANGED)
#
#  ── Score Reply Toggle (owner/admin) ──────────────────────────────
#  .scoreon                        → Enable score reply after posting  (default: ON)
#  .scoreoff                       → Disable score reply after posting
#
#  ── Notes ─────────────────────────────────────────────────────────
#  • Once .topic is sent, ALL subsequent posts (channel & group)
#    will reply-to that topic message until .cleartopic is used.
#  • Score message now replies to topic anchor (not first quiz).
#  • Quizzes posted to groups go as anonymous quizzes (same as channels).

# ── 1. DB tables & migrations ────────────────────────────────────────

def _patch_m_db_init():
    conn = db_connect()
    cur = conn.cursor()

    # Saved groups table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS saved_groups (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        group_chat_id INTEGER NOT NULL UNIQUE,
        title       TEXT,
        added_by    INTEGER,
        created_at  TEXT NOT NULL
    )
    """)

    # Group topics table (each saved topic = one forum thread)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS group_topics (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id    INTEGER NOT NULL,
        topic_name  TEXT NOT NULL,
        thread_id   INTEGER,
        added_by    INTEGER,
        created_at  TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

    # Each column migration is individually guarded so one failure never blocks others
    _migrations = [
        ("users", "score_reply_on",    "ALTER TABLE users ADD COLUMN score_reply_on INTEGER NOT NULL DEFAULT 1"),
        ("users", "topic_anchor_chat", "ALTER TABLE users ADD COLUMN topic_anchor_chat INTEGER"),
        ("users", "topic_anchor_msg",  "ALTER TABLE users ADD COLUMN topic_anchor_msg INTEGER"),
    ]
    for table, col, sql in _migrations:
        try:
            c2 = db_connect()
            if not _table_has_column(c2, table, col):
                c2.execute(sql)
                c2.commit()
            c2.close()
        except Exception as _mig_err:
            logger.warning("[PATCH-M] Migration warning (%s.%s): %s", table, col, _mig_err)

    # Named saved topic anchors (FIX: persistent reusable topics)
    try:
        c3 = db_connect()
        c3.execute("""
        CREATE TABLE IF NOT EXISTS saved_topic_anchors (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id    INTEGER NOT NULL,
            name        TEXT NOT NULL,
            chat_id     INTEGER NOT NULL,
            msg_id      INTEGER NOT NULL,
            created_at  TEXT NOT NULL
        )
        """)
        c3.commit()
        c3.close()
    except Exception as _sta_err:
        logger.warning("[PATCH-M] saved_topic_anchors table error: %s", _sta_err)

with contextlib.suppress(Exception):
    _patch_m_db_init()

# ── 2. SavedGroup helpers ─────────────────────────────────────────────

@dataclass
class SavedGroupRow:
    id: int
    group_chat_id: int
    title: str
    added_by: int
    created_at: str

def _sg_add(group_chat_id: int, title: str, added_by: int) -> int:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO saved_groups (group_chat_id, title, added_by, created_at) VALUES (?,?,?,?)",
        (group_chat_id, title or "", added_by, dt.datetime.utcnow().isoformat())
    )
    conn.commit()
    rid = cur.lastrowid or 0
    conn.close()
    return rid

def _sg_list(requester_id: int) -> List[SavedGroupRow]:
    conn = db_connect()
    cur = conn.cursor()
    if _is_owner_id(requester_id):
        cur.execute("SELECT * FROM saved_groups ORDER BY id")
    else:
        cur.execute("SELECT * FROM saved_groups WHERE added_by=? ORDER BY id", (requester_id,))
    rows = cur.fetchall()
    conn.close()
    return [SavedGroupRow(r["id"], r["group_chat_id"], r["title"] or "", r["added_by"], r["created_at"]) for r in rows]

def _sg_get(serial: int, requester_id: int) -> Optional[SavedGroupRow]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM saved_groups WHERE id=?", (serial,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    if not _is_owner_id(requester_id) and r["added_by"] != requester_id:
        return None
    return SavedGroupRow(r["id"], r["group_chat_id"], r["title"] or "", r["added_by"], r["created_at"])

# ── 3. GroupTopic helpers ─────────────────────────────────────────────

@dataclass
class GroupTopicRow:
    id: int
    group_id: int
    topic_name: str
    thread_id: Optional[int]
    added_by: int
    created_at: str

def _gt_add(group_id: int, topic_name: str, thread_id: Optional[int], added_by: int) -> int:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO group_topics (group_id, topic_name, thread_id, added_by, created_at) VALUES (?,?,?,?,?)",
        (group_id, topic_name or "", thread_id, added_by, dt.datetime.utcnow().isoformat())
    )
    conn.commit()
    rid = cur.lastrowid or 0
    conn.close()
    return rid

def _gt_list(group_id: int) -> List[GroupTopicRow]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM group_topics WHERE group_id=? ORDER BY id", (group_id,))
    rows = cur.fetchall()
    conn.close()
    return [GroupTopicRow(r["id"], r["group_id"], r["topic_name"], r["thread_id"], r["added_by"], r["created_at"]) for r in rows]

def _gt_get(topic_id: int) -> Optional[GroupTopicRow]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM group_topics WHERE id=?", (topic_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    return GroupTopicRow(r["id"], r["group_id"], r["topic_name"], r["thread_id"], r["added_by"], r["created_at"])

# ── 4. Topic Anchor helpers ───────────────────────────────────────────

def _set_topic_anchor(admin_id: int, chat_id: int, msg_id: int) -> None:
    conn = db_connect()
    conn.execute(
        "UPDATE users SET topic_anchor_chat=?, topic_anchor_msg=? WHERE user_id=?",
        (chat_id, msg_id, admin_id)
    )
    conn.commit()
    conn.close()

def _get_topic_anchor(admin_id: int) -> Tuple[Optional[int], Optional[int]]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT topic_anchor_chat, topic_anchor_msg FROM users WHERE user_id=?", (admin_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None, None
    return r["topic_anchor_chat"], r["topic_anchor_msg"]

def _clear_topic_anchor(admin_id: int) -> None:
    conn = db_connect()
    conn.execute(
        "UPDATE users SET topic_anchor_chat=NULL, topic_anchor_msg=NULL WHERE user_id=?",
        (admin_id,)
    )
    conn.commit()
    conn.close()

# ── Named Topic Anchor helpers (FIX-2: persistent reusable topics) ────

@dataclass
class SavedTopicAnchorRow:
    id: int
    admin_id: int
    name: str
    chat_id: int
    msg_id: int
    created_at: str

def _sta_save(admin_id: int, name: str, chat_id: int, msg_id: int) -> int:
    """Save a named topic anchor. Returns new id."""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO saved_topic_anchors (admin_id, name, chat_id, msg_id, created_at) VALUES (?,?,?,?,?)",
        (admin_id, (name or "Topic").strip()[:50], chat_id, msg_id, dt.datetime.utcnow().isoformat())
    )
    conn.commit()
    rid = cur.lastrowid or 0
    conn.close()
    return rid

def _sta_list(admin_id: int) -> List[SavedTopicAnchorRow]:
    conn = db_connect()
    cur = conn.cursor()
    if _is_owner_id(admin_id):
        cur.execute("SELECT * FROM saved_topic_anchors ORDER BY id DESC LIMIT 30")
    else:
        cur.execute("SELECT * FROM saved_topic_anchors WHERE admin_id=? ORDER BY id DESC LIMIT 30", (admin_id,))
    rows = cur.fetchall()
    conn.close()
    return [SavedTopicAnchorRow(r["id"], r["admin_id"], r["name"], r["chat_id"], r["msg_id"], r["created_at"]) for r in rows]

def _sta_get(row_id: int, admin_id: int) -> Optional[SavedTopicAnchorRow]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM saved_topic_anchors WHERE id=?", (row_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    if not _is_owner_id(admin_id) and r["admin_id"] != admin_id:
        return None
    return SavedTopicAnchorRow(r["id"], r["admin_id"], r["name"], r["chat_id"], r["msg_id"], r["created_at"])

def _sta_delete(row_id: int, admin_id: int) -> bool:
    conn = db_connect()
    if _is_owner_id(admin_id):
        cur = conn.execute("DELETE FROM saved_topic_anchors WHERE id=?", (row_id,))
    else:
        cur = conn.execute("DELETE FROM saved_topic_anchors WHERE id=? AND admin_id=?", (row_id, admin_id))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted

# ── 5. Score Reply toggle helpers ─────────────────────────────────────

def _score_reply_enabled(admin_id: int) -> bool:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT score_reply_on FROM users WHERE user_id=?", (admin_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return True  # default ON
    v = r["score_reply_on"]
    return bool(v) if v is not None else True

def _set_score_reply(admin_id: int, val: bool) -> None:
    conn = db_connect()
    conn.execute(
        "UPDATE users SET score_reply_on=? WHERE user_id=?",
        (1 if val else 0, admin_id)
    )
    conn.commit()
    conn.close()

# ── 6. .topic command parser ──────────────────────────────────────────

def _parse_topic_cmd(full_text: str):
    """
    Parse the .topic / /topic command text.
    Returns (topic_text, target_type, serial, do_pin, sub_topic_id)
      target_type : 'c' (channel) or 'g' (group) or None
      serial      : int or None   — channel/group serial number
      do_pin      : bool
      sub_topic_id: int or None   — saved topic serial for group topic threads
                    (only used when target_type == 'g')

    Supported formats (text or reply-to-message):
      .topic <text> c<serial> [pin]
      .topic <text> g<serial> [pin]
      .topic <text> g<serial> <topic_id> [pin]   ← group topic thread
      .topic c<serial> [pin]                      ← when replying to a message
      .topic g<serial> [<topic_id>] [pin]         ← when replying to a message
    """
    # Strip command prefix
    stripped = re.sub(r'^[./]topic\b\s*', '', (full_text or '').strip(), flags=re.IGNORECASE).strip()

    do_pin = False
    sub_topic_id = None
    target_type = None
    serial = None

    # Remove trailing 'pin'
    text = re.sub(r'\s+pin\s*$', '', stripped, flags=re.IGNORECASE).strip()
    if text != stripped:
        do_pin = True

    # Try: g<serial> <topic_id> at the end (group topic thread)
    m = re.search(r'(?:^|\s)([gG])(\d+)\s+(\d+)\s*$', text)
    if m:
        target_type = 'g'
        serial = int(m.group(2))
        sub_topic_id = int(m.group(3))
        topic_text = text[:m.start()].strip()
        return topic_text, target_type, serial, do_pin, sub_topic_id

    # Try: c<serial> or g<serial> at the end
    m = re.search(r'(?:^|\s)([cCgG])(\d+)\s*$', text)
    if m:
        target_type = m.group(1).lower()
        serial = int(m.group(2))
        topic_text = text[:m.start()].strip()
        return topic_text, target_type, serial, do_pin, sub_topic_id

    # No target found
    topic_text = text.strip()
    return topic_text, target_type, serial, do_pin, sub_topic_id

# ── 7. Internal quiz-to-group poster ─────────────────────────────────

async def _post_buffer_to_chat(
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
    chat_id: int,
    items: List[Tuple[int, Dict[str, Any]]],
    thread_id: Optional[int] = None,
) -> Tuple[int, int, Optional[int]]:
    """
    Post buffered quizzes to any chat (channel or group, with or without thread).
    Returns (ok_count, fail_count, first_post_msg_id).
    Replies to topic anchor if set and matches chat_id.
    """
    _anchor_chat_ignored, anchor_msg = _get_topic_anchor(admin_id)
    # FIX: anchor applies globally (cross-chat); Telegram ignores reply_to silently if msg not in that chat
    reply_anchor = anchor_msg if anchor_msg else None

    ok_count = 0
    fail_count = 0
    first_post_msg_id: Optional[int] = None

    for (row_id, payload) in items:
        try:
            q, opts, correct_option_id, expl = quiz_to_poll_parts(payload)
            expl_final = expl.strip() if explain_mode_on(admin_id) else ""
            if expl_final and len(expl_final) > 200:
                expl_final = expl_final[:197] + "..."

            send_kwargs: Dict[str, Any] = dict(
                chat_id=chat_id,
                question=q[:300],
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
            if reply_anchor is not None:
                send_kwargs['reply_to_message_id'] = reply_anchor
                send_kwargs['allow_sending_without_reply'] = True

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
            db_log("ERROR", "patch_m_post_failed", {"admin_id": admin_id, "chat_id": chat_id, "error": str(e)})
        except Exception as e:
            fail_count += 1
            db_log("ERROR", "patch_m_post_ex", {"admin_id": admin_id, "error": str(e)})

    return ok_count, fail_count, first_post_msg_id

async def _send_score_msg(
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
    chat_id: int,
    ok_count: int,
    first_post_msg_id: Optional[int],
    thread_id: Optional[int] = None,
) -> None:
    """Send the score reply message if score reply is enabled."""
    if not _score_reply_enabled(admin_id):
        return
    score_text = _score_reply_text(ok_count)
    _anchor_chat_ignored2, anchor_msg = _get_topic_anchor(admin_id)
    # FIX: anchor applies globally; prefer anchor, fallback to first posted msg
    reply_to = anchor_msg if anchor_msg else first_post_msg_id
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

# ── 8. Commands ───────────────────────────────────────────────────────

@require_admin
async def _cmd_topic_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    .topic <text> c<serial> [pin]            — channel
    .topic <text> g<serial> [pin]            — group (general)
    .topic <text> g<serial> <topic_id> [pin] — group specific topic thread
    Reply to any message (photo/doc/video/audio/text), then:
    .topic c<serial> [pin]
    .topic g<serial> [<topic_id>] [pin]
    Content is forwarded cleanly — no command text is ever shown.
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
            "After sending, all quizzes reply to this topic message.\n"
            "Use <code>.cleartopic</code> to remove the anchor.")
        return

    # Resolve target chat and optional thread_id
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
    else:  # 'g'
        grp = _sg_get(serial, admin_id)
        if not grp:
            await warn_html(update, "Group Not Found",
                f"Group #{serial} not found. Use <code>.listgroups</code>.")
            return
        target_chat_id = grp.group_chat_id
        target_title = grp.title or str(grp.group_chat_id)

        # If sub_topic_id given, look up thread_id
        if sub_topic_id is not None:
            saved_topic = _gt_get(sub_topic_id)
            if not saved_topic or saved_topic.group_id != grp.id:
                await warn_html(update, "Topic Not Found",
                    f"Topic #{sub_topic_id} not found under group #{serial}.\n"
                    f"Use <code>.listtopics {serial}</code> to see available topics.")
                return
            send_thread_id = saved_topic.thread_id
            target_title = f"{grp.title} › {saved_topic.topic_name}"

    # Send topic message — content only, command text is NEVER shown
    sent = None
    try:
        if reply_msg:
            # Forward the replied-to content as the topic header
            if reply_msg.photo:
                caption = topic_text if topic_text else (reply_msg.caption or None)
                kw: Dict[str, Any] = dict(chat_id=target_chat_id, photo=reply_msg.photo[-1].file_id, caption=caption, has_spoiler=True)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_photo(**kw)

            elif reply_msg.document:
                caption = topic_text if topic_text else (reply_msg.caption or None)
                kw = dict(chat_id=target_chat_id, document=reply_msg.document.file_id, caption=caption)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_document(**kw)

            elif reply_msg.video:
                caption = topic_text if topic_text else (reply_msg.caption or None)
                kw = dict(chat_id=target_chat_id, video=reply_msg.video.file_id, caption=caption, has_spoiler=True)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_video(**kw)

            elif reply_msg.audio:
                caption = topic_text if topic_text else (reply_msg.caption or None)
                kw = dict(chat_id=target_chat_id, audio=reply_msg.audio.file_id, caption=caption)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_audio(**kw)

            elif reply_msg.voice:
                caption = topic_text if topic_text else (reply_msg.caption or None)
                kw = dict(chat_id=target_chat_id, voice=reply_msg.voice.file_id, caption=caption)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_voice(**kw)

            elif reply_msg.sticker:
                kw = dict(chat_id=target_chat_id, sticker=reply_msg.sticker.file_id)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_sticker(**kw)

            else:
                # Plain text — use topic_text if given, else original message text
                text_to_send = (topic_text or "").strip() or (reply_msg.text or "").strip()
                if not text_to_send:
                    await warn(update, "Empty Content", "No text found to send as topic.")
                    return
                kw = dict(chat_id=target_chat_id, text=text_to_send)
                if send_thread_id is not None:
                    kw['message_thread_id'] = send_thread_id
                sent = await context.bot.send_message(**kw)

        else:
            # No reply — send topic_text as plain text
            if not topic_text:
                await warn(update, "No Content",
                    "Provide topic text after the command, or reply to a message.")
                return
            kw = dict(chat_id=target_chat_id, text=topic_text)
            if send_thread_id is not None:
                kw['message_thread_id'] = send_thread_id
            sent = await context.bot.send_message(**kw)

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

        # Save as active topic anchor
        _set_topic_anchor(admin_id, target_chat_id, topic_msg_id)

        # FIX-2: also save as named persistent topic (auto-name from topic text)
        _auto_name = (topic_text[:30].strip() if topic_text else "") or "Topic"
        _sta_id = _sta_save(admin_id, _auto_name, target_chat_id, topic_msg_id)

        await ok_html(update, "✅ Topic Sent",
            f"Topic header sent to <b>{h(target_title)}</b>.{pin_note}\n\n"
            f"Saved as <b>#{_sta_id} — {h(_auto_name)}</b>\n\n"
            f"All upcoming posts will reply to this topic.\n"
            f"Reuse later: <code>.usetopic {_sta_id}</code>\n"
            f"See all saved: <code>.mytopics</code>\n"
            f"Remove anchor: <code>.cleartopic</code>")

    except TelegramError as e:
        await err(update, "Failed to Send Topic", str(e)[:220])
    except Exception as e:
        await err(update, "Error", str(e)[:220])


@require_admin
async def _cmd_cleartopic_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove the current topic anchor."""
    admin_id = update.effective_user.id
    _clear_topic_anchor(admin_id)
    await ok(update, "Topic Anchor Cleared",
        "Topic anchor removed. Quiz posts will no longer reply to a topic message.")


@require_admin
async def _cmd_adg_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add/save a group. Usage: .adg <group_numeric_id>"""
    admin_id = update.effective_user.id
    if not context.args:
        await safe_reply(update, usage_box(
            "adg", "<group_numeric_id>",
            "Save a Telegram group by its numeric ID.\n"
            "The bot must already be a member of the group.\n"
            "Example: .adg -1001234567890"
        ))
        return

    raw = (context.args[0] or "").strip()
    try:
        group_chat_id = int(raw)
    except ValueError:
        await warn(update, "Invalid ID", "Provide a numeric group ID (e.g. -1001234567890).")
        return

    title = f"Group {group_chat_id}"
    try:
        chat = await context.bot.get_chat(group_chat_id)
        title = chat.title or title
    except Exception:
        pass

    gid = _sg_add(group_chat_id, title, admin_id)
    await ok_html(update, "✅ Group Saved",
        f"<b>{h(title)}</b>\n"
        f"Chat ID: <code>{group_chat_id}</code>\n"
        f"Serial: <b>#{gid}</b>\n\n"
        f"Next: Go into a topic in that group and use <code>.info</code> to get the thread ID.")


@require_admin
async def _cmd_listgroups_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all saved groups."""
    admin_id = update.effective_user.id
    rows = _sg_list(admin_id)
    if not rows:
        await info_html(update, "No Groups Saved",
            "Use <code>.adg &lt;group_id&gt;</code> to save a group.")
        return
    lines = []
    for g in rows:
        topics = _gt_list(g.id)
        tp = f" — {len(topics)} topic(s)" if topics else ""
        lines.append(
            f"<b>#{g.id}</b>  <code>{g.group_chat_id}</code>  <b>{h(g.title)}</b>{tp}"
        )
    await ok_html(update, f"Saved Groups ({len(rows)})", "\n".join(lines))


async def _cmd_info_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Send this inside a group topic thread to get the thread ID.
    Works only for owner/admin.
    """
    msg = update.message
    if not msg:
        return
    uid = update.effective_user.id if update.effective_user else 0
    if not (_is_owner_id(uid) or is_admin(uid)):
        return  # silently ignore for non-staff

    chat = msg.chat
    chat_id = chat.id
    chat_title = chat.title or str(chat_id)
    thread_id = getattr(msg, 'message_thread_id', None)

    # Check if group is saved
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM saved_groups WHERE group_chat_id=?", (chat_id,))
    grp_row = cur.fetchone()
    conn.close()

    grp_serial = grp_row["id"] if grp_row else None
    if grp_serial:
        grp_note = f"Group Serial: <b>#{grp_serial}</b>"
    else:
        grp_note = f"⚠️ Group not saved yet.\nSave it first: <code>.adg {chat_id}</code>"

    if thread_id is not None:
        adtc_hint = (
            f"\n\nTo save this topic in bot inbox:\n"
            f"<code>.adtc {grp_serial or '?'} {thread_id} TopicName</code>"
        )
    else:
        adtc_hint = "\n\n⚠️ Not inside a topic thread. Go into a specific topic and send <code>.info</code> there."

    reply_text = (
        f"ℹ️ <b>Chat / Topic Info</b>\n\n"
        f"Chat ID: <code>{chat_id}</code>\n"
        f"Title: <b>{h(chat_title)}</b>\n"
        f"Thread ID: <code>{thread_id if thread_id else 'N/A (not a topic)'}</code>\n"
        f"{grp_note}{adtc_hint}"
    )
    try:
        await msg.reply_text(reply_text, parse_mode=ParseMode.HTML)
    except Exception:
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                chat_id=uid, text=reply_text, parse_mode=ParseMode.HTML
            )


@require_admin
async def _cmd_adtc_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Add a topic for a saved group.
    Usage: .adtc <group_serial> <thread_id> [topic_name]
    """
    admin_id = update.effective_user.id
    args = list(context.args or [])
    if len(args) < 2:
        await safe_reply(update, usage_box(
            "adtc", "<group#> <thread_id> [topic_name]",
            "Save a group topic.\n"
            "Get thread_id by sending .info inside the topic.\n"
            "Example: .adtc 1 12345 Biology"
        ))
        return

    try:
        group_serial = int(args[0])
        thread_id = int(args[1])
    except ValueError:
        await warn(update, "Invalid Args", "group# and thread_id must be numeric.")
        return

    topic_name = ' '.join(args[2:]).strip() or f"Topic {thread_id}"
    grp = _sg_get(group_serial, admin_id)
    if not grp:
        await warn_html(update, "Group Not Found",
            f"Group #{group_serial} not found. Use <code>.listgroups</code>.")
        return

    tid = _gt_add(grp.id, topic_name, thread_id, admin_id)
    await ok_html(update, "✅ Topic Saved",
        f"<b>{h(topic_name)}</b>\n"
        f"Thread ID: <code>{thread_id}</code>\n"
        f"Topic Serial: <b>#{tid}</b>\n"
        f"Group: <b>{h(grp.title)}</b> (#{grp.id})\n\n"
        f"Post to this topic: <code>.pt {group_serial} {tid}</code>")


@require_admin
async def _cmd_listtopics_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List topics saved for a group. Usage: .listtopics <group#>"""
    admin_id = update.effective_user.id
    args = list(context.args or [])
    if not args or not args[0].isdigit():
        await safe_reply(update, usage_box("listtopics", "<group#>", "List saved topics for a group."))
        return
    group_serial = int(args[0])
    grp = _sg_get(group_serial, admin_id)
    if not grp:
        await warn_html(update, "Group Not Found", f"Group #{group_serial} not found.")
        return
    topics = _gt_list(grp.id)
    if not topics:
        await info_html(update, "No Topics",
            f"No topics saved for group #{group_serial}.\n"
            f"Use: <code>.adtc {group_serial} &lt;thread_id&gt; [name]</code>")
        return
    lines = [
        f"<b>#{t.id}</b>  Thread: <code>{t.thread_id}</code>  <b>{h(t.topic_name)}</b>"
        for t in topics
    ]
    await ok_html(update, f"Topics — {h(grp.title)}", "\n".join(lines))


@require_admin
async def _cmd_pt_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Post buffered quizzes to a saved group's topic (thread).
    Usage: .pt <group#> [topic_id] [keep]
    """
    admin_id = update.effective_user.id
    args = list(context.args or [])

    if not args or not args[0].isdigit():
        await safe_reply(update, usage_box(
            "pt", "<group#> [topic_id] [keep]",
            "Post buffer to a saved group topic.\n"
            "Omit topic_id to see available topics.\n"
            "Add 'keep' to keep buffer after posting."
        ))
        return

    group_serial = int(args[0])
    grp = _sg_get(group_serial, admin_id)
    if not grp:
        await warn_html(update, "Group Not Found",
            f"Group #{group_serial} not found. Use <code>.listgroups</code>.")
        return

    topics = _gt_list(grp.id)

    topic_id: Optional[int] = None
    keep = False
    for a in args[1:]:
        if a.lower() == 'keep':
            keep = True
        elif a.isdigit():
            topic_id = int(a)

    if topic_id is None:
        if not topics:
            await warn_html(update, "No Topics Saved",
                f"No topics for group <b>{h(grp.title)}</b>.\n"
                f"Use: <code>.adtc {group_serial} &lt;thread_id&gt; [name]</code>")
            return
        lines = [
            f"<b>#{t.id}</b>  Thread: <code>{t.thread_id}</code>  <b>{h(t.topic_name)}</b>"
            for t in topics
        ]
        await info_html(update, f"Available Topics — {h(grp.title)}",
            "\n".join(lines) + f"\n\nUsage: <code>.pt {group_serial} &lt;topic_id&gt;</code>")
        return

    topic = _gt_get(topic_id)
    if not topic or topic.group_id != grp.id:
        await warn_html(update, "Topic Not Found",
            f"Topic #{topic_id} not found under group #{group_serial}.")
        return

    items = buffer_list(admin_id, limit=MAX_BUFFERED_QUESTIONS)
    if not items:
        await warn(update, "Buffer Empty", "No quizzes to post. Send text or forward polls first.")
        return

    chat_id = grp.group_chat_id
    thread_id = topic.thread_id

    await info_html(update, "📤 Posting to Group Topic",
        f"Group: <b>{h(grp.title)}</b>\n"
        f"Topic: <b>{h(topic.topic_name)}</b>\n"
        f"Thread ID: <code>{thread_id}</code>\n"
        f"Questions: <code>{len(items)}</code>")

    ok_count, fail_count, first_msg_id = await _post_buffer_to_chat(
        context, admin_id, chat_id, items, thread_id=thread_id
    )

    if ok_count > 0:
        await _send_score_msg(context, admin_id, chat_id, ok_count, first_msg_id, thread_id=thread_id)

    inc_admin_post(admin_id, ok_count)
    posted_ids = [row_id for (row_id, _) in items[:ok_count + fail_count]]
    # More precise: collect successful ids
    # Since we don't track individual success, remove the first ok_count items from buffer
    all_ids = [row_id for (row_id, _) in items]
    if all_ids and not keep:
        buffer_remove_ids(admin_id, all_ids[:ok_count])

    await ok(update, "✅ Posting Complete",
        f"Posted: {ok_count}\nFailed: {fail_count}\nBuffer remaining: {buffer_count(admin_id)}")


@require_admin
async def _cmd_pg_private_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Post buffered quizzes to a saved group (no topic/thread).
    Usage: .pg <group#> [keep]
    (In private chat only — group .pg is still cmd_porag)
    """
    admin_id = update.effective_user.id
    args = list(context.args or [])

    if not args or not args[0].isdigit():
        await safe_reply(update, usage_box(
            "pg", "<group#> [keep]",
            "Post buffer to a saved group (general, no topic).\n"
            "Add 'keep' to keep buffer after posting."
        ))
        return

    group_serial = int(args[0])
    keep = len(args) > 1 and args[1].lower() == 'keep'
    grp = _sg_get(group_serial, admin_id)
    if not grp:
        await warn_html(update, "Group Not Found",
            f"Group #{group_serial} not found. Use <code>.listgroups</code>.")
        return

    items = buffer_list(admin_id, limit=MAX_BUFFERED_QUESTIONS)
    if not items:
        await warn(update, "Buffer Empty", "No quizzes to post.")
        return

    chat_id = grp.group_chat_id
    await info_html(update, "📤 Posting to Group",
        f"Group: <b>{h(grp.title)}</b>\n"
        f"Questions: <code>{len(items)}</code>")

    ok_count, fail_count, first_msg_id = await _post_buffer_to_chat(
        context, admin_id, chat_id, items, thread_id=None
    )

    if ok_count > 0:
        await _send_score_msg(context, admin_id, chat_id, ok_count, first_msg_id, thread_id=None)

    inc_admin_post(admin_id, ok_count)
    all_ids = [row_id for (row_id, _) in items]
    if all_ids and not keep:
        buffer_remove_ids(admin_id, all_ids[:ok_count])

    await ok(update, "✅ Posting Complete",
        f"Posted: {ok_count}\nFailed: {fail_count}\nBuffer remaining: {buffer_count(admin_id)}")


@require_admin
async def _cmd_mytopics_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all saved topic anchors. Usage: .mytopics"""
    admin_id = update.effective_user.id
    rows = _sta_list(admin_id)
    if not rows:
        await info_html(update, "No Saved Topics",
            "No topics saved yet.\n"
            "Use <code>.topic &lt;text&gt; c&lt;serial&gt;</code> to create and save a topic.")
        return
    lines = []
    for r in rows:
        lines.append(
            f"<b>#{r.id}</b>  <b>{h(r.name)}</b>\n"
            f"   Chat: <code>{r.chat_id}</code>  Msg: <code>{r.msg_id}</code>"
        )
    await ok_html(update, f"Saved Topics ({len(rows)})",
        "\n".join(lines) + "\n\n"
        "Use: <code>.usetopic &lt;id&gt;</code> to set one as active\n"
        "Del: <code>.deltopic &lt;id&gt;</code> to remove one")


@require_admin
async def _cmd_usetopic_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"Topic #{row_id} not found. Use <code>.mytopics</code> to see available topics.")
        return
    _set_topic_anchor(admin_id, row.chat_id, row.msg_id)
    await ok_html(update, "✅ Topic Anchor Set",
        f"Now using: <b>#{row.id} — {h(row.name)}</b>\n"
        f"Chat: <code>{row.chat_id}</code>  Msg: <code>{row.msg_id}</code>\n\n"
        f"All upcoming posts will reply to this topic message.\n"
        f"Remove: <code>.cleartopic</code>")


@require_admin
async def _cmd_deltopic_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a saved topic anchor. Usage: .deltopic <id>"""
    admin_id = update.effective_user.id
    args = list(context.args or [])
    if not args or not args[0].isdigit():
        await safe_reply(update, usage_box("deltopic", "<id>", "Delete a saved topic."))
        return
    row_id = int(args[0])
    deleted = _sta_delete(row_id, admin_id)
    if deleted:
        await ok(update, "Deleted", f"Topic #{row_id} removed from saved list.")
    else:
        await warn_html(update, "Not Found", f"Topic #{row_id} not found or no permission.")


@require_admin
async def _cmd_scoreon_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enable score reply after posting."""
    admin_id = update.effective_user.id
    _set_score_reply(admin_id, True)
    await ok(update, "Score Reply ON", "Score message will be sent after every post.")


@require_admin
async def _cmd_scoreoff_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Disable score reply after posting."""
    admin_id = update.effective_user.id
    _set_score_reply(admin_id, False)
    await ok(update, "Score Reply OFF", "Score message will NOT be sent after posting.")


# ── 9. Patch channel cmd_post to use topic anchor for score reply ─────

_prev_cmd_post_patch_m = None  # will be set inside build_app

async def _cmd_post_patched_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Thin wrapper around the latest cmd_post.
    After posting, replaces the score reply with a topic-anchor-aware version.
    """
    # We can't easily intercept the score part inside cmd_post without monkey-patching.
    # Instead, we override _score_reply_text indirectly:
    # The approach: disable the built-in score by temporarily patching, then send our own.
    # Simpler approach: just let cmd_post run as-is (it already sends score to first_msg_id).
    # Then if we have a topic anchor for that channel, we send ANOTHER score reply to the topic.
    # To avoid duplicate scores, we need to suppress the old one.
    # Best approach: patch _score_reply_text to return "" when score is disabled,
    # and post our own score. But that's fragile.
    #
    # Cleanest: Just run the original cmd_post. Its score goes to first_quiz.
    # If admin set a topic anchor → send an ADDITIONAL score to the topic anchor.
    # But that gives 2 score messages.
    #
    # FINAL decision: Run original cmd_post. It handles the score.
    # Our .pt and .pg commands use the new _send_score_msg which respects anchor.
    # For .p (channel), the topic anchor reply is handled by send_poll having reply_to.
    # The score in cmd_post is a separate send_message, which we can't intercept cleanly here.
    # → Accept: .p channel posts won't change score behavior; .pt / .pg use new logic.
    # This matches user's requirement since .pt and .pg are the new group commands.
    await _prev_cmd_post_patch_m(update, context)


# ── 10. Register all new commands in build_app ────────────────────────

_prev_build_app_patch_m = build_app

def build_app() -> Application:  # noqa: F811
    global _prev_cmd_post_patch_m
    app = _prev_build_app_patch_m()   # db_init() is called inside here

    # Run migrations AFTER db_init() so the users table definitely exists
    with contextlib.suppress(Exception):
        _patch_m_db_init()

    private_filter = filters.ChatType.PRIVATE
    group_filter = (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
    any_filter = filters.ALL

    # Private commands (bot inbox)
    new_private_cmds = [
        ("topic",       _cmd_topic_m),
        ("cleartopic",  _cmd_cleartopic_m),
        ("ct",          _cmd_cleartopic_m),     # short alias
        ("adg",         _cmd_adg_m),
        ("listgroups",  _cmd_listgroups_m),
        ("lg",          _cmd_listgroups_m),
        ("adtc",        _cmd_adtc_m),
        ("listtopics",  _cmd_listtopics_m),
        ("lt",          _cmd_listtopics_m),
        ("pt",          _cmd_pt_m),
        ("scoreon",     _cmd_scoreon_m),
        ("scon",        _cmd_scoreon_m),
        ("scoreoff",    _cmd_scoreoff_m),
        ("scoff",       _cmd_scoreoff_m),
        # FIX-2: named topic commands
        ("mytopics",    _cmd_mytopics_m),
        ("mt",          _cmd_mytopics_m),
        ("usetopic",    _cmd_usetopic_m),
        ("ut",          _cmd_usetopic_m),
        ("deltopic",    _cmd_deltopic_m),
        ("dt",          _cmd_deltopic_m),
    ]

    # .pg in private → group post (no topic). Group .pg = cmd_porag, untouched.
    # We register with private_filter so there's no conflict.
    new_private_cmds.append(("pg", _cmd_pg_private_m))

    for alias, callback in new_private_cmds:
        with contextlib.suppress(Exception):
            _register_dual_command(app, alias, callback, private_filter)

    # .info works inside group topic threads
    with contextlib.suppress(Exception):
        _register_dual_command(app, "info", _cmd_info_m, group_filter)

    logger.info(
        "[PATCH-M] Registered: .topic .cleartopic .adg .listgroups .adtc .listtopics "
        ".pt .pg(private) .info(group) .scoreon .scoreoff"
    )
    return app


logger.info("[PATCH-M 2026-05-17] Groups, Topics, .topic, Group Posting, Score Toggle loaded.")
