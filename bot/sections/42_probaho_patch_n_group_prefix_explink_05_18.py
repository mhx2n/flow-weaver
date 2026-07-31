# ──────────────────────────────────────────────────────────────────────────────
# Section: 42_probaho_patch_n_group_prefix_explink_05_18
# Original lines: 22623..23166
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════
# END PROBAHO PATCH-M
# ═══════════════════════════════════════════════════════════════════════

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  PROBAHO PATCH-N — Group Prefix/ExpLink · .cmd Refresh              ║
# ║  Added : 2026-05-18  |  Previous features NOT modified              ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# NEW COMMANDS (all work with / or . prefix):
#
#  .gsp  <group#> [text]   → Set quiz prefix for a saved group (clear if no text)
#  .gsx  <group#> [link]   → Set explanation link for a saved group (clear if none)
#
# UPDATED COMMANDS:
#  .listgroups / .lg       → Now shows prefix + explink per group
#  .cmd  (private)         → Now includes all Group-Management commands
#
# HOW PREFIX WORKS IN GROUPS (same as channels):
#  Each quiz question is prefixed with the group prefix before sending.
#  The explanation link is appended to the explanation field.

# ── 1. DB migrations for saved_groups columns ─────────────────────────

def _patch_n_db_init() -> None:
    _new_cols = [
        ("saved_groups", "prefix",   "ALTER TABLE saved_groups ADD COLUMN prefix TEXT DEFAULT ''"),
        ("saved_groups", "expl_link","ALTER TABLE saved_groups ADD COLUMN expl_link TEXT DEFAULT ''"),
    ]
    for table, col, sql in _new_cols:
        try:
            conn = db_connect()
            if not _table_has_column(conn, table, col):
                conn.execute(sql)
                conn.commit()
            conn.close()
        except Exception as _mig_e:
            logger.warning("[PATCH-N] Migration warning (%s.%s): %s", table, col, _mig_e)

with contextlib.suppress(Exception):
    _patch_n_db_init()

# ── 2. Updated SavedGroupRow + DB helpers ─────────────────────────────

@dataclass
class SavedGroupRow:   # noqa: F811 — intentional override
    id: int
    group_chat_id: int
    title: str
    added_by: int
    created_at: str
    prefix: str = ""
    expl_link: str = ""


def _sg_row_from_db(r) -> "SavedGroupRow":
    return SavedGroupRow(
        id=r["id"],
        group_chat_id=int(r["group_chat_id"]),
        title=r["title"] or "",
        added_by=r["added_by"],
        created_at=r["created_at"],
        prefix=r["prefix"] if r["prefix"] is not None else "",
        expl_link=r["expl_link"] if r["expl_link"] is not None else "",
    )


def _sg_list(requester_id: int) -> List["SavedGroupRow"]:   # noqa: F811
    conn = db_connect()
    cur = conn.cursor()
    try:
        if _is_owner_id(requester_id):
            cur.execute("SELECT * FROM saved_groups ORDER BY id")
        else:
            cur.execute("SELECT * FROM saved_groups WHERE added_by=? ORDER BY id", (requester_id,))
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    result = []
    for r in rows:
        try:
            result.append(_sg_row_from_db(r))
        except Exception:
            pass
    return result


def _sg_get(serial: int, requester_id: int) -> Optional["SavedGroupRow"]:   # noqa: F811
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM saved_groups WHERE id=?", (serial,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    if not _is_owner_id(requester_id) and r["added_by"] != requester_id:
        return None
    try:
        return _sg_row_from_db(r)
    except Exception:
        return SavedGroupRow(r["id"], int(r["group_chat_id"]), r["title"] or "", r["added_by"], r["created_at"])


def _sg_set_prefix(group_serial: int, prefix: str) -> bool:
    try:
        conn = db_connect()
        conn.execute("UPDATE saved_groups SET prefix=? WHERE id=?", (prefix or "", group_serial))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.warning("[PATCH-N] _sg_set_prefix error: %s", e)
        return False


def _sg_set_expl_link(group_serial: int, link: str) -> bool:
    try:
        conn = db_connect()
        conn.execute("UPDATE saved_groups SET expl_link=? WHERE id=?", (link or "", group_serial))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.warning("[PATCH-N] _sg_set_expl_link error: %s", e)
        return False

# ── 3. Updated _post_buffer_to_chat with prefix/expl_link support ──────

async def _post_buffer_to_chat(   # noqa: F811 — intentional override
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
    chat_id: int,
    items: List[Tuple[int, Dict[str, Any]]],
    thread_id: Optional[int] = None,
    group_prefix: str = "",
    group_expl_link: str = "",
) -> Tuple[int, int, Optional[int]]:
    """
    Post buffered quizzes to any chat (channel or group, with or without thread).
    Returns (ok_count, fail_count, first_post_msg_id).
    Replies to topic anchor if set and matches chat_id.
    Applies group_prefix and group_expl_link when provided.
    """
    anchor_chat, anchor_msg = _get_topic_anchor(admin_id)
    reply_anchor = anchor_msg if (anchor_chat == chat_id and anchor_msg) else None

    prefix = (group_prefix or "").strip()
    expl_tail = (group_expl_link or "").strip()
    SEP = "\n\u200b"

    ok_count = 0
    fail_count = 0
    first_post_msg_id: Optional[int] = None

    for (row_id, payload) in items:
        try:
            q, opts, correct_option_id, expl = quiz_to_poll_parts(payload)

            # Apply prefix
            q_final = f"{prefix}{SEP}{q}".strip() if prefix else q.strip()
            if len(q_final) > 300:
                q_final = q_final[:297] + "..."

            # Apply explanation
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
            db_log("ERROR", "patch_n_post_failed", {"admin_id": admin_id, "chat_id": chat_id, "error": str(e)})
        except Exception as e:
            fail_count += 1
            db_log("ERROR", "patch_n_post_ex", {"admin_id": admin_id, "error": str(e)})

    return ok_count, fail_count, first_post_msg_id

# ── 4. Updated .pt and .pg to pass group prefix/expl_link ─────────────

@require_admin
async def _cmd_pt_m(update: Update, context: ContextTypes.DEFAULT_TYPE):   # noqa: F811
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

    pfx_note = f"\nPrefix: <code>{h(grp.prefix)}</code>" if grp.prefix else ""
    lnk_note = f"\nExp.Link: <code>{h(grp.expl_link)}</code>" if grp.expl_link else ""

    await info_html(update, "📤 Posting to Group Topic",
        f"Group: <b>{h(grp.title)}</b>\n"
        f"Topic: <b>{h(topic.topic_name)}</b>\n"
        f"Thread ID: <code>{thread_id}</code>\n"
        f"Questions: <code>{len(items)}</code>{pfx_note}{lnk_note}")

    ok_count, fail_count, first_msg_id = await _post_buffer_to_chat(
        context, admin_id, chat_id, items,
        thread_id=thread_id,
        group_prefix=grp.prefix,
        group_expl_link=grp.expl_link,
    )

    if ok_count > 0:
        await _send_score_msg(context, admin_id, chat_id, ok_count, first_msg_id, thread_id=thread_id)

    inc_admin_post(admin_id, ok_count)
    all_ids = [row_id for (row_id, _) in items]
    if all_ids and not keep:
        buffer_remove_ids(admin_id, all_ids[:ok_count])

    await ok(update, "✅ Posting Complete",
        f"Posted: {ok_count}\nFailed: {fail_count}\nBuffer remaining: {buffer_count(admin_id)}")


@require_admin
async def _cmd_pg_private_m(update: Update, context: ContextTypes.DEFAULT_TYPE):   # noqa: F811
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
    pfx_note = f"\nPrefix: <code>{h(grp.prefix)}</code>" if grp.prefix else ""
    lnk_note = f"\nExp.Link: <code>{h(grp.expl_link)}</code>" if grp.expl_link else ""

    await info_html(update, "📤 Posting to Group",
        f"Group: <b>{h(grp.title)}</b>\n"
        f"Questions: <code>{len(items)}</code>{pfx_note}{lnk_note}")

    ok_count, fail_count, first_msg_id = await _post_buffer_to_chat(
        context, admin_id, chat_id, items,
        thread_id=None,
        group_prefix=grp.prefix,
        group_expl_link=grp.expl_link,
    )

    if ok_count > 0:
        await _send_score_msg(context, admin_id, chat_id, ok_count, first_msg_id, thread_id=None)

    inc_admin_post(admin_id, ok_count)
    all_ids = [row_id for (row_id, _) in items]
    if all_ids and not keep:
        buffer_remove_ids(admin_id, all_ids[:ok_count])

    await ok(update, "✅ Posting Complete",
        f"Posted: {ok_count}\nFailed: {fail_count}\nBuffer remaining: {buffer_count(admin_id)}")

# ── 5. Updated .listgroups to show prefix/explink ─────────────────────

@require_admin
async def _cmd_listgroups_m(update: Update, context: ContextTypes.DEFAULT_TYPE):   # noqa: F811
    """List all saved groups with prefix/explink info."""
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
        pfx = f"\n    Prefix: <code>{h(g.prefix)}</code>" if g.prefix else ""
        lnk = f"\n    Link: <code>{h(g.expl_link)}</code>" if g.expl_link else ""
        lines.append(
            f"<b>#{g.id}</b>  <code>{g.group_chat_id}</code>  <b>{h(g.title)}</b>{tp}{pfx}{lnk}"
        )
    await ok_html(update, f"Saved Groups ({len(rows)})", "\n\n".join(lines))

# ── 6. New commands: .gsp and .gsx ────────────────────────────────────

@require_admin
async def _cmd_gsp_n(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Set or clear the quiz prefix for a saved group.
    Usage: .gsp <group#> [prefix text]
    Omit prefix text to clear it.
    """
    admin_id = update.effective_user.id
    args = list(context.args or [])

    if not args or not args[0].isdigit():
        await safe_reply(update, usage_box(
            "gsp", "<group#> [prefix text]",
            "Set the quiz prefix for a saved group.\n"
            "Omit the prefix text to clear it.\n"
            "Example: .gsp 1 প্রবাহ\n"
            "Clear:   .gsp 1"
        ))
        return

    group_serial = int(args[0])
    grp = _sg_get(group_serial, admin_id)
    if not grp:
        await warn_html(update, "Group Not Found",
            f"Group #{group_serial} not found. Use <code>.listgroups</code>.")
        return

    new_prefix = " ".join(args[1:]).strip()
    old_prefix = grp.prefix or "(none)"
    ok_flag = _sg_set_prefix(group_serial, new_prefix)
    if ok_flag:
        if new_prefix:
            await ok_html(update, "✅ Group Prefix Set",
                f"Group: <b>{h(grp.title)}</b> (#{grp.id})\n"
                f"Old prefix: <code>{h(old_prefix)}</code>\n"
                f"New prefix: <code>{h(new_prefix)}</code>")
        else:
            await ok_html(update, "✅ Group Prefix Cleared",
                f"Group: <b>{h(grp.title)}</b> (#{grp.id})\n"
                f"Prefix removed.")
    else:
        await err(update, "Update Failed", "Could not update the group prefix. Try again.")


@require_admin
async def _cmd_gsx_n(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Set or clear the explanation link for a saved group.
    Usage: .gsx <group#> [https://...]
    Omit the link to clear it.
    """
    admin_id = update.effective_user.id
    args = list(context.args or [])

    if not args or not args[0].isdigit():
        await safe_reply(update, usage_box(
            "gsx", "<group#> [https://...]",
            "Set the explanation link for a saved group.\n"
            "Omit the link to clear it.\n"
            "Example: .gsx 1 https://t.me/mychannel\n"
            "Clear:   .gsx 1"
        ))
        return

    group_serial = int(args[0])
    grp = _sg_get(group_serial, admin_id)
    if not grp:
        await warn_html(update, "Group Not Found",
            f"Group #{group_serial} not found. Use <code>.listgroups</code>.")
        return

    new_link = " ".join(args[1:]).strip()
    old_link = grp.expl_link or "(none)"
    ok_flag = _sg_set_expl_link(group_serial, new_link)
    if ok_flag:
        if new_link:
            await ok_html(update, "✅ Group Exp.Link Set",
                f"Group: <b>{h(grp.title)}</b> (#{grp.id})\n"
                f"Old link: <code>{h(old_link)}</code>\n"
                f"New link: <code>{h(new_link)}</code>")
        else:
            await ok_html(update, "✅ Group Exp.Link Cleared",
                f"Group: <b>{h(grp.title)}</b> (#{grp.id})\n"
                f"Explanation link removed.")
    else:
        await err(update, "Update Failed", "Could not update the group exp.link. Try again.")

# ── 7. Update PRIVATE_COMMAND_SECTIONS + cmd_commands at runtime ───────

# Extend admin section with group-management and new group-prefix commands
_PATCH_N_ADMIN_CMDS = [
    # ── Group Management ──────────────────────────────────────────────
    ("adg",         "Save/add a group by numeric ID"),
    ("listgroups",  "List all saved groups (shows prefix & link)"),
    ("adtc",        "Save a topic thread for a group"),
    ("listtopics",  "List saved topics for a group"),
    # ── Group Posting ─────────────────────────────────────────────────
    ("pt",          "Post buffer to a group topic thread"),
    ("pg",          "Post buffer to a group (no topic)"),
    # ── Group Prefix / Link (new in PATCH-N) ──────────────────────────
    ("gsp",         "Set/clear quiz prefix for a group  (.gsp <g#> [text])"),
    ("gsx",         "Set/clear exp.link for a group  (.gsx <g#> [link])"),
    # ── Topic Header ──────────────────────────────────────────────────
    ("topic",       "Send topic header to channel/group/topic"),
    ("cleartopic",  "Remove current topic anchor"),
    # ── Score Toggle ──────────────────────────────────────────────────
    ("scoreon",     "Enable score reply after posting"),
    ("scoreoff",    "Disable score reply after posting"),
]

# De-duplicate: remove any existing entries with same command names
_patch_n_cmd_names = {c for c, _ in _PATCH_N_ADMIN_CMDS}
PRIVATE_COMMAND_SECTIONS["admin"] = [
    item for item in PRIVATE_COMMAND_SECTIONS["admin"]
    if item[0] not in _patch_n_cmd_names
] + _PATCH_N_ADMIN_CMDS

# Also add short aliases to COMMAND_ALIAS_REGISTRY
COMMAND_ALIAS_REGISTRY.update({
    "adg":        ["adg"],
    "listgroups": ["lg"],
    "adtc":       ["adtc"],
    "listtopics": ["lt"],
    "pt":         ["pt"],
    "gsp":        ["gsp"],
    "gsx":        ["gsx"],
    "topic":      ["topic"],
    "cleartopic": ["ct"],
    "scoreon":    ["scon"],
    "scoreoff":   ["scoff"],
})

# ── 8. Register new commands in build_app ─────────────────────────────

_prev_build_app_patch_n = build_app

def build_app() -> Application:   # noqa: F811
    app = _prev_build_app_patch_n()

    private_filter = filters.ChatType.PRIVATE
    group_filter = (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)

    new_cmds = [
        ("gsp",        _cmd_gsp_n),
        ("gsetprefix", _cmd_gsp_n),   # long alias
        ("gsx",        _cmd_gsx_n),
        ("gsetexplink",_cmd_gsx_n),   # long alias
        # Override .pt, .pg, .listgroups with updated versions
        ("pt",         _cmd_pt_m),
        ("pg",         _cmd_pg_private_m),
        ("listgroups", _cmd_listgroups_m),
        ("lg",         _cmd_listgroups_m),
    ]

    for alias, callback in new_cmds:
        with contextlib.suppress(Exception):
            _register_dual_command(app, alias, callback, private_filter)

    logger.info("[PATCH-N] Registered: .gsp .gsx .gsetprefix .gsetexplink (group prefix/link) + refreshed .pt .pg .listgroups")
    return app


logger.info("[PATCH-N 2026-05-18] Group Prefix/ExpLink, .cmd refresh, .pt/.pg updated.")
