# ──────────────────────────────────────────────────────────────────────────────
# Section: 36_ai_stability_04_12e
# Original lines: 19933..20082
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== AI STABILITY PATCH 2026-04-12-E =====
# Goals:
# 1) gemini3_solve: 429/rate-limit errors silently skipped, fallback continues
# 2) Perplexity tried before Gemini3 web scraping
# 3) User sees friendly Bangla error, no raw HTTP 429 codes
# 4) /qans + all model buttons work reliably
# =============================================

def _gemini3_solve_safe(prompt: str) -> "Optional[str]":
    """Wrapper: returns response string or None (never raises, never surfaces 429)."""
    try:
        res = chat_with_gemini(prompt)
        if not isinstance(res, dict):
            return None
        if res.get("success") and res.get("response"):
            return str(res["response"]).strip() or None
        err_msg = str(res.get("error") or "").lower()
        if any(k in err_msg for k in ("429", "rate", "quota", "exhausted", "limit", "http 4")):
            logger.debug("[Gemini3] Rate-limited/unavailable, skipping silently: %s", err_msg[:80])
            return None
        return None
    except Exception as e:
        logger.debug("[Gemini3] Exception (suppressed): %s", e)
        return None


def _query_ai_safe(prompt: str) -> "Optional[str]":
    """Perplexity with safe error handling. Returns None on any failure."""
    if not USE_PERPLEXITY_FALLBACK:
        return None
    try:
        result = query_ai(prompt)
        return result if result and str(result).strip() else None
    except Exception as e:
        logger.debug("[Perplexity] Error (suppressed): %s", e)
        return None


def _try_ai_text_stable(prompt: str, *, timeout_seconds: int = 20) -> "Tuple[str, str]":
    """
    Stable text backend chain:
      1) Gemini REST (if API key set)
      2) Perplexity HTTP
      3) Gemini3 web (429 silently ignored)
    Raises RuntimeError with Bangla-friendly message only if ALL fail.
    """
    # 1) Gemini REST
    if GEMINI_API_KEY:
        try:
            out = call_gemini_text_rest(prompt, timeout_seconds=timeout_seconds)
            if out and str(out).strip():
                return str(out).strip(), "Gemini"
        except Exception as e:
            logger.debug("[GeminiREST text] %s", e)

    # 2) Perplexity
    alt = _query_ai_safe(prompt)
    if alt:
        return alt, "Perplexity"

    # 3) Gemini3 web
    g3 = _gemini3_solve_safe(prompt)
    if g3:
        return g3, "Gemini Web"

    raise RuntimeError("AI সাময়িকভাবে অনুপলব্ধ। কিছুক্ষণ পর আবার চেষ্টা করুন।")


def _try_ai_mcq_stable(question: str, options: "List[str]") -> "Tuple[Dict[str, Any], str]":
    """
    Stable MCQ backend chain. Returns (result_dict, model_name).
    Priority: Gemini REST → Perplexity → Gemini3 web
    """
    try:
        prompt, opts = _build_mcq_json_prompt(question, options)
    except Exception as e:
        raise RuntimeError(f"MCQ prompt failed: {e}")

    # 1) Gemini REST
    if GEMINI_API_KEY:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=20, force_json=True)
            data = _extract_json_strict(raw)
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "Gemini"
        except Exception as e:
            logger.debug("[GeminiREST MCQ] %s", e)

    # 2) Perplexity
    alt = _query_ai_safe(prompt)
    if alt:
        try:
            data = _extract_json_strict(alt)
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "Perplexity"
        except Exception:
            pass
        inferred = _infer_option_from_text(alt, len(options))
        return {"answer": inferred, "confidence": 0, "explanation": str(alt)[:1800], "why_not": {}}, "Perplexity"

    # 3) Gemini3 web
    g3 = _gemini3_solve_safe(prompt)
    if g3:
        try:
            data = _extract_json_strict(g3)
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "Gemini Web"
        except Exception:
            pass
        inferred = _infer_option_from_text(g3, len(options))
        return {"answer": inferred, "confidence": 0, "explanation": str(g3)[:1800], "why_not": {}}, "Gemini Web"

    raise RuntimeError("সকল AI ব্যাকএন্ড সাময়িকভাবে অনুপলব্ধ। কিছুক্ষণ পর আবার চেষ্টা করুন।")


def _solve_mcq_with_preference_e(model: str, question: str, options: "List[str]") -> "Tuple[Dict[str, Any], str]":
    """Stable MCQ solver — overrides previous versions. model: G/P/D."""
    model = (model or "G").upper()
    if model == "P":
        try:
            return perplexity_solve_mcq_json(question, options), "Perplexity"
        except Exception:
            pass
        return _try_ai_mcq_stable(question, options)
    if model == "D":
        try:
            return deepseek_solve_mcq_json(question, options), "DeepSeek"
        except Exception:
            pass
        return _try_ai_mcq_stable(question, options)
    return _try_ai_mcq_stable(question, options)


# ── Override unstable functions with stable versions ──
_solve_mcq_with_preference = _solve_mcq_with_preference_e

def gemini_solve_text(problem_text: str) -> str:  # noqa: F811  # type: ignore[no-redef]
    prompt = STRICT_SYSTEM_PROMPT + "\n\nUser Message:\n" + (problem_text or "").strip()
    out, _ = _try_ai_text_stable(prompt, timeout_seconds=20)
    return out

def gemini_solve_mcq_json(question: str, options: "List[str]") -> "Dict[str, Any]":  # noqa: F811  # type: ignore[no-redef]
    data, _ = _try_ai_mcq_stable(question, options)
    return data

logger.info("[AI STABILITY PATCH 2026-04-12-E] Stable routing active: REST→Perplexity→Gemini3web. 429 silently skipped. Friendly errors enabled.")

# ===== END AI STABILITY PATCH 2026-04-12-E =====


