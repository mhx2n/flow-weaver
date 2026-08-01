# ──────────────────────────────────────────────────────────────────────────────
# Section 81 (2026-08-02) — language lock, quiz stop control, rich-topic slides
#
#  1) LANGUAGE LOCK — `.aiq`/`.gen` accept a language token:
#         en | english | ইংরেজি   → only English MCQs
#         bn | bangla  | বাংলা    → only Bangla MCQs
#         std | standard | mixed  → mixed (professional blend)
#     Without a token the source script decides (Bangla source → Bangla).
#     Enforced twice: in the AI prompt AND by rejecting off-language items.
#  2) STOP CONTROL — `/stopquiz` (`.stopquiz`) instantly halts an ongoing quiz
#     posting/generation run; `/resumequiz` clears the flag.
#  3) RICH TOPIC SLIDES — `.topicimg top|bottom <url…>` (or reply to a photo)
#     attaches a reviewable image slideshow above/below the AI topic.
#  4) `/allcmds` — every registered command, delivered to the owner inbox, and
#     all new commands are added to the owner "/" menu.
#
# Loaded last; every hook is a narrow, suppression-guarded override.
# ──────────────────────────────────────────────────────────────────────────────

import asyncio as _a81
import contextlib as _cx81
import html as _html81
import json as _json81
import re as _re81
import time as _time81


def _log81(message, level="info"):
    with _cx81.suppress(Exception):
        getattr(logger, level)("[S81] %s", message)  # type: ignore[name-defined]


def _is_owner_81(uid):
    try:
        return bool(is_owner(int(uid)))  # type: ignore[name-defined]
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 1) LANGUAGE LOCK
# ══════════════════════════════════════════════════════════════════════════════

_BN_RE_81 = _re81.compile(r"[\u0980-\u09FF]")
_EN_RE_81 = _re81.compile(r"[A-Za-z]")

_LANG_TOKENS_81 = {
    "en": "en", "eng": "en", "english": "en", "ing": "en", "ingreji": "en",
    "ইংরেজি": "en", "ইংলিশ": "en",
    "bn": "bn", "bd": "bn", "bang": "bn", "bangla": "bn", "bengali": "bn",
    "বাংলা": "bn",
    "mix": "mix", "mixed": "mix", "std": "mix", "standard": "mix",
    "both": "mix", "মিক্স": "mix", "স্ট্যান্ডার্ড": "mix", "স্টেন্ডার্ড": "mix",
}

# Active language mode for the running generation job ("en" | "bn" | "mix").
_active_lang_81 = None
# True only when the owner typed an explicit language token for this run.
# Auto-detected languages must never silently drop generated items.
_explicit_lang_81 = False


def _lang_token_81(token):
    cleaned = str(token or "").strip().strip(".,:;()[]{}").lower()
    if not cleaned:
        return None
    return _LANG_TOKENS_81.get(cleaned)


def _extract_lang_81(text, args):
    """Return (lang or None, cleaned_args). Never consumes non-language words."""
    tokens = [str(value or "").strip() for value in (args or []) if str(value or "").strip()]
    if not tokens:
        parts = _re81.split(r"\s+", str(text or "").strip())
        tokens = parts[1:] if len(parts) > 1 else []
    lang = None
    cleaned = []
    for token in tokens:
        found = _lang_token_81(token)
        if found and lang is None:
            lang = found
            continue
        cleaned.append(token)
    return lang, cleaned


def _detect_lang_81(source):
    text = str(source or "")
    bn = len(_BN_RE_81.findall(text))
    en = len(_EN_RE_81.findall(text))
    if bn >= 12 and bn * 3 >= en:
        return "bn"
    if en >= 12 and en > bn * 3:
        return "en"
    return "mix"


def _lang_directive_81(lang):
    if lang == "en":
        return (
            "\n\nLANGUAGE LOCK — ENGLISH ONLY (mandatory):\n"
            "- Write every question, every option and every explanation in English only.\n"
            "- Do NOT output any Bangla/Bengali character anywhere, even for names or units.\n"
            "- If the source is Bangla, translate its meaning accurately into English."
        )
    if lang == "bn":
        return (
            "\n\nLANGUAGE LOCK — বাংলা ONLY (mandatory):\n"
            "- প্রতিটি প্রশ্ন, প্রতিটি অপশন এবং ব্যাখ্যা শুধুমাত্র বাংলায় লিখবে।\n"
            "- কোনো প্রশ্ন বা অপশন ইংরেজিতে লেখা যাবে না; শুধু প্রয়োজনীয় বৈজ্ঞানিক/কারিগরি "
            "পরিভাষা বন্ধনীতে ইংরেজিতে রাখা যাবে (যেমন: ত্বরণ (acceleration))।\n"
            "- সোর্স ইংরেজি হলেও অর্থ ঠিক রেখে বাংলায় রূপান্তর করবে।"
        )
    return (
        "\n\nLANGUAGE MODE — STANDARD MIX:\n"
        "- Blend Bangla and English items professionally, as a real exam paper does.\n"
        "- Each single question must be internally consistent: its stem, options and "
        "explanation must all be in the same language. Never mix two languages inside one item."
    )


_prev_gen_sync_81 = globals().get("_generate_quizzes_from_ocr_sync")

if callable(_prev_gen_sync_81):
    def _generate_quizzes_from_ocr_sync(ocr_ctx, desired, user_id):  # noqa: F811
        ctx = dict(ocr_ctx or {})
        lang = globals().get("_active_lang_81")
        if not lang:
            lang = _detect_lang_81(
                str(ctx.get("clean_text") or "") + " " + str(ctx.get("raw_markdown") or "")
            )
            globals()["_active_lang_81"] = lang
        extra = _lang_directive_81(lang)
        for key in ("clean_text", "raw_markdown"):
            if str(ctx.get(key) or "").strip():
                ctx[key] = str(ctx[key]) + extra
                break
        else:
            ctx["clean_text"] = str(ctx.get("clean_text") or "") + extra
        return _prev_gen_sync_81(ctx, desired, user_id)

    globals()["_generate_quizzes_from_ocr_sync"] = _generate_quizzes_from_ocr_sync


def _payload_text_81(payload):
    parts = [str(payload.get("questions") or payload.get("question") or "")]
    for index in range(1, 6):
        parts.append(str(payload.get("option%d" % index) or ""))
    return "\n".join(parts)


def _lang_ok_81(payload, lang):
    """True when the item respects the locked language."""
    if lang not in ("en", "bn"):
        return True
    text = _payload_text_81(payload)
    bn = len(_BN_RE_81.findall(text))
    en = len(_EN_RE_81.findall(text))
    if lang == "en":
        return bn == 0
    # Bangla lock: the stem/options must be Bangla; a few English terms are fine.
    return bn >= 6 and bn * 2 >= en


_prev_buffer_add_81 = globals().get("buffer_add")


def buffer_add(user_id, payload):  # noqa: F811
    if not callable(_prev_buffer_add_81):
        return None
    data = dict(payload or {})
    lang = globals().get("_active_lang_81")
    generated = str(data.get("source") or "").lower().startswith("gen_")
    if (generated and bool(globals().get("_explicit_lang_81"))
            and lang in ("en", "bn") and not _lang_ok_81(data, lang)):
        _log81("dropped off-language (%s) generated item" % lang, "warning")
        return None
    return _prev_buffer_add_81(user_id, data)


globals()["buffer_add"] = buffer_add


def _wrap_lang_command_81(name):
    previous = globals().get(name)
    if not callable(previous):
        return

    async def wrapper(update, context, _previous=previous):
        lang = None
        with _cx81.suppress(Exception):
            lang, cleaned = _extract_lang_81(
                (update.message.text if update and update.message else "") or "",
                list(context.args or []),
            )
            if lang:
                context.args = cleaned
        globals()["_active_lang_81"] = lang
        globals()["_explicit_lang_81"] = bool(lang)
        # A new explicit generation command always cancels any stale stop flag,
        # otherwise an earlier /stopquiz would silently zero every later run.
        with _cx81.suppress(Exception):
            _stop_clear_81(update.effective_user.id if update.effective_user else None)
            _stop_clear_81(None)
        try:
            return await _previous(update, context)
        finally:
            globals()["_active_lang_81"] = None
            globals()["_explicit_lang_81"] = False

    globals()[name] = wrapper
    _log81("language lock installed on %s" % name)


for _name81 in ("cmd_aiq", "cmd_gen"):
    _wrap_lang_command_81(_name81)


# ══════════════════════════════════════════════════════════════════════════════
# 2) STOP AN ONGOING QUIZ RUN
# ══════════════════════════════════════════════════════════════════════════════

_STOP_81 = {"users": {}, "all_until": 0.0}


def _stop_request_81(user_id):
    _STOP_81["users"][int(user_id)] = _time81.time()
    _STOP_81["all_until"] = _time81.time() + 900.0


def _stop_clear_81(user_id=None):
    if user_id is None:
        _STOP_81["users"].clear()
    else:
        _STOP_81["users"].pop(int(user_id), None)
    _STOP_81["all_until"] = 0.0


def _stop_active_81(user_id=None):
    if user_id is not None and int(user_id) in _STOP_81["users"]:
        return True
    return _time81.time() < float(_STOP_81.get("all_until") or 0.0)


_prev_post_buffer_81 = globals().get("_post_buffer_to_chat")

if callable(_prev_post_buffer_81):
    async def _post_buffer_to_chat(context, admin_id, chat_id, items, thread_id=None,  # noqa: F811
                                   group_prefix="", group_expl_link=""):
        """Post one item at a time so /stopquiz can halt instantly.

        Behaviour of each individual post (anchors, prefixes, pacing, retries)
        is unchanged — the original implementation still does the sending.
        """
        _stop_clear_81(admin_id)
        rows = list(items or [])
        ok_total = 0
        fail_total = 0
        first_id = None
        stopped = False
        for row in rows:
            if _stop_active_81(admin_id):
                stopped = True
                break
            try:
                ok, fail, msg_id = await _prev_post_buffer_81(
                    context, admin_id, chat_id, [row], thread_id,
                    group_prefix, group_expl_link,
                )
            except Exception as error:
                _log81("post item failed: %s" % error, "warning")
                fail_total += 1
                continue
            ok_total += int(ok or 0)
            fail_total += int(fail or 0)
            if first_id is None and msg_id:
                first_id = msg_id
        if stopped:
            _log81("posting stopped by owner after %s quizzes" % ok_total)
            with _cx81.suppress(Exception):
                await context.bot.send_message(
                    chat_id=int(admin_id),
                    text=("⏹ <b>Quiz posting stopped</b>\nPosted: <code>%d</code>\n"
                          "Remaining in buffer: <code>%d</code>\n\n"
                          "আবার শুরু করতে: <code>/resumequiz</code> তারপর পোস্ট কমান্ড।"
                          % (ok_total, max(0, len(rows) - ok_total - fail_total))),
                    parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
                )
            _stop_clear_81(admin_id)
        return ok_total, fail_total, first_id

    globals()["_post_buffer_to_chat"] = _post_buffer_to_chat


_prev_gen_buffer_81 = globals().get("_generate_to_buffer_59")

if callable(_prev_gen_buffer_81):
    async def _generate_to_buffer_59(update, context, ocr_ctx, uid, count, mode="std"):  # noqa: F811
        if _stop_active_81(uid):
            _log81("generation round skipped — stop requested")
            return 0, 0
        return await _prev_gen_buffer_81(update, context, ocr_ctx, uid, count, mode)

    globals()["_generate_to_buffer_59"] = _generate_to_buffer_59


async def cmd_stopquiz_81(update, context):
    if not update.message or not update.effective_user:
        return
    uid = int(update.effective_user.id)
    staff = _is_owner_81(uid)
    with _cx81.suppress(Exception):
        staff = staff or bool(is_admin(uid))  # type: ignore[name-defined]
    if not staff:
        return
    _stop_request_81(uid)
    with _cx81.suppress(Exception):
        await update.message.reply_text(
            ui_box_html(  # type: ignore[name-defined]
                "Stop Requested",
                "চলমান কুইজ পোস্টিং/জেনারেশন থামানো হচ্ছে — বর্তমান কুইজটি শেষ হলেই থেমে যাবে।\n\n"
                "আবার চালু: <code>/resumequiz</code>",
                emoji="⏹",
            ),
            parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
        )


async def cmd_resumequiz_81(update, context):
    if not update.message or not update.effective_user:
        return
    uid = int(update.effective_user.id)
    staff = _is_owner_81(uid)
    with _cx81.suppress(Exception):
        staff = staff or bool(is_admin(uid))  # type: ignore[name-defined]
    if not staff:
        return
    _stop_clear_81(uid)
    with _cx81.suppress(Exception):
        await update.message.reply_text(
            ui_box_html(  # type: ignore[name-defined]
                "Stop Cleared",
                "Stop flag সরানো হয়েছে — এখন আবার পোস্ট/জেনারেশন চালানো যাবে।",
                emoji="▶️",
            ),
            parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3) RICH TOPIC IMAGE SLIDESHOW (top / bottom, reviewable)
# ══════════════════════════════════════════════════════════════════════════════

def _slides_db_init_81():
    with _cx81.suppress(Exception):
        connection = db_connect()  # type: ignore[name-defined]
        connection.execute(
            "CREATE TABLE IF NOT EXISTS ai_topic_slides ("
            "owner_id INTEGER PRIMARY KEY, position TEXT NOT NULL DEFAULT 'top', "
            "urls TEXT NOT NULL DEFAULT '[]', updated_at TEXT)"
        )
        connection.commit()
        connection.close()


_slides_db_init_81()

# Telegram delivers every photo in an album as a separate update.  Keep a
# short owner/media-group cache so replying to any one album item can attach
# the complete album instead of only the visible replied photo.
_ALBUM_BUF_81 = globals().setdefault("_ALBUM_BUF_81", {})
_COMPOSITE_SENT_81 = globals().setdefault("_COMPOSITE_SENT_81", set())


def _slides_get_81(owner_id):
    position, urls = "top", []
    with _cx81.suppress(Exception):
        connection = db_connect()  # type: ignore[name-defined]
        row = connection.execute(
            "SELECT position, urls FROM ai_topic_slides WHERE owner_id=?", (int(owner_id),)
        ).fetchone()
        connection.close()
        if row:
            position = str(row[0] or "top")
            parsed = _json81.loads(str(row[1] or "[]"))
            urls = [str(value) for value in parsed if str(value or "").strip()]
    return position, urls


def _slides_save_81(owner_id, position, urls):
    with _cx81.suppress(Exception):
        connection = db_connect()  # type: ignore[name-defined]
        connection.execute(
            "INSERT INTO ai_topic_slides(owner_id, position, urls, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(owner_id) DO UPDATE SET position=excluded.position, "
            "urls=excluded.urls, updated_at=excluded.updated_at",
            (int(owner_id), str(position or "top"), _json81.dumps(list(urls or [])),
             dt.datetime.utcnow().isoformat()),  # type: ignore[name-defined]
        )
        connection.commit()
        connection.close()


def _slides_clear_81(owner_id):
    with _cx81.suppress(Exception):
        connection = db_connect()  # type: ignore[name-defined]
        connection.execute("DELETE FROM ai_topic_slides WHERE owner_id=?", (int(owner_id),))
        connection.commit()
        connection.close()


async def _photo_urls_from_message_81(context, message):
    """Return public file URLs for photos/documents attached to a message."""
    urls = []
    if message is None:
        return urls
    token = ""
    with _cx81.suppress(Exception):
        token = str(globals().get("_BOT_TOKEN_77") or BOT_TOKEN or "").strip()  # type: ignore[name-defined]
    if not token:
        return urls
    candidates = []
    with _cx81.suppress(Exception):
        if getattr(message, "photo", None):
            candidates.append(message.photo[-1].file_id)
    with _cx81.suppress(Exception):
        document = getattr(message, "document", None)
        if document is not None and str(getattr(document, "mime_type", "") or "").startswith("image/"):
            candidates.append(document.file_id)
    for file_id in candidates:
        with _cx81.suppress(Exception):
            info = await context.bot.get_file(file_id)
            path = str(getattr(info, "file_path", "") or "")
            if path.startswith("http"):
                urls.append(path)
            elif path:
                urls.append("https://api.telegram.org/file/bot%s/%s" % (token, path))
    return urls


async def _capture_album_photo_81(update, context):
    message = getattr(update, "message", None)
    user = getattr(update, "effective_user", None)
    group_id = str(getattr(message, "media_group_id", "") or "")
    if not message or not user or not group_id or not _is_owner_81(user.id):
        return
    urls = await _photo_urls_from_message_81(context, message)
    if not urls:
        return
    key = (int(user.id), group_id)
    record = _ALBUM_BUF_81.setdefault(key, {"urls": [], "at": _time81.time()})
    record["at"] = _time81.time()
    for url in urls:
        if url not in record["urls"]:
            record["urls"].append(url)
    # Bound memory and remove stale albums opportunistically.
    cutoff = _time81.time() - 1800
    for old_key, old in list(_ALBUM_BUF_81.items()):
        if float(old.get("at") or 0) < cutoff:
            _ALBUM_BUF_81.pop(old_key, None)


async def _send_slideshow_81(context, chat_id, urls, thread_id=None, reply_to=None):
    """Native MTProto slideshow; falls back to a Bot API media group."""
    urls = [str(value) for value in (urls or []) if str(value or "").strip()][:10]
    if not urls:
        return None
    client_getter = globals().get("_get_client_77")
    peer_builder = globals().get("_peer_77")
    telethon_ok = bool(globals().get("_TELETHON_OK_77"))
    if callable(client_getter) and callable(peer_builder) and telethon_ok:
        try:
            client = await client_getter()
            peer = peer_builder(chat_id)
            if client is not None and peer is not None:
                import io as _io81
                import urllib.request as _url81
                from telethon import functions as _fn81, types as _ty81, helpers as _hp81

                def _fetch(url):
                    return _url81.urlopen(url, timeout=25).read()

                photos = []
                items = []
                for url in urls:
                    data = await _a81.to_thread(_fetch, url)
                    handle = await client.upload_file(_io81.BytesIO(data), file_name="slide.jpg")
                    uploaded = await client(_fn81.messages.UploadMediaRequest(
                        peer=peer, media=_ty81.InputMediaUploadedPhoto(file=handle)))
                    photo = uploaded.photo
                    photos.append(_ty81.InputPhoto(
                        id=photo.id, access_hash=photo.access_hash,
                        file_reference=photo.file_reference))
                for photo in photos:
                    items.append(_ty81.PageBlockPhoto(
                        photo_id=photo.id,
                        caption=_ty81.PageCaption(text=_ty81.TextEmpty(), credit=_ty81.TextEmpty()),
                    ))
                rich = _ty81.InputRichMessage(
                    blocks=[_ty81.PageBlockSlideshow(
                        items=items,
                        caption=_ty81.PageCaption(text=_ty81.TextEmpty(), credit=_ty81.TextEmpty()),
                    )],
                    photos=photos,
                )
                kwargs = {}
                with _cx81.suppress(Exception):
                    if reply_to or thread_id:
                        kwargs["reply_to"] = _ty81.InputReplyToMessage(
                            reply_to_msg_id=int(reply_to or thread_id),
                            top_msg_id=int(thread_id) if thread_id else None,
                        )
                result = await client(_fn81.messages.SendMessageRequest(
                    peer=peer,
                    message="topic slideshow",
                    random_id=_hp81.generate_random_long(),
                    rich_message=rich,
                    no_webpage=True,
                    **kwargs,
                ))
                extractor = globals().get("_msg_id_from_updates_77")
                message_id = extractor(result) if callable(extractor) else 0
                if message_id:
                    return int(message_id)
        except Exception as error:
            _log81("native slideshow failed, using media group: %s" % error, "warning")
    try:
        media = [InputMediaPhoto_81(url) for url in urls]  # type: ignore[name-defined]
    except Exception:
        media = None
    if media:
        with _cx81.suppress(Exception):
            kwargs = {"chat_id": chat_id, "media": media}
            if thread_id is not None:
                kwargs["message_thread_id"] = thread_id
            if reply_to:
                kwargs["reply_to_message_id"] = reply_to
                kwargs["allow_sending_without_reply"] = True
            sent = await context.bot.send_media_group(**kwargs)
            if sent:
                return int(getattr(sent[0], "message_id", 0) or 0)
    with _cx81.suppress(Exception):
        kwargs = {"chat_id": chat_id, "photo": urls[0]}
        if thread_id is not None:
            kwargs["message_thread_id"] = thread_id
        sent = await context.bot.send_photo(**kwargs)
        return int(getattr(sent, "message_id", 0) or 0)
    return None


def _topic_text_blocks_81(markdown):
    """Small safe Markdown→PageBlock converter for a combined topic+slides post."""
    from telethon import types as _ty81

    def rich_text(value):
        source = str(value or "").strip()
        pieces = []
        cursor = 0
        token = _re81.compile(r"\$\$([\s\S]+?)\$\$|(?<!\$)\$([^$\n]+?)\$(?!\$)|\*\*(.+?)\*\*")
        for match in token.finditer(source):
            if match.start() > cursor:
                pieces.append(_ty81.TextPlain(text=source[cursor:match.start()]))
            if match.group(1) or match.group(2):
                pieces.append(_ty81.TextMath(source=str(match.group(1) or match.group(2)).strip()))
            else:
                pieces.append(_ty81.TextBold(text=_ty81.TextPlain(text=match.group(3))))
            cursor = match.end()
        if cursor < len(source):
            pieces.append(_ty81.TextPlain(text=source[cursor:]))
        if not pieces:
            return _ty81.TextPlain(text=source or " ")
        return pieces[0] if len(pieces) == 1 else _ty81.TextConcat(texts=pieces)

    blocks = []
    for raw in str(markdown or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append(_ty81.PageBlockTitle(text=rich_text(line[2:])))
        elif line.startswith("## "):
            blocks.append(_ty81.PageBlockHeader(text=rich_text(line[3:])))
        elif line.startswith("### "):
            blocks.append(_ty81.PageBlockSubheader(text=rich_text(line[4:])))
        elif line.startswith("$$") and line.endswith("$$") and len(line) > 4:
            blocks.append(_ty81.PageBlockMath(source=line[2:-2].strip()))
        else:
            blocks.append(_ty81.PageBlockParagraph(text=rich_text(line)))
    return blocks


async def _send_topic_composite_81(context, owner_id, chat_id, text, thread_id=None):
    """Send text and slideshow as one native rich message; return PTB-like shim."""
    position, urls = _slides_get_81(owner_id)
    if not urls:
        return None
    client_getter = globals().get("_get_client_77")
    peer_builder = globals().get("_peer_77")
    if not (callable(client_getter) and callable(peer_builder) and globals().get("_TELETHON_OK_77")):
        return None
    try:
        import io as _io81
        import urllib.request as _url81
        from telethon import functions as _fn81, types as _ty81, helpers as _hp81

        client = await client_getter()
        peer = peer_builder(chat_id)
        if client is None or peer is None:
            return None

        def fetch(url):
            return _url81.urlopen(url, timeout=25).read()

        photos, items = [], []
        for index, url in enumerate(urls[:10]):
            data = await _a81.to_thread(fetch, url)
            handle = await client.upload_file(_io81.BytesIO(data), file_name="topic-%02d.jpg" % index)
            uploaded = await client(_fn81.messages.UploadMediaRequest(
                peer=peer, media=_ty81.InputMediaUploadedPhoto(file=handle)))
            photo = uploaded.photo
            input_photo = _ty81.InputPhoto(
                id=photo.id, access_hash=photo.access_hash, file_reference=photo.file_reference)
            photos.append(input_photo)
            items.append(_ty81.PageBlockPhoto(
                photo_id=input_photo.id,
                caption=_ty81.PageCaption(text=_ty81.TextEmpty(), credit=_ty81.TextEmpty()),
            ))
        slide = _ty81.PageBlockSlideshow(
            items=items, caption=_ty81.PageCaption(text=_ty81.TextEmpty(), credit=_ty81.TextEmpty()))
        text_blocks = _topic_text_blocks_81(text)
        blocks = ([slide] + text_blocks) if position == "top" else (text_blocks + [slide])
        rich = _ty81.InputRichMessage(blocks=blocks, photos=photos)
        kwargs = {}
        if thread_id:
            kwargs["reply_to"] = _ty81.InputReplyToMessage(
                reply_to_msg_id=int(thread_id), top_msg_id=int(thread_id))
        result = await client(_fn81.messages.SendMessageRequest(
            peer=peer, message="rich topic", random_id=_hp81.generate_random_long(),
            rich_message=rich, no_webpage=True, **kwargs))
        extractor = globals().get("_msg_id_from_updates_77")
        message_id = extractor(result) if callable(extractor) else 0
        shim = globals().get("_RichSentMessage77")
        if message_id and shim:
            _COMPOSITE_SENT_81.add(int(owner_id))
            return shim(context.bot, chat_id, message_id, text)
    except Exception as error:
        _log81("combined topic/slideshow failed: %s" % error, "warning")
    return None


globals()["_send_topic_composite_81"] = _send_topic_composite_81


with _cx81.suppress(Exception):
    from telegram import InputMediaPhoto as InputMediaPhoto_81  # noqa: F401
    globals()["InputMediaPhoto_81"] = InputMediaPhoto_81


async def cmd_topicimg_81(update, context):
    if not update.message or not update.effective_user or not _is_owner_81(update.effective_user.id):
        return
    owner_id = int(update.effective_user.id)
    body = _re81.sub(r"^[./]topicimg\b", "", str(update.message.text or "").strip(), flags=_re81.I).strip()
    position, urls = _slides_get_81(owner_id)

    if _re81.match(r"^(clear|reset|remove|off)\b", body, _re81.I):
        _slides_clear_81(owner_id)
        with _cx81.suppress(Exception):
            await update.message.reply_text("🗑 Topic slideshow images removed.")
        return

    match = _re81.match(r"^(top|bottom|up|down|above|below)\b", body, _re81.I)
    if match:
        token = match.group(1).lower()
        position = "bottom" if token in ("bottom", "down", "below") else "top"
        body = body[match.end():].strip()

    new_urls = _re81.findall(r"https?://\S+", body)
    reply = update.message.reply_to_message
    # Give all sibling album updates a moment to enter the media-group cache.
    if (getattr(reply, "media_group_id", None) or getattr(update.message, "media_group_id", None)):
        await _a81.sleep(1.0)
    if reply is not None:
        new_urls.extend(await _photo_urls_from_message_81(context, reply))
    new_urls.extend(await _photo_urls_from_message_81(context, update.message))
    for message in (reply, update.message):
        group_id = str(getattr(message, "media_group_id", "") or "")
        if group_id:
            record = _ALBUM_BUF_81.get((owner_id, group_id), {})
            new_urls.extend(record.get("urls") or [])
    new_urls = list(dict.fromkeys(new_urls))

    if not new_urls and not urls:
        with _cx81.suppress(Exception):
            await update.message.reply_text(
                ui_box_html(  # type: ignore[name-defined]
                    "Topic Slideshow",
                    "AI topic-এর সাথে ছবির স্লাইড যোগ করো:\n"
                    "• ছবিতে reply দিয়ে: <code>.topicimg top</code>\n"
                    "• লিংক দিয়ে: <code>.topicimg bottom https://… https://…</code>\n"
                    "• মুছতে: <code>.topicimg clear</code>\n\n"
                    "<b>top</b> = রিচ টেক্সটের উপরে, <b>bottom</b> = নিচে। "
                    "সেট করার পরে preview-তে স্লাইড দেখে তারপর Confirm করবে।",
                    emoji="🖼",
                ),
                parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
            )
        return

    urls = (list(urls) + list(new_urls))[:10] if new_urls else list(urls)
    _slides_save_81(owner_id, position, urls)
    with _cx81.suppress(Exception):
        await update.message.reply_text(
            ui_box_html(  # type: ignore[name-defined]
                "Topic Slideshow Updated",
                "Images: <code>%d</code>\nPosition: <b>%s</b>\n\nPreview পাঠানো হচ্ছে…"
                % (len(urls), "উপরে (top)" if position == "top" else "নিচে (bottom)"),
                emoji="🖼",
            ),
            parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
        )
    with _cx81.suppress(Exception):
        await _send_slideshow_81(context, update.message.chat_id, urls)


# Attach the slides to the AI-topic delivery (section 80 callback).
_prev_cb_aitopic_81 = globals().get("cb_aitopic_80")
_topic_get_81 = globals().get("_topic_get_80")
_topic_target_81 = globals().get("_topic_target_80")

if callable(_prev_cb_aitopic_81):
    async def cb_aitopic_80(update, context):  # noqa: F811
        query = update.callback_query
        owner_id = int(getattr(update.effective_user, "id", 0) or 0)
        action = ""
        with _cx81.suppress(Exception):
            matched = _re81.fullmatch(r"ait80:(send|pin|cancel):(\d+)",
                                      (query.data or "") if query else "")
            action = matched.group(1) if matched else ""
        if action not in ("send", "pin") or not _is_owner_81(owner_id):
            return await _prev_cb_aitopic_81(update, context)

        position, urls = _slides_get_81(owner_id)
        target = None
        with _cx81.suppress(Exception):
            row = _topic_get_81(owner_id) if callable(_topic_get_81) else None
            if row and callable(_topic_target_81):
                target = _topic_target_81(owner_id, row["target_type"], int(row["target_serial"]),
                                          row.get("sub_topic_id"))
        if not urls or not target:
            return await _prev_cb_aitopic_81(update, context)

        chat_id, _title, thread_id = target
        composite_available = callable(globals().get("_send_topic_composite_81"))
        if position == "top" and not composite_available:
            with _cx81.suppress(Exception):
                await _send_slideshow_81(context, chat_id, urls, thread_id=thread_id)
        result = await _prev_cb_aitopic_81(update, context)
        delivered = True
        with _cx81.suppress(Exception):
            delivered = _topic_get_81(owner_id) is None
        if delivered:
            composite_sent = owner_id in _COMPOSITE_SENT_81
            # If the one-message native composite failed, preserve every image
            # with an ordered media-group fallback instead of silently losing
            # top-position slides.
            if not composite_sent:
                with _cx81.suppress(Exception):
                    await _send_slideshow_81(context, chat_id, urls, thread_id=thread_id)
            _COMPOSITE_SENT_81.discard(owner_id)
            _slides_clear_81(owner_id)
        return result

    globals()["cb_aitopic_80"] = cb_aitopic_80


# ══════════════════════════════════════════════════════════════════════════════
# 4) OWNER VISIBILITY: full command list + "/" menu entries
# ══════════════════════════════════════════════════════════════════════════════

_NEW_OWNER_COMMANDS_81 = [
    ("aiq", "Unlimited quiz from any text/topic (.aiq buet en 50)"),
    ("aitopic", "AI rich-text topic → review → confirm/pin"),
    ("topicimg", "Add image slideshow above/below the AI topic"),
    ("cleartopic", "Remove the active topic anchor"),
    ("stopquiz", "Stop the running quiz posting/generation"),
    ("resumequiz", "Clear the stop flag"),
    ("qver", "Quiz poll language: bn | en"),
    ("mathpost", "Math 2-message rich format on/off"),
    ("shuffle", "Option shuffle on/off (ক খ গ ঘ order)"),
    ("postdelay", "Delay between quiz posts (seconds)"),
    ("rich", "Rich text transport on/off/status"),
    ("richdemo", "Send a rich-format demo"),
    ("allcmds", "Show every command in your inbox"),
]

with _cx81.suppress(Exception):
    _sections81 = globals().get("PRIVATE_COMMAND_SECTIONS")
    if isinstance(_sections81, dict) and "owner" in _sections81:
        _existing81 = {name for (name, _d) in _sections81["owner"]}
        for _name, _desc in _NEW_OWNER_COMMANDS_81:
            if _name not in _existing81:
                _sections81["owner"].append((_name, _desc))
                _existing81.add(_name)
        _sections81["owner"].sort(key=lambda item: item[0].lower())
        _log81("owner menu extended with %d command(s)" % len(_NEW_OWNER_COMMANDS_81))


def _all_command_names_81(app):
    names = set()
    with _cx81.suppress(Exception):
        for handlers in (app.handlers or {}).values():
            for handler in handlers or []:
                for attr in ("commands",):
                    values = getattr(handler, attr, None) or []
                    for value in values:
                        with _cx81.suppress(Exception):
                            names.add(str(value).lower())
    return sorted(name for name in names if _re81.fullmatch(r"[a-z0-9_]{2,32}", name or ""))


async def cmd_allcmds_81(update, context):
    if not update.message or not update.effective_user or not _is_owner_81(update.effective_user.id):
        return
    app = getattr(context, "application", None)
    names = _all_command_names_81(app) if app is not None else []
    described = dict(_NEW_OWNER_COMMANDS_81)
    with _cx81.suppress(Exception):
        for bucket in ("user", "admin", "owner"):
            for name, desc in (globals().get("PRIVATE_COMMAND_SECTIONS") or {}).get(bucket, []):
                described.setdefault(str(name), str(desc))
    lines = []
    for name in names:
        note = described.get(name, "")
        lines.append("/%s%s" % (_html81.escape(name), " — " + _html81.escape(note) if note else ""))
    if not lines:
        lines = ["(no command handlers found)"]
    chunk = []
    length = 0
    owner_chat = int(update.effective_user.id)
    for line in lines:
        if length + len(line) > 3200:
            with _cx81.suppress(Exception):
                await context.bot.send_message(chat_id=owner_chat, text="\n".join(chunk),
                                               parse_mode=ParseMode.HTML)  # type: ignore[name-defined]
            chunk, length = [], 0
        chunk.append(line)
        length += len(line) + 1
    if chunk:
        with _cx81.suppress(Exception):
            await context.bot.send_message(
                chat_id=owner_chat,
                text=("👑 <b>All Commands (%d)</b>\n" % len(lines)) + "\n".join(chunk),
                parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
            )


if "build_app" in globals():
    _prev_build_app_81 = build_app  # type: ignore[name-defined]

    def build_app():  # noqa: F811
        app = _prev_build_app_81()
        with _cx81.suppress(Exception):
            registrar = globals().get("_register_dual_command")
            pairs = (
                ("stopquiz", cmd_stopquiz_81),
                ("resumequiz", cmd_resumequiz_81),
                ("topicimg", cmd_topicimg_81),
                ("allcmds", cmd_allcmds_81),
            )
            for name, callback in pairs:
                if callable(registrar):
                    registrar(app, name, callback, group=-700)
                else:
                    app.add_handler(CommandHandler(name, callback), group=-700)  # type: ignore[name-defined]
            app.add_handler(MessageHandler(filters.PHOTO, _capture_album_photo_81), group=-710)  # type: ignore[name-defined]
        return app


_log81("section 81 ready: language lock, stop control, topic slideshow, full command list")
