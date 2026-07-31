# ──────────────────────────────────────────────────────────────────────────────
# Section: 25_short_admin_popup_safer_long_msg
# Original lines: 12751..12951
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===========================
# FINAL PATCH: short admin popup + safer long-message handling
# ===========================

_FINAL_TUTORIAL_ALERT = (
    "চালু: /probaho_on বা .probaho_on\n"
    "বন্ধ: /probaho_off বা .probaho_off\n"
    "ব্যবহার: /sh/.sh | রেঞ্জ: /porag বা .porag"
)


def _clip_plain(s: str, limit: int = 3500) -> str:
    s = str(s or "")
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)] + "…"


async def safe_reply(update: Update, text: str) -> None:
    if not update.message:
        return
    parts = list(chunk_text(str(text or ""), 3000)) or [""]
    for part in parts:
        part = _clip_plain(part, 3000)
        try:
            await update.message.reply_text(
                part,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except TelegramError:
            with contextlib.suppress(Exception):
                await update.message.reply_text(
                    _clip_plain(re.sub(r"<[^>]+>", "", part), 3000),
                    disable_web_page_preview=True,
                )


async def safe_send_text(bot, chat_id: int, text: str, protect: bool = False, **kwargs) -> None:
    parts = list(chunk_text(str(text or ""), 3000)) or [""]
    for part in parts:
        clipped = _clip_plain(part, 3000)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=clipped,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                protect_content=protect,
                **kwargs,
            )
        except RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.2)
            with contextlib.suppress(Exception):
                await bot.send_message(
                    chat_id=chat_id,
                    text=clipped,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    protect_content=protect,
                    **kwargs,
                )
        except TelegramError:
            with contextlib.suppress(Exception):
                await bot.send_message(
                    chat_id=chat_id,
                    text=_clip_plain(re.sub(r"<[^>]+>", "", clipped), 3000),
                    disable_web_page_preview=True,
                    protect_content=protect,
                    **kwargs,
                )
        except Exception:
            pass


@require_owner
async def cmd_ownerstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: compact health stats with short error list."""
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM users")
    total_users = int(cur.fetchone()["c"] or 0)

    cur.execute("SELECT COUNT(*) AS c FROM users WHERE role IN ('OWNER','ADMIN')")
    staff_count = int(cur.fetchone()["c"] or 0)

    since_dt = dt.datetime.now(timezone.utc) - dt.timedelta(hours=24)
    since_iso = since_dt.replace(microsecond=0).isoformat()
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE last_seen_at IS NOT NULL AND last_seen_at >= ?", (since_iso,))
    active_24h = int(cur.fetchone()["c"] or 0)

    cur.execute("SELECT COUNT(*) AS c FROM bot_logs WHERE level='ERROR' AND created_at >= ?", (since_iso,))
    err_24h = int(cur.fetchone()["c"] or 0)

    cur.execute("SELECT created_at, event, meta_json FROM bot_logs WHERE level='ERROR' ORDER BY id DESC LIMIT 3")
    last_errors = cur.fetchall()
    conn.close()

    db_mb = 0.0
    try:
        if os.path.exists(DB_PATH):
            db_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    except Exception:
        db_mb = 0.0

    rss_mb = process_rss_mb()

    lines = [
        "<b>👑 Owner Dashboard</b>",
        f"⏱ Uptime: <code>{h(fmt_uptime())}</code>",
        "",
        f"👥 Total Users: <b>{h(total_users)}</b>",
        f"🛠 (Owner+Admin): <b>{h(staff_count)}</b>",
        f"✅ Active (24h): <b>{h(active_24h)}</b>",
        "",
        f"💾 DB Size: <code>{h(fmt_mb(db_mb))}</code>",
        f"🧠 RAM (RSS): <code>{h(fmt_mb(rss_mb))}</code>",
        "",
        f"🔴 Error (24h): <b>{h(err_24h)}</b>",
    ]

    if last_errors:
        lines.append("")
        lines.append("<b>last 3 Error:</b>")
        for r in last_errors:
            ts = str(r["created_at"] or "")[-8:]
            ev = str(r["event"] or "")[:26]
            meta = ""
            try:
                meta_obj = json.loads(r["meta_json"] or "{}")
                meta = str(meta_obj.get("error") or "")
            except Exception:
                meta = ""
            meta = h(meta.replace("\n", " ")[:40]) if meta else ""
            if meta:
                lines.append(f"• <code>{h(ts)}</code> — {h(ev)} — <i>{meta}</i>")
            else:
                lines.append(f"• <code>{h(ts)}</code> — {h(ev)}")

    msg = "\n".join(lines)
    await safe_reply(update, msg)


async def on_tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.message or not q.message.chat:
        return
    uid = q.from_user.id if q.from_user else 0
    if not await _is_group_admin_user(context, q.message.chat.id, uid):
        with contextlib.suppress(Exception):
            await q.answer("Only group admins can view this.", show_alert=True, cache_time=0)
        return
    try:
        await q.answer(_FINAL_TUTORIAL_ALERT[:180], show_alert=True, cache_time=0)
    except TelegramError:
        with contextlib.suppress(Exception):
            await q.answer("চালু/বন্ধ: /probaho_on /probaho_off\nব্যবহার: /sh/.sh\nরেঞ্জ: /porag বা .porag", show_alert=True, cache_time=0)


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = getattr(update, 'my_chat_member', None)
    if not cmu:
        return
    try:
        old_status = cmu.old_chat_member.status
        new_status = cmu.new_chat_member.status
        chat = cmu.chat
        actor = cmu.from_user
    except Exception:
        return

    if new_status in ("member", "administrator") and old_status in ("left", "kicked") and chat.type in ("group", "supergroup"):
        actor_name = actor.first_name if actor else "Admin"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📘 Tutorial", callback_data="tutorial:show")]])
        text = (
            f"ধন্যবাদ {h(actor_name)}, {h(BOT_BRAND)} group-এ add করার জন্য।\n"
            "বিস্তারিত নিয়ম দেখতে নিচের <b>Tutorial</b> বাটনে চাপুন।"
        )
        with contextlib.suppress(Exception):
            msg = await context.bot.send_message(
                chat_id=chat.id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            asyncio.create_task(_auto_delete_after(context.bot, chat.id, [msg.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err_text = str(context.error or "")
    err_l = err_text.lower()
    if "message_too_long" in err_l or "message is too long" in err_l:
        logger.warning("Suppressed long-message error: %s", err_text[:200])
        db_log("WARN", "message_too_long", {"error": err_text[:120]})
        return
    logger.exception("Unhandled error: %s", context.error)
    db_log("ERROR", "unhandled_exception", {"error": err_text[:180]})


