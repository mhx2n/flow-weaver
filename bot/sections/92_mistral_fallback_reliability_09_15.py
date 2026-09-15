# ──────────────────────────────────────────────────────────────────────────────
# Section 92 (2026-09-15) — final Mistral fallback reliability layer.
#
# Loads Mistral credentials from every supported owner-managed source, rotates
# through keys/models, and prevents an earlier provider's internal error from
# leaking to users when Mistral is the final fallback.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx92
import json as _json92
import re as _re92


_MISTRAL_DEFAULT_URL_92 = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODELS_92 = ("mistral-large-latest", "mistral-small-latest")
_MISTRAL_KINDS_92 = {"mistral_chat", "mistral"}
_PUBLIC_AI_ERROR_92 = "এআই সেবা এই মুহূর্তে সাড়া দিচ্ছে না। অনুগ্রহ করে একটু পর আবার চেষ্টা করুন।"


def _log92(level: str, message: str, *args) -> None:
    with _cx92.suppress(Exception):
        getattr(logger, level)("[S92] " + message, *args)  # type: ignore[name-defined]


def _mistral_url_92(base_url: str = "") -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return _MISTRAL_DEFAULT_URL_92
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _mistral_candidates_92():
    """Return unique enabled Mistral credentials from DB, env and providers."""
    candidates, seen = [], set()

    def add(key, *, model="", base_url="", key_id=0, provider=None):
        secret = str(key or "").strip()
        if not secret:
            return
        model_name = str(model or "").strip() or _MISTRAL_MODELS_92[0]
        url = _mistral_url_92(base_url)
        marker = (secret, model_name, url)
        if marker in seen:
            return
        seen.add(marker)
        candidates.append({
            "api_key": secret,
            "model": model_name,
            "url": url,
            "key_id": int(key_id or 0),
            "provider": provider,
        })

    getter = globals().get("get_mistral_api_keys")
    if callable(getter):
        try:
            for item in getter() or []:
                if isinstance(item, dict) and item.get("is_enabled", True):
                    add(item.get("api_key"), key_id=item.get("id", 0))
        except Exception as exc:
            _log92("warning", "Could not load owner Mistral keys: %s", type(exc).__name__)

    env_values = [
        str(os.getenv("MISTRAL_API_KEY", "") or ""),  # type: ignore[name-defined]
        str(os.getenv("MISTRAL_API_KEYS", "") or ""),  # type: ignore[name-defined]
    ]
    for raw in env_values:
        for key in _re92.split(r"[,;\s]+", raw.strip()):
            add(key)

    loader = globals().get("_adv_load")
    try:
        rows = loader() if callable(loader) else (globals().get("_ADV_MEM_CACHE") or {}).get("rows", [])
    except Exception as exc:
        rows = []
        _log92("warning", "Could not load advanced providers: %s", type(exc).__name__)
    for provider in rows or []:
        if not isinstance(provider, dict) or not provider.get("enabled", True):
            continue
        kind = str(provider.get("kind") or "").lower().strip()
        base = str(provider.get("base_url") or "").lower()
        if kind in _MISTRAL_KINDS_92 or "mistral.ai" in base:
            add(
                provider.get("api_key"),
                model=provider.get("model"),
                base_url=provider.get("base_url"),
                provider=provider,
            )
    return candidates


def _mistral_models_for_92(candidate):
    preferred = str((candidate or {}).get("model") or "").strip()
    models = []
    for model in (preferred, *_MISTRAL_MODELS_92):
        if model and model not in models:
            models.append(model)
    return models


def _mistral_mark_92(candidate, success: bool, detail: str = "") -> None:
    key_id = int((candidate or {}).get("key_id") or 0)
    marker = globals().get("_mistral_mark_key_status")
    if key_id and callable(marker):
        with _cx92.suppress(Exception):
            marker(key_id, "ok" if success else "error", "" if success else str(detail)[:180])
    provider = (candidate or {}).get("provider")
    provider_marker = globals().get("_adv_mark_success" if success else "_adv_mark_failure")
    if isinstance(provider, dict) and callable(provider_marker):
        with _cx92.suppress(Exception):
            if success:
                provider_marker(provider)
            else:
                provider_marker(provider, str(detail)[:180], quota=False)


def _mistral_rescue_text_92(prompt: str, *, timeout_seconds: int = 24) -> str:
    body = str(prompt or "").strip()
    if not body:
        raise RuntimeError(_PUBLIC_AI_ERROR_92)
    candidates = _mistral_candidates_92()
    if not candidates:
        _log92("warning", "No enabled Mistral credential was found")
        raise RuntimeError(_PUBLIC_AI_ERROR_92)

    junk_check = globals().get("_is_junk_reply_91")
    failures = []
    for candidate in candidates:
        for model in _mistral_models_for_92(candidate):
            try:
                response = requests.post(  # type: ignore[name-defined]
                    candidate["url"],
                    headers={
                        "Authorization": "Bearer " + candidate["api_key"],
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "temperature": 0.2,
                        "max_tokens": 2400,
                        "messages": [{"role": "user", "content": body[:30000]}],
                    },
                    timeout=max(12, int(timeout_seconds or 24)),
                )
                if response.status_code != 200:
                    failures.append("HTTP " + str(response.status_code))
                    continue
                payload = response.json()
                answer = str(
                    (((payload.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
                ).strip()
                if not answer or (callable(junk_check) and junk_check(answer)):
                    failures.append("empty or placeholder response")
                    continue
                _mistral_mark_92(candidate, True)
                return answer
            except Exception as exc:
                failures.append(type(exc).__name__)
                continue
        _mistral_mark_92(candidate, False, failures[-1] if failures else "request failed")

    _log92("warning", "Mistral fallback exhausted %d candidate(s): %s", len(candidates), ", ".join(failures[-6:]))
    raise RuntimeError(_PUBLIC_AI_ERROR_92)


globals()["_mistral_candidates_92"] = _mistral_candidates_92
globals()["_mistral_rescue_text_92"] = _mistral_rescue_text_92
# Keep section 91's helper name pointed at the corrected implementation so any
# dynamically looked-up path also gets all key sources and key rotation.
globals()["_mistral_rescue_text_91"] = _mistral_rescue_text_92


def _clean_public_ai_error_92(exc) -> RuntimeError:
    _log92("warning", "All AI fallbacks failed: %s", type(exc).__name__)
    return RuntimeError(_PUBLIC_AI_ERROR_92)


def _wrap_text_pair_92(name: str, prompt_builder):
    previous = globals().get(name)
    if not callable(previous):
        return

    def wrapped(*args, **kwargs):
        try:
            out, used = previous(*args, **kwargs)
            check = globals().get("_is_junk_reply_91")
            if str(out or "").strip() and not (callable(check) and check(out)):
                return out, used
        except Exception as primary_error:
            saved_error = primary_error
        else:
            saved_error = RuntimeError("invalid provider response")
        try:
            return _mistral_rescue_text_92(prompt_builder(*args, **kwargs)), "Mistral"
        except Exception:
            raise _clean_public_ai_error_92(saved_error)

    globals()[name] = wrapped


_wrap_text_pair_92(
    "_try_gemini_text_backends",
    lambda prompt, **_kwargs: str(prompt or ""),
)
_wrap_text_pair_92(
    "_solve_text_via_prompt",
    lambda prompt, preferred="G", **_kwargs: str(prompt or ""),
)
_wrap_text_pair_92(
    "_solve_text_with_preference",
    lambda model, problem_text, scope="private_academic", **_kwargs: (
        str(globals().get("STRICT_SYSTEM_PROMPT") or "")
        + "\n\nCurrent user message:\n"
        + str(problem_text or "")
    ).strip(),
)


_prev_gemini_solve_text_92 = globals().get("gemini_solve_text")
if callable(_prev_gemini_solve_text_92):
    def gemini_solve_text(problem_text: str) -> str:  # noqa: F811
        try:
            answer = _prev_gemini_solve_text_92(problem_text)
            check = globals().get("_is_junk_reply_91")
            if str(answer or "").strip() and not (callable(check) and check(answer)):
                return answer
        except Exception as primary_error:
            saved_error = primary_error
        else:
            saved_error = RuntimeError("invalid provider response")
        prompt = (str(globals().get("STRICT_SYSTEM_PROMPT") or "")
                  + "\n\nUser Message:\n" + str(problem_text or "")).strip()
        try:
            return _mistral_rescue_text_92(prompt)
        except Exception:
            raise _clean_public_ai_error_92(saved_error)

    globals()["gemini_solve_text"] = gemini_solve_text


def _mistral_mcq_json_92(question, options):
    builder = globals().get("_build_mcq_json_prompt")
    extractor = globals().get("_extract_json_strict")
    if not callable(builder):
        raise RuntimeError(_PUBLIC_AI_ERROR_92)
    prompt, opts = builder(question, options)
    raw = _mistral_rescue_text_92(prompt, timeout_seconds=26)
    data = None
    if callable(extractor):
        with _cx92.suppress(Exception):
            data = extractor(raw)
    if data is None:
        with _cx92.suppress(Exception):
            match = _re92.search(r"\{.*\}", raw, _re92.S)
            data = _json92.loads(match.group(0) if match else raw)
    if isinstance(data, dict) and 1 <= int(data.get("answer", 0) or 0) <= len(opts):
        return data
    raise RuntimeError(_PUBLIC_AI_ERROR_92)


globals()["_mistral_mcq_json_92"] = _mistral_mcq_json_92
globals()["_mistral_mcq_json_91"] = _mistral_mcq_json_92


def _wrap_mcq_pair_92(name: str):
    previous = globals().get(name)
    if not callable(previous):
        return

    def wrapped(*args, **kwargs):
        question = args[-2] if len(args) >= 2 else kwargs.get("question", "")
        options = args[-1] if args else kwargs.get("options", [])
        try:
            data, used = previous(*args, **kwargs)
            bad = globals().get("_mcq_data_is_bad_91")
            if isinstance(data, dict) and not (callable(bad) and bad(data)):
                return data, used
        except Exception as primary_error:
            saved_error = primary_error
        else:
            saved_error = RuntimeError("invalid MCQ response")
        try:
            return _mistral_mcq_json_92(question, options), "Mistral"
        except Exception:
            raise _clean_public_ai_error_92(saved_error)

    globals()[name] = wrapped


_wrap_mcq_pair_92("_try_gemini_mcq_backends")
_wrap_mcq_pair_92("_solve_mcq_with_preference")

_log92("info", "Final Mistral fallback active with DB, environment and provider key rotation.")