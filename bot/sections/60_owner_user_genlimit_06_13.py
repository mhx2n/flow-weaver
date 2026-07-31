# ──────────────────────────────────────────────────────────────────────────────
# Section 60 (2026-06-13) — Owner-editable per-user .gen quiz daily limit.
#
# Adds ONLY this feature (everything else stays exactly as before):
#   • Daily counter of MCQs generated via .gen for each user.
#   • Owner commands (work as /cmd, .cmd):
#       .setgenlimit <N>                   -> set GLOBAL default per-day limit
#       .setgenlimit <user_id> <N>         -> set custom per-day limit for user
#       .getgenlimit [user_id]             -> show current limit + today's usage
#       .resetgenlimit <user_id>           -> remove custom limit for that user
#   • Owner & admins are exempt from the limit.
#
# The original .gen / picker / OCR flow from section 59 is untouched.
# ──────────────────────────────────────────────────────────────────────────────

import re as _re60
import datetime as _dt60

_GEN_LIMIT_GLOBAL_KEY_60 = "gen_daily_limit_global"
_GEN_LIMIT_DEFAULT_60 = 10


def _gen_limit_user_key_60(uid: int) -> str:
    return f"gen_daily_limit_user_{int(uid)}"

def _gen_used_key_60(uid: int, ymd: str) -> str:
    return f"gen_daily_used_{int(uid)}_{ymd}"

def _today_ymd_60() -> str:
    return _dt60.datetime.utcnow().strftime("%Y%m%d")


def _get_global_gen_limit_60() -> int:
    try:
        raw = (get_setting(_GEN_LIMIT_GLOBAL_KEY_60, "") or "").strip()
        if raw:
            return max(1, min(int(raw), 10000))
    except Exception:
        pass
    return _GEN_LIMIT_DEFAULT_60

def _get_user_gen_limit_60(uid: int) -> int:
    try:
        raw = (get_setting(_gen_limit_user_key_60(uid), "") or "").strip()
        if raw:
            return max(1, min(int(raw), 10000))
    except Exception:
        pass
    return _get_global_gen_limit_60()

def _get_user_gen_used_60(uid: int) -> int:
    try:
        raw = (get_setting(_gen_used_key_60(uid, _today_ymd_60()), "") or "").strip()
        return int(raw) if raw else 0
    except Exception:
        return 0

def _add_user_gen_used_60(uid: int, n: int) -> None:
    if n <= 0:
        return
    try:
        cur = _get_user_gen_used_60(uid)
        set_setting(_gen_used_key_60(uid, _today_ymd_60()), str(cur + int(n)))
    except Exception:
        pass

def _is_staff_60(uid: int) -> bool:
    try:
        if _is_owner_id(uid):
            return True
    except Exception:
        pass
    try:
        if is_admin(uid):
            return True
    except Exception:
        pass
    return False


# ─── Wrap _generate_to_buffer_59 to enforce daily limit ─────────────────────
try:
    _prev_generate_to_buffer_60 = _generate_to_buffer_59  # type: ignore[name-defined]
except Exception:
    _prev_generate_to_buffer_60 = None

async def _generate_to_buffer_59(update, context, ocr_ctx, uid, count, mode="std"):  # noqa: F811
    try:
        uid_i = int(uid)
    except Exception:
        uid_i = 0
    requested = max(0, int(count or 0))
    if uid_i and not _is_staff_60(uid_i):
        limit = _get_user_gen_limit_60(uid_i)
        used = _get_user_gen_used_60(uid_i)
        remaining = max(0, limit - used)
        if remaining <= 0:
            with contextlib.suppress(Exception):
                await update.effective_message.reply_text(
                    ui_box_html(
                        "Daily Limit Reached",
                        f"আজকের .gen লিমিট শেষ।\nLimit: <b>{limit}</b> / day\nব্যবহৃত: <b>{used}</b>\nআগামীকাল আবার চেষ্টা করো।",
                        emoji="🚫",
                    ),
                    parse_mode=ParseMode.HTML,
                )
            return 0, 0
        if requested > remaining:
            with contextlib.suppress(Exception):
                await update.effective_message.reply_text(
                    ui_box_html(
                        "Limit Adjusted",
                        f"আজ আর <b>{remaining}</b> টি বানানো যাবে (Limit: {limit}/day, used: {used}).",
                        emoji="ℹ️",
                    ),
                    parse_mode=ParseMode.HTML,
                )
            requested = remaining
    if _prev_generate_to_buffer_60 is None:
        return 0, 0
    added, dup = await _prev_generate_to_buffer_60(update, context, ocr_ctx, uid, requested, mode)
    if uid_i and not _is_staff_60(uid_i):
        _add_user_gen_used_60(uid_i, int(added or 0))
    return added, dup


# ─── Owner commands ─────────────────────────────────────────────────────────

async def cmd_setgenlimit_60(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_owner_id(uid):
        with contextlib.suppress(Exception):
            await update.effective_message.reply_text("Owner only.")
        return
    args = list(context.args or [])
    if not args:
        with contextlib.suppress(Exception):
            await update.effective_message.reply_text(
                "Usage:\n.setgenlimit <N>                  → global default\n"
                ".setgenlimit <user_id> <N>          → per-user override"
            )
        return
    try:
        if len(args) == 1:
            n = max(1, min(int(args[0]), 10000))
            set_setting(_GEN_LIMIT_GLOBAL_KEY_60, str(n))
            with contextlib.suppress(Exception):
                await update.effective_message.reply_text(
                    f"✅ Global daily .gen limit: <b>{n}</b>", parse_mode=ParseMode.HTML
                )
        else:
            target = int(args[0]); n = max(1, min(int(args[1]), 10000))
            set_setting(_gen_limit_user_key_60(target), str(n))
            with contextlib.suppress(Exception):
                await update.effective_message.reply_text(
                    f"✅ Daily .gen limit set for <code>{target}</code>: <b>{n}</b>",
                    parse_mode=ParseMode.HTML,
                )
    except Exception:
        with contextlib.suppress(Exception):
            await update.effective_message.reply_text("Invalid arguments.")


async def cmd_getgenlimit_60(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_owner_id(uid):
        return
    args = list(context.args or [])
    if not args:
        with contextlib.suppress(Exception):
            await update.effective_message.reply_text(
                f"Global daily .gen limit: <b>{_get_global_gen_limit_60()}</b>",
                parse_mode=ParseMode.HTML,
            )
        return
    try:
        target = int(args[0])
    except Exception:
        return
    lim = _get_user_gen_limit_60(target)
    used = _get_user_gen_used_60(target)
    custom = (get_setting(_gen_limit_user_key_60(target), "") or "").strip()
    tag = "custom" if custom else "global default"
    with contextlib.suppress(Exception):
        await update.effective_message.reply_text(
            f"user_id: <code>{target}</code>\nLimit: <b>{lim}</b> ({tag})\nUsed today: <b>{used}</b>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_resetgenlimit_60(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_owner_id(uid):
        return
    args = list(context.args or [])
    if not args:
        with contextlib.suppress(Exception):
            await update.effective_message.reply_text("Usage: .resetgenlimit <user_id>")
        return
    try:
        target = int(args[0])
    except Exception:
        return
    try:
        set_setting(_gen_limit_user_key_60(target), "")
    except Exception:
        pass
    with contextlib.suppress(Exception):
        await update.effective_message.reply_text(
            f"✅ Custom limit cleared for <code>{target}</code> — now using global default.",
            parse_mode=ParseMode.HTML,
        )


_DOT_RE_60 = _re60.compile(r"^\.(setgenlimit|getgenlimit|resetgenlimit)\b\s*(.*)$", _re60.IGNORECASE)

async def _dot_dispatch_60(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text:
        return
    m = _DOT_RE_60.match(msg.text.strip())
    if not m:
        return
    cmd = m.group(1).lower()
    rest = (m.group(2) or "").strip()
    context.args = rest.split() if rest else []
    if cmd == "setgenlimit":
        await cmd_setgenlimit_60(update, context)
    elif cmd == "getgenlimit":
        await cmd_getgenlimit_60(update, context)
    elif cmd == "resetgenlimit":
        await cmd_resetgenlimit_60(update, context)


_prev_build_app_60 = build_app

def build_app() -> Application:
    app = _prev_build_app_60()
    with contextlib.suppress(Exception):
        app.add_handler(CommandHandler("setgenlimit", cmd_setgenlimit_60))
        app.add_handler(CommandHandler("getgenlimit", cmd_getgenlimit_60))
        app.add_handler(CommandHandler("resetgenlimit", cmd_resetgenlimit_60))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _dot_dispatch_60), group=-400)
    return app

# ===== END SECTION 60 =====