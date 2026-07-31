# ──────────────────────────────────────────────────────────────────────────────
# Section: 32_final_ocr_reliability_user_picker_04_10f
# Original lines: 17420..17878
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL OCR RELIABILITY + USER PICKER PATCH (2026-04-10F) =====

_OCR_TEMP_DISABLED_EN = (
    "This OCR feature is temporarily unavailable at the moment. "
    "Please try again later."
)

_BN_TO_EN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _ocr_temporarily_disabled_html() -> str:
    return ui_box_html("OCR Temporarily Unavailable", h(_OCR_TEMP_DISABLED_EN), emoji="ℹ️")


def _normalize_question_no_token(value: str) -> str:
    s = str(value or "").translate(_BN_TO_EN_DIGITS)
    m = re.search(r"(\d{1,4})", s)
    return m.group(1) if m else ""


def _build_focused_ocr_prompt(ocr_ctx: Dict[str, Any], user_question: str, previous_answer: str = "") -> str:
    user_q = str(user_question or "").strip()
    prev = str(previous_answer or "").strip()
    items = list((ocr_ctx or {}).get("items") or [])
    picked = _pick_first_mcq_item(items, user_q)
    if picked:
        options = [str(picked.get(f"option{i}") or "").strip() for i in range(1, 6) if str(picked.get(f"option{i}") or "").strip()]
        qblock = str(picked.get("questions") or "").strip()
        opt_block = "\n".join([f"{_safe_letter(i+1)}. {options[i]}" for i in range(len(options))])
        visible = int(picked.get("answer", 0) or 0)
        visible_text = options[visible - 1] if 1 <= visible <= len(options) else ""
        prompt = (
            "You are continuing an OCR-based academic discussion.\n"
            "Answer only from the extracted content below.\n"
            "If the page contains a visibly marked answer, treat that visible marking as the highest-priority source.\n"
            "If the visible marking conflicts with ordinary reasoning, explicitly mention that the page appears to mark that option.\n"
            "Use Telegram-friendly plain text. No LaTeX. No Markdown headings.\n\n"
            f"User request:\n{user_q[:1500]}\n\n"
        )
        if prev:
            prompt += f"Previous bot answer:\n{prev[:3000]}\n\n"
        prompt += f"Focused MCQ:\n{qblock}\n\nOptions:\n{opt_block}\n"
        if visible_text:
            prompt += f"\nVisible marked answer on the page: {_safe_letter(visible)}) {visible_text}\n"
        return prompt

    base = str((ocr_ctx or {}).get("clean_text") or (ocr_ctx or {}).get("raw_markdown") or "").strip()
    prompt = (
        "The following text was extracted from a replied file using OCR.\n"
        "Answer only the user's request using this OCR content.\n"
        "If a visible answer marking exists in the page, prioritize that visible answer.\n"
        "Use Telegram-friendly plain text. No LaTeX.\n\n"
        f"User request:\n{user_q[:1500]}\n\n"
    )
    if prev:
        prompt += f"Previous bot answer:\n{prev[:3000]}\n\n"
    prompt += f"OCR TEXT:\n{base[:14000]}"
    return prompt


def _reply_message_plain_text(msg) -> str:
    if not msg:
        return ""
    return str(getattr(msg, "text", "") or getattr(msg, "caption", "") or "").strip()


def _has_ocr_context(context: ContextTypes.DEFAULT_TYPE, msg) -> bool:
    return bool(msg and _get_ocr_context(context, getattr(msg, 'message_id', 0) or 0))


def _is_user_followup_to_ocr_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    msg = update.message.reply_to_message if update and update.message else None
    if not msg:
        return False
    if not _has_ocr_context(context, msg):
        return False
    fu = getattr(msg, 'from_user', None)
    return bool(fu and getattr(fu, 'is_bot', False))


def _vision_marked_letter_prompt() -> str:
    return (
        "Return STRICT JSON only. No markdown. No extra text.\n"
        "Task: inspect this exam page image and detect only the question numbers whose correct option is explicitly marked.\n"
        "Pay special attention to green highlights, colored boxes, red dots, circles, ticks, checks, underlines, side-answer labels, or handwritten answer marks.\n"
        "If the marking is unclear, omit that question.\n"
        "Prefer question number + answer letter only; do not try to rewrite the full page.\n"
        "JSON format:\n"
        '{"marks":[{"question_no":"01","answer_letter":"C","marker_type":"green_highlight|red_dot|circle|tick|underline|ans_text|box","marker_confidence":90}]}'
    )


def _visual_marked_letters_from_image(image_path: str) -> List[Dict[str, Any]]:
    if not GEMINI_API_KEYS:
        return []
    prompt = _vision_marked_letter_prompt()
    try:
        raw = call_gemini_vision_rest(image_path, prompt, force_json=True)
        data = _extract_json_strict(raw)
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    marks = []
    if isinstance(data, dict):
        marks = data.get('marks') or data.get('items') or []
    for it in list(marks)[:120]:
        qno = _normalize_question_no_token(str(it.get('question_no') or it.get('question') or it.get('qno') or ''))
        letter = str(it.get('answer_letter') or it.get('letter') or '').strip().upper()
        if not qno:
            continue
        if len(letter) == 1 and 'A' <= letter <= 'E':
            answer = ord(letter) - 64
        else:
            raw_answer = _normalize_question_no_token(str(it.get('answer') or it.get('option') or ''))
            answer = int(raw_answer) if raw_answer.isdigit() else 0
            if 1 <= answer <= 5:
                letter = _safe_letter(answer)
        conf = 0
        with contextlib.suppress(Exception):
            conf = int(it.get('marker_confidence', 0) or 0)
        if conf and conf < 40:
            continue
        if not (1 <= answer <= 5):
            continue
        out.append({
            'question_no': qno,
            'answer': answer,
            'answer_letter': letter,
            'marker_type': str(it.get('marker_type') or '').strip(),
            'marker_confidence': conf,
        })
    return out


def _collect_visual_marked_letters_for_path(path: str) -> List[Dict[str, Any]]:
    mime = _guess_mime_type(path)
    if mime == 'application/pdf':
        page_paths = _render_pdf_to_page_images(path)
        if not page_paths:
            return []
        out: List[Dict[str, Any]] = []
        try:
            for pp in page_paths:
                out.extend(_visual_marked_letters_from_image(pp))
        finally:
            for pp in page_paths:
                with contextlib.suppress(Exception):
                    os.remove(pp)
            with contextlib.suppress(Exception):
                os.rmdir(os.path.dirname(page_paths[0]))
        return out
    if mime.startswith('image/'):
        return _visual_marked_letters_from_image(path)
    return []


def _merge_visual_letter_marks(base_items: List[Dict[str, Any]], letter_marks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    merged = [dict(x or {}) for x in (base_items or [])]
    applied = 0
    index_map: Dict[str, int] = {}
    for idx, item in enumerate(merged):
        qno = _normalize_question_no_token(_question_no_key(str(item.get('questions') or '')))
        if qno and qno not in index_map:
            index_map[qno] = idx
    for mark in (letter_marks or []):
        qno = _normalize_question_no_token(str(mark.get('question_no') or ''))
        ans = int(mark.get('answer', 0) or 0)
        if not qno or qno not in index_map:
            continue
        idx = index_map[qno]
        options = [str(merged[idx].get(f'option{i}') or '').strip() for i in range(1, 6) if str(merged[idx].get(f'option{i}') or '').strip()]
        if not (1 <= ans <= len(options)):
            continue
        if int(merged[idx].get('answer', 0) or 0) != ans:
            merged[idx]['answer'] = ans
            merged[idx]['explanation'] = str(merged[idx].get('explanation') or '').strip() or 'Detected from visible answer marking.'
            applied += 1
        else:
            applied += 1
    return merged, applied


_prev_extract_ocr_bundle_from_path_20260410F = _extract_ocr_bundle_from_path

def _extract_ocr_bundle_from_path(local_path: str, user_id: int) -> Dict[str, Any]:
    ocr = _mistral_ocr_process_path(local_path)
    pages = list(ocr.get('pages') or [])
    clean_text, items = _ocr_pages_to_clean_text_and_items(pages, user_id)
    visual_items = _collect_visual_marked_items_for_path(local_path)
    letter_marks = _collect_visual_marked_letters_for_path(local_path)
    items, visual_applied_1 = _merge_visual_marked_answers(items, visual_items)
    items, visual_applied_2 = _merge_visual_letter_marks(items, letter_marks)
    items = _drop_unclear_mcq_items(items)
    return {
        'ocr': ocr,
        'clean_text': clean_text,
        'items': items,
        'visual_marked_count': int((visual_applied_1 or 0) + (visual_applied_2 or 0)),
    }


_prev_on_solver_callback_20260410F = on_solver_callback

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

    uid = int(req.get('uid') or 0)
    if q.from_user and q.from_user.id != uid:
        with contextlib.suppress(Exception):
            await q.answer("This is not your request.", show_alert=True)
        return

    payload = req.get('payload') or {}
    problem_text = str(payload.get('text') or '').strip()
    kind = str(req.get('kind') or 'text').lower()
    ocr_ctx = req.get('ocr_ctx') if isinstance(req.get('ocr_ctx'), dict) else None
    is_user_ocr = bool(req.get('is_user_ocr'))
    scope = str(req.get('scope') or 'private_academic')

    with contextlib.suppress(Exception):
        await q.edit_message_text(
            ui_box_text('Solving', 'Please wait… Processing your request.', emoji='⏳'),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    try:
        if kind == 'poll' and payload.get('question'):
            question = str(payload.get('question', '')).strip()
            options = payload.get('options', [])
            if model == 'G':
                result = await _run_blocking(_role_of(uid), gemini_solve_mcq_json, question, options)
                model_name = 'Gemini'
            elif model == 'P':
                result = await _run_blocking(_role_of(uid), perplexity_solve_mcq_json, question, options)
                model_name = 'Perplexity'
            elif model == 'D':
                result = await _run_blocking(_role_of(uid), deepseek_solve_mcq_json, question, options)
                model_name = 'DeepSeek'
            else:
                result = {'answer': 0, 'confidence': 0, 'explanation': 'Unknown model', 'why_not': {}}
                model_name = 'AI'
            raw_expl = str(result.get('explanation', '') or '')
            clean_expl = clean_latex(raw_expl)
            raw_why_not = result.get('why_not', {}) or {}
            clean_why_not = {k: clean_latex(v) for k, v in raw_why_not.items()}
            msg_html = _format_user_poll_solution(
                question=question,
                options=options,
                model_ans=int(result.get('answer', 0) or 0),
                official_ans=int(payload.get('official_ans', 0) or 0),
                model_expl=f"[{model_name}]\n{clean_expl}".strip(),
                official_expl=str(payload.get('official_expl', '')).strip(),
                why_not=clean_why_not,
                conf=int(result.get('confidence', 0) or 0),
            )
            kb = _verify_kb(token, model, 'poll')
        else:
            if model == 'G':
                answer, used_model = await _run_blocking(_role_of(uid), _solve_text_with_preference, 'G', problem_text, scope)
            elif model == 'P':
                answer, used_model = await _run_blocking(_role_of(uid), _solve_text_with_preference, 'P', problem_text, scope)
            elif model == 'D':
                answer, used_model = await _run_blocking(_role_of(uid), _solve_text_with_preference, 'D', problem_text, scope)
            else:
                answer, used_model = ('Unknown model', 'AI')
            preserve_code = bool(is_admin(uid) or is_owner(uid))
            msg_html = _answer_to_tg_html(answer, model_name=used_model, preserve_code=preserve_code)
            kb = _verify_kb(token, model, 'text')

        if is_user_ocr:
            msg_html += f"\n\n<b>Daily OCR remaining</b>: <code>{h(str(_remaining_user_ocr_quota(uid)))}</code>"

        with contextlib.suppress(Exception):
            await q.edit_message_text(msg_html, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        if ocr_ctx and q.message:
            _remember_ocr_context(context, q.message.message_id, ocr_ctx)
        if q.message and getattr(q.message.chat, 'type', '') in ('group', 'supergroup'):
            asyncio.create_task(_auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], 300))
    except Exception as e:
        db_log('ERROR', 'solver_callback_failed', {'user_id': uid, 'model': model, 'error': str(e)})
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                ui_box_text('Solve Failed', str(e)[:180], emoji='❌'),
                parse_mode=ParseMode.HTML,
            )


_prev_handle_user_reply_ocr_question_20260410F = handle_user_reply_ocr_question

async def handle_user_reply_ocr_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user or not is_private_chat(update):
        return
    uid = int(update.effective_user.id)
    if is_banned(uid) or get_role(uid) != ROLE_USER:
        return
    reply_msg = update.message.reply_to_message
    if not reply_msg:
        return

    user_question = str(update.message.text or '').strip()
    if not user_question or user_question.startswith('/'):
        return

    reply_has_ctx = _has_ocr_context(context, reply_msg)
    reply_is_media = _is_supported_ocr_media_message(reply_msg)
    if not reply_is_media and not reply_has_ctx:
        return

    if not mistral_runtime_enabled():
        await safe_reply(update, _ocr_temporarily_disabled_html())
        raise ApplicationHandlerStop
    if not get_mistral_api_key():
        await warn(update, 'OCR Unavailable', 'The bot owner has not configured any active Mistral OCR key yet.')
        raise ApplicationHandlerStop

    # Direct replies to the source image/PDF require quota. Follow-ups to bot OCR answers do not.
    needs_quota = bool(reply_is_media)
    if needs_quota:
        remaining = _remaining_user_ocr_quota(uid)
        if remaining <= 0:
            await _send_ocr_limit_warning(update, get_mistral_user_daily_limit())
            raise ApplicationHandlerStop

    proc = await _processing_start(update.message, 'Preparing OCR Answer', 'Reading the replied content and preparing AI choices...')
    local_path = None
    try:
        ocr_ctx = _get_ocr_context(context, reply_msg.message_id) if reply_has_ctx else None
        if not ocr_ctx and reply_is_media:
            reply_doc = reply_msg.document
            suffix = '.jpg'
            if reply_doc:
                name = str(reply_doc.file_name or '').lower()
                if name.endswith('.pdf') or str(getattr(reply_doc, 'mime_type', '') or '').lower() == 'application/pdf':
                    suffix = '.pdf'
                else:
                    ext = os.path.splitext(name)[1].strip() or '.jpg'
                    suffix = ext if len(ext) <= 6 else '.jpg'
                tg_file = await reply_doc.get_file()
            else:
                tg_file = await reply_msg.photo[-1].get_file()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                local_path = f.name
            await tg_file.download_to_drive(local_path)
            await _processing_update(proc, 'Preparing OCR Answer', 'Running OCR and detecting marked answers...')
            bundle = await _run_blocking(_role_of(uid), _extract_ocr_bundle_from_path, local_path, uid, timeout=300)
            ocr = bundle['ocr']
            ocr_ctx = {
                'raw_markdown': str(ocr.get('raw_markdown') or ''),
                'clean_text': str(bundle.get('clean_text') or ''),
                'items': list(bundle.get('items') or []),
                'model': str(ocr.get('model') or MISTRAL_OCR_MODEL),
                'page_count': len(ocr.get('pages') or []),
                'used_key_mask': str(ocr.get('used_key_mask') or ''),
            }
            _remember_ocr_context(context, reply_msg.message_id, ocr_ctx)
            _inc_user_ocr_usage(uid, 1)

        if not ocr_ctx:
            await _processing_delete(proc)
            raise RuntimeError('No OCR context is available for this reply.')

        previous_answer = _reply_message_plain_text(reply_msg) if _is_user_followup_to_ocr_answer(update, context) else ''
        prompt_text = _build_focused_ocr_prompt(ocr_ctx, user_question, previous_answer=previous_answer)

        token = _make_token()
        store = _pending_store(context)
        store[token] = {
            'uid': uid,
            'kind': 'text',
            'scope': 'private_academic',
            'chat_id': update.message.chat_id,
            'payload': {'text': prompt_text, 'source_user_text': prompt_text},
            'ocr_ctx': dict(ocr_ctx),
            'is_user_ocr': True,
        }

        await _processing_delete(proc)
        proc = None
        await safe_reply(update, ui_box_html('Choose AI Model', 'Tap a model button below to answer from the replied OCR content.', emoji='🤖'))
        chooser = await update.message.reply_text(
            ui_box_text('AI Options', 'Select a model to continue from the OCR content.', emoji='⚙️'),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_solver_picker_kb(token),
        )
        if ocr_ctx and chooser:
            _remember_ocr_context(context, chooser.message_id, ocr_ctx)
        raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception as e:
        await _processing_delete(proc)
        db_log('ERROR', 'user_reply_ocr_question_failed', {'user_id': uid, 'error': str(e)})
        await err(update, 'OCR Question Failed', str(e)[:220])
        raise ApplicationHandlerStop
    finally:
        if local_path:
            with contextlib.suppress(Exception):
                os.remove(local_path)


_prev_handle_image_20260410F = handle_image

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = int(update.effective_user.id)
    if is_private_chat(update) and _can_use_staff_ocr(uid) and vision_mode_on(uid) and not mistral_runtime_enabled():
        await safe_reply(update, _ocr_temporarily_disabled_html())
        return
    return await _prev_handle_image_20260410F(update, context)


_prev_handle_private_ocr_document_20260410F = handle_private_ocr_document

async def handle_private_ocr_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = int(update.effective_user.id)
    if is_private_chat(update) and _can_use_staff_ocr(uid) and vision_mode_on(uid):
        doc = getattr(update.message, 'document', None)
        mime = str(getattr(doc, 'mime_type', '') or '').lower() if doc else ''
        name = str(getattr(doc, 'file_name', '') or '').lower() if doc else ''
        if doc and (mime == 'application/pdf' or name.endswith('.pdf')) and not mistral_runtime_enabled():
            await safe_reply(update, _ocr_temporarily_disabled_html())
            return
    return await _prev_handle_private_ocr_document_20260410F(update, context)


_prev_build_app_20260410F = build_app

def build_app() -> Application:
    app = _prev_build_app_20260410F()
    return app

# ===== END FINAL OCR RELIABILITY + USER PICKER PATCH =====


