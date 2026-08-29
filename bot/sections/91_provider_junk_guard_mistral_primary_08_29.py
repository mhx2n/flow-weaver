# ──────────────────────────────────────────────────────────────────────────────
# Section 91 (2026-08-29) — provider junk-reply guard + Mistral advanced rescue.
#
# Problem seen in production: the Gemini-web / Perplexity proxy backends stopped
# answering and started returning login placeholders such as
#     "Sign up and repeat your request."
#     "Sign in to continue."
# Those strings are HTTP-200 successes, so the old cascade accepted them and
# delivered them to the user as the AI answer.
#
# This overlay:
#   1) Detects placeholder / login / quota junk in ANY provider reply.
#   2) Turns such a reply into a failure so the cascade keeps going.
#   3) Adds Mistral (advanced model first) as the guaranteed rescue provider for
#      text answers and MCQ JSON, so the user always gets a real response.
#
# Nothing else is touched: commands, buffers, quiz posting, rich transport and
# the Bangla language locks from sections 77-90 stay exactly as they are.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx91
import re as _re91


def _log91(message: str) -> None:
    with _cx91.suppress(Exception):
        logger.info("[S91] %s", message)  # type: ignore[name-defined]


# ── 1) Junk / placeholder detection ──────────────────────────────────────────

_JUNK_PATTERNS_91 = (
    r"sign\s*up\s+and\s+repeat",
    r"sign\s*(?:up|in)\s+(?:to|and)\b",
    r"please\s+(?:sign|log)\s*(?:in|up)\b",
    r"\blog\s*in\s+to\s+continue\b",
    r"create\s+an?\s+account\s+to\s+continue",
    r"you(?:'| a)?re\s+not\s+signed\s+in",
    r"session\s+(?:expired|invalid)",
    r"unauthori[sz]ed",
    r"authentication\s+(?:required|failed)",
    r"repeat\s+your\s+request",
    r"try\s+again\s+later\s*\.?$",
    r"rate\s*limit(?:ed)?\b",
    r"quota\s+(?:exceeded|exhausted)",
    r"upgrade\s+your\s+plan",
    r"captcha",
    r"^\s*(?:error|failed|null|none|undefined)\s*\.?\s*$",
    r"service\s+(?:temporarily\s+)?unavailable",
    r"<!doctype html|<html",
)

_JUNK_RE_91 = _re91.compile("|".join(_JUNK_PATTERNS_91), _re91.I)


def _is_junk_reply_91(text) -> bool:
    """True when a provider returned a placeholder instead of a real answer."""
    body = str(text or "").strip()
    if not body:
        return True
    # Long, substantial answers are trusted even if they mention these words.
    head = body[:400]
    if _JUNK_RE_91.search(head) and len(body) < 900:
        return True
    if len(body) < 12 and not _re91.search(r"[0-9\u0980-\u09FF]", body):
        return True
    return False


globals()["_is_junk_reply_91"] = _is_junk_reply_91


def _guard_text_provider_91(name: str, fn):
    """Wrap a text provider so junk replies raise instead of being returned."""
    if not callable(fn):
        return fn

    def _wrapped(*args, **kwargs):
        out = fn(*args, **kwargs)
        if _is_junk_reply_91(out):
            raise RuntimeError(f"{name}: placeholder/login reply rejected")
        return out

    with _cx91.suppress(Exception):
        _wrapped.__name__ = getattr(fn, "__name__", name)
    return _wrapped


for _name91 in ("query_ai", "gemini3_solve", "call_gemini_text_rest", "deepseek_solve_text"):
    _fn91 = globals().get(_name91)
    if callable(_fn91):
        globals()[_name91] = _guard_text_provider_91(_name91, _fn91)
        _log91(f"guarded provider: {_name91}")


# _adv_call_text returns (text, provider_name) and cascades internally; drop a
# junk reply so the caller falls through to the Mistral rescue below.
_prev_adv_call_text_91 = globals().get("_adv_call_text")
if callable(_prev_adv_call_text_91):
    def _adv_call_text(prompt, *, force_json=False, timeout=18):  # noqa: F811
        out, used = _prev_adv_call_text_91(prompt, force_json=force_json, timeout=timeout)
        if not force_json and _is_junk_reply_91(out):
            raise RuntimeError("advmode: placeholder/login reply rejected")
        if force_json and not str(out or "").strip():
            raise RuntimeError("advmode: empty JSON reply")
        return out, used

    globals()["_adv_call_text"] = _adv_call_text


# ── 2) Mistral advanced rescue for plain text answers ────────────────────────

_MISTRAL_TEXT_91 = globals().get("_mistral_chat_text_90")
_SHAPE_PROMPT_91 = globals().get("_bangla_style_prompt_90")


def _mistral_rescue_text_91(prompt: str, *, timeout_seconds: int = 22) -> str:
    if not callable(_MISTRAL_TEXT_91):
        raise RuntimeError("mistral rescue unavailable")
    shaped = prompt
    if callable(_SHAPE_PROMPT_91):
        with _cx91.suppress(Exception):
            shaped = _SHAPE_PROMPT_91(prompt)
    out = _MISTRAL_TEXT_91(shaped, timeout_seconds=timeout_seconds)
    if _is_junk_reply_91(out):
        raise RuntimeError("mistral: placeholder reply")
    return str(out).strip()


globals()["_mistral_rescue_text_91"] = _mistral_rescue_text_91


_prev_try_text_91 = globals().get("_try_gemini_text_backends")
if callable(_prev_try_text_91):
    def _try_gemini_text_backends(prompt: str, *, timeout_seconds: int = 18):  # noqa: F811
        try:
            out, used = _prev_try_text_91(prompt, timeout_seconds=timeout_seconds)
            if not _is_junk_reply_91(out):
                return out, used
            _log91("cascade returned placeholder — switching to Mistral")
        except Exception as primary_error:
            try:
                return _mistral_rescue_text_91(prompt, timeout_seconds=max(18, timeout_seconds)), "Mistral"
            except Exception:
                raise primary_error
        return _mistral_rescue_text_91(prompt, timeout_seconds=max(18, timeout_seconds)), "Mistral"

    globals()["_try_gemini_text_backends"] = _try_gemini_text_backends


_prev_solve_pref_91 = globals().get("_solve_text_with_preference")
if callable(_prev_solve_pref_91):
    def _solve_text_with_preference(model: str, problem_text: str, scope: str = "private_academic"):  # noqa: F811
        base = str(globals().get("STRICT_SYSTEM_PROMPT") or "")
        rescue_prompt = (base + "\n\nCurrent user message:\n" + str(problem_text or "")).strip()
        try:
            out, used = _prev_solve_pref_91(model, problem_text, scope)
            if not _is_junk_reply_91(out):
                return out, used
        except Exception as primary_error:
            try:
                return _mistral_rescue_text_91(rescue_prompt), "Mistral"
            except Exception:
                raise primary_error
        return _mistral_rescue_text_91(rescue_prompt), "Mistral"

    globals()["_solve_text_with_preference"] = _solve_text_with_preference


_prev_solve_via_prompt_91 = globals().get("_solve_text_via_prompt")
if callable(_prev_solve_via_prompt_91):
    def _solve_text_via_prompt(prompt: str, preferred: str = "G"):  # noqa: F811
        try:
            out, used = _prev_solve_via_prompt_91(prompt, preferred)
            if not _is_junk_reply_91(out):
                return out, used
        except Exception as primary_error:
            try:
                return _mistral_rescue_text_91(prompt), "Mistral"
            except Exception:
                raise primary_error
        return _mistral_rescue_text_91(prompt), "Mistral"

    globals()["_solve_text_via_prompt"] = _solve_text_via_prompt


_prev_gemini_solve_text_91 = globals().get("gemini_solve_text")
if callable(_prev_gemini_solve_text_91):
    def gemini_solve_text(problem_text: str) -> str:  # noqa: F811
        prompt = str(globals().get("STRICT_SYSTEM_PROMPT") or "") + "\n\nUser Message:\n" + str(problem_text or "").strip()
        try:
            out = _prev_gemini_solve_text_91(problem_text)
            if not _is_junk_reply_91(out):
                return out
        except Exception as primary_error:
            try:
                return _mistral_rescue_text_91(prompt)
            except Exception:
                raise primary_error
        return _mistral_rescue_text_91(prompt)

    globals()["gemini_solve_text"] = gemini_solve_text


# ── 3) Mistral advanced rescue for MCQ / quiz JSON ───────────────────────────

def _mistral_mcq_json_91(question, options):
    builder = globals().get("_build_mcq_json_prompt")
    extract = globals().get("_extract_json_strict")
    if not (callable(builder) and callable(extract) and callable(_MISTRAL_TEXT_91)):
        raise RuntimeError("mistral MCQ rescue unavailable")
    prompt, opts = builder(question, options)
    raw = _MISTRAL_TEXT_91(prompt, timeout_seconds=22)
    data = extract(raw)
    if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
        return data
    inferred = globals().get("_infer_option_from_text")
    guess = inferred(str(raw), len(opts)) if callable(inferred) else 1
    return {
        "answer": int(guess or 1),
        "confidence": 0,
        "explanation": str(raw)[:1800],
        "why_not": {},
    }


globals()["_mistral_mcq_json_91"] = _mistral_mcq_json_91


def _mcq_data_is_bad_91(data) -> bool:
    if not isinstance(data, dict):
        return True
    if int(data.get("answer", 0) or 0) <= 0:
        return True
    return _is_junk_reply_91(str(data.get("explanation", "") or "")) and not str(data.get("why_not") or "")


_prev_try_mcq_91 = globals().get("_try_gemini_mcq_backends")
if callable(_prev_try_mcq_91):
    def _try_gemini_mcq_backends(question, options):  # noqa: F811
        try:
            data, used = _prev_try_mcq_91(question, options)
            if not _mcq_data_is_bad_91(data):
                return data, used
        except Exception as primary_error:
            try:
                return _mistral_mcq_json_91(question, options), "Mistral"
            except Exception:
                raise primary_error
        return _mistral_mcq_json_91(question, options), "Mistral"

    globals()["_try_gemini_mcq_backends"] = _try_gemini_mcq_backends


_prev_solve_mcq_pref_91 = globals().get("_solve_mcq_with_preference")
if callable(_prev_solve_mcq_pref_91):
    def _solve_mcq_with_preference(model, question, options):  # noqa: F811
        try:
            data, used = _prev_solve_mcq_pref_91(model, question, options)
            if not _mcq_data_is_bad_91(data):
                return data, used
        except Exception as primary_error:
            try:
                return _mistral_mcq_json_91(question, options), "Mistral"
            except Exception:
                raise primary_error
        return _mistral_mcq_json_91(question, options), "Mistral"

    globals()["_solve_mcq_with_preference"] = _solve_mcq_with_preference


# ── 4) Last line of defence: never deliver a placeholder to the user ─────────

_BN_BUSY_91 = (
    "⚠️ এই মুহূর্তে এআই সার্ভিস সাড়া দিচ্ছে না। অনুগ্রহ করে কিছুক্ষণ পর "
    "আবার চেষ্টা করুন — সমস্যা থাকলে মালিককে জানান।"
)


def _sanitize_ai_delivery_91(text) -> str:
    body = str(text or "").strip()
    if _is_junk_reply_91(body):
        return _BN_BUSY_91
    return body


globals()["_sanitize_ai_delivery_91"] = _sanitize_ai_delivery_91

_log91("Section 91 active: placeholder replies blocked, Mistral advanced rescue wired.")
