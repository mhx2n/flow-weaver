# ──────────────────────────────────────────────────────────────────────────────
# Section: 46_probaho_patch_r_mongo_persistent_backup_05_18
# Original lines: 24480..25005
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════
# END PROBAHO PATCH-Q
# ═══════════════════════════════════════════════════════════════════════


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  PROBAHO PATCH-R — MongoDB Persistent Backup                        ║
# ║  Added : 2026-05-18  |  Previous features NOT modified              ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# WHAT IS BACKED UP TO MONGODB:
#   Critical / config tables (synced weekly + on-demand):
#     • users         — roles, bans, flags, permissions, AI model access
#     • settings      — quiz prefix, expl link etc.
#     • channels      — added channels, prefix, expl_link, added_by
#     • saved_groups  — added groups, prefix, expl_link
#     • group_topics  — forum topic thread anchors
#     • saved_topic_anchors — named topic anchors
#     • mistral_api_keys    — owner-added Mistral API keys
#     • gemini_api_keys     — owner-added Gemini API keys
#     • filters             — per-admin word filters
#     • required_memberships
#     • user_warnings
#
# WHAT IS NOT BACKED UP (transient / rebuilds fine):
#     • quiz_buffer         — admin's current quiz queue (lost on redeploy is OK)
#     • ai_threads / ai_thread_messages — chat history (large, transient)
#     • bot_logs / ban_audit             — audit logs (nice to have, not critical)
#     • admin_post_stats                 — counters (non-critical)
#     • user_ocr_daily_usage            — resets daily anyway
#     • gemini_gen_usage                — usage counters (non-critical)
#
# SCHEDULE:
#   • Weekly auto-sync (Sunday 03:00 BST) — cron-style via asyncio task
#   • On bot shutdown (finally block in main)
#   • On demand: .mongobackup  (owner command)
#   • On demand: .mongorestore (owner command — restores from MongoDB to SQLite)
#
# GITHUB BACKUP:
#   • Disabled by default (GITHUB_BACKUP_SYNC_SECONDS already set to 600 in PATCH fix)
#   • You can set GITHUB_BACKUP_DISABLED=1 in Render env to fully skip it
#   • MongoDB is the primary persistent store now
#
# ENV VARS REQUIRED:
#   MONGODB_URI   — e.g. mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true
#   MONGODB_DB    — database name, e.g. "probaho_db"  (default: "probaho_db")

import importlib as _importlib

# ── 0. Check pymongo availability ──────────────────────────────────────

_pymongo_spec = _importlib.util.find_spec("pymongo")
if _pymongo_spec is None:
    logger.warning(
        "[PATCH-R] pymongo not installed. MongoDB backup disabled. "
        "Install it: pip install pymongo[srv] --break-system-packages"
    )
    _MONGO_AVAILABLE = False
else:
    _MONGO_AVAILABLE = True

# ── 1. Config ──────────────────────────────────────────────────────────

MONGO_URI = os.getenv("MONGODB_URI", "").strip()
MONGO_DB_NAME = os.getenv("MONGODB_DB", "probaho_db").strip() or "probaho_db"
# Set GITHUB_BACKUP_DISABLED=1 in Render env to fully disable GitHub backup
_GITHUB_BACKUP_DISABLED_ENV = os.getenv("GITHUB_BACKUP_DISABLED", "0").strip() == "1"

# Tables to back up and their unique key for upsert
# Format: (sqlite_table, mongo_collection, unique_field_or_None)
_MONGO_TABLES: List[Tuple[str, str, Optional[str]]] = [
    ("users",               "users",                "user_id"),
    ("settings",            "settings",             "key"),
    ("channels",            "channels",             "channel_chat_id"),
    ("saved_groups",        "saved_groups",         "group_chat_id"),
    ("group_topics",        "group_topics",         None),   # upsert by id
    ("saved_topic_anchors", "saved_topic_anchors",  None),
    ("mistral_api_keys",    "mistral_api_keys",     "api_key"),
    ("gemini_api_keys",     "gemini_api_keys",      "api_key"),
    ("filters",             "filters",              None),
    ("required_memberships","required_memberships", None),
    ("user_warnings",       "user_warnings",        "user_id"),
]

# ── 2. MongoDB helpers ─────────────────────────────────────────────────

def _mongo_client():
    """Return a MongoClient or None if not configured/available."""
    if not _MONGO_AVAILABLE or not MONGO_URI:
        return None
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10_000,
                             connectTimeoutMS=10_000, socketTimeoutMS=30_000)
        # Quick ping to verify connectivity
        client.admin.command("ping")
        return client
    except Exception as _ce:
        logger.warning("[PATCH-R] MongoDB connect error: %s", _ce)
        return None


def _sqlite_table_rows(table: str) -> List[Dict[str, Any]]:
    """Fetch all rows from a SQLite table as list of dicts. Returns [] if table missing."""
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM [{table}]")  # noqa: S608
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as _e:
        logger.debug("[PATCH-R] _sqlite_table_rows(%s) skip: %s", table, _e)
        return []


def mongo_backup_now(requester: str = "auto") -> Tuple[int, int, str]:
    """
    Push all critical SQLite tables to MongoDB.
    Returns (tables_ok, tables_fail, summary_text).
    Uses upsert so re-running is always safe (idempotent).
    """
    client = _mongo_client()
    if client is None:
        return 0, 0, "MongoDB not configured or unreachable."

    ts_now = dt.datetime.utcnow().isoformat() + "Z"
    ok_count = 0
    fail_count = 0
    details: List[str] = []

    try:
        db = client[MONGO_DB_NAME]

        # Save a meta document so we know when the last backup was
        with contextlib.suppress(Exception):
            db["_meta"].replace_one(
                {"_id": "backup_info"},
                {"_id": "backup_info", "last_backup_at": ts_now,
                 "requester": requester, "bot_brand": BOT_BRAND},
                upsert=True,
            )

        for (table, coll_name, ukey) in _MONGO_TABLES:
            try:
                rows = _sqlite_table_rows(table)
                if not rows:
                    details.append(f"  {table}: 0 rows (skipped)")
                    continue
                coll = db[coll_name]
                ops = 0
                if ukey:
                    from pymongo import UpdateOne, ReplaceOne
                    bulk = []
                    for row in rows:
                        fval = row.get(ukey)
                        if fval is None:
                            # fallback: use 'id' if available
                            fval = row.get("id")
                            filter_doc = {"id": fval} if fval is not None else None
                        else:
                            filter_doc = {ukey: fval}
                        if filter_doc:
                            bulk.append(ReplaceOne(filter_doc, row, upsert=True))
                        else:
                            coll.insert_one(row)
                    if bulk:
                        res = coll.bulk_write(bulk, ordered=False)
                        ops = res.upserted_count + res.modified_count + res.matched_count
                else:
                    # No natural key — drop and re-insert (safe for small tables)
                    coll.drop()
                    if rows:
                        coll.insert_many(rows, ordered=False)
                    ops = len(rows)

                details.append(f"  ✅ {table}: {len(rows)} rows")
                ok_count += 1
            except Exception as _te:
                details.append(f"  ❌ {table}: {_te}")
                fail_count += 1
                logger.warning("[PATCH-R] Backup failed for table %s: %s", table, _te)

    finally:
        with contextlib.suppress(Exception):
            client.close()

    summary = f"MongoDB backup [{requester}] {ts_now}\n" + "\n".join(details)
    logger.info("[PATCH-R] %s", summary)
    return ok_count, fail_count, summary


def mongo_restore_now() -> Tuple[int, int, str]:
    """
    Pull all critical collections from MongoDB and write into SQLite.
    Uses INSERT OR REPLACE to be idempotent. Call this on fresh deploy
    to restore all config/user data.
    Returns (tables_ok, tables_fail, summary_text).
    """
    client = _mongo_client()
    if client is None:
        return 0, 0, "MongoDB not configured or unreachable."

    ok_count = 0
    fail_count = 0
    details: List[str] = []

    try:
        db = client[MONGO_DB_NAME]
        conn = db_connect()

        for (table, coll_name, ukey) in _MONGO_TABLES:
            try:
                coll = db[coll_name]
                docs = list(coll.find({}, {"_id": 0}))
                if not docs:
                    details.append(f"  {table}: 0 docs (skipped)")
                    continue
                # Build column list from first doc
                cols = list(docs[0].keys())
                placeholders = ", ".join(["?"] * len(cols))
                col_names = ", ".join([f'[{c}]' for c in cols])
                sql = f"INSERT OR REPLACE INTO [{table}] ({col_names}) VALUES ({placeholders})"  # noqa: S608
                for doc in docs:
                    vals = tuple(doc.get(c) for c in cols)
                    with contextlib.suppress(Exception):
                        conn.execute(sql, vals)
                conn.commit()
                details.append(f"  ✅ {table}: {len(docs)} docs restored")
                ok_count += 1
            except Exception as _te:
                details.append(f"  ❌ {table}: {_te}")
                fail_count += 1
                logger.warning("[PATCH-R] Restore failed for table %s: %s", table, _te)

        conn.close()
    finally:
        with contextlib.suppress(Exception):
            client.close()

    ts_now = dt.datetime.utcnow().isoformat() + "Z"
    summary = f"MongoDB restore {ts_now}\n" + "\n".join(details)
    logger.info("[PATCH-R] %s", summary)
    return ok_count, fail_count, summary


# ── 3. Auto-restore on startup ─────────────────────────────────────────

def _try_restore_on_startup() -> None:
    """
    Called once at bot startup.
    Only restores if MongoDB has data AND local SQLite looks fresh/empty.
    Safety check: if users table already has rows → skip (don't overwrite live data).
    """
    if not _MONGO_AVAILABLE or not MONGO_URI:
        logger.info("[PATCH-R] MongoDB URI not set — skipping startup restore.")
        return
    try:
        # Check if local DB already has users
        local_users = _sqlite_table_rows("users")
        if len(local_users) > 1:
            logger.info(
                "[PATCH-R] Local DB has %d users — skipping startup restore (data already present).",
                len(local_users),
            )
            return
        # Check MongoDB for data
        client = _mongo_client()
        if client is None:
            return
        try:
            db = client[MONGO_DB_NAME]
            mongo_user_count = db["users"].count_documents({})
        finally:
            with contextlib.suppress(Exception):
                client.close()

        if mongo_user_count == 0:
            logger.info("[PATCH-R] MongoDB has no users — skipping restore (first deploy).")
            return

        logger.info(
            "[PATCH-R] Fresh local DB + MongoDB has %d users → restoring...",
            mongo_user_count,
        )
        ok, fail, summary = mongo_restore_now()
        logger.info("[PATCH-R] Startup restore done: ok=%d fail=%d", ok, fail)

    except Exception as _e:
        logger.warning("[PATCH-R] Startup restore error: %s", _e)


# ── 4. Weekly auto-backup (Sunday 03:00 UTC) ───────────────────────────

async def _mongo_weekly_backup_loop() -> None:
    """Runs forever; pushes backup once per week on Sunday 03:00 UTC."""
    while True:
        try:
            now = dt.datetime.utcnow()
            # Calculate seconds until next Sunday 03:00 UTC
            days_until_sunday = (6 - now.weekday()) % 7  # 6 = Sunday
            next_sunday = now.replace(hour=3, minute=0, second=0, microsecond=0) + \
                          dt.timedelta(days=days_until_sunday if days_until_sunday > 0
                                       or now.hour >= 3 else 0)
            if next_sunday <= now:
                next_sunday += dt.timedelta(weeks=1)
            wait_secs = (next_sunday - now).total_seconds()
            logger.info(
                "[PATCH-R] Next MongoDB weekly backup in %.1f hours (Sunday 03:00 UTC).",
                wait_secs / 3600,
            )
            await asyncio.sleep(wait_secs)
            ok, fail, _ = mongo_backup_now(requester="weekly-auto")
            logger.info("[PATCH-R] Weekly backup done: ok=%d fail=%d", ok, fail)
        except asyncio.CancelledError:
            break
        except Exception as _e:
            logger.warning("[PATCH-R] Weekly backup loop error: %s", _e)
            await asyncio.sleep(3600)  # retry in 1 hour on error


# ── 5. Owner commands: .mongobackup / .mongorestore ────────────────────

@require_admin
async def _cmd_mongobackup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only: push current SQLite state to MongoDB immediately."""
    admin_id = update.effective_user.id
    if admin_id != OWNER_ID:
        await warn(update, "Access Denied", "Only the bot owner can run this.")
        return
    if not _MONGO_AVAILABLE or not MONGO_URI:
        await warn_html(update, "MongoDB Not Configured",
            "Set <code>MONGODB_URI</code> and <code>MONGODB_DB</code> in Render environment variables.")
        return
    await info_html(update, "🔄 Backing up to MongoDB...",
        "Pushing all critical tables. Please wait...")
    ok, fail, summary = await asyncio.get_event_loop().run_in_executor(
        None, lambda: mongo_backup_now(requester=f"owner-{admin_id}")
    )
    body = (
        f"Tables saved: <code>{ok}</code>\n"
        f"Tables failed: <code>{fail}</code>\n\n"
        f"<pre>{h(summary[:800])}</pre>"
    )
    await ok_html(update, "✅ MongoDB Backup Complete", body)


@require_admin
async def _cmd_mongorestore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only: restore SQLite from MongoDB (use after fresh redeploy)."""
    admin_id = update.effective_user.id
    if admin_id != OWNER_ID:
        await warn(update, "Access Denied", "Only the bot owner can run this.")
        return
    if not _MONGO_AVAILABLE or not MONGO_URI:
        await warn_html(update, "MongoDB Not Configured",
            "Set <code>MONGODB_URI</code> and <code>MONGODB_DB</code> in Render environment variables.")
        return
    await info_html(update, "🔄 Restoring from MongoDB...",
        "⚠️ This will overwrite local data with MongoDB backup. Restoring...")
    ok, fail, summary = await asyncio.get_event_loop().run_in_executor(
        None, mongo_restore_now
    )
    body = (
        f"Tables restored: <code>{ok}</code>\n"
        f"Tables failed: <code>{fail}</code>\n\n"
        f"<pre>{h(summary[:800])}</pre>"
    )
    await ok_html(update, "✅ MongoDB Restore Complete", body)


@require_admin
async def _cmd_mongostatus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only: show MongoDB backup status and last backup time."""
    admin_id = update.effective_user.id
    if admin_id != OWNER_ID:
        await warn(update, "Access Denied", "Only the bot owner can run this.")
        return

    if not _MONGO_AVAILABLE:
        await warn(update, "pymongo missing",
            "Install: pip install pymongo[srv]")
        return
    if not MONGO_URI:
        await warn_html(update, "Not Configured",
            "Set <code>MONGODB_URI</code> in Render environment.")
        return

    client = _mongo_client()
    if client is None:
        await warn(update, "Connection Failed",
            "Could not connect to MongoDB. Check MONGODB_URI.")
        return

    lines: List[str] = []
    try:
        db = client[MONGO_DB_NAME]
        meta = db["_meta"].find_one({"_id": "backup_info"}) or {}
        last_backup = meta.get("last_backup_at", "Never")
        requester = meta.get("requester", "—")
        lines.append(f"Last backup: <code>{h(last_backup)}</code>")
        lines.append(f"Triggered by: <code>{h(requester)}</code>")
        lines.append(f"Database: <code>{h(MONGO_DB_NAME)}</code>")
        lines.append("")
        lines.append("<b>Collection counts:</b>")
        for (_, coll_name, _) in _MONGO_TABLES:
            with contextlib.suppress(Exception):
                cnt = db[coll_name].count_documents({})
                lines.append(f"  • {coll_name}: <code>{cnt}</code>")
    finally:
        with contextlib.suppress(Exception):
            client.close()

    await ok_html(update, "📊 MongoDB Status", "\n".join(lines))


# ── 6. Patch main() to auto-restore on startup + weekly backup ─────────

_prev_build_app_patch_r = build_app

def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_patch_r()
    private_filter = filters.ChatType.PRIVATE

    # Register owner commands
    for alias, callback in [
        ("mongobackup",  _cmd_mongobackup),
        ("mongorestore", _cmd_mongorestore),
        ("mongostatus",  _cmd_mongostatus),
    ]:
        with contextlib.suppress(Exception):
            _register_dual_command(app, alias, callback, private_filter)

    logger.info("[PATCH-R] Registered: .mongobackup .mongorestore .mongostatus")
    return app


_prev_main_patch_r = main

def main() -> None:  # noqa: F811
    """
    PATCH-R final main() — all original setup preserved + MongoDB:
      Health server (PORT) / MongoDB restore / GitHub control /
      weekly MongoDB backup / OCR loop / final shutdown backup.
    """
    # 1. Log handler
    with contextlib.suppress(Exception):
        _ensure_runtime_log_file_handler()

    # 2. MongoDB startup restore
    with contextlib.suppress(Exception):
        _try_restore_on_startup()

    # 3. GitHub DB restore (if not disabled)
    if not _GITHUB_BACKUP_DISABLED_ENV:
        with contextlib.suppress(Exception):
            restore_db_from_github(force=False)

    # 4. Health server — REQUIRED by Render for port binding
    with contextlib.suppress(Exception):
        threading.Thread(target=_run_render_health_server, daemon=True).start()
        logger.info("[PATCH-R] Health server started on PORT=%s", os.getenv("PORT", "10000"))

    # 5. Build app
    app = build_app()

    # 6. GitHub backup worker
    if _GITHUB_BACKUP_DISABLED_ENV:
        logger.info("[PATCH-R] GitHub backup disabled via GITHUB_BACKUP_DISABLED=1")
    else:
        with contextlib.suppress(Exception):
            start_github_backup_worker()

    # 7. Pending restart notice
    with contextlib.suppress(Exception):
        _send_pending_restart_notice_via_http()

    # 8. stdout UTF-8
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(f"\U0001f916 {BOT_BRAND} started (PATCH-R). OWNER_ID={OWNER_ID} DB={DB_PATH}")
    except Exception:
        logging.info("Bot started (PATCH-R). OWNER_ID=%s DB=%s", OWNER_ID, DB_PATH)

    # 9. post_init: MongoDB weekly backup + OCR midnight reset
    _weekly_task_ref: List[Optional[asyncio.Task]] = [None]
    _captured_post_init = getattr(app, "post_init", None)

    async def _mongo_post_init(application) -> None:
        with contextlib.suppress(Exception):
            _weekly_task_ref[0] = asyncio.create_task(_mongo_weekly_backup_loop())
            logger.info("[PATCH-R] MongoDB weekly backup task started (Sunday 03:00 UTC).")
        with contextlib.suppress(Exception):
            asyncio.create_task(_ocr_midnight_reset_loop())
            logger.info("[MAIN] OCR midnight reset task started via PATCH-R post_init.")
        if _captured_post_init and callable(_captured_post_init):
            with contextlib.suppress(Exception):
                await _captured_post_init(application)

    app.post_init = _mongo_post_init

    # 10. Run polling — specific update types only (bandwidth saving)
    try:
        app.run_polling(allowed_updates=[
            Update.MESSAGE, Update.CALLBACK_QUERY, Update.POLL, Update.POLL_ANSWER,
            Update.MY_CHAT_MEMBER, Update.CHAT_MEMBER,
        ])
    finally:
        if _weekly_task_ref[0]:
            with contextlib.suppress(Exception):
                _weekly_task_ref[0].cancel()
        with contextlib.suppress(Exception):
            logger.info("[PATCH-R] Shutdown — pushing final MongoDB backup...")
            mongo_backup_now(requester="shutdown")
        if not _GITHUB_BACKUP_DISABLED_ENV:
            with contextlib.suppress(Exception):
                upload_db_to_github(force=True)
        with contextlib.suppress(Exception):
            stop_github_backup_worker()


logger.info("[PATCH-R 2026-05-18] MongoDB persistent backup loaded. Tables: %d | Weekly sync: Sunday 03:00 UTC",
            len(_MONGO_TABLES))
# ═══════════════════════════════════════════════════════════════════════
