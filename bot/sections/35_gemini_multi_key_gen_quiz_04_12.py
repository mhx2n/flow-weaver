# ──────────────────────────────────────────────────────────────────────────────
# Section: 35_gemini_multi_key_gen_quiz_04_12
# Original lines: 18993..19932
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== GEMINI MULTI-KEY + /GEN QUIZ PATCH (2026-04-12) =====
# Adds:
# - Multiple Gemini API keys with sequential failover
# - Owner command to manage keys
# - /gen [n] from replied page image/OCR context
# - User limits: 10 quizzes per page, 30 per day; owner/admin unlimited
# - Better OCR normalization for quiz generation and question matching

import hashlib as _hashlib_gemini_patch
from collections import Counter as _Counter_gemini_patch

_GEMINI_KEY_TABLE = "gemini_api_keys"
_GEMINI_GEN_USAGE_TABLE = "gemini_gen_usage"
_GEMINI_DEFAULT_USER_DAILY_LIMIT = 30
_GEMINI_DEFAULT_PAGE_DAILY_LIMIT = 10
_GEMINI_MAX_BATCH_SIZE = 5


def _normalize_secret_mask(secret: str) -> str:
    s = str(secret or "").strip()
    if len(s) <= 10:
        return "*" * max(4, len(s))
    return f"{s[:4]}...{s[-4:]}"


def _ensure_gemini_runtime_tables() -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_GEMINI_KEY_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT NOT NULL UNIQUE,
            label TEXT DEFAULT '',
            is_enabled INTEGER NOT NULL DEFAULT 1,
            last_status TEXT DEFAULT '',
            fail_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_GEMINI_GEN_USAGE_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_hash TEXT NOT NULL,
            day_key TEXT NOT NULL,
            generated_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, source_hash, day_key)
        )
        """
    )
    conn.commit()
    conn.close()


def _load_gemini_env_keys() -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        for part in re.split(r"[\s,;\n]+", str(value or "")):
            k = part.strip()
            if not k or k in seen:
                continue
            seen.add(k)
            keys.append(k)

    add(os.getenv("GEMINI_API_KEY", ""))
    add(os.getenv("GEMINI_API_KEYS", ""))
    indexed: list[tuple[int, str]] = []
    for name, value in os.environ.items():
        m = re.fullmatch(r"GEMINI_API_KEY_(\d+)", name)
        if m and str(value or "").strip():
            indexed.append((int(m.group(1)), str(value).strip()))
    for _, value in sorted(indexed, key=lambda x: x[0]):
        add(value)
    return keys


def _gemini_key_rows(include_disabled: bool = True) -> list[dict[str, Any]]:
    _ensure_gemini_runtime_tables()
    conn = db_connect()
    cur = conn.cursor()
    if include_disabled:
        cur.execute(f"SELECT * FROM {_GEMINI_KEY_TABLE} ORDER BY id ASC")
    else:
        cur.execute(f"SELECT * FROM {_GEMINI_KEY_TABLE} WHERE is_enabled=1 ORDER BY id ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Add env keys as immutable fallbacks, after DB keys
    existing = {str(r.get("api_key") or "").strip() for r in rows}
    for idx, k in enumerate(_load_gemini_env_keys(), start=1):
        if k in existing:
            continue
        rows.append({
            "id": -(idx),
            "api_key": k,
            "label": "env",
            "is_enabled": 1,
            "last_status": "env",
            "fail_count": 0,
            "last_error": "",
            "created_at": "",
            "updated_at": "",
        })
    return rows


def get_gemini_api_keys() -> list[str]:
    rows = _gemini_key_rows(include_disabled=False)
    keys = [str(r.get("api_key") or "").strip() for r in rows if str(r.get("api_key") or "").strip()]
    # Compatibility globals used by older code paths
    globals()["GEMINI_API_KEYS"] = keys
    globals()["GEMINI_API_KEY"] = keys[0] if keys else ""
    return keys


def _refresh_gemini_globals() -> None:
    try:
        get_gemini_api_keys()
    except Exception:
        pass


def _gemini_key_id_from_selector(selector: str) -> int | None:
    s = str(selector or "").strip()
    if not s:
        return None
    rows = _gemini_key_rows(include_disabled=True)
    if re.fullmatch(r"-?\d+", s):
        target = int(s)
        for row in rows:
            if int(row.get("id") or 0) == target:
                return target
        return None
    # partial secret or label match
    for row in rows:
        key = str(row.get("api_key") or "").strip()
        label = str(row.get("label") or "").strip().lower()
        if s.lower() == label and label:
            return int(row.get("id") or 0)
        if s and s in key:
            return int(row.get("id") or 0)
    return None


def _gemini_add_key(secret: str, label: str = "") -> bool:
    key = str(secret or "").strip()
    if not key:
        return False
    _ensure_gemini_runtime_tables()
    ts = now_iso()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        f"INSERT OR IGNORE INTO {_GEMINI_KEY_TABLE}(api_key, label, is_enabled, created_at, updated_at) VALUES (?,?,?,?,?)",
        (key, label or "", 1, ts, ts),
    )
    cur.execute(
        f"UPDATE {_GEMINI_KEY_TABLE} SET is_enabled=1, label=COALESCE(NULLIF(label,''), ?), updated_at=? WHERE api_key=?",
        (label or "", ts, key),
    )
    conn.commit()
    conn.close()
    _refresh_gemini_globals()
    return True


def _gemini_remove_key(selector: str) -> bool:
    key_id = _gemini_key_id_from_selector(selector)
    if key_id is None:
        return False
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {_GEMINI_KEY_TABLE} WHERE id=?", (key_id,))
    conn.commit()
    conn.close()
    _refresh_gemini_globals()
    return True


def _gemini_clear_all_keys() -> int:
    _ensure_gemini_runtime_tables()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {_GEMINI_KEY_TABLE}")
    count = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()
    conn.close()
    _refresh_gemini_globals()
    return count


def _gemini_set_key_enabled(selector: str, enabled: bool) -> bool:
    key_id = _gemini_key_id_from_selector(selector)
    if key_id is None:
        return False
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {_GEMINI_KEY_TABLE} SET is_enabled=?, updated_at=? WHERE id=?",
        (1 if enabled else 0, now_iso(), key_id),
    )
    conn.commit()
    conn.close()
    _refresh_gemini_globals()
    return True


def _gemini_mark_key_status(api_key: str, status: str, error_text: str = "") -> None:
    key = str(api_key or "").strip()
    if not key:
        return
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {_GEMINI_KEY_TABLE} SET last_status=?, last_error=?, fail_count=CASE WHEN ?='ok' THEN 0 ELSE fail_count+1 END, updated_at=? WHERE api_key=?",
            (status, str(error_text or "")[:260], status, now_iso(), key),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _gemini_runtime_report_html() -> str:
    rows = _gemini_key_rows(include_disabled=True)
    active = [r for r in rows if int(r.get("is_enabled") or 0) == 1]
    env_only = len([r for r in rows if int(r.get("id") or 0) < 0])
    lines = [
        f"Enabled keys: <code>{h(str(len(active)))}</code>",
        f"Total saved entries: <code>{h(str(len(rows)))}</code>",
        f"Env fallback keys: <code>{h(str(env_only))}</code>",
        f"Text model: <code>{h(str(GEMINI_MODEL_TEXT))}</code>",
        f"Vision model: <code>{h(str(GEMINI_MODEL_VISION))}</code>",
    ]
    if active:
        lines.append("<b>Key order</b>")
        for r in active[:12]:
            lines.append(
                f"• <code>{h(str(r.get('id') or 'env'))}</code> | {h(_normalize_secret_mask(str(r.get('api_key') or '')))}"
                f" | {h(str(r.get('label') or ''))} | {h(str(r.get('last_status') or ''))}"
            )
    else:
        lines.append("<b>No active Gemini keys</b>")
    return "\n".join(lines)


# ----- Gemini REST failover -----

def _gemini_call_with_key_rotation(model: str, payload: Dict[str, Any], *, timeout_seconds: int) -> str:
    keys = get_gemini_api_keys()
    if not keys:
        raise RuntimeError("No Gemini API key configured. Use /gemini add YOUR_KEY first.")

    last_err: Exception | None = None
    for api_key in keys:
        url = f"https://generativelanguage.googleapis.com/v1beta/{_normalize_model_name(model)}:generateContent?key={api_key}"
        try:
            r = _requests_with_retries(
                requests.post,
                url,
                json_payload=payload,
                timeout=max(8, int(timeout_seconds or 10)),
                max_tries=1,
            )
            data = r.json()
            text = _extract_gemini_text_from_response(data)
            if text and str(text).strip():
                _gemini_mark_key_status(api_key, "ok", "")
                return str(text).strip()
            _gemini_mark_key_status(api_key, "empty", "Empty Gemini response")
            last_err = RuntimeError("Empty Gemini response")
        except RateLimitError as e:
            _gemini_mark_key_status(api_key, "quota", str(e))
            last_err = e
            continue
        except Exception as e:
            _gemini_mark_key_status(api_key, "error", str(e))
            last_err = e
            continue
    raise RuntimeError(str(last_err or "Gemini REST backend is unavailable."))


def call_gemini_text_rest(prompt: str, timeout_seconds: int = GEMINI_TEXT_TIMEOUT_SECONDS, *, force_json: bool = False) -> str:
    keys = get_gemini_api_keys()
    if not keys:
        raise RuntimeError("Gemini API key missing. Use /gemini add YOUR_KEY first.")

    last_err: Exception | None = None
    json_modes = [True, False] if force_json else [False]
    models = _all_text_model_candidates()

    for use_json_mode in json_modes:
        payload = _build_gemini_text_payload(prompt, force_json=use_json_mode)
        for model in models:
            try:
                out = _gemini_call_with_key_rotation(model, payload, timeout_seconds=timeout_seconds)
                if out and str(out).strip():
                    return str(out).strip()
            except Exception as e:
                last_err = e
                continue
    raise RuntimeError(str(last_err or "Gemini REST text backend is unavailable."))


def call_gemini_vision_rest(image_path: str, prompt: str, force_json: bool = True) -> str:
    keys = get_gemini_api_keys()
    if not keys:
        raise RuntimeError("Gemini API key missing. Use /gemini add YOUR_KEY first.")

    last_err: Exception | None = None
    json_modes = [True, False] if force_json else [False]
    models = _all_vision_model_candidates()

    for use_json_mode in json_modes:
        payload = _build_gemini_vision_payload(image_path, prompt, force_json=use_json_mode)
        for model in models:
            try:
                out = _gemini_call_with_key_rotation(model, payload, timeout_seconds=GEMINI_VISION_TIMEOUT_SECONDS)
                if out and str(out).strip():
                    return str(out).strip()
            except Exception as e:
                last_err = e
                continue
    raise RuntimeError(str(last_err or "Gemini vision backend is unavailable."))


def _gemini_text_router(prompt: str, *, timeout_seconds: int = 20) -> tuple[str, str]:
    # Official Gemini REST with multi-key rotation first
    if get_gemini_api_keys():
        try:
            out = call_gemini_text_rest(prompt, timeout_seconds=timeout_seconds)
            if out and str(out).strip():
                return str(out).strip(), "Gemini"
        except Exception as e:
            logger.debug("[Gemini REST text] %s", e)

    # Then Perplexity
    try:
        alt = query_ai(prompt)
        if alt and str(alt).strip():
            return str(alt).strip(), "Perplexity"
    except Exception as e:
        logger.debug("[Perplexity text] %s", e)

    # Then Gemini web session
    try:
        out = gemini3_solve(prompt)
        if out and str(out).strip():
            return str(out).strip(), "Gemini Web"
    except Exception as e:
        logger.debug("[Gemini web text] %s", e)

    raise RuntimeError("AI সাময়িকভাবে অনুপলব্ধ। কিছুক্ষণ পর আবার চেষ্টা করুন।")


def _gemini_mcq_router(question: str, options: list[str]) -> tuple[Dict[str, Any], str]:
    prompt, opts = _build_mcq_json_prompt(question, options)

    # 1) Official Gemini REST
    if get_gemini_api_keys():
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=18, force_json=True)
            data = _coerce_mcq_result(raw, len(opts))
            if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
                return data, "Gemini"
        except Exception as e:
            logger.debug("[Gemini REST MCQ] %s", e)

    # 2) Perplexity
    try:
        alt = query_ai(prompt)
        data = _coerce_mcq_result(alt or "", len(opts))
        if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
            return data, "Perplexity"
    except Exception as e:
        logger.debug("[Perplexity MCQ] %s", e)

    # 3) Gemini web
    try:
        g3 = gemini3_solve(prompt)
        data = _coerce_mcq_result(g3 or "", len(opts))
        if isinstance(data, dict) and int(data.get("answer", 0) or 0) > 0:
            return data, "Gemini Web"
    except Exception as e:
        logger.debug("[Gemini web MCQ] %s", e)

    raise RuntimeError("সকল AI ব্যাকএন্ড সাময়িকভাবে অনুপলব্ধ। কিছুক্ষণ পর আবার চেষ্টা করুন।")


def gemini_solve_text(problem_text: str) -> str:  # noqa: F811
    prompt = STRICT_SYSTEM_PROMPT + "\n\nUser Message:\n" + (problem_text or "").strip()
    out, _ = _gemini_text_router(prompt, timeout_seconds=20)
    return out


def gemini_solve_mcq_json(question: str, options: list[str]) -> Dict[str, Any]:  # noqa: F811
    data, _ = _gemini_mcq_router(question, options)
    return data


# ----- OCR normalization + /gen support -----

def _normalize_ocr_quiz_text(text: str) -> str:
    s = str(text or "")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"-\n(?=\w)", "", s)  # join hyphenated line breaks
    s = re.sub(r"\n{3,}", "\n\n", s)
    # remove obvious repeated page furniture
    drop_patterns = [
        r"^\s*Page\s*\d+\s*$",
        r"^\s*\d+\s*$",
        r"^\s*\d{1,2}[:\.]\d{2}\s*(AM|PM)?\s*$",
    ]
    out_lines = []
    for line in s.splitlines():
        t = line.strip()
        if not t:
            out_lines.append("")
            continue
        if any(re.match(p, t, re.IGNORECASE) for p in drop_patterns):
            continue
        out_lines.append(t)
    s = "\n".join(out_lines)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def _build_ocr_quiz_source(ocr_ctx: Dict[str, Any], max_items: int = 40) -> str:
    clean_text = _normalize_ocr_quiz_text(str((ocr_ctx or {}).get("clean_text") or (ocr_ctx or {}).get("raw_markdown") or ""))
    items = list((ocr_ctx or {}).get("items") or [])
    blocks: list[str] = []
    for idx, item in enumerate(items[:max_items], start=1):
        q = str(item.get("questions") or item.get("question") or "").strip()
        opts = [str(item.get(f"option{i}") or "").strip() for i in range(1, 6)]
        opts = [o for o in opts if o]
        if not q or len(opts) < 2:
            continue
        block = [f"Q{idx}. {q}"]
        for j, opt in enumerate(opts, start=1):
            block.append(f"{_safe_letter(j)}. {opt}")
        ans = int(item.get("answer", 0) or 0)
        if 1 <= ans <= len(opts):
            block.append(f"Answer: {_safe_letter(ans)}")
        blocks.append("\n".join(block))
    if blocks:
        return "\n\n".join(blocks) + "\n\n" + clean_text
    return clean_text


def _ocr_source_hash(ocr_ctx: Dict[str, Any]) -> str:
    base = _build_ocr_quiz_source(ocr_ctx, max_items=40)
    return _hashlib_gemini_patch.sha256(base.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _gen_day_key() -> str:
    return dt.datetime.now(_BD_TZ_MASTER).strftime("%Y-%m-%d")


def _gen_usage_total(user_id: int, day_key: str) -> int:
    _ensure_gemini_runtime_tables()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        f"SELECT COALESCE(SUM(generated_count),0) AS n FROM {_GEMINI_GEN_USAGE_TABLE} WHERE user_id=? AND day_key=?",
        (user_id, day_key),
    )
    row = cur.fetchone()
    conn.close()
    return int(row["n"] or 0) if row else 0


def _gen_usage_page(user_id: int, source_hash: str, day_key: str) -> int:
    _ensure_gemini_runtime_tables()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        f"SELECT generated_count FROM {_GEMINI_GEN_USAGE_TABLE} WHERE user_id=? AND source_hash=? AND day_key=?",
        (user_id, source_hash, day_key),
    )
    row = cur.fetchone()
    conn.close()
    return int(row["generated_count"] or 0) if row else 0


def _gen_usage_add(user_id: int, source_hash: str, day_key: str, amount: int) -> None:
    _ensure_gemini_runtime_tables()
    amount = max(0, int(amount or 0))
    if amount <= 0:
        return
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO {_GEMINI_GEN_USAGE_TABLE}(user_id, source_hash, day_key, generated_count, updated_at) VALUES (?,?,?,?,?) "
        f"ON CONFLICT(user_id, source_hash, day_key) DO UPDATE SET generated_count=generated_count + excluded.generated_count, updated_at=excluded.updated_at",
        (user_id, source_hash, day_key, amount, now_iso()),
    )
    conn.commit()
    conn.close()


def _parse_gen_count(text: str, args: list[str]) -> int:
    tokens = list(args or [])
    if tokens:
        for tok in tokens:
            t = re.sub(r"[^0-9]", "", str(tok or ""))
            if t:
                try:
                    return max(1, int(t))
                except Exception:
                    pass
    m = re.search(r"\b(\d{1,3})\b", str(text or ""))
    if m:
        try:
            return max(1, int(m.group(1)))
        except Exception:
            pass
    return 1


def _split_generation_batches(total: int, batch_size: int = _GEMINI_MAX_BATCH_SIZE) -> list[int]:
    total = max(1, int(total or 1))
    batch_size = max(1, int(batch_size or 1))
    out: list[int] = []
    while total > 0:
        n = min(batch_size, total)
        out.append(n)
        total -= n
    return out


def _verify_mcq_answer(question: str, options: list[str], tentative: int | None = None) -> tuple[int, str]:
    opts = _normalize_options(list(options or []), max_n=4)
    answers: list[int] = []
    explanations: dict[int, str] = {}
    for solver in (gemini_solve_mcq_json, perplexity_solve_mcq_json, deepseek_solve_mcq_json):
        try:
            res = solver(question, opts)
            ans = int(res.get("answer", 0) or 0)
            if 1 <= ans <= len(opts):
                answers.append(ans)
                expl = str(res.get("explanation", "") or "").strip()
                if expl and ans not in explanations:
                    explanations[ans] = expl
        except Exception:
            continue
    if answers:
        counts = _Counter_gemini_patch(answers)
        best_ans, freq = counts.most_common(1)[0]
        if freq >= 2:
            return best_ans, explanations.get(best_ans, "")
        if tentative and 1 <= tentative <= len(opts):
            return tentative, explanations.get(tentative, explanations.get(best_ans, ""))
        return best_ans, explanations.get(best_ans, "")
    if tentative and 1 <= tentative <= len(opts):
        return tentative, ""
    return 1, ""


def _make_gen_prompt(source_text: str, count: int) -> str:
    return (
        "Return STRICT JSON only. No markdown. No extra text.\n"
        f"Create exactly {count} professional MCQ quizzes from the OCR source below.\n"
        "Rules:\n"
        "- Use only the provided source page content.\n"
        "- Keep language consistent with the source page.\n"
        "- Do not duplicate the source questions verbatim.\n"
        "- Each item must have 4 options and exactly one correct answer.\n"
        "- Keep explanations short, exam-style, and accurate.\n"
        "- Prefer the most likely correct answer based on the source content.\n"
        "JSON format exactly:\n"
        '{"items":[{"question":"...","options":["...","...","...","..."],"answer":1,"explanation":"..."}]}\n\n'
        "OCR SOURCE:\n"
        f"{source_text[:16000]}"
    )


def _generate_quizzes_from_ocr_sync(ocr_ctx: Dict[str, Any], desired: int, user_id: int) -> list[Dict[str, Any]]:
    source_text = _build_ocr_quiz_source(ocr_ctx)
    source_text = source_text.strip()
    if not source_text:
        raise RuntimeError("No readable OCR text was found on the replied page.")

    desired = max(1, int(desired or 1))
    batches = _split_generation_batches(desired, batch_size=_GEMINI_MAX_BATCH_SIZE)
    out: list[Dict[str, Any]] = []
    seen: set[str] = set()

    for batch_n in batches:
        prompt = _make_gen_prompt(source_text + "\n\nPreviously generated items must not be repeated.", batch_n)
        raw = None
        # Official Gemini multi-key first, then Perplexity, then Gemini web
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=18, force_json=True)
        except Exception:
            raw = None
        if not raw:
            try:
                raw = query_ai(prompt)
            except Exception:
                raw = None
        if not raw:
            try:
                raw = gemini3_solve(prompt)
            except Exception:
                raw = None
        if not raw:
            continue

        schema_hint = '{"items":[{"question":"...","options":["...","...","...","..."],"answer":1,"explanation":"..."}]}'
        try:
            data = _extract_json_strict(raw)
        except Exception:
            data = _repair_to_json(raw, schema_hint=schema_hint, timeout_seconds=18)
        items = []
        if isinstance(data, dict):
            items = list(data.get("items") or [])

        for it in items:
            q = str(it.get("question") or "").strip()
            opts = _normalize_options([str(x) for x in (it.get("options") or [])], max_n=4)
            tentative = int(it.get("answer", 0) or 0)
            expl = str(it.get("explanation") or "").strip()
            if not q or len(opts) < 4:
                continue
            sig = re.sub(r"\s+", " ", q).lower()
            if sig in seen:
                continue
            seen.add(sig)
            ans, v_expl = _verify_mcq_answer(q, opts, tentative)
            if v_expl:
                expl = v_expl
            out.append({"question": q, "options": opts[:4], "answer": ans, "explanation": expl})
            if len(out) >= desired:
                return out

    return out[:desired]


async def cmd_gemini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = int(update.effective_user.id if update.effective_user else 0)
    if not is_owner(uid):
        await warn(update, "Owner Only", "Only the owner can manage Gemini API keys.")
        return

    _ensure_gemini_runtime_tables()
    args = [str(a).strip() for a in (context.args or []) if str(a).strip()]
    action = (args[0].lower() if args else "status")
    rest = " ".join(args[1:]).strip() if len(args) > 1 else ""

    if action in ("status", "show"):
        await ok_html(update, "Gemini Key Status", _gemini_runtime_report_html(), emoji="🔐")
        return

    if action == "list":
        rows = _gemini_key_rows(include_disabled=True)
        lines = []
        for r in rows:
            lines.append(
                f"<b>ID</b>: <code>{h(str(r.get('id')))}</code> | "
                f"<b>Key</b>: <code>{h(_normalize_secret_mask(str(r.get('api_key') or '')))}</code> | "
                f"<b>Label</b>: {h(str(r.get('label') or ''))} | "
                f"<b>Status</b>: {h(str(r.get('last_status') or ''))} | "
                f"<b>Enabled</b>: {h('YES' if int(r.get('is_enabled') or 0) == 1 else 'NO')}"
            )
        await ok_html(update, "Gemini Keys", "\n".join(lines) if lines else "No keys saved.", emoji="📋")
        return

    if action == "add":
        if not rest:
            await safe_reply(update, usage_box("gemini", "add YOUR_KEY [label]", "Add a Gemini API key to the bot."))
            return
        parts = rest.split(maxsplit=1)
        key = parts[0].strip()
        label = parts[1].strip() if len(parts) > 1 else ""
        if _gemini_add_key(key, label):
            await ok_html(update, "Gemini Key Added", f"Saved key: <code>{h(_normalize_secret_mask(key))}</code>", emoji="🔑")
            return
        await err(update, "Add Failed", "Could not save the Gemini key.")
        return

    if action == "remove":
        if not rest:
            await safe_reply(update, usage_box("gemini", "remove <id|secret|label>", "Delete a saved Gemini key."))
            return
        if _gemini_remove_key(rest):
            await ok_html(update, "Gemini Key Removed", f"Removed: <code>{h(rest)}</code>", emoji="🗑️")
        else:
            await err(update, "Remove Failed", "Key not found.")
        return

    if action in ("enable", "disable"):
        if not rest:
            await safe_reply(update, usage_box("gemini", f"{action} <id|secret|label>", "Enable or disable a saved Gemini key."))
            return
        ok = _gemini_set_key_enabled(rest, action == "enable")
        if ok:
            await ok_html(update, "Gemini Key Updated", f"Key {h(rest)} -> <code>{h(action.upper())}</code>", emoji="✅")
        else:
            await err(update, "Update Failed", "Key not found.")
        return

    if action == "clear":
        count = _gemini_clear_all_keys()
        await ok_html(update, "Gemini Keys Cleared", f"Removed <code>{h(str(count))}</code> saved Gemini keys.", emoji="🧹")
        return

    await safe_reply(
        update,
        usage_box(
            "gemini",
            "<status|list|add KEY [label]|remove ID|enable ID|disable ID|clear>",
            "Manage multiple Gemini API keys with automatic sequential failover.\n\nTip: /models shows the active model order."
        ),
    )


async def cmd_pans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Alias for the direct answer command.
    if "cmd_qans" in globals():
        return await globals()["cmd_qans"](update, context)
    await err(update, "Unavailable", "Direct answer mode is not available right now.")


async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = int(update.effective_user.id)
    if is_banned(uid):
        return

    reply_msg = update.message.reply_to_message
    if not reply_msg:
        await safe_reply(update, usage_box("gen", "[count]", "Reply to a page image, OCR message, or supported document and run /gen."))
        return

    requested = _parse_gen_count(update.message.text or "", list(context.args or []))
    is_staff = is_owner(uid) or is_admin(uid)

    # Need OCR context from replied message or direct OCR extraction.
    ocr_ctx = None
    reply_has_ctx = _has_ocr_context(context, reply_msg) if "_has_ocr_context" in globals() else False
    if reply_has_ctx:
        ocr_ctx = _get_ocr_context(context, reply_msg.message_id)

    reply_is_media = bool(
        getattr(reply_msg, "photo", None) or getattr(reply_msg, "document", None)
    )

    local_path = None
    if not ocr_ctx and reply_is_media:
        if not mistral_runtime_enabled():
            await safe_reply(update, "OCR is temporarily disabled. Please try again later.")
            return
        if not get_mistral_api_key():
            await warn(update, "OCR Unavailable", "The bot owner has not configured an active OCR key yet.")
            return
        try:
            if reply_msg.document:
                suffix = os.path.splitext(str(reply_msg.document.file_name or ""))[1].strip() or ".jpg"
                if len(suffix) > 6:
                    suffix = ".jpg"
                tg_file = await reply_msg.document.get_file()
            else:
                suffix = ".jpg"
                tg_file = await reply_msg.photo[-1].get_file()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                local_path = f.name
            await tg_file.download_to_drive(local_path)
            bundle = await _run_blocking(_role_of(uid), _extract_ocr_bundle_from_path, local_path, uid, timeout=300)
            ocr = bundle.get("ocr") or {}
            ocr_ctx = {
                "raw_markdown": str(ocr.get("raw_markdown") or ""),
                "clean_text": str(bundle.get("clean_text") or ""),
                "items": list(bundle.get("items") or []),
                "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
                "page_count": len(ocr.get("pages") or []),
            }
            _remember_ocr_context(context, reply_msg.message_id, ocr_ctx)
        except Exception as e:
            db_log("ERROR", "gen_ocr_failed", {"user_id": uid, "error": str(e)})
            await err(update, "OCR Failed", str(e)[:220])
            return
        finally:
            if local_path:
                with contextlib.suppress(Exception):
                    os.remove(local_path)

    if not ocr_ctx:
        await warn(update, "No OCR Context", "Reply to a page image or an OCR-scanned message first.")
        return

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
                update,
                "Generation Limit Reached",
                f"This page has reached your daily limit.\n"
                f"Page limit: <code>{h(str(_GEMINI_DEFAULT_PAGE_DAILY_LIMIT))}</code>\n"
                f"Daily limit: <code>{h(str(_GEMINI_DEFAULT_USER_DAILY_LIMIT))}</code>",
                emoji="⛔",
            )
            return
    else:
        allowed = requested

    proc = None
    try:
        proc = await _processing_start(update.message, "Generating Quizzes", f"Creating {allowed} quiz item(s)...")
    except Exception:
        proc = None

    try:
        items = await _run_blocking(_role_of(uid), _generate_quizzes_from_ocr_sync, ocr_ctx, allowed, uid, timeout=360)
        if not items:
            raise RuntimeError("No quiz items could be generated from this page.")

        chat_id = update.message.chat_id
        lock = _get_chat_lock(context, chat_id)
        qpfx = (get_setting("quiz_prefix", "প্রবাহ") or "প্রবাহ").strip()
        qlink = (get_setting("quiz_expl_link", "") or "").strip()

        async with lock:
            for item in items[:allowed]:
                q = str(item.get("question") or "").strip()
                opts = _normalize_options([str(x) for x in (item.get("options") or [])], max_n=4)
                ans = int(item.get("answer", 1) or 1)
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
                await asyncio.sleep(0.35)

        if not is_staff:
            _gen_usage_add(uid, source_hash, day_key, len(items[:allowed]))

        if proc:
            with contextlib.suppress(Exception):
                await _processing_delete(proc)
        await safe_reply(update, ui_box_text("Quiz Generated", f"Generated <b>{h(str(len(items[:allowed])))}</b> quiz item(s).", emoji="📊"))
    except Exception as e:
        if proc:
            with contextlib.suppress(Exception):
                await _processing_delete(proc)
        db_log("ERROR", "gen_quiz_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Generate Quiz Failed", str(e)[:220])


# Patch OCR bundle extraction to normalize text before downstream parsing.
if "_extract_ocr_bundle_from_path" in globals():
    _prev_extract_ocr_bundle_from_path_gemini = _extract_ocr_bundle_from_path

    def _extract_ocr_bundle_from_path(local_path: str, user_id: int) -> Dict[str, Any]:  # noqa: F811
        bundle = _prev_extract_ocr_bundle_from_path_gemini(local_path, user_id)
        try:
            clean_text = _normalize_ocr_quiz_text(str(bundle.get("clean_text") or ""))
            bundle["clean_text"] = clean_text
            if isinstance(bundle.get("items"), list):
                bundle["items"] = list(bundle.get("items") or [])
            bundle["source_hash"] = _hashlib_gemini_patch.sha256(clean_text.encode("utf-8", errors="ignore")).hexdigest()[:16]
        except Exception:
            pass
        return bundle


if "_all_commands_for" in globals():
    _prev_all_commands_for_gemini_patch = _all_commands_for

    def _all_commands_for(user_id: int):
        sections = list(_prev_all_commands_for_gemini_patch(user_id))
        role = get_role(int(user_id or 0))
        extra_items = []
        if role in (ROLE_ADMIN, ROLE_OWNER):
            extra_items.extend([
                ("/gemini", "Manage Gemini API keys"),
                ("/gen", "Generate quizzes from replied page image"),
                ("/pans", "Direct answer from reply"),
            ])
        if not extra_items:
            return sections
        inserted = False
        new_sections = []
        for title, items in sections:
            if "Staff Commands" in str(title):
                merged = list(items) + extra_items
                new_sections.append((title, merged))
                inserted = True
            else:
                new_sections.append((title, items))
        if not inserted:
            new_sections.append(("🛠 Staff Commands", extra_items))
        return new_sections


_prev_build_app_gemini_patch = build_app

def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_gemini_patch()
    private_filter = filters.ChatType.PRIVATE
    _register_dual_command(app, "gemini", cmd_gemini, private_filter, group=-100)
    _register_dual_command(app, "gen", cmd_gen, group=-100)
    _register_dual_command(app, "pans", cmd_pans, group=-100)
    _register_dual_command(app, "ans", cmd_pans, group=-100)
    return app

logger.info("[GEMINI PATCH] Multi-key Gemini routing + /gemini + /gen + /pans loaded.")
# ===== END GEMINI MULTI-KEY + /GEN QUIZ PATCH =====

