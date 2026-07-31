# ──────────────────────────────────────────────────────────────────────────────
# Section 74 (2026-06-15) — real generation-path speed/zero-result fix.
# Additive overlay only; OCR/source-post/export/Mongo logic is left untouched.
#
# Fixes:
#   • /advmode providers are tried BEFORE old Gemini/Perplexity defaults.
#   • Recently failing providers are skipped briefly instead of retried every
#     generation round, which was causing 2–4 minute waits.
#   • OpenAI-compatible JSON mode now retries without response_format when a
#     provider rejects it, so Mistral/Cohere/NVIDIA-style endpoints don't yield
#     empty output.
#   • .gen direct flow and inline Generate buttons now use the SAME fast,
#     robust generator/parser.
#   • If OCR has source MCQs, generation uses them only as topic/concept hints;
#     it explicitly avoids copying source questions/options.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx74
import json as _json74
import re as _re74
import time as _time74
import requests as _requests74


_FAST_ADV_KINDS_74 = {
    "openai_compat", "groq", "openrouter", "mistral_chat", "cohere", "nvidia",
    "together", "fireworks", "deepseek", "xai", "cerebras", "sambanova",
}
_SLOW_BUILTIN_KINDS_74 = {"gemini_rest", "gemini_web", "perplexity"}


def _provider_defaults_74(kind: str):
    return (globals().get("_PROVIDER_DEFAULTS_71") or {}).get(kind, {}) or {}


def _provider_sort_key_74(prov):
    kind = str((prov or {}).get("kind") or "").lower()
    # User-added API-key providers first; old built-ins last.
    slow = 1 if kind in _SLOW_BUILTIN_KINDS_74 else 0
    no_key_fast = 1 if (kind in _FAST_ADV_KINDS_74 and not (prov.get("api_key") or "")) else 0
    return (slow, no_key_fast, int((prov or {}).get("priority") or 100), int((prov or {}).get("id") or 0))


def _adv_call_openai_compat(prov, prompt, *, force_json, timeout):  # noqa: F811
    """OpenAI-compatible call with JSON-mode compatibility fallback."""
    kind = str((prov or {}).get("kind") or "").lower()
    base = str((prov or {}).get("base_url") or _provider_defaults_74(kind).get("base") or "").rstrip("/")
    if not base:
        raise RuntimeError("base_url missing")
    key = str((prov or {}).get("api_key") or "")
    if not key:
        raise RuntimeError("api_key missing")
    model = str((prov or {}).get("model") or _provider_defaults_74(kind).get("model") or "llama-3.1-8b-instant")
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    # 15–18s is the practical sweet spot: enough for Mistral/Cohere/NVIDIA JSON
    # completions, still far below the old multi-minute stall.
    per_timeout = max(6, min(int(timeout or 18), 18))

    def _post(use_json_mode: bool):
        messages = [{"role": "user", "content": prompt}]
        if not use_json_mode:
            messages.insert(0, {"role": "system", "content": "Return STRICT valid JSON only. No markdown."})
        payload = {"model": model, "messages": messages, "temperature": 0.1, "max_tokens": 4096}
        if use_json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        return _requests74.post(url, json=payload, headers=headers, timeout=per_timeout)

    r = _post(bool(force_json))
    # Some providers are OpenAI-compatible but reject response_format. Retry once
    # without it; 400/422 responses are immediate, so this does not add minutes.
    if force_json and r.status_code in (400, 422) and _re74.search(r"response_format|json_object|schema", r.text or "", _re74.I):
        r = _post(False)
    if r.status_code != 200:
        body = (r.text or "")[:300]
        if _adv_is_quota_err(f"{r.status_code} {body}"):  # type: ignore[name-defined]
            raise RateLimitError(f"HTTP {r.status_code}: {body}")  # type: ignore[name-defined]
        raise RuntimeError(f"HTTP {r.status_code}: {body}")
    data = r.json()
    with _cx74.suppress(Exception):
        return str(data["choices"][0]["message"]["content"] or "").strip()
    with _cx74.suppress(Exception):
        return str(data["message"]["content"] or data["text"] or "").strip()
    return ""


globals()["_adv_call_openai_compat"] = _adv_call_openai_compat


def _adv_call_text(prompt, *, force_json=False, timeout=18):  # noqa: F811
    """Fast cascade: fresh rows, user providers first, short cooldown for failures."""
    per = max(6, min(int(timeout or 18), 18))
    now = _time74.time()
    rows = []
    with _cx74.suppress(Exception):
        rows = list(_adv_load() or [])  # type: ignore[name-defined]
    if not rows:
        rows = list((globals().get("_ADV_MEM_CACHE") or {}).get("rows") or [])
    rows = sorted(rows, key=_provider_sort_key_74)
    last_err = None
    delayed = []

    for prov in rows:
        if not prov.get("enabled"):
            continue
        age = now - float(prov.get("last_error_ts") or 0)
        if not prov.get("healthy") and age < 480:
            continue
        if prov.get("healthy") and prov.get("last_error") and age < 45:
            delayed.append(prov)
            continue
        try:
            out = _adv_call_provider(prov, prompt, force_json=force_json, timeout=per)  # type: ignore[name-defined]
            if out and str(out).strip():
                _adv_mark_success(prov)  # type: ignore[name-defined]
                return str(out).strip(), str(prov.get("name") or prov.get("kind"))
            _adv_mark_failure(prov, "empty response", quota=False)  # type: ignore[name-defined]
        except RateLimitError as e:  # type: ignore[name-defined]
            last_err = e
            _adv_mark_failure(prov, str(e), quota=True)  # type: ignore[name-defined]
        except Exception as e:
            last_err = e
            _adv_mark_failure(prov, str(e), quota=_adv_is_quota_err(str(e)))  # type: ignore[name-defined]

    # If every candidate was just delayed, try at most two of them as a last shot.
    for prov in delayed[:2]:
        try:
            out = _adv_call_provider(prov, prompt, force_json=force_json, timeout=per)  # type: ignore[name-defined]
            if out and str(out).strip():
                _adv_mark_success(prov)  # type: ignore[name-defined]
                return str(out).strip(), str(prov.get("name") or prov.get("kind"))
        except Exception as e:
            last_err = e
    raise RuntimeError(str(last_err) if last_err else "All providers failed")


globals()["_adv_call_text"] = _adv_call_text


def _json_items_74(raw):
    text = str(raw or "").strip()
    if not text:
        return []
    text = _re74.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=_re74.I | _re74.S).strip()
    data = None
    for parser in (
        lambda s: _extract_json_strict(s),  # type: ignore[name-defined]
        lambda s: _json74.loads(_re74.search(r"\{.*\}", s, _re74.S).group(0)),
        lambda s: _json74.loads(_re74.search(r"\[.*\]", s, _re74.S).group(0)),
    ):
        try:
            data = parser(text)
            break
        except Exception:
            data = None
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("items", "mcqs", "questions", "quizzes", "data"):
        val = data.get(key)
        if isinstance(val, list):
            return val
    return []


def _answer_to_int_74(value, opts, *, zero_based=False):
    try:
        n = int(value)
        if zero_based and 0 <= n < len(opts):
            return n + 1
        if 1 <= n <= len(opts):
            return n
    except Exception:
        pass
    s = str(value or "").strip()
    if not s:
        return 0
    m = _re74.search(r"(?:option\s*)?([A-E])\b", s, _re74.I)
    if m:
        n = ord(m.group(1).upper()) - 64
        if 1 <= n <= len(opts):
            return n
    for ch, n in {"ক": 1, "খ": 2, "গ": 3, "ঘ": 4, "ঙ": 5}.items():
        if ch in s and n <= len(opts):
            return n
    sl = _re74.sub(r"\s+", " ", s).lower()
    for i, opt in enumerate(opts, start=1):
        ol = _re74.sub(r"\s+", " ", str(opt or "")).lower()
        if ol and (sl == ol or sl in ol or ol in sl):
            return i
    return 0


def _normalise_mcq_74(it):
    if not isinstance(it, dict):
        return None
    q = str(it.get("question") or it.get("questions") or it.get("q") or it.get("stem") or "").strip()
    if not q or len(q) < 4:
        return None
    raw_opts = it.get("options") or it.get("choices") or []
    if isinstance(raw_opts, dict):
        raw_opts = [raw_opts.get(k) for k in sorted(raw_opts.keys())]
    if not isinstance(raw_opts, list):
        raw_opts = []
    opts = [str(x or "").strip() for x in raw_opts if str(x or "").strip()]
    if len(opts) < 2:
        opts = [str(it.get(f"option{i}") or "").strip() for i in range(1, 6)]
        opts = [x for x in opts if x]
    opts = opts[:5]
    if len(opts) < 2:
        return None
    ans = 0
    if "correct_option_id" in it:
        ans = _answer_to_int_74(it.get("correct_option_id"), opts, zero_based=True)
    for key in ("answer", "correct", "correct_answer", "correctOption", "correct_option", "correct_option_text"):
        if not ans and key in it:
            ans = _answer_to_int_74(it.get(key), opts)
    if not (1 <= ans <= len(opts)):
        ans = 1
    expl = str(it.get("explanation") or it.get("reason") or it.get("solution") or "").strip()
    with _cx74.suppress(Exception):
        expl = _adv_strip_latex_for_telegram(expl)  # type: ignore[name-defined]
    return {"question": q, "options": opts, "answer": ans, "explanation": expl[:200]}


def _source_avoid_text_74(ocr_ctx_or_text):
    items = []
    if isinstance(ocr_ctx_or_text, dict):
        items = list(ocr_ctx_or_text.get("items") or ocr_ctx_or_text.get("source_items") or [])
    lines = []
    for it in items[:30]:
        q = str((it or {}).get("questions") or (it or {}).get("question") or "").strip()
        if q:
            lines.append("- " + q[:160])
    return "\n".join(lines)


def _make_fast_new_mcq_prompt_74(source_text, n, *, easy=0, medium=0, hard=0, avoid_text=""):
    diff = f"easy={easy}, medium={medium}, hard={hard}" if (easy + medium + hard) > 0 else f"total={n}"
    return (
        "Return STRICT compact JSON only. No markdown.\n"
        f"Create exactly {int(n)} NEW unique MCQs from the topics/concepts in the source. Counts: {diff}.\n"
        "Same language as source (Bangla/English/mixed). Use readable Unicode math (√, ², ₁), no raw LaTeX.\n"
        "If the source contains existing MCQs, DO NOT copy, reuse, or lightly rephrase those source questions/options. "
        "Infer the underlying topic and make different new exam-quality questions.\n"
        "Each item needs 4 options and one correct answer. answer may be 1-4.\n"
        "JSON schema: {\"items\":[{\"question\":\"...\",\"options\":[\"...\",\"...\",\"...\",\"...\"],\"answer\":1,\"explanation\":\"short\"}]}\n"
        + (f"\nSOURCE QUESTIONS TO AVOID COPYING:\n{avoid_text[:2500]}\n" if avoid_text else "")
        + f"\nSOURCE/TOPICS:\n{str(source_text or '')[:9000]}"
    )


def _generate_batch_fast_74(source_text, need, *, easy=0, medium=0, hard=0, avoid_text=""):
    prompt = _make_fast_new_mcq_prompt_74(source_text, need, easy=easy, medium=medium, hard=hard, avoid_text=avoid_text)
    raw = ""
    try:
        raw, _used = _adv_call_text(prompt, force_json=True, timeout=18)
    except Exception as e:
        db_log("WARN", "fast_gen_adv_failed_74", {"error": str(e)[:180]})  # type: ignore[name-defined]
        return []
    out = []
    for item in _json_items_74(raw):
        norm = _normalise_mcq_74(item)
        if norm:
            out.append(norm)
    return out


def _generate_quizzes_from_ocr_sync(ocr_ctx, desired, user_id):  # noqa: F811
    source_text = str((ocr_ctx or {}).get("clean_text") or (ocr_ctx or {}).get("raw_markdown") or "").strip()
    if not source_text:
        raise RuntimeError("No readable OCR text found on this page.")
    desired = max(1, min(int(desired or 1), 200))
    avoid = _source_avoid_text_74(ocr_ctx)
    out, seen = [], set()
    batch = 15 if desired > 20 else min(10, desired)
    rounds = max(1, min(6, (desired + batch - 1) // batch + 1))
    for _ in range(rounds):
        if len(out) >= desired:
            break
        need = min(batch, desired - len(out))
        recent = "\n".join("- " + x["question"][:140] for x in out[-20:])
        items = _generate_batch_fast_74(source_text, need, avoid_text=(avoid + "\n" + recent).strip())
        if not items:
            break
        for it in items:
            sig = _re74.sub(r"\s+", " ", it["question"]).lower()[:100]
            if sig in seen:
                continue
            seen.add(sig)
            out.append(it)
            if len(out) >= desired:
                break
    if not out:
        raise RuntimeError("All active AI providers returned invalid/empty quiz JSON.")
    return out[:desired]


globals()["_generate_quizzes_from_ocr_sync"] = _generate_quizzes_from_ocr_sync


def _generate_mcqs_from_content(content_text, *, easy, medium, hard):  # noqa: F811
    total = max(0, int(easy or 0) + int(medium or 0) + int(hard or 0))
    if total <= 0 or not str(content_text or "").strip():
        return []
    items = _generate_batch_fast_74(
        str(content_text or ""),
        min(total, 30),
        easy=int(easy or 0), medium=int(medium or 0), hard=int(hard or 0),
        avoid_text="Existing/source MCQs in the text must not be copied or lightly rephrased.",
    )
    out = []
    for it in items[:total]:
        opts = list(it.get("options") or [])[:5]
        row = {"questions": it["question"], "answer": int(it.get("answer") or 1),
               "explanation": str(it.get("explanation") or "")[:200], "type": 1, "section": 1}
        for i in range(5):
            row[f"option{i+1}"] = opts[i] if i < len(opts) else ""
        out.append(row)
    return out


globals()["_generate_mcqs_from_content"] = _generate_mcqs_from_content


async def _generate_to_buffer_59(update, context, ocr_ctx, uid, count, mode="std"):  # noqa: F811
    """Direct .gen buffer writer; do not let old per-source seen cache ghost new attempts."""
    count = max(1, min(500, int(count or 20)))
    globals()["_active_gen_mode_57"] = mode or "std"
    try:
        items = await _run_blocking(  # type: ignore[name-defined]
            _role_of(uid), _generate_quizzes_from_ocr_sync,  # type: ignore[name-defined]
            ocr_ctx, count, uid, timeout=max(35, min(160, count * 4)),
        )
    except Exception as e:
        db_log("WARN", "direct_gen_failed_74", {"user_id": int(uid), "error": str(e)[:200]})  # type: ignore[name-defined]
        items = []
    finally:
        globals()["_active_gen_mode_57"] = None

    seen, added, dup = set(), 0, 0
    with _cx74.suppress(Exception):
        for _, it in (buffer_list(uid, limit=99999) or []):  # type: ignore[name-defined]
            seen.add(_fp_question(it))  # type: ignore[name-defined]
    for raw in items or []:
        try:
            q = str(raw.get("question") or raw.get("questions") or "").strip()
            opts = raw.get("options") if isinstance(raw.get("options"), list) else _opts_59(raw)  # type: ignore[name-defined]
            opts = [str(o or "").strip() for o in (opts or []) if str(o or "").strip()][:5]
            ans = int(raw.get("answer", 1) or 1)
            if not q or len(opts) < 2 or not (1 <= ans <= len(opts)):
                continue
            payload = {"questions": q, "answer": ans,
                       "explanation": str(raw.get("explanation") or "")[:200],
                       "type": 1, "section": 1, "source": f"gen_{mode}"}
            for i in range(5):
                payload[f"option{i+1}"] = opts[i] if i < len(opts) else ""
            with _cx74.suppress(Exception):
                payload = _enforce_option_parity(payload)  # type: ignore[name-defined]
            fp = _fp_question(payload)  # type: ignore[name-defined]
            if fp in seen:
                dup += 1
                continue
            if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:  # type: ignore[name-defined]
                break
            if not explain_mode_on(uid):  # type: ignore[name-defined]
                payload["explanation"] = ""
            buffer_add(uid, payload)  # type: ignore[name-defined]
            seen.add(fp)
            added += 1
        except Exception:
            continue
    with _cx74.suppress(Exception):
        _gen_seen_for(context, uid, _source_hash_59(ocr_ctx, mode)).update(seen)  # type: ignore[name-defined]
    return added, dup


globals()["_generate_to_buffer_59"] = _generate_to_buffer_59


with _cx74.suppress(Exception):
    logger.info("[PATCH-74] fast provider-first generation path active; source MCQs are avoid-list only.")  # type: ignore[name-defined]

# ===== END SECTION 74 =====