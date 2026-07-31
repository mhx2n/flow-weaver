# ──────────────────────────────────────────────────────────────────────────────
# Section: 21_final_backend_routing_fix_03_16
# Original lines: 11082..11318
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL BACKEND ROUTING FIX (2026-03-16) =====
# Goal:
# 1) Prefer official Google AI Studio REST for Gemini selections so requests appear in AI Studio usage.
# 2) Fall back to Gemini Web scraping only if REST fails.
# 3) Fall back to Perplexity only as the last option.
# 4) Show the ACTUAL backend name in quiz/text replies.
USE_OFFICIAL_GEMINI_REST_FALLBACK = True
USE_GEMINI_REST_FOR_GENQUIZ = True


def _try_gemini_text_backends(prompt: str, *, timeout_seconds: int = 18) -> Tuple[str, str]:
    last_error = None

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


# Keep the public helper name, but route Gemini choice to REST first.
def gemini_solve_text(problem_text: str) -> str:
    prompt = STRICT_SYSTEM_PROMPT + "\n\nUser Message:\n" + (problem_text or "").strip()
    out, _used_model = _try_gemini_text_backends(prompt, timeout_seconds=18)
    return out


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
        "Task: Solve the following MCQ and pick the correct option.\n"
        "Rules:\n"
        "- answer must be 1-5 (A=1,B=2,C=3,D=4,E=5). If unsure, pick the best option.\n"
        f"- {lang_rule}\n"
        "- explanation: clear exam-style explanation.\n"
        "- why_not: short reason for wrong options.\n"
        "- confidence: 0-100 integer.\n\n"
        f"Question:\n{q}\n\nOptions:\n{opt_lines}\n\n"
        "JSON format:\n"
        f'{{"answer":1,"confidence":0,"explanation":"{schema_expl}","why_not":{{"A":"..","B":"..","C":"..","D":"..","E":".."}}}}'
    )
    return prompt, opts


def _try_gemini_mcq_backends(question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:
    prompt, opts = _build_mcq_json_prompt(question, options)
    last_error = None

    if USE_OFFICIAL_GEMINI_REST_FALLBACK and GEMINI_API_KEY:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=18, force_json=True)
            data = _extract_json_strict(raw)
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "Gemini REST"
        except Exception as e:
            last_error = e

    try:
        raw = gemini3_solve(prompt)
        data = _extract_json_strict(raw)
        if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
            return data, "Gemini Web"
    except Exception as e:
        last_error = e

    if USE_PERPLEXITY_FALLBACK:
        try:
            alt = query_ai(prompt)
            if alt:
                try:
                    data = _extract_json_strict(alt)
                    if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                        return data, "Perplexity"
                except Exception:
                    pass
                inferred = _infer_option_from_text(alt, len(opts))
                return {
                    "answer": inferred,
                    "confidence": 0,
                    "explanation": (alt[:1800] if isinstance(alt, str) else str(alt)[:1800]),
                    "why_not": {},
                }, "Perplexity"
        except Exception as e:
            last_error = e

    raise RuntimeError(str(last_error or "AI backend is temporarily unavailable. Please try again."))


def gemini_solve_mcq_json(question: str, options: List[str]) -> Dict[str, Any]:
    data, _used_model = _try_gemini_mcq_backends(question, options)
    return data


def _solve_mcq_with_preference(model: str, question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:
    model = (model or "G").upper()
    if model == "P":
        try:
            return perplexity_solve_mcq_json(question, options), "Perplexity"
        except Exception:
            return _try_gemini_mcq_backends(question, options)
    if model == "D":
        try:
            return deepseek_solve_mcq_json(question, options), "DeepSeek"
        except Exception:
            return _try_gemini_mcq_backends(question, options)
    return _try_gemini_mcq_backends(question, options)


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
        data, used_model = await _run_blocking(_role_of(uid), _solve_mcq_with_preference, "G", qtext, options)
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
            model_expl=f"[{used_model}]\n{model_expl}".strip(),
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
        await send_poll_verify_buttons(update, context, poll_payload, msg_html)
    except Exception as e:
        if spinner_task:
            spinner_task.cancel()
        if spinner_msg:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(chat_id=spinner_msg.chat_id, message_id=spinner_msg.message_id)
        db_log("ERROR", "poll_solver_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Solve Failed", f"{h(str(e)[:160])}")



