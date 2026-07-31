# ──────────────────────────────────────────────────────────────────────────────
# Section: 50_master_ocr_quiz_extractor_06_13
# Master OCR → MCQ extractor + per-page content-question generator.
# DO NOT import directly — exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────

# ==== MASTER MCQ EXTRACTION PROMPT (handles ALL formats: Bangla/English/mixed,
# ক)খ)গ)ঘ), a)b)c)d), A.B.C.D., 1.2.3.4, tables, numbered, "Answer: D",
# "সঠিক উত্তর: ক) 5.0", (a)(b)(c)(d) trailing markers, ⓐ ⓑ circled,
# Sol", Ans:, ✓/✔ marks, bold/underlined correct option, multi-column layouts) ====

_MASTER_MCQ_PROMPT_HEADER = (
    "Return STRICT JSON only. No markdown, no commentary.\n"
    "TASK: Extract EVERY visible multiple-choice question (MCQ) from the OCR text below.\n"
    "The text may be Bangla, English, or mixed. It may use any of these formats:\n"
    "  • Question numbering: ১., 1., (1), Q1., 01., প্রশ্ন ১: , etc.\n"
    "  • Option markers: ক)/খ)/গ)/ঘ)/ঙ), a)/b)/c)/d)/e), A./B./C./D./E.,\n"
    "    (a)/(b)/(c)/(d), 1)/2)/3)/4), i)/ii)/iii)/iv), ①②③④, ⓐⓑⓒⓓ.\n"
    "  • Multi-column layout (left/right): preserve question→options grouping.\n"
    "  • Tables of options.\n"
    "  • Correct answer markers may appear as:\n"
    "      'সঠিক উত্তর: ঘ) 2', 'উত্তরঃ ক', 'Answer: D', 'Ans: (b)',\n"
    "      'Correct: C', 'Sol\":', trailing letter in a circle ⓑ/ⓐ,\n"
    "      a bold/underlined/ticked (✓/✔) option, or an answer key table.\n"
    "  • Explanations may follow 'Explanation:', 'ব্যাখ্যা:', 'Sol:', '[…]'.\n"
    "RULES:\n"
    " 1. Keep the question text in its ORIGINAL language and wording. Strip leading numbering.\n"
    " 2. Options must be CLEAN plain text — strip leading 'ক)', 'A.', '(a)' etc. but keep the answer content.\n"
    " 3. Most MCQs have 4 options; allow 2–5.\n"
    " 4. If correct option is identifiable (any of the markers above), set answer = 1..N matching option order.\n"
    " 5. correct_option_text MUST repeat the exact extracted text of the correct option when answer>0.\n"
    " 6. If unclear, set answer=0 and correct_option_text=''.\n"
    " 7. Put any visible explanation/solution into explanation; otherwise ''.\n"
    " 8. SKIP questions that are not MCQ (essays, fill-in-the-blank without options, short-answer).\n"
    " 9. DO NOT invent options or answers. DO NOT translate.\n"
    "10. Output every MCQ you can see — do not stop early.\n\n"
    'JSON FORMAT (strict):\n'
    '{"items":[{"questions":"...","option1":"...","option2":"...","option3":"...","option4":"...","option5":"","answer":0,"correct_option_text":"","explanation":""}]}\n\n'
    "OCR TEXT:\n"
)


def _extract_mcq_items_master(chunk_text: str) -> List[Dict[str, Any]]:
    body = (chunk_text or "").strip()
    if not body:
        return []
    prompt = _MASTER_MCQ_PROMPT_HEADER + body[:18000]
    raw = None
    last_err = None
    if GEMINI_API_KEYS:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=14, force_json=True)
        except Exception as e:
            last_err = e
    if not raw:
        try:
            raw = gemini3_solve(prompt)
        except Exception as e:
            last_err = e
    if not raw and USE_PERPLEXITY_FALLBACK:
        try:
            raw = query_ai(prompt)
        except Exception as e:
            last_err = e
    if not raw:
        if last_err:
            db_log("WARN", "master_mcq_extract_failed", {"error": str(last_err)})
        return []
    try:
        data = _extract_json_strict(raw)
    except Exception:
        try:
            data = _repair_to_json(
                raw,
                schema_hint='{"items":[{"questions":"...","option1":"...","option2":"...","option3":"...","option4":"...","option5":"","answer":0,"correct_option_text":"","explanation":""}]}',
                timeout_seconds=10,
            )
        except Exception:
            return []
    if not isinstance(data, dict):
        return []
    out: List[Dict[str, Any]] = []
    for it in (data.get("items") or [])[:120]:
        q = str(it.get("questions") or it.get("question") or "").strip()
        if not q:
            continue
        opts: List[str] = []
        if isinstance(it.get("options"), list):
            opts = [str(x or "").strip() for x in it["options"] if str(x or "").strip()]
        else:
            for k in ("option1", "option2", "option3", "option4", "option5"):
                v = str(it.get(k) or "").strip()
                if v:
                    opts.append(v)
        if len(opts) < 2:
            continue
        ans = int(it.get("answer", 0) or 0)
        mapped = _match_answer_text_to_options(str(it.get("correct_option_text") or ""), opts)
        if mapped:
            ans = mapped
        if not (1 <= ans <= len(opts)):
            ans = 0
        out.append({
            "questions": q,
            "option1": opts[0] if len(opts) > 0 else "",
            "option2": opts[1] if len(opts) > 1 else "",
            "option3": opts[2] if len(opts) > 2 else "",
            "option4": opts[3] if len(opts) > 3 else "",
            "option5": opts[4] if len(opts) > 4 else "",
            "answer": ans,
            "explanation": _sanitize_quiz_explanation_text(str(it.get("explanation") or "").strip()),
            "type": 1,
            "section": 1,
        })
    return out


# ==== Page-by-page processor: extract MCQs per page, classify content-pages ====

def _page_clean_text(page: Dict[str, Any]) -> str:
    md = str((page or {}).get("markdown") or "").strip()
    return _ocr_preserve_text_layout(md) if md else ""


def _estimate_generatable_counts(content_text: str) -> Dict[str, int]:
    """Ask Gemini how many easy/medium/hard MCQs can be generated from a content page."""
    body = (content_text or "").strip()
    if len(body) < 80:
        return {"easy": 0, "medium": 0, "hard": 0}
    prompt = (
        "Return STRICT JSON only.\n"
        "Read the academic content text below (any language).\n"
        "Estimate the MAXIMUM number of high-quality MCQ questions that can be created from it, by difficulty.\n"
        "Be realistic — count only facts/concepts that yield a clean MCQ with 4 options.\n"
        'JSON: {"easy":N,"medium":N,"hard":N}\n\n'
        f"CONTENT:\n{body[:9000]}"
    )
    raw = None
    if GEMINI_API_KEYS:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=10, force_json=True)
        except Exception:
            pass
    if not raw:
        try:
            raw = gemini3_solve(prompt)
        except Exception:
            return {"easy": 0, "medium": 0, "hard": 0}
    try:
        data = _extract_json_strict(raw)
    except Exception:
        return {"easy": 0, "medium": 0, "hard": 0}
    if not isinstance(data, dict):
        return {"easy": 0, "medium": 0, "hard": 0}
    return {
        "easy": max(0, min(15, int(data.get("easy", 0) or 0))),
        "medium": max(0, min(15, int(data.get("medium", 0) or 0))),
        "hard": max(0, min(15, int(data.get("hard", 0) or 0))),
    }


def _generate_mcqs_from_content(content_text: str, *, easy: int, medium: int, hard: int) -> List[Dict[str, Any]]:
    if (easy + medium + hard) <= 0:
        return []
    body = (content_text or "").strip()
    if not body:
        return []
    prompt = (
        "Return STRICT JSON only.\n"
        "Create high-quality MCQ questions from the academic content below.\n"
        "Keep the SAME language as the content (Bangla/English/mixed).\n"
        f"Counts required: easy={easy}, medium={medium}, hard={hard}.\n"
        "Each MCQ: 4 plausible options, exactly one correct, short explanation.\n"
        "Vary difficulty: easy=direct recall, medium=apply concept, hard=multi-step/tricky distractors.\n"
        "Do NOT repeat questions. Do NOT invent facts not supported by the text.\n"
        'JSON: {"items":[{"questions":"...","option1":"...","option2":"...","option3":"...","option4":"...","option5":"","answer":1,"explanation":"...","difficulty":"easy|medium|hard"}]}\n\n'
        f"CONTENT:\n{body[:12000]}"
    )
    raw = None
    if GEMINI_API_KEYS:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=18, force_json=True)
        except Exception:
            pass
    if not raw:
        try:
            raw = gemini3_solve(prompt)
        except Exception:
            return []
    try:
        data = _extract_json_strict(raw)
    except Exception:
        try:
            data = _repair_to_json(raw, schema_hint='{"items":[]}', timeout_seconds=8)
        except Exception:
            return []
    if not isinstance(data, dict):
        return []
    out: List[Dict[str, Any]] = []
    for it in (data.get("items") or [])[:30]:
        q = str(it.get("questions") or it.get("question") or "").strip()
        if not q:
            continue
        opts = [str(it.get(f"option{i}") or "").strip() for i in range(1, 6)]
        opts = [o for o in opts if o]
        if len(opts) < 2:
            continue
        ans = int(it.get("answer", 0) or 0)
        if not (1 <= ans <= len(opts)):
            ans = 1
        out.append({
            "questions": q,
            "option1": opts[0] if len(opts) > 0 else "",
            "option2": opts[1] if len(opts) > 1 else "",
            "option3": opts[2] if len(opts) > 2 else "",
            "option4": opts[3] if len(opts) > 3 else "",
            "option5": opts[4] if len(opts) > 4 else "",
            "answer": ans,
            "explanation": _sanitize_quiz_explanation_text(str(it.get("explanation") or "").strip()),
            "type": 1,
            "section": 1,
        })
    return out


# ==== Override page-aggregator to use master extractor and per-page processing ====

def _ocr_pages_to_clean_text_and_items(pages: List[Dict[str, Any]], user_id: int) -> Tuple[str, List[Dict[str, Any]]]:
    pages = list(pages or [])
    parts: List[str] = []
    items: List[Dict[str, Any]] = []
    for idx, page in enumerate(pages, start=1):
        cleaned = _page_clean_text(page)
        if not cleaned:
            continue
        parts.append(f"[Page {idx}]\n{cleaned}")
        try:
            page_items = _extract_mcq_items_master(cleaned)
            if page_items:
                items.extend(page_items)
        except Exception as e:
            db_log("WARN", "master_mcq_page_failed", {"page": idx, "error": str(e)})
            continue
    clean_text = "\n\n".join(parts).strip()
    if not items and clean_text:
        # final fallback: legacy block parser
        try:
            for block in split_blocks(clean_text):
                parsed = parse_text_block(block, user_id)
                if parsed:
                    items.append(parsed)
        except Exception:
            pass
    items = _dedupe_mcq_items(items)
    return clean_text, items


def _collect_content_pages(pages: List[Dict[str, Any]]) -> List[Tuple[int, str]]:
    """Return [(page_idx, clean_text)] for pages with NO MCQs detected."""
    out: List[Tuple[int, str]] = []
    for idx, page in enumerate(pages or [], start=1):
        text = _page_clean_text(page)
        if not text or len(text) < 80:
            continue
        try:
            its = _extract_mcq_items_master(text)
        except Exception:
            its = []
        if not its:
            out.append((idx, text))
    return out


# ==== Generation flow: confirmation keyboard + callbacks ====

_GENQ_STORE_KEY = "_master_genq_store"


def _genq_store(context) -> Dict[str, Any]:
    bd = context.application.bot_data
    if _GENQ_STORE_KEY not in bd:
        bd[_GENQ_STORE_KEY] = {}
    return bd[_GENQ_STORE_KEY]


def _genq_kb(token: str, counts: Dict[str, int]) -> InlineKeyboardMarkup:
    e, m, hd = int(counts.get("easy", 0)), int(counts.get("medium", 0)), int(counts.get("hard", 0))
    total = e + m + hd
    rows = []
    if total > 0:
        rows.append([InlineKeyboardButton(f"✅ Generate ({total}) E:{e} M:{m} H:{hd}", callback_data=f"genq:go:{token}")])
    rows.append([
        InlineKeyboardButton("🔄 Regenerate Counts", callback_data=f"genq:re:{token}"),
        InlineKeyboardButton("🚫 Skip", callback_data=f"genq:no:{token}"),
    ])
    return InlineKeyboardMarkup(rows)


async def _send_content_page_offer(context, chat_id: int, uid: int, page_idx: int, text: str):
    counts = await _run_blocking(_role_of(uid), _estimate_generatable_counts, text, timeout=40)
    token = uuid.uuid4().hex[:10]
    _genq_store(context)[token] = {
        "uid": uid,
        "chat_id": chat_id,
        "page": page_idx,
        "text": text,
        "counts": counts,
        "ts": time.time(),
    }
    total = sum(int(counts.get(k, 0)) for k in ("easy", "medium", "hard"))
    body = (
        f"📄 Page <code>{page_idx}</code> looks like content (no MCQs found).\n\n"
        f"Generatable MCQs estimate:\n"
        f"  • Easy: <code>{int(counts.get('easy',0))}</code>\n"
        f"  • Medium: <code>{int(counts.get('medium',0))}</code>\n"
        f"  • Hard: <code>{int(counts.get('hard',0))}</code>\n"
        f"  • Total: <code>{total}</code>\n\n"
        "Generate these MCQs and add to your buffer?"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=ui_box_html(f"Generate from Page {page_idx}?", body, emoji="🧠"),
        parse_mode=ParseMode.HTML,
        reply_markup=_genq_kb(token, counts),
        disable_web_page_preview=True,
    )


async def cb_genq(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        return
    uid = int(entry.get("uid") or 0)
    caller = q.from_user.id if q.from_user else 0
    if caller != uid:
        with contextlib.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        return
    text = str(entry.get("text") or "")
    counts = entry.get("counts") or {}
    page_idx = int(entry.get("page") or 0)

    if action == "no":
        store.pop(token, None)
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                ui_box_html(f"Page {page_idx} Skipped", "No MCQs generated.", emoji="🚫"),
                parse_mode=ParseMode.HTML,
            )
        with contextlib.suppress(Exception):
            await q.answer("Skipped")
        return

    if action == "re":
        with contextlib.suppress(Exception):
            await q.answer("Re-estimating…")
        try:
            new_counts = await _run_blocking(_role_of(uid), _estimate_generatable_counts, text, timeout=40)
        except Exception:
            new_counts = counts
        entry["counts"] = new_counts
        total = sum(int(new_counts.get(k, 0)) for k in ("easy", "medium", "hard"))
        body = (
            f"📄 Page <code>{page_idx}</code> (re-estimated)\n\n"
            f"  • Easy: <code>{int(new_counts.get('easy',0))}</code>\n"
            f"  • Medium: <code>{int(new_counts.get('medium',0))}</code>\n"
            f"  • Hard: <code>{int(new_counts.get('hard',0))}</code>\n"
            f"  • Total: <code>{total}</code>"
        )
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                ui_box_html(f"Generate from Page {page_idx}?", body, emoji="🧠"),
                parse_mode=ParseMode.HTML,
                reply_markup=_genq_kb(token, new_counts),
            )
        return

    if action == "go":
        with contextlib.suppress(Exception):
            await q.answer("Generating…")
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                ui_box_html(f"Generating Page {page_idx}", "Building MCQs, please wait…", emoji="⏳"),
                parse_mode=ParseMode.HTML,
            )
        try:
            items = await _run_blocking(
                _role_of(uid),
                _generate_mcqs_from_content,
                text,
                easy=int(counts.get("easy", 0)),
                medium=int(counts.get("medium", 0)),
                hard=int(counts.get("hard", 0)),
                timeout=120,
            )
        except Exception as e:
            db_log("ERROR", "genq_generate_failed", {"user_id": uid, "error": str(e)})
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
                    f"Page {page_idx} → Buffer",
                    f"Added <code>{added}</code> generated MCQ(s).\nTotal buffered: <code>{buffer_count(uid)}</code>\n\nUse /done to export or /post to publish.",
                    emoji="✅",
                ),
                parse_mode=ParseMode.HTML,
            )
        return


# ==== Override staff OCR pipeline: after extraction, offer per-page generation ====

_prev_run_staff_ocr_pipeline_master = _run_staff_ocr_pipeline


async def _run_staff_ocr_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE, source_msg, local_path: str, *, source_label: str = "image") -> Dict[str, Any]:
    ctx_payload = await _prev_run_staff_ocr_pipeline_master(update, context, source_msg, local_path, source_label=source_label)
    # Offer content-page generation for any pages with no MCQs
    try:
        pages = []
        # Re-run OCR cache via raw_markdown? We already have it; we need pages list.
        # The previous pipeline doesn't return pages directly, but we can reuse last context.
        # Instead, recompute lightweight from raw_markdown split by [Page N] markers if available.
        raw = str((ctx_payload or {}).get("raw_markdown") or "")
        if raw:
            # split clean_text by [Page N] markers
            ct = str((ctx_payload or {}).get("clean_text") or "")
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
            # For each page with NO MCQs in items (heuristic: items don't carry page info,
            # so we re-check per page whether master extractor finds MCQs)
            uid = update.effective_user.id if update and update.effective_user else 0
            chat_id = source_msg.chat_id
            content_pages = await _run_blocking(
                _role_of(uid),
                lambda: [(i, t) for (i, t) in page_texts if t and len(t) >= 80 and not _extract_mcq_items_master(t)],
                timeout=180,
            )
            for (idx, txt) in content_pages[:6]:  # cap to avoid spam
                try:
                    await _send_content_page_offer(context, chat_id, uid, idx, txt)
                except Exception as e:
                    db_log("WARN", "send_content_offer_failed", {"page": idx, "error": str(e)})
    except Exception as e:
        db_log("WARN", "master_pipeline_postprocess_failed", {"error": str(e)})
    return ctx_payload


# ==== Register callback handler ====

_prev_build_app_master_06_13 = build_app


def build_app() -> Application:
    app = _prev_build_app_master_06_13()
    with contextlib.suppress(Exception):
        app.add_handler(CallbackQueryHandler(cb_genq, pattern=r"^genq:(go|re|no):[0-9a-f]+$"))
    return app

# ===== END MASTER OCR QUIZ EXTRACTOR =====
