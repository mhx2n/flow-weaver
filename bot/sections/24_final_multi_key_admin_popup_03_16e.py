# ──────────────────────────────────────────────────────────────────────────────
# Section: 24_final_multi_key_admin_popup_03_16e
# Original lines: 12449..12750
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL MULTI-KEY / ADMIN-POPUP PATCH (2026-03-16E) =====
# This block is placed immediately before __main__ so it wins over earlier duplicates.
# It keeps user-facing labels simple while improving failover and group admin UX.
USE_OFFICIAL_GEMINI_REST_FALLBACK = True
USE_GEMINI_REST_FOR_GENQUIZ = True
GEMINI_TIMEOUT_SECONDS = 16
GEMINI_TEXT_TIMEOUT_SECONDS = 10
GEMINI_VISION_TIMEOUT_SECONDS = 18
GEMINI_MODEL_TEXT = os.getenv("GEMINI_MODEL_TEXT", os.getenv("GEMINI_MODEL_PRIMARY", "models/gemini-3-flash-preview")).strip() or "models/gemini-3-flash-preview"
GEMINI_MODEL_VISION = os.getenv("GEMINI_MODEL_VISION", os.getenv("GEMINI_MODEL_FALLBACK", "models/gemini-2.5-flash")).strip() or "models/gemini-2.5-flash"


def _load_gemini_api_keys() -> List[str]:
    keys: List[str] = []
    seen: set[str] = set()

    def add(value: Optional[str]):
        for part in re.split(r"[\s,;\n]+", str(value or "")):
            k = part.strip()
            if not k:
                continue
            if k in seen:
                continue
            seen.add(k)
            keys.append(k)

    add(os.getenv("GEMINI_API_KEY", ""))
    add(os.getenv("GEMINI_API_KEYS", ""))

    indexed: List[Tuple[int, str]] = []
    for name, value in os.environ.items():
        m = re.fullmatch(r"GEMINI_API_KEY_(\d+)", name)
        if m and str(value or "").strip():
            indexed.append((int(m.group(1)), str(value).strip()))
    for _idx, value in sorted(indexed, key=lambda x: x[0]):
        add(value)

    return keys


GEMINI_API_KEYS = _load_gemini_api_keys()
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""

_FINAL_TUTORIAL_ALERT = (
    "শুধু গ্রুপ owner/admin-রা এই নির্দেশনা দেখতে পারবে।\n\n"
    "১) AI চালু: /probaho_on বা .probaho_on\n"
    "২) AI বন্ধ: /probaho_off বা .probaho_off\n"
    "৩) প্রশ্ন/রিপ্লাই: /sh বা .sh\n"
    "৪) রেঞ্জ ডিলিট: রিপ্লাই দিয়ে /porag\n"
    "৫) সাধারণ member-রা শুধু /sh বা .sh ব্যবহার করবে।\n"
    "৬) Bot reply group-এ auto-delete হবে।"
)


def _gemini_env_missing_message() -> str:
    return (
        "কোনো Gemini API key পাওয়া যায়নি।\n\n"
        "Render -> Environment এ <code>GEMINI_API_KEY</code> অথবা "
        "<code>GEMINI_API_KEY_1</code>, <code>GEMINI_API_KEY_2</code> ... সেট করে deploy/restart দিন।"
    )


def _all_text_model_candidates() -> List[str]:
    raw = os.getenv("GEMINI_TEXT_MODELS", "models/gemini-2.0-flash,models/gemini-2.5-flash,models/gemini-3-flash").strip()
    models: List[str] = []
    seen: set[str] = set()

    def add_model(v: Optional[str]):
        for part in re.split(r"[\s,;\n]+", str(v or "")):
            m = _normalize_model_name(part.strip()) if part.strip() else ""
            if not m or m in seen:
                continue
            seen.add(m)
            models.append(m)

    add_model(raw)
    add_model(GEMINI_MODEL_TEXT)
    for m in _candidate_gemini_models(GEMINI_MODEL_TEXT, want_vision=False, limit=4):
        add_model(m)
    # Safe fallback if preview access is unavailable.
    add_model("models/gemini-2.5-flash")
    return models or ["models/gemini-2.5-flash"]


def _all_vision_model_candidates() -> List[str]:
    raw = os.getenv("GEMINI_VISION_MODELS", "models/gemini-2.0-flash,models/gemini-2.5-flash").strip()
    models: List[str] = []
    seen: set[str] = set()

    def add_model(v: Optional[str]):
        for part in re.split(r"[\s,;\n]+", str(v or "")):
            m = _normalize_model_name(part.strip()) if part.strip() else ""
            if not m or m in seen:
                continue
            seen.add(m)
            models.append(m)

    add_model(raw)
    add_model(GEMINI_MODEL_VISION)
    for m in _candidate_gemini_models(GEMINI_MODEL_VISION, want_vision=True, limit=5):
        add_model(m)
    add_model("models/gemini-2.5-flash")
    return models or ["models/gemini-2.5-flash"]


def _call_gemini_generate_content_multi(model: str, payload: Dict[str, Any], *, timeout_seconds: int) -> str:
    model = _normalize_model_name(model)
    if not GEMINI_API_KEYS:
        raise RuntimeError("No Gemini API key configured.")

    last_err: Optional[Exception] = None
    for key in GEMINI_API_KEYS:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={key}"
        try:
            r = _requests_with_retries(
                requests.post,
                url,
                json_payload=payload,
                timeout=max(8, int(timeout_seconds or 10)),
                max_tries=1,
            )
            data = r.json()
            text = _extract_gemini_text_from_response(data)
            if text and str(text).strip():
                return str(text).strip()
            last_err = RuntimeError("Empty Gemini response")
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(str(last_err or "Gemini REST backend is unavailable."))


def call_gemini_text_rest(prompt: str, timeout_seconds: int = GEMINI_TEXT_TIMEOUT_SECONDS, *, force_json: bool = False) -> str:
    if not GEMINI_API_KEYS:
        raise RuntimeError("Gemini API key missing in Render environment.")

    last_err: Optional[Exception] = None
    json_modes = [True, False] if force_json else [False]
    models = _all_text_model_candidates()

    for use_json_mode in json_modes:
        payload = _build_gemini_text_payload(prompt, force_json=use_json_mode)
        for model in models:
            try:
                out = _call_gemini_generate_content_multi(model, payload, timeout_seconds=timeout_seconds)
                if out and str(out).strip():
                    return str(out).strip()
            except Exception as e:
                last_err = e
                continue

    raise RuntimeError(str(last_err or "Gemini REST text backend is unavailable."))


def call_gemini_vision_rest(image_path: str, prompt: str, force_json: bool = True) -> str:
    if not GEMINI_API_KEYS:
        raise RuntimeError("Gemini API key missing in Render environment.")

    last_err: Optional[Exception] = None
    json_modes = [True, False] if force_json else [False]
    models = _all_vision_model_candidates()

    for use_json_mode in json_modes:
        payload = _build_gemini_vision_payload(image_path, prompt, force_json=use_json_mode)
        for model in models:
            try:
                out = _call_gemini_generate_content_multi(model, payload, timeout_seconds=GEMINI_VISION_TIMEOUT_SECONDS)
                if out and str(out).strip():
                    return str(out).strip()
            except Exception as e:
                last_err = e
                continue

    raise RuntimeError(str(last_err or "Gemini vision backend is unavailable."))


def _try_gemini_text_backends(prompt: str, *, timeout_seconds: int = 10) -> Tuple[str, str]:
    last_error: Optional[Exception] = None

    # Fastest public-facing path requested by user: Web Gemini first, then official API key rotation.
    try:
        out = gemini3_solve(prompt)
        if out and str(out).strip():
            return str(out).strip(), "Gemini"
    except Exception as e:
        last_error = e

    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEYS:
        try:
            out = call_gemini_text_rest(prompt, timeout_seconds=timeout_seconds)
            if out and str(out).strip():
                return str(out).strip(), "Gemini"
        except Exception as e:
            last_error = e

    if USE_PERPLEXITY_FALLBACK:
        try:
            alt = query_ai(prompt)
            if alt and str(alt).strip():
                return str(alt).strip(), "Perplexity"
        except Exception as e:
            last_error = e

    raise RuntimeError(str(last_error or "AI backend is temporarily unavailable. Please try again."))


def _try_gemini_mcq_backends(question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:
    prompt, opts = _build_mcq_json_prompt(question, options)
    last_error: Optional[Exception] = None

    try:
        raw = gemini3_solve(prompt)
        data = _coerce_mcq_result(raw, len(opts))
        if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
            return data, "Gemini"
    except Exception as e:
        last_error = e

    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEYS:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=10, force_json=True)
            data = _coerce_mcq_result(raw, len(opts))
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "Gemini"
        except Exception as e:
            last_error = e

    if USE_PERPLEXITY_FALLBACK:
        try:
            alt = query_ai(prompt)
            data = _coerce_mcq_result(alt or "", len(opts))
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "Perplexity"
        except Exception as e:
            last_error = e

    raise RuntimeError(str(last_error or "AI backend is temporarily unavailable. Please try again."))


async def cmd_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    uid = update.effective_user.id if update.effective_user else 0
    chat_id = update.effective_chat.id
    if not await _is_group_admin_user(context, chat_id, uid):
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    with contextlib.suppress(Exception):
        await update.message.delete()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📘 Show Tutorial", callback_data="tutorial:show")]])
    sent = await context.bot.send_message(
        chat_id=chat_id,
        text="📘 Tutorial",
        reply_markup=kb,
        reply_to_message_id=None,
        allow_sending_without_reply=True,
    )
    asyncio.create_task(_auto_delete_after(context.bot, chat_id, [sent.message_id], 90))


async def on_tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.message or not q.message.chat:
        return
    uid = q.from_user.id if q.from_user else 0
    if not await _is_group_admin_user(context, q.message.chat.id, uid):
        await q.answer("Only group admins can view the tutorial.", show_alert=True)
        return
    await q.answer(_FINAL_TUTORIAL_ALERT, show_alert=True)


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
            f"ধন্যবাদ {h(actor_name)}, {h(BOT_BRAND)} বটটি group-এ add করার জন্য।\n"
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


