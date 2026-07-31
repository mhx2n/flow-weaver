# ──────────────────────────────────────────────────────────────────────────────
# Section: 04_http_ratelimit_helpers
# Original lines: 264..312
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# =========================================================
# ✅ HTTP / Rate-limit helpers
# =========================================================
class RateLimitError(RuntimeError):
    """Raised when a backend is rate-limited / quota exhausted."""
    pass

def _is_gemini_quota_error(status_code: int, body_text: str) -> bool:
    t = (body_text or "").lower()
    if status_code in (429,):
        return True
    # Gemini sometimes returns 403 for quota/project billing issues
    if status_code in (403,) and ("quota" in t or "rate" in t or "exhaust" in t or "billing" in t):
        return True
    if "resource_exhausted" in t or "rate limit" in t or "quota" in t:
        return True
    return False

def _requests_with_retries(method, url: str, *, json_payload=None, params=None, timeout=25, max_tries=3):
    """requests.* wrapper with small retries + backoff for transient network/rate errors."""
    import requests as _rq
    last_err = None
    for i in range(max_tries):
        try:
            r = method(url, json=json_payload, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            # Rate limit / quota
            if _is_gemini_quota_error(r.status_code, r.text):
                raise RateLimitError(f"Gemini rate-limited/quota exhausted (HTTP {r.status_code}).")
            # transient server errors
            if r.status_code in (500, 502, 503, 504):
                last_err = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            else:
                # non-retryable
                r.raise_for_status()
                return r
        except RateLimitError:
            raise
        except Exception as e:
            last_err = e
        time.sleep(0.8 * (2 ** i))
    if last_err:
        raise last_err
    raise RuntimeError("Request failed.")




