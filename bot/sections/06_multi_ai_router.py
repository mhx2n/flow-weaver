# ──────────────────────────────────────────────────────────────────────────────
# Section: 06_multi_ai_router
# Original lines: 335..2126
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# =========================================================
# ✅ Multi-AI Router (Gemini3 / Perplexity / DeepSeek) — Inline Buttons
# =========================================================

_PENDING_KEY = "pending_solve_requests"

def _pending_store(context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Any]:
    d = context.application.bot_data.get(_PENDING_KEY)
    if not isinstance(d, dict):
        d = {}
        context.application.bot_data[_PENDING_KEY] = d
    return d

def _make_token() -> str:
    return uuid.uuid4().hex[:10]

def _solver_picker_kb(token: str) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("✨Gemini 3 Flash", callback_data=f"solve:G:{token}"),
            InlineKeyboardButton("֎Perplexity (GPT-5.1)", callback_data=f"solve:P:{token}"),
        ],
        #[
           # InlineKeyboardButton("🐳 DeepSeek", callback_data=f"solve:D:{token}"),
        #],
    ]
    return InlineKeyboardMarkup(kb)

def _verify_kb(token: str, used: str, kind: str = "text") -> InlineKeyboardMarkup:
    alt = []
    if used != "P":
        alt.append(InlineKeyboardButton("⚛ Perplexity", callback_data=f"solve:P:{token}"))
    if used != "G":
        alt.append(InlineKeyboardButton("✨ Gemini", callback_data=f"solve:G:{token}"))

    rows = [alt[i:i+2] for i in range(0, len(alt), 2)]

    # Show Generate Quiz ONLY for quiz/poll based solutions
    if str(kind or "") == "poll":
        rows.append([InlineKeyboardButton("📊 Generate Quiz", callback_data=f"genquiz:{token}")])

    return InlineKeyboardMarkup(rows)

# def _deepseek_client() -> OpenAI:
#     if not DEEPSEEK_API_KEY or "sk-" not in str(DEEPSEEK_API_KEY):
#         raise RuntimeError("DeepSeek API Key সেট করা নেই।")
#     return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

def deepseek_solve_text(problem_text: str) -> str:
    prompt = (STRICT_SYSTEM_PROMPT + "\n\nUser Message:\n" + (problem_text or "").strip()).strip()
    client = _deepseek_client()
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL_TEXT,
        messages=[
            {"role": "system", "content": "You are a strict academic problem-solving assistant."},
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    return (resp.choices[0].message.content or "").strip() or "..."

def perplexity_solve_text(problem_text: str) -> str:
    prompt = (STRICT_SYSTEM_PROMPT + "\n\nUser Message:\n" + (problem_text or "").strip()).strip()
    alt = query_ai(prompt)
    if alt:
        return alt.strip()
    raise RuntimeError("Perplexity unavailable.")

def perplexity_solve_mcq_json(question: str, options: List[str]) -> Dict[str, Any]:
    # Ask Perplexity proxy to return strict JSON
    q = (question or "").strip()
    opts = [(o or "").strip() for o in (options or []) if (o or "").strip()][:5]
    opt_lines = "\n".join([f"{_safe_letter(i+1)}. {opts[i]}" for i in range(len(opts))])
    is_bn = _is_bangla_text(q + " " + " ".join(opts))
    lang_rule = _quiz_language_rule_block(is_bn)
    schema_expl = _quiz_schema_example_explanation(is_bn)
    p2 = (
        "Return STRICT JSON only (no markdown).\n"
        "Solve the MCQ and respond in this JSON format exactly:\n"
        f'{{"answer":1,"confidence":0,"explanation":"{schema_expl}","why_not":{{"A":"..","B":"..","C":"..","D":"..","E":".."}}}}\n\n'
        f"{lang_rule}\n"
        "Keep the explanation short, exam-style, and accurate.\n"
        f"Question:\n{q}\n\nOptions:\n{opt_lines}\n"
    )
    alt = query_ai(p2)
    if not alt:
        raise RuntimeError("Perplexity unavailable.")
    try:
        data = _extract_json_strict(alt)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"answer": 0, "confidence": 0, "explanation": (alt[:1800] if isinstance(alt, str) else str(alt)[:1800]), "why_not": {}}
def deepseek_solve_mcq_json(question: str, options: List[str]) -> Dict[str, Any]:
    """Solve an MCQ using DeepSeek and return strict JSON dict.

    This function must NEVER raise due to minor JSON formatting issues; it will attempt repair.
    """
    q = (question or "").strip()
    opts = [(o or "").strip() for o in (options or []) if (o or "").strip()][:5]
    opt_lines = "\n".join([f"{_safe_letter(i+1)}. {opts[i]}" for i in range(len(opts))])
    is_bn = _is_bangla_text(q + " " + " ".join(opts))
    lang_rule = _quiz_language_rule_block(is_bn)
    schema_expl = _quiz_schema_example_explanation(is_bn)

    prompt = (
        "Return STRICT JSON only. No markdown. No extra text.\n"
        "Solve the MCQ and respond in this JSON format exactly:\n"
        f'{{"answer":1,"confidence":0,"explanation":"{schema_expl}","why_not":{{"A":"..","B":"..","C":"..","D":"..","E":".."}}}}\n\n'
        f"{lang_rule}\n"
        "Keep the explanation short, exam-style, and accurate.\n"
        f"Question:\n{q}\n\nOptions:\n{opt_lines}\n"
    )

    client = _deepseek_client()
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL_TEXT,
        messages=[
            {"role": "system", "content": "You are a strict academic problem-solving assistant."},
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    raw = (resp.choices[0].message.content or "").strip()

    schema_hint = (
        f'{{"answer":1,"confidence":0.0,"explanation":"{schema_expl}",'
        '"why_not":{"A":"..","B":"..","C":"..","D":"..","E":".."}}'
    )
    try:
        data = _extract_json_strict(raw)
    except Exception:
        repaired = _repair_to_json(raw, schema_hint=schema_hint, timeout_seconds=18)
        if not repaired:
            # graceful fallback
            return {"answer": 0, "confidence": 0, "explanation": (raw[:1800] or ""), "why_not": {}}
        data = repaired

    if isinstance(data, dict):
        return data
    return {"answer": 0, "confidence": 0, "explanation": (raw[:1800] or ""), "why_not": {}}


# Regex to detect Bangla characters
_BN_CHAR_RE = re.compile(r"[\u0980-\u09FF]")

def _is_bangla_text(s: str) -> bool:
    return bool(_BN_CHAR_RE.search(s or ""))


def _quiz_language_rule_block(is_bn: bool) -> str:
    """Return the language rule for QUIZ/MCQ explanations only."""
    if is_bn:
        return (
            "If the question is in Bangla, explanation MUST be in Bangla only. \
Do not answer in English."
        )
    return (
        "If the question is in English, explanation MUST be bilingual: Bangla first, then English. \
Both parts must be short and consistent."
    )


def _quiz_schema_example_explanation(is_bn: bool) -> str:
    if is_bn:
        return "বাংলা ব্যাখ্যা..."
    return "বাংলা ব্যাখ্যা...\nEnglish explanation..."

def _normalize_options(options: List[str], max_n: int = 4) -> List[str]:
    opts = [(o or "").strip() for o in (options or []) if (o or "").strip()]
    if len(opts) < 2:
        return ["Option A", "Option B", "Option C", "Option D"][:max_n]
    if len(opts) >= max_n:
        return opts[:max_n]
    while len(opts) < max_n:
        opts.append(f"Option {chr(65+len(opts))}")
    return opts[:max_n]

def _trim_expl_for_poll(expl: str, link: str = "") -> str:
    # Keep explanation short enough for Telegram quiz explanation field.
    # Telegram allows ~200 chars, but we keep it smaller to avoid errors.
    t = (expl or "").strip()

    # Prefer only first 2 lines if many lines
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if lines:
        t = "\n".join(lines[:2])

    if link:
        t = (t + "\n" if t else "") + f" {link}".strip()

    t = t.strip()
    if len(t) > 160:
        t = t[:157] + "..."
    return t


def generate_quiz_items_gemini_then_verify(seed_question: str, seed_options: List[str]) -> List[Dict[str, Any]]:
    """Generate 3 MCQs on the same topic using Gemini3, then verify each with Perplexity."""
    sq = (seed_question or "").strip()
    so = _normalize_options(seed_options or [], max_n=4)

    is_bn = _is_bangla_text(sq + " " + " ".join(so))
    lang_rule = _quiz_language_rule_block(is_bn)
    schema_expl = _quiz_schema_example_explanation(is_bn)

    prompt = (
        "Return STRICT JSON only (no markdown, no extra text).\n"
        "Task: You are given a SEED quiz question (MCQ) with options.\n"
        "1) Infer the *MICRO-TOPIC / chapter concept* strictly from the seed (e.g., 'Kinematics: acceleration from velocity-position relation', 'Myelinated neuron: saltatory conduction', etc.).\n"
        "2) Generate exactly 3 NEW MCQs ONLY from that same micro-topic (same concept family).\n"
        "   - Do NOT generate from the whole subject/book.\n"
        "   - Do NOT repeat the seed question or trivially rephrase it.\n"
        "   - Keep difficulty similar to admission-style questions.\n"
        "3) Each MCQ must have 4 options and exactly one correct answer.\n"
        "4) Keep the question language consistent with the seed question language.\n"
        f"5) {lang_rule}\n"
        "6) Keep the explanation SHORT (1-2 lines max).\n\n"
        "Allowed major topics (for labeling only): Physics, Chemistry, Math, Biology, Bangla, English, General Knowledge, Humanities Skills.\n"
        "JSON format:\n"
        "{\n"
        '  "topic": "<major topic>",\n'
        '  "microtopic": "<micro-topic inferred from seed>",\n'
        '  "items": [\n'
        "    {\n"
        '      "question": "...",\n'
        '      "options": ["...","...","...","..."],\n'
        '      "answer": 1,\n'
        f'      "explanation": "{schema_expl}"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"Seed Question:\n{sq}\n\n"
        "Seed Options:\n" + "\n".join([f"{_safe_letter(i+1)}. {so[i]}" for i in range(len(so))])
    )

    raw = None
    last_err = None

    if USE_GEMINI_REST_FOR_GENQUIZ and GEMINI_API_KEY:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=18, force_json=True)
        except Exception as e:
            last_err = e
            raw = None

    if not raw and USE_PERPLEXITY_FALLBACK:
        try:
            raw = query_ai(prompt)
        except Exception as e:
            last_err = e
            raw = None

    if not raw:
        try:
            raw = gemini3_solve(prompt)
        except Exception as e:
            last_err = e
            raw = None

    if not raw:
        raise RuntimeError(f"Quiz generation failed: {last_err or 'all backends unavailable'}")

    schema_hint = (
        '{"microtopic":"<micro>","items":[{"question":"...","options":["...","...","...","..."],'
        + '"answer":1,"explanation":"' + schema_expl + '"}]}'
    )
    try:
        data = _extract_json_strict(raw)
    except Exception:
        repaired = _repair_to_json(raw, schema_hint=schema_hint, timeout_seconds=18)
        if not repaired:
            raise
        data = repaired

    if not isinstance(data, dict):
        raise RuntimeError("Quiz generation failed.")

    items = data.get("items", []) or []
    out: List[Dict[str, Any]] = []
    for it in items[:3]:
        q = str(it.get("question", "")).strip()
        opts = _normalize_options([str(x) for x in (it.get("options", []) or [])], max_n=4)
        ans = int(it.get("answer", 0) or 0)
        expl = str(it.get("explanation", "")).strip()

        try:
            ver = perplexity_solve_mcq_json(q, opts)
            vans = int((ver or {}).get("answer", 0) or 0)
            vexpl = str((ver or {}).get("explanation", "") or "").strip()
            if 1 <= vans <= 4:
                ans = vans
            if vexpl:
                expl = vexpl
        except Exception:
            pass

        if q and opts and 1 <= ans <= 4:
            out.append({"question": q, "options": opts, "answer": ans, "explanation": expl})

    return out[:3]


async def on_solver_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle solver button callbacks: solve:G/P/D:<token>"""
    if not update.callback_query:
        return
    q = update.callback_query
    await q.answer("Processing…", show_alert=False)

    data = (q.data or "").strip()
    m = re.match(r"^solve:([GPD]):([0-9a-f]{6,16})$", data)
    if not m:
        return
    model = m.group(1)  # G=Gemini, P=Perplexity, D=DeepSeek
    token = m.group(2)

    store = _pending_store(context)
    req = store.get(token)
    if not isinstance(req, dict):
        with contextlib.suppress(Exception):
            await q.edit_message_text("⚠️ This request has expired. Please send your question again.")
        return

    uid = int(req.get("uid") or 0)
    if q.from_user and q.from_user.id != uid:
        with contextlib.suppress(Exception):
            await q.answer("This is not your request.", show_alert=True)
        return

    payload = req.get("payload") or {}
    problem_text = str(payload.get("text") or "").strip()
    kind = str(req.get("kind") or "text").lower()

    # Show processing message
    with contextlib.suppress(Exception):
        await q.edit_message_text(
            ui_box_text("Solving", "Please wait… Processing your request.", emoji="⏳"),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    try:
        if kind == "poll" and payload.get("question"):
            # MCQ solve
            question = str(payload.get("question", "")).strip()
            options = payload.get("options", [])
            
            if model == "G":
                result = await _run_blocking(_role_of(uid), gemini_solve_mcq_json, question, options)
            elif model == "P":
                result = await _run_blocking(_role_of(uid), perplexity_solve_mcq_json, question, options)
            elif model == "D":
                result = await _run_blocking(_role_of(uid), deepseek_solve_mcq_json, question, options)
            else:
                result = {"answer": 0, "confidence": 0, "explanation": "Unknown model", "why_not": {}}

            # --- NEW CODE START ---
            raw_expl = str(result.get('explanation', '') or "")
            clean_expl = clean_latex(raw_expl)  # এখানে ক্লিন করা হচ্ছে

            # Why not অপশনগুলোও ক্লিন করা দরকার
            raw_why_not = result.get("why_not", {}) or {}
            clean_why_not = {k: clean_latex(v) for k, v in raw_why_not.items()}

            msg_html = _format_user_poll_solution(
                question=question,
                options=options,
                model_ans=int(result.get("answer", 0) or 0),
                official_ans=int(payload.get("official_ans", 0) or 0),
                # এখানে ক্লিন করা টেক্সট পাঠানো হচ্ছে
                model_expl=f"[{['Gemini', 'Perplexity', 'DeepSeek'][['G','P','D'].index(model)]}]\n{clean_expl}".strip(),
                official_expl=str(payload.get("official_expl", "")).strip(),
                why_not=clean_why_not,
                conf=int(result.get("confidence", 0) or 0),
            )
            # --- NEW CODE END ---
            kb = _verify_kb(token, model, "poll")
        else:
            # Text solve
            if model == "G":
                answer = await _run_blocking(_role_of(uid), gemini_solve_text, problem_text)
            elif model == "P":
                answer = await _run_blocking(_role_of(uid), perplexity_solve_text, problem_text)
            elif model == "D":
                answer = await _run_blocking(_role_of(uid), deepseek_solve_text, problem_text)
            else:
                answer = "Unknown model"

            if is_admin(uid) or is_owner(uid):
                src_text = problem_text
                if looks_like_programming_request(src_text) or looks_like_programming_request(answer):
                    msg_html = f"<pre>{h(answer)}</pre>"
                else:
                    msg_html = h(answer)
            else:
                msg_html = h(answer)
            kb = _verify_kb(token, model, "text")

        with contextlib.suppress(Exception):
            await q.edit_message_text(msg_html, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        if q.message and getattr(q.message.chat, "type", "") in ("group", "supergroup"):
            asyncio.create_task(_auto_delete_after(context.bot, q.message.chat_id, [q.message.message_id], 300))

    except Exception as e:
        db_log("ERROR", "solver_callback_failed", {"user_id": uid, "model": model, "error": str(e)})
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                ui_box_text("Solve Failed", str(e)[:180], emoji="❌"),
                parse_mode=ParseMode.HTML,
            )


async def on_genquiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return
    q = update.callback_query
    await q.answer("Processing…", show_alert=False)

    data = (q.data or "").strip()
    m = re.match(r"^genquiz:([0-9a-f]{6,16})$", data)
    if not m:
        return
    token = m.group(1)

    store = _pending_store(context)
    req = store.get(token)
    if not isinstance(req, dict):
        with contextlib.suppress(Exception):
            await q.edit_message_text("⚠️ This request has expired. Please send the quiz again.")
        return

    uid = int(req.get("uid") or 0)
    if q.from_user and q.from_user.id != uid:
        with contextlib.suppress(Exception):
            await q.answer("This is not your request.", show_alert=True)
        return

    # ONLY allow when the original content was a Poll/Quiz
    if str(req.get("kind") or "") != "poll":
        with contextlib.suppress(Exception):
            await q.answer("Generate Quiz is available only for quiz questions.", show_alert=True)
        return

    payload = req.get("payload") or {}
    seed_question = str(payload.get("question") or "").strip()
    seed_options = payload.get("options") or []

    qpfx = (get_setting("quiz_prefix", "প্রবাহ") or "প্রবাহ").strip()
    qlink = (get_setting("quiz_expl_link", "") or "").strip()

    # UI feedback
    with contextlib.suppress(Exception):
        await q.edit_message_text(
            ui_box_text("Generating Quizzes", "Please wait… Creating quizzes...", emoji="⏳"),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


    try:
        chat_id = int(req.get("chat_id") or (q.message.chat_id if q.message else uid))
    
        # Generate until we have 3 quizzes (best effort, no feature loss)
        items = []
        seen_q = set()
        for _attempt in range(3):
            new_items = await _run_blocking(_role_of(uid), generate_quiz_items_gemini_then_verify, seed_question, seed_options)
            for it in (new_items or []):
                qt = str(it.get("question","") or "").strip()
                if not qt:
                    continue
                key = re.sub(r"\s+", " ", qt).lower()
                if key in seen_q:
                    continue
                seen_q.add(key)
                items.append(it)
                if len(items) >= 3:
                    break
            if len(items) >= 3:
                break
    
        if not items:
            raise RuntimeError("Quiz generation returned empty items.")
    
        items = items[:3]
    
        # Serialize sending per-chat to avoid flood-control cutting off the batch
        lock = _get_chat_lock(context, chat_id)
        async with lock:
            SEP = "\n\u200b"
            for it in items:
                qq = str(it["question"]).strip()
                opts = [str(x).strip() for x in it["options"]]
                ans = int(it["answer"])
                expl = _trim_expl_for_poll(str(it.get("explanation", "")), qlink)

                # FIX: shuffle options so correct answer position varies per quiz
                _corr_id0 = (ans - 1) if 1 <= ans <= len(opts) else 0
                qq, opts, _corr_id0 = _shuffle_quiz_payload(qq, opts, _corr_id0)
    
                q_final = f"{qpfx}{SEP}{qq}".strip() if qpfx else qq
                if len(q_final) > 300:
                    q_final = q_final[:297] + "..."
    
                await _send_poll_with_retry(
                    context.bot,
                    chat_id=chat_id,
                    question=q_final,
                    options=opts,
                    is_anonymous=True,
                    type=Poll.QUIZ,
                    correct_option_id=max(0, _corr_id0),
                    explanation=expl if expl else None,
                )
                await asyncio.sleep(0.35)
    
        done_msg = ui_box_text("Quizzes Generated", "Quizzes have been generated ✅", emoji="📊")
        with contextlib.suppress(Exception):
            await q.edit_message_text(done_msg, parse_mode=ParseMode.HTML)
    
    except Exception as e:
        db_log("ERROR", "generate_quiz_failed", {"user_id": uid, "error": str(e)})
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                ui_box_text("Generate Quiz Failed", str(e)[:180], emoji="❌"),
                parse_mode=ParseMode.HTML,
            )


# ---------------------------
# UTIL
# ---------------------------
from datetime import timezone


def now_iso() -> str:
    return dt.datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def chunk_text(s: str, size: int = 3500) -> Iterable[str]:
    if not s:
        return []
    return (s[i:i + size] for i in range(0, len(s), size))


# ---------------------------
# Process / System stats helpers (owner dashboard)
# ---------------------------
def process_rss_mb() -> float:
    """Approximate RSS memory usage (MB) for this process. Works on Linux; graceful fallback."""
    try:
        # Linux: /proc/self/statm
        with open("/proc/self/statm", "r") as f:
            parts = f.read().strip().split()
        if len(parts) >= 2:
            rss_pages = int(parts[1])
            page_size = os.sysconf("SC_PAGE_SIZE")  # bytes
            return (rss_pages * page_size) / (1024 * 1024)
    except Exception:
        pass
    try:
        import resource  # stdlib
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is KB on Linux, bytes on macOS. We assume Linux here.
        return float(rusage.ru_maxrss) / 1024.0
    except Exception:
        return 0.0

def fmt_mb(x: float) -> str:
    try:
        return f"{x:.1f} MB"
    except Exception:
        return "N/A"

def fmt_uptime() -> str:
    try:
        secs = int(time.time() - START_TIME)
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"
    except Exception:
        return "N/A"


# ---------------------------
# HTML helpers (safer + cleaner formatting)
# ---------------------------
def h(s: Any) -> str:
    """Escape text for Telegram HTML parse mode."""
    return html_escape.escape(str(s if s is not None else ""), quote=False)

def b(s: Any) -> str:
    return f"<b>{h(s)}</b>"

def code(s: Any) -> str:
    return f"<code>{h(s)}</code>"

def md_to_html_basic(s: str) -> str:
    """Convert a small subset of Markdown (**bold**, `code`) to Telegram-safe HTML."""
    if not s:
        return ""
    s = re.sub(r"`([^`]+)`", lambda m: f"<code>{html_escape.escape(m.group(1), quote=False)}</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", lambda m: f"<b>{html_escape.escape(m.group(1), quote=False)}</b>", s)
    return s

def to_int(s: str) -> Optional[int]:
    try:
        return int(str(s).strip())
    except Exception:
        return None


def looks_like_programming_request(text: str) -> bool:
    s = (text or "").lower()
    keys = [
        "python", "javascript", "js", "java", "c++", "cpp", "c#", "php", "sql", "html", "css",
        "program", "code", "bug", "error", "traceback", "exception", "api", "function", "class",
        "loop", "array", "dict", "json", "regex", "algorithm", "query", "database", "telegram bot"
    ]
    return any(k in s for k in keys)


# ---------------------------
# DB
# ---------------------------
def db_connect() -> sqlite3.Connection:
    # SQLite tuning for multi-user / multi-update concurrency.
    # - WAL allows concurrent readers + a writer
    # - busy_timeout avoids 'database is locked' spikes under load
    # - longer connect timeout helps on slower disks (e.g., Pella)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        # If PRAGMA fails for any reason, continue with defaults (do not break bot).
        pass
    return conn


def _table_has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r["name"] for r in cur.fetchall()]
    return col in cols


def db_init() -> None:
    conn = db_connect()
    cur = conn.cursor()

    # Users: includes role + banned
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        role TEXT NOT NULL DEFAULT 'USER',
        first_name TEXT,
        username TEXT,
        is_banned INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    # Migration: optional access flag
    if not _table_has_column(conn, "users", "can_view_all"):
        cur.execute("ALTER TABLE users ADD COLUMN can_view_all INTEGER NOT NULL DEFAULT 0")

    # Migration: optional vision (image→quiz) access flag
    if not _table_has_column(conn, "users", "can_use_vision"):
        cur.execute("ALTER TABLE users ADD COLUMN can_use_vision INTEGER NOT NULL DEFAULT 0")


    # Migration: per-user feature toggles (command-based)
    if not _table_has_column(conn, "users", "vision_mode_on"):
        cur.execute("ALTER TABLE users ADD COLUMN vision_mode_on INTEGER NOT NULL DEFAULT 0")
    if not _table_has_column(conn, "users", "solver_mode_on"):
        cur.execute("ALTER TABLE users ADD COLUMN solver_mode_on INTEGER NOT NULL DEFAULT 0")
    if not _table_has_column(conn, "users", "explain_mode_on"):
        cur.execute("ALTER TABLE users ADD COLUMN explain_mode_on INTEGER NOT NULL DEFAULT 0")

    # Migration: last seen timestamp (for active user stats)
    if not _table_has_column(conn, "users", "last_seen_at"):
        cur.execute("ALTER TABLE users ADD COLUMN last_seen_at TEXT")

    # Filters (per admin)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS filters (
        user_id INTEGER NOT NULL,
        phrase TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (user_id, phrase)
    )
    """)

    # Quiz buffer (per admin)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS quiz_buffer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    # Channels (added_by indicates who added it)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_chat_id INTEGER NOT NULL UNIQUE,
        title TEXT,
        prefix TEXT DEFAULT '',
        expl_link TEXT DEFAULT '',
        added_by INTEGER,
        created_at TEXT NOT NULL
    )
    """)

    # Admin post stats
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_post_stats (
        admin_id INTEGER PRIMARY KEY,
        total_posts INTEGER NOT NULL DEFAULT 0,
        last_post_at TEXT
    )
    """)

    # Inbox / Tickets
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        student_name TEXT,
        status TEXT NOT NULL DEFAULT 'OPEN',
        created_at TEXT NOT NULL,
        last_update_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ticket_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        from_role TEXT NOT NULL, -- STUDENT or STAFF
        from_id INTEGER NOT NULL,
        message_text TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    # Ban audit (who banned whom)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ban_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_user_id INTEGER NOT NULL,
        action TEXT NOT NULL, -- BAN or UNBAN
        by_user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    # Logs (lightweight)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        event TEXT NOT NULL,
        meta_json TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # Global settings defaults (non-breaking)
    settings_init_defaults(conn)


    conn.commit()
    conn.close()


def db_log(level: str, event: str, meta: Optional[Dict[str, Any]] = None) -> None:
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO bot_logs(level, event, meta_json, created_at) VALUES (?,?,?,?)",
            (level.upper(), event, json.dumps(meta or {}, ensure_ascii=False), now_iso()),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("db_log failed (ignored)")


# ---------------------------
# GLOBAL SETTINGS (Generate Quiz prefix / explanation link)
# ---------------------------
def settings_init_defaults(conn: sqlite3.Connection) -> None:
    """Ensure settings table exists + defaults (non-breaking)."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    ts = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    cur.execute("INSERT OR IGNORE INTO settings(key,value,updated_at) VALUES (?,?,?)", ("quiz_prefix", "প্রবাহ", ts))
    cur.execute("INSERT OR IGNORE INTO settings(key,value,updated_at) VALUES (?,?,?)", ("quiz_expl_link", "", ts))

def get_setting(key: str, default: str = "") -> str:
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        conn.close()
        if row and row["value"] is not None:
            return str(row["value"])
    except Exception:
        pass
    return default

def set_setting(key: str, value: str) -> None:
    conn = db_connect()
    cur = conn.cursor()
    ts = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    cur.execute(
        "INSERT INTO settings(key,value,updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value or "", ts),
    )
    conn.commit()
    conn.close()


# ---------------------------
# ROLES / PERMISSIONS
# ---------------------------
ROLE_OWNER = "OWNER"
ROLE_ADMIN = "ADMIN"
ROLE_USER = "USER"


def normalize_role(role: str) -> str:
    r = (role or "").upper().strip()
    return r if r in (ROLE_OWNER, ROLE_ADMIN, ROLE_USER) else ROLE_USER


def ensure_user(update: Update) -> None:
    if not update.effective_user:
        return
    u = update.effective_user
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE user_id=?", (u.id,))
    row = cur.fetchone()
    if row is None:
        role = ROLE_OWNER if _is_owner_id(u.id) else ROLE_USER
        cur.execute(
            "INSERT INTO users(user_id, role, first_name, username, is_banned, created_at, can_view_all, can_use_vision, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (u.id, role, u.first_name, u.username, 0, now_iso(), 0, 0, now_iso()),
        )
    else:
        cur.execute(
            "UPDATE users SET first_name=?, username=?, last_seen_at=? WHERE user_id=?",
            (u.first_name, u.username, now_iso(), u.id),
        )
    conn.commit()
    conn.close()


def get_role(user_id: int) -> str:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row and row["role"]:
        return normalize_role(row["role"])
    return ROLE_OWNER if _is_owner_id(user_id) else ROLE_USER


def _role_of(user_id: int) -> str:
    """Return role label for concurrency pools (OWNER/ADMIN/USER)."""
    try:
        return get_role(int(user_id or 0))
    except Exception:
        return ROLE_USER


# ---------------------------
# Per-chat locks (avoid flood + keep per chat ordering)
# ---------------------------
def _get_chat_lock(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> asyncio.Lock:
    """Get/create an asyncio.Lock for a chat_id stored in application bot_data."""
    try:
        locks = context.application.bot_data.get("_chat_locks")
        if not isinstance(locks, dict):
            locks = {}
            context.application.bot_data["_chat_locks"] = locks
        lock = locks.get(int(chat_id))
        if not isinstance(lock, asyncio.Lock):
            lock = asyncio.Lock()
            locks[int(chat_id)] = lock
        return lock
    except Exception:
        # last resort: a new lock (won't be shared)
        return asyncio.Lock()


async def _send_poll_with_retry(
    bot,
    *,
    chat_id: int,
    question: str,
    options: List[str],
    is_anonymous: bool = True,
    type: str = Poll.QUIZ,
    correct_option_id: int | None = None,
    explanation: str | None = None,
    allows_multiple_answers: bool = False,
    protect_content: bool = False,
    max_tries: int = 5,
):
    """send_poll wrapper with RetryAfter handling + small backoff."""
    last_err = None
    for i in range(max_tries):
        try:
            return await bot.send_poll(
                chat_id=chat_id,
                question=question,
                options=options,
                is_anonymous=is_anonymous,
                type=type,
                correct_option_id=correct_option_id,
                explanation=explanation,
                allows_multiple_answers=allows_multiple_answers,
                protect_content=protect_content,
            )
        except RetryAfter as e:
            await asyncio.sleep(float(getattr(e, "retry_after", 1.0)) + 0.2)
            last_err = e
        except TelegramError as e:
            # transient errors: retry a bit
            last_err = e
            await asyncio.sleep(0.4 * (2 ** i))
        except Exception as e:
            last_err = e
            await asyncio.sleep(0.4 * (2 ** i))
    raise RuntimeError(str(last_err) if last_err else "send_poll failed")


def _deepseek_client():
    """Lazy DeepSeek client (OpenAI-compatible). Only used if DeepSeek is enabled."""
    if not globals().get("DEEPSEEK_API_KEY") or "sk-" not in str(globals().get("DEEPSEEK_API_KEY")):
        raise RuntimeError("DeepSeek API Key সেট করা নেই।")
    try:
        from openai import OpenAI  # optional dependency
    except Exception as e:
        raise RuntimeError("openai package missing for DeepSeek.") from e
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def is_owner(user_id: int) -> bool:
    return _is_owner_id(user_id) or get_role(user_id) == ROLE_OWNER


def is_admin(user_id: int) -> bool:
    return get_role(user_id) in (ROLE_OWNER, ROLE_ADMIN)


def is_banned(user_id: int) -> bool:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    return int(row["is_banned"] or 0) == 1


def set_ban(user_id: int, banned: bool) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_banned=? WHERE user_id=?", (1 if banned else 0, user_id))
    conn.commit()
    conn.close()


def audit_ban(by_user_id: int, target_user_id: int, action: str) -> None:
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ban_audit(target_user_id, action, by_user_id, created_at) VALUES (?,?,?,?)",
            (target_user_id, action, by_user_id, now_iso()),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("audit_ban failed (ignored)")


def can_view_all(user_id: int) -> bool:
    if is_owner(user_id):
        return True
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT can_view_all FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    return int(row["can_view_all"] or 0) == 1


def set_can_view_all(user_id: int, value: bool) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET can_view_all=? WHERE user_id=?", (1 if value else 0, user_id))
    conn.commit()
    conn.close()



def can_use_vision(user_id: int) -> bool:
    """Owner always can. Others need explicit grant (can_use_vision=1)."""
    if is_owner(user_id):
        return True
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT can_use_vision FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    return int(row["can_use_vision"] or 0) == 1


def set_can_use_vision(user_id: int, value: bool) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET can_use_vision=? WHERE user_id=?", (1 if value else 0, user_id))
    conn.commit()
    conn.close()



def vision_mode_on(user_id: int) -> bool:
    """Command-based toggle: if OFF, image→quiz handler ignores images."""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT vision_mode_on FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row["vision_mode_on"] or 0) == 1 if row else False


def set_vision_mode_on(user_id: int, value: bool) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET vision_mode_on=? WHERE user_id=?", (1 if value else 0, user_id))
    conn.commit()
    conn.close()


def solver_mode_on(user_id: int) -> bool:
    """Command-based toggle: if ON (USER role), bot will solve incoming text."""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT solver_mode_on FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row["solver_mode_on"] or 0) == 1 if row else False


def set_solver_mode_on(user_id: int, value: bool) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET solver_mode_on=? WHERE user_id=?", (1 if value else 0, user_id))
    conn.commit()
    conn.close()




def himusai_mode_on(user_id: int) -> bool:
    """Alias for admin/owner inbox AI-only mode.

    Historical builds used a separate HimusAI toggle name, but the current
    database stores this state in users.solver_mode_on. Keeping this alias
    prevents NameError in the active handlers and restores the previous flow
    where private admin/owner chats skip poll/text buffering when HimusAI is on.
    """
    return solver_mode_on(user_id)


def set_himusai_mode_on(user_id: int, value: bool) -> None:
    """Persist HimusAI mode using the existing solver_mode_on column."""
    set_solver_mode_on(user_id, value)

def explain_mode_on(user_id: int) -> bool:
    """Command-based toggle: if ON, quizzes include explanation; if OFF, quizzes are posted without explanation."""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT explain_mode_on FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row["explain_mode_on"] or 0) == 1 if row else False


def set_explain_mode_on(user_id: int, value: bool) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET explain_mode_on=? WHERE user_id=?", (1 if value else 0, user_id))
    conn.commit()
    conn.close()



async def warn_unauthorized(update: Update, reason: str = "This action is not allowed for your role.") -> None:
    body = f"{h(reason)}\n\nIf you genuinely need access, contact the owner: {h(OWNER_CONTACT)}"
    await warn(update, "Unauthorized", body)


def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        ensure_user(update)
        uid = update.effective_user.id if update.effective_user else 0
        if is_banned(uid):
            await safe_reply(update, f"🚫 Access denied. You are banned.\nContact: {OWNER_CONTACT}")
            return
        if not is_admin(uid):
            await warn_unauthorized(update, "Only Admin/Owner can use this feature.")
            return
        return await func(update, context)
    return wrapper


def require_owner(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        ensure_user(update)
        uid = update.effective_user.id if update.effective_user else 0
        if is_banned(uid):
            await safe_reply(update, f"🚫 Access denied. You are banned.\nContact: {OWNER_CONTACT}")
            return
        if not is_owner(uid):
            return
        return await func(update, context)
    return wrapper


# For message handlers: silently ignore non-admins (prevents double warnings)
def require_admin_silent(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        ensure_user(update)
        uid = update.effective_user.id if update.effective_user else 0
        if is_banned(uid):
            return
        if not is_admin(uid):
            return
        return await func(update, context)
    return wrapper



def require_vision(func):
    """Owner or granted users can use image→quiz feature."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        ensure_user(update)
        uid = update.effective_user.id if update.effective_user else 0
        if is_banned(uid):
            await safe_reply(update, f"🚫 Access denied. You are banned.\nContact: {OWNER_CONTACT}")
            return
        if not can_use_vision(uid):
            await warn_unauthorized(update, "Only the Owner (or explicitly granted staff) can use Image→Quiz.")
            return
        return await func(update, context)
    return wrapper


def require_vision_silent(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        ensure_user(update)
        uid = update.effective_user.id if update.effective_user else 0
        if is_banned(uid):
            return
        if not can_use_vision(uid):
            return
        return await func(update, context)
    return wrapper


# ---------------------------
# TELEGRAM SAFE SEND
# ---------------------------
async def safe_reply(update: Update, text: str) -> None:
    if not update.message:
        return
    for part in chunk_text(text, 3500):
        try:
            await update.message.reply_text(
                part,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except TelegramError as e:
            logger.exception("HTML parse error in safe_reply: %s", e)
            # Send plain text if HTML formatting fails
            with contextlib.suppress(Exception):
                await update.message.reply_text(
                    part,
                    disable_web_page_preview=True,
                )


async def safe_send_text(bot, chat_id: int, text: str, protect: bool = False) -> None:
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            protect_content=protect,
        )
    except RetryAfter as e:
        await asyncio.sleep(float(e.retry_after) + 0.2)
        with contextlib.suppress(Exception):
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                protect_content=protect,
            )
    except (Forbidden, TelegramError):
        pass
    except Exception:
        pass


async def safe_copy_message(bot, chat_id: int, from_chat_id: int, message_id: int, protect: bool = False) -> bool:
    """
    Copies a message without forward header.
    protect_content=True restricts forwarding/saving (Telegram feature).
    """
    try:
        await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            protect_content=protect,
        )
        return True
    except RetryAfter as e:
        await asyncio.sleep(float(e.retry_after) + 0.2)
        with contextlib.suppress(Exception):
            await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                protect_content=protect,
            )
            return True
    except (Forbidden, TelegramError):
        return False
    except Exception:
        return False



# ---------------------------
# Solver "searching" animation (Telegram-friendly)
# ---------------------------
async def _spinner_task(bot, chat_id: int, message_id: int) -> None:
    frames = [
        "🔎 Searching",
        "🔎 Searching.",
        "🔎 Searching..",
        "🔎 Searching...",
        "⏳ Preparing solution...",
    ]
    i = 0
    while True:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=frames[i % len(frames)],
            )
        except Exception:
            pass
        i += 1
        await asyncio.sleep(0.9)

# -------------------------------
# Gemini3 single-file core (NO Flask)
# -------------------------------

def extract_snlm0e_token(html):
    snlm0e_patterns = [
        r'"SNlM0e":"([^"]+)"',
        r"'SNlM0e':'([^']+)'",
        r'SNlM0e["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'"FdrFJe":"([^"]+)"',
        r"'FdrFJe':'([^']+)'",
        r'FdrFJe["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'"cfb2h":"([^"]+)"',
        r"'cfb2h':'([^']+)'",
        r'cfb2h["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'at["\']?\s*[:=]\s*["\']([^"\']{50,})["\']',
        r'"at":"([^"]+)"',
        r'"token":"([^"]+)"',
        r'data-token["\']?\s*=\s*["\']([^"\']+)["\']',
    ]

    for pattern in snlm0e_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            token = match.group(1)
            if len(token) > 20:
                return token
    return None


def extract_from_script_tags(html):
    soup = BeautifulSoup(html, 'html.parser')
    script_tags = soup.find_all('script')

    for script in script_tags:
        if script.string:
            script_content = script.string

            if 'SNlM0e' in script_content or 'FdrFJe' in script_content:
                token = extract_snlm0e_token(script_content)
                if token:
                    return token

            json_patterns = [
                r'\{[^}]*"[^"]*token[^"]*"[^}]*\}',
                r'\{[^}]*SNlM0e[^}]*\}',
                r'\{[^}]*FdrFJe[^}]*\}',
            ]

            for pattern in json_patterns:
                for match in re.finditer(pattern, script_content, re.IGNORECASE):
                    try:
                        json_obj = json.loads(match.group(0))
                        for _k, v in json_obj.items():
                            if isinstance(v, str) and len(v) > 50:
                                return v
                    except Exception:
                        continue
    return None


def extract_build_and_session_params(html):
    params = {}

    bl_patterns = [
        r'bl["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'"bl":"([^"]+)"',
        r'buildLabel["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'boq[_-]assistant[^"\']*_(\d+\.\d+[^"\']*)',
        r'/_/BardChatUi.*?bl=([^&"\']+)',
    ]
    for pattern in bl_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            params['bl'] = match.group(1)
            break

    fsid_patterns = [
        r'f\.sid["\']?\s*[:=]\s*["\']?([^"\'&\s]+)',
        r'"fsid":"([^"]+)"',
        r'f\.sid=([^&"\']+)',
        r'sessionId["\']?\s*[:=]\s*["\']([^"\']+)["\']',
    ]
    for pattern in fsid_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            params['fsid'] = match.group(1)
            break

    reqid_match = re.search(r'_reqid["\']?\s*[:=]\s*["\']?(\d+)', html)
    if reqid_match:
        params['reqid'] = int(reqid_match.group(1))

    if not params.get('bl'):
        params['bl'] = 'boq_assistant-bard-web-server_20251217.07_p5'
    if not params.get('fsid'):
        params['fsid'] = str(-1 * int(time.time() * 1000))
    if not params.get('reqid'):
        params['reqid'] = int(time.time() * 1000) % 1000000

    return params


# -------------------------------
# Gemini3 session cache (reduces latency)
# -------------------------------
_G3_CACHE = {"data": None, "ts": 0.0}
_G3_CACHE_TTL_SECONDS = 900  # 15 minutes


def scrape_fresh_session():
    session = requests.Session()
    url = 'https://gemini.google.com/app'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-site': 'none',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-dest': 'document',
        'upgrade-insecure-requests': '1',
        'cache-control': 'no-cache',
        'pragma': 'no-cache'
    }

    try:
        response = session.get(url, headers=headers, timeout=30)
        html = response.text

        cookies = {c.name: c.value for c in session.cookies}

        snlm0e = extract_snlm0e_token(html) or extract_from_script_tags(html)
        if not snlm0e:
            return None

        params = extract_build_and_session_params(html)

        return {
            'session': session,
            'cookies': cookies,
            'snlm0e': snlm0e,
            'bl': params['bl'],
            'fsid': params['fsid'],
            'reqid': params['reqid'],
            'html': html
        }
    except Exception:
        return None


def build_payload(prompt, snlm0e):
    escaped_prompt = prompt.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    session_id = uuid.uuid4().hex
    request_uuid = str(uuid.uuid4()).upper()

    payload_data = [
        [escaped_prompt, 0, None, None, None, None, 0],
        ["en-US"],
        ["", "", "", None, None, None, None, None, None, ""],
        snlm0e,
        session_id,
        None,
        [0],
        1,
        None,
        None,
        1,
        0,
        None,
        None,
        None,
        None,
        None,
        [[0]],
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        1,
        None,
        None,
        [4],
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        [2],
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        0,
        None,
        None,
        None,
        None,
        None,
        request_uuid,
        None,
        []
    ]

    payload_str = json.dumps(payload_data, separators=(',', ':'))
    escaped_payload = payload_str.replace('\\', '\\\\').replace('"', '\\"')

    return {'f.req': f'[null,"{escaped_payload}"]', '': ''}


def parse_streaming_response(response_text):
    lines = response_text.strip().split('\n')
    full_text = ""

    for line in lines:
        if not line or line.startswith(')]}'):
            continue
        try:
            if line.isdigit():
                continue
            data = json.loads(line)
            if isinstance(data, list) and len(data) > 0:
                if data[0][0] == "wrb.fr" and len(data[0]) > 2:
                    inner_json = data[0][2]
                    if inner_json:
                        parsed = json.loads(inner_json)
                        if isinstance(parsed, list) and len(parsed) > 4:
                            content_array = parsed[4]
                            if isinstance(content_array, list) and len(content_array) > 0:
                                first_item = content_array[0]
                                if isinstance(first_item, list) and len(first_item) > 0:
                                    response_id = first_item[0]
                                    if isinstance(response_id, str) and response_id.startswith('rc_'):
                                        if len(first_item) > 1 and isinstance(first_item[1], list):
                                            text_array = first_item[1]
                                            if len(text_array) > 0:
                                                text_content = text_array[0]
                                                if isinstance(text_content, str) and len(text_content) > len(full_text):
                                                    full_text = text_content
        except Exception:
            continue

    if full_text:
        full_text = full_text.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
    return full_text if full_text else None


def chat_with_gemini(prompt):
    start_time = time.time()
    # Reuse a cached Gemini session to reduce latency.
    scraped = None
    now_ts = time.time()
    try:
        cached = _G3_CACHE.get("data")
        if cached and (now_ts - float(_G3_CACHE.get("ts") or 0.0) < _G3_CACHE_TTL_SECONDS):
            scraped = cached
    except Exception:
        scraped = None

    if not scraped:
        scraped = scrape_fresh_session()
        if not scraped:
            return {'success': False, 'error': 'Failed to establish session with Gemini'}
        _G3_CACHE["data"] = scraped
        _G3_CACHE["ts"] = now_ts

    session = scraped['session']

    cookies = scraped['cookies']
    snlm0e = scraped['snlm0e']
    bl = scraped['bl']
    fsid = scraped['fsid']
    reqid = scraped['reqid']

    # refresh _reqid each request to avoid stale sessions
    reqid = int(time.time() * 1000) % 1000000
    base_url = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
    url = f"{base_url}?bl={bl}&f.sid={fsid}&hl=en-US&_reqid={reqid}&rt=c"

    payload = build_payload(prompt, snlm0e)
    cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'x-same-domain': '1',
        'origin': 'https://gemini.google.com',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'referer': 'https://gemini.google.com/',
        'Cookie': cookie_str
    }

    try:
        response = session.post(url, data=payload, headers=headers, timeout=20)
        if response.status_code != 200:
            return {'success': False, 'error': f'HTTP {response.status_code}'}

        result = parse_streaming_response(response.text)

        response_time = round(time.time() - start_time, 2)
        if result:
            return {
                'success': True,
                'response': result,
                'metadata': {
                    'response_time': f'{response_time}s',
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'model': 'gemini',
                    'character_count': len(result),
                    'word_count': len(result.split())
                }
            }
        return {'success': False, 'error': 'No response received from Gemini'}

    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': str(e)}

def gemini3_solve(prompt: str) -> str:
    """
    Single-file Gemini3 wrapper.
    Returns only the response text (same as your old usage).
    """
    res = chat_with_gemini(prompt)
    if isinstance(res, dict) and res.get("success") and res.get("response"):
        return str(res["response"]).strip()
    err = res.get("error") if isinstance(res, dict) else None
    raise RuntimeError(err or "Gemini3 solve failed.")


# ---------------------------
# MESSAGE HELPER FUNCTIONS
# ---------------------------
async def ok(update: Update, title: str, body: str) -> None:
    """Send success message using plain text."""
    msg = ui_box_text(title, body, emoji="✅")
    await safe_reply(update, msg)


async def ok_html(update: Update, title: str, body_html: str, emoji: str = "✅", footer_html: str = "") -> None:
    """Send success message with HTML formatting."""
    msg = ui_box_html(title, body_html, emoji=emoji, footer_html=footer_html)
    await safe_reply(update, msg)


async def warn(update: Update, title: str, body: str) -> None:
    """Send warning message using plain text."""
    msg = ui_box_text(title, body, emoji="⚠️")
    await safe_reply(update, msg)


async def warn_html(update: Update, title: str, body_html: str, emoji: str = "⚠️", footer_html: str = "") -> None:
    """Send warning message with HTML formatting."""
    msg = ui_box_html(title, body_html, emoji=emoji, footer_html=footer_html)
    await safe_reply(update, msg)


async def err(update: Update, title: str, body: str) -> None:
    """Send error message using plain text."""
    msg = ui_box_text(title, body, emoji="❌")
    await safe_reply(update, msg)


async def err_html(update: Update, title: str, body_html: str, emoji: str = "❌", footer_html: str = "") -> None:
    """Send error message with HTML formatting."""
    msg = ui_box_html(title, body_html, emoji=emoji, footer_html=footer_html)
    await safe_reply(update, msg)


async def info_html(update: Update, title: str, body_html: str, emoji: str = "ℹ️", footer_html: str = "") -> None:
    """Send informational message with HTML formatting."""
    msg = ui_box_html(title, body_html, emoji=emoji, footer_html=footer_html)
    await safe_reply(update, msg)


def reply_text_or_caption(update: Update) -> str:
    """
    Returns text from the replied message if present; otherwise empty string.
    """
    if not update.message or not update.message.reply_to_message:
        return ""
    m = update.message.reply_to_message
    return (m.text or m.caption or "").strip()


def parse_ticket_id_from_any_message(msg) -> Optional[int]:
    if not msg:
        return None
    text = "\n".join([
        str(getattr(msg, "text", "") or ""),
        str(getattr(msg, "caption", "") or ""),
    ]).strip()
    if not text:
        return None
    patterns = [
        r"(?:^|\n)\s*Ticket\s*[:#-]\s*(\d+)",
        r"(?:^|\n)\s*Ticket ID\s*[:#-]\s*(\d+)",
        r"/reply\s+(\d+)(?:\s|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
    return None


# ---------------------------
# CLEANER / PARSER
# ---------------------------
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)", re.IGNORECASE)
BRACKET_ANY_RE = re.compile(r"\[[^\]]*\]")  # removes [ ... ] anywhere
OPT_LINE_RE = re.compile(r"^\s*[\(\[]?[a-zA-Z0-9\u0980-\u09ff]+[\)\]\.]+\s+")


def get_user_filters(user_id: int) -> List[str]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT phrase FROM filters WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [r["phrase"] for r in rows]


def clean_common(text: str, user_id: int) -> str:
    if not text:
        return ""

    for phrase in get_user_filters(user_id):
        if phrase:
            text = text.replace(phrase, "")

    text = BRACKET_ANY_RE.sub("", text)

    # Remove leading numbering: "62." "62)" "(62)" "৬২." "৬২)" "62।"
    text = re.sub(r"^\s*\(?[0-9\u09E6-\u09EF]+\)?\s*[\.\)\।]\s*", "", text)

    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def clean_explanation(text: str, user_id: int) -> str:
    if not text:
        return ""
    text = clean_common(text, user_id)
    # Remove common boilerplate headings
    text = re.sub(r"^\s*(Explanation\s*(for\s*question\s*\d+)?|Explain)\s*[:\-]*\s*", "", text, flags=re.IGNORECASE)
    text = MD_LINK_RE.sub("", text)
    text = BRACKET_ANY_RE.sub("", text)
    text = URL_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

