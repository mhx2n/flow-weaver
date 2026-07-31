# ──────────────────────────────────────────────────────────────────────────────
# Section: 54_advanced_fixes_user_quiz_06_13
# Fixes:
#   1) Auto-buffer plain text → OFF by default; owner toggles via /autobuf
#   2) Duplicate "Generate from Page" offers → dedupe at source
#   3) "🔁 More Generate" button on offer card (unique MCQs only)
#   4) User-side OCR quiz feature with owner controls (toggle, daily limit,
#      per-user stats). Sends generated quizzes back to user inbox using the
#      global প্রবাহ-style quiz_prefix (or none if cleared).
# DO NOT import directly — exec'd in shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import hashlib
import json as _json
import datetime as _dt


# ============================================================
# 1) Auto-buffer toggle  (default OFF)
# ============================================================

def _autobuf_on() -> bool:
    try:
        return str(get_setting("text_autobuf_on", "0")).strip() in ("1", "on", "true", "yes")
    except Exception:
        return False


_prev_handle_text_54 = handle_text


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not _autobuf_on():
            # Silently skip — do not auto-add plain text to buffer
            return
    except Exception:
        return
    return await _prev_handle_text_54(update, context)


async def cmd_autobuf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        return
    args = [a.lower() for a in (context.args or [])]
    if not args:
        cur = "ON" if _autobuf_on() else "OFF"
        await safe_reply(update, ui_box_text("Text Auto-Buffer", f"Currently: {cur}\nUsage: /autobuf on|off", emoji="📝"))
        return
    val = "1" if args[0] in ("on", "1", "true", "yes") else "0"
    set_setting("text_autobuf_on", val)
    await safe_reply(update, ui_box_text("Text Auto-Buffer", f"Set to: {'ON' if val=='1' else 'OFF'}", emoji="✅"))


# ============================================================
# 2) Dedupe "Generate from Page" offers (50 + 52 collision)
# ============================================================

_OFFER_DEDUPE_KEY = "_offer_dedupe_06_13"


def _offer_dedupe_store(context=None) -> Dict[str, float]:
    # We use a module-level dict keyed by (uid, page, content_hash)
    if not hasattr(_offer_dedupe_store, "_d"):
        _offer_dedupe_store._d = {}
    return _offer_dedupe_store._d


_prev_send_content_page_offer_54 = _send_content_page_offer


async def _send_content_page_offer(context, chat_id: int, uid: int, page_idx: int, text: str):
    try:
        h = hashlib.md5((str(uid) + "|" + str(page_idx) + "|" + (text or "")[:600]).encode("utf-8", "ignore")).hexdigest()
    except Exception:
        h = f"{uid}|{page_idx}"
    store = _offer_dedupe_store()
    now = time.time()
    # prune old (>10 min)
    for k in list(store.keys()):
        if now - store[k] > 600:
            store.pop(k, None)
    if h in store:
        return
    store[h] = now
    return await _prev_send_content_page_offer_54(context, chat_id, uid, page_idx, text)


# ============================================================
# 3) "🔁 More Generate" button — unique MCQs only
# ============================================================

_prev_genq_kb_54 = _genq_kb


def _genq_kb(token: str, counts: Dict[str, int]) -> InlineKeyboardMarkup:
    kb = _prev_genq_kb_54(token, counts)
    rows = list(kb.inline_keyboard)
    # Insert "More Generate" beside Re-estimate
    rows.append([InlineKeyboardButton("🔁 More Generate (+5)", callback_data=f"genq:mo:{token}")])
    return InlineKeyboardMarkup(rows)


def _fp_question(it: Dict[str, Any]) -> str:
    try:
        q = re.sub(r"\s+", " ", str(it.get("questions") or "")).strip().lower()
        return hashlib.md5(q.encode("utf-8", "ignore")).hexdigest()
    except Exception:
        return uuid.uuid4().hex


_prev_cb_genq_54 = cb_genq


async def cb_genq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) != 3 or parts[0] != "genq" or parts[1] != "mo":
        return await _prev_cb_genq_54(update, context)

    token = parts[2]
    store = _genq_store(context)
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
    text = str(entry.get("text") or "")
    page_idx = int(entry.get("page") or 0)
    seen: set = set(entry.get("seen_fp") or set())

    # Append exclusion hint to seed uniqueness
    hint = ""
    if seen:
        hint = "\n\n[Generate NEW unique MCQs only. Do NOT repeat earlier questions. Vary angle, sub-topic, and difficulty.]"
    seed_text = (text + hint)[:6000]

    with contextlib.suppress(Exception):
        await q.answer("Generating more…")
    try:
        items = await _run_blocking(
            _role_of(uid),
            _generate_mcqs_from_content,
            seed_text,
            easy=2, medium=2, hard=1,
            timeout=120,
        )
    except Exception as e:
        db_log("ERROR", "genq_more_failed", {"user_id": uid, "error": str(e)})
        items = []

    added = 0
    for p in items or []:
        fp = _fp_question(p)
        if fp in seen:
            continue
        if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
            break
        pp = dict(p)
        if not explain_mode_on(uid):
            pp["explanation"] = ""
        buffer_add(uid, pp)
        seen.add(fp)
        added += 1
    entry["seen_fp"] = seen
    store[token] = entry
    with contextlib.suppress(Exception):
        await context.bot.send_message(
            chat_id=int(entry.get("chat_id") or q.message.chat_id),
            text=ui_box_html(
                f"More from Page {page_idx}",
                f"Added <code>{added}</code> NEW unique MCQ(s).\nBuffered: <code>{buffer_count(uid)}</code>",
                emoji="🔁",
            ),
            parse_mode=ParseMode.HTML,
        )


# Wrap cb_genq generation paths (go/ge/gm/gh) to remember fingerprints
_prev_cb_genq_track_54 = cb_genq


async def cb_genq(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
    q = update.callback_query
    pre = 0
    uid = 0
    token = None
    try:
        if q and q.from_user:
            uid = int(q.from_user.id)
            pre = int(buffer_count(uid))
            parts = q.data.split(":")
            if len(parts) == 3 and parts[0] == "genq":
                token = parts[2]
    except Exception:
        pass
    await _prev_cb_genq_track_54(update, context)
    # Record fingerprints of newly added items
    try:
        if not token or uid <= 0:
            return
        store = _genq_store(context)
        entry = store.get(token)
        if not entry:
            return
        added_items = []
        try:
            tail = buffer_list(uid, limit=99999) or []
            extra = max(0, len(tail) - pre)
            if extra > 0:
                added_items = [it for _, it in tail[-extra:]]
        except Exception:
            added_items = []
        seen: set = set(entry.get("seen_fp") or set())
        for it in added_items:
            seen.add(_fp_question(it))
        entry["seen_fp"] = seen
        store[token] = entry
    except Exception:
        pass


# ============================================================
# 4) User-side OCR Quiz feature (owner-controlled)
# ============================================================

def _uq_on() -> bool:
    try:
        return str(get_setting("user_quiz_on", "0")).strip() in ("1", "on", "true", "yes")
    except Exception:
        return False


def _uq_daily_limit() -> int:
    try:
        return max(0, int(str(get_setting("user_quiz_daily_limit", "5")).strip() or "5"))
    except Exception:
        return 5


def _uq_today_key() -> str:
    return _dt.datetime.utcnow().strftime("uq_use_%Y%m%d")


def _uq_usage_get() -> Dict[str, int]:
    try:
        raw = get_setting(_uq_today_key(), "")
        if raw:
            d = _json.loads(raw)
            return {str(k): int(v) for k, v in d.items()}
    except Exception:
        pass
    return {}


def _uq_usage_inc(uid: int, n: int = 1) -> int:
    d = _uq_usage_get()
    cur = int(d.get(str(uid), 0)) + n
    d[str(uid)] = cur
    try:
        set_setting(_uq_today_key(), _json.dumps(d))
    except Exception:
        pass
    return cur


def _uq_user_blocked(uid: int) -> bool:
    try:
        raw = get_setting("user_quiz_blocked", "")
        if not raw:
            return False
        return str(uid) in set(s.strip() for s in raw.split(",") if s.strip())
    except Exception:
        return False


async def cmd_userquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        return
    args = [a.lower() for a in (context.args or [])]
    if not args:
        cur = "ON" if _uq_on() else "OFF"
        lim = _uq_daily_limit()
        await safe_reply(update, ui_box_text(
            "User Quiz Feature",
            f"Status: {cur}\nDaily limit per user: {lim}\n\n"
            "Commands:\n"
            "/userquiz on|off — toggle\n"
            "/userquizlimit N — set per-user daily limit\n"
            "/userquizstats — today's usage\n"
            "/userquizblock <uid> — block a user\n"
            "/userquizunblock <uid> — unblock a user",
            emoji="🧪",
        ))
        return
    val = "1" if args[0] in ("on", "1", "true", "yes") else "0"
    set_setting("user_quiz_on", val)
    await safe_reply(update, ui_box_text("User Quiz", f"Set to: {'ON' if val=='1' else 'OFF'}", emoji="✅"))


async def cmd_userquizlimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        return
    if not context.args:
        await safe_reply(update, ui_box_text("User Quiz Limit", f"Current: {_uq_daily_limit()}\nUsage: /userquizlimit N", emoji="⚙️"))
        return
    try:
        n = max(0, int(context.args[0]))
    except Exception:
        await safe_reply(update, ui_box_text("Invalid", "Provide a number.", emoji="⚠️"))
        return
    set_setting("user_quiz_daily_limit", str(n))
    await safe_reply(update, ui_box_text("User Quiz Limit", f"Updated to {n}/day", emoji="✅"))


async def cmd_userquizstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        return
    d = _uq_usage_get()
    if not d:
        await safe_reply(update, ui_box_text("User Quiz Stats", "No usage today.", emoji="📊"))
        return
    rows = sorted(d.items(), key=lambda x: -int(x[1]))[:30]
    body = "\n".join(f"• <code>{h(k)}</code> — {v}" for k, v in rows)
    await safe_reply_html(update, ui_box_html("User Quiz Stats (today)", body, emoji="📊"))


async def cmd_userquizblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid) or not context.args:
        return
    target = context.args[0].strip()
    raw = get_setting("user_quiz_blocked", "")
    s = set(x.strip() for x in raw.split(",") if x.strip())
    s.add(target)
    set_setting("user_quiz_blocked", ",".join(sorted(s)))
    await safe_reply(update, ui_box_text("Blocked", f"User {target} blocked from user-quiz.", emoji="🚫"))


async def cmd_userquizunblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid) or not context.args:
        return
    target = context.args[0].strip()
    raw = get_setting("user_quiz_blocked", "")
    s = set(x.strip() for x in raw.split(",") if x.strip())
    s.discard(target)
    set_setting("user_quiz_blocked", ",".join(sorted(s)))
    await safe_reply(update, ui_box_text("Unblocked", f"User {target} unblocked.", emoji="✅"))


# Safe HTML reply fallback
async def safe_reply_html(update, text):
    with contextlib.suppress(Exception):
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# ============================================================
# 5) Register commands & callback patterns
# ============================================================

_prev_build_app_54 = build_app


def build_app() -> Application:
    app = _prev_build_app_54()
    with contextlib.suppress(Exception):
        app.add_handler(CommandHandler("autobuf", cmd_autobuf, prefixes=("/", ".")))
    with contextlib.suppress(Exception):
        app.add_handler(CommandHandler("userquiz", cmd_userquiz, prefixes=("/", ".")))
    with contextlib.suppress(Exception):
        app.add_handler(CommandHandler("userquizlimit", cmd_userquizlimit, prefixes=("/", ".")))
    with contextlib.suppress(Exception):
        app.add_handler(CommandHandler("userquizstats", cmd_userquizstats, prefixes=("/", ".")))
    with contextlib.suppress(Exception):
        app.add_handler(CommandHandler("userquizblock", cmd_userquizblock, prefixes=("/", ".")))
    with contextlib.suppress(Exception):
        app.add_handler(CommandHandler("userquizunblock", cmd_userquizunblock, prefixes=("/", ".")))
    # Re-register cb_genq with extended pattern including 'mo'
    with contextlib.suppress(Exception):
        app.add_handler(CallbackQueryHandler(cb_genq, pattern=r"^genq:(go|re|no|ge|gm|gh|mo):[0-9a-f]+$"))
    # Re-register handle_text so the auto-buffer toggle takes effect
    with contextlib.suppress(Exception):
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    return app

# ===== END ADVANCED FIXES + USER QUIZ =====