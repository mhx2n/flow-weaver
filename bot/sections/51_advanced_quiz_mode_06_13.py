# ──────────────────────────────────────────────────────────────────────────────
# Section: 51_advanced_quiz_mode_06_13
# ADVANCED MODE — owner-managed AI provider registry with cascading failover
# for unlimited quiz extraction & generation. Telegram-friendly plain-text
# explanations (LaTeX stripped for polls, preserved in CSV exports).
# DO NOT import directly — exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────

import json as _adv_json
import time as _adv_time

_ADV_TABLE = "adv_providers"
_ADV_QUOTA_NOTIFY_COOLDOWN = 600  # seconds — don't spam owner more than once / 10 min per provider
_ADV_LAST_NOTIFY: Dict[str, float] = {}
_ADV_MEM_CACHE: Dict[str, Any] = {"loaded": False, "rows": []}


def _adv_db_init() -> None:
    try:
        conn = db_connect(); cur = conn.cursor()
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS {_ADV_TABLE} ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " name TEXT NOT NULL,"
            " kind TEXT NOT NULL,"      # gemini_rest | gemini_web | perplexity | openai_compat
            " model TEXT,"
            " api_key TEXT,"
            " base_url TEXT,"
            " priority INTEGER DEFAULT 100,"
            " enabled INTEGER DEFAULT 1,"
            " healthy INTEGER DEFAULT 1,"
            " last_error TEXT,"
            " last_error_ts REAL DEFAULT 0,"
            " created_ts REAL DEFAULT 0"
            ")"
        )
        conn.commit()
    except Exception as e:
        logger.warning("[advmode] db init failed: %s", e)


_adv_db_init()


def _adv_load() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        conn = db_connect(); cur = conn.cursor()
        cur.execute(
            f"SELECT id, name, kind, model, api_key, base_url, priority, enabled, healthy,"
            f" last_error, last_error_ts FROM {_ADV_TABLE} ORDER BY priority ASC, id ASC"
        )
        for r in cur.fetchall():
            rows.append({
                "id": int(r[0]), "name": str(r[1] or ""), "kind": str(r[2] or ""),
                "model": str(r[3] or ""), "api_key": str(r[4] or ""),
                "base_url": str(r[5] or ""), "priority": int(r[6] or 100),
                "enabled": bool(r[7]), "healthy": bool(r[8]),
                "last_error": str(r[9] or ""), "last_error_ts": float(r[10] or 0.0),
            })
    except Exception as e:
        logger.warning("[advmode] load failed: %s", e)
    _ADV_MEM_CACHE["rows"] = rows
    _ADV_MEM_CACHE["loaded"] = True
    return rows


def _adv_seed_defaults() -> None:
    """First-run: seed with built-in providers if registry is empty."""
    rows = _adv_load()
    if rows:
        return
    defaults = [
        ("Gemini REST", "gemini_rest", "", "", "", 10),
        ("Gemini Web", "gemini_web", "", "", "", 20),
        ("Perplexity", "perplexity", "", "", "", 30),
    ]
    try:
        conn = db_connect(); cur = conn.cursor()
        for (name, kind, model, key, base, prio) in defaults:
            cur.execute(
                f"INSERT INTO {_ADV_TABLE} (name, kind, model, api_key, base_url, priority,"
                f" enabled, healthy, last_error, last_error_ts, created_ts)"
                f" VALUES (?,?,?,?,?,?,1,1,'',0,?)",
                (name, kind, model, key, base, prio, _adv_time.time()),
            )
        conn.commit()
    except Exception as e:
        logger.warning("[advmode] seed failed: %s", e)
    _adv_load()


_adv_seed_defaults()


def _adv_get(pid: int) -> Optional[Dict[str, Any]]:
    for r in _ADV_MEM_CACHE.get("rows") or []:
        if int(r.get("id") or 0) == int(pid):
            return r
    return None


def _adv_update(pid: int, **fields) -> None:
    if not fields:
        return
    keys = list(fields.keys())
    vals = [fields[k] for k in keys]
    try:
        conn = db_connect(); cur = conn.cursor()
        cur.execute(
            f"UPDATE {_ADV_TABLE} SET " + ", ".join(f"{k}=?" for k in keys) + " WHERE id=?",
            (*vals, int(pid)),
        )
        conn.commit()
    except Exception as e:
        logger.warning("[advmode] update failed: %s", e)
    _adv_load()


def _adv_insert(name: str, kind: str, *, model: str = "", api_key: str = "",
                base_url: str = "", priority: int = 100) -> int:
    try:
        conn = db_connect(); cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {_ADV_TABLE} (name, kind, model, api_key, base_url, priority,"
            f" enabled, healthy, last_error, last_error_ts, created_ts)"
            f" VALUES (?,?,?,?,?,?,1,1,'',0,?)",
            (name, kind, model, api_key, base_url, int(priority), _adv_time.time()),
        )
        new_id = int(cur.lastrowid or 0)
        conn.commit()
        _adv_load()
        return new_id
    except Exception as e:
        logger.warning("[advmode] insert failed: %s", e)
        return 0


def _adv_delete(pid: int) -> bool:
    try:
        conn = db_connect(); cur = conn.cursor()
        cur.execute(f"DELETE FROM {_ADV_TABLE} WHERE id=?", (int(pid),))
        conn.commit()
        _adv_load()
        return True
    except Exception:
        return False


def _adv_mark_failure(prov: Dict[str, Any], err: str, *, quota: bool = False) -> None:
    pid = int(prov.get("id") or 0)
    _adv_update(pid, healthy=0 if quota else 1, last_error=str(err)[:240], last_error_ts=_adv_time.time())
    if quota:
        _adv_maybe_notify_owner(prov, err)


def _adv_mark_success(prov: Dict[str, Any]) -> None:
    pid = int(prov.get("id") or 0)
    if not prov.get("healthy"):
        _adv_update(pid, healthy=1, last_error="", last_error_ts=0)


def _adv_maybe_notify_owner(prov: Dict[str, Any], err: str) -> None:
    key = f"{prov.get('id')}:{prov.get('name')}"
    now = _adv_time.time()
    last = _ADV_LAST_NOTIFY.get(key, 0.0)
    if now - last < _ADV_QUOTA_NOTIFY_COOLDOWN:
        return
    _ADV_LAST_NOTIFY[key] = now
    text = (
        "⚠️ <b>Quota / Rate-limit hit</b>\n"
        f"Provider: <code>{h(str(prov.get('name')))}</code> (id <code>{int(prov.get('id') or 0)}</code>)\n"
        f"Kind: <code>{h(str(prov.get('kind')))}</code>\n"
        f"Error: <code>{h(str(err)[:180])}</code>\n\n"
        "Marked as <b>unhealthy</b>. Add a new key/provider via <code>/advadd</code> or re-enable via <code>/advmode</code>."
    )
    try:
        import asyncio as _aio
        loop = _aio.get_event_loop()
        app = globals().get("_APP_SINGLETON")
        if not app:
            return
        for oid in (globals().get("OWNER_IDS") or ()):
            try:
                loop.create_task(app.bot.send_message(chat_id=int(oid), text=text, parse_mode=ParseMode.HTML))
            except Exception:
                pass
    except Exception:
        pass


# ───────────────────────── Provider call dispatchers ─────────────────────────

def _adv_is_quota_err(msg: str) -> bool:
    t = (msg or "").lower()
    return any(k in t for k in (
        "429", "rate", "quota", "exhaust", "limit", "billing", "insufficient",
        "resource_exhausted", "credit",
    ))


def _adv_call_openai_compat(prov: Dict[str, Any], prompt: str, *, force_json: bool, timeout: int) -> str:
    base = (prov.get("base_url") or "").rstrip("/")
    if not base:
        raise RuntimeError("base_url missing")
    key = prov.get("api_key") or ""
    if not key:
        raise RuntimeError("api_key missing")
    model = prov.get("model") or "llama-3.1-8b-instant"
    url = f"{base}/chat/completions"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    if force_json:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if r.status_code != 200:
        body = r.text[:300]
        if _adv_is_quota_err(f"{r.status_code} {body}"):
            raise RateLimitError(f"HTTP {r.status_code}: {body}")
        raise RuntimeError(f"HTTP {r.status_code}: {body}")
    data = r.json()
    try:
        return str(data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return ""


def _adv_call_provider(prov: Dict[str, Any], prompt: str, *, force_json: bool, timeout: int) -> str:
    kind = (prov.get("kind") or "").lower()
    if kind == "gemini_rest":
        return call_gemini_text_rest(prompt, timeout_seconds=timeout, force_json=force_json)
    if kind == "gemini_web":
        out = gemini3_solve(prompt)
        return str(out or "").strip()
    if kind == "perplexity":
        if not USE_PERPLEXITY_FALLBACK:
            raise RuntimeError("perplexity disabled")
        out = query_ai(prompt)
        if not out:
            raise RuntimeError("empty response")
        return str(out).strip()
    if kind in ("openai_compat", "groq", "openrouter", "mistral_chat"):
        return _adv_call_openai_compat(prov, prompt, force_json=force_json, timeout=timeout)
    raise RuntimeError(f"unknown kind: {kind}")


def _adv_call_text(prompt: str, *, force_json: bool = False, timeout: int = 18) -> Tuple[str, str]:
    """Cascade across enabled providers (priority order). Return (text, provider_name)."""
    last_err: Optional[Exception] = None
    rows = _ADV_MEM_CACHE.get("rows") or _adv_load()
    for prov in rows:
        if not prov.get("enabled"):
            continue
        if not prov.get("healthy"):
            # Allow retry every 30 minutes
            if _adv_time.time() - float(prov.get("last_error_ts") or 0) < 1800:
                continue
        try:
            out = _adv_call_provider(prov, prompt, force_json=force_json, timeout=timeout)
            if out and str(out).strip():
                _adv_mark_success(prov)
                return str(out).strip(), str(prov.get("name") or prov.get("kind"))
            _adv_mark_failure(prov, "empty response", quota=False)
        except RateLimitError as e:
            last_err = e
            _adv_mark_failure(prov, str(e), quota=True)
        except Exception as e:
            last_err = e
            quota = _adv_is_quota_err(str(e))
            _adv_mark_failure(prov, str(e), quota=quota)
    raise RuntimeError(str(last_err) if last_err else "All providers failed")


# ────────────── Override quiz extractors to use the cascading chain ──────────

_prev_extract_mcq_items_master = globals().get("_extract_mcq_items_master")
_prev_estimate_generatable_counts = globals().get("_estimate_generatable_counts")
_prev_generate_mcqs_from_content = globals().get("_generate_mcqs_from_content")


def _adv_strip_latex_for_telegram(text: str) -> str:
    """Final pass: ensure no LaTeX leaks into Telegram poll explanations."""
    t = str(text or "").strip()
    if not t:
        return ""
    try:
        t = _sanitize_quiz_explanation_text(t)
    except Exception:
        pass
    # Extra safety — clean_latex may have missed some inline tokens
    t = re.sub(r"\\\((.*?)\\\)", r"\1", t)
    t = re.sub(r"\\\[(.*?)\\\]", r"\1", t)
    t = re.sub(r"\$\$(.*?)\$\$", r"\1", t, flags=re.S)
    t = re.sub(r"\$(.+?)\$", r"\1", t)
    t = re.sub(r"\\(frac|sqrt|times|cdot|left|right|begin|end)\b\{?[^}\s]*\}?", " ", t)
    t = re.sub(r"[{}]", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    # Telegram poll explanation max length is 200 chars
    if len(t) > 200:
        t = t[:197].rstrip() + "..."
    return t


def _extract_mcq_items_master(chunk_text: str) -> List[Dict[str, Any]]:  # noqa: F811
    body = (chunk_text or "").strip()
    if not body:
        return []
    prompt = _MASTER_MCQ_PROMPT_HEADER + body[:18000]
    raw = ""
    try:
        raw, _used = _adv_call_text(prompt, force_json=True, timeout=14)
    except Exception as e:
        db_log("WARN", "adv_mcq_extract_failed", {"error": str(e)})
        return []
    if not raw:
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
            "explanation": _adv_strip_latex_for_telegram(str(it.get("explanation") or "").strip()),
            "type": 1,
            "section": 1,
        })
    return out


def _estimate_generatable_counts(content_text: str) -> Dict[str, int]:  # noqa: F811
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
    try:
        raw, _ = _adv_call_text(prompt, force_json=True, timeout=10)
    except Exception:
        return {"easy": 0, "medium": 0, "hard": 0}
    try:
        data = _extract_json_strict(raw)
    except Exception:
        return {"easy": 0, "medium": 0, "hard": 0}
    if not isinstance(data, dict):
        return {"easy": 0, "medium": 0, "hard": 0}
    return {
        "easy": max(0, min(20, int(data.get("easy", 0) or 0))),
        "medium": max(0, min(20, int(data.get("medium", 0) or 0))),
        "hard": max(0, min(20, int(data.get("hard", 0) or 0))),
    }


def _generate_mcqs_from_content(content_text: str, *, easy: int, medium: int, hard: int) -> List[Dict[str, Any]]:  # noqa: F811
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
        "Explanation MUST be PLAIN TEXT for Telegram (no LaTeX, no $...$, no \\frac, no markdown).\n"
        "Keep each explanation under 180 characters.\n"
        "Vary difficulty: easy=direct recall, medium=apply concept, hard=multi-step.\n"
        "Do NOT repeat questions. Do NOT invent facts not supported by the text.\n"
        'JSON: {"items":[{"questions":"...","option1":"...","option2":"...","option3":"...","option4":"...","option5":"","answer":1,"explanation":"...","difficulty":"easy|medium|hard"}]}\n\n'
        f"CONTENT:\n{body[:12000]}"
    )
    try:
        raw, _ = _adv_call_text(prompt, force_json=True, timeout=22)
    except Exception as e:
        db_log("WARN", "adv_genq_failed", {"error": str(e)})
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
    for it in (data.get("items") or [])[:60]:
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
            "explanation": _adv_strip_latex_for_telegram(str(it.get("explanation") or "").strip()),
            "type": 1,
            "section": 1,
        })
    return out


# ──────────────────── Owner UI: /advmode, /advadd, /advrm ────────────────────

_ADV_KIND_LABELS = {
    "gemini_rest": "Gemini REST",
    "gemini_web": "Gemini Web",
    "perplexity": "Perplexity",
    "openai_compat": "OpenAI-Compat",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "mistral_chat": "Mistral Chat",
}


def _adv_render_list_kb() -> InlineKeyboardMarkup:
    rows = []
    for r in (_ADV_MEM_CACHE.get("rows") or []):
        pid = int(r.get("id") or 0)
        on = "🟢" if r.get("enabled") else "⚪"
        hl = "" if r.get("healthy") else " ⚠️"
        label = f"{on} {r.get('name')}{hl}"
        rows.append([
            InlineKeyboardButton(label, callback_data=f"adv:tog:{pid}"),
            InlineKeyboardButton("🗑", callback_data=f"adv:del:{pid}"),
        ])
    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="adv:ref:0")])
    return InlineKeyboardMarkup(rows)


def _adv_render_list_html() -> str:
    rows = _ADV_MEM_CACHE.get("rows") or []
    if not rows:
        return "No providers configured."
    lines = []
    for r in rows:
        on = "ON " if r.get("enabled") else "OFF"
        hl = "OK" if r.get("healthy") else "QUOTA"
        kind = _ADV_KIND_LABELS.get(r.get("kind"), r.get("kind"))
        model = f" · <code>{h(r.get('model'))}</code>" if r.get("model") else ""
        lines.append(
            f"<b>#{r.get('id')}</b> {h(r.get('name'))} — <code>{h(kind)}</code>{model} · "
            f"[{on}/{hl}] · prio <code>{r.get('priority')}</code>"
        )
        if not r.get("healthy") and r.get("last_error"):
            lines.append(f"   ↳ <i>{h(str(r.get('last_error'))[:120])}</i>")
    return "\n".join(lines)


async def cmd_advmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not _is_owner_id(update.effective_user.id):
        return
    _adv_load()
    body = (
        "🧠 <b>Advanced Mode — AI Provider Registry</b>\n\n"
        + _adv_render_list_html()
        + "\n\n<b>Commands:</b>\n"
        "• <code>/advadd &lt;name&gt; &lt;kind&gt; [model] [api_key] [base_url]</code>\n"
        "  kinds: <code>gemini_rest, gemini_web, perplexity, openai_compat, groq, openrouter, mistral_chat</code>\n"
        "• <code>/advrm &lt;id&gt;</code> — remove\n"
        "• <code>/advprio &lt;id&gt; &lt;number&gt;</code> — set priority (lower = first)\n"
        "• Tap a provider below to toggle ON/OFF."
    )
    await update.effective_message.reply_text(
        body, parse_mode=ParseMode.HTML, reply_markup=_adv_render_list_kb(),
        disable_web_page_preview=True,
    )


async def cmd_advadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not _is_owner_id(update.effective_user.id):
        return
    args = list(context.args or [])
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Usage: <code>/advadd &lt;name&gt; &lt;kind&gt; [model] [api_key] [base_url]</code>\n"
            "Kinds: gemini_rest, gemini_web, perplexity, openai_compat, groq, openrouter, mistral_chat\n\n"
            "Examples:\n"
            "• <code>/advadd Groq-Llama groq llama-3.3-70b-versatile gsk_xxx https://api.groq.com/openai/v1</code>\n"
            "• <code>/advadd OR-Mixtral openrouter mistralai/mixtral-8x7b-instruct sk-or-xxx https://openrouter.ai/api/v1</code>\n"
            "• <code>/advadd Mistral mistral_chat mistral-large-latest xxx https://api.mistral.ai/v1</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    name = args[0]
    kind = args[1].lower()
    model = args[2] if len(args) > 2 else ""
    api_key = args[3] if len(args) > 3 else ""
    base_url = args[4] if len(args) > 4 else ""
    # defaults for known providers
    if kind == "groq" and not base_url:
        base_url = "https://api.groq.com/openai/v1"
    if kind == "openrouter" and not base_url:
        base_url = "https://openrouter.ai/api/v1"
    if kind == "mistral_chat" and not base_url:
        base_url = "https://api.mistral.ai/v1"
    if kind not in _ADV_KIND_LABELS:
        await update.effective_message.reply_text(f"Unknown kind: {kind}")
        return
    new_id = _adv_insert(name, kind, model=model, api_key=api_key, base_url=base_url, priority=100)
    await update.effective_message.reply_text(
        f"✅ Added provider <b>{h(name)}</b> (id <code>{new_id}</code>, kind <code>{h(kind)}</code>).",
        parse_mode=ParseMode.HTML,
    )


async def cmd_advrm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not _is_owner_id(update.effective_user.id):
        return
    args = list(context.args or [])
    if not args:
        await update.effective_message.reply_text("Usage: <code>/advrm &lt;id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        pid = int(args[0])
    except Exception:
        await update.effective_message.reply_text("Invalid id")
        return
    if _adv_delete(pid):
        await update.effective_message.reply_text(f"🗑 Removed provider <code>{pid}</code>.", parse_mode=ParseMode.HTML)
    else:
        await update.effective_message.reply_text("Failed to remove.")


async def cmd_advprio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not _is_owner_id(update.effective_user.id):
        return
    args = list(context.args or [])
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: <code>/advprio &lt;id&gt; &lt;number&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        pid = int(args[0]); prio = int(args[1])
    except Exception:
        await update.effective_message.reply_text("Invalid args")
        return
    _adv_update(pid, priority=prio)
    await update.effective_message.reply_text(f"✅ Priority of <code>{pid}</code> = <code>{prio}</code>", parse_mode=ParseMode.HTML)


async def cb_adv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    if not q.from_user or not _is_owner_id(q.from_user.id):
        with contextlib.suppress(Exception):
            await q.answer("Owner only", show_alert=False)
        return
    parts = q.data.split(":")
    if len(parts) != 3 or parts[0] != "adv":
        return
    action, raw_id = parts[1], parts[2]
    try:
        pid = int(raw_id)
    except Exception:
        pid = 0
    if action == "tog" and pid:
        prov = _adv_get(pid)
        if prov:
            new_val = 0 if prov.get("enabled") else 1
            _adv_update(pid, enabled=new_val, healthy=1, last_error="", last_error_ts=0)
            with contextlib.suppress(Exception):
                await q.answer("Toggled")
    elif action == "del" and pid:
        _adv_delete(pid)
        with contextlib.suppress(Exception):
            await q.answer("Removed")
    elif action == "ref":
        _adv_load()
        with contextlib.suppress(Exception):
            await q.answer("Refreshed")
    body = (
        "🧠 <b>Advanced Mode — AI Provider Registry</b>\n\n"
        + _adv_render_list_html()
        + "\n\nTap any provider to toggle. <code>/advadd</code> to add."
    )
    with contextlib.suppress(Exception):
        await q.edit_message_text(body, parse_mode=ParseMode.HTML, reply_markup=_adv_render_list_kb(),
                                  disable_web_page_preview=True)


# ───────────────────── Register handlers + capture app ref ───────────────────

_prev_build_app_adv_51 = build_app


def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_adv_51()
    globals()["_APP_SINGLETON"] = app
    with contextlib.suppress(Exception):
        app.add_handler(CommandHandler("advmode", cmd_advmode))
        app.add_handler(CommandHandler("advadd", cmd_advadd))
        app.add_handler(CommandHandler("advrm", cmd_advrm))
        app.add_handler(CommandHandler("advprio", cmd_advprio))
        app.add_handler(CallbackQueryHandler(cb_adv, pattern=r"^adv:(tog|del|ref):\d+$"))
    return app


logger.info("[ADVANCED MODE 06_13] Provider registry loaded with %d providers.", len(_ADV_MEM_CACHE.get("rows") or []))

# ===== END ADVANCED QUIZ MODE =====