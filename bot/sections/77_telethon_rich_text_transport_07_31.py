# ──────────────────────────────────────────────────────────────────────────────
# Section: 77_telethon_rich_text_transport_07_31
#
# Telegram Rich Messages (Bot API 10.1 layer) — REAL native rendering via
# MTProto (Telethon side-client using the SAME bot token).
#
# Adds:
#   • Native tables, LaTeX math ($…$ / $$…$$), task lists, headings,
#     fenced code, quotes, spoilers — rendered by Telegram itself.
#   • Works everywhere (user + admin + owner, private/group/channel) because
#     it hooks telegram.Bot.send_message / edit_message_text at the transport
#     layer, so every existing call site benefits without being modified.
#   • Absolutely non-breaking: any missing config, any MTProto error, any
#     unsupported case → silent fallback to the original PTB call.
#   • Returned object is PTB-compatible (message_id / chat / delete() /
#     edit_text()), so all existing cleanup + edit logic keeps working.
#
# Env (optional — without them the bot behaves exactly as before):
#   TELEGRAM_API_ID    (or API_ID)
#   TELEGRAM_API_HASH  (or API_HASH)
#   RICH_TEXT=off      → hard-disable
#
# Owner commands: /rich  [on|off|status]   ·   /richdemo
# ──────────────────────────────────────────────────────────────────────────────

import asyncio as _a77
import contextlib as _cx77
import html as _html77
import os as _os77
import re as _re77
import time as _t77
import requests as _requests77


def _log77(msg):
    with _cx77.suppress(Exception):
        logger.info("[RICH-77] %s", msg)  # type: ignore[name-defined]


def _int77(v):
    try:
        return int(str(v).strip())
    except Exception:
        return 0


_API_ID_77 = _int77(_os77.getenv("TELEGRAM_API_ID") or _os77.getenv("API_ID") or 0)
_API_HASH_77 = (_os77.getenv("TELEGRAM_API_HASH") or _os77.getenv("API_HASH") or "").strip()
_RICH_ENV_OFF_77 = (_os77.getenv("RICH_TEXT", "on").strip().lower() in ("0", "off", "false", "no"))

try:
    _BOT_TOKEN_77 = str(BOT_TOKEN or "").strip()  # type: ignore[name-defined]
except Exception:
    _BOT_TOKEN_77 = (_os77.getenv("BOT_TOKEN") or "").strip()


class _RichState77:
    """Runtime state for the MTProto rich transport."""

    def __init__(self):
        # Bot API 10.1 has a first-class sendRichMessage method. It only needs
        # the bot token; API_ID/API_HASH are retained for the MTProto fallback.
        self.enabled = bool(_BOT_TOKEN_77 and not _RICH_ENV_OFF_77)
        self.client = None
        self.lock = _a77.Lock()
        self.fail_streak = 0
        self.cooldown_until = 0.0
        self.sent_ok = 0
        self.sent_fail = 0
        self.last_error = ""
        self.available = None  # None = untested, True/False = tested

    def ready(self):
        return bool(self.enabled and _t77.time() >= self.cooldown_until)

    def note_ok(self):
        self.fail_streak = 0
        self.sent_ok += 1
        self.available = True

    def note_fail(self, err):
        self.sent_fail += 1
        self.fail_streak += 1
        self.last_error = str(err)[:300]
        if self.fail_streak >= 3:
            # Back off for 5 minutes so users never feel added latency.
            self.cooldown_until = _t77.time() + 300.0
            self.fail_streak = 0
            _log77("cooldown 300s after repeated failures: %s" % self.last_error)


_RICH77 = _RichState77()


# ── Telethon import (optional dependency) ─────────────────────────────────────
try:
    from telethon import TelegramClient as _TgClient77, functions as _tfn77, types as _tt77, helpers as _th77
    from telethon.sessions import StringSession as _StrSession77

    _TELETHON_OK_77 = hasattr(_tt77, "InputRichMessageMarkdown")
except Exception as _e:  # telethon missing → transparent no-op
    _TgClient77 = None
    _TELETHON_OK_77 = False
    _log77("telethon unavailable (%s) — rich transport disabled, bot unaffected." % _e)

# Official Bot API 10.1 rich messages do not depend on Telethon. A missing or
# older Telethon installation only disables the secondary MTProto fallback.


async def _get_client_77():
    """Lazily start one shared Telethon bot client on the running loop."""
    if not _RICH77.ready() or _TgClient77 is None:
        return None
    if _RICH77.client is not None and _RICH77.client.is_connected():
        return _RICH77.client
    async with _RICH77.lock:
        if _RICH77.client is not None and _RICH77.client.is_connected():
            return _RICH77.client
        try:
            client = _TgClient77(_StrSession77(), _API_ID_77, _API_HASH_77)
            await _a77.wait_for(client.start(bot_token=_BOT_TOKEN_77), timeout=25.0)
            _RICH77.client = client
            _log77("MTProto rich client connected (native tables/LaTeX/task-lists ON).")
            return client
        except Exception as e:
            _RICH77.client = None
            _RICH77.enabled = False
            _RICH77.available = False
            _RICH77.last_error = str(e)[:300]
            _log77("client start failed → falling back to classic HTML: %s" % e)
            return None


def _peer_77(chat_id):
    """Build an InputPeer without needing an entity cache (bots may use
    access_hash=0 for peers that have interacted with them)."""
    cid = _int77(chat_id)
    if cid == 0:
        return None
    if cid > 0:
        return _tt77.InputPeerUser(user_id=cid, access_hash=0)
    s = str(cid)
    if s.startswith("-100"):
        return _tt77.InputPeerChannel(channel_id=int(s[4:]), access_hash=0)
    return _tt77.InputPeerChat(chat_id=-cid)


def _msg_id_from_updates_77(res):
    with _cx77.suppress(Exception):
        for u in getattr(res, "updates", []) or []:
            mid = getattr(u, "id", None)
            if mid and type(u).__name__ == "UpdateMessageID":
                return int(mid)
        for u in getattr(res, "updates", []) or []:
            m = getattr(u, "message", None)
            if m is not None and getattr(m, "id", None):
                return int(m.id)
    with _cx77.suppress(Exception):
        if getattr(res, "id", None):
            return int(res.id)
    return 0


# ── HTML / Markdown helpers ───────────────────────────────────────────────────
_TAG_RE_77 = _re77.compile(r"<[^>]+>")


def _strip_tags_77(s):
    txt = _TAG_RE_77.sub("", str(s or ""))
    with _cx77.suppress(Exception):
        txt = _html77.unescape(txt)
    return txt


_RICH_MARKERS_77 = (
    _re77.compile(r"^\s{0,3}#{1,6}\s+\S", _re77.M),          # headings
    _re77.compile(r"^\s*\|.*\|\s*$", _re77.M),               # tables
    _re77.compile(r"^\s*[-*+]\s+\[[ xX✓]\]", _re77.M),       # task lists
    _re77.compile(r"```"),                                    # fenced code
    _re77.compile(r"\$\$[\s\S]+?\$\$"),                      # display math
    _re77.compile(r"(?<!\$)\$[^$\n]{2,200}\$(?!\$)"),        # inline math
    _re77.compile(r"\\(frac|sqrt|int|sum|prod|lim|alpha|beta|theta|pi|Delta)\b"),
    _re77.compile(r"^\s*>\s+\S", _re77.M),                   # quotes
    _re77.compile(r"\*\*[^*\n]+\*\*"),                       # bold md
    _re77.compile(r"<(b|i|u|s|code|pre|blockquote|tg-spoiler)\b", _re77.I),
)


def _looks_rich_77(text):
    """Only upgrade content that actually benefits from rich rendering.
    Short progress/status pings stay on the classic fast path so they can
    always be edited/deleted exactly as before."""
    s = str(text or "")
    if len(s.strip()) < 12:
        return False
    for rx in _RICH_MARKERS_77:
        if rx.search(s):
            return True
    return len(s) >= 400 and "\n" in s


def _rich_payload_77(text, parse_mode):
    """Return (rich_message, plain_fallback_text)."""
    s = str(text or "")
    pm = str(parse_mode or "").lower()
    if "html" in pm or _re77.search(r"<(b|i|u|s|a|code|pre|blockquote|tg-spoiler)\b", s, _re77.I):
        return _tt77.InputRichMessageHTML(html=s), _strip_tags_77(s)
    return _tt77.InputRichMessageMarkdown(markdown=s), s


# ── PTB-compatible shim so existing edit/delete logic keeps working ───────────
class _RichSentMessage77:
    __slots__ = ("message_id", "chat_id", "text", "_bot", "date")

    def __init__(self, bot, chat_id, message_id, text):
        self._bot = bot
        self.chat_id = _int77(chat_id)
        self.message_id = _int77(message_id)
        self.text = text
        self.date = None

    # PTB-like attributes used across the codebase
    @property
    def id(self):
        return self.message_id

    @property
    def chat(self):
        class _C:
            pass
        c = _C()
        c.id = self.chat_id
        return c

    @property
    def message_thread_id(self):
        return None

    @property
    def caption(self):
        return None

    async def delete(self, *a, **k):
        with _cx77.suppress(Exception):
            return await self._bot.delete_message(chat_id=self.chat_id, message_id=self.message_id)
        return False

    async def edit_text(self, text, **kwargs):
        kwargs.pop("chat_id", None)
        kwargs.pop("message_id", None)
        return await self._bot.edit_message_text(
            chat_id=self.chat_id, message_id=self.message_id, text=text, **kwargs
        )

    edit_message_text = edit_text

    async def reply_text(self, text, **kwargs):
        return await self._bot.send_message(chat_id=self.chat_id, text=text, **kwargs)

    async def pin(self, *a, **k):
        with _cx77.suppress(Exception):
            return await self._bot.pin_chat_message(chat_id=self.chat_id, message_id=self.message_id)
        return False

    def __bool__(self):
        return bool(self.message_id)


# ── Core senders ──────────────────────────────────────────────────────────────
async def rich_send_77(bot, chat_id, text, *, parse_mode=None, reply_to=None,
                       thread_id=None, silent=False, no_webpage=True):
    """Send a native rich message through Bot API 10.1, then MTProto fallback."""
    rich, plain = _rich_payload_77(text, parse_mode) if _TELETHON_OK_77 else (None, _strip_tags_77(text))
    source = str(text or "")
    pm = str(parse_mode or "").lower()
    rich_body = {"html": source} if ("html" in pm or _re77.search(r"<(b|i|u|s|a|code|pre|blockquote|tg-spoiler)\b", source, _re77.I)) else {"markdown": source}
    payload = {
        "chat_id": chat_id,
        "rich_message": rich_body,
        "disable_notification": bool(silent),
    }
    if thread_id:
        payload["message_thread_id"] = _int77(thread_id)
    if reply_to:
        payload["reply_parameters"] = {"message_id": _int77(reply_to)}

    def _bot_api_send():
        return _requests77.post(
            f"https://api.telegram.org/bot{_BOT_TOKEN_77}/sendRichMessage",
            json=payload,
            timeout=20,
        )

    if _RICH77.ready():
        try:
            response = await _a77.wait_for(_a77.to_thread(_bot_api_send), timeout=22.0)
            data = response.json()
            if response.ok and data.get("ok"):
                mid = _int77((data.get("result") or {}).get("message_id"))
                if mid:
                    _RICH77.note_ok()
                    return _RichSentMessage77(bot, chat_id, mid, text)
            _RICH77.note_fail(f"Bot API {response.status_code}: {str(data)[:240]}")
        except Exception as e:
            _RICH77.note_fail(f"Bot API sendRichMessage: {e}")

    # Compatibility fallback for deployments where Telegram has not exposed
    # Bot API 10.1 yet. This path needs API_ID/API_HASH and a recent Telethon.
    if not (_API_ID_77 and _API_HASH_77 and _TELETHON_OK_77):
        return None
    client = await _get_client_77()
    if client is None:
        return None
    peer = _peer_77(chat_id)
    if peer is None:
        return None
    rich, plain = _rich_payload_77(text, parse_mode)
    plain = (plain or " ")[:4000]
    kw = {}
    if reply_to:
        with _cx77.suppress(Exception):
            kw["reply_to"] = _tt77.InputReplyToMessage(
                reply_to_msg_id=_int77(reply_to),
                top_msg_id=_int77(thread_id) or None,
            )
    elif thread_id:
        with _cx77.suppress(Exception):
            kw["reply_to"] = _tt77.InputReplyToMessage(reply_to_msg_id=_int77(thread_id))
    try:
        res = await _a77.wait_for(
            client(_tfn77.messages.SendMessageRequest(
                peer=peer,
                message=plain,
                random_id=_th77.generate_random_long(),
                rich_message=rich,
                no_webpage=bool(no_webpage),
                silent=bool(silent),
                **kw,
            )),
            timeout=20.0,
        )
    except Exception as e:
        _RICH77.note_fail(e)
        return None
    mid = _msg_id_from_updates_77(res)
    if not mid:
        _RICH77.note_fail("no message id in updates")
        return None
    _RICH77.note_ok()
    return _RichSentMessage77(bot, chat_id, mid, text)


async def rich_edit_77(chat_id, message_id, text, *, parse_mode=None):
    """Edit an existing message into a native rich message. True on success."""
    client = await _get_client_77()
    if client is None:
        return False
    peer = _peer_77(chat_id)
    if peer is None:
        return False
    rich, plain = _rich_payload_77(text, parse_mode)
    try:
        await _a77.wait_for(
            client(_tfn77.messages.EditMessageRequest(
                peer=peer,
                id=_int77(message_id),
                message=(plain or " ")[:4000],
                rich_message=rich,
                no_webpage=True,
            )),
            timeout=20.0,
        )
    except Exception as e:
        _RICH77.note_fail(e)
        return False
    _RICH77.note_ok()
    return True


# ── Transport hooks on telegram.Bot (every call site upgraded at once) ─────────
try:
    from telegram import Bot as _PTBBot77

    _orig_send_77 = _PTBBot77.send_message
    _orig_edit_77 = _PTBBot77.edit_message_text
except Exception:
    _PTBBot77 = None
    _orig_send_77 = None
    _orig_edit_77 = None


def _unsupported_kwargs_77(kwargs):
    """Cases MTProto rich path should not handle → keep classic transport."""
    # Inline keyboards are attached in a second, documented Bot API call after
    # the rich MTProto send/edit succeeds.  Treating reply_markup as unsupported
    # made every final AI answer miss this transport because those answers carry
    # the Verify keyboard.
    for k in ("entities", "link_preview_options"):
        if kwargs.get(k) is not None:
            return True
    return False


async def _attach_markup_77(bot, chat_id, message_id, reply_markup):
    """Attach/replace an inline keyboard without downgrading rich message text."""
    if reply_markup is None or not message_id:
        return True
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
        )
        return True
    except Exception as e:
        # The answer itself is more important than an optional action keyboard.
        # Keep the native rich result and record the non-fatal keyboard failure.
        _log77("rich text sent; keyboard attach failed: %s" % e)
        return False


if _orig_send_77 is not None:

    async def _send_message_rich_77(self, chat_id=None, text=None, *args, **kwargs):
        if chat_id is None:
            chat_id = kwargs.pop("chat_id", None)
        if text is None:
            text = kwargs.pop("text", None)
        try:
            use_rich = (
                _RICH77.ready()
                and not args
                and not _unsupported_kwargs_77(kwargs)
                and _looks_rich_77(text)
            )
        except Exception:
            use_rich = False
        if use_rich:
            with _cx77.suppress(Exception):
                sent = await rich_send_77(
                    self, chat_id, text,
                    parse_mode=kwargs.get("parse_mode"),
                    reply_to=kwargs.get("reply_to_message_id"),
                    thread_id=kwargs.get("message_thread_id"),
                    silent=bool(kwargs.get("disable_notification")),
                )
                if sent:
                    await _attach_markup_77(
                        self, chat_id, sent.message_id, kwargs.get("reply_markup")
                    )
                    return sent
        return await _orig_send_77(self, chat_id, text, *args, **kwargs)

    async def _edit_message_text_rich_77(self, text=None, *args, **kwargs):
        if text is None:
            text = kwargs.pop("text", None)
        chat_id = kwargs.get("chat_id")
        message_id = kwargs.get("message_id")
        try:
            use_rich = (
                _RICH77.ready()
                and not args
                and chat_id is not None
                and message_id is not None
                and kwargs.get("inline_message_id") is None
                and not _unsupported_kwargs_77(kwargs)
                and _looks_rich_77(text)
            )
        except Exception:
            use_rich = False
        if use_rich:
            with _cx77.suppress(Exception):
                ok = await rich_edit_77(chat_id, message_id, text,
                                        parse_mode=kwargs.get("parse_mode"))
                if ok:
                    await _attach_markup_77(
                        self, chat_id, message_id, kwargs.get("reply_markup")
                    )
                    return _RichSentMessage77(self, chat_id, message_id, text)
        return await _orig_edit_77(self, text, *args, **kwargs)

    with _cx77.suppress(Exception):
        _PTBBot77.send_message = _send_message_rich_77
        _PTBBot77.edit_message_text = _edit_message_text_rich_77
        _log77("transport hooks installed on telegram.Bot (send_message / edit_message_text).")


# ── Owner commands: /rich, /richdemo ──────────────────────────────────────────
def _is_owner_77(uid):
    with _cx77.suppress(Exception):
        return bool(is_owner(uid))  # type: ignore[name-defined]
    with _cx77.suppress(Exception):
        return _int77(uid) in set(OWNER_IDS)  # type: ignore[name-defined]
    return False


_RICH_DEMO_77 = """# Rich Text — Live Check

**Native Telegram rendering** is active for tables, math, code and task lists.

## Table

| Feature | Status |
|:--------|:------:|
| Tables | ✅ |
| LaTeX math | ✅ |
| Task lists | ✅ |

## Math

Inline: $x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$

$$\\int_{0}^{\\infty} e^{-x^2}\\,dx = \\frac{\\sqrt{\\pi}}{2}$$

## Task list

- [x] MTProto transport
- [x] Math rendering
- [ ] Nothing left

> Everything else in the bot works exactly as before.
"""


async def cmd_rich_77(update, context):
    m = getattr(update, "effective_message", None)
    u = getattr(update, "effective_user", None)
    if m is None or u is None or not _is_owner_77(u.id):
        return
    arg = (context.args[0].strip().lower() if getattr(context, "args", None) else "status")
    if arg in ("on", "enable"):
        if not _BOT_TOKEN_77:
            await m.reply_text("Cannot enable: BOT_TOKEN is missing.")
            return
        _RICH77.enabled = True
        _RICH77.cooldown_until = 0.0
        await m.reply_text("Rich text: ON")
        return
    if arg in ("off", "disable"):
        _RICH77.enabled = False
        await m.reply_text("Rich text: OFF (classic HTML)")
        return
    cd = max(0, int(_RICH77.cooldown_until - _t77.time()))
    await m.reply_text(
        "Rich text status\n"
        "• primary transport: Official Bot API sendRichMessage\n"
        f"• MTProto fallback: {'available' if (_API_ID_77 and _API_HASH_77 and _TELETHON_OK_77) else 'unavailable'}\n"
        f"• enabled: {_RICH77.enabled}\n"
        f"• cooldown: {cd}s\n"
        f"• sent ok / fallback: {_RICH77.sent_ok} / {_RICH77.sent_fail}\n"
        f"• last error: {_RICH77.last_error or '—'}"
    )


async def cmd_richdemo_77(update, context):
    m = getattr(update, "effective_message", None)
    u = getattr(update, "effective_user", None)
    if m is None or u is None or not _is_owner_77(u.id):
        return
    sent = None
    with _cx77.suppress(Exception):
        sent = await rich_send_77(context.bot, m.chat_id, _RICH_DEMO_77, parse_mode=None)
    if not sent:
        await m.reply_text(
            "Rich send failed — fallback shown.\nlast error: " + (_RICH77.last_error or "—")
        )


try:
    _prev_build_app_77 = build_app  # type: ignore[name-defined]
except Exception:
    _prev_build_app_77 = None


def build_app():  # noqa: F811  # type: ignore[name-defined]
    app = _prev_build_app_77() if _prev_build_app_77 else None
    if app is None:
        return app
    with _cx77.suppress(Exception):
        app.add_handler(CommandHandler("rich", cmd_rich_77), group=-600)        # type: ignore[name-defined]
        app.add_handler(CommandHandler("richdemo", cmd_richdemo_77), group=-600)
    return app


_log77(
    "section loaded — enabled=%s telethon=%s creds=%s"
    % (_RICH77.enabled, _TELETHON_OK_77, bool(_API_ID_77 and _API_HASH_77))
)

# ===== END SECTION 77 =====