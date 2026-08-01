# ──────────────────────────────────────────────────────────────────────────────
# Section 84 (2026-08-02) — Rich text ALWAYS, and reply-to-answer continues the
# same AI thread again.
#
# Two user-visible bugs are fixed here (nothing else is touched):
#
#   1) Rich text appeared only "sometimes".
#      Cause: section 77's `_RichState77.note_fail()` puts the whole rich
#      transport into a 5-minute cooldown after 3 failures, and
#      `_get_client_77()` sets `enabled = False` permanently after one failed
#      MTProto start.  So a single hiccup silently downgraded every following
#      answer to classic HTML for minutes (or forever).
#      → cooldown is now 15s, the streak threshold is higher, the transport
#        self-heals, and each rich delivery retries once after clearing the
#        cooldown before it gives up.  Fallback still exists, so no user
#        can ever see an error.
#
#   2) Replying to an AI answer no longer continued the chat ("Please send your
#      question." again).
#      Cause: rich delivery deletes the original bot message and posts a NEW
#      message, but the thread registry stored the OLD (deleted) message id,
#      so `ai_thread_lookup_by_bot_message()` found nothing for the message the
#      user actually replied to.
#      → every rich message id produced for an answer is now registered on the
#        same thread, so replying to any of them resumes the conversation.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx84
import time as _t84


def _log84(msg: str) -> None:
    with _cx84.suppress(Exception):
        logger.info("[S84] %s", msg)  # type: ignore[name-defined]


# ══════════════════════════════════════════════════════════════════════════
# 1) SELF-HEALING RICH TRANSPORT (rich text stops being intermittent)
# ══════════════════════════════════════════════════════════════════════════

_RICH_STATE_84 = globals().get("_RICH77")


def _heal_rich_84() -> None:
    """Clear cooldowns / soft-disables so the next attempt really tries."""
    state = _RICH_STATE_84
    if state is None:
        return
    with _cx84.suppress(Exception):
        state.cooldown_until = 0.0
        state.fail_streak = 0
        if not getattr(state, "enabled", False):
            token = globals().get("_BOT_TOKEN_77")
            if token and not globals().get("_RICH_ENV_OFF_77"):
                state.enabled = True


globals()["_heal_rich_84"] = _heal_rich_84


def _install_soft_cooldown_84() -> None:
    state = _RICH_STATE_84
    if state is None:
        return
    cls = type(state)
    if getattr(cls, "_s84_patched", False):
        return

    def note_fail(self, err):  # noqa: ANN001
        self.sent_fail += 1
        self.fail_streak += 1
        self.last_error = str(err)[:300]
        if self.fail_streak >= 6:
            # Very short breather only — long cooldowns were the reason rich
            # formatting disappeared for whole minutes.
            self.cooldown_until = _t84.time() + 15.0
            self.fail_streak = 0

    cls.note_fail = note_fail
    cls._s84_patched = True


_install_soft_cooldown_84()


_prev_get_client_84 = globals().get("_get_client_77")


async def _get_client_84():
    """Never let one failed MTProto start disable rich text permanently."""
    if not callable(_prev_get_client_84):
        return None
    client = None
    with _cx84.suppress(Exception):
        client = await _prev_get_client_84()
    if client is None:
        _heal_rich_84()
    return client


if callable(_prev_get_client_84):
    globals()["_get_client_77"] = _get_client_84
globals()["_get_client_84"] = _get_client_84


# ══════════════════════════════════════════════════════════════════════════
# 2) RICH DELIVERY WITH ONE RETRY + MESSAGE-ID BOOKKEEPING
# ══════════════════════════════════════════════════════════════════════════

# chat_id -> [(message_id, timestamp)] produced by rich delivery, waiting to be
# attached to the AI thread of the answer being stored.
_PENDING_RICH_84: dict = {}
_PENDING_TTL_84 = 180.0


def _note_rich_message_84(chat_id, message_id) -> None:
    with _cx84.suppress(Exception):
        cid = int(chat_id or 0)
        mid = int(message_id or 0)
        if not cid or not mid:
            return
        now = _t84.time()
        bucket = [it for it in _PENDING_RICH_84.get(cid, []) if now - it[1] <= _PENDING_TTL_84]
        bucket.append((mid, now))
        _PENDING_RICH_84[cid] = bucket[-12:]
        if len(_PENDING_RICH_84) > 300:
            for stale in list(_PENDING_RICH_84.keys())[:150]:
                _PENDING_RICH_84.pop(stale, None)


def _take_rich_messages_84(chat_id):
    with _cx84.suppress(Exception):
        cid = int(chat_id or 0)
        now = _t84.time()
        bucket = _PENDING_RICH_84.pop(cid, []) or []
        return [mid for mid, ts in bucket if now - ts <= _PENDING_TTL_84]
    return []


_prev_rich_deliver_84 = globals().get("rich_deliver_83")


async def rich_deliver_84(bot, chat_id, markdown, *, reply_to=None, thread_id=None,
                          reply_markup=None):
    """Rich send that heals the transport and retries once before falling back."""
    if not callable(_prev_rich_deliver_84):
        return None
    if not str(markdown or "").strip():
        return None
    sent = None
    for attempt in (0, 1):
        if attempt:
            _heal_rich_84()
        with _cx84.suppress(Exception):
            sent = await _prev_rich_deliver_84(
                bot, chat_id, markdown,
                reply_to=reply_to, thread_id=thread_id, reply_markup=reply_markup,
            )
        if sent:
            break
    if sent:
        _note_rich_message_84(chat_id, getattr(sent, "message_id", None))
    return sent


globals()["rich_deliver_83"] = rich_deliver_84
globals()["rich_deliver_84"] = rich_deliver_84


# ══════════════════════════════════════════════════════════════════════════
# 3) FINAL ANSWER DELIVERY KEEPS THE REPLY ANCHOR
# ══════════════════════════════════════════════════════════════════════════

_prev_edit_final_84 = globals().get("_edit_query_final_66")
_RICH_SRC_84 = globals().get("_RICH_SRC_83")
_key_fn_84 = globals().get("_key83")


async def _edit_query_final_84(q, html_text, *, reply_markup=None, plain_fallback=""):
    markdown = ""
    if isinstance(_RICH_SRC_84, dict) and callable(_key_fn_84):
        with _cx84.suppress(Exception):
            markdown = _RICH_SRC_84.get(_key_fn_84(html_text)) or ""
    message = getattr(q, "message", None)
    if markdown and message is not None:
        bot = None
        with _cx84.suppress(Exception):
            bot = q.get_bot()
        if bot is None:
            with _cx84.suppress(Exception):
                bot = message.get_bot()
        chat_id = getattr(message, "chat_id", None)
        # keep the visual reply chain to the user's own question
        anchor = None
        with _cx84.suppress(Exception):
            src = getattr(message, "reply_to_message", None)
            anchor = getattr(src, "message_id", None) if src else None
        if bot is not None and chat_id is not None:
            sent = await rich_deliver_84(
                bot, chat_id, markdown,
                reply_to=anchor,
                thread_id=getattr(message, "message_thread_id", None),
                reply_markup=reply_markup,
            )
            if sent:
                with _cx84.suppress(Exception):
                    await message.delete()
                return sent
    if callable(_prev_edit_final_84):
        return await _prev_edit_final_84(q, html_text, reply_markup=reply_markup,
                                        plain_fallback=plain_fallback)
    return None


if callable(_prev_edit_final_84):
    globals()["_edit_query_final_66"] = _edit_query_final_84
globals()["_edit_query_final_84"] = _edit_query_final_84


# ══════════════════════════════════════════════════════════════════════════
# 4) REPLY-TO-ANSWER RESUMES THE SAME THREAD AGAIN
# ══════════════════════════════════════════════════════════════════════════

_prev_upsert_bot_answer_84 = globals().get("ai_thread_upsert_bot_answer")


def ai_thread_upsert_bot_answer_84(thread_id, content, chat_id, message_id,
                                   reply_to_message_id=0, model_code='', model_name=''):
    """Register the answer for the classic message id AND every rich message id."""
    if not callable(_prev_upsert_bot_answer_84):
        return None
    ids = []
    with _cx84.suppress(Exception):
        ids = _take_rich_messages_84(chat_id)
    with _cx84.suppress(Exception):
        _prev_upsert_bot_answer_84(thread_id, content, chat_id, message_id,
                                   reply_to_message_id, model_code, model_name)
    for mid in ids:
        if int(mid or 0) == int(message_id or 0):
            continue
        with _cx84.suppress(Exception):
            _prev_upsert_bot_answer_84(thread_id, content, chat_id, mid,
                                       reply_to_message_id, model_code, model_name)
    return None


if callable(_prev_upsert_bot_answer_84):
    globals()["ai_thread_upsert_bot_answer"] = ai_thread_upsert_bot_answer_84
globals()["ai_thread_upsert_bot_answer_84"] = ai_thread_upsert_bot_answer_84


# Extra chunks are rich-delivered too; their ids must join the same thread, so
# route them through the bookkeeping wrapper as well.
_prev_extra_chunks_84 = globals().get("_reply_extra_chunks_66")


async def _reply_extra_chunks_84(message, chunks):
    if not message or not chunks:
        return
    if callable(_prev_extra_chunks_84):
        with _cx84.suppress(Exception):
            return await _prev_extra_chunks_84(message, chunks)
    return None


if callable(_prev_extra_chunks_84):
    globals()["_reply_extra_chunks_66"] = _reply_extra_chunks_84
globals()["_reply_extra_chunks_84"] = _reply_extra_chunks_84


_log84("section 84 ready: self-healing rich transport (retry + 15s max cooldown), "
       "reply-anchored rich answers, thread continuity for rich message ids")
