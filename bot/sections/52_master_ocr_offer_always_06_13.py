# ──────────────────────────────────────────────────────────────────────────────
# Section: 52_master_ocr_offer_always_06_13
# Ensures generation-offer buttons ALWAYS appear after OCR (image or PDF page)
# and aggressively trims explanations for Telegram poll limits across all
# providers. DO NOT import directly — exec'd by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────


# ---------- 1) Hard cap explanations everywhere ----------

def _hard_trim_expl(text: str) -> str:
    try:
        t = _sanitize_quiz_explanation_text(str(text or "")).strip()
    except Exception:
        t = str(text or "").strip()
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 180:
        t = t[:177].rstrip() + "..."
    return t


# Wrap the master extractor + content generator to enforce trimming
_prev_extract_mcq_items_master_52 = _extract_mcq_items_master
_prev_generate_mcqs_from_content_52 = _generate_mcqs_from_content


def _extract_mcq_items_master(chunk_text: str) -> List[Dict[str, Any]]:
    items = _prev_extract_mcq_items_master_52(chunk_text) or []
    for it in items:
        it["explanation"] = _hard_trim_expl(it.get("explanation") or "")
    return items


def _generate_mcqs_from_content(content_text: str, *, easy: int, medium: int, hard: int) -> List[Dict[str, Any]]:
    items = _prev_generate_mcqs_from_content_52(content_text, easy=easy, medium=medium, hard=hard) or []
    for it in items:
        it["explanation"] = _hard_trim_expl(it.get("explanation") or "")
    return items


# ---------- 2) Always-offer post-OCR (one offer per page, with buttons) ----------

_prev_run_staff_ocr_pipeline_offer = _run_staff_ocr_pipeline


async def _run_staff_ocr_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE, source_msg, local_path: str, *, source_label: str = "image") -> Dict[str, Any]:
    ctx_payload = await _prev_run_staff_ocr_pipeline_offer(update, context, source_msg, local_path, source_label=source_label)
    try:
        ct = str((ctx_payload or {}).get("clean_text") or "")
        if not ct.strip():
            return ctx_payload
        # Re-parse [Page N] markers from clean_text. If none, treat full text as page 1.
        page_texts: List[Tuple[int, str]] = []
        cur_idx = None
        cur_buf: List[str] = []
        for line in ct.splitlines():
            m = re.match(r"^\[Page\s+(\d+)\]\s*$", line.strip())
            if m:
                if cur_idx is not None and cur_buf:
                    page_texts.append((cur_idx, "\n".join(cur_buf).strip()))
                cur_idx = int(m.group(1))
                cur_buf = []
            else:
                if cur_idx is not None:
                    cur_buf.append(line)
        if cur_idx is not None and cur_buf:
            page_texts.append((cur_idx, "\n".join(cur_buf).strip()))
        if not page_texts:
            page_texts = [(1, ct.strip())]

        uid = update.effective_user.id if update and update.effective_user else 0
        chat_id = source_msg.chat_id
        # Cap to first 8 pages to avoid Render free-tier overload
        for (idx, txt) in page_texts[:8]:
            if not txt or len(txt) < 60:
                continue
            try:
                await _send_content_page_offer(context, chat_id, uid, idx, txt)
            except Exception as e:
                db_log("WARN", "offer_always_failed", {"page": idx, "error": str(e)})
    except Exception as e:
        db_log("WARN", "offer_always_postprocess_failed", {"error": str(e)})
    return ctx_payload


# ---------- 3) Improve the offer card: show all 3 difficulty buttons + custom ----------

_prev_genq_kb_52 = _genq_kb


def _genq_kb(token: str, counts: Dict[str, int]) -> InlineKeyboardMarkup:
    e = int(counts.get("easy", 0))
    m = int(counts.get("medium", 0))
    hd = int(counts.get("hard", 0))
    total = e + m + hd
    rows: List[List[InlineKeyboardButton]] = []
    if total > 0:
        rows.append([InlineKeyboardButton(f"✅ Generate ALL ({total})", callback_data=f"genq:go:{token}")])
    # Difficulty-specific quick buttons
    diff_row: List[InlineKeyboardButton] = []
    if e > 0:
        diff_row.append(InlineKeyboardButton(f"🟢 Easy ({e})", callback_data=f"genq:ge:{token}"))
    if m > 0:
        diff_row.append(InlineKeyboardButton(f"🟡 Medium ({m})", callback_data=f"genq:gm:{token}"))
    if hd > 0:
        diff_row.append(InlineKeyboardButton(f"🔴 Hard ({hd})", callback_data=f"genq:gh:{token}"))
    if diff_row:
        rows.append(diff_row)
    rows.append([
        InlineKeyboardButton("🔄 Re-estimate", callback_data=f"genq:re:{token}"),
        InlineKeyboardButton("🚫 Skip", callback_data=f"genq:no:{token}"),
    ])
    return InlineKeyboardMarkup(rows)


# Extend callback handler to support ge/gm/gh
_prev_cb_genq_52 = cb_genq


async def cb_genq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) != 3 or parts[0] != "genq":
        return
    action = parts[1]
    if action not in ("ge", "gm", "gh"):
        return await _prev_cb_genq_52(update, context)
    token = parts[2]
    store = _genq_store(context)
    entry = store.get(token)
    if not entry:
        with contextlib.suppress(Exception):
            await q.answer("Expired", show_alert=False)
        return
    uid = int(entry.get("uid") or 0)
    caller = q.from_user.id if q.from_user else 0
    if caller != uid:
        with contextlib.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        return
    counts = entry.get("counts") or {}
    text = str(entry.get("text") or "")
    page_idx = int(entry.get("page") or 0)
    e = int(counts.get("easy", 0)) if action == "ge" else 0
    m = int(counts.get("medium", 0)) if action == "gm" else 0
    hd = int(counts.get("hard", 0)) if action == "gh" else 0
    label = {"ge": "Easy", "gm": "Medium", "gh": "Hard"}[action]
    with contextlib.suppress(Exception):
        await q.answer(f"Generating {label}…")
    with contextlib.suppress(Exception):
        await q.edit_message_text(
            ui_box_html(f"Generating {label} (Page {page_idx})", "Please wait…", emoji="⏳"),
            parse_mode=ParseMode.HTML,
        )
    try:
        items = await _run_blocking(
            _role_of(uid),
            _generate_mcqs_from_content,
            text,
            easy=e, medium=m, hard=hd,
            timeout=120,
        )
    except Exception as ex:
        db_log("ERROR", "genq_diff_generate_failed", {"user_id": uid, "error": str(ex)})
        items = []
    added = 0
    for p in items:
        if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
            break
        pp = dict(p)
        if not explain_mode_on(uid):
            pp["explanation"] = ""
        buffer_add(uid, pp)
        added += 1
    store.pop(token, None)
    with contextlib.suppress(Exception):
        await q.edit_message_text(
            ui_box_html(
                f"Page {page_idx} → Buffer ({label})",
                f"Added <code>{added}</code> MCQ(s).\nBuffered: <code>{buffer_count(uid)}</code>\n\nUse /done or /post.",
                emoji="✅",
            ),
            parse_mode=ParseMode.HTML,
        )


# Re-register callback with the broadened pattern
_prev_build_app_offer_52 = build_app


def build_app() -> Application:
    app = _prev_build_app_offer_52()
    with contextlib.suppress(Exception):
        app.add_handler(CallbackQueryHandler(cb_genq, pattern=r"^genq:(go|re|no|ge|gm|gh):[0-9a-f]+$"))
    return app

# ===== END MASTER OCR ALWAYS-OFFER =====