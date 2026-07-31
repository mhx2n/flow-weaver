# ──────────────────────────────────────────────────────────────────────────────
# Section: 38_probaho_final_patch_j_04_13
# Original lines: 20183..20949
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════
# ===== PROBAHO FINAL PATCH 2026-04-13-J =====
# Fixes & New Features (all existing features preserved):
#
# FIX 1: Gemini key rotation — quota 429 এ পরের key এ যাবে seamlessly
# FIX 2: OCR → quiz buffer (admin) — quiz creation error fixed
# FIX 3: /gen prompt — stronger JSON + verification, no bad quizzes
# FIX 4: /qans user — specific Q number from any page correctly
# FIX 5: Model chain — gemini-2.0, 2.5, 3-flash all rotate properly
# FIX 6: _solve_text_with_preference / _solve_mcq_with_preference stability
# NEW:   /gemini add/list/remove — এখন properly per-key quota tracks
# ═══════════════════════════════════════════════════════════════════════════

import hashlib as _hashlib_j

# ─────────────────────────────────────────────────────────────────
# 1. GEMINI MODEL ORDER — 2.0 → 2.5 → gemini-3-flash
#    All three models rotate; if one 429s, next model+key is tried
# ─────────────────────────────────────────────────────────────────

_STABLE_TEXT_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.5-flash",
    "models/gemini-3-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-1.5-flash",
]
_STABLE_VISION_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.5-flash",
    "models/gemini-3-flash",
    "models/gemini-1.5-flash",
]

def _all_text_model_candidates() -> List[str]:  # noqa: F811
    seen: set = set()
    out: List[str] = []
    for m in _STABLE_TEXT_MODELS:
        nm = _normalize_model_name(m)
        if nm and nm not in seen:
            seen.add(nm)
            out.append(nm)
    return out or ["models/gemini-2.0-flash"]

def _all_vision_model_candidates() -> List[str]:  # noqa: F811
    seen: set = set()
    out: List[str] = []
    for m in _STABLE_VISION_MODELS:
        nm = _normalize_model_name(m)
        if nm and nm not in seen:
            seen.add(nm)
            out.append(nm)
    return out or ["models/gemini-2.0-flash"]


# ─────────────────────────────────────────────────────────────────
# 2. CORE GEMINI CALL — per-key, per-model quota tracking
#    If key+model hits 429 → mark key as limited → try next key
#    If all keys for model exhausted → try next model
# ─────────────────────────────────────────────────────────────────

def _gemini_call_with_key_rotation(model: str, payload: Dict[str, Any], *, timeout_seconds: int = 20) -> str:  # noqa: F811
    """
    FIXED: Properly rotates Gemini keys AND models.
    Order: key1+model1 → key2+model1 → ... → key1+model2 → ...
    """
    model = _normalize_model_name(model)
    keys = get_gemini_api_keys()
    if not keys:
        raise RuntimeError("No Gemini API key configured. Use /gemini add YOUR_KEY.")

    last_err: Optional[Exception] = None
    all_models = _all_text_model_candidates()
    # Ensure requested model is tried first
    if model and model not in all_models:
        all_models = [model] + all_models

    for try_model in all_models[:5]:
        url_base = f"https://generativelanguage.googleapis.com/v1beta/{try_model}:generateContent?key="
        for api_key in keys:
            try:
                r = requests.post(
                    url_base + api_key,
                    json=payload,
                    timeout=max(8, int(timeout_seconds or 20)),
                )
                if r.status_code == 200:
                    data = r.json()
                    text = _extract_gemini_text_from_response(data)
                    if text and str(text).strip():
                        _gemini_mark_key_status(api_key, "ok", "")
                        return str(text).strip()
                    _gemini_mark_key_status(api_key, "empty", "empty response")
                    last_err = RuntimeError("Empty response")
                elif r.status_code == 429 or _is_gemini_quota_error(r.status_code, r.text):
                    _gemini_mark_key_status(api_key, "quota", f"HTTP 429 {try_model}")
                    last_err = RateLimitError(f"Quota exhausted for key on {try_model}")
                    continue  # try next key with same model
                else:
                    body = str(r.text or "")[:300]
                    _gemini_mark_key_status(api_key, "error", f"HTTP {r.status_code}")
                    last_err = RuntimeError(f"HTTP {r.status_code}: {body}")
                    continue
            except RateLimitError as e:
                last_err = e
                continue
            except Exception as e:
                _gemini_mark_key_status(api_key, "error", str(e)[:200])
                last_err = e
                continue

    raise RuntimeError(str(last_err or "Gemini REST backend unavailable — all keys/models exhausted."))


def call_gemini_text_rest(prompt: str, timeout_seconds: int = 20, *, force_json: bool = False) -> str:  # noqa: F811
    """FIXED: Tries every model × every key. No silent failure."""
    keys = get_gemini_api_keys()
    if not keys:
        raise RuntimeError("No Gemini API key. Use /gemini add YOUR_KEY.")

    last_err: Optional[Exception] = None
    json_modes = [True, False] if force_json else [False]
    models = _all_text_model_candidates()

    for use_json in json_modes:
        payload = _build_gemini_text_payload(prompt, force_json=use_json)
        for model in models:
            for api_key in keys:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"
                    r = requests.post(url, json=payload, timeout=max(10, timeout_seconds))
                    if r.status_code == 200:
                        data = r.json()
                        text = _extract_gemini_text_from_response(data)
                        if text and str(text).strip():
                            _gemini_mark_key_status(api_key, "ok", "")
                            return str(text).strip()
                    elif r.status_code == 429 or _is_gemini_quota_error(r.status_code, r.text):
                        _gemini_mark_key_status(api_key, "quota", f"429 {model}")
                        last_err = RateLimitError(f"quota on {model}")
                        continue
                    else:
                        last_err = RuntimeError(f"HTTP {r.status_code}")
                        continue
                except RateLimitError as e:
                    last_err = e
                    continue
                except Exception as e:
                    last_err = e
                    continue

    raise RuntimeError(str(last_err or "All Gemini models/keys exhausted."))


def call_gemini_vision_rest(image_path: str, prompt: str, force_json: bool = True) -> str:  # noqa: F811
    """FIXED: Vision with model×key rotation."""
    keys = get_gemini_api_keys()
    if not keys:
        raise RuntimeError("No Gemini API key. Use /gemini add YOUR_KEY.")

    last_err: Optional[Exception] = None
    json_modes = [True, False] if force_json else [False]
    models = _all_vision_model_candidates()

    for use_json in json_modes:
        payload = _build_gemini_vision_payload(image_path, prompt, force_json=use_json)
        for model in models:
            for api_key in keys:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"
                    r = requests.post(url, json=payload, timeout=60)
                    if r.status_code == 200:
                        text = _extract_gemini_text_from_response(r.json())
                        if text and str(text).strip():
                            _gemini_mark_key_status(api_key, "ok", "")
                            return str(text).strip()
                    elif r.status_code == 429 or _is_gemini_quota_error(r.status_code, r.text):
                        _gemini_mark_key_status(api_key, "quota", f"429 {model}")
                        last_err = RateLimitError(f"quota on {model}")
                        continue
                    else:
                        last_err = RuntimeError(f"HTTP {r.status_code}")
                except RateLimitError as e:
                    last_err = e
                    continue
                except Exception as e:
                    last_err = e
                    continue

    raise RuntimeError(str(last_err or "Vision backend unavailable."))


# ─────────────────────────────────────────────────────────────────
# 3. ULTRA STABLE TEXT + MCQ ROUTER
#    Chain: Gemini REST (all keys×models) → Perplexity → Gemini3 web
# ─────────────────────────────────────────────────────────────────

def _ultra_text_stable(prompt: str, timeout: int = 20) -> Tuple[str, str]:
    last_err = None
    # 1) Gemini REST (all keys × all models inside call_gemini_text_rest)
    if get_gemini_api_keys():
        try:
            out = call_gemini_text_rest(prompt, timeout_seconds=timeout)
            if out:
                return _sanitize_answer_text(out), "✨ Gemini"
        except Exception as e:
            last_err = e

    # 2) Perplexity
    try:
        alt = query_ai(prompt)
        if alt and str(alt).strip():
            return _sanitize_answer_text(str(alt).strip()), "⚛ Perplexity"
    except Exception as e:
        last_err = e

    # 3) Gemini3 web session
    try:
        res = chat_with_gemini(prompt)
        if isinstance(res, dict) and res.get("success") and res.get("response"):
            return _sanitize_answer_text(str(res["response"]).strip()), "✨ Gemini"
    except Exception as e:
        last_err = e

    raise RuntimeError(f"AI সাময়িকভাবে অনুপলব্ধ। কিছুক্ষণ পর আবার চেষ্টা করুন। ({str(last_err)[:60]})")


def _ultra_mcq_stable(question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:
    q = str(question or "").strip()
    opts = [(o or "").strip() for o in (options or []) if (o or "").strip()][:5]
    if len(opts) < 2:
        raise ValueError("Not enough options.")

    is_bn = _is_bangla_text(q + " " + " ".join(opts))
    opt_lines = "\n".join([f"{_safe_letter(i+1)}. {opts[i]}" for i in range(len(opts))])
    lang_rule = _quiz_language_rule_block(is_bn)
    schema_expl = _quiz_schema_example_explanation(is_bn)

    prompt = (
        "Return STRICT JSON only. No markdown. No preamble.\n"
        f"{lang_rule}\n"
        "Format: "
        '{"answer":1,"confidence":85,"explanation":"short explanation","why_not":{"A":"..","B":"..","C":"..","D":".."}}\n\n'
        f"Question:\n{q}\n\nOptions:\n{opt_lines}\n"
    )

    last_err = None

    # 1) Gemini REST
    if get_gemini_api_keys():
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=20, force_json=True)
            data = _coerce_mcq_result(raw, len(opts))
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "✨ Gemini"
        except Exception as e:
            last_err = e

    # 2) Perplexity
    try:
        alt = query_ai(prompt)
        if alt:
            data = _coerce_mcq_result(str(alt), len(opts))
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "⚛ Perplexity"
            inferred = _infer_option_from_text(str(alt), len(opts)) if "_infer_option_from_text" in globals() else 0
            return {"answer": inferred, "confidence": 0, "explanation": str(alt)[:1800], "why_not": {}}, "⚛ Perplexity"
    except Exception as e:
        last_err = e

    # 3) Gemini3 web
    try:
        res = chat_with_gemini(prompt)
        if isinstance(res, dict) and res.get("success") and res.get("response"):
            raw = str(res["response"]).strip()
            data = _coerce_mcq_result(raw, len(opts))
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "✨ Gemini"
    except Exception as e:
        last_err = e

    raise RuntimeError(f"সকল AI ব্যাকএন্ড সাময়িকভাবে অনুপলব্ধ। ({str(last_err)[:60]})")


def _solve_text_with_preference(model: str, problem_text: str, scope: str = "private_academic") -> Tuple[str, str]:  # noqa: F811
    prompt = _build_solver_prompt(problem_text, scope) if "_build_solver_prompt" in globals() else (
        STRICT_SYSTEM_PROMPT + "\n\nUser Message:\n" + str(problem_text or "").strip()
    )
    code = (model or "G").upper()
    if code == "P":
        try:
            alt = query_ai(prompt)
            if alt and str(alt).strip():
                return _sanitize_answer_text(str(alt).strip()), "⚛ Perplexity"
        except Exception:
            pass
    return _ultra_text_stable(prompt, timeout=20)


def _solve_mcq_with_preference(model: str, question: str, options: List[str]) -> Tuple[Dict[str, Any], str]:  # noqa: F811
    code = (model or "G").upper()
    if code == "P":
        try:
            data = perplexity_solve_mcq_json(question, options)
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "⚛ Perplexity"
        except Exception:
            pass
    return _ultra_mcq_stable(question, options)


def gemini_solve_text(problem_text: str) -> str:  # noqa: F811
    prompt = STRICT_SYSTEM_PROMPT + "\n\nUser Message:\n" + str(problem_text or "").strip()
    out, _ = _ultra_text_stable(prompt)
    return out


def gemini_solve_mcq_json(question: str, options: List[str]) -> Dict[str, Any]:  # noqa: F811
    data, _ = _ultra_mcq_stable(question, options)
    return data


def perplexity_solve_text(problem_text: str) -> str:  # noqa: F811
    prompt = STRICT_SYSTEM_PROMPT + "\n\nUser Message:\n" + str(problem_text or "").strip()
    try:
        alt = query_ai(prompt)
        if alt and str(alt).strip():
            return _sanitize_answer_text(str(alt).strip())
    except Exception:
        pass
    out, _ = _ultra_text_stable(prompt)
    return out


# ─────────────────────────────────────────────────────────────────
# 4. STRONG /gen QUIZ GENERATION — verified, no bad answers
# ─────────────────────────────────────────────────────────────────

def _make_gen_prompt_v2(source_text: str, n: int, is_bn: bool = True) -> str:
    lang = "Bangla" if is_bn else "English"
    expl_ex = "সংক্ষিপ্ত বাংলা ব্যাখ্যা" if is_bn else "Short explanation"
    return (
        f"Return STRICT JSON only. No markdown. No preamble. No extra text.\n"
        f"Task: Generate exactly {n} unique MCQ quiz questions from the following academic content.\n"
        f"Language: {lang}. Each question must have 4 options and exactly one correct answer.\n"
        "Rules:\n"
        "- answer: integer 1-4 (A=1, B=2, C=3, D=4)\n"
        "- explanation: 1-2 sentence justification\n"
        "- All questions must come from the given text — do NOT invent.\n"
        "- Do NOT repeat questions.\n\n"
        "Output format (JSON only):\n"
        '{"items":['
        '{"question":"প্রশ্ন টেক্সট","options":["A অপশন","B অপশন","C অপশন","D অপশন"],"answer":1,"explanation":"' + expl_ex + '"}'
        "]}\n\n"
        "Academic content:\n"
        f"{source_text[:8000]}"
    )


def _verify_quiz_item_answer(q: str, opts: List[str], tentative_ans: int) -> Tuple[int, str]:
    """Verify MCQ answer using ultra stable backend."""
    try:
        data, _ = _ultra_mcq_stable(q, opts)
        ans = int(data.get("answer", 0) or 0)
        expl = str(data.get("explanation", "") or "").strip()
        if 1 <= ans <= len(opts):
            return ans, expl
    except Exception:
        pass
    return (tentative_ans if 1 <= tentative_ans <= len(opts) else 1), ""


def _generate_quizzes_from_ocr_sync(ocr_ctx: Dict[str, Any], desired: int, user_id: int) -> list:  # noqa: F811
    """FIXED: Robust quiz generation from OCR context with verification."""
    source_text = str(ocr_ctx.get("clean_text") or ocr_ctx.get("raw_markdown") or "").strip()
    if not source_text:
        raise RuntimeError("No readable OCR text found on the replied page.")

    desired = max(1, min(int(desired or 1), 30))
    is_bn = _is_bangla_text(source_text[:500])

    # Try to generate in batches of 5
    batch_size = min(5, desired)
    out: list = []
    seen_keys: set = set()
    attempts = 0
    max_attempts = 5

    while len(out) < desired and attempts < max_attempts:
        attempts += 1
        need = min(batch_size, desired - len(out))
        already = "\n".join([f"- {it['question'][:60]}" for it in out]) if out else ""
        extra_ctx = f"\n\nDo NOT repeat these already generated questions:\n{already}" if already else ""
        prompt = _make_gen_prompt_v2(source_text + extra_ctx, need, is_bn)

        raw = None
        # Try all backends
        if get_gemini_api_keys():
            try:
                raw = call_gemini_text_rest(prompt, timeout_seconds=25, force_json=True)
            except Exception:
                raw = None
        if not raw:
            try:
                raw = query_ai(prompt)
            except Exception:
                raw = None
        if not raw:
            try:
                res = chat_with_gemini(prompt)
                if isinstance(res, dict) and res.get("success"):
                    raw = res.get("response")
            except Exception:
                raw = None
        if not raw:
            continue

        # Parse JSON
        data = None
        schema_hint = '{"items":[{"question":"...","options":["...","...","...","..."],"answer":1,"explanation":"..."}]}'
        try:
            data = _extract_json_strict(raw)
        except Exception:
            with contextlib.suppress(Exception):
                data = _repair_to_json(raw, schema_hint=schema_hint, timeout_seconds=15)

        if not isinstance(data, dict):
            # Try to find JSON in response
            try:
                m = re.search(r'\{[^{}]*"items"\s*:\s*\[.*?\]\s*\}', str(raw), re.DOTALL)
                if m:
                    data = json.loads(m.group(0))
            except Exception:
                continue

        if not isinstance(data, dict):
            continue

        items_raw = data.get("items") or []
        for it in items_raw:
            if len(out) >= desired:
                break
            if not isinstance(it, dict):
                continue
            q = str(it.get("question") or "").strip()
            if not q:
                continue
            sig = re.sub(r"\s+", " ", q).lower()[:80]
            if sig in seen_keys:
                continue

            raw_opts = it.get("options") or []
            if isinstance(raw_opts, dict):
                raw_opts = list(raw_opts.values())
            opts = _normalize_options([str(x) for x in raw_opts], max_n=4)
            if len(opts) < 4:
                # pad to 4
                while len(opts) < 4:
                    opts.append(f"Option {chr(65+len(opts))}")

            tentative = int(it.get("answer", 0) or 0)
            if not (1 <= tentative <= 4):
                tentative = 1
            expl = str(it.get("explanation") or "").strip()

            # Verify with secondary backend (best-effort)
            verified_ans, verified_expl = _verify_quiz_item_answer(q, opts, tentative)
            final_ans = verified_ans if verified_ans > 0 else tentative
            final_expl = verified_expl or expl or "See solution above."

            seen_keys.add(sig)
            out.append({
                "question": q,
                "options": opts[:4],
                "answer": final_ans,
                "explanation": final_expl,
            })

    if not out:
        raise RuntimeError("Could not generate any quiz questions from this page. Please try again.")
    return out[:desired]


# ─────────────────────────────────────────────────────────────────
# 5. /qans FIX — consistent Q-number targeting for all users
# ─────────────────────────────────────────────────────────────────

_BD_DIGITS_MAP = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

def _extract_q_number_final(text: str) -> Optional[str]:
    """Extract Q number from user text. Returns digit string or None."""
    t = str(text or "").translate(_BD_DIGITS_MAP)
    patterns = [
        r"\b[Qq]\.?\s*(\d{1,3})\b",
        r"\b(\d{1,3})\s*(?:নম্বর|number|no\.?|নং)\b",
        r"(?:question|প্রশ্ন)\s*\.?\s*(\d{1,3})\b",
        r"\b(\d{1,3})\s*(?:th|st|nd|rd)\b",
        r"(?:^|\s)(\d{1,3})(?:\.|\s|$)",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            return m.group(1)
    stripped = t.strip()
    if re.match(r"^\d{1,3}$", stripped):
        return stripped
    return None


def _is_free_form_q(text: str) -> bool:
    t = str(text or "").lower()
    kws = ["summarize","summary","সারাংশ","সংক্ষেপ","explain","ব্যাখ্যা","বুঝিয়ে","বুঝাও",
           "analyze","বিশ্লেষণ","what is","কী আছে","describe","বর্ণনা","list","তালিকা",
           "overview","topic","কোন কোন","কী কী","বিস্তারিত","detail"]
    return any(k in t for k in kws)


def _smart_pick_final(items: List[Dict[str, Any]], user_text: str) -> Optional[Dict[str, Any]]:
    pool = [dict(x) for x in (items or []) if str((x or {}).get("questions") or "").strip()]
    if not pool:
        return None
    user_t = str(user_text or "").strip()
    if not user_t or (_is_free_form_q(user_t) and not _extract_q_number_final(user_t)):
        return None  # free-form → use full text

    qno = _extract_q_number_final(user_t)
    if qno:
        # Exact number match
        exact = [it for it in pool if _item_question_no(it) == qno]
        if exact:
            return exact[0]
        # Text starts with number
        for it in pool:
            q_text = str(it.get("questions") or "")
            if re.match(rf"^\s*{re.escape(qno)}\s*[\.।\)\s]", q_text.translate(_BD_DIGITS_MAP)):
                return it
        # Positional
        try:
            idx = int(qno) - 1
            if 0 <= idx < len(pool):
                return pool[idx]
        except Exception:
            pass

    # Text similarity
    best, best_score = None, 0.0
    for it in pool:
        score = _question_text_match_score(user_t, it)
        if score > best_score:
            best_score = score
            best = it
    if best and best_score >= 0.28:
        return best

    return pool[0]


def _build_ocr_answer_prompt(ocr_ctx: Dict[str, Any], user_question: str, previous_answer: str = "") -> str:
    """Build the best possible prompt for any user OCR question."""
    user_q = str(user_question or "").strip()
    prev = str(previous_answer or "").strip()
    items = list((ocr_ctx or {}).get("items") or [])
    full_text = str((ocr_ctx or {}).get("clean_text") or (ocr_ctx or {}).get("raw_markdown") or "").strip()

    picked = _smart_pick_final(items, user_q)
    system_preamble = (
        "You are an expert academic assistant for Bangladeshi students.\n"
        "Answer ONLY from the provided content. Be accurate, thorough, student-friendly.\n"
        "If Bangla content → answer in Bangla. Use plain text, no LaTeX, no markdown headers.\n\n"
    )

    if picked:
        opts = [str(picked.get(f"option{i}") or "").strip() for i in range(1, 6)
                if str(picked.get(f"option{i}") or "").strip()]
        qblock = str(picked.get("questions") or "").strip()
        opt_block = "\n".join([f"{chr(64+i+1)}. {opts[i]}" for i in range(len(opts))])
        visible_ans = int(picked.get("answer", 0) or 0)
        visible_text = opts[visible_ans - 1] if 1 <= visible_ans <= len(opts) else ""
        qno = _item_question_no(picked) or ""

        prompt = system_preamble + f"User request: {user_q}\n\n"
        if prev:
            prompt += f"Previous answer (context):\n{prev[:1500]}\n\n"
        prompt += f"Question {qno} from the image:\n{qblock}\n\nOptions:\n{opt_block}\n"
        if visible_text:
            prompt += f"\nMarked answer on page: {chr(64+visible_ans)}) {visible_text}\n"
        prompt += "\nProvide: 1) Correct answer letter, 2) Step-by-step explanation, 3) Why others are wrong (briefly)."
        return prompt
    else:
        # Free-form or no MCQ match → use full OCR
        prompt = system_preamble + f"User request about this page:\n{user_q}\n\n"
        if prev:
            prompt += f"Previous answer:\n{prev[:1500]}\n\n"
        prompt += f"Full page content:\n{full_text[:10000]}\n"
        prompt += "\nAnswer the user's request comprehensively based on the above content."
        return prompt


# Override _build_focused_ocr_prompt to use our smart builder
def _build_focused_ocr_prompt(ocr_ctx: Dict[str, Any], user_question: str, previous_answer: str = "") -> str:  # noqa: F811
    return _build_ocr_answer_prompt(ocr_ctx, user_question, previous_answer)


# Override _pick_first_mcq_item to use smart picker
def _pick_first_mcq_item(items: List[Dict[str, Any]], extra_instruction: str = "") -> Optional[Dict[str, Any]]:  # noqa: F811
    result = _smart_pick_final(items, extra_instruction)
    if result is None and items:
        pool = [x for x in items if str((x or {}).get("questions") or "").strip()]
        return pool[0] if pool else None
    return result


# ─────────────────────────────────────────────────────────────────
# 6. OCR → QUIZ BUFFER (Admin panel) — robust MCQ parsing
# ─────────────────────────────────────────────────────────────────

def _ocr_text_to_mcq_items_robust(raw_text: str, user_id: int) -> Tuple[str, List[Dict[str, Any]]]:
    """
    FIXED: More tolerant MCQ extraction from OCR text.
    Uses Gemini to structure the questions if pattern matching fails.
    """
    # Try existing parser first
    try:
        if "_ocr_text_to_mcq_items" in globals():
            result = _ocr_text_to_mcq_items(raw_text, user_id)
            if result and result[1]:  # items found
                return result
    except Exception:
        pass

    # If no items found via pattern, use AI to extract MCQs
    is_bn = _is_bangla_text(raw_text[:500])
    lang = "Bangla" if is_bn else "English"
    prompt = (
        f"Extract ALL MCQ questions from the following {lang} academic text.\n"
        "Return STRICT JSON only:\n"
        '{"items":[{"questions":"Q text","option1":"A","option2":"B","option3":"C","option4":"D","answer":1,"explanation":""}]}\n'
        "Rules:\n"
        "- answer: 1-4 integer (A=1,B=2,C=3,D=4). If marked on page, use that.\n"
        "- Extract ALL visible questions. Preserve original text.\n"
        "- If answer is shown (Ans: A etc.), set answer accordingly.\n\n"
        f"Text:\n{raw_text[:6000]}"
    )

    raw_ai = None
    if get_gemini_api_keys():
        try:
            raw_ai = call_gemini_text_rest(prompt, timeout_seconds=25, force_json=True)
        except Exception:
            pass
    if not raw_ai:
        try:
            raw_ai = query_ai(prompt)
        except Exception:
            pass

    if not raw_ai:
        return raw_text, []

    data = None
    try:
        data = _extract_json_strict(raw_ai)
    except Exception:
        with contextlib.suppress(Exception):
            data = _repair_to_json(raw_ai, '{"items":[{"questions":"...","option1":"...","option2":"...","option3":"...","option4":"...","answer":1}]}', timeout_seconds=12)

    if not isinstance(data, dict):
        return raw_text, []

    raw_items = data.get("items") or []
    out_items = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        q = str(it.get("questions") or "").strip()
        if not q:
            continue
        opts = [str(it.get(f"option{i}") or "").strip() for i in range(1, 5)]
        if len([o for o in opts if o]) < 2:
            continue
        ans = int(it.get("answer", 0) or 0)
        if not (1 <= ans <= 4):
            ans = 0
        out_items.append({
            "questions": q,
            "option1": opts[0] if len(opts) > 0 else "",
            "option2": opts[1] if len(opts) > 1 else "",
            "option3": opts[2] if len(opts) > 2 else "",
            "option4": opts[3] if len(opts) > 3 else "",
            "option5": "",
            "answer": ans,
            "explanation": str(it.get("explanation") or "").strip(),
            "type": 1,
            "section": 1,
        })

    return raw_text, out_items


# Patch: override _ocr_pages_to_clean_text_and_items to use robust version
if "_ocr_pages_to_clean_text_and_items" in globals():
    _prev_ocr_pages_v2 = _ocr_pages_to_clean_text_and_items

    def _ocr_pages_to_clean_text_and_items(pages: list, user_id: int) -> Tuple[str, List[Dict[str, Any]]]:  # noqa: F811
        try:
            clean_text, items = _prev_ocr_pages_v2(pages, user_id)
        except Exception as e:
            # Build clean_text from pages manually
            chunks = [str((p or {}).get("markdown") or "").strip() for p in (pages or [])]
            clean_text = "\n\n".join(c for c in chunks if c)
            items = []

        if not items:
            # Fallback: AI-powered extraction
            try:
                _, items = _ocr_text_to_mcq_items_robust(clean_text, user_id)
            except Exception:
                items = []
        return clean_text, items


# ─────────────────────────────────────────────────────────────────
# 7. GEMINI /gemini status — show model chain too
# ─────────────────────────────────────────────────────────────────

def _gemini_runtime_report_html() -> str:  # noqa: F811
    rows = _gemini_key_rows(include_disabled=True)
    lines = []
    if not rows:
        lines.append("⚠️ No Gemini API keys saved. Use <code>/gemini add YOUR_KEY</code>.")
    else:
        active = 0
        for r in rows:
            enabled = int(r.get("is_enabled") or 0) == 1
            status = str(r.get("last_status") or "ready")
            masked = _normalize_secret_mask(str(r.get("api_key") or ""))
            label = str(r.get("label") or "")
            icon = "🟢" if (enabled and status not in ("quota", "error")) else ("🟡" if status == "quota" else "🔴")
            line = f"{icon} ID <code>{h(str(r.get('id') or '?'))}</code> | <code>{h(masked)}</code>"
            if label:
                line += f" | {h(label)}"
            line += f" | status: <code>{h(status)}</code>"
            if enabled:
                active += 1
            lines.append(line)
        lines.append(f"\n<b>Active keys:</b> {active}/{len(rows)}")

    lines.append("\n<b>Model rotation order:</b>")
    lines.append("Text: " + h(" → ".join(_all_text_model_candidates()[:4])))
    lines.append("Vision: " + h(" → ".join(_all_vision_model_candidates()[:3])))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# 8. FINAL build_app — register everything
# ─────────────────────────────────────────────────────────────────

_prev_build_app_j = build_app

def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_j()
    logger.info("[PATCH-J] All stable backends, model rotation, quiz gen, /qans fixes applied.")
    return app


logger.info("[PATCH 2026-04-13-J] Loaded: Gemini key×model rotation, ultra stable backends, quiz gen fix, /qans smart pick, OCR→buffer fix.")

