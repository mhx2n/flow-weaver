# ──────────────────────────────────────────────────────────────────────────────
# Section 78 (2026-08-01) — Owner quiz-generation upgrade
#
#  1) `.aiq` — unlimited quiz generation from ANY text/topic (reply to a text
#     message, or pass the topic inline). Same buffer/post pipeline as `.gen`.
#  2) Exam-standard targeting for BOTH `.aiq` and `.gen`:
#        .aiq buet 50   .gen med dmc 30   .aiq board 20   .gen ver du 40
#     (buet/cuet/kuet/ruet/du/ju/cu/ru/sust/dmc/medical/board/hsc/…)
#  3) MATH questions are posted in an advanced 2-message format:
#        message #1 → native RICH TEXT card with the full question, options
#                     and professional LaTeX math
#        message #2 → quiz poll: "উপরের প্রশ্নের সঠিক উত্তর কোনটি?"
#                     with option labels only ((ক)(খ)(গ)(ঘ) / (A)(B)(C)(D))
#     Owner picks the poll language with `/qver bn|en`, toggle with
#     `/mathpost on|off`.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import re as _re78
import contextlib as _cx78

import telegram as _tg78


def _log78(msg: str) -> None:
    with _cx78.suppress(Exception):
        logger.info("[S78] %s", msg)  # type: ignore[name-defined]


# ── 0) tiny settings store (sqlite, same db as the rest of the bot) ──────────

def _m78_init() -> None:
    with _cx78.suppress(Exception):
        conn = db_connect()  # type: ignore[name-defined]
        conn.execute("CREATE TABLE IF NOT EXISTS m78_settings(k TEXT PRIMARY KEY, v TEXT)")
        conn.commit()
        conn.close()


_m78_init()


def _m78_get(key: str, default: str = "") -> str:
    try:
        conn = db_connect()  # type: ignore[name-defined]
        cur = conn.execute("SELECT v FROM m78_settings WHERE k=?", (str(key),))
        row = cur.fetchone()
        conn.close()
        if row and row[0] is not None:
            return str(row[0])
    except Exception:
        pass
    return default


def _m78_set(key: str, value: str) -> None:
    with _cx78.suppress(Exception):
        conn = db_connect()  # type: ignore[name-defined]
        conn.execute(
            "INSERT INTO m78_settings(k, v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (str(key), str(value)),
        )
        conn.commit()
        conn.close()


def _math_post_on_78() -> bool:
    return _m78_get("math_post", "on").strip().lower() not in ("0", "off", "false", "no")


def _quiz_lang_78() -> str:
    return "en" if _m78_get("quiz_lang", "bn").strip().lower().startswith("en") else "bn"


# ── 1) exam-standard presets ────────────────────────────────────────────────

_STD_78 = {
    "buet": ("BUET", "BUET (Bangladesh University of Engineering & Technology) admission standard — very high difficulty, multi-step conceptual/analytical Physics-Chemistry-Math problems, no direct memory questions."),
    "cuet": ("CUET", "CUET engineering admission standard — analytical, calculation-heavy engineering level problems."),
    "kuet": ("KUET", "KUET engineering admission standard — analytical, calculation-heavy engineering level problems."),
    "ruet": ("RUET", "RUET engineering admission standard — analytical, calculation-heavy engineering level problems."),
    "du": ("DU", "University of Dhaka (DU) admission unit standard — concept + application mix, exam-authentic wording and difficulty."),
    "ju": ("JU", "Jahangirnagar University (JU) admission standard — short, tricky, concept-testing questions."),
    "cu": ("CU", "University of Chittagong (CU) admission standard — balanced concept and application questions."),
    "ru": ("RU", "University of Rajshahi (RU) admission standard — balanced concept and application questions."),
    "sust": ("SUST", "SUST admission standard — analytical, slightly math-heavy questions."),
    "dmc": ("DMC", "Dhaka Medical College / MBBS (DGHS) admission standard — precise, single-fact-plus-reasoning medical admission level."),
    "medical": ("MEDICAL", "MBBS/DGHS medical admission standard — precise biology-chemistry-physics admission level questions."),
    "dental": ("DENTAL", "BDS dental admission standard."),
    "gst": ("GST", "GST (guccho) integrated university admission standard."),
    "board": ("BOARD", "Bangladesh Education Board HSC/SSC board-exam standard — textbook-faithful MCQ wording and difficulty."),
    "hsc": ("HSC", "HSC syllabus standard — textbook-level MCQs."),
    "ssc": ("SSC", "SSC syllabus standard — textbook-level MCQs."),
    "varsity": ("VARSITY", "General public-university admission standard."),
    "bcs": ("BCS", "BCS preliminary standard — factual precision with tricky distractors."),
}

_STD_ALIAS_78 = {
    "bd": "board", "boards": "board", "dhaka": "du", "dumc": "dmc", "mbbs": "medical",
    "med": None, "eng": None, "engg": None, "ver": None, "std": None,  # legacy mode tokens: ignore here
    "sustaid": "sust", "guccho": "gst",
}


def _std_token_78(tok: str):
    t = _re78.sub(r"[^a-z]", "", str(tok or "").lower())
    if not t:
        return None
    if t in _STD_78:
        return t
    mapped = _STD_ALIAS_78.get(t)
    if mapped:
        return mapped
    return None


def _extract_standard_78(text: str, args):
    """Return (std_key or None, cleaned_args)."""
    toks = [str(a or "").strip() for a in (args or []) if str(a or "").strip()]
    if not toks:
        parts = _re78.split(r"\s+", str(text or "").strip())
        toks = parts[1:] if len(parts) > 1 else []
    std = None
    cleaned = []
    for t in toks:
        k = _std_token_78(t)
        if k and std is None:
            std = k
            continue
        cleaned.append(t)
    return std, cleaned


_MATH_DIRECTIVE_78 = (
    "MATH / PHYSICS FORMATTING RULE (mandatory): whenever a question, option or "
    "explanation contains mathematics, write the math in valid LaTeX wrapped in "
    "single dollar signs, e.g. $\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}$, "
    "$\\lim_{x\\to0}\\frac{\\sin x}{x}$, $\\int_0^1 x^2dx$. Never write broken or "
    "half-escaped LaTeX, never use images, never leave stray backslashes. "
    "Math questions must be genuinely solvable and the explanation must show the "
    "key steps compactly."
)


def _standard_directive_78(std) -> str:
    if not std:
        return ""
    label, desc = _STD_78.get(std, (str(std).upper(), ""))
    return (
        f"\n\nEXAM STANDARD TARGET: {label}.\n{desc}\n"
        f"Every generated MCQ must match the real {label} question style, "
        f"difficulty, option pattern and language.\n" + _MATH_DIRECTIVE_78
    )


# active standard for the running generation job
_active_std_78 = None


def _apply_std_to_ctx_78(ocr_ctx):
    ctx = dict(ocr_ctx or {})
    extra = _standard_directive_78(globals().get("_active_std_78"))
    if not extra:
        extra = "\n\n" + _MATH_DIRECTIVE_78
    for key in ("clean_text", "raw_markdown"):
        if str(ctx.get(key) or "").strip():
            ctx[key] = str(ctx[key]) + extra
            break
    else:
        ctx["clean_text"] = str(ctx.get("clean_text") or "") + extra
    return ctx


_prev_gen_sync_78 = globals().get("_generate_quizzes_from_ocr_sync")

if callable(_prev_gen_sync_78):
    def _generate_quizzes_from_ocr_sync(ocr_ctx, desired, user_id):  # noqa: F811
        return _prev_gen_sync_78(_apply_std_to_ctx_78(ocr_ctx), desired, user_id)

    globals()["_generate_quizzes_from_ocr_sync"] = _generate_quizzes_from_ocr_sync


# ── 2) `.gen` keeps working, now also understands a standard token ───────────

_prev_cmd_gen_78 = globals().get("cmd_gen")

if callable(_prev_cmd_gen_78):
    async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
        std = None
        with _cx78.suppress(Exception):
            std, cleaned = _extract_standard_78(
                (update.message.text if update and update.message else "") or "",
                list(context.args or []),
            )
            if std:
                context.args = cleaned
        globals()["_active_std_78"] = std or globals().get("_sticky_std_78")
        try:
            return await _prev_cmd_gen_78(update, context)
        finally:
            pass  # keep the standard sticky for the follow-up picker/count step

    globals()["cmd_gen"] = cmd_gen


# ── 3) `.aiq` — unlimited quiz generation straight from text/topic ───────────

def _aiq_usage_78() -> str:
    names = ", ".join(sorted(_STD_78.keys()))
    return ui_box_html(  # type: ignore[name-defined]
        "AI Quiz from Text",
        (
            "একটি টেক্সট/টপিক মেসেজে reply দিয়ে চালাও:\n"
            "<code>.aiq buet 50</code>\n"
            "<code>.aiq dmc 30</code>\n"
            "<code>.aiq board 100</code>\n"
            "অথবা সরাসরি: <code>.aiq du 20 ভেক্টর ও গতিবিদ্যা</code>\n\n"
            f"Standards: <code>{h(names)}</code>\n"  # type: ignore[name-defined]
            "Count না দিলে ডিফল্ট 20; unlimited-এর জন্য বড় সংখ্যা দাও (যেমন 300)."
        ),
        emoji="🧠",
    )


def _parse_aiq_args_78(text: str, args):
    std, cleaned = _extract_standard_78(text, args)
    count = None
    rest = []
    for t in cleaned:
        m = _re78.fullmatch(r"\d{1,4}", _re78.sub(r"[^0-9]", "", t) or "x")
        if m and count is None:
            count = max(1, min(2000, int(m.group(0))))
            continue
        rest.append(t)
    return std, (count or 20), " ".join(rest).strip()


async def cmd_aiq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)  # type: ignore[name-defined]
    if not update.message or not update.effective_user:
        raise ApplicationHandlerStop  # type: ignore[name-defined]
    uid = int(update.effective_user.id)
    if is_banned(uid):  # type: ignore[name-defined]
        raise ApplicationHandlerStop  # type: ignore[name-defined]
    is_staff = False
    with _cx78.suppress(Exception):
        is_staff = bool(is_owner(uid) or is_admin(uid))  # type: ignore[name-defined]
    if not is_staff:
        raise ApplicationHandlerStop  # type: ignore[name-defined]

    std, count, inline_topic = _parse_aiq_args_78(update.message.text or "", list(context.args or []))
    reply = update.message.reply_to_message
    topic = ""
    if reply is not None:
        topic = str(getattr(reply, "text", None) or getattr(reply, "caption", None) or "").strip()
    if inline_topic:
        topic = (topic + "\n\n" + inline_topic).strip() if topic else inline_topic
    if len(topic) < 3:
        with _cx78.suppress(Exception):
            await update.message.reply_text(_aiq_usage_78(), parse_mode=ParseMode.HTML)  # type: ignore[name-defined]
        raise ApplicationHandlerStop  # type: ignore[name-defined]

    label = _STD_78.get(std, ("AUTO", ""))[0] if std else "AUTO"
    status = None
    with _cx78.suppress(Exception):
        status = await update.message.reply_text(
            ui_box_html(  # type: ignore[name-defined]
                "Generating from Text",
                f"Standard: <b>{h(label)}</b>\nTarget: <code>{count}</code> MCQ\nSource: <code>{len(topic)}</code> chars",
                emoji="⏳",
            ),
            parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
        )

    ocr_ctx = {"clean_text": topic, "raw_markdown": topic, "items": [], "source_label": "text"}
    globals()["_active_std_78"] = std
    globals()["_sticky_std_78"] = std
    total_added = total_dup = 0
    try:
        remaining = int(count)
        rounds = 0
        while remaining > 0 and rounds < 20:
            chunk = min(60, remaining)
            try:
                added, dup = await _generate_to_buffer_59(update, context, ocr_ctx, uid, chunk, "std")  # type: ignore[name-defined]
            except Exception as e:
                db_log("ERROR", "aiq_round_failed_78", {"user_id": uid, "error": str(e)[:200]})  # type: ignore[name-defined]
                added, dup = 0, 0
            total_added += int(added or 0)
            total_dup += int(dup or 0)
            remaining -= chunk
            rounds += 1
            if not added:
                break
            with _cx78.suppress(Exception):
                if status and remaining > 0:
                    await status.edit_text(
                        ui_box_html(  # type: ignore[name-defined]
                            "Generating from Text",
                            f"Standard: <b>{h(label)}</b>\nAdded so far: <code>{total_added}</code>/<code>{count}</code>",
                            emoji="⏳",
                        ),
                        parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
                    )
            with _cx78.suppress(Exception):
                if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:  # type: ignore[name-defined]
                    break
    finally:
        globals()["_active_std_78"] = None

    with _cx78.suppress(Exception):
        body = (
            f"Standard: <b>{h(label)}</b>\n"
            f"Added: <code>{total_added}</code>\n"
            f"Duplicates skipped: <code>{total_dup}</code>\n"
            f"Buffered total: <code>{buffer_count(uid)}</code>"  # type: ignore[name-defined]
        )
        if status:
            await status.edit_text(
                ui_box_html("Text → Quiz Buffer" if total_added else "Generation Failed", body, emoji="✅" if total_added else "⚠️"),  # type: ignore[name-defined]
                parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
            )
    if total_added > 0:
        with _cx78.suppress(Exception):
            await _send_pb_action_card(context, update.message.chat_id, uid, total_added)  # type: ignore[name-defined]
    raise ApplicationHandlerStop  # type: ignore[name-defined]


# ── 4) owner controls: /qver bn|en , /mathpost on|off ────────────────────────

def _is_owner_78(uid: int) -> bool:
    try:
        return bool(is_owner(int(uid)))  # type: ignore[name-defined]
    except Exception:
        return False


async def cmd_qver_78(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not _is_owner_78(update.effective_user.id):
        return
    arg = (list(context.args or []) or [""])[0].strip().lower()
    if arg.startswith("en"):
        _m78_set("quiz_lang", "en")
    elif arg.startswith("bn") or arg.startswith("bd") or arg.startswith("ba"):
        _m78_set("quiz_lang", "bn")
    lang = _quiz_lang_78()
    with _cx78.suppress(Exception):
        await update.message.reply_text(
            ui_box_html(  # type: ignore[name-defined]
                "Quiz Language",
                f"Poll version: <b>{'English' if lang == 'en' else 'বাংলা'}</b>\n"
                f"Labels: <code>{'A B C D' if lang == 'en' else 'ক খ গ ঘ'}</code>\n\n"
                "Change: <code>/qver bn</code> | <code>/qver en</code>",
                emoji="🌐",
            ),
            parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
        )


async def cmd_mathpost_78(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not _is_owner_78(update.effective_user.id):
        return
    arg = (list(context.args or []) or [""])[0].strip().lower()
    if arg in ("on", "1", "true", "yes"):
        _m78_set("math_post", "on")
    elif arg in ("off", "0", "false", "no"):
        _m78_set("math_post", "off")
    with _cx78.suppress(Exception):
        await update.message.reply_text(
            ui_box_html(  # type: ignore[name-defined]
                "Math Rich Posting",
                f"Status: <b>{'ON' if _math_post_on_78() else 'OFF'}</b>\n"
                "ON হলে math প্রশ্ন প্রথমে rich text card, তারপর label-only quiz poll যাবে.\n\n"
                "Change: <code>/mathpost on</code> | <code>/mathpost off</code>",
                emoji="➗",
            ),
            parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
        )


# ── 5) MATH → rich card + label-only quiz poll ──────────────────────────────

_LABELS_BN_78 = ["ক", "খ", "গ", "ঘ", "ঙ", "চ", "ছ", "জ", "ঝ", "ঞ"]
_LABELS_EN_78 = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]

_MATH_MARKERS_78 = (
    _re78.compile(r"\\(frac|sqrt|int|lim|sum|prod|sin|cos|tan|log|ln|pm|theta|pi|alpha|beta|infty|begin\{|displaystyle|cdot|times|div|leq|geq|neq|Rightarrow)"),
    _re78.compile(r"\$[^$\n]{2,}\$"),
    _re78.compile(r"\\\(|\\\[|\\\)|\\\]"),
    _re78.compile(r"[0-9a-zA-Z\)\}]\s*\^\s*[0-9a-zA-Z\{\-]"),
    _re78.compile(r"[√∫∑∏≤≥≠±∞π∂θ×÷⇒→]"),
    _re78.compile(r"(?:^|\s)(?:সমীকরণ|ম্যাট্রিক্স|অন্তরজ|সমাকলন|উপবৃত্ত|বৃত্তের|ত্রিভুজ|লব্ধি|ভেক্টর|লগারিদম|অসমতা|স্থানাঙ্ক)"),
    _re78.compile(r"\b(equation|matrix|integral|derivative|limit|logarithm|coordinate|vector|ellipse|hyperbola|parabola|probability)\b", _re78.I),
    _re78.compile(r"\d+\s*/\s*\d+\s*[+\-=]"),
)


def _is_math_78(*chunks) -> bool:
    s = " ".join(str(c or "") for c in chunks)
    if not s.strip():
        return False
    hits = 0
    for rx in _MATH_MARKERS_78:
        if rx.search(s):
            hits += 1
            if hits >= 1:
                return True
    return False


def _norm_key_78(s: str) -> str:
    return _re78.sub(r"\s+", " ", _re78.sub(r"<[^>]+>", "", str(s or ""))).strip().lower()[:160]


# raw (LaTeX-preserving) item registry, filled just before polls are sent
_RAW_ITEMS_78: dict = {}


def _remember_raw_78(item: dict) -> None:
    with _cx78.suppress(Exception):
        q = str(item.get("questions") or item.get("question") or "").strip()
        if not q:
            return
        payload = {
            "questions": q,
            "options": [str(item.get(f"option{i}") or "").strip() for i in range(1, 6)],
            "explanation": str(item.get("explanation") or "").strip(),
        }
        _RAW_ITEMS_78[_norm_key_78(q)] = payload
        if len(_RAW_ITEMS_78) > 4000:
            for k in list(_RAW_ITEMS_78.keys())[:2000]:
                _RAW_ITEMS_78.pop(k, None)


_prev_sanitize_item_78 = globals().get("_sanitize_item_for_poll")

if callable(_prev_sanitize_item_78):
    def _sanitize_item_for_poll(it):  # noqa: F811
        out = _prev_sanitize_item_78(it)
        with _cx78.suppress(Exception):
            _remember_raw_78(dict(it or {}))
            # index by the sanitized question too, that is what send_poll sees
            raw = dict(it or {})
            q_clean = str((out or {}).get("questions") or "").strip()
            if q_clean:
                _RAW_ITEMS_78[_norm_key_78(q_clean)] = {
                    "questions": str(raw.get("questions") or q_clean),
                    "options": [str(raw.get(f"option{i}") or "").strip() for i in range(1, 6)],
                    "explanation": str(raw.get("explanation") or "").strip(),
                }
        return out

    globals()["_sanitize_item_for_poll"] = _sanitize_item_for_poll


def _tidy_latex_78(s: str) -> str:
    t = str(s or "")
    t = t.replace("\r", "")
    t = _re78.sub(r"\\\((.+?)\\\)", r"$\1$", t, flags=_re78.S)
    t = _re78.sub(r"\\\[(.+?)\\\]", r"$$\1$$", t, flags=_re78.S)
    t = _re78.sub(r"\$\$\s*\\displaystyle\s*", "$$", t)
    t = _re78.sub(r"\$\s*\\displaystyle\s*", "$", t)
    t = _re78.sub(r"[ \t]+", " ", t)
    return t.strip()


def _rich_math_card_78(question: str, options, explanation: str = "", lang: str = "bn") -> str:
    labels = _LABELS_EN_78 if lang == "en" else _LABELS_BN_78
    q = _tidy_latex_78(question)
    lines = [q, ""]
    for i, opt in enumerate(options or []):
        o = _tidy_latex_78(opt)
        if not o:
            continue
        lines.append(f"**({labels[i] if i < len(labels) else i + 1})** {o}")
    return "\n".join(lines).strip()


def _poll_prompt_78(lang: str) -> str:
    return ("Which one is the correct answer to the question above?"
            if lang == "en" else "উপরের প্রশ্নের সঠিক উত্তর কোনটি?")


_POLL_MARK_78 = ("উপরের প্রশ্নের সঠিক উত্তর কোনটি?", "Which one is the correct answer to the question above?")


async def _send_math_card_78(bot, chat_id, markdown, *, reply_to=None, thread_id=None) -> bool:
    """Native rich first; graceful HTML fallback. Never raises."""
    sender = globals().get("rich_send_77")
    if callable(sender):
        try:
            msg = await sender(bot, chat_id, markdown, reply_to=reply_to, thread_id=thread_id)
            if msg:
                return True
        except Exception as e:
            _log78(f"rich card failed, falling back: {e}")
    # Fallback: readable HTML (LaTeX kept inline, monospace for the math parts)
    try:
        html_body = markdown
        with _cx78.suppress(Exception):
            html_body = h(markdown)  # type: ignore[name-defined]
        html_body = _re78.sub(r"\*\*\((.{1,3})\)\*\*", r"<b>(\1)</b>", html_body)
        kw = {"chat_id": chat_id, "text": html_body[:4000],
              "parse_mode": ParseMode.HTML, "disable_web_page_preview": True}  # type: ignore[name-defined]
        if thread_id:
            kw["message_thread_id"] = thread_id
        await bot.send_message(**kw)
        return True
    except Exception as e:
        _log78(f"fallback card failed: {e}")
        return False


_PTB_SEND_POLL_78 = getattr(_tg78.Bot, "_s78_original_send_poll", None) or _tg78.Bot.send_poll


async def _send_poll_78(self, chat_id=None, question=None, options=None, *args, **kwargs):
    q_text = kwargs.pop("question", question)
    opts = kwargs.pop("options", options)
    cid = kwargs.pop("chat_id", chat_id)
    try:
        opt_list = [str(getattr(o, "text", o) or "").strip() for o in (opts or [])]
    except Exception:
        opt_list = []

    try:
        already = any(m in str(q_text or "") for m in _POLL_MARK_78)
        if (not already) and _math_post_on_78() and len(opt_list) >= 2:
            raw = _RAW_ITEMS_78.get(_norm_key_78(q_text)) or {}
            r_q = str(raw.get("questions") or q_text or "")
            r_opts = [o for o in (raw.get("options") or []) if str(o or "").strip()] or opt_list
            if len(r_opts) != len(opt_list):
                r_opts = opt_list
            if _is_math_78(r_q, " ".join(r_opts), str(raw.get("explanation") or "")):
                lang = _quiz_lang_78()
                card = _rich_math_card_78(r_q, r_opts, str(raw.get("explanation") or ""), lang)
                thread_id = kwargs.get("message_thread_id")
                ok = await _send_math_card_78(self, cid, card, thread_id=thread_id)
                if ok:
                    labels = _LABELS_EN_78 if lang == "en" else _LABELS_BN_78
                    new_opts = [f"({labels[i] if i < len(labels) else i + 1})" for i in range(len(opt_list))]
                    return await _PTB_SEND_POLL_78(self, cid, _poll_prompt_78(lang), new_opts, *args, **kwargs)
    except Exception as e:
        _log78(f"math poll upgrade skipped: {e}")

    return await _PTB_SEND_POLL_78(self, cid, q_text, opts, *args, **kwargs)


with _cx78.suppress(Exception):
    if not getattr(_tg78.Bot, "_s78_patched", False):
        _tg78.Bot._s78_original_send_poll = _PTB_SEND_POLL_78
        _tg78.Bot.send_poll = _send_poll_78
        _tg78.Bot._s78_patched = True
        _log78("send_poll patched for math rich posting")


# ── 6) registration ─────────────────────────────────────────────────────────

if "build_app" in globals():
    _prev_build_app_78 = build_app  # type: ignore[name-defined]

    def build_app() -> Application:  # noqa: F811  # type: ignore[name-defined]
        app = _prev_build_app_78()
        with _cx78.suppress(Exception):
            if "_register_dual_command" in globals():
                _register_dual_command(app, "aiq", cmd_aiq, group=-500)  # type: ignore[name-defined]
            else:
                app.add_handler(CommandHandler("aiq", cmd_aiq), group=-500)  # type: ignore[name-defined]
                app.add_handler(_build_dot_command_handler("aiq", cmd_aiq), group=-500)  # type: ignore[name-defined]
        with _cx78.suppress(Exception):
            if "_register_dual_command" in globals():
                _register_dual_command(app, "qver", cmd_qver_78, group=-490)  # type: ignore[name-defined]
                _register_dual_command(app, "mathpost", cmd_mathpost_78, group=-490)  # type: ignore[name-defined]
            else:
                app.add_handler(CommandHandler("qver", cmd_qver_78), group=-490)  # type: ignore[name-defined]
                app.add_handler(CommandHandler("mathpost", cmd_mathpost_78), group=-490)  # type: ignore[name-defined]
        return app

_log78("section 78 ready: .aiq text-quiz, exam standards, math rich posting")

# ===== END SECTION 78 =====
