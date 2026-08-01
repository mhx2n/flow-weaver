# ──────────────────────────────────────────────────────────────────────────────
# Section: 82_link_topic_anchor_from_post_url_08_02
# PROBAHO PATCH-82 — Make ANY existing channel/group post a topic anchor
# by pasting its t.me link. Quizzes then reply to that post (same-chat or
# cross-chat) exactly like AI-generated topics, until a new topic is set
# or the anchor is removed.
#
# Commands (owner/admin, private inbox):
#   .linktopic <t.me post link> [| name]   → set that post as active topic
#   .lt <link>                             → alias
#   .topicinfo                             → show current active anchor
#   .topicoff                              → remove active anchor
#
# Also works by REPLYING to a forwarded channel post with `.linktopic`.
#
# Supported link forms:
#   https://t.me/c/1234567890/55            (private channel/group)
#   https://t.me/c/1234567890/12/55         (forum topic thread)
#   https://t.me/mychannel/55               (public @username)
#   https://t.me/mychannel/12/55            (public forum thread)
#   t.me/… , telegram.me/… , with or without scheme, ?comment=/&single ignored
# DO NOT import this file directly — exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx82
import re as _re82


def _log82(msg, *args):
    with _cx82.suppress(Exception):
        logger.info("[PATCH-82] " + str(msg), *args)  # type: ignore[name-defined]


_LINK_RE_82 = _re82.compile(
    r"(?:https?://)?(?:www\.)?(?:t(?:elegram)?\.me|telegram\.dog)/"
    r"(?P<body>[^\s<>()\[\]]+)",
    _re82.IGNORECASE,
)


class TopicLinkError82(Exception):
    """Raised when a t.me link cannot be turned into a topic anchor."""


def parse_post_link_82(text: str):
    """
    Parse a Telegram post link.

    Returns (chat_ref, message_id) where chat_ref is either an int chat_id
    (for /c/ links) or a '@username' string. Raises TopicLinkError82.
    """
    raw = (text or "").strip()
    if not raw:
        raise TopicLinkError82("No link found.")
    m = _LINK_RE_82.search(raw)
    if not m:
        raise TopicLinkError82("That does not look like a t.me post link.")

    body = m.group("body")
    body = body.split("?", 1)[0].split("#", 1)[0].strip("/")
    parts = [p for p in body.split("/") if p]
    if not parts:
        raise TopicLinkError82("Link has no post id.")

    if parts[0].lower() == "c":
        # /c/<internal_id>/[thread/]<msg_id>
        nums = [p for p in parts[1:] if p.isdigit()]
        if len(nums) < 2:
            raise TopicLinkError82("Private link must be t.me/c/&lt;id&gt;/&lt;post&gt;.")
        internal = nums[0]
        msg_id = int(nums[-1])
        chat_id = int("-100" + internal) if not internal.startswith("-") else int(internal)
        return chat_id, msg_id

    if parts[0].lower() in {"s", "joinchat", "addstickers", "share", "proxy", "iv"}:
        raise TopicLinkError82("That is not a post link.")

    username = parts[0].lstrip("@")
    if not _re82.fullmatch(r"[A-Za-z0-9_]{3,32}", username):
        raise TopicLinkError82("Invalid channel username in link.")
    nums = [p for p in parts[1:] if p.isdigit()]
    if not nums:
        raise TopicLinkError82("Link has no post id.")
    return "@" + username, int(nums[-1])


async def _resolve_chat_82(context, chat_ref):
    """Resolve chat_ref → (chat_id, title). Raises TopicLinkError82."""
    try:
        chat = await context.bot.get_chat(chat_ref)
    except Exception as exc:
        raise TopicLinkError82(
            "Bot cannot access that chat. Add the bot to the channel/group "
            "(as admin) and try again.<br>Detail: " + h(str(exc)[:160])  # type: ignore[name-defined]
        ) from exc
    title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat.id)
    return int(chat.id), str(title)


def _anchor_from_forward_82(message):
    """Extract (chat_id, msg_id, title) from a replied-to forwarded post."""
    src = getattr(message, "reply_to_message", None)
    if src is None:
        return None
    origin = getattr(src, "forward_origin", None)
    chat = getattr(origin, "chat", None) if origin is not None else None
    msg_id = getattr(origin, "message_id", None) if origin is not None else None
    if chat is None:
        chat = getattr(src, "forward_from_chat", None)
        msg_id = getattr(src, "forward_from_message_id", None)
    if chat is None or not msg_id:
        return None
    title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat.id)
    return int(chat.id), int(msg_id), str(title)


async def _preview_anchor_82(context, owner_id: int, chat_id: int, msg_id: int) -> str:
    """
    Verify the post really exists / is reachable by copying it to the owner.
    Returns "" on success, else a human-readable warning.
    """
    try:
        await context.bot.copy_message(
            chat_id=owner_id, from_chat_id=chat_id, message_id=msg_id,
            disable_notification=True,
        )
        return ""
    except Exception as exc:
        return str(exc)[:180]


@require_admin  # type: ignore[name-defined]
async def cmd_linktopic_82(update, context):
    """.linktopic <t.me post link> [| name] — use an existing post as topic anchor."""
    if not update.message or not update.effective_user:
        return
    admin_id = int(update.effective_user.id)
    raw = " ".join(context.args or []).strip()
    name = ""
    if "|" in raw:
        raw, name = raw.split("|", 1)
        raw, name = raw.strip(), name.strip()[:60]

    chat_id = msg_id = None
    title = ""

    if raw:
        try:
            chat_ref, msg_id = parse_post_link_82(raw)
        except TopicLinkError82 as exc:
            await warn_html(  # type: ignore[name-defined]
                update, "Invalid Post Link",
                str(exc).replace("<br>", "\n")
                + "\n\nExample: <code>.linktopic https://t.me/c/1234567890/55</code>",
            )
            return
        if isinstance(chat_ref, str):
            try:
                chat_id, title = await _resolve_chat_82(context, chat_ref)
            except TopicLinkError82 as exc:
                await warn_html(update, "Chat Not Reachable",  # type: ignore[name-defined]
                                str(exc).replace("<br>", "\n"))
                return
        else:
            chat_id = int(chat_ref)
            with _cx82.suppress(Exception):
                _cid, title = await _resolve_chat_82(context, chat_id)
                chat_id = _cid
    else:
        fwd = _anchor_from_forward_82(update.message)
        if not fwd:
            await safe_reply(update, usage_box(  # type: ignore[name-defined]
                "linktopic", "<t.me post link> [| name]",
                "Turn an existing channel/group post into the active topic anchor. "
                "You can also reply to a forwarded post with .linktopic",
            ))
            return
        chat_id, msg_id, title = fwd

    if not chat_id or not msg_id:
        await warn_html(update, "Invalid Post Link", "Could not read chat id / post id.")  # type: ignore[name-defined]
        return

    if not title:
        title = str(chat_id)

    problem = await _preview_anchor_82(context, admin_id, chat_id, msg_id)

    preview_text = ""
    with _cx82.suppress(Exception):
        preview_text = ("Linked post: " + title)[:400]

    with _cx82.suppress(Exception):
        _set_topic_anchor(admin_id, chat_id, msg_id, preview_text, "")  # type: ignore[name-defined]

    with _cx82.suppress(Exception):
        _sta_save(admin_id, name or ("Linked · " + title), chat_id, msg_id, preview_text, "")  # type: ignore[name-defined]

    with _cx82.suppress(Exception):
        db_log("INFO", "linktopic_set",  # type: ignore[name-defined]
               {"admin_id": admin_id, "chat_id": chat_id, "msg_id": msg_id})

    body = (
        f"<b>Chat</b>: <code>{h(title)}</code> (<code>{h(str(chat_id))}</code>)\n"  # type: ignore[name-defined]
        f"<b>Post</b>: <code>{h(str(msg_id))}</code>\n\n"  # type: ignore[name-defined]
        "All quizzes posted from now on will <b>reply to this post</b> "
        "(same-chat or cross-chat), until you set a new topic or run "
        "<code>.topicoff</code>."
    )
    if problem:
        body += (
            "\n\n⚠️ Preview failed — the anchor is still saved, but verify the bot "
            f"is an admin there.\n<code>{h(problem)}</code>"  # type: ignore[name-defined]
        )
    await ok_html(update, "Topic Anchor Linked", body, emoji="🔗")  # type: ignore[name-defined]


@require_admin  # type: ignore[name-defined]
async def cmd_topicinfo_82(update, context):
    """.topicinfo — show the currently active topic anchor."""
    if not update.effective_user:
        return
    admin_id = int(update.effective_user.id)
    anchor_chat, anchor_msg = _get_topic_anchor(admin_id)  # type: ignore[name-defined]
    if not anchor_msg:
        await warn_html(  # type: ignore[name-defined]
            update, "No Active Topic",
            "Set one with <code>.aitopic</code> or "
            "<code>.linktopic &lt;post link&gt;</code>.",
        )
        return
    title = str(anchor_chat)
    with _cx82.suppress(Exception):
        _cid, title = await _resolve_chat_82(context, int(anchor_chat))
    link = ""
    with _cx82.suppress(Exception):
        s = str(anchor_chat)
        if s.startswith("-100"):
            link = f"https://t.me/c/{s[4:]}/{anchor_msg}"
    body = (
        f"<b>Chat</b>: <code>{h(title)}</code> (<code>{h(str(anchor_chat))}</code>)\n"  # type: ignore[name-defined]
        f"<b>Post</b>: <code>{h(str(anchor_msg))}</code>"  # type: ignore[name-defined]
    )
    if link:
        body += f"\n<b>Link</b>: {h(link)}"  # type: ignore[name-defined]
    body += "\n\nQuizzes reply to this post. Remove with <code>.topicoff</code>."
    await ok_html(update, "Active Topic Anchor", body, emoji="📌")  # type: ignore[name-defined]


@require_admin  # type: ignore[name-defined]
async def cmd_topicoff_82(update, context):
    """.topicoff — clear the active topic anchor."""
    if not update.effective_user:
        return
    admin_id = int(update.effective_user.id)
    with _cx82.suppress(Exception):
        _clear_topic_anchor(admin_id)  # type: ignore[name-defined]
    await ok_html(  # type: ignore[name-defined]
        update, "Topic Anchor Removed",
        "Quizzes will now post without any reply header until a new topic is set.",
        emoji="🧹",
    )


_NEW_OWNER_COMMANDS_82 = [
    ("linktopic", "Use an existing channel/group post link as topic anchor"),
    ("lt", "Alias of /linktopic"),
    ("topicinfo", "Show the currently active topic anchor"),
    ("topicoff", "Remove the active topic anchor"),
]

with _cx82.suppress(Exception):
    _sections82 = globals().get("PRIVATE_COMMAND_SECTIONS")
    if isinstance(_sections82, dict):
        _bucket82 = _sections82.setdefault("owner", [])
        _have82 = {str(n) for n, _d in _bucket82}
        for _n, _d in _NEW_OWNER_COMMANDS_82:
            if _n not in _have82:
                _bucket82.append((_n, _d))
        _bucket82.sort(key=lambda item: item[0].lower())


if "build_app" in globals():
    _prev_build_app_82 = build_app  # type: ignore[name-defined]

    def build_app():  # noqa: F811
        app = _prev_build_app_82()
        with _cx82.suppress(Exception):
            registrar = globals().get("_register_dual_command")
            pairs = (
                ("linktopic", cmd_linktopic_82),
                ("lt", cmd_linktopic_82),
                ("topiclink", cmd_linktopic_82),
                ("topicinfo", cmd_topicinfo_82),
                ("topicoff", cmd_topicoff_82),
            )
            for _name, _cb in pairs:
                if callable(registrar):
                    registrar(app, _name, _cb, group=-720)
                else:
                    app.add_handler(CommandHandler(_name, _cb), group=-720)  # type: ignore[name-defined]
        return app


_log82("section 82 ready: post-link topic anchors (.linktopic / .topicinfo / .topicoff)")