# ──────────────────────────────────────────────────────────────────────────────
# Section: 53_post_buffer_action_card_06_13
# After OCR→generation adds MCQs to buffer, show an action card with buttons:
#   📤 Post to Channel (প্রবাহ tag) / 🎯 Choose channel / 📂 Export CSV
# DO NOT import directly — exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────


_PB_ACTION_STORE_KEY = "_pb_action_store_06_13"


def _pb_store(context) -> Dict[str, Any]:
    bd = context.application.bot_data
    if _PB_ACTION_STORE_KEY not in bd:
        bd[_PB_ACTION_STORE_KEY] = {}
    return bd[_PB_ACTION_STORE_KEY]


def _pb_action_kb(token: str, channels: List[Any]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    # Top: quick channel pick (max 6)
    quick: List[InlineKeyboardButton] = []
    for ch in (channels or [])[:6]:
        title = (getattr(ch, "title", None) or str(getattr(ch, "channel_chat_id", "?")))[:18]
        quick.append(InlineKeyboardButton(f"📤 {title}", callback_data=f"pba:post:{ch.id}:{token}"))
    # 2 per row
    while quick:
        rows.append(quick[:2])
        quick = quick[2:]
    if len(channels or []) > 6:
        rows.append([InlineKeyboardButton("🎯 More channels…", callback_data=f"pba:list:{token}")])
    rows.append([
        InlineKeyboardButton("📂 Export CSV", callback_data=f"pba:csv:{token}"),
        InlineKeyboardButton("🧹 Clear Buffer", callback_data=f"pba:clr:{token}"),
    ])
    rows.append([InlineKeyboardButton("✖ Close", callback_data=f"pba:close:{token}")])
    return InlineKeyboardMarkup(rows)


async def _send_pb_action_card(context, chat_id: int, uid: int, added: int):
    try:
        channels = channel_list_for_user(uid) or []
    except Exception:
        channels = []
    token = uuid.uuid4().hex[:10]
    _pb_store(context)[token] = {"uid": uid, "chat_id": chat_id, "ts": time.time()}
    total_buf = 0
    try:
        total_buf = buffer_count(uid)
    except Exception:
        pass
    body = (
        f"✅ Added <code>{added}</code> MCQ(s) to your buffer.\n"
        f"Buffered total: <code>{total_buf}</code>\n\n"
        "Choose what to do next:"
    )
    if not channels:
        body += "\n\n<i>Tip: add a channel via /addchannel to enable quick post.</i>"
    with contextlib.suppress(Exception):
        await context.bot.send_message(
            chat_id=chat_id,
            text=ui_box_html("Quiz Actions", body, emoji="🎯"),
            parse_mode=ParseMode.HTML,
            reply_markup=_pb_action_kb(token, channels),
            disable_web_page_preview=True,
        )


async def cb_pba(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) < 3 or parts[0] != "pba":
        return
    action = parts[1]
    token = parts[-1]
    store = _pb_store(context)
    entry = store.get(token)
    if not entry:
        with contextlib.suppress(Exception):
            await q.answer("Expired", show_alert=False)
        return
    uid = int(entry.get("uid") or 0)
    caller = q.from_user.id if q.from_user else 0
    if caller != uid:
        with contextlib.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        return
    chat_id = int(entry.get("chat_id") or q.message.chat_id)

    if action == "close":
        store.pop(token, None)
        with contextlib.suppress(Exception):
            await q.edit_message_reply_markup(reply_markup=None)
        with contextlib.suppress(Exception):
            await q.answer("Closed")
        return

    if action == "clr":
        with contextlib.suppress(Exception):
            buffer_clear(uid)
        store.pop(token, None)
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                ui_box_html("Buffer Cleared", "All buffered quizzes removed.", emoji="🧹"),
                parse_mode=ParseMode.HTML,
            )
        with contextlib.suppress(Exception):
            await q.answer("Cleared")
        return

    if action == "csv":
        with contextlib.suppress(Exception):
            await q.answer("Exporting CSV…")
        try:
            items = buffer_list(uid, limit=99999) or []
            if not items:
                with contextlib.suppress(Exception):
                    await q.edit_message_text(
                        ui_box_html("Buffer Empty", "Nothing to export.", emoji="📂"),
                        parse_mode=ParseMode.HTML,
                    )
                return
            rows = []
            for _, it in items:
                rows.append({
                    "questions": it.get("questions", ""),
                    "option1": it.get("option1", ""),
                    "option2": it.get("option2", ""),
                    "option3": it.get("option3", ""),
                    "option4": it.get("option4", ""),
                    "option5": it.get("option5", ""),
                    "answer": it.get("answer", 0),
                    "explanation": it.get("explanation", ""),
                    "type": it.get("type", 1),
                    "section": it.get("section", 1),
                })
            df = pd.DataFrame(rows)
            with tempfile.NamedTemporaryFile("w+b", suffix=".csv", delete=False) as f:
                path = f.name
            df.to_csv(path, index=False, encoding="utf-8-sig")
            with open(path, "rb") as rf:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=rf,
                    filename=f"probaho_buffer_{int(time.time())}.csv",
                    caption=f"📂 Buffer CSV — {len(rows)} questions",
                )
        except Exception as e:
            db_log("ERROR", "pba_csv_failed", {"user_id": uid, "error": str(e)})
            with contextlib.suppress(Exception):
                await q.answer("CSV failed", show_alert=True)
        return

    if action == "list":
        # show extended channel list (up to 30)
        try:
            channels = channel_list_for_user(uid) or []
        except Exception:
            channels = []
        rows: List[List[InlineKeyboardButton]] = []
        for ch in channels[:30]:
            title = (getattr(ch, "title", None) or str(getattr(ch, "channel_chat_id", "?")))[:24]
            rows.append([InlineKeyboardButton(f"📤 {title}", callback_data=f"pba:post:{ch.id}:{token}")])
        rows.append([InlineKeyboardButton("✖ Close", callback_data=f"pba:close:{token}")])
        with contextlib.suppress(Exception):
            await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
        with contextlib.suppress(Exception):
            await q.answer()
        return

    if action == "post":
        if len(parts) < 4:
            with contextlib.suppress(Exception):
                await q.answer("Bad data")
            return
        try:
            cid = int(parts[2])
        except Exception:
            with contextlib.suppress(Exception):
                await q.answer("Bad channel")
            return
        ch = None
        try:
            ch = channel_get_by_id_for_user(uid, cid)
        except Exception:
            pass
        if not ch:
            with contextlib.suppress(Exception):
                await q.answer("Channel not found", show_alert=True)
            return
        items = buffer_list(uid, limit=MAX_BUFFERED_QUESTIONS) or []
        if not items:
            with contextlib.suppress(Exception):
                await q.answer("Buffer empty", show_alert=True)
            return
        with contextlib.suppress(Exception):
            await q.answer(f"Posting {len(items)}…")
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                ui_box_html("Posting to Channel",
                            f"<b>{h(ch.title)}</b>\nPosting <code>{len(items)}</code> quiz(es)…",
                            emoji="📤"),
                parse_mode=ParseMode.HTML,
            )
        target_chat_id = ch.channel_chat_id
        # Resolve topic anchor if present
        _reply_kw: Dict[str, Any] = {}
        try:
            _anchor_chat, _anchor_msg = _get_topic_anchor(uid)
            if _anchor_msg:
                if _anchor_chat == target_chat_id:
                    _reply_kw = _make_reply_params(_anchor_msg)
                else:
                    _reply_kw = _make_reply_params(_anchor_msg, chat_id=_anchor_chat)
        except Exception:
            _reply_kw = {}

        posted = 0
        failed = 0
        for _, it in items:
            try:
                opts: List[str] = []
                for k in ("option1", "option2", "option3", "option4", "option5"):
                    v = str(it.get(k) or "").strip()
                    if v:
                        opts.append(v)
                ans = int(it.get("answer", 0) or 0)
                if not (1 <= ans <= len(opts)):
                    failed += 1
                    continue
                qtext = str(it.get("questions") or "").strip()
                # Channel-specific prefix only when set; no forced "প্রবাহ"
                ch_prefix = (getattr(ch, "prefix", "") or "").strip()
                if ch_prefix and not qtext.startswith(ch_prefix):
                    qtext = f"{ch_prefix}\n{qtext}"
                expl = ""
                if explain_mode_on(uid):
                    expl = _trim_expl_for_poll(str(it.get("explanation") or ""))
                kw: Dict[str, Any] = dict(
                    chat_id=target_chat_id,
                    question=qtext[:300],
                    options=opts[:10],
                    type=Poll.QUIZ,
                    correct_option_id=ans - 1,
                    is_anonymous=True,
                    explanation=expl if expl else None,
                    explanation_parse_mode=ParseMode.HTML if expl else None,
                )
                if _reply_kw:
                    kw.update(_reply_kw)
                await context.bot.send_poll(**kw)
                posted += 1
                await asyncio.sleep(2.0)
            except RetryAfter as ra:
                await asyncio.sleep(float(getattr(ra, "retry_after", 2)) + 1.0)
            except Exception as e:
                failed += 1
                db_log("WARN", "pba_post_failed", {"user_id": uid, "error": str(e)})
        # Clear buffer after post
        with contextlib.suppress(Exception):
            buffer_clear(uid)
        store.pop(token, None)
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                chat_id=chat_id,
                text=ui_box_html(
                    "✅ Posted",
                    f"Channel: <b>{h(ch.title)}</b>\nPosted: <code>{posted}</code>\nFailed: <code>{failed}</code>\nBuffer cleared.",
                    emoji="📤",
                ),
                parse_mode=ParseMode.HTML,
            )
        return


# ─── Wrap cb_genq so the action card appears after items are buffered ───

_prev_cb_genq_53 = cb_genq


async def cb_genq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    pre_count = 0
    uid = 0
    chat_id = 0
    try:
        if q and q.from_user:
            uid = int(q.from_user.id)
            chat_id = int(q.message.chat_id)
            pre_count = int(buffer_count(uid))
    except Exception:
        pass
    await _prev_cb_genq_53(update, context)
    # Determine if any items were added (post genq:go|ge|gm|gh)
    try:
        if not q or not q.data:
            return
        parts = q.data.split(":")
        action = parts[1] if len(parts) >= 2 else ""
        if action not in ("go", "ge", "gm", "gh"):
            return
        if uid <= 0 or chat_id <= 0:
            return
        post_count = int(buffer_count(uid))
        added = max(0, post_count - pre_count)
        if added <= 0:
            return
        await _send_pb_action_card(context, chat_id, uid, added)
    except Exception as e:
        db_log("WARN", "pba_card_failed", {"error": str(e)})


_prev_build_app_pba_53 = build_app


def build_app() -> Application:
    app = _prev_build_app_pba_53()
    with contextlib.suppress(Exception):
        app.add_handler(CallbackQueryHandler(cb_pba, pattern=r"^pba:(post|csv|clr|list|close):.+$"))
    # Re-register cb_genq with the wrapped version
    with contextlib.suppress(Exception):
        app.add_handler(CallbackQueryHandler(cb_genq, pattern=r"^genq:(go|re|no|ge|gm|gh):[0-9a-f]+$"))
    return app

# ===== END POST-BUFFER ACTION CARD =====