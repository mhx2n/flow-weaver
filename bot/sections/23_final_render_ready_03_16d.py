# ──────────────────────────────────────────────────────────────────────────────
# Section: 23_final_render_ready_03_16d
# Original lines: 12020..12448
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL RENDER-READY PATCH (2026-03-16D) =====
# Final override block placed just before __main__ so it wins over earlier duplicates.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
USE_OFFICIAL_GEMINI_REST_FALLBACK = True
USE_GEMINI_REST_FOR_GENQUIZ = True
GEMINI_TIMEOUT_SECONDS = 18
GEMINI_TEXT_TIMEOUT_SECONDS = 12
GEMINI_VISION_TIMEOUT_SECONDS = 20

_FINAL_TUTORIAL_ALERT = (
    "১) /probaho_on বা .probaho_on দিয়ে AI চালু করুন।\n"
    "২) /sh বা .sh দিয়ে প্রশ্ন করুন।\n"
    "৩) Reply করে /sh দিলে reply-mode কাজ করবে।\n"
    "৪) Bot reply 10 মিনিটে auto-delete হবে।"
)
_FINAL_TUTORIAL_ALERT = _FINAL_TUTORIAL_ALERT[:190]


def _gemini_env_missing_message() -> str:
    return (
        "GEMINI_API_KEY পাওয়া যায়নি।\n\n"
        "Render -> Environment এ <code>GEMINI_API_KEY</code> সেট করে deploy/restart দিন।"
    )


def query_ai(prompt: str) -> str | None:
    """Perplexity HTTP client with lower timeout for faster UX."""
    if not USE_PERPLEXITY_FALLBACK:
        return None
    try:
        r = requests.get(PERPLEXITY_API, params={"prompt": prompt}, timeout=18)
        if r.status_code != 200:
            logging.error("Perplexity HTTP %s: %s", r.status_code, (r.text or "")[:1500])
            return None
        data = r.json()
        if data.get("status") == "success" and "answer" in data:
            return str(data["answer"]).strip()
        logging.error("Perplexity bad response: %s", str(data)[:1500])
        return None
    except Exception as e:
        logging.exception("Perplexity error: %s", e)
        return None


def _call_gemini_generate_content(model: str, payload: Dict[str, Any], *, timeout_seconds: int) -> str:
    model = _normalize_model_name(model)
    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_API_KEY}"
    try:
        r = _requests_with_retries(
            requests.post,
            url,
            json_payload=payload,
            timeout=max(8, int(timeout_seconds or 12)),
            max_tries=2,
        )
    except RateLimitError:
        raise
    except Exception as e:
        response = getattr(e, "response", None)
        status = getattr(response, "status_code", None)
        body = getattr(response, "text", "")
        if status is not None:
            raise RuntimeError(f"Gemini API error {status}: {str(body)[:600]}") from e
        raise
    data = r.json()
    return _extract_gemini_text_from_response(data)


def call_gemini_text_rest(prompt: str, timeout_seconds: int = GEMINI_TEXT_TIMEOUT_SECONDS, *, force_json: bool = False) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing in Render environment.")

    candidates = _candidate_gemini_models(GEMINI_MODEL_TEXT, want_vision=False, limit=3)
    last_err: Optional[Exception] = None
    json_modes = [True, False] if force_json else [False]

    for use_json_mode in json_modes:
        payload = _build_gemini_text_payload(prompt, force_json=use_json_mode)
        for model in candidates:
            try:
                out = _call_gemini_generate_content(model, payload, timeout_seconds=timeout_seconds)
                if out and str(out).strip():
                    return str(out).strip()
            except Exception as e:
                last_err = e
                continue

    raise RuntimeError(str(last_err or "Gemini REST text backend is unavailable."))


def call_gemini_vision_rest(image_path: str, prompt: str, force_json: bool = True) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing in Render environment.")

    candidates = _candidate_gemini_models(GEMINI_MODEL_VISION, want_vision=True, limit=4)
    last_err: Optional[Exception] = None
    json_modes = [True, False] if force_json else [False]

    for use_json_mode in json_modes:
        payload = _build_gemini_vision_payload(image_path, prompt, force_json=use_json_mode)
        for model in candidates:
            try:
                out = _call_gemini_generate_content(model, payload, timeout_seconds=GEMINI_VISION_TIMEOUT_SECONDS)
                if out and str(out).strip():
                    return str(out).strip()
            except Exception as e:
                last_err = e
                continue

    raise RuntimeError(str(last_err or "Gemini vision backend is unavailable."))


def gemini_extract_mcq_from_image_rest(image_path: str) -> List[Dict[str, Any]]:
    prompt = (
        "You are an exam question extractor.\n"
        "From the given image, extract ALL MCQ questions exactly as shown.\n"
        "Return STRICT JSON only (no markdown, no commentary, no extra text).\n\n"
        "Output format:\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "questions": "...",\n'
        '      "option1": "...",\n'
        '      "option2": "...",\n'
        '      "option3": "...",\n'
        '      "option4": "...",\n'
        '      "option5": "",\n'
        '      "answer": 0,\n'
        '      "explanation": "..."\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Keep Bengali/English text exactly as shown.\n"
        "- Preserve math symbols and option order carefully.\n"
        "- If an option is missing, keep it as an empty string.\n"
        "- answer must be 1-5. If unknown, use 0.\n"
        "- If the correct option is marked/ticked/highlighted/written, set answer accordingly.\n"
        "- explanation must be short and exam-style.\n"
        "- Never invent a question that is not visible in the image.\n"
    )

    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            raw = call_gemini_vision_rest(image_path, prompt, force_json=True)
            try:
                data = _extract_json_strict(raw)
            except Exception:
                data = _repair_to_json(raw, schema_hint=_IMAGE_JSON_SCHEMA_HINT, timeout_seconds=12)
            if not isinstance(data, dict):
                raise RuntimeError("Vision model did not return valid JSON.")

            items = data.get("items", []) or []
            out: List[Dict[str, Any]] = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                answer = int(it.get("answer", 0) or 0)
                if answer < 0 or answer > 5:
                    answer = 0
                out.append({
                    "questions": str(it.get("questions", "")).strip(),
                    "option1": str(it.get("option1", "")).strip(),
                    "option2": str(it.get("option2", "")).strip(),
                    "option3": str(it.get("option3", "")).strip(),
                    "option4": str(it.get("option4", "")).strip(),
                    "option5": str(it.get("option5", "")).strip(),
                    "answer": answer,
                    "explanation": str(it.get("explanation", "")).strip(),
                    "type": 1,
                    "section": 1,
                })
            out = [x for x in out if x.get("questions")]
            if out:
                return out
            raise RuntimeError("No MCQ items were extracted from the image.")
        except Exception as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))

    raise RuntimeError(f"Image extraction failed: {last_err}")


def _public_model_name(model_code: str, fallback: str = "AI") -> str:
    code = str(model_code or "").upper()
    if code == "G":
        return "Gemini"
    if code == "P":
        return "Perplexity"
    if code == "D":
        return "DeepSeek"
    return fallback


def _model_display_name(model_code: str, fallback: str = "AI") -> str:
    return _public_model_name(model_code, fallback)


def _solver_picker_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✨ Gemini", callback_data=f"solve:G:{token}"),
            InlineKeyboardButton("⚛ Perplexity", callback_data=f"solve:P:{token}"),
        ]
    ])


def _try_gemini_text_backends(prompt: str, *, timeout_seconds: int = 12) -> Tuple[str, str]:
    last_error: Optional[Exception] = None

    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEY:
        try:
            out = call_gemini_text_rest(prompt, timeout_seconds=timeout_seconds)
            if out and str(out).strip():
                return str(out).strip(), "Gemini REST"
        except Exception as e:
            last_error = e

    try:
        out = gemini3_solve(prompt)
        if out and str(out).strip():
            return str(out).strip(), "Gemini Web"
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


def _solve_text_via_prompt(prompt: str, preferred: str = "G") -> Tuple[str, str]:
    code = (preferred or "G").upper()
    if code == "P":
        try:
            out = query_ai(prompt)
            if out and str(out).strip():
                return str(out).strip(), "Perplexity"
        except Exception:
            pass
        return _try_gemini_text_backends(prompt, timeout_seconds=12)
    if code == "D":
        try:
            out = deepseek_solve_text(prompt)
            if out and str(out).strip():
                return str(out).strip(), "DeepSeek"
        except Exception:
            pass
        return _try_gemini_text_backends(prompt, timeout_seconds=12)
    return _try_gemini_text_backends(prompt, timeout_seconds=12)


def gemini_solve_text(problem_text: str) -> str:
    prompt = _build_solver_prompt(problem_text, "private_academic")
    out, _backend = _try_gemini_text_backends(prompt, timeout_seconds=12)
    return out


def _try_gemini_mcq_backends(question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:
    prompt, opts = _build_mcq_json_prompt(question, options)
    last_error: Optional[Exception] = None

    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEY:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=12, force_json=True)
            data = _coerce_mcq_result(raw, len(opts))
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "Gemini REST"
        except Exception as e:
            last_error = e

    try:
        raw = gemini3_solve(prompt)
        data = _coerce_mcq_result(raw, len(opts))
        if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
            return data, "Gemini Web"
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


def gemini_solve_mcq_json(question: str, options: List[str]) -> Dict[str, Any]:
    data, _backend = _try_gemini_mcq_backends(question, options)
    return data


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Private image/scan -> extract MCQs into buffer. Owner/Admin always eligible; others need vision grant."""
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = update.effective_user.id
    if is_banned(uid):
        return
    if not is_private_chat(update):
        return
    if not can_use_vision(uid):
        return
    if not vision_mode_on(uid):
        return

    if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
        await warn(update, "Buffer Limit Reached", f"You have {MAX_BUFFERED_QUESTIONS} questions buffered.\n\nUse /done to export or /clear to reset.")
        return

    msg = update.message
    tg_file = None
    if msg.photo:
        tg_file = await msg.photo[-1].get_file()
    elif msg.document and getattr(msg.document, 'mime_type', '').startswith('image/'):
        tg_file = await msg.document.get_file()
    else:
        return

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        local_path = f.name

    await tg_file.download_to_drive(local_path)

    try:
        if not GEMINI_API_KEY:
            await safe_reply(update, f"❌ {ui_box_html('Gemini API Key Missing', _gemini_env_missing_message(), emoji='❌')}")
            return

        items = await _run_blocking(_role_of(uid), gemini_extract_mcq_from_image_rest, local_path)

        added = 0
        for payload in items:
            if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
                break
            if not explain_mode_on(uid):
                payload["explanation"] = ""
            buffer_add(uid, payload)
            added += 1

        if added:
            await ok_html(update, "Image Processed", f"<code>{h(added)}</code> question(s) extracted.\n\nTotal buffered: <code>{h(buffer_count(uid))}</code>", footer_html="Use <code>/done</code> to export")
        else:
            await warn(update, "No Questions Found", "No MCQs detected in image. Try a clearer scan or tighter crop.")
    except Exception as e:
        db_log("ERROR", "image_extract_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Image Extraction Failed", f"{h(str(e)[:220])}")
    finally:
        with contextlib.suppress(Exception):
            os.remove(local_path)


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
            f"ধন্যবাদ {h(actor_name)}, {h(BOT_BRAND)} বটটি group-এ add করার জন্য।\n\n"
            "AI চালু করতে <code>/probaho_on</code> বা <code>.probaho_on</code> দিন।\n"
            "ব্যবহার করতে <code>/sh</code> বা <code>.sh</code> দিন।\n"
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




