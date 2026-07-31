# ──────────────────────────────────────────────────────────────────────────────
# Section: 29_mistral_ocr_owner_admin_04_10
# Original lines: 14972..15789
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL MISTRAL OCR OWNER/ADMIN PATCH (2026-04-10) =====
import mimetypes
from difflib import SequenceMatcher

MISTRAL_OCR_MODEL = (os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest") or "mistral-ocr-latest").strip()

def _setting_bool(name: str, default: bool = False) -> bool:
    raw = str(get_setting(name, "1" if default else "0") or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "enabled"}

def _set_setting_bool(name: str, value: bool) -> None:
    set_setting(name, "1" if bool(value) else "0")

def get_mistral_api_key() -> str:
    return (get_setting("mistral_api_key", "") or os.getenv("MISTRAL_API_KEY", "") or "").strip()

def mistral_runtime_enabled() -> bool:
    return _setting_bool("mistral_enabled", default=True)

def _mask_secret(secret: str) -> str:
    s = str(secret or "").strip()
    if not s:
        return "not set"
    if len(s) <= 10:
        return s[:2] + "***"
    return s[:4] + "..." + s[-4:]

def _can_use_staff_ocr(user_id: int) -> bool:
    role = get_role(int(user_id or 0))
    if role not in (ROLE_OWNER, ROLE_ADMIN):
        return False
    return is_owner(user_id) or can_use_vision(user_id)

def _guess_mime_type(path: str) -> str:
    mime = mimetypes.guess_type(path)[0]
    if mime:
        return mime
    ext = str(path or "").lower()
    if ext.endswith(".jpg") or ext.endswith(".jpeg"):
        return "image/jpeg"
    if ext.endswith(".png"):
        return "image/png"
    if ext.endswith(".webp"):
        return "image/webp"
    if ext.endswith(".pdf"):
        return "application/pdf"
    return "application/octet-stream"

def _mistral_upload_file(path: str, api_key: str) -> str:
    filename = os.path.basename(path)
    mime = _guess_mime_type(path)
    with open(path, "rb") as f:
        files = {"file": (filename, f, mime)}
        data = {"purpose": "ocr", "visibility": "user"}
        resp = requests.post(
            "https://api.mistral.ai/v1/files",
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
            timeout=60,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Mistral file upload failed ({resp.status_code}): {resp.text[:220]}")
    payload = resp.json()
    file_id = str(payload.get("id") or "").strip()
    if not file_id:
        raise RuntimeError("Mistral file upload did not return a file id.")
    return file_id

def _mistral_ocr_request(document_payload: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    resp = requests.post(
        "https://api.mistral.ai/v1/ocr",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MISTRAL_OCR_MODEL,
            "document": document_payload,
            "include_image_base64": False,
        },
        timeout=90,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Mistral OCR failed ({resp.status_code}): {resp.text[:260]}")
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("Mistral OCR returned an invalid response.")
    return data

def _mistral_ocr_process_path(path: str) -> Dict[str, Any]:
    api_key = get_mistral_api_key()
    if not api_key:
        raise RuntimeError("No Mistral API key configured. Use /mistral set YOUR_KEY first.")
    mime = _guess_mime_type(path)
    raw_bytes = Path(path).read_bytes()
    doc_payload = None
    if mime.startswith("image/"):
        b64 = base64.b64encode(raw_bytes).decode("utf-8")
        doc_payload = {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"}
    elif mime == "application/pdf":
        b64 = base64.b64encode(raw_bytes).decode("utf-8")
        doc_payload = {"type": "document_url", "document_url": f"data:{mime};base64,{b64}"}
    if doc_payload is None:
        file_id = _mistral_upload_file(path, api_key)
        doc_payload = {"file_id": file_id}
    data = _mistral_ocr_request(doc_payload, api_key)
    pages = data.get("pages", []) or []
    chunks = []
    for page in pages:
        md = str((page or {}).get("markdown") or "").strip()
        if md:
            chunks.append(md)
    raw_markdown = "\n\n".join(chunks).strip()
    return {
        "raw_markdown": raw_markdown,
        "pages": pages,
        "model": str(data.get("model") or MISTRAL_OCR_MODEL),
        "usage_info": data.get("usage_info") or {},
        "response": data,
    }

def _basic_ocr_text_cleanup(text: str) -> str:
    s = str(text or "")
    if not s:
        return ""
    s = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", s)
    s = re.sub(r"\[[^\]]+\]\(([^)]+)\)", r"\1", s)
    s = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", s)
    s = re.sub(r"`{1,3}", "", s)
    s = clean_latex(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _plain_ai_text_cleanup(prompt: str) -> str:
    last_err = None
    if GEMINI_API_KEYS:
        try:
            out = call_gemini_text_rest(prompt, timeout_seconds=12, force_json=False)
            if out and str(out).strip():
                return str(out).strip()
        except Exception as e:
            last_err = e
    if USE_PERPLEXITY_FALLBACK:
        try:
            out = query_ai(prompt)
            if out and str(out).strip():
                return str(out).strip()
        except Exception as e:
            last_err = e
    try:
        out = gemini3_solve(prompt)
        if out and str(out).strip():
            return str(out).strip()
    except Exception as e:
        last_err = e
    if last_err:
        raise last_err
    raise RuntimeError("AI text cleanup backend unavailable.")

def _format_ocr_text_for_telegram(raw_text: str) -> str:
    base = _basic_ocr_text_cleanup(raw_text)
    if not base:
        return ""
    prompt = (
        "Clean the following OCR text for Telegram.\n"
        "Rules:\n"
        "- Return plain text only.\n"
        "- Preserve the original language.\n"
        "- Keep questions, options, equations, numbering and important lines.\n"
        "- Convert markdown and LaTeX into simple readable plain text.\n"
        "- Fix obvious OCR spacing issues only.\n"
        "- Do not add answers or extra commentary.\n\n"
        f"OCR TEXT:\n{base[:14000]}"
    )
    try:
        cleaned = _plain_ai_text_cleanup(prompt)
        cleaned = _basic_ocr_text_cleanup(cleaned)
        return cleaned or base
    except Exception:
        return base

def _normalize_option_text_for_match(text: str) -> str:
    s = clean_latex(str(text or "")).lower()
    s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _match_answer_text_to_options(answer_text: str, options: List[str]) -> int:
    target = _normalize_option_text_for_match(answer_text)
    if not target:
        return 0
    best_idx = 0
    best_score = 0.0
    for idx, opt in enumerate(options, start=1):
        norm_opt = _normalize_option_text_for_match(opt)
        if not norm_opt:
            continue
        if target == norm_opt:
            return idx
        if target in norm_opt or norm_opt in target:
            return idx
        score = SequenceMatcher(None, target, norm_opt).ratio()
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx if best_score >= 0.72 else 0

_prev_infer_option_from_text_20260410 = _infer_option_from_text

def _infer_option_from_text(text: str, n: int) -> int:
    s = clean_latex(str(text or "")).upper()
    patterns = [
        r"(?:FINAL\s+ANSWER|CORRECT\s+ANSWER|SELECTED\s+OPTION|CORRECT\s+OPTION|RIGHT\s+OPTION|ANSWER|ANS)\s*[:\-]?\s*(?:OPTION\s*)?([A-E])\b",
        r"(?:FINAL\s+ANSWER|CORRECT\s+ANSWER|SELECTED\s+OPTION|CORRECT\s+OPTION|RIGHT\s+OPTION|ANSWER|ANS)\s*[:\-]?\s*([1-5])\b",
        r"\bOPTION\s*([A-E])\b",
        r"\b([A-E])\s+IS\s+CORRECT\b",
        r"\bCORRECT\s*[:\-]?\s*([A-E])\b",
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if not m:
            continue
        raw = m.group(1)
        if raw.isdigit():
            idx = int(raw)
        else:
            idx = ord(raw) - 64
        if 1 <= idx <= int(n or 0):
            return idx
    try:
        return _prev_infer_option_from_text_20260410(text, n)
    except Exception:
        return 0

def _coerce_mcq_result_with_options(raw_text: str, options: List[str]) -> Dict[str, Any]:
    opts = [(o or "").strip() for o in (options or []) if (o or "").strip()]
    option_count = len(opts)
    raw = str(raw_text or "").strip()
    if option_count < 2:
        raise ValueError("Not enough options to solve.")
    data = None
    try:
        data = _extract_json_strict(raw)
    except Exception:
        data = _repair_to_json(
            raw,
            schema_hint='{"answer":1,"answer_letter":"A","correct_option_text":"...","confidence":0,"explanation":".","why_not":{"A":".","B":".","C":".","D":".","E":"."}}',
            timeout_seconds=10,
        )
    if not isinstance(data, dict):
        inferred = _infer_option_from_text(raw, option_count)
        return {
            "answer": inferred,
            "confidence": 0,
            "explanation": _sanitize_quiz_explanation_text(raw[:700]),
            "why_not": {},
        }

    answer_idx = int(data.get("answer", 0) or 0)

    answer_letter = str(
        data.get("answer_letter")
        or data.get("correct_letter")
        or data.get("option_letter")
        or ""
    ).strip().upper()
    if len(answer_letter) == 1 and "A" <= answer_letter <= "E":
        answer_idx = ord(answer_letter) - 64

    option_text_fields = [
        data.get("correct_option_text"),
        data.get("answer_text"),
        data.get("correct_text"),
        data.get("option_text"),
        data.get("correct_option"),
    ]
    mapped_idx = 0
    for field in option_text_fields:
        mapped_idx = _match_answer_text_to_options(str(field or ""), opts)
        if mapped_idx:
            break

    if mapped_idx:
        answer_idx = mapped_idx
    elif not (1 <= answer_idx <= option_count):
        answer_idx = _infer_option_from_text(raw, option_count)

    explanation = _sanitize_quiz_explanation_text(
        str(data.get("explanation", "") or data.get("reason", "") or "").strip() or raw[:700]
    )
    why_not_raw = data.get("why_not", {}) if isinstance(data.get("why_not"), dict) else {}
    why_not = {}
    for k, v in why_not_raw.items():
        if not v:
            continue
        why_not[str(k)] = _sanitize_quiz_explanation_text(v)

    return {
        "answer": answer_idx if 1 <= answer_idx <= option_count else 0,
        "confidence": int(data.get("confidence", 0) or 0),
        "explanation": explanation,
        "why_not": why_not,
    }

_prev_build_mcq_json_prompt_20260410 = _build_mcq_json_prompt

def _build_mcq_json_prompt(question: str, options: List[str]) -> Tuple[str, List[str]]:
    q = (question or "").strip()
    opts = [(o or "").strip() for o in (options or []) if (o or "").strip()][:5]
    if len(opts) < 2:
        raise ValueError("Not enough options to solve.")
    is_bn = _is_bangla_text(q + " " + " ".join(opts))
    lang_rule = _quiz_language_rule_block(is_bn)
    schema_expl = _quiz_schema_example_explanation(is_bn)
    opt_lines = "\n".join([f"{_safe_letter(i+1)}. {opts[i]}" for i in range(len(opts))])
    prompt = (
        "Return STRICT JSON only. No markdown. No extra text.\n\n"
        "Task: Solve the following MCQ and choose the correct option.\n"
        "Rules:\n"
        "- answer must be 1-5 (A=1,B=2,C=3,D=4,E=5).\n"
        "- answer_letter must be the letter of the correct option.\n"
        "- correct_option_text must repeat the exact text of the correct option.\n"
        f"- {lang_rule}\n"
        "- explanation must be concise but accurate.\n"
        "- why_not must explain why the other options are wrong.\n"
        "- confidence must be an integer from 0 to 100.\n\n"
        f"Question:\n{q}\n\nOptions:\n{opt_lines}\n\n"
        "JSON format:\n"
        f'{{"answer":1,"answer_letter":"A","correct_option_text":"{opts[0]}","confidence":0,"explanation":"{schema_expl}","why_not":{{"A":"..","B":"..","C":"..","D":"..","E":".."}}}}'
    )
    return prompt, opts

def _try_gemini_mcq_backends(question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:
    prompt, opts = _build_mcq_json_prompt(question, options)
    last_error: Optional[Exception] = None

    try:
        raw = gemini3_solve(prompt)
        data = _coerce_mcq_result_with_options(raw, opts)
        if int(data.get("answer", 0) or 0) > 0:
            return data, "Gemini"
    except Exception as e:
        last_error = e

    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEYS:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=10, force_json=True)
            data = _coerce_mcq_result_with_options(raw, opts)
            if int(data.get("answer", 0) or 0) > 0:
                return data, "Gemini"
        except Exception as e:
            last_error = e

    if USE_PERPLEXITY_FALLBACK:
        try:
            alt = query_ai(prompt)
            data = _coerce_mcq_result_with_options(alt or "", opts)
            if int(data.get("answer", 0) or 0) > 0:
                return data, "Perplexity"
        except Exception as e:
            last_error = e

    raise RuntimeError(str(last_error or "AI backend is temporarily unavailable. Please try again."))

def gemini_solve_mcq_json(question: str, options: List[str]) -> Dict[str, Any]:
    data, _used = _try_gemini_mcq_backends(question, options)
    return data

def perplexity_solve_mcq_json(question: str, options: List[str]) -> Dict[str, Any]:
    q = (question or "").strip()
    opts = [(o or "").strip() for o in (options or []) if (o or "").strip()][:5]
    if len(opts) < 2:
        raise ValueError("Not enough options to solve.")
    prompt, _ = _build_mcq_json_prompt(q, opts)
    alt = query_ai(prompt)
    if not alt:
        raise RuntimeError("Perplexity unavailable.")
    data = _coerce_mcq_result_with_options(alt, opts)
    if int(data.get("answer", 0) or 0) <= 0:
        raise RuntimeError("Perplexity returned no valid answer.")
    return data

def deepseek_solve_mcq_json(question: str, options: List[str]) -> Dict[str, Any]:
    q = (question or "").strip()
    opts = [(o or "").strip() for o in (options or []) if (o or "").strip()][:5]
    if len(opts) < 2:
        raise ValueError("Not enough options to solve.")
    prompt, _ = _build_mcq_json_prompt(q, opts)
    client = _deepseek_client()
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL_TEXT,
        messages=[
            {"role": "system", "content": "You are a strict academic problem-solving assistant."},
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    raw = (resp.choices[0].message.content or "").strip()
    data = _coerce_mcq_result_with_options(raw, opts)
    if int(data.get("answer", 0) or 0) <= 0:
        raise RuntimeError("DeepSeek returned no valid answer.")
    return data

def _ocr_text_to_mcq_items(raw_text: str, user_id: int) -> Tuple[str, List[Dict[str, Any]]]:
    base_text = _basic_ocr_text_cleanup(raw_text)
    clean_text = _format_ocr_text_for_telegram(base_text)
    prompt = (
        "Return STRICT JSON only (no markdown).\n"
        "From the OCR text below, extract every visible MCQ.\n"
        "Rules:\n"
        "- Keep the original language.\n"
        "- Preserve question wording as much as possible.\n"
        "- Options should be clean plain text.\n"
        "- If the correct answer is not clearly visible, set answer to 0.\n"
        "- correct_option_text should contain the exact correct option text when known, otherwise empty.\n"
        "- explanation should be a short exam-style note only when the answer is visible; otherwise keep it empty.\n"
        "- Also return clean_text: a Telegram-friendly plain text version of the OCR.\n\n"
        "JSON format:\n"
        '{"clean_text":"...","items":[{"questions":"...","option1":"...","option2":"...","option3":"...","option4":"...","option5":"","answer":1,"correct_option_text":"...","explanation":"..."}]}\n\n'
        f"OCR TEXT:\n{base_text[:15000]}"
    )
    raw = None
    last_err = None
    if GEMINI_API_KEYS:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=12, force_json=True)
        except Exception as e:
            last_err = e
    if not raw and USE_PERPLEXITY_FALLBACK:
        try:
            raw = query_ai(prompt)
        except Exception as e:
            last_err = e
    if not raw:
        try:
            raw = gemini3_solve(prompt)
        except Exception as e:
            last_err = e
    items: List[Dict[str, Any]] = []
    if raw:
        try:
            data = _extract_json_strict(raw)
        except Exception:
            data = _repair_to_json(
                raw,
                schema_hint='{"clean_text":"...","items":[{"questions":"...","option1":"...","option2":"...","option3":"...","option4":"...","option5":"","answer":0,"correct_option_text":"","explanation":""}]}',
                timeout_seconds=10,
            )
        if isinstance(data, dict):
            clean_text = _basic_ocr_text_cleanup(data.get("clean_text") or clean_text)
            for it in (data.get("items") or [])[:50]:
                question = str(it.get("questions") or it.get("question") or "").strip()
                options = []
                if isinstance(it.get("options"), list):
                    options = [str(x or "").strip() for x in it.get("options", []) if str(x or "").strip()]
                else:
                    for k in ("option1", "option2", "option3", "option4", "option5"):
                        val = str(it.get(k) or "").strip()
                        if val:
                            options.append(val)
                if not question or len(options) < 2:
                    continue
                answer = int(it.get("answer", 0) or 0)
                mapped = _match_answer_text_to_options(str(it.get("correct_option_text") or ""), options)
                if mapped:
                    answer = mapped
                if not (1 <= answer <= len(options)):
                    answer = 0
                payload = {
                    "questions": question,
                    "option1": options[0] if len(options) > 0 else "",
                    "option2": options[1] if len(options) > 1 else "",
                    "option3": options[2] if len(options) > 2 else "",
                    "option4": options[3] if len(options) > 3 else "",
                    "option5": options[4] if len(options) > 4 else "",
                    "answer": answer,
                    "explanation": _sanitize_quiz_explanation_text(str(it.get("explanation") or "").strip()),
                    "type": 1,
                    "section": 1,
                }
                items.append(payload)
    if not items:
        for block in split_blocks(clean_text):
            parsed = parse_text_block(block, user_id)
            if parsed:
                items.append(parsed)
    return clean_text, items

def _remember_ocr_context(context: ContextTypes.DEFAULT_TYPE, message_id: int, payload: Dict[str, Any]) -> None:
    store = context.application.bot_data.get("_ocr_context_store")
    if not isinstance(store, dict):
        store = {}
        context.application.bot_data["_ocr_context_store"] = store
    store[int(message_id)] = dict(payload or {})
    if len(store) > 600:
        for key in list(sorted(store.keys()))[:200]:
            store.pop(key, None)

def _get_ocr_context(context: ContextTypes.DEFAULT_TYPE, message_id: int) -> Optional[Dict[str, Any]]:
    store = context.application.bot_data.get("_ocr_context_store")
    if not isinstance(store, dict):
        return None
    payload = store.get(int(message_id))
    return dict(payload) if isinstance(payload, dict) else None

def _solve_from_ocr_text(clean_text: str, extra_instruction: str = "") -> Tuple[str, str]:
    body = _basic_ocr_text_cleanup(clean_text)
    prompt = (
        "The following text was extracted from an image using OCR.\n"
        "Solve the visible academic question(s) accurately.\n"
        "If it is an MCQ, clearly state the correct option and explain briefly.\n"
        "Use Telegram-friendly plain text. No LaTeX. No markdown headings.\n"
    )
    extra_instruction = str(extra_instruction or "").strip()
    if extra_instruction:
        prompt += f"Extra user instruction: {extra_instruction}\n"
    prompt += f"\nOCR TEXT:\n{body[:14000]}"
    return _solve_text_with_preference("G", prompt, "private_academic")

_prev_handle_image_20260410 = handle_image

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = update.effective_user.id
    if is_banned(uid):
        return
    if not is_private_chat(update):
        return
    if not _can_use_staff_ocr(uid):
        return await _prev_handle_image_20260410(update, context)
    if not vision_mode_on(uid):
        return await _prev_handle_image_20260410(update, context)
    if not mistral_runtime_enabled():
        return await _prev_handle_image_20260410(update, context)
    if not get_mistral_api_key():
        await warn(update, "Mistral API Key Missing", "Use /mistral set YOUR_KEY first, or turn Mistral OCR off with /mistral off.")
        return

    if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
        await warn(update, "Buffer Limit Reached", f"You have {MAX_BUFFERED_QUESTIONS} questions buffered.\n\nUse /done to export or /clear to reset.")
        return

    msg = update.message
    tg_file = None
    suffix = ".jpg"
    if msg.photo:
        tg_file = await msg.photo[-1].get_file()
        suffix = ".jpg"
    elif msg.document and getattr(msg.document, "mime_type", "").startswith("image/"):
        tg_file = await msg.document.get_file()
        ext = os.path.splitext(str(msg.document.file_name or ""))[1].strip() or ".jpg"
        suffix = ext if len(ext) <= 6 else ".jpg"
    else:
        return await _prev_handle_image_20260410(update, context)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        local_path = f.name
    await tg_file.download_to_drive(local_path)

    try:
        ocr = await _run_blocking(_role_of(uid), _mistral_ocr_process_path, local_path, timeout=120)
        raw_markdown = str(ocr.get("raw_markdown") or "").strip()
        if not raw_markdown:
            await warn(update, "OCR Returned Empty Text", "Mistral OCR could not read usable text from this image.")
            return
        clean_text, items = await _run_blocking(_role_of(uid), _ocr_text_to_mcq_items, raw_markdown, uid, timeout=120)

        added = 0
        for payload in items:
            if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
                break
            if not explain_mode_on(uid):
                payload["explanation"] = ""
            buffer_add(uid, payload)
            added += 1

        ctx_payload = {
            "raw_markdown": raw_markdown,
            "clean_text": clean_text,
            "items": items,
            "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
        }
        _remember_ocr_context(context, msg.message_id, ctx_payload)

        preview = clean_text.strip()
        if len(preview) > 3000:
            preview = preview[:2997].rstrip() + "..."
        status_bits = [f"OCR model: <code>{h(str(ocr.get('model') or MISTRAL_OCR_MODEL))}</code>"]
        if added:
            status_bits.append(f"Buffered MCQ: <code>{h(str(added))}</code>")
        else:
            status_bits.append("Buffered MCQ: <code>0</code>")
        preview_msg = await msg.reply_text(
            ui_box_html("Mistral OCR Complete", "\n".join(status_bits) + f"\n\n{h(preview)}", emoji="🧾"),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        _remember_ocr_context(context, preview_msg.message_id, ctx_payload)

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write(clean_text)
            txt_path = tf.name
        try:
            with open(txt_path, "rb") as fh:
                sent_doc = await msg.reply_document(
                    document=fh,
                    filename=f"mistral_ocr_{uid}.txt",
                    caption=f"<b>✅ OCR Text Extracted</b>\n<i>{h(str(len(clean_text)))} characters</i>",
                    parse_mode=ParseMode.HTML,
                )
            _remember_ocr_context(context, sent_doc.message_id, ctx_payload)
        finally:
            with contextlib.suppress(Exception):
                os.remove(txt_path)

        if added:
            await ok_html(update, "OCR + Quiz Buffer Ready", f"Buffered <code>{h(str(added))}</code> MCQ(s).\nUse <code>/done</code> to export or <code>/post</code> to publish.\nReply to the image with <code>/qans</code> to solve directly.", emoji="✅")
        else:
            await warn_html(update, "OCR Text Extracted", "Text was extracted successfully, but no clean MCQ set was detected for buffering.\nReply to the image with <code>/qans</code> to solve the visible question directly.", emoji="⚠️")
    except Exception as e:
        db_log("ERROR", "mistral_ocr_handle_image_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Mistral OCR Failed", str(e)[:220])
    finally:
        with contextlib.suppress(Exception):
            os.remove(local_path)

@require_admin
async def cmd_mistral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id if update.effective_user else 0
    if not is_private_chat(update):
        await warn(update, "Private Only", "Use this command in private chat with the bot.")
        return

    args = list(context.args or [])
    action = (args[0] if args else "status").strip().lower()
    remainder = " ".join(args[1:]).strip() if len(args) > 1 else ""
    if not remainder and update.message.reply_to_message:
        remainder = reply_text_or_caption(update)

    if action in {"status", "info"}:
        key = get_mistral_api_key()
        body = (
            f"Enabled: <code>{'ON' if mistral_runtime_enabled() else 'OFF'}</code>\n"
            f"Key: <code>{h(_mask_secret(key))}</code>\n"
            f"Model: <code>{h(MISTRAL_OCR_MODEL)}</code>"
        )
        await ok_html(update, "Mistral OCR Status", body, emoji="🧾")
        return

    if action in {"on", "enable"}:
        _set_setting_bool("mistral_enabled", True)
        await ok_html(update, "Mistral OCR Enabled", "Mistral OCR is now active for owner/admin image workflows.", emoji="✅")
        return

    if action in {"off", "disable"}:
        _set_setting_bool("mistral_enabled", False)
        await ok_html(update, "Mistral OCR Disabled", "Mistral OCR is now turned off. The bot will fall back to the previous image flow.", emoji="✅")
        return

    if action in {"delete", "del", "remove", "clear"}:
        set_setting("mistral_api_key", "")
        await ok_html(update, "Mistral API Key Deleted", "The saved Mistral API key has been removed from the bot database.", emoji="🗑️")
        return

    if action in {"set", "add", "change", "update"}:
        candidate = str(remainder or "").strip()
        m = re.search(r"(?:mistral|ma)_?[A-Za-z0-9\-_]+", candidate)
        if m:
            candidate = m.group(0).strip()
        if not candidate:
            await safe_reply(update, usage_box("mistral", "<status|on|off|set KEY|delete>", "Examples:\n/mistral status\n/mistral on\n/mistral set YOUR_MISTRAL_KEY\n/mistral delete"))
            return
        set_setting("mistral_api_key", candidate)
        await ok_html(update, "Mistral API Key Saved", f"Saved key: <code>{h(_mask_secret(candidate))}</code>\nYou can now use <code>/vision_on</code> and send an image.", emoji="🔐")
        return

    await safe_reply(update, usage_box("mistral", "<status|on|off|set KEY|delete>", "Manage the bot's Mistral OCR key and toggle."))

@require_admin
async def cmd_qans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    if not is_private_chat(update):
        await warn(update, "Private Only", "Use this command in private chat by replying to an image, text, or quiz.")
        return
    uid = update.effective_user.id
    if not _can_use_staff_ocr(uid):
        await warn_unauthorized(update, "Only Owner/Admin OCR users can use this command.")
        return
    reply_msg = update.message.reply_to_message
    if not reply_msg:
        await safe_reply(update, usage_box("qans", "[extra instruction]", "Reply to an image, extracted OCR text, text question, or poll, then use this command."))
        return

    extra_instruction = " ".join(context.args or []).strip()
    ocr_ctx = _get_ocr_context(context, reply_msg.message_id)

    try:
        if getattr(reply_msg, "poll", None):
            poll = reply_msg.poll
            question = str(poll.question or "").strip()
            options = [str(o.text or "").strip() for o in (poll.options or []) if str(o.text or "").strip()]
            if len(options) < 2:
                raise RuntimeError("This poll does not contain enough options.")
            data = await _run_blocking(_role_of(uid), gemini_solve_mcq_json, question, options, timeout=60)
            raw_expl = str(data.get("explanation", "") or "").strip()
            clean_expl = clean_latex(raw_expl)
            why_not = {k: clean_latex(v) for k, v in (data.get("why_not", {}) or {}).items()}
            msg_html = _format_user_poll_solution(
                question=question,
                options=options,
                model_ans=int(data.get("answer", 0) or 0),
                official_ans=_poll_official_answer(poll),
                model_expl=clean_expl,
                official_expl=str(getattr(poll, "explanation", "") or "").strip(),
                why_not=why_not,
                conf=int(data.get("confidence", 0) or 0),
            )
            await safe_reply(update, msg_html)
            return

        if reply_msg.photo or (reply_msg.document and str(getattr(reply_msg.document, "mime_type", "") or "").startswith("image/")):
            if not mistral_runtime_enabled() or not get_mistral_api_key():
                raise RuntimeError("Mistral OCR is not ready. Use /mistral status or /mistral set YOUR_KEY first.")
            suffix = ".jpg"
            if reply_msg.document:
                ext = os.path.splitext(str(reply_msg.document.file_name or ""))[1].strip() or ".jpg"
                suffix = ext if len(ext) <= 6 else ".jpg"
                tg_file = await reply_msg.document.get_file()
            else:
                tg_file = await reply_msg.photo[-1].get_file()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                local_path = f.name
            await tg_file.download_to_drive(local_path)
            try:
                ocr = await _run_blocking(_role_of(uid), _mistral_ocr_process_path, local_path, timeout=120)
                clean_text, items = await _run_blocking(_role_of(uid), _ocr_text_to_mcq_items, str(ocr.get("raw_markdown") or ""), uid, timeout=120)
                answer, used_model = await _run_blocking(_role_of(uid), _solve_from_ocr_text, clean_text, extra_instruction, timeout=120)
                _remember_ocr_context(context, reply_msg.message_id, {
                    "raw_markdown": str(ocr.get("raw_markdown") or ""),
                    "clean_text": clean_text,
                    "items": items,
                    "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
                })
                header = f"<b>{h(used_model)}</b>\n\n" if used_model else ""
                preview = clean_text[:1200].strip()
                if len(clean_text) > 1200:
                    preview += "\n..."
                body = _answer_to_tg_html(answer, model_name=used_model, preserve_code=False)
                if preview:
                    body += f"\n\n<b>OCR Preview</b>\n{h(preview)}"
                await safe_reply(update, body)
                return
            finally:
                with contextlib.suppress(Exception):
                    os.remove(local_path)

        source_text = ""
        if ocr_ctx:
            source_text = str(ocr_ctx.get("clean_text") or ocr_ctx.get("raw_markdown") or "").strip()
        if not source_text:
            source_text = str(reply_msg.text or reply_msg.caption or "").strip()
        if not source_text:
            raise RuntimeError("No readable text found in the replied message.")
        if extra_instruction:
            source_text = f"{source_text}\n\nExtra user instruction:\n{extra_instruction}"
        answer, used_model = await _run_blocking(_role_of(uid), _solve_text_with_preference, "G", source_text, "private_academic", timeout=90)
        await safe_reply(update, _answer_to_tg_html(answer, model_name=used_model, preserve_code=False))
    except Exception as e:
        db_log("ERROR", "qans_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Question Answer Failed", str(e)[:220])

if "_all_commands_for" in globals():
    _prev_all_commands_for_20260410 = _all_commands_for
    def _all_commands_for(user_id: int):
        sections = list(_prev_all_commands_for_20260410(user_id))
        role = get_role(int(user_id or 0))
        extra_items = []
        if role in (ROLE_ADMIN, ROLE_OWNER):
            extra_items.extend([
                ("/mistral", "Manage Mistral OCR key and toggle"),
                ("/qans", "Reply to image/text/poll and solve it directly"),
            ])
        if not extra_items:
            return sections
        inserted = False
        new_sections = []
        for title, items in sections:
            if "Staff Commands" in str(title):
                merged = list(items) + extra_items
                new_sections.append((title, merged))
                inserted = True
            else:
                new_sections.append((title, items))
        if not inserted:
            new_sections.append(("🛠 Staff Commands", extra_items))
        return new_sections

_prev_build_app_20260410 = build_app

def build_app() -> Application:
    app = _prev_build_app_20260410()
    private_filter = filters.ChatType.PRIVATE
    _register_dual_command(app, "mistral", cmd_mistral, private_filter)
    _register_dual_command(app, "qans", cmd_qans, private_filter)
    _register_dual_command(app, "mk", cmd_mistral, private_filter)
    _register_dual_command(app, "qa", cmd_qans, private_filter)
    return app

# ===== END FINAL MISTRAL OCR OWNER/ADMIN PATCH =====


