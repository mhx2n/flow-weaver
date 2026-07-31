# ──────────────────────────────────────────────────────────────────────────────
# Section: 31_multi_key_mistral_user_reply_ocr_04_10
# Original lines: 16369..17419
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== MULTI-KEY MISTRAL + USER REPLY OCR PATCH (2026-04-10) =====
from telegram.ext import ApplicationHandlerStop
import hashlib

_BD_TZ = dt.timezone(dt.timedelta(hours=6))


def _today_bd_key() -> str:
    return dt.datetime.now(_BD_TZ).strftime("%Y-%m-%d")


def _ensure_mistral_runtime_tables() -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mistral_api_keys (
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
        """
        CREATE TABLE IF NOT EXISTS user_ocr_daily_usage (
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            used_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, day_key)
        )
        """
    )
    conn.commit()
    conn.close()
    _migrate_legacy_mistral_key_if_needed()


def _migrate_legacy_mistral_key_if_needed() -> None:
    legacy = str(get_setting("mistral_api_key", "") or os.getenv("MISTRAL_API_KEY", "") or "").strip()
    if not legacy:
        return
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM mistral_api_keys WHERE api_key=?", (legacy,))
    row = cur.fetchone()
    if not row:
        ts = now_iso()
        cur.execute(
            "INSERT OR IGNORE INTO mistral_api_keys(api_key,label,is_enabled,last_status,fail_count,last_error,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (legacy, "legacy", 1, "migrated", 0, "", ts, ts),
        )
        conn.commit()
    conn.close()


def _mistral_key_rows(include_disabled: bool = True) -> List[sqlite3.Row]:
    _ensure_mistral_runtime_tables()
    conn = db_connect()
    cur = conn.cursor()
    if include_disabled:
        cur.execute("SELECT * FROM mistral_api_keys ORDER BY id ASC")
    else:
        cur.execute("SELECT * FROM mistral_api_keys WHERE is_enabled=1 ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def _mistral_key_id_from_selector(selector: str) -> Optional[int]:
    raw = str(selector or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    rows = _mistral_key_rows(include_disabled=True)
    raw_low = raw.lower()
    for row in rows:
        masked = _mask_secret(row["api_key"])
        if raw_low in masked.lower():
            return int(row["id"])
    return None


def _mistral_add_key(secret: str, label: str = "") -> bool:
    key = str(secret or "").strip()
    if not key:
        return False
    _ensure_mistral_runtime_tables()
    conn = db_connect()
    cur = conn.cursor()
    ts = now_iso()
    cur.execute(
        "INSERT OR IGNORE INTO mistral_api_keys(api_key,label,is_enabled,last_status,fail_count,last_error,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (key, str(label or "").strip(), 1, "ready", 0, "", ts, ts),
    )
    changed = cur.rowcount > 0
    if not changed:
        cur.execute("UPDATE mistral_api_keys SET is_enabled=1, updated_at=? WHERE api_key=?", (ts, key))
        changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def _mistral_remove_key(selector: str) -> bool:
    key_id = _mistral_key_id_from_selector(selector)
    if not key_id:
        return False
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM mistral_api_keys WHERE id=?", (key_id,))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def _mistral_clear_all_keys() -> int:
    _ensure_mistral_runtime_tables()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM mistral_api_keys")
    count = int(cur.rowcount or 0)
    conn.commit()
    conn.close()
    return count


def _mistral_set_key_enabled(selector: str, enabled: bool) -> bool:
    key_id = _mistral_key_id_from_selector(selector)
    if not key_id:
        return False
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE mistral_api_keys SET is_enabled=?, updated_at=? WHERE id=?",
        (1 if enabled else 0, now_iso(), key_id),
    )
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def _mistral_mark_key_status(key_id: int, status: str, error_text: str = "") -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE mistral_api_keys SET last_status=?, last_error=?, fail_count=CASE WHEN ?='ok' THEN 0 ELSE fail_count+1 END, updated_at=? WHERE id=?",
        (str(status or "")[:48], str(error_text or "")[:260], str(status or ""), now_iso(), int(key_id)),
    )
    conn.commit()
    conn.close()


def get_mistral_api_keys() -> List[Dict[str, Any]]:
    rows = _mistral_key_rows(include_disabled=False)
    out = []
    for row in rows:
        out.append({
            "id": int(row["id"]),
            "api_key": str(row["api_key"] or "").strip(),
            "label": str(row["label"] or "").strip(),
            "last_status": str(row["last_status"] or "").strip(),
            "last_error": str(row["last_error"] or "").strip(),
            "is_enabled": int(row["is_enabled"] or 0) == 1,
        })
    return out


def get_mistral_api_key() -> str:
    keys = get_mistral_api_keys()
    if keys:
        return str(keys[0].get("api_key") or "").strip()
    return str(os.getenv("MISTRAL_API_KEY", "") or "").strip()


def get_mistral_user_daily_limit() -> int:
    try:
        val = int(str(get_setting("mistral_user_daily_limit", "3") or "3").strip())
        return max(0, min(val, 100))
    except Exception:
        return 3


def set_mistral_user_daily_limit(value: int) -> None:
    set_setting("mistral_user_daily_limit", str(max(0, min(int(value), 100))))


def _get_user_ocr_usage(user_id: int, day_key: Optional[str] = None) -> int:
    _ensure_mistral_runtime_tables()
    day_key = str(day_key or _today_bd_key())
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT used_count FROM user_ocr_daily_usage WHERE user_id=? AND day_key=?", (int(user_id), day_key))
    row = cur.fetchone()
    conn.close()
    return int(row["used_count"] or 0) if row else 0


def _inc_user_ocr_usage(user_id: int, amount: int = 1) -> int:
    _ensure_mistral_runtime_tables()
    day_key = _today_bd_key()
    amount = max(1, int(amount or 1))
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT used_count FROM user_ocr_daily_usage WHERE user_id=? AND day_key=?", (int(user_id), day_key))
    row = cur.fetchone()
    used = int(row["used_count"] or 0) if row else 0
    new_used = used + amount
    cur.execute(
        "INSERT INTO user_ocr_daily_usage(user_id, day_key, used_count, updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id, day_key) DO UPDATE SET used_count=excluded.used_count, updated_at=excluded.updated_at",
        (int(user_id), day_key, new_used, now_iso()),
    )
    conn.commit()
    conn.close()
    return new_used


def _remaining_user_ocr_quota(user_id: int) -> int:
    limit = get_mistral_user_daily_limit()
    if limit <= 0:
        return 0
    return max(0, limit - _get_user_ocr_usage(user_id))


def _mistral_error_kind(status_code: int, body_text: str) -> str:
    text = str(body_text or "").lower()
    if status_code in (429,):
        return "limit"
    if status_code in (401,):
        return "auth"
    if status_code in (403,) and any(k in text for k in ["quota", "limit", "rate", "billing", "workspace"]):
        return "limit"
    if status_code in (403,):
        return "auth"
    if status_code in (400, 404):
        return "bad_request"
    if status_code in (500, 502, 503, 504):
        return "server"
    if any(k in text for k in ["rate limit", "quota", "resource_exhausted", "too many requests"]):
        return "limit"
    return "other"


def _mistral_post_json(url: str, api_key: str, payload: Dict[str, Any], timeout: int = 90):
    return requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )


def _mistral_upload_file_for_key(path: str, api_key: str) -> Tuple[bool, Any]:
    filename = os.path.basename(path)
    mime = _guess_mime_type(path)
    with open(path, "rb") as f:
        files = {"file": (filename, f, mime)}
        data = {"purpose": "ocr", "visibility": "user"}
        resp = requests.post(
            "https://api.mistral.ai/v1/files",
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
            timeout=60,
        )
    if resp.status_code != 200:
        return False, (resp.status_code, resp.text[:300])
    payload = resp.json()
    file_id = str(payload.get("id") or "").strip()
    if not file_id:
        return False, (500, "Mistral file upload did not return a file id.")
    return True, file_id


def _mistral_ocr_with_failover(path: str) -> Dict[str, Any]:
    keys = get_mistral_api_keys()
    if not keys:
        single = str(os.getenv("MISTRAL_API_KEY", "") or "").strip()
        if single:
            keys = [{"id": 0, "api_key": single, "label": "env", "last_status": "", "last_error": "", "is_enabled": True}]
    if not keys:
        raise RuntimeError("No Mistral API key configured. Use /mistral add YOUR_KEY first.")

    mime = _guess_mime_type(path)
    size_bytes = 0
    with contextlib.suppress(Exception):
        size_bytes = int(os.path.getsize(path) or 0)

    last_error = None
    limit_failures = []

    for key_info in keys:
        key_id = int(key_info.get("id") or 0)
        api_key = str(key_info.get("api_key") or "").strip()
        if not api_key:
            continue
        try:
            doc_payload = None
            if mime.startswith("image/") and size_bytes <= 6 * 1024 * 1024:
                raw_bytes = Path(path).read_bytes()
                b64 = base64.b64encode(raw_bytes).decode("utf-8")
                doc_payload = {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"}
            else:
                ok, up_res = _mistral_upload_file_for_key(path, api_key)
                if not ok:
                    status_code, body = up_res
                    kind = _mistral_error_kind(int(status_code), str(body))
                    _mistral_mark_key_status(key_id, kind, f"upload: {body}")
                    last_error = RuntimeError(f"upload failed ({status_code})")
                    if kind == "limit":
                        limit_failures.append(_mask_secret(api_key))
                        continue
                    if kind in {"auth", "server", "bad_request", "other"}:
                        continue
                doc_payload = {"type": "file", "file_id": str(up_res)}

            resp = _mistral_post_json(
                "https://api.mistral.ai/v1/ocr",
                api_key,
                {"model": MISTRAL_OCR_MODEL, "document": doc_payload, "include_image_base64": False},
                timeout=120,
            )
            if resp.status_code != 200:
                kind = _mistral_error_kind(resp.status_code, resp.text)
                _mistral_mark_key_status(key_id, kind, resp.text[:260])
                last_error = RuntimeError(f"ocr failed ({resp.status_code})")
                if kind == "limit":
                    limit_failures.append(_mask_secret(api_key))
                    continue
                if kind in {"auth", "server", "bad_request", "other"}:
                    continue
            data = resp.json()
            if not isinstance(data, dict):
                _mistral_mark_key_status(key_id, "bad_response", "invalid JSON response")
                last_error = RuntimeError("Mistral OCR returned an invalid response.")
                continue
            pages = data.get("pages", []) or []
            chunks = []
            for page in pages:
                md = str((page or {}).get("markdown") or "").strip()
                if md:
                    chunks.append(md)
            raw_markdown = "\n\n".join(chunks).strip()
            _mistral_mark_key_status(key_id, "ok", "")
            return {
                "raw_markdown": raw_markdown,
                "pages": pages,
                "model": str(data.get("model") or MISTRAL_OCR_MODEL),
                "usage_info": data.get("usage_info") or {},
                "response": data,
                "used_key_mask": _mask_secret(api_key),
                "limit_failures": list(limit_failures),
            }
        except Exception as e:
            _mistral_mark_key_status(key_id, "error", str(e)[:260])
            last_error = e
            continue

    if limit_failures:
        raise RuntimeError("All active Mistral keys are limited/exhausted right now. Failed keys: " + ", ".join(limit_failures[:8]))
    raise RuntimeError(str(last_error or "Mistral OCR failed."))


def _mistral_ocr_process_path(path: str) -> Dict[str, Any]:
    return _mistral_ocr_with_failover(path)


def _question_no_key(text: str) -> str:
    s = clean_latex(str(text or "")).strip()
    m = re.match(r"^\s*([0-9\u09E6-\u09EF]{1,4})", s)
    if not m:
        return ""
    return m.group(1)


def _option_overlap_score(a_opts: List[str], b_opts: List[str]) -> float:
    if not a_opts or not b_opts:
        return 0.0
    scores = []
    for ao in a_opts[:5]:
        na = _normalize_option_text_for_match(ao)
        best = 0.0
        for bo in b_opts[:5]:
            nb = _normalize_option_text_for_match(bo)
            if not na or not nb:
                continue
            if na == nb:
                best = 1.0
                break
            best = max(best, SequenceMatcher(None, na, nb).ratio())
        scores.append(best)
    return sum(scores) / max(1, len(scores))


def _best_match_visual_item(visual_item: Dict[str, Any], base_items: List[Dict[str, Any]]) -> int:
    vq = str(visual_item.get("questions") or "").strip()
    vopts = [str(visual_item.get(f"option{i}") or "").strip() for i in range(1, 6) if str(visual_item.get(f"option{i}") or "").strip()]
    vno = _question_no_key(vq)
    best_idx = -1
    best_score = 0.0
    for idx, item in enumerate(base_items):
        iq = str(item.get("questions") or "").strip()
        iopts = [str(item.get(f"option{i}") or "").strip() for i in range(1, 6) if str(item.get(f"option{i}") or "").strip()]
        ino = _question_no_key(iq)
        qscore = SequenceMatcher(None, _normalize_option_text_for_match(vq), _normalize_option_text_for_match(iq)).ratio()
        oscore = _option_overlap_score(vopts, iopts)
        score = (0.68 * qscore) + (0.32 * oscore)
        if vno and ino and vno == ino:
            score += 0.22
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx if best_score >= 0.58 else -1


def _vision_marked_answer_prompt() -> str:
    return (
        "Return STRICT JSON only. No markdown. No extra text.\n"
        "Task: analyze this exam page image and find ONLY MCQs whose correct option is explicitly marked or written on the page.\n"
        "A correct answer counts as explicit only if there is a visible dot, circle, tick, check, highlight, underline, side-note like Ans:, solution label, or any other clear visual marker.\n"
        "If the answer is unclear, omit that question entirely.\n"
        "Keep the original language. Preserve the question and option texts enough to match the page.\n"
        "JSON format:\n"
        '{"items":[{"questions":"...","option1":"...","option2":"...","option3":"...","option4":"...","option5":"","answer":1,"correct_option_text":"...","marker_type":"highlight|dot|ans_text|tick|circle|underline","marker_confidence":90}]}'
    )


def _visual_marked_items_from_image(image_path: str) -> List[Dict[str, Any]]:
    if not GEMINI_API_KEYS:
        return []
    prompt = _vision_marked_answer_prompt()
    try:
        raw = call_gemini_vision_rest(image_path, prompt, force_json=True)
        data = _extract_json_strict(raw)
    except Exception:
        return []
    items = []
    if not isinstance(data, dict):
        return items
    for it in (data.get("items") or [])[:80]:
        try:
            answer = int(it.get("answer", 0) or 0)
        except Exception:
            answer = 0
        options = [str(it.get(f"option{i}") or "").strip() for i in range(1, 6) if str(it.get(f"option{i}") or "").strip()]
        if len(options) < 2 or answer <= 0 or answer > len(options):
            mapped = _match_answer_text_to_options(str(it.get("correct_option_text") or ""), options)
            answer = mapped if mapped else 0
        if len(options) < 2 or not (1 <= answer <= len(options)):
            continue
        conf = 0
        with contextlib.suppress(Exception):
            conf = int(it.get("marker_confidence", 0) or 0)
        if conf and conf < 55:
            continue
        payload = {
            "questions": str(it.get("questions") or "").strip(),
            "option1": options[0] if len(options) > 0 else "",
            "option2": options[1] if len(options) > 1 else "",
            "option3": options[2] if len(options) > 2 else "",
            "option4": options[3] if len(options) > 3 else "",
            "option5": options[4] if len(options) > 4 else "",
            "answer": answer,
            "explanation": "",
            "marker_type": str(it.get("marker_type") or "").strip(),
        }
        if payload["questions"]:
            items.append(payload)
    return items


def _render_pdf_to_page_images(pdf_path: str) -> List[str]:
    import fitz
    paths: List[str] = []
    doc = None
    tmp_dir = tempfile.mkdtemp(prefix="probaho_pdf_pages_")
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        for idx in range(total_pages):
            page = doc.load_page(idx)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            out_path = os.path.join(tmp_dir, f"page_{idx+1}.png")
            pix.save(out_path)
            paths.append(out_path)
    except Exception:
        for p in list(paths):
            with contextlib.suppress(Exception):
                os.remove(p)
        with contextlib.suppress(Exception):
            os.rmdir(tmp_dir)
        return []
    finally:
        with contextlib.suppress(Exception):
            if doc is not None:
                doc.close()
    return paths


def _collect_visual_marked_items_for_path(path: str) -> List[Dict[str, Any]]:
    mime = _guess_mime_type(path)
    if mime == "application/pdf":
        page_paths = _render_pdf_to_page_images(path)
        if not page_paths:
            return []
        out: List[Dict[str, Any]] = []
        try:
            for pp in page_paths:
                out.extend(_visual_marked_items_from_image(pp))
        finally:
            for pp in page_paths:
                with contextlib.suppress(Exception):
                    os.remove(pp)
            with contextlib.suppress(Exception):
                os.rmdir(os.path.dirname(page_paths[0]))
        return out
    if mime.startswith("image/"):
        return _visual_marked_items_from_image(path)
    return []


def _merge_visual_marked_answers(base_items: List[Dict[str, Any]], visual_items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    merged = [dict(x or {}) for x in (base_items or [])]
    applied = 0
    for v in (visual_items or []):
        if int(v.get("answer", 0) or 0) <= 0:
            continue
        idx = _best_match_visual_item(v, merged)
        if idx >= 0:
            cur_ans = int(merged[idx].get("answer", 0) or 0)
            if cur_ans != int(v.get("answer", 0) or 0):
                merged[idx]["answer"] = int(v.get("answer", 0) or 0)
                if not str(merged[idx].get("explanation") or "").strip():
                    merged[idx]["explanation"] = "Detected from visible answer marking."
                applied += 1
            elif cur_ans > 0:
                applied += 1
            continue
        q = str(v.get("questions") or "").strip()
        opts = [str(v.get(f"option{i}") or "").strip() for i in range(1, 6) if str(v.get(f"option{i}") or "").strip()]
        if q and len(opts) >= 2:
            merged.append({
                "questions": q,
                "option1": opts[0] if len(opts) > 0 else "",
                "option2": opts[1] if len(opts) > 1 else "",
                "option3": opts[2] if len(opts) > 2 else "",
                "option4": opts[3] if len(opts) > 3 else "",
                "option5": opts[4] if len(opts) > 4 else "",
                "answer": int(v.get("answer", 0) or 0),
                "explanation": "Detected from visible answer marking.",
                "type": 1,
                "section": 1,
            })
            applied += 1
    return merged, applied


def _drop_unclear_mcq_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned = []
    seen = set()
    for it in items or []:
        q = str(it.get("questions") or "").strip()
        opts = [str(it.get(f"option{i}") or "").strip() for i in range(1, 6) if str(it.get(f"option{i}") or "").strip()]
        if not q or len(opts) < 2:
            continue
        norm_q = _normalize_option_text_for_match(q)
        if not norm_q or len(norm_q) < 6:
            continue
        key = (q[:120], tuple(opts[:4]))
        if key in seen:
            continue
        seen.add(key)
        if int(it.get("answer", 0) or 0) < 0 or int(it.get("answer", 0) or 0) > len(opts):
            it["answer"] = 0
        cleaned.append(it)
    return cleaned


def _extract_ocr_bundle_from_path(local_path: str, user_id: int) -> Dict[str, Any]:
    ocr = _mistral_ocr_process_path(local_path)
    pages = list(ocr.get("pages") or [])
    clean_text, items = _ocr_pages_to_clean_text_and_items(pages, user_id)
    visual_items = _collect_visual_marked_items_for_path(local_path)
    items, visual_applied = _merge_visual_marked_answers(items, visual_items)
    items = _drop_unclear_mcq_items(items)
    return {
        "ocr": ocr,
        "clean_text": clean_text,
        "items": items,
        "visual_marked_count": int(visual_applied or 0),
    }


def _mistral_status_body_html() -> str:
    rows = _mistral_key_rows(include_disabled=True)
    lines = [
        f"Enabled: <code>{'ON' if mistral_runtime_enabled() else 'OFF'}</code>",
        f"Model: <code>{h(MISTRAL_OCR_MODEL)}</code>",
        f"User daily limit: <code>{h(str(get_mistral_user_daily_limit()))}</code>",
        f"Active keys: <code>{h(str(len([r for r in rows if int(r['is_enabled'] or 0) == 1])) )}</code>",
    ]
    if rows:
        lines.append("")
        lines.append("<b>Saved keys</b>")
        for row in rows:
            status = str(row["last_status"] or "ready").strip() or "ready"
            extra = str(row["last_error"] or "").strip()
            label = str(row["label"] or "").strip()
            prefix = f"#{int(row['id'])}"
            bits = [prefix, _mask_secret(str(row["api_key"] or "")), "ON" if int(row["is_enabled"] or 0) == 1 else "OFF", status]
            if label:
                bits.append(label)
            line = " • ".join(bits)
            if extra:
                line += f"\n<code>{h(extra[:120])}</code>"
            lines.append(line)
    else:
        lines.append("\n<b>No saved Mistral keys.</b>")
    return "\n".join(lines)


async def cmd_mistral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id if update.effective_user else 0
    if not is_private_chat(update):
        await warn(update, "Private Only", "Use this command in private chat with the bot.")
        return
    _ensure_mistral_runtime_tables()
    args = list(context.args or [])
    action = (args[0] if args else "status").strip().lower()
    rest = args[1:]
    remainder = " ".join(rest).strip()
    if not remainder and update.message.reply_to_message:
        remainder = reply_text_or_caption(update)

    owner_only_actions = {"add", "set", "remove", "delete", "del", "clear", "enablekey", "disablekey", "limit", "on", "off", "enable", "disable"}
    if action in owner_only_actions and not is_owner(uid):
        await warn(update, "Owner Only", "Only the owner can change Mistral keys or OCR limits.")
        return

    if action in {"status", "info", "list"}:
        await ok_html(update, "Mistral OCR Status", _mistral_status_body_html(), emoji="🧾")
        return

    if action in {"on", "enable"}:
        _set_setting_bool("mistral_enabled", True)
        await ok_html(update, "Mistral OCR Enabled", "OCR is now active. The bot will fail over to the next saved key if the current key is limited.", emoji="✅")
        return

    if action in {"off", "disable"}:
        _set_setting_bool("mistral_enabled", False)
        await ok_html(update, "Mistral OCR Disabled", "OCR is now turned off.", emoji="✅")
        return

    if action in {"limit"}:
        if not remainder or not str(remainder).strip().isdigit():
            await safe_reply(update, usage_box("mistral", "limit <number>", "Example:\n/mistral limit 5"))
            return
        set_mistral_user_daily_limit(int(str(remainder).strip()))
        await ok_html(update, "User OCR Limit Updated", f"New daily OCR limit per normal user: <code>{h(str(get_mistral_user_daily_limit()))}</code>", emoji="🎚️")
        return

    if action in {"add", "set"}:
        candidate = str(remainder or "").strip()
        if not candidate:
            await safe_reply(update, usage_box("mistral", "add YOUR_KEY", "Examples:\n/mistral add YOUR_MISTRAL_KEY\n/mistral list\n/mistral remove 2\n/mistral limit 5"))
            return
        m = re.search(r"(?:mistral|ma)_?[A-Za-z0-9\-_]+", candidate)
        if m:
            candidate = m.group(0)
        if not _mistral_add_key(candidate):
            await warn(update, "Key Already Saved", f"This key is already stored or could not be added: <code>{h(_mask_secret(candidate))}</code>")
            return
        await ok_html(update, "Mistral API Key Added", f"Saved key: <code>{h(_mask_secret(candidate))}</code>\nActive key count: <code>{h(str(len(get_mistral_api_keys())))}</code>", emoji="🔐")
        return

    if action in {"remove", "delete", "del"}:
        selector = str(remainder or "").strip()
        if not selector:
            await safe_reply(update, usage_box("mistral", "remove <id>", "Use /mistral list to see saved key ids. Use /mistral clear to remove all keys."))
            return
        if not _mistral_remove_key(selector):
            await warn(update, "Key Not Found", "No saved key matched that selector.")
            return
        await ok_html(update, "Mistral Key Removed", f"Removed key selector: <code>{h(selector)}</code>", emoji="🗑️")
        return

    if action in {"clear"}:
        count = _mistral_clear_all_keys()
        set_setting("mistral_api_key", "")
        await ok_html(update, "All Mistral Keys Deleted", f"Deleted <code>{h(str(count))}</code> saved key(s).", emoji="🗑️")
        return

    if action in {"enablekey", "disablekey"}:
        selector = str(remainder or "").strip()
        if not selector:
            await safe_reply(update, usage_box("mistral", f"{action} <id>", "Use /mistral list to see saved key ids."))
            return
        ok = _mistral_set_key_enabled(selector, action == "enablekey")
        if not ok:
            await warn(update, "Key Not Found", "No saved key matched that selector.")
            return
        await ok_html(update, "Mistral Key Updated", f"Key <code>{h(selector)}</code> is now <code>{'enabled' if action == 'enablekey' else 'disabled'}</code>.", emoji="✅")
        return

    await safe_reply(update, usage_box("mistral", "<status|list|on|off|add KEY|remove ID|clear|limit N|enablekey ID|disablekey ID>", "Manage multiple Mistral OCR keys with automatic failover."))


def _answer_user_question_from_ocr(clean_text: str, user_question: str) -> Tuple[str, str]:
    body = _basic_ocr_text_cleanup(clean_text)
    user_q = str(user_question or "").strip()
    prompt = (
        "The following text was extracted from a replied file using OCR.\n"
        "Answer only the user's question using the OCR text.\n"
        "If the OCR contains an MCQ and the answer is visible, mention the correct option clearly.\n"
        "Use Telegram-friendly plain text. No LaTeX.\n\n"
        f"User question:\n{user_q[:1200]}\n\nOCR TEXT:\n{body[:14000]}"
    )
    return _solve_text_with_preference("G", prompt, "private_academic")


def _is_supported_ocr_media_message(msg) -> bool:
    if not msg:
        return False
    if getattr(msg, "photo", None):
        return True
    doc = getattr(msg, "document", None)
    if not doc:
        return False
    mime = str(getattr(doc, "mime_type", "") or "").lower()
    name = str(getattr(doc, "file_name", "") or "").lower()
    return mime.startswith("image/") or mime == "application/pdf" or name.endswith(".pdf")


async def handle_user_reply_ocr_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user or not is_private_chat(update):
        return
    uid = int(update.effective_user.id)
    if is_banned(uid) or get_role(uid) != ROLE_USER:
        return
    if not update.message.reply_to_message:
        return
    if not _is_supported_ocr_media_message(update.message.reply_to_message):
        return
    user_question = str(update.message.text or "").strip()
    if not user_question or user_question.startswith("/"):
        return
    if not mistral_runtime_enabled():
        return
    if not get_mistral_api_key():
        await warn(update, "OCR Unavailable", "The bot owner has not configured any active Mistral OCR key yet.")
        raise ApplicationHandlerStop

    reply_msg = update.message.reply_to_message
    cached = _get_ocr_context(context, reply_msg.message_id)
    if not cached:
        remaining = _remaining_user_ocr_quota(uid)
        if remaining <= 0:
            await _send_ocr_limit_warning(update, get_mistral_user_daily_limit())
            raise ApplicationHandlerStop

    proc = await _processing_start(update.message, "Processing OCR Question", "Reading the replied file and preparing an answer...")
    local_path = None
    try:
        ocr_ctx = cached
        if not ocr_ctx:
            reply_doc = reply_msg.document
            suffix = ".jpg"
            if reply_doc:
                name = str(reply_doc.file_name or "").lower()
                if name.endswith(".pdf") or str(getattr(reply_doc, "mime_type", "") or "").lower() == "application/pdf":
                    suffix = ".pdf"
                else:
                    ext = os.path.splitext(name)[1].strip() or ".jpg"
                    suffix = ext if len(ext) <= 6 else ".jpg"
                tg_file = await reply_doc.get_file()
            else:
                tg_file = await reply_msg.photo[-1].get_file()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                local_path = f.name
            await tg_file.download_to_drive(local_path)
            await _processing_update(proc, "Processing OCR Question", "Running OCR and detecting visible marked answers...")
            bundle = await _run_blocking(_role_of(uid), _extract_ocr_bundle_from_path, local_path, uid, timeout=300)
            ocr = bundle["ocr"]
            ocr_ctx = {
                "raw_markdown": str(ocr.get("raw_markdown") or ""),
                "clean_text": str(bundle.get("clean_text") or ""),
                "items": list(bundle.get("items") or []),
                "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
                "page_count": len(ocr.get("pages") or []),
                "used_key_mask": str(ocr.get("used_key_mask") or ""),
            }
            _remember_ocr_context(context, reply_msg.message_id, ocr_ctx)
            _inc_user_ocr_usage(uid, 1)
        await _processing_update(proc, "Processing OCR Question", "Solving from the extracted OCR text...")
        answer, used_model = await _run_blocking(_role_of(uid), _answer_user_question_from_ocr, str(ocr_ctx.get("clean_text") or ocr_ctx.get("raw_markdown") or ""), user_question, timeout=180)
        await _processing_delete(proc)
        proc = None
        out = _answer_to_tg_html(answer, model_name=used_model, preserve_code=False)
        usage_line = f"\n\n<b>Daily OCR remaining</b>: <code>{h(str(_remaining_user_ocr_quota(uid)))}</code>"
        await safe_reply(update, out + usage_line)
        raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception as e:
        await _processing_delete(proc)
        db_log("ERROR", "user_reply_ocr_question_failed", {"user_id": uid, "error": str(e)})
        await err(update, "OCR Question Failed", str(e)[:220])
        raise ApplicationHandlerStop
    finally:
        if local_path:
            with contextlib.suppress(Exception):
                os.remove(local_path)


async def _run_staff_ocr_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE, source_msg, local_path: str, *, source_label: str = "image") -> Dict[str, Any]:
    uid = int(update.effective_user.id if update.effective_user else 0)
    proc = await _processing_start(source_msg, "Processing OCR", f"Running Mistral OCR on this {source_label}...")
    try:
        await _processing_update(proc, "Processing OCR", "Extracting text and detecting visible marked answers...")
        bundle = await _run_blocking(_role_of(uid), _extract_ocr_bundle_from_path, local_path, uid, timeout=300)
        ocr = bundle["ocr"]
        clean_text = str(bundle.get("clean_text") or "").strip()
        items = list(bundle.get("items") or [])
        visual_marked_count = int(bundle.get("visual_marked_count") or 0)

        added = 0
        for payload in items:
            if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
                break
            if not explain_mode_on(uid):
                payload["explanation"] = ""
            buffer_add(uid, payload)
            added += 1

        ctx_payload = {
            "raw_markdown": str(ocr.get("raw_markdown") or ""),
            "clean_text": clean_text,
            "items": items,
            "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
            "page_count": len(ocr.get("pages") or []),
            "used_key_mask": str(ocr.get("used_key_mask") or ""),
        }
        _remember_ocr_context(context, source_msg.message_id, ctx_payload)

        preview = clean_text.strip()
        if len(preview) > 2800:
            preview = preview[:2797].rstrip() + "..."
        status_bits = [
            f"OCR model: <code>{h(str(ocr.get('model') or MISTRAL_OCR_MODEL))}</code>",
            f"Used key: <code>{h(str(ocr.get('used_key_mask') or 'active'))}</code>",
            f"Pages: <code>{h(str(len(ocr.get('pages') or []) or 1))}</code>",
            f"Buffered MCQ: <code>{h(str(added))}</code>",
            f"Marked answers detected: <code>{h(str(visual_marked_count))}</code>",
        ]
        if ocr.get("limit_failures"):
            status_bits.append(f"Failover warnings: <code>{h(', '.join(list(ocr.get('limit_failures') or [])[:5]))}</code>")

        await _processing_delete(proc)
        proc = None
        preview_msg = await source_msg.reply_text(
            ui_box_html("Mistral OCR Complete", "\n".join(status_bits) + (f"\n\n{h(preview)}" if preview else ""), emoji="🧾"),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        _remember_ocr_context(context, preview_msg.message_id, ctx_payload)

        base_name = _display_name_from_message(source_msg, fallback=f"mistral_ocr_{uid}")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write(clean_text)
            txt_path = tf.name
        try:
            with open(txt_path, "rb") as fh:
                sent_doc = await source_msg.reply_document(
                    document=fh,
                    filename=f"{base_name}_ocr.txt",
                    caption=f"<b>✅ OCR Text Extracted</b>\n<i>{h(str(len(clean_text)))} characters • {h(str(len(ocr.get('pages') or []) or 1))} pages</i>",
                    parse_mode=ParseMode.HTML,
                )
            _remember_ocr_context(context, sent_doc.message_id, ctx_payload)
        finally:
            with contextlib.suppress(Exception):
                os.remove(txt_path)

        ready_title = "OCR + Quiz Buffer Ready" if added else "OCR Text Extracted"
        ready_body = (
            f"Buffered <code>{h(str(added))}</code> MCQ(s).\nUse <code>/done</code> to export or <code>/post</code> to publish.\nReply with <code>/qans</code> to choose an AI model and solve."
            if added else
            "Text was extracted successfully, but only unclear or incomplete MCQs were skipped from the buffer.\nReply with <code>/qans</code> to choose an AI model and solve from the OCR text."
        )
        ready_msg = await source_msg.reply_text(ui_box_html(ready_title, ready_body, emoji="✅" if added else "⚠️"), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        _remember_ocr_context(context, ready_msg.message_id, ctx_payload)
        return ctx_payload
    except Exception:
        await _processing_delete(proc)
        raise


async def cmd_qans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    if not update.message or not update.effective_user:
        return
    uid = int(update.effective_user.id)
    if is_banned(uid):
        return
    if not is_private_chat(update):
        await warn(update, "Private Only", "Use this command in private chat with the bot.")
        return
    if not _can_use_staff_ocr(uid):
        await warn(update, "Unauthorized", "Only owner/admin can use /qans.")
        return
    reply_msg = update.message.reply_to_message
    if not reply_msg:
        await safe_reply(update, usage_box("qans", "[extra instruction]", "Reply to an image, PDF, OCR text, text question, or poll, then use this command."))
        return

    extra_instruction = " ".join(context.args or []).strip()
    ocr_ctx = _get_ocr_context(context, reply_msg.message_id)
    proc = None
    local_path = None
    try:
        payload = None
        kind = "text"
        prompt_note = "Choose the AI model to continue."

        if getattr(reply_msg, "poll", None):
            poll = reply_msg.poll
            question = str(poll.question or "").strip()
            options = [str(o.text or "").strip() for o in (poll.options or []) if str(o.text or "").strip()]
            if len(options) < 2:
                raise RuntimeError("This poll does not contain enough options.")
            payload = {
                "question": question,
                "options": options,
                "official_ans": _poll_official_answer(poll),
                "official_expl": str(getattr(poll, "explanation", "") or "").strip(),
            }
            kind = "poll"
            prompt_note = "Choose the AI model to solve the replied quiz."
        else:
            if not ocr_ctx and _is_supported_ocr_media_message(reply_msg):
                if not mistral_runtime_enabled() or not get_mistral_api_key():
                    raise RuntimeError("Mistral OCR is not ready. Use /mistral status or /mistral add YOUR_KEY first.")
                suffix = ".jpg"
                if reply_msg.document:
                    name = str(reply_msg.document.file_name or "").lower()
                    suffix = ".pdf" if name.endswith(".pdf") or str(getattr(reply_msg.document, "mime_type", "") or "").lower() == "application/pdf" else ((os.path.splitext(name)[1].strip() or ".jpg")[:6] or ".jpg")
                    tg_file = await reply_msg.document.get_file()
                else:
                    tg_file = await reply_msg.photo[-1].get_file()
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    local_path = f.name
                await tg_file.download_to_drive(local_path)
                proc = await _processing_start(update.message, "Preparing /qans", "Running OCR on the replied file...")
                try:
                    await _processing_update(proc, "Preparing /qans", "Detecting visible marked answers and preparing AI choices...")
                    bundle = await _run_blocking(_role_of(uid), _extract_ocr_bundle_from_path, local_path, uid, timeout=300)
                    ocr = bundle["ocr"]
                    ocr_ctx = {
                        "raw_markdown": str(ocr.get("raw_markdown") or ""),
                        "clean_text": str(bundle.get("clean_text") or ""),
                        "items": list(bundle.get("items") or []),
                        "model": str(ocr.get("model") or MISTRAL_OCR_MODEL),
                        "page_count": len(ocr.get("pages") or []),
                        "used_key_mask": str(ocr.get("used_key_mask") or ""),
                    }
                    _remember_ocr_context(context, reply_msg.message_id, ocr_ctx)
                finally:
                    with contextlib.suppress(Exception):
                        os.remove(local_path)
                        local_path = None

            if ocr_ctx:
                picked = _pick_first_mcq_item(ocr_ctx.get("items") or [], extra_instruction)
                if picked:
                    options = [str(picked.get(f"option{i}") or "").strip() for i in range(1, 6) if str(picked.get(f"option{i}") or "").strip()]
                    if len(options) >= 2:
                        payload = {
                            "question": str(picked.get("questions") or "").strip(),
                            "options": options,
                            "official_ans": int(picked.get("answer", 0) or 0),
                            "official_expl": str(picked.get("explanation") or "").strip(),
                        }
                        kind = "poll"
                        prompt_note = "Choose the AI model to solve the extracted MCQ."
                if payload is None:
                    source_text = str(ocr_ctx.get("clean_text") or ocr_ctx.get("raw_markdown") or "").strip()
                    if not source_text:
                        raise RuntimeError("No readable OCR text found in the replied file.")
                    if extra_instruction:
                        source_text = f"{source_text}\n\nExtra user instruction:\n{extra_instruction}"
                    payload = {"text": source_text, "source_user_text": source_text}
                    kind = "text"
                    prompt_note = "Choose the AI model to solve from the OCR text."
            else:
                source_text = str(reply_msg.text or reply_msg.caption or "").strip()
                if not source_text:
                    raise RuntimeError("No readable text found in the replied message.")
                if extra_instruction:
                    source_text = f"{source_text}\n\nExtra user instruction:\n{extra_instruction}"
                payload = {"text": source_text, "source_user_text": source_text}
                kind = "text"
                prompt_note = "Choose the AI model to answer this prompt."

        token = _make_token()
        store = _pending_store(context)
        store[token] = {
            "uid": uid,
            "kind": kind,
            "scope": "private_academic",
            "chat_id": update.message.chat_id,
            "payload": payload,
        }
        await _processing_delete(proc)
        proc = None
        await safe_reply(update, ui_box_html("Choose AI Model", prompt_note, emoji="🤖"))
        await update.message.reply_text(
            ui_box_text("AI Options", "Tap a model button below to get the response.", emoji="⚙️"),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_solver_picker_kb(token),
        )
    except Exception as e:
        await _processing_delete(proc)
        db_log("ERROR", "qans_failed", {"user_id": uid, "error": str(e)})
        await err(update, "Question Answer Failed", str(e)[:220])


_prev_build_app_20260410_final = build_app

def build_app() -> Application:
    app = _prev_build_app_20260410_final()
    with contextlib.suppress(Exception):
        app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & filters.REPLY & (~filters.COMMAND), handle_user_reply_ocr_question), group=-10)
    return app

# ===== END MULTI-KEY MISTRAL + USER REPLY OCR PATCH =====


