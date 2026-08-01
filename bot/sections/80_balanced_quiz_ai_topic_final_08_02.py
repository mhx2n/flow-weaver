# ──────────────────────────────────────────────────────────────────────────────
# Section 80 (2026-08-02) — final quiz integrity + balanced answers + AI topics
#
# Loaded last by bot/__main__.py.  This section deliberately uses narrow final
# overrides so all existing commands and data remain compatible.
# ──────────────────────────────────────────────────────────────────────────────

import asyncio as _a80
import contextlib as _cx80
import html as _html80
import json as _json80
import re as _re80
import time as _time80

import telegram as _tg80


def _log80(message, level="info"):
    with _cx80.suppress(Exception):
        getattr(logger, level)("[S80] %s", message)  # type: ignore[name-defined]


# ══════════════════════════════════════════════════════════════════════════════
# 1) STRICT GENERATED-MCQ INTEGRITY
# ══════════════════════════════════════════════════════════════════════════════

def _clean_mcq_text_80(value):
    text = str(value or "").replace("\x00", "").strip()
    text = _re80.sub(r"[ \t]+", " ", text)
    text = _re80.sub(r"\n{3,}", "\n\n", text)
    return text


def _answer_int_80(item, options):
    """Resolve an explicit answer without ever guessing option 1."""
    if not isinstance(item, dict):
        return 0
    zero_based = item.get("correct_option_id")
    if zero_based is not None:
        with _cx80.suppress(Exception):
            value = int(zero_based)
            if 0 <= value < len(options):
                return value + 1
    for key in ("answer", "correct", "correct_answer", "correctOption", "correct_option"):
        if key not in item:
            continue
        value = item.get(key)
        with _cx80.suppress(Exception):
            number = int(str(value).strip())
            if 1 <= number <= len(options):
                return number
        token = str(value or "").strip().lower().strip("()[]{}.: ")
        label_map = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5,
                     "ক": 1, "খ": 2, "গ": 3, "ঘ": 4, "ঙ": 5}
        if token in label_map and label_map[token] <= len(options):
            return label_map[token]
    answer_text = _clean_mcq_text_80(item.get("correct_option_text") or "").casefold()
    if answer_text:
        exact = [i + 1 for i, option in enumerate(options)
                 if _clean_mcq_text_80(option).casefold() == answer_text]
        if len(exact) == 1:
            return exact[0]
    return 0


def _valid_generated_mcq_80(item):
    if not isinstance(item, dict):
        return None
    question = _clean_mcq_text_80(
        item.get("question") or item.get("questions") or item.get("q") or item.get("stem")
    )
    if len(question) < 5 or question in ("?", "প্রশ্ন", "question"):
        return None
    raw_options = item.get("options") or item.get("choices") or []
    if isinstance(raw_options, dict):
        raw_options = list(raw_options.values())
    options = [_clean_mcq_text_80(value) for value in raw_options] if isinstance(raw_options, list) else []
    options = [value for value in options if value]
    if len(options) < 2:
        options = [_clean_mcq_text_80(item.get("option%d" % i)) for i in range(1, 6)]
        options = [value for value in options if value]
    options = options[:5]
    if len(options) < 2:
        return None
    signatures = [_re80.sub(r"\W+", "", value, flags=_re80.UNICODE).casefold() for value in options]
    if any(not signature for signature in signatures) or len(set(signatures)) != len(signatures):
        return None
    answer = _answer_int_80(item, options)
    if not (1 <= answer <= len(options)):
        return None
    explanation = _clean_mcq_text_80(
        item.get("explanation") or item.get("reason") or item.get("solution")
    )[:200]
    return {"question": question, "options": options, "answer": answer, "explanation": explanation}


# Replace the permissive normalizer that previously converted a missing answer
# to option 1. Invalid items now make the provider cascade try another response.
def _normalise_mcq_74(item):  # noqa: F811
    return _valid_generated_mcq_80(item)


globals()["_normalise_mcq_74"] = _normalise_mcq_74


_prev_prompt_80 = globals().get("_make_fast_new_mcq_prompt_74")


def _make_fast_new_mcq_prompt_74(source_text, n, *, easy=0, medium=0, hard=0, avoid_text=""):  # noqa: F811
    if callable(_prev_prompt_80):
        prompt = _prev_prompt_80(
            source_text, n, easy=easy, medium=medium, hard=hard, avoid_text=avoid_text
        )
    else:
        prompt = str(source_text or "")
    return prompt + (
        "\n\nCRITICAL OUTPUT INTEGRITY:\n"
        "- Every item must contain a non-empty self-contained question and 4 non-empty, unique options.\n"
        "- Never omit the question, any option, or the explicit answer. Never guess an answer.\n"
        "- Across this batch distribute correct answer positions as evenly as possible among 1,2,3,4; "
        "do not cluster them in positions 1 or 2.\n"
        "- Verify the stated answer against the option text before returning JSON."
    )


globals()["_make_fast_new_mcq_prompt_74"] = _make_fast_new_mcq_prompt_74


def _payload_parts_80(payload):
    question = _clean_mcq_text_80(payload.get("questions") or payload.get("question"))
    options = [_clean_mcq_text_80(payload.get("option%d" % i)) for i in range(1, 6)]
    options = [option for option in options if option]
    answer = 0
    with _cx80.suppress(Exception):
        answer = int(payload.get("answer") or 0)
    return question, options, answer


def _generated_payload_80(payload):
    source = str(payload.get("source") or "").lower()
    return source.startswith("gen_") or source in ("ai", "aiq", "generated")


_ANSWER_BALANCE_CACHE_80 = {}


def _answer_counts_80(user_id, option_count):
    current_size = 0
    with _cx80.suppress(Exception):
        current_size = int(buffer_count(user_id))  # type: ignore[name-defined]
    cached = _ANSWER_BALANCE_CACHE_80.get((int(user_id), int(option_count)))
    if cached and int(cached.get("size", -1)) == current_size:
        return list(cached.get("counts") or [0] * option_count)
    counts = [0] * option_count
    with _cx80.suppress(Exception):
        for _, existing in buffer_list(user_id, limit=1000):  # type: ignore[name-defined]
            _, opts, answer = _payload_parts_80(existing)
            if len(opts) == option_count and 1 <= answer <= option_count:
                counts[answer - 1] += 1
    _ANSWER_BALANCE_CACHE_80[(int(user_id), int(option_count))] = {
        "size": current_size,
        "counts": list(counts),
    }
    return counts


def _rebalance_payload_80(user_id, payload):
    """Move the correct option to the least-used slot while preserving meaning."""
    data = dict(payload or {})
    # Manual imports, forwarded Telegram polls and legacy regular polls retain
    # their exact old behaviour. Strict rejection/balancing is generation-only.
    if not _generated_payload_80(data):
        return data
    question, options, answer = _payload_parts_80(data)
    if not question or len(options) < 2 or not (1 <= answer <= len(options)):
        return None
    signatures = [_re80.sub(r"\W+", "", value, flags=_re80.UNICODE).casefold() for value in options]
    if any(not value for value in signatures) or len(set(signatures)) != len(signatures):
        return None
    if _generated_payload_80(data):
        counts = _answer_counts_80(user_id, len(options))
        minimum = min(counts)
        candidates = [i for i, count in enumerate(counts) if count == minimum]
        # Rotate ties using total count, producing 1,2,3,4 rather than random streaks.
        target = candidates[sum(counts) % len(candidates)]
        current = answer - 1
        if current != target:
            options[current], options[target] = options[target], options[current]
            answer = target + 1
    data["questions"] = question
    data["answer"] = answer
    for index in range(5):
        data["option%d" % (index + 1)] = options[index] if index < len(options) else ""
    return data


_prev_buffer_add_80 = globals().get("buffer_add")


def buffer_add(user_id, payload):  # noqa: F811
    if not callable(_prev_buffer_add_80):
        return None
    checked = _rebalance_payload_80(int(user_id), dict(payload or {}))
    if checked is None:
        _log80("rejected incomplete/ambiguous quiz payload for user %s" % user_id, "warning")
        return None
    result = _prev_buffer_add_80(user_id, checked)
    if _generated_payload_80(checked):
        _, options, answer = _payload_parts_80(checked)
        key = (int(user_id), len(options))
        cached = _ANSWER_BALANCE_CACHE_80.get(key)
        if cached and 1 <= answer <= len(options):
            counts = list(cached.get("counts") or [0] * len(options))
            counts[answer - 1] += 1
            cached["counts"] = counts
            cached["size"] = int(cached.get("size", 0)) + 1
    return result


globals()["buffer_add"] = buffer_add


# Make the rich card easier to scan while guaranteeing that neither its stem nor
# options can disappear. Invalid content falls back to the ordinary poll path.
def _rich_math_card_80(question, options, explanation="", lang="bn"):
    labels = globals().get("_LABELS_EN_79", []) if lang == "en" else globals().get("_LABELS_BN_79", [])
    clean = globals().get("mathify_79")
    render = clean if callable(clean) else _clean_mcq_text_80
    question_text = render(question)
    option_texts = [render(value) for value in (options or []) if _clean_mcq_text_80(value)]
    if not question_text or len(option_texts) < 2:
        return ""
    lines = ["**" + question_text + "**", "", "—", ""]
    for index, option in enumerate(option_texts):
        label = labels[index] if index < len(labels) else str(index + 1)
        lines.extend(["**(" + label + ")**  " + option, ""])
    return "\n".join(lines).strip()


globals()["_rich_math_card_78"] = _rich_math_card_80
globals()["_rich_math_card_79"] = _rich_math_card_80


_prev_blocks_80 = globals().get("_rich_math_blocks_79")


def _rich_math_blocks_80(question, options, lang="bn"):
    question_text = _clean_mcq_text_80(question)
    option_texts = [_clean_mcq_text_80(value) for value in (options or []) if _clean_mcq_text_80(value)]
    if not question_text or len(option_texts) < 2:
        return []
    if callable(_prev_blocks_80):
        blocks = _prev_blocks_80(question_text, option_texts, lang) or []
        # Paragraphs are separate native blocks; the divider leaves visual air.
        return blocks
    return []


globals()["_rich_math_blocks_79"] = _rich_math_blocks_80


# Final delivery guard: if the rich card wrapper fails after sending the card,
# retry the actual poll through PTB's original sender instead of leaving an
# orphan question card. RetryAfter is respected without blocking other updates.
_prev_send_poll_80 = _tg80.Bot.send_poll
_raw_send_poll_80 = globals().get("_PTB_SEND_POLL_78")


async def _send_poll_80(self, chat_id=None, question=None, options=None, *args, **kwargs):
    cid = kwargs.pop("chat_id", chat_id)
    stem = kwargs.pop("question", question)
    choices = kwargs.pop("options", options)
    stem = _clean_mcq_text_80(stem)
    choices = [_clean_mcq_text_80(getattr(value, "text", value)) for value in (choices or [])]
    choices = [value for value in choices if value]
    if not stem or len(choices) < 2:
        raise ValueError("Quiz rejected: question or options are incomplete")
    try:
        result = await _prev_send_poll_80(self, cid, stem, choices, *args, **kwargs)
        if result is not None:
            return result
    except RetryAfter as error:  # type: ignore[name-defined]
        await _a80.sleep(float(error.retry_after) + 0.5)
    except Exception as error:
        _log80("primary poll delivery failed; using raw recovery: %s" % error, "warning")
    if not callable(_raw_send_poll_80):
        raise RuntimeError("Quiz poll delivery failed")
    for attempt in range(2):
        try:
            return await _raw_send_poll_80(self, cid, stem, choices, *args, **kwargs)
        except RetryAfter as error:  # type: ignore[name-defined]
            await _a80.sleep(float(error.retry_after) + 0.5)
        except Exception:
            if attempt == 0:
                await _a80.sleep(1.2)
            else:
                raise


_tg80.Bot.send_poll = _send_poll_80
globals()["_send_poll_80"] = _send_poll_80


# ══════════════════════════════════════════════════════════════════════════════
# 2) OWNER AI-RICH TOPIC: DRAFT → REVIEW → REVISE → CONFIRM/PIN
# ══════════════════════════════════════════════════════════════════════════════

def _topic_db_init_80():
    with _cx80.suppress(Exception):
        connection = db_connect()  # type: ignore[name-defined]
        connection.execute(
            "CREATE TABLE IF NOT EXISTS ai_topic_drafts ("
            "owner_id INTEGER PRIMARY KEY, source_text TEXT NOT NULL, instructions TEXT, "
            "draft_text TEXT NOT NULL, target_type TEXT NOT NULL, target_serial INTEGER NOT NULL, "
            "sub_topic_id INTEGER, do_pin INTEGER NOT NULL DEFAULT 0, preview_chat_id INTEGER, "
            "preview_msg_id INTEGER, control_msg_id INTEGER, updated_at TEXT NOT NULL)"
        )
        connection.commit()
        connection.close()


_topic_db_init_80()


def _topic_save_80(owner_id, source, instructions, draft, target_type, serial, sub_topic_id,
                   do_pin, preview_chat_id=None, preview_msg_id=None, control_msg_id=None):
    connection = db_connect()  # type: ignore[name-defined]
    connection.execute(
        "INSERT INTO ai_topic_drafts(owner_id,source_text,instructions,draft_text,target_type,"
        "target_serial,sub_topic_id,do_pin,preview_chat_id,preview_msg_id,control_msg_id,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET "
        "source_text=excluded.source_text,instructions=excluded.instructions,draft_text=excluded.draft_text,"
        "target_type=excluded.target_type,target_serial=excluded.target_serial,sub_topic_id=excluded.sub_topic_id,"
        "do_pin=excluded.do_pin,preview_chat_id=excluded.preview_chat_id,preview_msg_id=excluded.preview_msg_id,"
        "control_msg_id=excluded.control_msg_id,updated_at=excluded.updated_at",
        (owner_id, source, instructions, draft, target_type, serial, sub_topic_id, int(bool(do_pin)),
         preview_chat_id, preview_msg_id, control_msg_id, dt.datetime.utcnow().isoformat()),  # type: ignore[name-defined]
    )
    connection.commit()
    connection.close()


def _topic_get_80(owner_id):
    connection = db_connect()  # type: ignore[name-defined]
    row = connection.execute("SELECT * FROM ai_topic_drafts WHERE owner_id=?", (owner_id,)).fetchone()
    connection.close()
    return dict(row) if row else None


def _topic_delete_80(owner_id):
    with _cx80.suppress(Exception):
        connection = db_connect()  # type: ignore[name-defined]
        connection.execute("DELETE FROM ai_topic_drafts WHERE owner_id=?", (owner_id,))
        connection.commit()
        connection.close()


def _topic_target_80(owner_id, target_type, serial, sub_topic_id=None):
    if target_type == "c":
        channel = channel_get_by_id_for_user(owner_id, serial)  # type: ignore[name-defined]
        if not channel:
            return None
        return int(channel.channel_chat_id), str(channel.title or channel.channel_chat_id), None
    group = _sg_get(serial, owner_id)  # type: ignore[name-defined]
    if not group:
        return None
    thread_id = None
    title = str(group.title or group.group_chat_id)
    if sub_topic_id is not None:
        topic = _gt_get(sub_topic_id)  # type: ignore[name-defined]
        if not topic or int(topic.group_id) != int(group.id):
            return None
        thread_id = topic.thread_id
        title += " › " + str(topic.topic_name)
    return int(group.group_chat_id), title, thread_id


def _parse_ai_topic_80(text, reply_text=""):
    body = _re80.sub(r"^[./]aitopic\b", "", str(text or "").strip(), flags=_re80.I).strip()
    do_pin = bool(_re80.search(r"(?:^|\s)pin(?:\s|$)", body, _re80.I))
    body = _re80.sub(r"(?:^|\s)pin(?:\s|$)", " ", body, flags=_re80.I).strip()
    match = _re80.search(r"(?:^|\s)([cg])(\d+)(?:\s+(\d+))?(?=\s|$)", body, _re80.I)
    if not match:
        return None
    target_type, serial = match.group(1).lower(), int(match.group(2))
    sub_topic_id = int(match.group(3)) if match.group(3) and target_type == "g" else None
    instructions = (body[:match.start()] + " " + body[match.end():]).strip()
    source = str(reply_text or "").strip()
    if source:
        instructions = instructions or "পেশাদার, পরিষ্কার ও পরীক্ষামুখী টপিক হেডার তৈরি করো"
    else:
        source, instructions = instructions, "পেশাদার, পরিষ্কার ও পরীক্ষামুখী টপিক হেডার তৈরি করো"
    return source, instructions, target_type, serial, sub_topic_id, do_pin


def _topic_prompt_80(source, instructions):
    return (
        "You are an expert educational editor. Create one polished Telegram rich-text topic header.\n"
        "Follow the owner's requested customization exactly. Keep the source facts accurate.\n"
        "Use concise Markdown: a strong title, short structured sections, useful bold emphasis, bullets, "
        "and valid $LaTeX$ only when math exists. Leave one blank line between sections.\n"
        "Do not mention AI, drafting, instructions, channels, quizzes, or this prompt. Do not use code fences.\n"
        "Return only the final topic content, maximum 3200 characters.\n\n"
        "OWNER CUSTOMIZATION:\n" + str(instructions or "")[:1200] +
        "\n\nSOURCE CONTENT:\n" + str(source or "")[:9000]
    )


def _generate_topic_sync_80(source, instructions):
    prompt = _topic_prompt_80(source, instructions)
    caller = globals().get("_adv_call_text")
    last_error = ""
    if callable(caller):
        try:
            result = caller(prompt, force_json=False, timeout=24)
            text = result[0] if isinstance(result, tuple) else result
            text = str(text or "").strip()
            if text:
                return text[:3800]
        except Exception as error:
            last_error = str(error)
    builtin = globals().get("call_gemini_text_rest")
    if callable(builtin):
        try:
            text = str(builtin(prompt, timeout_seconds=28, force_json=False) or "").strip()
            if text:
                return text[:3800]
        except Exception as error:
            last_error = str(error)
    raise RuntimeError(last_error or "No working AI provider is configured")


def _topic_keyboard_80(owner_id):
    return InlineKeyboardMarkup([  # type: ignore[name-defined]
        [InlineKeyboardButton("✅ Confirm", callback_data="ait80:send:%s" % owner_id),  # type: ignore[name-defined]
         InlineKeyboardButton("📌 Send & Pin", callback_data="ait80:pin:%s" % owner_id)],  # type: ignore[name-defined]
        [InlineKeyboardButton("🗑 Cancel", callback_data="ait80:cancel:%s" % owner_id)],  # type: ignore[name-defined]
    ])


async def _show_topic_review_80(update, context, owner_id, source, instructions, draft,
                                target_type, serial, sub_topic_id, do_pin):
    chat_id = update.effective_chat.id
    old = _topic_get_80(owner_id)
    for key in ("preview_msg_id", "control_msg_id"):
        if old and old.get(key):
            with _cx80.suppress(Exception):
                await context.bot.delete_message(chat_id=chat_id, message_id=int(old[key]))
    preview = None
    sender = globals().get("rich_send_77")
    if callable(sender):
        with _cx80.suppress(Exception):
            preview = await sender(context.bot, chat_id, draft)
    if preview is None:
        preview = await context.bot.send_message(chat_id=chat_id, text=draft[:4000])
    control = await context.bot.send_message(
        chat_id=chat_id,
        text=("👁 <b>AI Topic Review</b>\n\nএই preview-তে reply করে কী add/remove/modify করতে হবে লিখুন।\n"
              "পছন্দ হলে Confirm বা Send &amp; Pin চাপুন।"),
        parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
        reply_to_message_id=preview.message_id,
        allow_sending_without_reply=True,
        reply_markup=_topic_keyboard_80(owner_id),
    )
    _topic_save_80(owner_id, source, instructions, draft, target_type, serial, sub_topic_id,
                   do_pin, chat_id, preview.message_id, control.message_id)


async def cmd_aitopic_80(update, context):
    if not update.message or not update.effective_user or not is_owner(update.effective_user.id):  # type: ignore[name-defined]
        return
    owner_id = int(update.effective_user.id)
    reply = update.message.reply_to_message
    reply_text = str(getattr(reply, "text", None) or getattr(reply, "caption", None) or "").strip()
    parsed = _parse_ai_topic_80(update.message.text or "", reply_text)
    if not parsed:
        await update.message.reply_text(
            "Reply to source text: <code>.aitopic c1 [pin] [custom instructions]</code>\n"
            "Group/topic: <code>.aitopic g1 3 [pin] [instructions]</code>\n"
            "Inline: <code>.aitopic c1 তোমার topic/source</code>", parse_mode=ParseMode.HTML)  # type: ignore[name-defined]
        return
    source, instructions, target_type, serial, sub_topic_id, do_pin = parsed
    if len(source) < 3 or not _topic_target_80(owner_id, target_type, serial, sub_topic_id):
        await warn(update, "Invalid AI Topic", "Source text or target channel/group/topic was not found.")  # type: ignore[name-defined]
        return
    status = await update.message.reply_text("✨ AI topic draft তৈরি হচ্ছে…")
    try:
        draft = await _a80.wait_for(
            _a80.to_thread(_generate_topic_sync_80, source, instructions), timeout=45
        )
        with _cx80.suppress(Exception):
            await status.delete()
        await _show_topic_review_80(update, context, owner_id, source, instructions, draft,
                                    target_type, serial, sub_topic_id, do_pin)
    except Exception as error:
        with _cx80.suppress(Exception):
            await status.edit_text("⚠️ AI topic তৈরি হয়নি: " + str(error)[:220])


async def revise_aitopic_80(update, context):
    if not update.message or not update.effective_user or not is_owner(update.effective_user.id):  # type: ignore[name-defined]
        return
    reply = update.message.reply_to_message
    if not reply:
        return
    owner_id = int(update.effective_user.id)
    row = _topic_get_80(owner_id)
    if not row or int(reply.message_id) not in (
        int(row.get("preview_msg_id") or 0), int(row.get("control_msg_id") or 0)
    ):
        return
    revision = _clean_mcq_text_80(update.message.text)
    if len(revision) < 2:
        return
    combined = (str(row.get("instructions") or "") + "\nLatest revision: " + revision).strip()
    status = await update.message.reply_text("♻️ পরিবর্তন অনুযায়ী নতুন draft তৈরি হচ্ছে…")
    try:
        draft = await _a80.wait_for(
            _a80.to_thread(_generate_topic_sync_80, row["source_text"], combined), timeout=45
        )
        with _cx80.suppress(Exception):
            await status.delete()
        await _show_topic_review_80(
            update, context, owner_id, row["source_text"], combined, draft,
            row["target_type"], int(row["target_serial"]), row.get("sub_topic_id"), bool(row["do_pin"]),
        )
        raise ApplicationHandlerStop  # type: ignore[name-defined]
    except ApplicationHandlerStop:  # type: ignore[name-defined]
        raise
    except Exception as error:
        with _cx80.suppress(Exception):
            await status.edit_text("⚠️ Revision তৈরি হয়নি: " + str(error)[:220])
        raise ApplicationHandlerStop  # type: ignore[name-defined]


async def cb_aitopic_80(update, context):
    query = update.callback_query
    if not query or not update.effective_user or not is_owner(update.effective_user.id):  # type: ignore[name-defined]
        return
    match = _re80.fullmatch(r"ait80:(send|pin|cancel):(\d+)", query.data or "")
    if not match or int(match.group(2)) != int(update.effective_user.id):
        await query.answer("This draft is not yours.", show_alert=True)
        return
    owner_id = int(update.effective_user.id)
    row = _topic_get_80(owner_id)
    if not row:
        await query.answer("Draft expired.", show_alert=True)
        return
    action = match.group(1)
    if action == "cancel":
        _topic_delete_80(owner_id)
        await query.answer("Cancelled")
        with _cx80.suppress(Exception):
            await query.edit_message_text("🗑 AI topic draft cancelled.")
        return
    target = _topic_target_80(owner_id, row["target_type"], int(row["target_serial"]), row.get("sub_topic_id"))
    if not target:
        await query.answer("Target is unavailable.", show_alert=True)
        return
    chat_id, title, thread_id = target
    await query.answer("Sending…")
    sent = None
    try:
        composite_sender = globals().get("_send_topic_composite_81")
        if callable(composite_sender):
            with _cx80.suppress(Exception):
                sent = await composite_sender(
                    context, owner_id, chat_id, row["draft_text"], thread_id=thread_id
                )
        sender = globals().get("rich_send_77")
        if sent is None and callable(sender):
            with _cx80.suppress(Exception):
                sent = await sender(context.bot, chat_id, row["draft_text"], thread_id=thread_id)
        if sent is None:
            kwargs = {"chat_id": chat_id, "text": row["draft_text"][:4000]}
            if thread_id is not None:
                kwargs["message_thread_id"] = thread_id
            sent = await context.bot.send_message(**kwargs)
    except Exception as error:
        _log80("AI topic delivery failed: %s" % error, "warning")
        await query.answer("Topic পাঠানো যায়নি—draft রাখা হয়েছে। আবার চেষ্টা করুন।", show_alert=True)
        return
    if sent is None or not getattr(sent, "message_id", None):
        await query.answer("Topic delivery নিশ্চিত করা যায়নি—draft রাখা হয়েছে।", show_alert=True)
        return
    should_pin = action == "pin" or bool(row.get("do_pin"))
    pinned = False
    if should_pin:
        try:
            await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent.message_id,
                                               disable_notification=True)
            pinned = True
        except Exception as error:
            _log80("AI topic pin failed: %s" % error, "warning")
    _set_topic_anchor(owner_id, chat_id, sent.message_id, row["draft_text"])  # type: ignore[name-defined]
    name = _re80.sub(r"[*_`#]", "", str(row["draft_text"])).strip().split("\n", 1)[0][:50] or "AI Topic"
    with _cx80.suppress(Exception):
        _sta_save(owner_id, name, chat_id, sent.message_id, row["draft_text"])  # type: ignore[name-defined]
    _topic_delete_80(owner_id)
    with _cx80.suppress(Exception):
        await query.edit_message_text(
            "✅ <b>AI topic sent</b>\nTarget: <b>%s</b>\nPinned: <b>%s</b>\n\n"
            "পরবর্তী topic তৈরি বা <code>.cleartopic</code> না করা পর্যন্ত quiz-গুলো এটাকেই reply করবে।"
            % (_html80.escape(title), "Yes" if pinned else ("Failed" if should_pin else "No")),
            parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
        )


if "build_app" in globals():
    _prev_build_app_80 = build_app  # type: ignore[name-defined]

    def build_app():  # noqa: F811
        app = _prev_build_app_80()
        if "_register_dual_command" in globals():
            _register_dual_command(app, "aitopic", cmd_aitopic_80, group=-620)  # type: ignore[name-defined]
        else:
            app.add_handler(CommandHandler("aitopic", cmd_aitopic_80), group=-620)  # type: ignore[name-defined]
        app.add_handler(CallbackQueryHandler(cb_aitopic_80, pattern=r"^ait80:"), group=-620)  # type: ignore[name-defined]
        app.add_handler(
            MessageHandler(filters.TEXT & (~filters.COMMAND), revise_aitopic_80), group=-610  # type: ignore[name-defined]
        )
        return app


_log80("section 80 ready: strict quizzes, balanced answers, poll recovery, AI topics")
