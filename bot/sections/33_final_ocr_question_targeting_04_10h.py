# ──────────────────────────────────────────────────────────────────────────────
# Section: 33_final_ocr_question_targeting_04_10h
# Original lines: 17879..18159
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL OCR QUESTION TARGETING + ANSWER MAP PATCH (2026-04-10H) =====

_EXPLICIT_ANSWER_LETTER_RE = re.compile(
    r"(?i)(?:\[\s*ans\s*[:：]?\s*([a-e])\s*\]|\bans\s*[:：]?\s*([a-e])\b|সমাধান\s*[:：]?\s*\(?\s*([a-e])\s*\)?|উত্তর\s*[:：]?\s*\(?\s*([a-e])\s*\)?)"
)


def _item_question_no(item: Dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return ""
    direct = _normalize_question_no_token(str(item.get('question_no') or ''))
    if direct:
        return direct
    return _normalize_question_no_token(_question_no_key(str(item.get('questions') or '')))


def _detect_question_numbers_from_clean_text(clean_text: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for line in str(clean_text or '').splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^([0-9\u09E6-\u09EF]{1,4})\s*[\.)\]:।-]?\s+", s)
        if not m:
            continue
        qno = _normalize_question_no_token(m.group(1))
        if qno and qno not in seen:
            seen.add(qno)
            out.append(qno)
    return out


def _assign_question_numbers_by_order(items: List[Dict[str, Any]], clean_text: str) -> List[Dict[str, Any]]:
    out = [dict(x or {}) for x in (items or [])]
    if not out:
        return out
    detected = _detect_question_numbers_from_clean_text(clean_text)
    if not detected:
        return out

    used = set()
    for it in out:
        qno = _item_question_no(it)
        if qno:
            it['question_no'] = qno
            used.add(qno)

    remaining = [q for q in detected if q not in used]
    missing_idx = [idx for idx, it in enumerate(out) if not _item_question_no(it)]
    if remaining and missing_idx:
        for idx, qno in zip(missing_idx, remaining):
            out[idx]['question_no'] = qno
    return out


def _extract_explicit_answer_marks_from_clean_text(clean_text: str) -> Dict[str, int]:
    marks: Dict[str, int] = {}
    current_qno = ""
    for line in str(clean_text or '').splitlines():
        s = line.strip()
        if not s:
            continue
        m_q = re.match(r"^([0-9\u09E6-\u09EF]{1,4})\s*[\.)\]:।-]?\s+", s)
        if m_q:
            current_qno = _normalize_question_no_token(m_q.group(1))
        m_ans = _EXPLICIT_ANSWER_LETTER_RE.search(s)
        if not m_ans:
            continue
        letter = next((g for g in m_ans.groups() if g), '')
        letter = str(letter or '').strip().upper()
        if current_qno and len(letter) == 1 and 'A' <= letter <= 'E':
            marks[current_qno] = ord(letter) - 64
    return marks


def _merge_textual_answer_marks(items: List[Dict[str, Any]], clean_text: str) -> Tuple[List[Dict[str, Any]], int]:
    merged = [dict(x or {}) for x in (items or [])]
    marks = _extract_explicit_answer_marks_from_clean_text(clean_text)
    if not marks:
        return merged, 0
    applied = 0
    for it in merged:
        qno = _item_question_no(it)
        if not qno:
            continue
        it['question_no'] = qno
        ans = int(marks.get(qno, 0) or 0)
        if ans <= 0:
            continue
        options = [str(it.get(f'option{i}') or '').strip() for i in range(1, 6) if str(it.get(f'option{i}') or '').strip()]
        if not (1 <= ans <= len(options)):
            continue
        if int(it.get('answer', 0) or 0) != ans:
            it['answer'] = ans
            if not str(it.get('explanation') or '').strip():
                it['explanation'] = 'Detected from the printed answer shown on the page.'
        applied += 1
    return merged, applied


def _question_text_match_score(query: str, item: Dict[str, Any]) -> float:
    q = _normalize_option_text_for_match(str(query or ''))
    if not q:
        return 0.0
    iq = _normalize_option_text_for_match(str((item or {}).get('questions') or ''))
    if not iq:
        return 0.0
    score = SequenceMatcher(None, q, iq).ratio()
    if q in iq or iq in q:
        score += 0.25
    for tok in [t for t in re.split(r"\s+", q) if len(t) >= 2][:8]:
        if tok in iq:
            score += 0.06
    return score


def _pick_first_mcq_item(items: List[Dict[str, Any]], extra_instruction: str = "") -> Optional[Dict[str, Any]]:
    pool = [dict(x) for x in (items or []) if str((x or {}).get('questions') or '').strip()]
    if not pool:
        return None
    ins = str(extra_instruction or '').strip()
    if not ins:
        return pool[0]

    qno = _normalize_question_no_token(ins)
    if qno:
        exact = [it for it in pool if _item_question_no(it) == qno]
        if exact:
            return exact[0]
        # fallback only when there are no assigned question numbers at all
        if not any(_item_question_no(it) for it in pool):
            idx = int(qno) - 1
            if 0 <= idx < len(pool):
                return pool[idx]

    best_item = None
    best_score = 0.0
    for it in pool:
        score = _question_text_match_score(ins, it)
        if score > best_score:
            best_score = score
            best_item = it
    if best_item and best_score >= 0.42:
        return best_item
    return pool[0]


def _extract_ocr_bundle_from_path(local_path: str, user_id: int) -> Dict[str, Any]:
    ocr = _mistral_ocr_process_path(local_path)
    pages = list(ocr.get('pages') or [])
    clean_text, items = _ocr_pages_to_clean_text_and_items(pages, user_id)
    items = _assign_question_numbers_by_order(items, clean_text)
    visual_items = _collect_visual_marked_items_for_path(local_path)
    letter_marks = _collect_visual_marked_letters_for_path(local_path)
    items, visual_applied_1 = _merge_visual_marked_answers(items, visual_items)
    items, visual_applied_2 = _merge_visual_letter_marks(items, letter_marks)
    items, textual_applied = _merge_textual_answer_marks(items, clean_text)
    items = _drop_unclear_mcq_items(items)
    return {
        'ocr': ocr,
        'clean_text': clean_text,
        'items': items,
        'visual_marked_count': int((visual_applied_1 or 0) + (visual_applied_2 or 0) + (textual_applied or 0)),
    }


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

    # Count only NEW source files. Re-replying to the same image/PDF should reuse cached OCR without spending quota.
    needs_quota = bool(reply_is_media and not reply_has_ctx)
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
        chooser = await update.message.reply_text(
            ui_box_text('Choose AI Model', 'Tap a model button below to answer from the replied OCR content.', emoji='🤖'),
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

# ===== END FINAL OCR QUESTION TARGETING + ANSWER MAP PATCH =====


