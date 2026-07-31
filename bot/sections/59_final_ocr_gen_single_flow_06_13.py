# ──────────────────────────────────────────────────────────────────────────────
# Section: 59_final_ocr_gen_single_flow_06_13
# Final single-flow override:
#   • one OCR result card only (no duplicate action-card spam)
#   • source-image MCQs stay selectable separately for CSV/channel post
#   • missing answers are AI-verified before buffering
#   • .gen / .gen med|eng|engg|ver|std [N] uses a direct, non-forged flow
# DO NOT import directly — exec'd in shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

_SRC_STORE_59_KEY = "_source_mcq_action_store_59"
_GEN59_STORE_KEY = "_pending_gen_flow_59"


def _src_store_59(context) -> Dict[str, Any]:
    bd = context.application.bot_data
    if _SRC_STORE_59_KEY not in bd:
        bd[_SRC_STORE_59_KEY] = {}
    return bd[_SRC_STORE_59_KEY]


def _g59_store(context) -> Dict[str, Any]:
    bd = context.application.bot_data
    if _GEN59_STORE_KEY not in bd:
        bd[_GEN59_STORE_KEY] = {}
    return bd[_GEN59_STORE_KEY]


def _mode_count_59(text: str, args) -> Tuple[Optional[str], Optional[int], List[str]]:
    raw = str(text or "").strip().lower()
    toks = [str(x or "").strip().lower() for x in (args or []) if str(x or "").strip()]
    if not toks:
        parts = re.split(r"\s+", raw)
        toks = [p for p in parts[1:] if p] if parts and re.match(r"^[./]?gen(?:@\w+)?$", parts[0]) else []
    alias = {
        "med": "med", "medical": "med", "mbbs": "med", "dental": "med",
        "eng": "eng", "engg": "eng", "engineering": "eng", "buet": "eng",
        "ver": "ver", "versity": "ver", "varsity": "ver", "university": "ver", "univ": "ver",
        "std": "std", "standard": "std", "hsc": "std",
    }
    mode = None
    cleaned: List[str] = []
    count = None
    for t in toks:
        tt = re.sub(r"[^0-9a-z]+", "", t)
        if tt in alias:
            mode = alias[tt]
            continue
        m = re.search(r"\d{1,4}", tt)
        if m and count is None:
            count = max(1, min(500, int(m.group(0))))
            cleaned.append(str(count))
            continue
        cleaned.append(t)
    return mode, count, cleaned


def _source_hash_59(ocr_ctx: Dict[str, Any], mode: str = "std") -> str:
    try:
        base = _ocr_source_hash(ocr_ctx)
    except Exception:
        base = hashlib.md5(str(ocr_ctx or {}).encode("utf-8", "ignore")).hexdigest()
    return f"{mode}:{base}"


def _opts_59(it: Dict[str, Any]) -> List[str]:
    return [str((it or {}).get(f"option{i}") or "").strip() for i in range(1, 6) if str((it or {}).get(f"option{i}") or "").strip()]


def _apply_visible_answer_marks_59(it: Dict[str, Any]) -> Dict[str, Any]:
    o = dict(it or {})
    opts = _opts_59(o)
    if not opts:
        return o
    if int(o.get("answer", 0) or 0) <= 0:
        for idx, opt in enumerate(opts, start=1):
            if re.search(r"(^|\s)(?:✓|✔|✅|☑|⊙|●|◉|\[\s*ans\s*\])", opt, flags=re.I):
                o["answer"] = idx
                break
    for idx, opt in enumerate(opts, start=1):
        clean = re.sub(r"(?:✓|✔|✅|☑|⊙|●|◉)", "", opt).strip()
        o[f"option{idx}"] = clean
    return o


def _ai_fill_missing_answers_59(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = [_apply_visible_answer_marks_59(dict(x or {})) for x in (items or [])]
    missing = []
    for idx, it in enumerate(out):
        opts = _opts_59(it)
        ans = int(it.get("answer", 0) or 0)
        if opts and not (1 <= ans <= len(opts)):
            missing.append((idx, it, opts))
    if not missing:
        return out
    payload = []
    for idx, it, opts in missing[:80]:
        payload.append({"idx": idx, "q": str(it.get("questions") or "")[:600], "options": opts[:5]})
    prompt = (
        "Return STRICT JSON only. Solve the MCQs and choose the correct option. "
        "Use Bangladesh HSC/admission-level science knowledge when needed. "
        "If the printed answer mark is absent, infer the academically correct answer from the question/options. "
        "JSON: {\"answers\":[{\"idx\":0,\"answer\":1,\"explanation\":\"short reason\"}]}\n\n"
        f"MCQS:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    raw = None
    try:
        if GEMINI_API_KEYS:
            raw = call_gemini_text_rest(prompt, timeout_seconds=35, force_json=True)
    except Exception:
        raw = None
    if not raw:
        with contextlib.suppress(Exception):
            raw = gemini3_solve(prompt)
    data = None
    if raw:
        with contextlib.suppress(Exception):
            data = _extract_json_strict(raw)
    if isinstance(data, dict):
        for row in data.get("answers") or []:
            try:
                idx = int(row.get("idx"))
                ans = int(row.get("answer"))
                opts = _opts_59(out[idx])
                if 0 <= idx < len(out) and 1 <= ans <= len(opts):
                    out[idx]["answer"] = ans
                    if not str(out[idx].get("explanation") or "").strip():
                        out[idx]["explanation"] = _hard_trim_expl(str(row.get("explanation") or "AI verified answer.")) if "_hard_trim_expl" in globals() else str(row.get("explanation") or "AI verified answer.")[:180]
                    out[idx]["answer_checked"] = "ai"
            except Exception:
                continue
    # Last safety: a quiz poll cannot be posted without a correct_option_id.
    # This path should rarely run; it keeps export/post flows from breaking.
    for it in out:
        opts = _opts_59(it)
        ans = int(it.get("answer", 0) or 0)
        if opts and not (1 <= ans <= len(opts)):
            it["answer"] = 1
            it.setdefault("explanation", "AI answer check unavailable; please verify.")
    return out


def _clean_source_items_59(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    checked = _ai_fill_missing_answers_59(items or [])
    out: List[Dict[str, Any]] = []
    seen = set()
    for raw in checked:
        it = dict(raw or {})
        q = str(it.get("questions") or "").strip()
        opts = _opts_59(it)
        ans = int(it.get("answer", 0) or 0)
        if not q or len(opts) < 2 or not (1 <= ans <= len(opts)):
            continue
        if re.search(r"(উদ্দীপক|উদ্দীপকের|নিচের\s*চিত্র|উপরের\s*আলোকে|তথ্যের\s*আলোকে)", q):
            continue
        for i in range(5):
            it[f"option{i+1}"] = opts[i] if i < len(opts) else ""
        it["answer"] = ans
        it["type"] = int(it.get("type", 1) or 1)
        it["section"] = int(it.get("section", 1) or 1)
        it["source"] = "ocr_source_checked"
        with contextlib.suppress(Exception):
            it = _enforce_option_parity(it)
        fp = _fp_question(it) if "_fp_question" in globals() else hashlib.md5(q.lower().encode("utf-8", "ignore")).hexdigest()
        if fp in seen:
            continue
        seen.add(fp)
        out.append(it)
    return out


def _estimate_counts_fast_59(source_count: int, text: str = "") -> Dict[str, int]:
    n = max(0, int(source_count or 0))
    if n <= 0:
        base = 5 if len(str(text or "")) > 500 else 0
        return {"easy": max(0, base // 3), "medium": max(0, base // 3), "hard": max(0, base - 2 * (base // 3)), "ocr_checked": 0, "source_checked": 0}
    easy = max(1, round(n * 0.35))
    medium = max(1, round(n * 0.45))
    hard = max(0, n - easy - medium)
    return {"easy": easy, "medium": medium, "hard": hard, "ocr_checked": n, "source_checked": n}


def _genq_kb_59(token: str, counts: Dict[str, int]) -> InlineKeyboardMarkup:
    e, m, hd = int(counts.get("easy", 0)), int(counts.get("medium", 0)), int(counts.get("hard", 0))
    src = int(counts.get("source_checked", counts.get("ocr_checked", 0)) or 0)
    total = e + m + hd
    rows: List[List[InlineKeyboardButton]] = []
    first: List[InlineKeyboardButton] = []
    if total > 0:
        first.append(InlineKeyboardButton(f"✅ Generate ({total})", callback_data=f"genq:go:{token}"))
    if src > 0:
        first.append(InlineKeyboardButton(f"📌 Source MCQ ({src})", callback_data=f"genq:src:{token}"))
    if first:
        rows.append(first)
    diff: List[InlineKeyboardButton] = []
    if e > 0:
        diff.append(InlineKeyboardButton(f"🟢 Easy ({e})", callback_data=f"genq:ge:{token}"))
    if m > 0:
        diff.append(InlineKeyboardButton(f"🟡 Medium ({m})", callback_data=f"genq:gm:{token}"))
    if hd > 0:
        diff.append(InlineKeyboardButton(f"🔴 Hard ({hd})", callback_data=f"genq:gh:{token}"))
    if diff:
        rows.append(diff)
    rows.append([InlineKeyboardButton("🔁 More Generate (+5)", callback_data=f"genq:mo:{token}")])
    rows.append([InlineKeyboardButton("🔄 Re-check", callback_data=f"genq:re:{token}"), InlineKeyboardButton("🚫 Skip", callback_data=f"genq:no:{token}")])
    return InlineKeyboardMarkup(rows)


globals()["_genq_kb"] = _genq_kb_59


def _src_action_kb_59(token: str, channels: List[Any]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    quick: List[InlineKeyboardButton] = []
    for ch in (channels or [])[:6]:
        title = (getattr(ch, "title", None) or str(getattr(ch, "channel_chat_id", "?")))[:18]
        quick.append(InlineKeyboardButton(f"📤 {title}", callback_data=f"src59:post:{ch.id}:{token}"))
    while quick:
        rows.append(quick[:2])
        quick = quick[2:]
    if len(channels or []) > 6:
        rows.append([InlineKeyboardButton("🎯 More channels…", callback_data=f"src59:list:{token}")])
    rows.append([InlineKeyboardButton("📂 Source CSV", callback_data=f"src59:csv:{token}")])
    rows.append([InlineKeyboardButton("✖ Close", callback_data=f"src59:close:{token}")])
    return InlineKeyboardMarkup(rows)


async def _show_source_actions_59(q, context, token: str, entry: Dict[str, Any]):
    uid = int(entry.get("uid") or 0)
    items = list(entry.get("source_items") or [])
    try:
        channels = channel_list_for_user(uid) or []
    except Exception:
        channels = []
    _src_store_59(context)[token] = {
        "uid": uid,
        "chat_id": int(entry.get("chat_id") or q.message.chat_id),
        "items": items,
        "ts": time.time(),
    }
    body = (
        f"Image/PDF থেকে পাওয়া checked MCQ: <code>{len(items)}</code>\n"
        "এগুলো original source প্রশ্ন — new generated নয়."
    )
    if not channels:
        body += "\n\n<i>Tip: /addchannel দিয়ে channel add করলে এখান থেকেই post করা যাবে.</i>"
    with contextlib.suppress(Exception):
        await q.edit_message_text(
            ui_box_html("Source MCQ Actions", body, emoji="📌"),
            parse_mode=ParseMode.HTML,
            reply_markup=_src_action_kb_59(token, channels),
            disable_web_page_preview=True,
        )


async def _export_items_csv_59(context, chat_id: int, uid: int, rows_items: List[Dict[str, Any]], prefix: str):
    rows = _csv_ready_rows([(i, it) for i, it in enumerate(rows_items)], uid) if "_csv_ready_rows" in globals() else []
    if not rows:
        rows = []
        for it in rows_items:
            opts = _opts_59(it)
            ans = int(it.get("answer", 0) or 0)
            rows.append({
                "questions": it.get("questions", ""),
                "option1": opts[0] if len(opts) > 0 else "",
                "option2": opts[1] if len(opts) > 1 else "",
                "option3": opts[2] if len(opts) > 2 else "",
                "option4": opts[3] if len(opts) > 3 else "",
                "option5": opts[4] if len(opts) > 4 else "",
                "answer": ans,
                "correct_answer": {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}.get(ans, ""),
                "answer_text": opts[ans - 1] if 1 <= ans <= len(opts) else "",
                "explanation": it.get("explanation", ""),
                "type": it.get("type", 1),
                "section": it.get("section", 1),
            })
    with tempfile.NamedTemporaryFile("w+b", suffix=".csv", delete=False) as f:
        path = f.name
    try:
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
        with open(path, "rb") as rf:
            await context.bot.send_document(
                chat_id=chat_id,
                document=rf,
                filename=f"{prefix}_{int(time.time())}.csv",
                caption=f"📂 CSV — {len(rows)} questions",
            )
    finally:
        with contextlib.suppress(Exception):
            os.remove(path)


async def _post_items_59(context, uid: int, chat_id: int, ch, items: List[Dict[str, Any]]) -> Tuple[int, int]:
    target_chat_id = ch.channel_chat_id
    reply_kw: Dict[str, Any] = {}
    with contextlib.suppress(Exception):
        anchor_chat, anchor_msg = _get_topic_anchor(uid)
        if anchor_msg:
            reply_kw = _make_reply_params(anchor_msg) if anchor_chat == target_chat_id else _make_reply_params(anchor_msg, chat_id=anchor_chat)
    posted = failed = 0
    for raw in items:
        try:
            it = _sanitize_item_for_poll(raw) if "_sanitize_item_for_poll" in globals() else dict(raw or {})
            opts = _opts_59(it)[:10]
            ans = int(it.get("answer", 0) or 0)
            if len(opts) < 2 or not (1 <= ans <= len(opts)):
                failed += 1
                continue
            qtext = str(it.get("questions") or "").strip()
            if "_v57_apply_prefix" in globals():
                qtext = _v57_apply_prefix(ch, qtext)
            else:
                pfx = (getattr(ch, "prefix", "") or "").strip()
                if pfx and not qtext.startswith(pfx):
                    qtext = f"{pfx}\n{qtext}"
            expl = ""
            if explain_mode_on(uid):
                expl = _trim_expl_for_poll(str(it.get("explanation") or ""))
                if "_v57_apply_expl" in globals():
                    expl = _v57_apply_expl(ch, expl)
            kw = dict(chat_id=target_chat_id, question=qtext[:300], options=opts, type=Poll.QUIZ,
                      correct_option_id=ans - 1, is_anonymous=True,
                      explanation=expl if expl else None,
                      explanation_parse_mode=ParseMode.HTML if expl else None)
            if reply_kw:
                kw.update(reply_kw)
            await context.bot.send_poll(**kw)
            posted += 1
            await asyncio.sleep(2.0)
        except RetryAfter as ra:
            await asyncio.sleep(float(getattr(ra, "retry_after", 2)) + 1.0)
        except Exception as e:
            failed += 1
            with contextlib.suppress(Exception):
                db_log("WARN", "post_items_59_failed", {"user_id": uid, "error": str(e)})
    return posted, failed


async def _resolve_ocr_ctx_59(update, context, reply_msg, uid: int) -> Optional[Dict[str, Any]]:
    ocr_ctx = None
    with contextlib.suppress(Exception):
        if _has_ocr_context(context, reply_msg):
            ocr_ctx = _get_ocr_context(context, reply_msg.message_id)
    if ocr_ctx:
        return ocr_ctx
    is_media = bool(getattr(reply_msg, "photo", None) or getattr(reply_msg, "document", None))
    if not is_media:
        return None
    if not mistral_runtime_enabled() or not get_mistral_api_key():
        return None
    local_path = None
    try:
        if getattr(reply_msg, "document", None):
            name = str(reply_msg.document.file_name or "")
            suffix = os.path.splitext(name)[1].strip() or ".jpg"
            if len(suffix) > 8:
                suffix = ".jpg"
            tg_file = await reply_msg.document.get_file()
        else:
            suffix = ".jpg"
            tg_file = await reply_msg.photo[-1].get_file()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            local_path = f.name
        await tg_file.download_to_drive(local_path)
        bundle = await _run_blocking(_role_of(uid), _extract_ocr_bundle_from_path, local_path, uid, timeout=300)
        ocr = bundle.get("ocr") or {}
        ocr_ctx = {
            "raw_markdown": str(ocr.get("raw_markdown") or ""),
            "clean_text": str(bundle.get("clean_text") or ""),
            "items": list(bundle.get("items") or []),
            "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
            "page_count": len(ocr.get("pages") or []),
        }
        with contextlib.suppress(Exception):
            _remember_ocr_context(context, reply_msg.message_id, ocr_ctx)
        return ocr_ctx
    finally:
        if local_path:
            with contextlib.suppress(Exception):
                os.remove(local_path)


async def _generate_to_buffer_59(update, context, ocr_ctx: Dict[str, Any], uid: int, count: int, mode: str = "std") -> Tuple[int, int]:
    count = max(1, min(500, int(count or 20)))
    globals()["_active_gen_mode_57"] = mode or "std"
    try:
        items = await _run_blocking(_role_of(uid), _generate_quizzes_from_ocr_sync, ocr_ctx, count, uid, timeout=420)
    finally:
        globals()["_active_gen_mode_57"] = None
    seen = set()
    with contextlib.suppress(Exception):
        seen.update(_gen_seen_for(context, uid, _source_hash_59(ocr_ctx, mode)))
    with contextlib.suppress(Exception):
        for _, it in (buffer_list(uid, limit=99999) or []):
            seen.add(_fp_question(it))
    added = dup = 0
    for raw in items or []:
        try:
            q = str(raw.get("question") or raw.get("questions") or "").strip()
            opts = raw.get("options") if isinstance(raw.get("options"), list) else _opts_59(raw)
            opts = [str(o or "").strip() for o in (opts or []) if str(o or "").strip()][:5]
            ans = int(raw.get("answer", 1) or 1)
            if not q or len(opts) < 2 or not (1 <= ans <= len(opts)):
                continue
            payload = {"questions": q, "answer": ans, "explanation": str(raw.get("explanation") or "")[:200], "type": 1, "section": 1, "source": f"gen_{mode}"}
            for i in range(5):
                payload[f"option{i+1}"] = opts[i] if i < len(opts) else ""
            with contextlib.suppress(Exception):
                payload = _enforce_option_parity(payload)
            fp = _fp_question(payload) if "_fp_question" in globals() else hashlib.md5(q.lower().encode("utf-8", "ignore")).hexdigest()
            if fp in seen:
                dup += 1
                continue
            if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
                break
            if not explain_mode_on(uid):
                payload["explanation"] = ""
            buffer_add(uid, payload)
            seen.add(fp)
            added += 1
        except Exception:
            continue
    with contextlib.suppress(Exception):
        _gen_seen_for(context, uid, _source_hash_59(ocr_ctx, mode)).update(seen)
    return added, dup


async def cb_genq_59(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) != 3 or parts[0] != "genq":
        return
    action, token = parts[1], parts[2]
    store = _genq_store(context)
    entry = store.get(token)
    if not entry:
        with contextlib.suppress(Exception):
            await q.answer("Expired", show_alert=False)
        raise ApplicationHandlerStop
    uid = int(entry.get("uid") or 0)
    if q.from_user and int(q.from_user.id) != uid:
        with contextlib.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        raise ApplicationHandlerStop
    chat_id = int(entry.get("chat_id") or q.message.chat_id)
    text = str(entry.get("text") or "")
    counts = dict(entry.get("counts") or {})
    page_idx = int(entry.get("page") or 1)

    if action == "no":
        store.pop(token, None)
        with contextlib.suppress(Exception):
            await q.edit_message_text(ui_box_html("Skipped", "No extra generation started.", emoji="🚫"), parse_mode=ParseMode.HTML)
        raise ApplicationHandlerStop

    if action == "src":
        await _show_source_actions_59(q, context, token, entry)
        raise ApplicationHandlerStop

    if action == "re":
        src_items = _clean_source_items_59(list(entry.get("source_items") or []))
        entry["source_items"] = src_items
        counts = _estimate_counts_fast_59(len(src_items), text)
        entry["counts"] = counts
        store[token] = entry
        body = (
            f"📄 OCR Page Ready\n"
            f"• Source checked MCQ: <code>{len(src_items)}</code>\n"
            f"• Easy: <code>{counts['easy']}</code> | Medium: <code>{counts['medium']}</code> | Hard: <code>{counts['hard']}</code>\n\n"
            "Generate new unique MCQs or use 📌 Source MCQ for original image/PDF questions."
        )
        with contextlib.suppress(Exception):
            await q.edit_message_text(ui_box_html("Quiz Options", body, emoji="🧠"), parse_mode=ParseMode.HTML, reply_markup=_genq_kb_59(token, counts))
        raise ApplicationHandlerStop

    if action in ("go", "ge", "gm", "gh", "mo"):
        if action == "ge":
            easy, medium, hard = int(counts.get("easy", 0)), 0, 0
        elif action == "gm":
            easy, medium, hard = 0, int(counts.get("medium", 0)), 0
        elif action == "gh":
            easy, medium, hard = 0, 0, int(counts.get("hard", 0))
        elif action == "mo":
            easy, medium, hard = 2, 2, 1
        else:
            easy, medium, hard = int(counts.get("easy", 0)), int(counts.get("medium", 0)), int(counts.get("hard", 0))
        if (easy + medium + hard) <= 0:
            easy, medium, hard = 2, 2, 1
        seen = set(entry.get("seen_fp") or set())
        hint = "\n\n[Generate ONLY NEW unique MCQs. Do not repeat source questions or earlier generated questions.]" if seen else ""
        with contextlib.suppress(Exception):
            await q.answer("Generating…")
            await q.edit_message_text(ui_box_html("Generating", f"Creating <code>{easy+medium+hard}</code> new MCQ(s)…", emoji="⏳"), parse_mode=ParseMode.HTML)
        try:
            items = await _run_blocking(_role_of(uid), _generate_mcqs_from_content, (text + hint)[:7000], easy=easy, medium=medium, hard=hard, timeout=150)
        except Exception as e:
            db_log("ERROR", "genq_59_generate_failed", {"user_id": uid, "error": str(e)})
            items = []
        added = 0
        for raw in items or []:
            try:
                fp = _fp_question(raw)
                if fp in seen:
                    continue
                if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
                    break
                pp = dict(raw)
                if not explain_mode_on(uid):
                    pp["explanation"] = ""
                buffer_add(uid, pp)
                seen.add(fp)
                added += 1
            except Exception:
                continue
        entry["seen_fp"] = seen
        entry["more_added"] = int(entry.get("more_added", 0) or 0) + added
        store[token] = entry
        body = f"Added new unique MCQ: <code>{added}</code>\nBuffered total: <code>{buffer_count(uid)}</code>"
        with contextlib.suppress(Exception):
            await q.edit_message_text(ui_box_html("Generated → Buffer", body, emoji="✅"), parse_mode=ParseMode.HTML, reply_markup=_genq_kb_59(token, counts))
        if added > 0:
            with contextlib.suppress(Exception):
                await _send_pb_action_card(context, chat_id, uid, added)
        raise ApplicationHandlerStop


async def cb_src59(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) < 3 or parts[0] != "src59":
        return
    action, token = parts[1], parts[-1]
    store = _src_store_59(context)
    entry = store.get(token)
    if not entry:
        with contextlib.suppress(Exception):
            await q.answer("Expired", show_alert=False)
        raise ApplicationHandlerStop
    uid = int(entry.get("uid") or 0)
    if q.from_user and int(q.from_user.id) != uid:
        with contextlib.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        raise ApplicationHandlerStop
    chat_id = int(entry.get("chat_id") or q.message.chat_id)
    items = list(entry.get("items") or [])
    if action == "close":
        with contextlib.suppress(Exception):
            await q.edit_message_reply_markup(reply_markup=None)
        raise ApplicationHandlerStop
    if action == "csv":
        with contextlib.suppress(Exception):
            await q.answer("Exporting…")
        await _export_items_csv_59(context, chat_id, uid, items, "source_checked_mcq")
        raise ApplicationHandlerStop
    if action == "list":
        try:
            channels = channel_list_for_user(uid) or []
        except Exception:
            channels = []
        rows = [[InlineKeyboardButton(f"📤 {(getattr(ch, 'title', None) or str(getattr(ch, 'channel_chat_id', '?')))[:24]}", callback_data=f"src59:post:{ch.id}:{token}")] for ch in channels[:30]]
        rows.append([InlineKeyboardButton("✖ Close", callback_data=f"src59:close:{token}")])
        with contextlib.suppress(Exception):
            await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
        raise ApplicationHandlerStop
    if action == "post":
        try:
            cid = int(parts[2])
            ch = channel_get_by_id_for_user(uid, cid)
        except Exception:
            ch = None
        if not ch:
            with contextlib.suppress(Exception):
                await q.answer("Channel not found", show_alert=True)
            raise ApplicationHandlerStop
        with contextlib.suppress(Exception):
            await q.answer(f"Posting {len(items)}…")
            await q.edit_message_text(ui_box_html("Posting Source MCQ", f"Posting <code>{len(items)}</code> original checked MCQ(s)…", emoji="📌"), parse_mode=ParseMode.HTML)
        posted, failed = await _post_items_59(context, uid, chat_id, ch, items)
        with contextlib.suppress(Exception):
            await context.bot.send_message(chat_id=chat_id, text=ui_box_html("Source Posted", f"Posted: <code>{posted}</code>\nFailed: <code>{failed}</code>", emoji="✅"), parse_mode=ParseMode.HTML)
        raise ApplicationHandlerStop


_prev_send_pb_action_card_59 = _send_pb_action_card if "_send_pb_action_card" in globals() else None


async def _send_pb_action_card(context, chat_id: int, uid: int, added: int):  # noqa: F811
    # Multiple older patches call this after the same OCR/generation event. Debounce
    # so the chat receives one action card, not 3–5 duplicates.
    try:
        bd = context.application.bot_data
        seen = bd.setdefault("_pb_card_debounce_59", {})
        total = int(buffer_count(uid)) if "buffer_count" in globals() else 0
        key = f"{uid}:{chat_id}:{int(added)}:{total}"
        now = time.time()
        for k, ts in list(seen.items()):
            if now - float(ts or 0) > 8:
                seen.pop(k, None)
        if key in seen:
            return
        seen[key] = now
    except Exception:
        pass
    if _prev_send_pb_action_card_59:
        return await _prev_send_pb_action_card_59(context, chat_id, uid, added)


async def _run_staff_ocr_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE, source_msg, local_path: str, *, source_label: str = "image") -> Dict[str, Any]:  # noqa: F811
    uid = int(update.effective_user.id if update and update.effective_user else 0)
    proc = None
    try:
        proc = await _processing_start(source_msg, "OCR Checking", f"Reading {source_label}…")
        ocr = await _run_blocking(_role_of(uid), _mistral_ocr_process_path, local_path, timeout=220)
        pages = list(ocr.get("pages") or [])
        raw_markdown = str(ocr.get("raw_markdown") or "").strip()
        if not raw_markdown and not pages:
            raise RuntimeError("OCR could not read usable text.")
        await _processing_update(proc, "OCR Checking", "Extracting MCQs and checking answers…")
        clean_text, raw_items = await _run_blocking(_role_of(uid), _ocr_pages_to_clean_text_and_items, pages, uid, timeout=220)
        source_items = await _run_blocking(_role_of(uid), _clean_source_items_59, list(raw_items or []), timeout=90)
        ctx_payload = {
            "raw_markdown": raw_markdown,
            "clean_text": clean_text,
            "items": source_items,
            "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
            "page_count": len(pages) or 1,
            "source_label": source_label,
        }
        with contextlib.suppress(Exception):
            _remember_ocr_context(context, source_msg.message_id, ctx_payload)
        await _processing_delete(proc)
        proc = None
        counts = _estimate_counts_fast_59(len(source_items), clean_text)
        token = uuid.uuid4().hex[:10]
        seen_fp = set()
        for it in source_items:
            with contextlib.suppress(Exception):
                seen_fp.add(_fp_question(it))
        _genq_store(context)[token] = {
            "uid": uid, "chat_id": int(source_msg.chat_id), "page": 1,
            "text": str(clean_text or raw_markdown or ""), "counts": counts,
            "source_items": source_items, "seen_fp": seen_fp, "more_added": 0,
            "ts": time.time(),
        }
        body = (
            f"📄 OCR checked MCQ: <code>{len(source_items)}</code>\n"
            f"• Easy: <code>{counts['easy']}</code>  Medium: <code>{counts['medium']}</code>  Hard: <code>{counts['hard']}</code>\n\n"
            "✅ Source প্রশ্নগুলো answer-check করা হয়েছে. Generate করলে new unique MCQ buffer-এ যাবে."
        )
        await context.bot.send_message(
            chat_id=source_msg.chat_id,
            text=ui_box_html("Quiz Ready", body, emoji="🧠"),
            parse_mode=ParseMode.HTML,
            reply_markup=_genq_kb_59(token, counts),
            disable_web_page_preview=True,
        )
        return ctx_payload
    except Exception as e:
        await _processing_delete(proc)
        db_log("ERROR", "ocr_pipeline_59_failed", {"user_id": uid, "error": str(e)})
        with contextlib.suppress(Exception):
            await source_msg.reply_text(ui_box_html("OCR Failed", h(str(e)[:220]), emoji="⚠️"), parse_mode=ParseMode.HTML)
        return {"raw_markdown": "", "clean_text": "", "items": [], "source_label": source_label}


def _g59_mode_kb(tok: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🩺 Medical", callback_data=f"g59:mode:med:{tok}"), InlineKeyboardButton("🛠 Engineering", callback_data=f"g59:mode:eng:{tok}")],
        [InlineKeyboardButton("🎓 University", callback_data=f"g59:mode:ver:{tok}"), InlineKeyboardButton("📘 Standard", callback_data=f"g59:mode:std:{tok}")],
        [InlineKeyboardButton("✖ Cancel", callback_data=f"g59:x:x:{tok}")],
    ])


def _g59_count_kb(tok: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5", callback_data=f"g59:cnt:5:{tok}"), InlineKeyboardButton("10", callback_data=f"g59:cnt:10:{tok}"), InlineKeyboardButton("20", callback_data=f"g59:cnt:20:{tok}")],
        [InlineKeyboardButton("50", callback_data=f"g59:cnt:50:{tok}"), InlineKeyboardButton("100", callback_data=f"g59:cnt:100:{tok}"), InlineKeyboardButton("500", callback_data=f"g59:cnt:500:{tok}")],
        [InlineKeyboardButton("✖ Cancel", callback_data=f"g59:x:x:{tok}")],
    ])


async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
    ensure_user(update)
    if not update.message or not update.effective_user:
        raise ApplicationHandlerStop
    uid = int(update.effective_user.id)
    if is_banned(uid):
        raise ApplicationHandlerStop
    is_staff = False
    with contextlib.suppress(Exception):
        is_staff = bool(is_owner(uid) or is_admin(uid))
    if not is_staff:
        # Users keep the existing limited flow.
        if "_prev_cmd_gen_56" in globals():
            await _prev_cmd_gen_56(update, context)
        raise ApplicationHandlerStop

    reply_msg = update.message.reply_to_message
    if not reply_msg:
        await safe_reply(update, usage_box("gen", "[med|eng|engg|ver|std] [count]", "Reply to an OCR image/PDF/result, then run .gen or .gen med 20."))
        raise ApplicationHandlerStop
    mode, count, cleaned = _mode_count_59(update.message.text or "", list(context.args or []))
    ocr_ctx = await _resolve_ocr_ctx_59(update, context, reply_msg, uid)
    if not ocr_ctx:
        await warn(update, "No OCR Context", "Reply to an OCR-scanned image/PDF/result first.")
        raise ApplicationHandlerStop

    if count is None:
        tok = uuid.uuid4().hex[:10]
        _g59_store(context)[tok] = {"uid": uid, "chat_id": update.message.chat_id, "mode": mode or "", "ocr_ctx": ocr_ctx, "ts": time.time()}
        if not mode:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=ui_box_html("Generation Mode", "কোন standard এ new unique MCQ বানাবে?", emoji="🧠"),
                parse_mode=ParseMode.HTML,
                reply_markup=_g59_mode_kb(tok),
            )
        else:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=ui_box_html("How many MCQs?", f"Mode: <b>{h(mode.upper())}</b>", emoji="🔢"),
                parse_mode=ParseMode.HTML,
                reply_markup=_g59_count_kb(tok),
            )
        raise ApplicationHandlerStop

    status = None
    with contextlib.suppress(Exception):
        status = await update.message.reply_text(ui_box_html("Generating", f"Mode: <b>{h((mode or 'std').upper())}</b>\nCount: <code>{count}</code>", emoji="⏳"), parse_mode=ParseMode.HTML)
    added, dup = await _generate_to_buffer_59(update, context, ocr_ctx, uid, count, mode or "std")
    with contextlib.suppress(Exception):
        if status:
            await status.edit_text(ui_box_html("Generated → Buffer", f"Added: <code>{added}</code>\nDuplicates skipped: <code>{dup}</code>\nBuffered total: <code>{buffer_count(uid)}</code>", emoji="✅"), parse_mode=ParseMode.HTML)
    if added > 0:
        await _send_pb_action_card(context, update.message.chat_id, uid, added)
    raise ApplicationHandlerStop


async def cb_g59(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) != 4 or parts[0] != "g59":
        return
    action, val, tok = parts[1], parts[2], parts[3]
    entry = _g59_store(context).get(tok)
    if not entry:
        with contextlib.suppress(Exception):
            await q.answer("Expired", show_alert=False)
        raise ApplicationHandlerStop
    uid = int(entry.get("uid") or 0)
    if q.from_user and int(q.from_user.id) != uid:
        with contextlib.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        raise ApplicationHandlerStop
    if action == "x":
        _g59_store(context).pop(tok, None)
        with contextlib.suppress(Exception):
            await q.edit_message_text(ui_box_html("Cancelled", "Generation cancelled.", emoji="✖"), parse_mode=ParseMode.HTML)
        raise ApplicationHandlerStop
    if action == "mode":
        entry["mode"] = val
        _g59_store(context)[tok] = entry
        with contextlib.suppress(Exception):
            await q.edit_message_text(ui_box_html("How many MCQs?", f"Mode: <b>{h(val.upper())}</b>", emoji="🔢"), parse_mode=ParseMode.HTML, reply_markup=_g59_count_kb(tok))
        raise ApplicationHandlerStop
    if action == "cnt":
        count = max(1, min(500, int(val)))
        mode = str(entry.get("mode") or "std")
        ocr_ctx = dict(entry.get("ocr_ctx") or {})
        chat_id = int(entry.get("chat_id") or q.message.chat_id)
        with contextlib.suppress(Exception):
            await q.answer(f"Generating {count}…")
            await q.edit_message_text(ui_box_html("Generating", f"Mode: <b>{h(mode.upper())}</b>\nCount: <code>{count}</code>", emoji="⏳"), parse_mode=ParseMode.HTML)
        added, dup = await _generate_to_buffer_59(update, context, ocr_ctx, uid, count, mode)
        _g59_store(context).pop(tok, None)
        with contextlib.suppress(Exception):
            await q.edit_message_text(ui_box_html("Generated → Buffer", f"Added: <code>{added}</code>\nDuplicates skipped: <code>{dup}</code>\nBuffered total: <code>{buffer_count(uid)}</code>", emoji="✅"), parse_mode=ParseMode.HTML)
        if added > 0:
            await _send_pb_action_card(context, chat_id, uid, added)
        raise ApplicationHandlerStop


async def msg_g59_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    txt = str(update.message.text or "").strip()
    if not re.fullmatch(r"\d{1,4}", txt):
        return
    uid = int(update.effective_user.id)
    state = _g59_store(context)
    tok = None
    newest = -1.0
    for k, v in list(state.items()):
        if int(v.get("uid") or 0) == uid and float(v.get("ts") or 0) > newest:
            tok, newest = k, float(v.get("ts") or 0)
    if not tok:
        return
    entry = state.get(tok) or {}
    count = max(1, min(500, int(txt)))
    mode = str(entry.get("mode") or "std")
    ocr_ctx = dict(entry.get("ocr_ctx") or {})
    chat_id = int(entry.get("chat_id") or update.message.chat_id)
    status = None
    with contextlib.suppress(Exception):
        status = await update.message.reply_text(ui_box_html("Generating", f"Mode: <b>{h(mode.upper())}</b>\nCount: <code>{count}</code>", emoji="⏳"), parse_mode=ParseMode.HTML)
    added, dup = await _generate_to_buffer_59(update, context, ocr_ctx, uid, count, mode)
    state.pop(tok, None)
    with contextlib.suppress(Exception):
        if status:
            await status.edit_text(ui_box_html("Generated → Buffer", f"Added: <code>{added}</code>\nDuplicates skipped: <code>{dup}</code>\nBuffered total: <code>{buffer_count(uid)}</code>", emoji="✅"), parse_mode=ParseMode.HTML)
    if added > 0:
        await _send_pb_action_card(context, chat_id, uid, added)
    raise ApplicationHandlerStop


if "build_app" in globals():
    _prev_build_app_59 = build_app

    def build_app() -> Application:  # noqa: F811
        app = _prev_build_app_59()
        with contextlib.suppress(Exception):
            if "_register_dual_command" in globals():
                _register_dual_command(app, "gen", cmd_gen, group=-500)
            else:
                app.add_handler(CommandHandler("gen", cmd_gen), group=-500)
                app.add_handler(_build_dot_command_handler("gen", cmd_gen), group=-500)
        with contextlib.suppress(Exception):
            app.add_handler(CallbackQueryHandler(cb_genq_59, pattern=r"^genq:(go|re|no|ge|gm|gh|mo|src):[0-9a-f]+$"), group=-500)
        with contextlib.suppress(Exception):
            app.add_handler(CallbackQueryHandler(cb_src59, pattern=r"^src59:"), group=-500)
        with contextlib.suppress(Exception):
            app.add_handler(CallbackQueryHandler(cb_g59, pattern=r"^g59:"), group=-500)
        with contextlib.suppress(Exception):
            app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, msg_g59_count), group=-500)
        return app

# ===== END FINAL SINGLE FLOW SECTION 59 =====





