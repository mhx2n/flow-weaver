# ──────────────────────────────────────────────────────────────────────────────
# Section: 22_final_stable_ux_gemini_routing_03_16c
# Original lines: 11319..12019
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL STABLE UX + GEMINI ROUTING PATCH (2026-03-16C) =====
# This patch intentionally overrides earlier duplicated definitions.
USE_OFFICIAL_GEMINI_REST_FALLBACK = True
USE_GEMINI_REST_FOR_GENQUIZ = True

_GEMINI_MODELS_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_IMAGE_JSON_SCHEMA_HINT = (
    '{"items":[{"questions":"","option1":"","option2":"","option3":"",'
    '"option4":"","option5":"","answer":0,"explanation":""}]}'
)


def _list_gemini_models_cached(ttl_seconds: int = 300) -> Dict[str, Any]:
    now = time.time()
    cached = _GEMINI_MODELS_CACHE.get("data")
    ts = float(_GEMINI_MODELS_CACHE.get("ts") or 0.0)
    if cached and (now - ts) < max(30, int(ttl_seconds or 300)):
        return cached
    data = list_gemini_models()
    _GEMINI_MODELS_CACHE["data"] = data
    _GEMINI_MODELS_CACHE["ts"] = now
    return data


def _normalize_model_name(name: str) -> str:
    n = str(name or "").strip()
    if not n:
        return ""
    return n if n.startswith("models/") else f"models/{n}"


def _candidate_gemini_models(preferred: str, *, want_vision: bool = False, limit: int = 6) -> List[str]:
    preferred = _normalize_model_name(preferred)
    blocked_keywords = (
        "embedding",
        "image-4",
        "veo",
        "tts",
        "audio",
        "dialog",
        "robotics",
        "computer-use",
        "research",
        "aqa",
        "generate-image",
    )
    static_fallbacks = [
        preferred,
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash",
        "models/gemini-1.5-flash",
        "models/gemini-2.5-pro",
        "models/gemini-1.5-pro",
    ]
    seen = set()
    items: List[str] = []

    def add(name: str) -> None:
        n = _normalize_model_name(name)
        if not n or n in seen:
            return
        seen.add(n)
        items.append(n)

    for name in static_fallbacks:
        add(name)

    try:
        data = _list_gemini_models_cached()
        for model in data.get("models", []) or []:
            name = _normalize_model_name(model.get("name", ""))
            methods = [str(x).lower() for x in (model.get("supportedGenerationMethods", []) or [])]
            if "generatecontent" not in methods:
                continue
            low = name.lower()
            if any(bad in low for bad in blocked_keywords):
                continue
            if want_vision:
                # For image understanding we prefer multimodal flash/pro families only.
                if not any(tag in low for tag in ("flash", "pro")):
                    continue
            add(name)
    except Exception as e:
        logging.warning("Gemini model discovery failed: %s", e)

    def score(name: str) -> int:
        low = name.lower()
        s = 0
        if preferred and name == preferred:
            s += 10000
        if "2.5-flash" in low:
            s += 950
        elif "2.0-flash" in low:
            s += 900
        elif "1.5-flash" in low:
            s += 850
        elif "2.5-pro" in low:
            s += 820
        elif "1.5-pro" in low:
            s += 780
        elif "flash-lite" in low or low.endswith("lite"):
            s += 740
        elif "flash" in low:
            s += 700
        elif "pro" in low:
            s += 650
        if "preview" in low:
            s -= 20
        if "exp" in low:
            s -= 30
        return s

    ordered = sorted(items, key=score, reverse=True)
    return ordered[: max(1, int(limit or 6))]


def _extract_gemini_text_from_response(data: Dict[str, Any]) -> str:
    candidates = data.get("candidates", []) or []
    if not candidates:
        feedback = data.get("promptFeedback", {}) or {}
        block_reason = str(feedback.get("blockReason") or "").strip()
        if block_reason:
            raise RuntimeError(f"Gemini returned no candidates (blockReason={block_reason}).")
        raise RuntimeError("Gemini returned no candidates.")

    cand0 = candidates[0] or {}
    content = cand0.get("content", {}) or {}
    parts = content.get("parts", []) or []
    texts = []
    for part in parts:
        if isinstance(part, dict):
            t = str(part.get("text") or "").strip()
            if t:
                texts.append(t)
    if texts:
        return "\n".join(texts).strip()

    finish_reason = str(cand0.get("finishReason") or "").strip()
    if finish_reason:
        raise RuntimeError(f"Gemini returned no text (finishReason={finish_reason}).")
    raise RuntimeError("Unexpected Gemini response format (no text parts).")


def _call_gemini_generate_content(model: str, payload: Dict[str, Any], *, timeout_seconds: int) -> str:
    model = _normalize_model_name(model)
    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_API_KEY}"
    try:
        r = _requests_with_retries(
            requests.post,
            url,
            json_payload=payload,
            timeout=timeout_seconds,
            max_tries=3,
        )
    except RateLimitError:
        raise
    except Exception as e:
        response = getattr(e, "response", None)
        status = getattr(response, "status_code", None)
        body = getattr(response, "text", "")
        if status is not None:
            raise RuntimeError(f"Gemini API error {status}: {str(body)[:800]}") from e
        raise

    data = r.json()
    return _extract_gemini_text_from_response(data)


def _build_gemini_text_payload(prompt: str, *, force_json: bool = False) -> Dict[str, Any]:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.9,
            "maxOutputTokens": 2048,
        },
    }
    if force_json:
        payload.setdefault("generationConfig", {})["responseMimeType"] = "application/json"
    return payload


def _build_gemini_vision_payload(image_path: str, prompt: str, *, force_json: bool = False) -> Dict[str, Any]:
    import mimetypes

    mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    if not str(mime_type).startswith("image/"):
        mime_type = "image/jpeg"

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": img_b64}},
            ],
        }],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.9,
            "maxOutputTokens": 4096,
        },
    }
    if force_json:
        payload.setdefault("generationConfig", {})["responseMimeType"] = "application/json"
    return payload


def call_gemini_text_rest(prompt: str, timeout_seconds: int = GEMINI_TEXT_TIMEOUT_SECONDS, *, force_json: bool = False) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set inside the code.")

    candidates = _candidate_gemini_models(GEMINI_MODEL_TEXT, want_vision=False, limit=6)
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
        raise RuntimeError("GEMINI_API_KEY is not set inside the code.")

    candidates = _candidate_gemini_models(GEMINI_MODEL_VISION, want_vision=True, limit=8)
    last_err: Optional[Exception] = None
    json_modes = [True, False] if force_json else [False]

    for use_json_mode in json_modes:
        payload = _build_gemini_vision_payload(image_path, prompt, force_json=use_json_mode)
        for model in candidates:
            try:
                out = _call_gemini_generate_content(model, payload, timeout_seconds=GEMINI_TEXT_TIMEOUT_SECONDS)
                if out and str(out).strip():
                    return str(out).strip()
            except Exception as e:
                last_err = e
                continue

    raise RuntimeError(str(last_err or "Gemini vision backend is unavailable."))


def _coerce_mcq_result(raw_text: str, option_count: int) -> Optional[Dict[str, Any]]:
    raw = str(raw_text or "").strip()
    if not raw:
        return None
    data = None
    try:
        data = _extract_json_strict(raw)
    except Exception:
        data = _repair_to_json(
            raw,
            schema_hint='{"answer":1,"confidence":0,"explanation":"...","why_not":{"A":"..","B":"..","C":"..","D":"..","E":".."}}',
            timeout_seconds=18,
        )
    if isinstance(data, dict):
        ans = int(data.get("answer", 0) or 0)
        if not (1 <= ans <= option_count):
            ans = _infer_option_from_text(raw, option_count)
        explanation = str(data.get("explanation", "") or "").strip() or raw[:1800]
        why_not = data.get("why_not", {}) if isinstance(data.get("why_not", {}), dict) else {}
        result = {
            "answer": ans,
            "confidence": int(data.get("confidence", 0) or 0),
            "explanation": explanation,
            "why_not": why_not,
        }
        if result["answer"] > 0:
            return result
    inferred = _infer_option_from_text(raw, option_count)
    if inferred > 0:
        return {
            "answer": inferred,
            "confidence": 0,
            "explanation": raw[:1800],
            "why_not": {},
        }
    return None


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
        "- Preserve mathematical symbols and option order carefully.\n"
        "- If an option is missing, keep it as an empty string.\n"
        "- answer must be 1-5. If unknown, use 0.\n"
        "- If the correct option is marked/ticked/highlighted/written, set answer accordingly.\n"
        "- explanation must be short and exam-style.\n"
        "- Never invent a question that is not visible in the image.\n"
    )

    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            raw = call_gemini_vision_rest(image_path, prompt, force_json=True)
            try:
                data = _extract_json_strict(raw)
            except Exception:
                data = _repair_to_json(raw, schema_hint=_IMAGE_JSON_SCHEMA_HINT, timeout_seconds=20)
            if not isinstance(data, dict):
                raise RuntimeError("Vision model did not return valid JSON.")

            items = data.get("items", []) or []
            out: List[Dict[str, Any]] = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                out.append({
                    "questions": str(it.get("questions", "")).strip(),
                    "option1": str(it.get("option1", "")).strip(),
                    "option2": str(it.get("option2", "")).strip(),
                    "option3": str(it.get("option3", "")).strip(),
                    "option4": str(it.get("option4", "")).strip(),
                    "option5": str(it.get("option5", "")).strip(),
                    "answer": int(it.get("answer", 0) or 0),
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
            time.sleep(1.0 * (attempt + 1))

    raise RuntimeError(f"Image extraction failed: {last_err}")


def can_use_vision(user_id: int) -> bool:
    """Owner/Admin always can. Others need explicit grant."""
    if is_admin(user_id) or is_owner(user_id):
        return True
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT can_use_vision FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    return int(row["can_use_vision"] or 0) == 1


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


def _try_gemini_text_backends(prompt: str, *, timeout_seconds: int = 18) -> Tuple[str, str]:
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
    model = (preferred or "G").upper()

    if model == "P":
        try:
            out = query_ai(prompt)
            if out and str(out).strip():
                return str(out).strip(), "Perplexity"
        except Exception:
            pass
        return _try_gemini_text_backends(prompt, timeout_seconds=18)

    if model == "D":
        try:
            out = deepseek_solve_text(prompt)
            if out and str(out).strip():
                return str(out).strip(), "DeepSeek"
        except Exception:
            pass
        return _try_gemini_text_backends(prompt, timeout_seconds=18)

    return _try_gemini_text_backends(prompt, timeout_seconds=18)


def gemini_solve_text(problem_text: str) -> str:
    prompt = _build_solver_prompt(problem_text, "private_academic")
    out, _backend = _try_gemini_text_backends(prompt, timeout_seconds=18)
    return out


def _try_gemini_mcq_backends(question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:
    prompt, opts = _build_mcq_json_prompt(question, options)
    last_error: Optional[Exception] = None

    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEY:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=18, force_json=True)
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


def _solve_mcq_with_preference(model: str, question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:
    code = (model or "G").upper()
    if code == "P":
        try:
            return perplexity_solve_mcq_json(question, options), "Perplexity"
        except Exception:
            return _try_gemini_mcq_backends(question, options)
    if code == "D":
        try:
            return deepseek_solve_mcq_json(question, options), "DeepSeek"
        except Exception:
            return _try_gemini_mcq_backends(question, options)
    return _try_gemini_mcq_backends(question, options)


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if vision_mode_on(uid):
        return await globals()["_original_handle_image"](update, context)
    if uid and get_role(uid) in (ROLE_ADMIN, ROLE_OWNER) and is_private_chat(update) and solver_mode_on(uid):
        return
    return await globals()["_original_handle_image"](update, context)


async def _reply_group_ai_direct(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_text: str, scope: str = "group_general") -> None:
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    spinner = await update.message.reply_text("🤖 ভাবছি...")
    try:
        uid = update.effective_user.id if update.effective_user else 0
        answer, backend_used = await _run_blocking(_role_of(uid), _solve_text_with_preference, "G", prompt_text, scope)
        if _contains_adult_content(answer):
            answer = _adult_refusal_text(prompt_text)
        preserve_code = looks_like_programming_request(prompt_text) or looks_like_programming_request(answer)
        html = _answer_to_tg_html(answer, model_name="Gemini", preserve_code=preserve_code)
        await spinner.edit_text(html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        db_log("INFO", "group_text_backend", {"user_id": uid, "requested": "G", "backend": backend_used})
    except Exception as e:
        db_log("ERROR", "group_text_ai_failed", {"user_id": update.effective_user.id if update.effective_user else 0, "error": str(e)})
        fail_html = h("AI backend is temporarily unavailable. Please try again.")
        with contextlib.suppress(Exception):
            await spinner.edit_text(fail_html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    finally:
        asyncio.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [spinner.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


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
    public_name = _public_model_name(model, "AI")
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
            result, backend_used = await _run_blocking(_role_of(uid), _solve_mcq_with_preference, model, question, options)
            raw_expl = str(result.get("explanation", "") or "")
            clean_expl = clean_latex(raw_expl)
            raw_why_not = result.get("why_not", {}) or {}
            clean_why_not = {k: clean_latex(v) for k, v in raw_why_not.items()}
            msg_html = _format_user_poll_solution(
                question=question,
                options=options,
                model_ans=int(result.get("answer", 0) or 0),
                official_ans=int(payload.get("official_ans", 0) or 0),
                model_expl=f"[{public_name}]\n{clean_expl}".strip(),
                official_expl=str(payload.get("official_expl", "")).strip(),
                why_not=clean_why_not,
                conf=int(result.get("confidence", 0) or 0),
            )
            kb = _verify_kb(token, model, "poll")
            db_log("INFO", "solver_poll_backend", {"user_id": uid, "requested": model, "backend": backend_used})
        else:
            if _contains_adult_content(problem_text):
                answer = _adult_refusal_text(problem_text)
                backend_used = "adult_refusal"
            else:
                answer, backend_used = await _run_blocking(_role_of(uid), _solve_text_with_preference, model, problem_text, scope)
                if _contains_adult_content(answer):
                    answer = _adult_refusal_text(problem_text)
            preserve_code = (is_admin(uid) or is_owner(uid)) and (looks_like_programming_request(problem_text) or looks_like_programming_request(answer))
            msg_html = _answer_to_tg_html(answer, model_name=public_name, preserve_code=preserve_code)
            kb = _verify_kb(token, model, "text")
            db_log("INFO", "solver_text_backend", {"user_id": uid, "requested": model, "backend": backend_used, "scope": scope})

        with contextlib.suppress(Exception):
            await q.edit_message_text(msg_html, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            if q.message and kind == "poll":
                _remember_quiz_context(context, q.message.message_id, payload)
            if q.message and q.message.chat and q.message.chat.type in ("group", "supergroup"):
                asyncio.create_task(_auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))
    except Exception as e:
        db_log("ERROR", "solver_callback_failed", {"user_id": uid, "model": model, "error": str(e)})
        with contextlib.suppress(Exception):
            await q.edit_message_text(h("AI backend is temporarily unavailable. Please try again."), parse_mode=ParseMode.HTML)
            if q.message and q.message.chat and q.message.chat.type in ("group", "supergroup"):
                asyncio.create_task(_auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


async def handle_user_poll_solver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.effective_user or not update.message or not update.message.poll:
        return
    uid = update.effective_user.id
    if is_banned(uid):
        return
    if not await enforce_required_memberships(update, context):
        return

    role = get_role(uid)
    private = is_private_chat(update)
    if role == ROLE_USER:
        if not solver_mode_on(uid):
            return
        if not private and not is_group_ai_enabled(update.effective_chat.id):
            return
    elif role in (ROLE_ADMIN, ROLE_OWNER):
        if not private or not solver_mode_on(uid):
            return
    else:
        return

    poll = update.message.poll
    qtext = (poll.question or "").strip()
    options = [str(o.text).strip() for o in (poll.options or []) if str(o.text or "").strip()]
    official_expl = str(getattr(poll, "explanation", "") or "").strip()
    official_ans = _poll_official_answer(poll)

    spinner_msg = None
    spinner_task = None
    try:
        spinner_msg = await update.message.reply_text("🔎 Searching")
        spinner_task = asyncio.create_task(_spinner_task(context.bot, spinner_msg.chat_id, spinner_msg.message_id))
        data, backend_used = await _run_blocking(_role_of(uid), _solve_mcq_with_preference, "G", qtext, options)
        model_ans = int(data.get("answer", 0) or 0)
        conf = int(data.get("confidence", 0) or 0)
        raw_expl = str(data.get("explanation", "") or "").strip()
        model_expl = clean_latex(raw_expl)
        raw_why_not = data.get("why_not", {}) or {}
        why_not = {k: clean_latex(v) for k, v in raw_why_not.items()}

        if spinner_task:
            spinner_task.cancel()
        if spinner_msg:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(chat_id=spinner_msg.chat_id, message_id=spinner_msg.message_id)

        msg_html = _format_user_poll_solution(
            question=qtext,
            options=options,
            model_ans=model_ans,
            official_ans=official_ans,
            model_expl=f"[Gemini]\n{model_expl}".strip(),
            official_expl=official_expl,
            why_not=why_not if isinstance(why_not, dict) else {},
            conf=conf,
        )
        poll_payload = {
            "question": qtext,
            "options": options,
            "official_ans": official_ans,
            "official_expl": official_expl,
        }
        db_log("INFO", "poll_solver_backend", {"user_id": uid, "requested": "G", "backend": backend_used})
        await send_poll_verify_buttons(update, context, poll_payload, msg_html)
    except Exception as e:
        if spinner_task:
            spinner_task.cancel()
        if spinner_msg:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(chat_id=spinner_msg.chat_id, message_id=spinner_msg.message_id)
        db_log("ERROR", "poll_solver_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Solve Failed", f"{h(str(e)[:200])}")


