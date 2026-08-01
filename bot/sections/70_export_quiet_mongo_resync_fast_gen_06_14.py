# ──────────────────────────────────────────────────────────────────────────────
# Section 70 (2026-06-14) — Quiet export, MongoDB resync, faster generation.
#
# Additive overlay — does NOT touch working OCR / quiz / AI logic.
#
#   1) Suppress the second "✅ Export Complete / Buffer cleared." follow-up
#      that appears after the CSV file is already delivered. The CSV file
#      caption already says "✅ CSV Export — N questions exported", so the
#      extra message is redundant.
#
#   2) MongoDB ↔ SQLite sync hardening:
#        • On startup, if MongoDB has MORE rows than local SQLite for the
#          users table → automatically pull a full restore. Previously the
#          guard skipped restore whenever local had >1 user, so the bot
#          forgot 67 users after a Render restart.
#        • Manual /mongorestore stays available and now always proceeds.
#        • Backup is unchanged (already upserts — non-destructive).
#
#   3) Faster generation: reduce the outer gen timeout from 420s to a
#      provider-friendly 110s so a stalled Gemini key fails over to the
#      next provider in the cascade quickly instead of blocking the user
#      for 4 minutes.
#
# DO NOT import directly — exec'd in shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx70


# ─── 1) Quiet the duplicate "Export Complete" follow-up ─────────────────────

async def _cmd_done_impl_70(update, context):
    uid = update.effective_user.id if update.effective_user else 0
    chat_id = update.effective_chat.id if update.effective_chat else uid
    if not (buffer_list(uid, limit=1) or []):
        await warn(update, "Buffer Empty", "No questions to export. Use /add or send quizzes first.")
        return
    n = await _send_done_export_62(context, chat_id, uid)
    if n <= 0:
        await warn(update, "Buffer Empty", "No questions to export. Use /add or send quizzes first.")
        return
    buffer_clear(uid)
    # Intentionally no trailing "Export Complete" message — file caption already says it.


async def cb_pba_csv_70(update, context):
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) < 3 or parts[0] != "pba" or parts[1] != "csv":
        return
    token = parts[-1]
    store = _pb_store(context)
    entry = store.get(token)
    if not entry:
        with _cx70.suppress(Exception):
            await q.answer("Expired", show_alert=False)
        raise ApplicationHandlerStop
    uid = int(entry.get("uid") or 0)
    caller = q.from_user.id if q.from_user else 0
    if caller != uid:
        with _cx70.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        raise ApplicationHandlerStop
    chat_id = int(entry.get("chat_id") or (q.message.chat_id if q.message else 0))
    with _cx70.suppress(Exception):
        await q.answer("Exporting…")
    try:
        if not (buffer_list(uid, limit=1) or []):
            with _cx70.suppress(Exception):
                await q.edit_message_text(ui_box_html("Buffer Empty", "Nothing to export.", emoji="📂"), parse_mode=ParseMode.HTML)
            store.pop(token, None)
            raise ApplicationHandlerStop
        await _send_done_export_62(context, chat_id, uid)
        buffer_clear(uid)
        store.pop(token, None)
        with _cx70.suppress(Exception):
            await q.message.delete()
        # No trailing follow-up message — CSV file already shows the count.
    except ApplicationHandlerStop:
        raise
    except Exception as e:
        with _cx70.suppress(Exception):
            db_log("ERROR", "pba_csv_failed_v70", {"user_id": uid, "error": str(e)})
        with _cx70.suppress(Exception):
            await q.answer("CSV failed", show_alert=True)
    raise ApplicationHandlerStop


try:
    cmd_done = require_admin(_cmd_done_impl_70)  # noqa: F811
except Exception:
    cmd_done = _cmd_done_impl_70  # noqa: F811


# ─── 2) MongoDB resync on startup (mongo > local ⇒ restore) ─────────────────

def _try_restore_on_startup() -> None:  # noqa: F811
    """Restore from MongoDB whenever it holds more user rows than the local
    SQLite (e.g. after a Render restart wiped the ephemeral disk)."""
    if not _MONGO_AVAILABLE or not MONGO_URI:
        with _cx70.suppress(Exception):
            logger.info("[PATCH-R/70] MongoDB URI not set — skipping startup restore.")
        return
    try:
        local_users = _sqlite_table_rows("users")
        client = _mongo_client()
        if client is None:
            return
        try:
            db = client[MONGO_DB_NAME]
            mongo_user_count = db["users"].count_documents({})
        finally:
            with _cx70.suppress(Exception):
                client.close()

        if mongo_user_count == 0:
            logger.info("[PATCH-70] MongoDB empty — nothing to restore.")
            return

        if len(local_users) >= mongo_user_count:
            logger.info(
                "[PATCH-70] Local DB (%d users) ≥ MongoDB (%d) — skipping restore.",
                len(local_users), mongo_user_count,
            )
            return

        logger.info(
            "[PATCH-70] Local DB has %d users, MongoDB has %d → restoring full snapshot...",
            len(local_users), mongo_user_count,
        )
        ok, fail, _ = mongo_restore_now()
        logger.info("[PATCH-70] Startup restore done: ok=%d fail=%d", ok, fail)
    except Exception as _e:
        with _cx70.suppress(Exception):
            logger.warning("[PATCH-70] Startup restore error: %s", _e)


# ─── 3) Faster gen timeout so cascade fails over quickly ────────────────────

with _cx70.suppress(Exception):
    _prev_generate_to_buffer_59 = _generate_to_buffer_59

    async def _generate_to_buffer_59(update, context, ocr_ctx, uid, count, mode="std"):  # noqa: F811
        count = max(1, min(500, int(count or 20)))
        globals()["_active_gen_mode_57"] = mode or "std"
        try:
            items = await _run_blocking(
                _role_of(uid), _generate_quizzes_from_ocr_sync,
                ocr_ctx, count, uid, timeout=110,
            )
        except Exception as _ge:
            logger.warning("[PATCH-70] gen primary failed (%s) — retrying once fast.", _ge)
            try:
                items = await _run_blocking(
                    _role_of(uid), _generate_quizzes_from_ocr_sync,
                    ocr_ctx, count, uid, timeout=90,
                )
            except Exception:
                items = []
        finally:
            globals()["_active_gen_mode_57"] = None

        seen = set()
        with _cx70.suppress(Exception):
            seen.update(_gen_seen_for(context, uid, _source_hash_59(ocr_ctx, mode)))
        with _cx70.suppress(Exception):
            for _, it in (buffer_list(uid, limit=99999) or []):
                seen.add(_fp_question(it))
        added = dup = 0
        for raw in items or []:
            try:
                q = str(raw.get("question") or raw.get("questions") or "").strip()
                opts = raw.get("options") if isinstance(raw.get("options"), list) else _opts_59(raw)
                opts = [str(o or "").strip() for o in (opts or []) if str(o or "").strip()][:5]
                ans = int(raw.get("answer", 1) or 1)
                if not q or len(opts) < 2 or not (1 <= ans <= len(opts)):
                    continue
                payload = {"questions": q, "answer": ans,
                           "explanation": str(raw.get("explanation") or "")[:200],
                           "type": 1, "section": 1, "source": f"gen_{mode}"}
                for i in range(5):
                    payload[f"option{i+1}"] = opts[i] if i < len(opts) else ""
                with _cx70.suppress(Exception):
                    payload = _enforce_option_parity(payload)
                fp = _fp_question(payload)
                if fp in seen:
                    dup += 1
                    continue
                if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
                    break
                buffer_add(uid, payload)
                seen.add(fp)
                added += 1
            except Exception:
                continue
        with _cx70.suppress(Exception):
            _gen_seen_for(context, uid, _source_hash_59(ocr_ctx, mode)).update(seen)
        return added, dup


# ─── 4) Re-register `.d` / `/done` with the quiet handler ───────────────────

_prev_build_app_70 = build_app

def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_70()
    with _cx70.suppress(Exception):
        app.add_handler(CallbackQueryHandler(cb_pba_csv_70, pattern=r"^pba:csv:[0-9a-f]+$"), group=-2000)
    with _cx70.suppress(Exception):
        if "_register_dual_command" in globals():
            _register_dual_command(app, "done", cmd_done, filters.ChatType.PRIVATE, group=-2000)
            _register_dual_command(app, "d", cmd_done, filters.ChatType.PRIVATE, group=-2000)
    logger.info("[PATCH-70] Quiet export, mongo resync, fast gen (110s) — active.")
    return app
