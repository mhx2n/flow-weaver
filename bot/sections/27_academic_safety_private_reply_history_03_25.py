# ──────────────────────────────────────────────────────────────────────────────
# Section: 27_academic_safety_private_reply_history_03_25
# Original lines: 13942..14514
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL ACADEMIC SAFETY + PRIVATE REPLY HISTORY PATCH (2026-03-25) =====
# Goal:
# 1) Do not falsely block study-related questions as 18+/explicit.
# 2) In private chat, replying to an AI response continues the same chat thread.
# 3) New normal question starts a new thread.
# 4) Conversation state is stored in SQLite, which is already synced to GitHub by existing backup logic.

_CHAT_HISTORY_MAX_TURNS = 12
_CHAT_HISTORY_MAX_CHARS = 5000

_STRONG_EXPLICIT_REQUEST_RE = re.compile(
    r"(?is)(?:\b(?:porn|porno|pornography|xxx|nsfw|nudes?|send nudes?|sex chat|sexting|blowjob|handjob|cumshot|anal sex|oral sex|dick pic|vagina pic|naked pic|erotic story|fetish|bdsm)\b|"
    r"পর্ন|পর্নো|নিউড পাঠা|নগ্ন ছবি|অশ্লীল ভিডিও|যৌন উত্তেজনা|সেক্স চ্যাট|ব্লোজব|হ্যান্ডজব|ওরাল সেক্স|পর্ন ভিডিও)"
)

_ACADEMIC_SENSITIVE_ALLOW_RE = re.compile(
    r"(?is)(?:\b(?:biology|botany|zoology|anatomy|physiology|medical|medicine|disease|symptom|treatment|drug|pharmacology|"
    r"reproduction|reproductive|fertilization|pollination|flower|seed|plant|taxonomy|classification|gymnosperm|angiosperm|ephedra|fungi|bacteria|virus|parasite|parasitism|"
    r"mutualism|commensalism|hormone|cell|chromosome|organ|ovary|ovule|anther|stamen|pistil|testis|uterus|sperm|zygote|embryo|leaf|root|stem|fruit|gene|genetics|evolution|ecology)\b|"
    r"জীববিজ্ঞান|বায়োলজি|উদ্ভিদবিদ্যা|প্রাণিবিদ্যা|শরীরতত্ত্ব|অঙ্গসংস্থান|রোগ|উপসর্গ|চিকিৎসা|ওষুধ|প্রজনন|নিষেক|পরাগায়ন|পরাগ|ফুল|বীজ|উদ্ভিদ|শ্রেণিবিন্যাস|ট্যাক্সোনমি|"
    r"সুপ্তবীজি|গুপ্তবীজি|আবৃতবীজি|অনাবৃতবীজি|জিমনোস্পার্ম|অ্যাঞ্জিওস্পার্ম|এফিড্রা|ব্যাকটেরিয়া|ভাইরাস|ছত্রাক|পরজীবী|পরজীবিতা|মিউচুয়ালিজম|সহবাস|সহাবস্থান|"
    r"হরমোন|কোষ|ক্রোমোজোম|অঙ্গ|ডিম্বাশয়|অণ্ডাশয়|ডিম্বক|পরাগধানী|পুংকেশর|স্ত্রীকেশর|শুক্রাণু|জাইগোট|ভ্রূণ|পাতা|মূল|কাণ্ড|ফল|জিন|জেনেটিক্স|বিবর্তন|পরিবেশবিদ্যা)"
)

_FALSE_REFUSAL_RE = re.compile(
    r"(?is)(?:18\+|explicit|adult content|sexual content|pornographic|nsfw|does not provide 18\+|cannot help with explicit|"
    r"দুঃখিত.*(?:১৮\+|explicit)|এই বট .*উত্তর দেয় না|উত্তর দেয় না|I can(?:not|'t) help with that|can't assist with that)"
)

_prev_db_init_20260325 = db_init

def _ai_history_db_init() -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_threads (
            thread_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            scope TEXT NOT NULL DEFAULT 'private_academic',
            origin TEXT NOT NULL DEFAULT 'private',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_thread_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model_code TEXT,
            model_name TEXT,
            telegram_chat_id INTEGER,
            telegram_message_id INTEGER,
            reply_to_message_id INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_thread_messages_thread ON ai_thread_messages(thread_id, id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_thread_messages_tg ON ai_thread_messages(telegram_chat_id, telegram_message_id)")
    conn.commit()
    conn.close()


def db_init() -> None:
    _prev_db_init_20260325()
    _ai_history_db_init()


def _new_ai_thread_id() -> str:
    return uuid.uuid4().hex


def ai_thread_create(user_id: int, chat_id: int, scope: str = "private_academic", origin: str = "private") -> str:
    thread_id = _new_ai_thread_id()
    ts = now_iso()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ai_threads(thread_id, user_id, chat_id, scope, origin, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (thread_id, int(user_id), int(chat_id), str(scope or 'private_academic'), str(origin or 'private'), ts, ts),
    )
    conn.commit()
    conn.close()
    return thread_id


def ai_thread_touch(thread_id: str) -> None:
    if not thread_id:
        return
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE ai_threads SET updated_at=? WHERE thread_id=?", (now_iso(), str(thread_id)))
    conn.commit()
    conn.close()


def ai_thread_get_scope(thread_id: str) -> str:
    if not thread_id:
        return ""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT scope FROM ai_threads WHERE thread_id=?", (str(thread_id),))
    row = cur.fetchone()
    conn.close()
    return str(row["scope"] or "") if row else ""


def ai_thread_lookup_by_bot_message(chat_id: int, message_id: int) -> Optional[str]:
    if not chat_id or not message_id:
        return None
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT thread_id FROM ai_thread_messages
        WHERE telegram_chat_id=? AND telegram_message_id=? AND role='assistant'
        ORDER BY id DESC LIMIT 1
        """,
        (int(chat_id), int(message_id)),
    )
    row = cur.fetchone()
    conn.close()
    return str(row["thread_id"]) if row and row["thread_id"] else None


def ai_thread_recent_messages(thread_id: str, limit: int = _CHAT_HISTORY_MAX_TURNS) -> List[sqlite3.Row]:
    if not thread_id:
        return []
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM ai_thread_messages WHERE thread_id=? ORDER BY id DESC LIMIT ?",
        (str(thread_id), max(1, int(limit or _CHAT_HISTORY_MAX_TURNS))),
    )
    rows = cur.fetchall()
    conn.close()
    rows = list(rows)[::-1]
    return rows


def _compact_history_text(s: str) -> str:
    s = str(s or "").strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > 900:
        s = s[:900] + "..."
    return s.strip()


def _build_thread_continuation_input(thread_id: str, new_user_text: str) -> str:
    rows = ai_thread_recent_messages(thread_id, _CHAT_HISTORY_MAX_TURNS)
    parts = []
    for row in rows:
        role = str(row["role"] or "")
        content = _compact_history_text(row["content"] or "")
        if not content:
            continue
        speaker = "User" if role == "user" else "Assistant"
        parts.append(f"{speaker}: {content}")
    history = "\n".join(parts).strip()
    if len(history) > _CHAT_HISTORY_MAX_CHARS:
        history = history[-_CHAT_HISTORY_MAX_CHARS:]
    new_user_text = str(new_user_text or "").strip()
    if history:
        return (
            "Continue the same private chat thread. Use the previous conversation when relevant. "
            "If the new user message changes the topic, answer the new message directly.\n\n"
            f"Conversation History:\n{history}\n\nCurrent User Message:\n{new_user_text}"
        ).strip()
    return new_user_text


def ai_thread_append_user_if_missing(thread_id: str, content: str, chat_id: int, message_id: int = 0, reply_to_message_id: int = 0) -> None:
    if not thread_id or not str(content or "").strip():
        return
    conn = db_connect()
    cur = conn.cursor()
    if message_id:
        cur.execute(
            "SELECT id FROM ai_thread_messages WHERE telegram_chat_id=? AND telegram_message_id=? AND role='user' ORDER BY id DESC LIMIT 1",
            (int(chat_id), int(message_id)),
        )
        row = cur.fetchone()
        if row:
            conn.close()
            ai_thread_touch(thread_id)
            return
    cur.execute(
        """
        INSERT INTO ai_thread_messages(thread_id, role, content, model_code, model_name, telegram_chat_id, telegram_message_id, reply_to_message_id, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (str(thread_id), 'user', str(content).strip(), '', '', int(chat_id or 0), int(message_id or 0), int(reply_to_message_id or 0), now_iso()),
    )
    conn.commit()
    conn.close()
    ai_thread_touch(thread_id)


def ai_thread_upsert_bot_answer(thread_id: str, content: str, chat_id: int, message_id: int, reply_to_message_id: int = 0, model_code: str = '', model_name: str = '') -> None:
    if not thread_id or not str(content or "").strip() or not chat_id or not message_id:
        return
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM ai_thread_messages WHERE telegram_chat_id=? AND telegram_message_id=? AND role='assistant' ORDER BY id DESC LIMIT 1",
        (int(chat_id), int(message_id)),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE ai_thread_messages SET thread_id=?, content=?, model_code=?, model_name=?, reply_to_message_id=? WHERE id=?",
            (str(thread_id), str(content).strip(), str(model_code or ''), str(model_name or ''), int(reply_to_message_id or 0), int(row['id'])),
        )
    else:
        cur.execute(
            """
            INSERT INTO ai_thread_messages(thread_id, role, content, model_code, model_name, telegram_chat_id, telegram_message_id, reply_to_message_id, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (str(thread_id), 'assistant', str(content).strip(), str(model_code or ''), str(model_name or ''), int(chat_id), int(message_id), int(reply_to_message_id or 0), now_iso()),
        )
    conn.commit()
    conn.close()
    ai_thread_touch(thread_id)


def _is_academic_safe_override(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    if _STRONG_EXPLICIT_REQUEST_RE.search(s):
        return False
    if _ACADEMIC_SENSITIVE_ALLOW_RE.search(s):
        return True
    if _STUDY_HINT_RE.search(s):
        return True
    return False


def _contains_adult_content(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    raw_match = bool(_ADULT_CONTENT_RE.search(s))
    if not raw_match:
        return False
    if _is_academic_safe_override(s):
        return False
    return True


def _looks_like_false_refusal(text: str) -> bool:
    return bool(_FALSE_REFUSAL_RE.search(str(text or "")))


def _build_academic_rescue_prompt(problem_text: str, scope: str = "private_academic") -> str:
    body = (
        "IMPORTANT ACADEMIC OVERRIDE:\n"
        "- The following message is a legitimate study / educational question.\n"
        "- It may include biology, botany, anatomy, disease, medicine, reproduction, plant names, or similar sensitive academic terms.\n"
        "- Do NOT misclassify such educational terms as 18+ or explicit.\n"
        "- Refuse only if the user is actually asking for obscene sexual entertainment, porn, erotic stimulation, or explicit adult content.\n\n"
        "Original User Message:\n"
        f"{str(problem_text or '').strip()}"
    ).strip()
    rescue_scope = "private_academic" if str(scope or '').startswith("private") else (scope or "group_general")
    return _build_solver_prompt(body, rescue_scope)


_prev_solve_text_with_preference_20260325 = _solve_text_with_preference

def _solve_text_with_preference(model: str, problem_text: str, scope: str = "private_academic") -> Tuple[str, str]:
    if _contains_adult_content(problem_text):
        return _adult_refusal_text(problem_text), _model_display_name(model)

    answer, used_model = _prev_solve_text_with_preference_20260325(model, problem_text, scope)

    if _is_academic_safe_override(problem_text) and _looks_like_false_refusal(answer):
        rescue_prompt = _build_academic_rescue_prompt(problem_text, scope)
        rescue_order = []
        for pref in ["P", "G", "D"]:
            if pref not in rescue_order:
                rescue_order.append(pref)
        if str(model or "").upper() in rescue_order:
            rescue_order.remove(str(model or "").upper())
            rescue_order.insert(0, str(model or "").upper())
        for pref in rescue_order:
            try:
                rescued, rescued_model = _solve_text_via_prompt(rescue_prompt, preferred=pref)
                if rescued and not _looks_like_false_refusal(rescued) and not _contains_adult_content(rescued):
                    return rescued, f"{rescued_model} (academic)"
            except Exception:
                continue

    if _contains_adult_content(answer) and not _is_academic_safe_override(problem_text):
        return _adult_refusal_text(problem_text), used_model or _model_display_name(model)

    return answer, used_model


_prev_classify_private_query_scope_20260325 = _classify_private_query_scope

def _classify_private_query_scope(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    if _contains_adult_content(s):
        return ""
    if _ACADEMIC_SENSITIVE_ALLOW_RE.search(s):
        return "private_academic"
    scope = _prev_classify_private_query_scope_20260325(s)
    if scope:
        return scope
    if re.search(r"(?is)(নাকি|or|vs|versus)", s) and _is_academic_safe_override(s):
        return "private_academic"
    return ""


async def send_solver_picker(update: Update, context: ContextTypes.DEFAULT_TYPE, problem_text: str, scope: Optional[str] = None, extra_payload: Optional[Dict[str, Any]] = None) -> None:
    if not update.message or not update.effective_user:
        return
    problem_text = (problem_text or "").strip()
    if not problem_text:
        return
    scope = str(scope or ("group_general" if update.effective_chat and update.effective_chat.type in ("group", "supergroup") else "private_academic"))
    if _contains_adult_content(problem_text):
        html = ui_box_html("Not Allowed", h(_adult_refusal_text(problem_text)), emoji="🚫")
        if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
            await _reply_group_temporary(update, context, html)
        else:
            await safe_reply(update, html)
        return
    token = _make_token()
    store = _pending_store(context)
    uid = update.effective_user.id
    payload = {
        "text": problem_text,
        "source_user_text": (extra_payload or {}).get("source_user_text") or (update.message.text or update.message.caption or problem_text),
        "source_message_id": int((extra_payload or {}).get("source_message_id") or update.message.message_id or 0),
        "source_reply_message_id": int((extra_payload or {}).get("source_reply_message_id") or (update.message.reply_to_message.message_id if update.message.reply_to_message else 0) or 0),
    }
    for k, v in (extra_payload or {}).items():
        if k not in payload:
            payload[k] = v
    store[token] = {
        "uid": uid,
        "chat_id": update.effective_chat.id if update.effective_chat else uid,
        "kind": "text",
        "scope": scope,
        "payload": payload,
    }
    kb = _solver_picker_kb(token)
    msg = ui_box_html("Which AI model?", f"<code>{h(problem_text[:100])}</code>", emoji="🧠")
    sent = await update.message.reply_text(msg, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        asyncio.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [sent.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


async def handle_user_text_unusual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = update.effective_user.id
    if is_banned(uid):
        return
    role = get_role(uid)
    private = is_private_chat(update)

    if role == ROLE_USER:
        if private:
            if not solver_mode_on(uid):
                await warn_unauthorized(update, "This bot is currently restricted for staff operations. Please use /ask [message] for support.")
                return
            if not await enforce_required_memberships(update, context):
                return
        else:
            if not is_group_ai_enabled(update.effective_chat.id):
                return
            if not await enforce_required_memberships(update, context):
                return
    elif role in (ROLE_ADMIN, ROLE_OWNER):
        if private:
            if not solver_mode_on(uid):
                return
        else:
            if not is_group_ai_enabled(update.effective_chat.id):
                return
    else:
        return

    user_text = (update.message.text or "").strip()
    if not user_text:
        return

    if _contains_adult_content(user_text):
        if private:
            await safe_reply(update, h(_adult_refusal_text(user_text)))
        else:
            await _reply_group_temporary(update, context, h(_adult_refusal_text(user_text)))
        return

    reply_msg = update.message.reply_to_message
    prompt = user_text
    scope = "group_general" if not private else ""
    extra_payload: Dict[str, Any] = {
        "source_user_text": user_text,
        "source_message_id": int(update.message.message_id or 0),
        "source_reply_message_id": int(reply_msg.message_id if reply_msg else 0),
    }

    if private:
        thread_id = None
        if reply_msg and update.effective_chat:
            thread_id = ai_thread_lookup_by_bot_message(update.effective_chat.id, reply_msg.message_id)
        if thread_id:
            scope = ai_thread_get_scope(thread_id) or "private_academic"
            prompt = _build_thread_continuation_input(thread_id, user_text)
            extra_payload["thread_id"] = thread_id
            await send_solver_picker(update, context, prompt, scope=scope, extra_payload=extra_payload)
            return

        if reply_msg:
            ctx = _get_quiz_context(context, reply_msg.message_id)
            if not ctx and getattr(reply_msg, 'poll', None):
                poll = reply_msg.poll
                ctx = {
                    "question": str(poll.question or "").strip(),
                    "options": [str(o.text).strip() for o in (poll.options or []) if str(o.text or '').strip()],
                    "official_ans": _poll_official_answer(poll),
                    "official_expl": str(getattr(poll, 'explanation', '') or '').strip(),
                }
            if ctx:
                qtext = str(ctx.get("question", "") or "").strip()
                opts = ctx.get("options", []) or []
                prompt = f"Question:\n{qtext}\n\nOptions:\n" + "\n".join([f"{_safe_letter(i+1)}. {o}" for i, o in enumerate(opts)]) + f"\n\nUser follow-up:\n{user_text}"
                scope = "private_academic"
                await send_solver_picker(update, context, prompt, scope=scope, extra_payload=extra_payload)
                return

        scope = _classify_private_query_scope(user_text)
        if not scope:
            await safe_reply(update, h(_private_prompt_request_text(user_text)))
            return
        await send_solver_picker(update, context, user_text, scope=scope, extra_payload=extra_payload)
        return

    # group flow keeps previous lightweight behavior
    if reply_msg:
        ctx = _get_quiz_context(context, reply_msg.message_id)
        if not ctx and getattr(reply_msg, 'poll', None):
            poll = reply_msg.poll
            ctx = {
                "question": str(poll.question or "").strip(),
                "options": [str(o.text).strip() for o in (poll.options or []) if str(o.text or '').strip()],
                "official_ans": _poll_official_answer(poll),
                "official_expl": str(getattr(poll, 'explanation', '') or '').strip(),
            }
        if ctx:
            qtext = str(ctx.get("question", "") or "").strip()
            opts = ctx.get("options", []) or []
            prompt = f"Question:\n{qtext}\n\nOptions:\n" + "\n".join([f"{_safe_letter(i+1)}. {o}" for i, o in enumerate(opts)]) + f"\n\nUser follow-up:\n{user_text}"
        elif reply_msg.text or reply_msg.caption:
            base = (reply_msg.text or reply_msg.caption or "").strip()
            if base:
                prompt = f"Context:\n{base}\n\nUser message:\n{user_text}"

    await _reply_group_ai_direct(update, context, prompt, scope="group_general")


async def on_solver_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return
    q = update.callback_query
    await q.answer("Processing…", show_alert=False)
    data = (q.data or "").strip()
    m = re.match(r"^solve:([GPD]):([0-9a-f]{6,16})$", data)
    if not m:
        return
    model = m.group(1)
    token = m.group(2)
    store = _pending_store(context)
    req = store.get(token)
    if not isinstance(req, dict):
        with contextlib.suppress(Exception):
            await q.edit_message_text("⚠️ This request has expired. Please send your question again.")
        return
    uid = int(req.get("uid") or 0)
    if q.from_user and q.from_user.id != uid:
        with contextlib.suppress(Exception):
            await q.answer("This is not your request.", show_alert=True)
        return

    payload = req.get("payload") or {}
    problem_text = str(payload.get("text") or "").strip()
    kind = str(req.get("kind") or "text").lower()
    scope = str(req.get("scope") or ("group_general" if q.message and q.message.chat and q.message.chat.type in ("group", "supergroup") else "private_academic"))

    with contextlib.suppress(Exception):
        await q.edit_message_text(ui_box_text("Solving", "Please wait… Processing your request.", emoji="⏳"), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    try:
        if kind == "poll" and payload.get("question"):
            question = str(payload.get("question", "")).strip()
            options = payload.get("options", [])
            result, model_name = await _run_blocking(_role_of(uid), _solve_mcq_with_preference, model, question, options)
            raw_expl = str(result.get("explanation", "") or "")
            clean_expl = clean_latex(raw_expl)
            raw_why_not = result.get("why_not", {}) or {}
            clean_why_not = {k: clean_latex(v) for k, v in raw_why_not.items()}
            msg_html = _format_user_poll_solution(
                question=question,
                options=options,
                model_ans=int(result.get("answer", 0) or 0),
                official_ans=int(payload.get("official_ans", 0) or 0),
                model_expl=f"[{model_name}]\n{clean_expl}".strip(),
                official_expl=str(payload.get("official_expl", "")).strip(),
                why_not=clean_why_not,
                conf=int(result.get("confidence", 0) or 0),
            )
            kb = _verify_kb(token, model, "poll")
            answer_for_store = clean_expl or raw_expl
            used_model_name = model_name
        else:
            if _contains_adult_content(problem_text):
                answer = _adult_refusal_text(problem_text)
                used_model_name = _model_display_name(model)
            else:
                answer, used_model_name = await _run_blocking(_role_of(uid), _solve_text_with_preference, model, problem_text, scope)
                if _contains_adult_content(answer) and not _is_academic_safe_override(problem_text):
                    answer = _adult_refusal_text(problem_text)
            preserve_code = (is_admin(uid) or is_owner(uid)) and (looks_like_programming_request(problem_text) or looks_like_programming_request(answer))
            msg_html = _answer_to_tg_html(answer, model_name=used_model_name, preserve_code=preserve_code)
            kb = _verify_kb(token, model, "text")
            answer_for_store = answer

        with contextlib.suppress(Exception):
            await q.edit_message_text(msg_html, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            if q.message and kind == "poll":
                _remember_quiz_context(context, q.message.message_id, payload)
            if q.message and kind == "text" and q.message.chat and q.message.chat.type == "private":
                thread_id = str(payload.get("thread_id") or "").strip()
                if not thread_id:
                    thread_id = ai_thread_create(uid, q.message.chat.id, scope if str(scope).startswith("private") else "private_academic", origin="private")
                    payload["thread_id"] = thread_id
                    req["payload"] = payload
                source_user_text = str(payload.get("source_user_text") or problem_text or "").strip()
                source_message_id = int(payload.get("source_message_id") or (q.message.reply_to_message.message_id if q.message.reply_to_message else 0) or 0)
                source_reply_message_id = int(payload.get("source_reply_message_id") or 0)
                ai_thread_append_user_if_missing(thread_id, source_user_text, q.message.chat.id, source_message_id, source_reply_message_id)
                ai_thread_upsert_bot_answer(thread_id, answer_for_store, q.message.chat.id, q.message.message_id, source_message_id, model_code=model, model_name=used_model_name)
                with contextlib.suppress(Exception):
                    upload_db_to_github(force=False)
            if q.message and q.message.chat and q.message.chat.type in ("group", "supergroup"):
                asyncio.create_task(_auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))
    except Exception as e:
        db_log("ERROR", "solver_callback_failed", {"user_id": uid, "model": model, "error": str(e)})
        with contextlib.suppress(Exception):
            await q.edit_message_text(h("AI backend is temporarily unavailable. Please try again."), parse_mode=ParseMode.HTML)
            if q.message and q.message.chat and q.message.chat.type in ("group", "supergroup"):
                asyncio.create_task(_auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))

# ===== END FINAL ACADEMIC SAFETY + PRIVATE REPLY HISTORY PATCH =====

_ensure_runtime_log_file_handler()
# ===== END FINAL COMMAND / LOG / PERSISTENCE PATCH =====


