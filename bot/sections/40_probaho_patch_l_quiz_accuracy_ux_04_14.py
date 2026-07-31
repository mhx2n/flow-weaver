# ──────────────────────────────────────────────────────────────────────────────
# Section: 40_probaho_patch_l_quiz_accuracy_ux_04_14
# Original lines: 21130..21510
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════
# ===== PROBAHO PATCH-L: QUIZ ACCURACY + UX FIX (2026-04-14) =====
#
# সমস্যা ও সমাধান:
# 1. Quiz answer wrong  → generation prompt-এই সঠিক উত্তর থাকে,
#    verification phase আলাদা AI call করে ভুল করছিল → বাদ দেওয়া হয়েছে
# 2. Explanation মিলছে না → answer আর explanation একসাথে generate হবে
# 3. <b> tag দেখা যাচ্ছে → ui_box_html() দিয়ে ঠিক করা
# 4. /gen processing message প্রফেশনাল করা হয়েছে
# ═══════════════════════════════════════════════════════════════════════════

def _make_accurate_gen_prompt(source_text: str, n: int) -> str:
    """
    Generates a strong prompt that produces correct answer + matching explanation.
    Key insight: explanation must justify WHY the chosen answer is correct.
    """
    is_bn = _is_bangla_text(source_text[:300])
    lang = "Bangla" if is_bn else "English"
    expl_note = (
        "ব্যাখ্যায় সঠিক উত্তরটি কেন সঠিক তা স্পষ্টভাবে বলতে হবে।"
        if is_bn else
        "The explanation must clearly state WHY the correct answer is correct."
    )
    return (
        "Return STRICT JSON only. No markdown. No extra text before or after JSON.\n"
        f"Generate exactly {n} MCQ questions based ONLY on the academic content below.\n"
        f"Language: {lang}.\n\n"
        "CRITICAL RULES:\n"
        "1. answer: integer 1, 2, 3, or 4 — this MUST point to the CORRECT option.\n"
        "2. explanation: must match and justify the answer field. " + expl_note + "\n"
        "3. All 4 options must be plausible but only ONE is correct.\n"
        "4. Base every question strictly on the provided text — no invention.\n"
        "5. Do NOT repeat questions.\n\n"
        "JSON format (output ONLY this, nothing else):\n"
        '{"items":['
        '{"question":"...question text...","options":["A option","B option","C option","D option"],'
        '"answer":2,"explanation":"Option B is correct because..."}'
        "]}\n\n"
        f"Academic Content:\n{source_text[:10000]}"
    )


def _generate_quizzes_from_ocr_sync(ocr_ctx: Dict[str, Any], desired: int, user_id: int) -> List[Dict[str, Any]]:  # noqa: F811
    """
    PATCH-L MASTER: Accurate quiz generation.
    - Single-pass generation with strong prompt (no bad verification step)
    - Trust the AI's answer+explanation as a unit (they're generated together)
    - Only reject if answer is completely out of range
    """
    source_text = str(
        ocr_ctx.get("clean_text") or ocr_ctx.get("raw_markdown") or ""
    ).strip()
    if not source_text:
        raise RuntimeError("No readable OCR text found on this page.")

    desired = max(1, min(int(desired or 1), 30))
    out: List[Dict[str, Any]] = []
    seen: set = set()
    batch_size = 5
    max_rounds = max(3, (desired // batch_size) + 2)

    for _round in range(max_rounds):
        if len(out) >= desired:
            break

        need = min(batch_size, desired - len(out))
        avoid = ""
        if out:
            avoid = "\n\nAlready generated (DO NOT repeat):\n" + "\n".join(
                f"- {x['question'][:70]}" for x in out
            )

        prompt = _make_accurate_gen_prompt(source_text + avoid, need)

        raw = None
        # Backend chain: Gemini REST → Gemini3 web → Perplexity
        for backend_fn in [
            lambda: call_gemini_text_rest(prompt, timeout_seconds=30, force_json=True),
            lambda: (gemini3_solve(prompt) if callable(gemini3_solve) else None),
            lambda: query_ai(prompt),
        ]:
            try:
                result = backend_fn()
                if result and str(result).strip():
                    raw = str(result).strip()
                    break
            except Exception:
                pass

        if not raw:
            continue

        # Parse JSON robustly
        data = None
        for parse_attempt in [
            lambda s: _extract_json_strict(s),
            lambda s: json.loads(
                re.search(r'\{"items"\s*:\s*\[.*?\]\s*\}', s, re.DOTALL).group(0)
            ) if re.search(r'\{"items"\s*:\s*\[.*?\]\s*\}', s, re.DOTALL) else (_ for _ in ()).throw(ValueError()),
            lambda s: _repair_to_json(
                s,
                schema_hint='{"items":[{"question":"...","options":["...","...","...","..."],"answer":1,"explanation":"..."}]}',
                timeout_seconds=12,
            ),
        ]:
            try:
                data = parse_attempt(raw)
                if isinstance(data, dict) and data.get("items"):
                    break
            except Exception:
                data = None

        if not isinstance(data, dict):
            continue

        for it in (data.get("items") or []):
            if len(out) >= desired:
                break
            if not isinstance(it, dict):
                continue

            q = str(it.get("question") or "").strip()
            if not q or len(q) < 5:
                continue

            sig = re.sub(r"\s+", " ", q).lower()[:80]
            if sig in seen:
                continue

            # Options
            raw_opts = it.get("options") or []
            if isinstance(raw_opts, dict):
                raw_opts = list(raw_opts.values())
            opts = [str(x).strip() for x in raw_opts if str(x).strip()][:4]
            while len(opts) < 4:
                opts.append(f"Option {chr(65 + len(opts))}")

            # Answer — trust generation (answer and explanation were generated together)
            ans = int(it.get("answer", 0) or 0)
            if not (1 <= ans <= 4):
                # Try to infer from explanation text
                expl_text = str(it.get("explanation") or "").upper()
                for letter, num in [("A", 1), ("B", 2), ("C", 3), ("D", 4)]:
                    if f"OPTION {letter}" in expl_text or f"({letter})" in expl_text:
                        ans = num
                        break
                if not (1 <= ans <= 4):
                    ans = 1  # last resort default

            expl = str(it.get("explanation") or "").strip()

            seen.add(sig)
            out.append({
                "question": q,
                "options": opts,
                "answer": ans,
                "explanation": expl,
            })

    if not out:
        raise RuntimeError("Quiz generation failed. Please try again or use a different page.")
    return out[:desired]


# ── FIX: cmd_gen — professional processing + correct HTML ──
async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
    """PATCH-L: /gen with professional UX + accurate quizzes."""
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = int(update.effective_user.id)
    if is_banned(uid):
        return

    reply_msg = update.message.reply_to_message
    if not reply_msg:
        await safe_reply(update, usage_box(
            "gen", "[count]",
            "Reply to a page image or OCR message, then use:\n"
            "/gen — generate 1 quiz\n"
            "/gen 5 — generate 5 quizzes\n"
            "/gen 10 — generate 10 quizzes (max per page for users)"
        ))
        return

    requested = _parse_gen_count(update.message.text or "", list(context.args or []))
    is_staff = is_owner(uid) or is_admin(uid)

    # Get OCR context
    ocr_ctx = None
    reply_has_ctx = _has_ocr_context(context, reply_msg)
    if reply_has_ctx:
        ocr_ctx = _get_ocr_context(context, reply_msg.message_id)

    reply_is_media = bool(
        getattr(reply_msg, "photo", None) or
        (getattr(reply_msg, "document", None) and
         not str(getattr(getattr(reply_msg, "document", None), "file_name", "") or "").endswith(".txt"))
    )

    local_path = None
    proc = None

    if not ocr_ctx and reply_is_media:
        if not mistral_runtime_enabled() or not get_mistral_api_key():
            await warn(update, "OCR Unavailable",
                       "OCR is not configured. The owner needs to set up a Mistral API key first.")
            return
        try:
            proc = await _processing_start(
                update.message,
                "📄 Scanning Page",
                "Reading the image with Mistral OCR..."
            )
            if reply_msg.document:
                suffix = os.path.splitext(str(reply_msg.document.file_name or ""))[1][:6] or ".jpg"
                tg_file = await reply_msg.document.get_file()
            else:
                suffix = ".jpg"
                tg_file = await reply_msg.photo[-1].get_file()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                local_path = f.name
            await tg_file.download_to_drive(local_path)
            await _processing_update(proc, "📄 Scanning Page", "Extracting text and questions from image...")
            bundle = await _run_blocking(
                _role_of(uid), _extract_ocr_bundle_from_path, local_path, uid, timeout=300
            )
            ocr = bundle.get("ocr") or {}
            ocr_ctx = {
                "raw_markdown": str(ocr.get("raw_markdown") or ""),
                "clean_text": str(bundle.get("clean_text") or ""),
                "items": list(bundle.get("items") or []),
                "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
            }
            _remember_ocr_context(context, reply_msg.message_id, ocr_ctx)
            await _processing_delete(proc)
            proc = None
        except Exception as e:
            await _processing_delete(proc)
            proc = None
            db_log("ERROR", "gen_ocr_failed", {"user_id": uid, "error": str(e)})
            await err(update, "OCR Failed", f"Could not scan the image: {str(e)[:180]}")
            return
        finally:
            if local_path:
                with contextlib.suppress(Exception):
                    os.remove(local_path)

    if not ocr_ctx:
        await warn(update, "No Content", "Reply to a page image or an already-scanned OCR message first.")
        return

    # Quota check
    source_hash = _ocr_source_hash(ocr_ctx)
    day_key = _gen_day_key()

    if not is_staff:
        page_used = _gen_usage_page(uid, source_hash, day_key)
        day_used = _gen_usage_total(uid, day_key)
        page_left = max(0, _GEMINI_DEFAULT_PAGE_DAILY_LIMIT - page_used)
        day_left = max(0, _GEMINI_DEFAULT_USER_DAILY_LIMIT - day_used)
        allowed = min(requested, page_left, day_left)
        if allowed <= 0:
            await warn_html(
                update, "Daily Limit Reached",
                f"আজকের quiz generation limit শেষ হয়েছে।\n"
                f"প্রতি page: <code>{_GEMINI_DEFAULT_PAGE_DAILY_LIMIT}</code> টি\n"
                f"প্রতিদিন মোট: <code>{_GEMINI_DEFAULT_USER_DAILY_LIMIT}</code> টি",
                emoji="⛔",
            )
            return
    else:
        allowed = requested

    # Professional processing message
    try:
        proc = await _processing_start(
            update.message,
            "🧠 Generating Quizzes",
            f"Creating {allowed} accurate quiz question(s) from this page...\nThis may take 10–30 seconds."
        )
    except Exception:
        proc = None

    try:
        items = await _run_blocking(
            _role_of(uid),
            _generate_quizzes_from_ocr_sync,
            ocr_ctx, allowed, uid,
            timeout=360,
        )
        if not items:
            raise RuntimeError("No quiz items could be generated from this page.")

        await _processing_delete(proc)
        proc = None

        chat_id = update.message.chat_id
        lock = _get_chat_lock(context, chat_id)
        qpfx = (get_setting("quiz_prefix", "প্রবাহ") or "প্রবাহ").strip()
        qlink = (get_setting("quiz_expl_link", "") or "").strip()

        async with lock:
            for item in items[:allowed]:
                q = str(item.get("question") or "").strip()
                opts = _normalize_options([str(x) for x in (item.get("options") or [])], max_n=4)
                ans = int(item.get("answer") or 1)
                expl = _trim_expl_for_poll(str(item.get("explanation") or ""), qlink)

                if qpfx:
                    q = f"{qpfx}\n\u200b{q}"
                if len(q) > 300:
                    q = q[:297] + "..."
                if not (1 <= ans <= len(opts)):
                    ans = 1

                await _send_poll_with_retry(
                    context.bot,
                    chat_id=chat_id,
                    question=q,
                    options=opts,
                    is_anonymous=True,
                    type=Poll.QUIZ,
                    correct_option_id=ans - 1,
                    explanation=expl if expl else None,
                )
                await asyncio.sleep(0.3)

        if not is_staff:
            _gen_usage_add(uid, source_hash, day_key, len(items[:allowed]))

        # ✅ FIXED: use ok_html so HTML renders properly
        remaining_page = max(0, _GEMINI_DEFAULT_PAGE_DAILY_LIMIT - _gen_usage_page(uid, source_hash, day_key)) if not is_staff else "∞"
        remaining_day  = max(0, _GEMINI_DEFAULT_USER_DAILY_LIMIT  - _gen_usage_total(uid, day_key))             if not is_staff else "∞"
        quota_line = f"\n📊 Remaining — Page: <code>{remaining_page}</code> | Today: <code>{remaining_day}</code>" if not is_staff else ""

        await ok_html(
            update,
            "✅ Quiz Generated",
            f"Successfully created <b>{len(items[:allowed])}</b> quiz question(s) from this page.{quota_line}",
            emoji="📊",
        )

    except Exception as e:
        await _processing_delete(proc)
        proc = None
        db_log("ERROR", "gen_quiz_failed_l", {"user_id": uid, "error": str(e)})
        await err(update, "Quiz Generation Failed", str(e)[:220])


# ── Re-register cmd_gen at highest priority ──
_prev_build_app_l = build_app

def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_l()

    # Remove old cmd_gen handlers
    for gid, handler_list in list(app.handlers.items()):
        to_del = [
            h_ for h_ in list(handler_list)
            if isinstance(h_, (CommandHandler, MessageHandler))
            and getattr(getattr(h_, "callback", None), "__name__", "") == "cmd_gen"
        ]
        for h_ in to_del:
            with contextlib.suppress(Exception):
                app.remove_handler(h_, gid)

    # Register fresh cmd_gen everywhere
    app.add_handler(CommandHandler("gen", cmd_gen), group=-300)
    try:
        app.add_handler(_build_dot_command_handler("gen", cmd_gen), group=-300)
    except Exception:
        pass

    logger.info("[PATCH-L] /gen re-registered with accurate quiz generation + professional UX.")
    return app


logger.info("[PATCH-L 2026-04-14] Accurate quiz gen, no bad verification, professional /gen UX, HTML fix.")

# ===== END PROBAHO PATCH-L =====
