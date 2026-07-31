# ──────────────────────────────────────────────────────────────────────────────
# Section: 30_advanced_ocr_pdf_qans_picker_04_10
# Original lines: 15790..16368
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== ADVANCED OCR + PDF + /QANS PICKER PATCH (2026-04-10) =====

def _processing_box(title: str, detail: str) -> str:
    return ui_box_text(title, detail, emoji="⏳")

async def _processing_start(msg, title: str, detail: str):
    try:
        return await msg.reply_text(_processing_box(title, detail), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception:
        return None

async def _processing_update(proc_msg, title: str, detail: str):
    if not proc_msg:
        return
    with contextlib.suppress(Exception):
        await proc_msg.edit_text(_processing_box(title, detail), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def _processing_delete(proc_msg):
    if not proc_msg:
        return
    with contextlib.suppress(Exception):
        await proc_msg.delete()

_prev_mistral_ocr_process_path_20260410_adv = _mistral_ocr_process_path

def _mistral_ocr_process_path(path: str) -> Dict[str, Any]:
    api_key = get_mistral_api_key()
    if not api_key:
        raise RuntimeError("No Mistral API key configured. Use /mistral set YOUR_KEY first.")
    mime = _guess_mime_type(path)
    size_bytes = 0
    with contextlib.suppress(Exception):
        size_bytes = int(os.path.getsize(path) or 0)
    doc_payload = None
    if mime.startswith("image/") and size_bytes <= 6 * 1024 * 1024:
        raw_bytes = Path(path).read_bytes()
        b64 = base64.b64encode(raw_bytes).decode("utf-8")
        doc_payload = {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"}
    else:
        file_id = _mistral_upload_file(path, api_key)
        doc_payload = {"type": "file", "file_id": file_id}
    data = _mistral_ocr_request(doc_payload, api_key)
    pages = data.get("pages", []) or []
    chunks = []
    for i, page in enumerate(pages, start=1):
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


def _ocr_preserve_text_layout(text: str) -> str:
    s = str(text or "")
    if not s:
        return ""
    s = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", s)
    s = re.sub(r"\[[^\]]+\]\(([^)]+)\)", r"\1", s)
    s = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", s)
    s = re.sub(r"`{1,3}", "", s)
    s = clean_latex(s)
    lines = []
    for raw_line in s.splitlines():
        line = raw_line.replace("\t", " ").strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        line = re.sub(r"[ \u00A0]+", " ", line).strip()
        lines.append(line)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _pages_to_clean_text(pages: List[Dict[str, Any]]) -> str:
    parts = []
    for idx, page in enumerate(pages or [], start=1):
        md = str((page or {}).get("markdown") or "").strip()
        if not md:
            continue
        cleaned = _ocr_preserve_text_layout(md)
        if not cleaned:
            continue
        parts.append(f"[Page {idx}]\n{cleaned}")
    joined = "\n\n".join(parts).strip()
    return joined or _ocr_preserve_text_layout("\n\n".join([str((p or {}).get("markdown") or "") for p in (pages or [])]))


def _split_ocr_text_for_ai(text: str, max_chars: int = 4200) -> List[str]:
    body = str(text or "").strip()
    if not body:
        return []
    page_chunks = []
    current = []
    cur_len = 0
    for part in re.split(r"(?=\[Page\s+\d+\])", body):
        part = part.strip()
        if not part:
            continue
        if len(part) <= max_chars:
            page_chunks.append(part)
            continue
        blocks = re.split(r"\n\n+", part)
        current = []
        cur_len = 0
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            extra = len(block) + (2 if current else 0)
            if current and cur_len + extra > max_chars:
                page_chunks.append("\n\n".join(current).strip())
                current = [block]
                cur_len = len(block)
            else:
                current.append(block)
                cur_len += extra
        if current:
            page_chunks.append("\n\n".join(current).strip())
    return [c for c in page_chunks if c]


def _extract_mcq_items_from_chunk(chunk_text: str) -> List[Dict[str, Any]]:
    prompt = (
        "Return STRICT JSON only (no markdown).\n"
        "Task: Extract all visible MCQ questions from the OCR text chunk below.\n"
        "Rules:\n"
        "- Keep the original language exactly.\n"
        "- Preserve question wording as much as possible.\n"
        "- Extract every visible MCQ from this chunk.\n"
        "- Options must be clean plain text.\n"
        "- If a correct option is visibly marked/ticked/circled/underlined/dotted/boxed, set answer accordingly.\n"
        "- If the answer is not clearly marked, set answer to 0.\n"
        "- correct_option_text must repeat the exact correct option text when answer is known, otherwise empty.\n"
        "- explanation must stay short; empty if the answer is not visible.\n\n"
        "JSON format:\n"
        '{"items":[{"questions":"...","option1":"...","option2":"...","option3":"...","option4":"...","option5":"","answer":0,"correct_option_text":"","explanation":""}]}\n\n'
        f"OCR CHUNK:\n{chunk_text[:15000]}"
    )
    raw = None
    last_err = None
    if GEMINI_API_KEYS:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=10, force_json=True)
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
    if not raw:
        if last_err:
            raise last_err
        return []
    data = None
    try:
        data = _extract_json_strict(raw)
    except Exception:
        data = _repair_to_json(raw, schema_hint='{"items":[{"questions":"...","option1":"...","option2":"...","option3":"...","option4":"...","option5":"","answer":0,"correct_option_text":"","explanation":""}]}', timeout_seconds=8)
    if not isinstance(data, dict):
        return []
    out = []
    for it in (data.get("items") or [])[:80]:
        question = str(it.get("questions") or it.get("question") or "").strip()
        if not question:
            continue
        options = []
        if isinstance(it.get("options"), list):
            options = [str(x or "").strip() for x in (it.get("options") or []) if str(x or "").strip()]
        else:
            for k in ("option1", "option2", "option3", "option4", "option5"):
                val = str(it.get(k) or "").strip()
                if val:
                    options.append(val)
        if len(options) < 2:
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
        out.append(payload)
    return out


def _dedupe_mcq_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for item in items or []:
        q = str(item.get("questions") or "").strip()
        if not q:
            continue
        key = re.sub(r"\s+", " ", _normalize_option_text_for_match(q))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _ocr_pages_to_clean_text_and_items(pages: List[Dict[str, Any]], user_id: int) -> Tuple[str, List[Dict[str, Any]]]:
    clean_text = _pages_to_clean_text(pages)
    items: List[Dict[str, Any]] = []
    for chunk in _split_ocr_text_for_ai(clean_text, max_chars=4200):
        try:
            items.extend(_extract_mcq_items_from_chunk(chunk))
        except Exception:
            continue
    if not items:
        for block in split_blocks(clean_text):
            parsed = parse_text_block(block, user_id)
            if parsed:
                items.append(parsed)
    items = _dedupe_mcq_items(items)
    return clean_text, items


def _file_suffix_from_message(msg) -> str:
    if getattr(msg, "document", None):
        ext = os.path.splitext(str(msg.document.file_name or ""))[1].strip()
        if ext and len(ext) <= 8:
            return ext
    if getattr(msg, "photo", None):
        return ".jpg"
    return ".bin"


def _display_name_from_message(msg, fallback: str = "ocr_output") -> str:
    if getattr(msg, "document", None):
        name = os.path.splitext(str(msg.document.file_name or "").strip())[0]
        if name:
            return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:60]
    return fallback


def _pick_first_mcq_item(items: List[Dict[str, Any]], extra_instruction: str = "") -> Optional[Dict[str, Any]]:
    pool = [dict(x) for x in (items or []) if str((x or {}).get("questions") or "").strip()]
    if not pool:
        return None
    ins = str(extra_instruction or "").strip()
    if ins:
        m = re.search(r"(?:q|question|প্রশ্ন)?\s*(\d{1,3})", ins, flags=re.I)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(pool):
                return pool[idx]
    return pool[0]


async def _run_staff_ocr_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE, source_msg, local_path: str, *, source_label: str = "image") -> Dict[str, Any]:
    uid = update.effective_user.id if update and update.effective_user else 0
    proc = await _processing_start(source_msg, "OCR Processing", f"Preparing {source_label} for OCR...")
    try:
        await _processing_update(proc, "OCR Processing", "Running Mistral OCR...")
        ocr = await _run_blocking(_role_of(uid), _mistral_ocr_process_path, local_path, timeout=180)
        raw_markdown = str(ocr.get("raw_markdown") or "").strip()
        pages = ocr.get("pages") or []
        if not raw_markdown and not pages:
            raise RuntimeError("Mistral OCR could not read usable text from this file.")
        await _processing_update(proc, "OCR Processing", "Structuring text and extracting MCQs...")
        clean_text, items = await _run_blocking(_role_of(uid), _ocr_pages_to_clean_text_and_items, list(pages), uid, timeout=180)

        added = 0
        for payload in items:
            if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
                break
            p = dict(payload)
            if not explain_mode_on(uid):
                p["explanation"] = ""
            buffer_add(uid, p)
            added += 1

        ctx_payload = {
            "raw_markdown": raw_markdown,
            "clean_text": clean_text,
            "items": items,
            "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
            "page_count": len(pages),
            "source_label": source_label,
        }
        _remember_ocr_context(context, source_msg.message_id, ctx_payload)

        await _processing_delete(proc)
        proc = None

        preview = clean_text.strip()
        if len(preview) > 1800:
            preview = preview[:1797].rstrip() + "..."
        status_bits = [
            f"OCR model: <code>{h(str(ocr.get('model') or MISTRAL_OCR_MODEL))}</code>",
            f"Pages: <code>{h(str(len(pages) or 1))}</code>",
            f"Characters: <code>{h(str(len(clean_text)))}</code>",
            f"Buffered MCQ: <code>{h(str(added))}</code>",
        ]
        preview_msg = await source_msg.reply_text(
            ui_box_html("Mistral OCR Complete", "\n".join(status_bits) + (f"\n\n{h(preview)}" if preview else ""), emoji="🧾"),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        _remember_ocr_context(context, preview_msg.message_id, ctx_payload)

        base_name = _display_name_from_message(source_msg, fallback=f"mistral_ocr_{uid}")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write(clean_text)
            txt_path = tf.name
        try:
            with open(txt_path, "rb") as fh:
                sent_doc = await source_msg.reply_document(
                    document=fh,
                    filename=f"{base_name}_ocr.txt",
                    caption=f"<b>✅ OCR Text Extracted</b>\n<i>{h(str(len(clean_text)))} characters • {h(str(len(pages) or 1))} pages</i>",
                    parse_mode=ParseMode.HTML,
                )
            _remember_ocr_context(context, sent_doc.message_id, ctx_payload)
        finally:
            with contextlib.suppress(Exception):
                os.remove(txt_path)

        if added:
            ready = await source_msg.reply_text(
                ui_box_html("OCR + Quiz Buffer Ready", f"Buffered <code>{h(str(added))}</code> MCQ(s).\nUse <code>/done</code> to export or <code>/post</code> to publish.\nReply with <code>/qans</code> to choose an AI model and solve.", emoji="✅"),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            _remember_ocr_context(context, ready.message_id, ctx_payload)
        else:
            ready = await source_msg.reply_text(
                ui_box_html("OCR Text Extracted", "Text was extracted successfully, but no clean MCQ set was detected for buffering.\nReply with <code>/qans</code> to choose an AI model and solve from the OCR text.", emoji="⚠️"),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            _remember_ocr_context(context, ready.message_id, ctx_payload)
        return ctx_payload
    except Exception:
        await _processing_delete(proc)
        raise


_prev_handle_image_20260410_adv = handle_image

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = update.effective_user.id
    if is_banned(uid) or not is_private_chat(update) or not _can_use_staff_ocr(uid) or not vision_mode_on(uid):
        return await _prev_handle_image_20260410_adv(update, context)
    if not mistral_runtime_enabled():
        return await _prev_handle_image_20260410_adv(update, context)
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
    elif msg.document and str(getattr(msg.document, "mime_type", "") or "").startswith("image/"):
        tg_file = await msg.document.get_file()
        suffix = _file_suffix_from_message(msg)
    else:
        return await _prev_handle_image_20260410_adv(update, context)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        local_path = f.name
    await tg_file.download_to_drive(local_path)
    try:
        await _run_staff_ocr_pipeline(update, context, msg, local_path, source_label="image")
    except Exception as e:
        db_log("ERROR", "mistral_ocr_handle_image_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Mistral OCR Failed", str(e)[:220])
    finally:
        with contextlib.suppress(Exception):
            os.remove(local_path)


async def handle_private_ocr_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = update.effective_user.id
    msg = update.message
    doc = getattr(msg, "document", None)
    if not doc:
        return
    mime = str(getattr(doc, "mime_type", "") or "").strip().lower()
    file_name = str(getattr(doc, "file_name", "") or "").lower()
    is_pdf = (mime == "application/pdf") or file_name.endswith(".pdf")
    if not is_pdf:
        return
    if is_banned(uid) or not is_private_chat(update) or not _can_use_staff_ocr(uid) or not vision_mode_on(uid):
        return
    if not mistral_runtime_enabled():
        return
    if not get_mistral_api_key():
        await warn(update, "Mistral API Key Missing", "Use /mistral set YOUR_KEY first, or turn Mistral OCR off with /mistral off.")
        return
    if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
        await warn(update, "Buffer Limit Reached", f"You have {MAX_BUFFERED_QUESTIONS} questions buffered.\n\nUse /done to export or /clear to reset.")
        return
    tg_file = await doc.get_file()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        local_path = f.name
    await tg_file.download_to_drive(local_path)
    try:
        await _run_staff_ocr_pipeline(update, context, msg, local_path, source_label="pdf")
    except Exception as e:
        db_log("ERROR", "mistral_ocr_handle_pdf_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Mistral OCR Failed", str(e)[:220])
    finally:
        with contextlib.suppress(Exception):
            os.remove(local_path)


async def cmd_qans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    if not is_private_chat(update):
        await warn(update, "Private Only", "Use this command in private chat by replying to an image, PDF, text, or quiz.")
        return
    uid = update.effective_user.id
    if not _can_use_staff_ocr(uid):
        await warn_unauthorized(update, "Only Owner/Admin OCR users can use this command.")
        return
    reply_msg = update.message.reply_to_message
    if not reply_msg:
        await safe_reply(update, usage_box("qans", "[extra instruction]", "Reply to an image, PDF, OCR text, text question, or poll, then use this command."))
        return

    extra_instruction = " ".join(context.args or []).strip()
    ocr_ctx = _get_ocr_context(context, reply_msg.message_id)
    proc = None
    try:
        payload = None
        kind = "text"
        prompt_note = ""

        if getattr(reply_msg, "poll", None):
            poll = reply_msg.poll
            question = str(poll.question or "").strip()
            options = [str(o.text or "").strip() for o in (poll.options or []) if str(o.text or "").strip()]
            if len(options) < 2:
                raise RuntimeError("This poll does not contain enough options.")
            payload = {
                "question": question,
                "options": options,
                "official_ans": _poll_official_answer(poll),
                "official_expl": str(getattr(poll, "explanation", "") or "").strip(),
            }
            kind = "poll"
            prompt_note = "Choose the AI model to solve this quiz."
        else:
            if not ocr_ctx and (reply_msg.photo or (reply_msg.document and (str(getattr(reply_msg.document, "mime_type", "") or "").startswith("image/") or str(getattr(reply_msg.document, "mime_type", "") or "").lower() == "application/pdf" or str(getattr(reply_msg.document, "file_name", "") or "").lower().endswith(".pdf")))):
                if not mistral_runtime_enabled() or not get_mistral_api_key():
                    raise RuntimeError("Mistral OCR is not ready. Use /mistral status or /mistral set YOUR_KEY first.")
                suffix = ".jpg"
                if reply_msg.document:
                    mime = str(getattr(reply_msg.document, "mime_type", "") or "").lower()
                    suffix = ".pdf" if mime == "application/pdf" or str(getattr(reply_msg.document, "file_name", "") or "").lower().endswith(".pdf") else _file_suffix_from_message(reply_msg)
                    tg_file = await reply_msg.document.get_file()
                else:
                    tg_file = await reply_msg.photo[-1].get_file()
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    local_path = f.name
                proc = await _processing_start(update.message, "Preparing /qans", "Running OCR on the replied file...")
                await tg_file.download_to_drive(local_path)
                try:
                    await _processing_update(proc, "Preparing /qans", "Reading the file and preparing AI choices...")
                    ocr = await _run_blocking(_role_of(uid), _mistral_ocr_process_path, local_path, timeout=180)
                    clean_text, items = await _run_blocking(_role_of(uid), _ocr_pages_to_clean_text_and_items, list(ocr.get("pages") or []), uid, timeout=180)
                    ocr_ctx = {
                        "raw_markdown": str(ocr.get("raw_markdown") or ""),
                        "clean_text": clean_text,
                        "items": items,
                        "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
                        "page_count": len(ocr.get("pages") or []),
                    }
                    _remember_ocr_context(context, reply_msg.message_id, ocr_ctx)
                finally:
                    with contextlib.suppress(Exception):
                        os.remove(local_path)

            if ocr_ctx:
                picked = _pick_first_mcq_item(ocr_ctx.get("items") or [], extra_instruction)
                if picked:
                    options = [str(picked.get(f"option{i}") or "").strip() for i in range(1, 6) if str(picked.get(f"option{i}") or "").strip()]
                    if len(options) >= 2:
                        payload = {
                            "question": str(picked.get("questions") or "").strip(),
                            "options": options,
                            "official_ans": int(picked.get("answer", 0) or 0),
                            "official_expl": str(picked.get("explanation") or "").strip(),
                        }
                        kind = "poll"
                        prompt_note = "Choose the AI model to solve the extracted MCQ."
                if payload is None:
                    source_text = str(ocr_ctx.get("clean_text") or ocr_ctx.get("raw_markdown") or "").strip()
                    if not source_text:
                        raise RuntimeError("No readable OCR text found in the replied file.")
                    if extra_instruction:
                        source_text = f"{source_text}\n\nExtra user instruction:\n{extra_instruction}"
                    payload = {"text": source_text, "source_user_text": source_text}
                    kind = "text"
                    prompt_note = "Choose the AI model to solve from the OCR text."
            else:
                source_text = str(reply_msg.text or reply_msg.caption or "").strip()
                if not source_text:
                    raise RuntimeError("No readable text found in the replied message.")
                if extra_instruction:
                    source_text = f"{source_text}\n\nExtra user instruction:\n{extra_instruction}"
                payload = {"text": source_text, "source_user_text": source_text}
                kind = "text"
                prompt_note = "Choose the AI model to answer this prompt."

        token = _make_token()
        store = _pending_store(context)
        store[token] = {
            "uid": uid,
            "kind": kind,
            "scope": "private_academic",
            "chat_id": update.message.chat_id,
            "payload": payload,
        }
        await _processing_delete(proc)
        proc = None
        header = ui_box_html("Choose AI Model", prompt_note, emoji="🤖")
        await safe_reply(update, header)
        await update.message.reply_text(
            ui_box_text("AI Options", "Tap a model button below to get the response.", emoji="⚙️"),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_solver_picker_kb(token),
        )
    except Exception as e:
        await _processing_delete(proc)
        db_log("ERROR", "qans_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Question Answer Failed", str(e)[:220])


_prev_build_app_20260410_adv = build_app

def build_app() -> Application:
    app = _prev_build_app_20260410_adv()
    with contextlib.suppress(Exception):
        app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Document.ALL, handle_private_ocr_document))
    return app

# ===== END ADVANCED OCR + PDF + /QANS PICKER PATCH =====


