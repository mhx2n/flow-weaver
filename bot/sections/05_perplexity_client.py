# ──────────────────────────────────────────────────────────────────────────────
# Section: 05_perplexity_client
# Original lines: 313..334
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# =========================================================
# ✅ Perplexity fallback client (merged from main.py)
# =========================================================
def query_ai(prompt: str) -> str | None:
    """HTTP fallback solver. Returns plain text answer or None."""
    if not USE_PERPLEXITY_FALLBACK:
        return None
    try:
        r = requests.get(PERPLEXITY_API, params={"prompt": prompt}, timeout=60)
        if r.status_code != 200:
            logger.error("Perplexity HTTP %s: %s", r.status_code, (r.text or "")[:2000])
            return None
        data = r.json()
        if data.get("status") == "success" and "answer" in data:
            return str(data["answer"]).strip()
        logger.error("Perplexity bad response: %s", str(data)[:2000])
        return None
    except Exception as e:
        logger.exception("Perplexity error: %s", e)
        return None


