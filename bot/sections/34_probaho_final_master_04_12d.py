# ──────────────────────────────────────────────────────────────────────────────
# Section: 34_probaho_final_master_04_12d
# Original lines: 18160..18992
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════
# ===== PROBAHO FINAL MASTER PATCH (2026-04-12-D) =====
#
# সমস্যা সমাধান:
# 1. User image reply: নির্দিষ্ট Q নম্বর বা যেকোনো প্রশ্নের সঠিক উত্তর
# 2. যেকোনো free-form প্রশ্ন (summarize, explain, analyze) থেকে উত্তর
# 3. প্রতি response এ remaining OCR limit দেখাবে
# 4. Limit শেষে proper warning (HTML correct)
# 5. Midnight BD time reset + owner কে notification
# 6. AI spinner: professional English ("AI is thinking...")
# 7. Solver callback: একবারই চলবে, double process নেই
# 8. Group: quote ছাড়া সাধারণ message
# 9. /ownerstats: stats + "Download Log" button (আলাদা)
# ═══════════════════════════════════════════════════════════════════════════

import asyncio as _asyncio_master

# ── DEDUP SET: prevent double solver callback ──
_MASTER_SOLVING_SET: set = set()
_MASTER_ANSWERED_CBS: set = set()

# ─────────────────────────────────────────────
# 1. SMART OCR QUESTION PICKER
#    - নির্দিষ্ট প্রশ্ন নম্বর ধরতে পারে (Q8, ৮ নম্বর, 8)
#    - keyword দিয়ে প্রশ্ন খুঁজে পায়
#    - না পেলে full OCR text দেয় (summarize, explain etc.)
# ─────────────────────────────────────────────

_BD_DIGITS_TR = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

def _extract_question_number(text: str) -> Optional[str]:
    """Extract a question number from user text. Returns string digit or None."""
    t = str(text or "").translate(_BD_DIGITS_TR)
    # Patterns like: Q8, q 8, ৮ নম্বর, 8 number, question 8, 8th, No.8
    patterns = [
        r"\b[Qq]\.?\s*(\d{1,3})\b",
        r"\b(\d{1,3})\s*(?:নম্বর|number|no\.?|th|st|nd|rd)\b",
        r"(?:question|প্রশ্ন)\s*\.?\s*(\d{1,3})\b",
        r"\b(\d{1,3})\s*(?:নং|নম্বর)\b",
        r"\bNo\s*[\.\:\-]?\s*(\d{1,3})\b",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            return m.group(1)
    # standalone digit if short message
    stripped = t.strip()
    if re.match(r"^\d{1,3}$", stripped):
        return stripped
    return None


def _is_free_form_question(text: str) -> bool:
    """Returns True if the user is asking a free-form question (not MCQ targeting)."""
    t = str(text or "").lower()
    free_form_keywords = [
        "summarize", "summary", "সারাংশ", "সংক্ষেপ",
        "explain", "ব্যাখ্যা", "বুঝিয়ে দাও", "বুঝাও",
        "analyze", "analysis", "বিশ্লেষণ",
        "what is", "কী", "কি আছে",
        "describe", "বর্ণনা",
        "list", "তালিকা",
        "topic", "টপিক",
        "type", "ধরন",
        "কোন কোন", "কী কী",
        "overview",
    ]
    return any(kw in t for kw in free_form_keywords)


def _smart_pick_mcq_item(items: List[Dict[str, Any]], user_text: str) -> Optional[Dict[str, Any]]:
    """
    MASTER FIX: Smart MCQ picker.
    - Q number দিলে সেই নম্বরের প্রশ্ন দেয়
    - keyword দিলে best match দেয়
    - কিছু না বললে প্রথমটা দেয়
    Returns None if free-form question (no MCQ targeting)
    """
    pool = [dict(x) for x in (items or []) if str((x or {}).get("questions") or "").strip()]
    if not pool:
        return None

    user_t = str(user_text or "").strip()

    # Free-form: user wants page-level analysis
    if _is_free_form_question(user_t) and not _extract_question_number(user_t):
        return None  # signal: use full OCR text

    # Try question number extraction
    qno = _extract_question_number(user_t)
    if qno:
        # Match by assigned question number
        exact = [it for it in pool if _item_question_no(it) == qno]
        if exact:
            return exact[0]
        # Match by question text starting with that number
        for it in pool:
            q_text = str(it.get("questions") or "")
            if re.match(rf"^\s*{re.escape(qno)}\s*[\.।\)]", q_text):
                return it
        # Positional fallback
        try:
            idx = int(qno) - 1
            if 0 <= idx < len(pool):
                return pool[idx]
        except Exception:
            pass

    # Text similarity matching
    if user_t:
        best_item = None
        best_score = 0.0
        for it in pool:
            score = _question_text_match_score(user_t, it)
            if score > best_score:
                best_score = score
                best_item = it
        if best_item and best_score >= 0.3:
            return best_item

    return pool[0]  # default: first item


def _build_master_ocr_prompt(ocr_ctx: Dict[str, Any], user_question: str, previous_answer: str = "") -> str:
    """
    MASTER FIX: Build smart OCR prompt.
    - Q নম্বর দিলে → সেই MCQ focus করে
    - Free-form → পুরো OCR text দিয়ে সঠিক উত্তর
    - যেকোনো প্রশ্নই হোক → সঠিক উত্তর দেবে
    """
    user_q = str(user_question or "").strip()
    prev = str(previous_answer or "").strip()
    items = list((ocr_ctx or {}).get("items") or [])
    full_text = str((ocr_ctx or {}).get("clean_text") or (ocr_ctx or {}).get("raw_markdown") or "").strip()

    picked = _smart_pick_mcq_item(items, user_q)

    system_preamble = (
        "You are an expert academic AI assistant for a Bangladeshi student preparation platform.\n"
        "Answer ONLY from the provided OCR content below.\n"
        "Language: If the content is in Bangla, answer in Bangla. Mix English only for technical terms.\n"
        "Format: Use clean plain text. No LaTeX math notation. No markdown headers.\n"
        "Be thorough, accurate, and student-friendly.\n\n"
    )

    if picked:
        # MCQ-focused answer
        options = [str(picked.get(f"option{i}") or "").strip() for i in range(1, 6)
                   if str(picked.get(f"option{i}") or "").strip()]
        qblock = str(picked.get("questions") or "").strip()
        opt_block = "\n".join([f"{chr(64+i+1)}. {options[i]}" for i in range(len(options))])
        visible_ans = int(picked.get("answer", 0) or 0)
        visible_text = options[visible_ans - 1] if 1 <= visible_ans <= len(options) else ""
        qno = _item_question_no(picked) or ""
        qno_label = f"Question {qno}" if qno else "Question"

        prompt = system_preamble
        prompt += f"User's request: {user_q}\n\n"
        if prev:
            prompt += f"Previous answer (context):\n{prev[:2000]}\n\n"
        prompt += f"--- {qno_label} from the image ---\n{qblock}\n\nOptions:\n{opt_block}\n"
        if visible_text:
            prompt += f"\nCorrect answer marked on the page: {chr(64+visible_ans)}) {visible_text}\n"
        prompt += (
            "\nProvide:\n"
            "1) The correct answer with the option letter\n"
            "2) A clear step-by-step explanation\n"
            "3) Why the other options are wrong (briefly)\n"
        )
        return prompt

    else:
        # Free-form / page-level question
        prompt = system_preamble
        prompt += f"User's request about this page:\n{user_q}\n\n"
        if prev:
            prompt += f"Previous answer:\n{prev[:2000]}\n\n"
        prompt += f"--- Full OCR content of the page ---\n{full_text[:12000]}\n"
        prompt += "\nAnswer the user's request comprehensively based on the above content."
        return prompt


# ─────────────────────────────────────────────
# 2. MASTER handle_user_reply_ocr_question
#    (replaces all previous versions)
# ─────────────────────────────────────────────

async def handle_user_reply_ocr_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    MASTER FIX: User image reply handler.
    - যেকোনো প্রশ্নের সঠিক উত্তর দেয়
    - নির্দিষ্ট Q নম্বর থেকে সঠিক উত্তর
    - summarize, explain, analyze সব করতে পারে
    - প্রতি response এ remaining limit দেখায়
    """
    ensure_user(update)
    if not update.message or not update.effective_user or not is_private_chat(update):
        return
    uid = int(update.effective_user.id)
    if is_banned(uid) or get_role(uid) != ROLE_USER:
        return

    reply_msg = update.message.reply_to_message
    if not reply_msg:
        return

    user_question = str(update.message.text or "").strip()
    if not user_question or user_question.startswith("/") or user_question.startswith("."):
        return

    reply_has_ctx = _has_ocr_context(context, reply_msg)
    reply_is_media = _is_supported_ocr_media_message(reply_msg)

    # Also check: is user replying to a bot AI response? (conversation continuation)
    is_bot_msg = False
    try:
        bot_id = context.bot.id
        from_id = getattr(getattr(reply_msg, "from_user", None), "id", None)
        if bot_id and from_id and int(from_id) == int(bot_id):
            is_bot_msg = True
    except Exception:
        pass

    # Conversation continuation: user replied to bot answer
    if is_bot_msg and not reply_is_media and not reply_has_ctx:
        if solver_mode_on(uid):
            prev_text = str(reply_msg.text or reply_msg.caption or "").strip()
            if prev_text:
                cont_prompt = (
                    f"Previous AI answer (context):\n{prev_text[:2000]}\n\n"
                    f"User's follow-up question:\n{user_question}"
                )
                token = _make_token()
                _pending_store(context)[token] = {
                    "uid": uid, "kind": "text", "scope": "private_academic",
                    "chat_id": update.message.chat_id,
                    "payload": {"text": cont_prompt, "source_user_text": user_question},
                }
                try:
                    await update.message.reply_text(
                        ui_box_text("Continue Discussion", "Choose AI to continue:", emoji="💬"),
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                        reply_markup=_solver_picker_kb(token),
                    )
                except Exception:
                    pass
                raise ApplicationHandlerStop
        return

    if not reply_is_media and not reply_has_ctx:
        return

    # OCR availability check
    if not mistral_runtime_enabled():
        await safe_reply(update, _ocr_temporarily_disabled_html())
        raise ApplicationHandlerStop
    if not get_mistral_api_key():
        await warn(update, "OCR Unavailable", "Mistral OCR key not configured. Please contact the owner.")
        raise ApplicationHandlerStop

    # Quota check (only for new OCR, not cached)
    needs_quota = bool(reply_is_media and not reply_has_ctx)
    if needs_quota:
        remaining = _remaining_user_ocr_quota(uid)
        daily_limit = get_mistral_user_daily_limit()
        if remaining <= 0:
            await warn_html(
                update, "Daily OCR Limit Reached",
                f"আজকের জন্য আপনার OCR quota শেষ হয়েছে।\n"
                f"প্রতিদিন রাত ১২টায় (BD time) limit রিফ্রেশ হয়।\n"
                f"Daily limit: <code>{h(str(daily_limit))}</code> scans"
            )
            raise ApplicationHandlerStop

    proc = await _processing_start(update.message, "Scanning Image", "Extracting content via Mistral OCR...")
    local_path = None
    try:
        # Get or build OCR context
        ocr_ctx = _get_ocr_context(context, reply_msg.message_id) if reply_has_ctx else None
        if not ocr_ctx and reply_is_media:
            if reply_msg.document:
                name = str(reply_msg.document.file_name or "").lower()
                if name.endswith(".pdf") or str(getattr(reply_msg.document, "mime_type", "") or "").lower() == "application/pdf":
                    suffix = ".pdf"
                else:
                    ext = os.path.splitext(name)[1].strip() or ".jpg"
                    suffix = ext if len(ext) <= 6 else ".jpg"
                tg_file = await reply_msg.document.get_file()
            else:
                tg_file = await reply_msg.photo[-1].get_file()
                suffix = ".jpg"

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                local_path = f.name
            await tg_file.download_to_drive(local_path)
            await _processing_update(proc, "Scanning Image", "Running OCR — detecting questions and answers...")
            bundle = await _run_blocking(_role_of(uid), _extract_ocr_bundle_from_path, local_path, uid, timeout=300)
            ocr = bundle["ocr"]
            ocr_ctx = {
                "raw_markdown": str(ocr.get("raw_markdown") or ""),
                "clean_text": str(bundle.get("clean_text") or ""),
                "items": list(bundle.get("items") or []),
                "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
                "page_count": len(ocr.get("pages") or []),
            }
            _remember_ocr_context(context, reply_msg.message_id, ocr_ctx)
            _inc_user_ocr_usage(uid, 1)

        if not ocr_ctx:
            await _processing_delete(proc)
            raise RuntimeError("Could not extract OCR context from the replied image.")

        # Build smart prompt
        previous_answer = _reply_message_plain_text(reply_msg) if _is_user_followup_to_ocr_answer(update, context) else ""
        prompt_text = _build_master_ocr_prompt(ocr_ctx, user_question, previous_answer=previous_answer)

        # Remaining quota for display
        remaining_after = _remaining_user_ocr_quota(uid)
        daily_limit = get_mistral_user_daily_limit()

        token = _make_token()
        _pending_store(context)[token] = {
            "uid": uid, "kind": "text", "scope": "private_academic",
            "chat_id": update.message.chat_id,
            "payload": {
                "text": prompt_text,
                "source_user_text": user_question,
                "ocr_remaining": remaining_after,
                "ocr_daily_limit": daily_limit,
            },
            "ocr_ctx": dict(ocr_ctx),
            "is_user_ocr": True,
        }

        await _processing_delete(proc)
        proc = None

        # Show remaining quota info + model picker
        quota_line = f"📊 OCR remaining today: <code>{remaining_after}/{daily_limit}</code>"
        chooser = await update.message.reply_text(
            ui_box_html(
                "Choose AI Model",
                f"Image scanned successfully. Choose an AI to answer:\n\n{quota_line}",
                emoji="🤖"
            ),
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
        db_log("ERROR", "master_user_reply_ocr_failed", {"user_id": uid, "error": str(e)})
        await err(update, "OCR Failed", f"Could not process the image: {str(e)[:180]}")
        raise ApplicationHandlerStop
    finally:
        if local_path:
            with contextlib.suppress(Exception):
                os.remove(local_path)


# ─────────────────────────────────────────────
# 3. MASTER SOLVER CALLBACK
#    - একবারই চলে (dedup guard)
#    - Professional English spinner
#    - Streaming: ⏳ edit → final answer
#    - OCR response এ remaining limit দেখায়
# ─────────────────────────────────────────────

_MODEL_NAMES = {"G": "✨ Gemini", "P": "⚛ Perplexity", "D": "🐳 DeepSeek"}

async def on_solver_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """MASTER FIXED: Single-fire, streaming, professional UX."""
    if not update.callback_query:
        return
    q = update.callback_query

    # ── Dedup: prevent double fire ──
    cb_id = str(q.id or "")
    if cb_id and cb_id in _MASTER_ANSWERED_CBS:
        with contextlib.suppress(Exception):
            await q.answer()
        return
    if cb_id:
        _MASTER_ANSWERED_CBS.add(cb_id)
        if len(_MASTER_ANSWERED_CBS) > 3000:
            items_list = list(_MASTER_ANSWERED_CBS)
            _MASTER_ANSWERED_CBS.clear()
            _MASTER_ANSWERED_CBS.update(items_list[-1500:])

    # Acknowledge immediately (no popup)
    with contextlib.suppress(Exception):
        await q.answer()

    data_str = (q.data or "").strip()
    m = re.match(r"^solve:([GPD]):([0-9a-f]{6,16})$", data_str)
    if not m:
        return

    model = m.group(1)
    token = m.group(2)
    model_name = _MODEL_NAMES.get(model, "AI")

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

    # Dedup by token+model (prevent rapid double-tap)
    lock_key = f"{uid}:{token}:{model}"
    if lock_key in _MASTER_SOLVING_SET:
        with contextlib.suppress(Exception):
            await q.answer("Already processing, please wait...", show_alert=False)
        return
    _MASTER_SOLVING_SET.add(lock_key)

    try:
        payload = req.get("payload") or {}
        problem_text = str(payload.get("text") or "").strip()
        kind = str(req.get("kind") or "text").lower()
        is_group = bool(q.message and q.message.chat and q.message.chat.type in ("group", "supergroup"))
        scope = str(req.get("scope") or ("group_general" if is_group else "private_academic"))

        # ── Professional streaming spinner ──
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                f"🔍 <b>{model_name}</b> is analyzing your question...",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        if q.message:
            with contextlib.suppress(Exception):
                await context.bot.send_chat_action(
                    chat_id=q.message.chat_id,
                    action=ChatAction.TYPING,
                )

        # ── Solve ──
        msg_html = ""
        kb = None

        if kind == "poll" and payload.get("question"):
            question = str(payload.get("question", "")).strip()
            options = payload.get("options", [])
            result, backend_used = await _run_blocking(
                _role_of(uid), _solve_mcq_with_preference, model, question, options
            )
            raw_expl = str(result.get("explanation", "") or "")
            clean_expl = clean_latex(raw_expl)
            raw_why_not = result.get("why_not", {}) or {}
            clean_why_not = {k: clean_latex(v) for k, v in raw_why_not.items()}
            msg_html = _format_user_poll_solution(
                question=question, options=options,
                model_ans=int(result.get("answer", 0) or 0),
                official_ans=int(payload.get("official_ans", 0) or 0),
                model_expl=f"[{model_name}]\n{clean_expl}".strip(),
                official_expl=str(payload.get("official_expl", "")).strip(),
                why_not=clean_why_not,
                conf=int(result.get("confidence", 0) or 0),
            )
            kb = _verify_kb(token, model, "poll")

        else:
            if _contains_adult_content(problem_text):
                answer = _adult_refusal_text(problem_text)
            else:
                answer, backend_used = await _run_blocking(
                    _role_of(uid), _solve_text_with_preference, model, problem_text, scope
                )
                if _contains_adult_content(answer) and not _is_academic_safe_override(problem_text):
                    answer = _adult_refusal_text(problem_text)
            preserve_code = (is_admin(uid) or is_owner(uid)) and (
                looks_like_programming_request(problem_text) or looks_like_programming_request(answer)
            )
            msg_html = _answer_to_tg_html(answer, model_name=model_name, preserve_code=preserve_code)

            # Add OCR remaining quota if this was an OCR request
            is_user_ocr = bool(req.get("is_user_ocr"))
            if is_user_ocr:
                remaining = _remaining_user_ocr_quota(uid)
                daily_limit = get_mistral_user_daily_limit()
                quota_footer = f"\n\n<i>📊 OCR scans remaining today: {remaining}/{daily_limit}</i>"
                if len(msg_html) + len(quota_footer) <= 4096:
                    msg_html += quota_footer

            kb = _verify_kb(token, model, "text")

        # ── Streaming: edit with final answer ──
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                (msg_html or "❌ No response received.")[:4096],
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

        # Post-solve: save thread, auto-delete in group
        if q.message:
            if kind == "poll":
                with contextlib.suppress(Exception):
                    _remember_quiz_context(context, q.message.message_id, payload)
            if is_group:
                asyncio.create_task(
                    _auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS)
                )

    except Exception as e:
        db_log("ERROR", "master_solver_failed", {"uid": uid, "model": model, "error": str(e)})
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                ui_box_html("AI Error", h(str(e)[:200]), emoji="❌"),
                parse_mode=ParseMode.HTML,
            )
        if q.message and is_group:
            with contextlib.suppress(Exception):
                asyncio.create_task(
                    _auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], 120)
                )
    finally:
        _MASTER_SOLVING_SET.discard(lock_key)


# ─────────────────────────────────────────────
# 4. GROUP: No-quote safe_reply
# ─────────────────────────────────────────────

_master_orig_safe_reply = safe_reply

async def safe_reply(update: Update, text: str) -> None:
    """MASTER FIX: Group এ quote ছাড়া সাধারণ message।"""
    if not update or not update.message:
        return
    chat_type = str(getattr(update.effective_chat, "type", "") or "")
    if chat_type in ("group", "supergroup"):
        chat_id = update.effective_chat.id
        try:
            bot = update.message.bot
        except Exception:
            bot = None
        if bot:
            for part in chunk_text(text, 4000):
                with contextlib.suppress(Exception):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=part,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
            return
    await _master_orig_safe_reply(update, text)


# ─────────────────────────────────────────────
# 5. OCR MIDNIGHT RESET (Bangladesh time, 12:00 AM)
#    + Owner notification
# ─────────────────────────────────────────────

_BD_TZ_MASTER = dt.timezone(dt.timedelta(hours=6))
_master_reset_started = False

async def _master_midnight_reset_loop(bot=None) -> None:
    """Reset OCR daily usage at midnight BD time. Notify owner."""
    global _master_reset_started
    while True:
        try:
            now_bd = dt.datetime.now(_BD_TZ_MASTER)
            next_midnight = (now_bd + dt.timedelta(days=1)).replace(hour=0, minute=0, second=10, microsecond=0)
            wait_secs = (next_midnight - now_bd).total_seconds()
            await asyncio.sleep(max(wait_secs, 60))

            # Delete old usage records (keep only today's)
            today = dt.datetime.now(_BD_TZ_MASTER).strftime("%Y-%m-%d")
            conn = db_connect()
            cur = conn.cursor()
            cur.execute("DELETE FROM user_ocr_daily_usage WHERE day_key < ?", (today,))
            deleted = cur.rowcount
            conn.commit()
            conn.close()

            logger.info("[OCR RESET] Daily reset done. Deleted %d old records. New day: %s", deleted, today)

            # Notify all owners
            if bot:
                for owner_id in OWNER_IDS:
                    with contextlib.suppress(Exception):
                        await bot.send_message(
                            chat_id=owner_id,
                            text=(
                                "🔄 <b>Daily OCR Limit Refreshed</b>\n\n"
                                f"Bangladesh time: <code>12:00 AM</code>\n"
                                f"Date: <code>{today}</code>\n"
                                f"Cleared records: <code>{deleted}</code>\n\n"
                                "All users can now use their full OCR quota again."
                            ),
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[OCR RESET] Error: %s", e)
            await asyncio.sleep(300)


# ─────────────────────────────────────────────
# 6. /ownerstats: Stats + Download Log button
# ─────────────────────────────────────────────

@require_owner
async def cmd_ownerstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """MASTER FIXED /ownerstats: accurate stats + log download button."""
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM users")
    total_users = int(cur.fetchone()["c"] or 0)

    cur.execute("SELECT COUNT(*) AS c FROM users WHERE role IN ('OWNER','ADMIN')")
    staff_count = int(cur.fetchone()["c"] or 0)

    since_24h = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).replace(microsecond=0).isoformat()
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE last_seen_at IS NOT NULL AND last_seen_at >= ?", (since_24h,))
    active_24h = int(cur.fetchone()["c"] or 0)

    since_1h = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).replace(microsecond=0).isoformat()
    cur.execute("SELECT COUNT(*) AS c FROM bot_logs WHERE level='ERROR' AND created_at >= ?", (since_1h,))
    err_1h = int(cur.fetchone()["c"] or 0)

    cur.execute("SELECT COUNT(*) AS c FROM bot_logs WHERE level='ERROR' AND created_at >= ?", (since_24h,))
    err_24h = int(cur.fetchone()["c"] or 0)

    cur.execute("SELECT created_at, event, meta_json FROM bot_logs WHERE level='ERROR' ORDER BY id DESC LIMIT 5")
    last_errors = cur.fetchall()

    # Mistral keys
    mistral_rows = _mistral_key_rows(include_disabled=False)
    active_keys = len(mistral_rows)

    # Today's OCR usage
    today_key = dt.datetime.now(_BD_TZ_MASTER).strftime("%Y-%m-%d")
    cur.execute("SELECT SUM(used_count) AS total FROM user_ocr_daily_usage WHERE day_key=?", (today_key,))
    ocr_row = cur.fetchone()
    ocr_today = int(ocr_row["total"] or 0) if ocr_row and ocr_row["total"] else 0

    # Active users with solver mode on
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE solver_mode_on=1")
    solver_on_count = int(cur.fetchone()["c"] or 0)

    conn.close()

    db_mb = 0.0
    with contextlib.suppress(Exception):
        if os.path.exists(DB_PATH):
            db_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    rss_mb = process_rss_mb()
    github_ok = False
    with contextlib.suppress(Exception):
        github_ok = _github_backup_enabled()

    lines = [
        "📑 <b>System Dashboard</b>",
        f"⏱ Uptime: <code>{h(fmt_uptime())}</code>",
        "",
        "👥 <b>Users</b>",
        f"  Total: <code>{total_users}</code>  |  Staff: <code>{staff_count}</code>",
        f"  Active (24h): <code>{active_24h}</code>  |  AI Mode ON: <code>{solver_on_count}</code>",
        "",
        "💻 <b>System</b>",
        f"  DB: <code>{h(fmt_mb(db_mb))}</code>  |  RAM: <code>{h(fmt_mb(rss_mb))}</code>",
        f"  GitHub: {'✅ Enabled' if github_ok else '❌ Disabled'}",
        "",
        "🔑 <b>Mistral OCR</b>",
        f"  Active keys: <code>{active_keys}</code>  |  Used today: <code>{ocr_today}</code>",
        "",
        f"🔴 <b>Errors:</b> <code>{err_1h}</code> (1h)  /  <code>{err_24h}</code> (24h)",
    ]

    if last_errors:
        lines += ["", "<b>Last 5 Errors:</b>"]
        for row in last_errors:
            ts = str(row["created_at"] or "")
            # Show only HH:MM:SS part
            try:
                ts_parsed = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ts_bd = ts_parsed.astimezone(_BD_TZ_MASTER)
                ts_disp = ts_bd.strftime("%m-%d %H:%M:%S")
            except Exception:
                ts_disp = ts[-14:-5] if len(ts) > 14 else ts
            ev = h(str(row["event"] or "")[:35])
            meta = ""
            with contextlib.suppress(Exception):
                meta = h(str((json.loads(row["meta_json"] or "{}") or {}).get("error") or "")[:70])
            if meta:
                lines.append(f"• <code>{ts_disp}</code> <b>{ev}</b> — <i>{meta}</i>")
            else:
                lines.append(f"• <code>{ts_disp}</code> <b>{ev}</b>")

    stats_text = "\n".join(lines)
    log_req_id = uuid.uuid4().hex[:10]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📥 Download Full Log", callback_data=f"master_dl_log:{log_req_id}")
    ]])

    if update.message:
        with contextlib.suppress(Exception):
            await update.message.reply_text(
                stats_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=kb,
            )


async def _master_log_download_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log download button — owner only, one-time."""
    q = update.callback_query
    if not q:
        return
    with contextlib.suppress(Exception):
        await q.answer("Generating log file...")

    uid = q.from_user.id if q.from_user else 0
    if not _is_owner_id(uid):
        with contextlib.suppress(Exception):
            await q.answer("Owner only.", show_alert=True)
        return

    # Remove button immediately
    with contextlib.suppress(Exception):
        await q.edit_message_reply_markup(reply_markup=None)

    snap = None
    try:
        snap = _write_combined_log_snapshot()
        now_bd = dt.datetime.now(_BD_TZ_MASTER).strftime("%Y%m%d_%H%M")
        with open(snap, "rb") as rf:
            await context.bot.send_document(
                chat_id=uid,
                document=rf,
                filename=f"probaho_logs_{now_bd}.log",
                caption=f"📋 Full log snapshot — {now_bd} (BD time)",
            )
    except Exception as e:
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                chat_id=uid,
                text=f"❌ Log export failed: {h(str(e)[:200])}",
                parse_mode=ParseMode.HTML,
            )
    finally:
        if snap:
            with contextlib.suppress(Exception):
                os.remove(snap)


# ─────────────────────────────────────────────
# 7. MASTER build_app: register everything once
# ─────────────────────────────────────────────

_master_prev_build_app = build_app

def build_app() -> Application:
    app = _master_prev_build_app()

    # ── Remove ALL existing solve: handlers (prevent duplicates) ──
    for group_id, handler_list in list(app.handlers.items()):
        to_remove = [
            h_ for h_ in list(handler_list)
            if isinstance(h_, CallbackQueryHandler) and
            "solve" in str(getattr(getattr(h_, "pattern", None), "pattern", str(getattr(h_, "pattern", ""))) or "")
        ]
        for h_ in to_remove:
            with contextlib.suppress(Exception):
                app.remove_handler(h_, group_id)

    # ── Register master handlers at group -100 (highest priority) ──
    app.add_handler(
        CallbackQueryHandler(on_solver_callback, pattern=r"^solve:[GPD]:[0-9a-f]{6,16}$"),
        group=-100,
    )
    app.add_handler(
        CallbackQueryHandler(_master_log_download_cb, pattern=r"^master_dl_log:"),
        group=-100,
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & filters.REPLY & (~filters.COMMAND),
            handle_user_reply_ocr_question,
        ),
        group=-100,
    )
    app.add_handler(
        CommandHandler(["ownerstats", "logs"], cmd_ownerstats, filters=filters.ChatType.PRIVATE),
        group=-100,
    )

    # ── Start midnight reset loop (post_init) ──
    _master_orig_post_init = getattr(app, "post_init", None)

    async def _master_post_init(application):
        if _master_orig_post_init and callable(_master_orig_post_init):
            try:
                await _master_orig_post_init(application)
            except Exception:
                pass
        asyncio.create_task(_master_midnight_reset_loop(bot=application.bot))
        logger.info("[MASTER PATCH] Midnight OCR reset loop started.")

    app.post_init = _master_post_init

    logger.info("[MASTER PATCH 2026-04-12-D] All fixes applied successfully.")
    return app


logger.info("[MASTER PATCH 2026-04-12-D] Loaded: smart OCR reply, dedup solver, professional streaming, group no-quote, midnight reset+notify, ownerstats button.")

# ===== END PROBAHO FINAL MASTER PATCH =====


