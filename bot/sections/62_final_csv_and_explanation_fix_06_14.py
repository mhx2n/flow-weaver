# ──────────────────────────────────────────────────────────────────────────────
# Section 62 (2026-06-14) — Final export-format + explanation scrub overlay.
#
# Fixes ONLY the reported issues:
#   • Action-card “Export CSV” now exports exactly like .d/.done:
#       questions, option1..option5, answer, explanation, type, section
#     plus the matching JSON file, then clears the buffer.
#   • After clicking the CSV button, the action-card message is deleted.
#   • Explanation text is scrubbed in every path (buffer/export/poll/generation)
#     so boilerplate like “Option 4 is correct…”, “সঠিক উত্তর…”, “উদ্দীপক হতে”,
#     “প্রদত্ত পাঠ্য…”, “পাঠ্য পত্র হতে”, “পাঠ্যবইয়ের … নম্বর প্রশ্ন” cannot leak.
# ──────────────────────────────────────────────────────────────────────────────

import hashlib as _hl62
import json as _json62
import re as _re62


_EXPL_EXTRA_RULES_62 = (
    "\n[STRICT EXPLANATION RULES — mandatory]\n"
    "• explanation must be the actual academic reason only; no boilerplate.\n"
    "• Never start with: Option N is correct, Correct answer is, Answer:, সঠিক উত্তর, এটাই সঠিক অপশন.\n"
    "• Never mention source/passage/book words: উদ্দীপক, প্রদত্ত পাঠ্য, পাঠ্য পত্র, পাঠ্যবই, পাঠ্যসূচি, নম্বর প্রশ্ন.\n"
    "• Do not say ‘from the passage/text/book’; write the concept/reason directly.\n"
    "• Keep it one short sentence under 160 characters, same language as the question.\n"
)


_EXPL_PREFIX_PATTERNS_62 = [
    _re62.compile(r"^\s*(?:Option|Answer|Correct\s*answer|The\s+correct\s+(?:answer|option))\s*[A-Ea-e0-9০-৯]*\s*(?:is|:|=|-|–|—)?\s*(?:correct)?\s*(?:because|as)?[\s:,.।;\-–—]*", _re62.I),
    _re62.compile(r"^\s*(?:সঠিক\s*(?:উত্তর|অপশন)|উত্তর)\s*(?:হলো|হল|হচ্ছে|হবে|:|ঃ)?\s*(?:[কখগঘঙa-eA-E১-৫০-৯0-9]+\s*)?(?:নম্বর\s*)?(?:অপশন)?\s*(?:কারণ|যেহেতু)?[\s:,.।;\-–—]*"),
    _re62.compile(r"^\s*এটাই\s*সঠিক\s*(?:অপশন|উত্তর)?\s*(?:কারণ|যেহেতু)?[\s:,.।;\-–—]*"),
    _re62.compile(r"^\s*(?:কারণ|যেহেতু|ব্যাখ্যা|Explanation|Reason)\s*[:ঃ,.।;\-–—]*", _re62.I),
    _re62.compile(r"^\s*(?:উদ্দ[ীি]পক(?:ের|টি)?|উদ্দ[ীি]পকের|প্রদত্ত\s*(?:পাঠ্য|পাঠ্যের|অনুচ্ছেদ|উদ্দ[ীি]পক)(?:ের)?|পাঠ্য\s*পত্র|পাঠ্যপত্র|পাঠ্যসূচি|লিখিত\s*অংশ)\s*(?:থেকে|হতে|অনুযায়ী|অনুযায়ী|এর\s*আলোকে|বিষয়ের?|বিষয়ের?|প্রশ্ন(?:ের)?)?[\s:,.।;\-–—]*"),
    _re62.compile(r"^\s*(?:পাঠ্যবই(?:য়ের|য়ের|এর)?|পাঠ্যের|পাঠ্য)\s*(?:[০-৯0-9]+\s*(?:নম্বর|নং)\s*)?(?:প্রশ্ন(?:ের)?|বিষয়ের?|বিষয়ের?)?\s*(?:থেকে|হতে|অনুযায়ী|অনুযায়ী|এর\s*আলোকে)?[\s:,.।;\-–—]*"),
    _re62.compile(r"^\s*(?:উপরের|নিচের|নিম্নের)\s*(?:তথ্য|চিত্র|অনুচ্ছেদ|আলোকে|উদ্দ[ীি]পক)[^।:,.]{0,80}[\s:,.।;\-–—]*"),
]

_BAD_EXPL_RE_62 = _re62.compile(
    r"(?i)(Option\s*[A-E0-9০-৯]+\s*(?:is\s*)?correct|correct\s+answer|the\s+correct\s+(?:answer|option)|"
    r"সঠিক\s*(?:উত্তর|অপশন)|এটাই\s*সঠিক|উদ্দ[ীি]পক|প্রদত্ত\s*পাঠ্য|পাঠ্য\s*পত্র|পাঠ্যপত্র|"
    r"পাঠ্যবই|পাঠ্যসূচি|লিখিত\s*অংশ|নম্বর\s*প্রশ্ন|নং\s*প্রশ্ন)"
)

_SOURCE_LEAD_RE_62 = _re62.compile(
    r"^\s*(?:উদ্দ[ীি]পক(?:ের|টি)?|প্রদত্ত\s*(?:পাঠ্য|পাঠ্যের|অনুচ্ছেদ|উদ্দ[ীি]পক)(?:ের)?|পাঠ্য\s*পত্র|পাঠ্যপত্র|পাঠ্যবই(?:য়ের|য়ের|এর)?|পাঠ্যসূচি|লিখিত\s*অংশ|পাঠ্যের|পাঠ্য)"
    r"(?:\s*[০-৯0-9]+\s*(?:নম্বর|নং))?"
    r"(?:\s*(?:প্রশ্ন(?:ের)?|বিষয়ের?|বিষয়ের?|থেকে|হতে|অনুযায়ী|অনুযায়ী|আলোকে|এর\s*আলোকে))*"
    r"\s*(?:দেখা\s*যা[য়য]|বলা\s*হয়)?[\s:,.।;\-–—]*"
)

_EXPL_CACHE_62: Dict[str, str] = {}


def _strip_expl_noise_62(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    t = raw.replace("\r", "\n")
    t = _re62.sub(r"```(?:json|text)?", "", t, flags=_re62.I)
    t = _re62.sub(r"\s+", " ", t).strip()
    t = _SOURCE_LEAD_RE_62.sub("", t).strip()
    for _ in range(6):
        before = t
        for pat in _EXPL_PREFIX_PATTERNS_62:
            t = pat.sub("", t, count=1).strip()
        t = t.strip(" ।,:;.-–—")
        if t == before:
            break
    if _BAD_EXPL_RE_62.search(t):
        # If a source reference still survived, it is safer to remove the short
        # leading clause than leak it into Telegram/CSV.
        t = _SOURCE_LEAD_RE_62.sub("", t).strip(" ।,:;.-–—")
    return (t or "").strip()


def _is_bad_expl_62(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return True
    if _BAD_EXPL_RE_62.search(t):
        return True
    if len(_strip_expl_noise_62(t)) < 8:
        return True
    return False


def _opts_from_item_62(it: Dict[str, Any]) -> List[str]:
    return [str((it or {}).get(f"option{i}") or "").strip() for i in range(1, 6) if str((it or {}).get(f"option{i}") or "").strip()]


def _repair_explanation_62(it: Dict[str, Any]) -> str:
    try:
        q = str((it or {}).get("questions") or "").strip()
        opts = _opts_from_item_62(it)
        ans = int((it or {}).get("answer", 0) or 0)
        if not q or not (1 <= ans <= len(opts)):
            return ""
        key = _hl62.md5(_json62.dumps({"q": q, "o": opts, "a": ans}, ensure_ascii=False, sort_keys=True).encode("utf-8", "ignore")).hexdigest()
        if key in _EXPL_CACHE_62:
            return _EXPL_CACHE_62[key]
        prompt = (
            "Return STRICT JSON only: {\"explanation\":\"...\"}.\n"
            "Write the real academic reason why the answer is correct. "
            "Do NOT mention option number/letter, সঠিক উত্তর, correct answer, passage, উদ্দীপক, প্রদত্ত পাঠ্য, পাঠ্য পত্র, পাঠ্যবই, পাঠ্যসূচি, or question number. "
            "Do not just repeat the answer text. One sentence, under 160 chars, same language as the question.\n\n"
            f"QUESTION: {q[:700]}\n"
            f"OPTIONS: {_json62.dumps(opts[:5], ensure_ascii=False)}\n"
            f"ANSWER_INDEX: {ans}\nANSWER_TEXT: {opts[ans - 1]}"
        )
        raw = ""
        try:
            if globals().get("GEMINI_API_KEYS"):
                raw = call_gemini_text_rest(prompt, timeout_seconds=12, force_json=True)
        except Exception:
            raw = ""
        if not raw:
            with contextlib.suppress(Exception):
                raw = gemini3_solve(prompt)
        expl = ""
        if raw:
            with contextlib.suppress(Exception):
                data = _extract_json_strict(raw)
                if isinstance(data, dict):
                    expl = str(data.get("explanation") or "").strip()
            if not expl:
                expl = str(raw or "").strip()
        expl = _strip_expl_noise_62(expl)
        if expl and not _BAD_EXPL_RE_62.search(expl):
            if len(expl) > 180:
                expl = expl[:177].rstrip() + "..."
            _EXPL_CACHE_62[key] = expl
            return expl
    except Exception:
        pass
    return ""


def _final_expl_62(text: str, item: Optional[Dict[str, Any]] = None, *, allow_ai: bool = False) -> str:
    cleaned = _strip_expl_noise_62(text)
    if allow_ai and item is not None and _is_bad_expl_62(text):
        repaired = _repair_explanation_62(item)
        if repaired:
            cleaned = repaired
    cleaned = _strip_expl_noise_62(cleaned)
    if len(cleaned) > 180:
        cleaned = cleaned[:177].rstrip() + "..."
    return cleaned


# ─── Make all existing sanitizer/trim call sites use the stronger scrubber ───

_prev_sanitize_quiz_explanation_text_62 = globals().get("_sanitize_quiz_explanation_text")
if callable(_prev_sanitize_quiz_explanation_text_62):
    def _sanitize_quiz_explanation_text(text: str) -> str:  # noqa: F811
        try:
            base = _prev_sanitize_quiz_explanation_text_62(text)
        except Exception:
            base = str(text or "")
        return _final_expl_62(base)

_prev_hard_trim_expl_62 = globals().get("_hard_trim_expl")
if callable(_prev_hard_trim_expl_62):
    def _hard_trim_expl(text: str) -> str:  # noqa: F811
        t = _final_expl_62(text)
        try:
            t = _prev_hard_trim_expl_62(t)
        except Exception:
            pass
        return _final_expl_62(t)

_prev_trim_expl_for_poll_62 = globals().get("_trim_expl_for_poll")
if callable(_prev_trim_expl_for_poll_62):
    def _trim_expl_for_poll(expl: str, link: str = "") -> str:  # noqa: F811
        t = _final_expl_62(expl)
        try:
            out = _prev_trim_expl_for_poll_62(t, link)
        except Exception:
            out = t
        return _final_expl_62(out)


# ─── Strengthen future generation prompts + clean generated/extracted items ───

_prev_make_gen_prompt_62 = globals().get("_make_gen_prompt")
if callable(_prev_make_gen_prompt_62):
    def _make_gen_prompt(source_text: str, count: int) -> str:  # noqa: F811
        return _prev_make_gen_prompt_62(source_text, count) + _EXPL_EXTRA_RULES_62

_prev_generate_mcqs_from_content_62 = globals().get("_generate_mcqs_from_content")
if callable(_prev_generate_mcqs_from_content_62):
    def _generate_mcqs_from_content(content_text: str, *, easy: int, medium: int, hard: int) -> List[Dict[str, Any]]:  # noqa: F811
        items = _prev_generate_mcqs_from_content_62(str(content_text or "") + "\n\n" + _EXPL_EXTRA_RULES_62, easy=easy, medium=medium, hard=hard) or []
        for it in items:
            with contextlib.suppress(Exception):
                it["explanation"] = _final_expl_62(it.get("explanation") or "")
        return items

_prev_extract_mcq_items_master_62 = globals().get("_extract_mcq_items_master")
if callable(_prev_extract_mcq_items_master_62):
    def _extract_mcq_items_master(chunk_text: str) -> List[Dict[str, Any]]:  # noqa: F811
        items = _prev_extract_mcq_items_master_62(chunk_text) or []
        for it in items:
            with contextlib.suppress(Exception):
                it["explanation"] = _final_expl_62(it.get("explanation") or "")
        return items


# ─── Keep future buffer entries clean without changing buffer behaviour ───

_prev_buffer_add_62 = globals().get("buffer_add")
if callable(_prev_buffer_add_62):
    def buffer_add(user_id: int, payload: Dict[str, Any]):  # noqa: F811
        p = dict(payload or {})
        with contextlib.suppress(Exception):
            p["explanation"] = _final_expl_62(p.get("explanation") or "")
        return _prev_buffer_add_62(user_id, p)


# ─── Shared .d-style export builder ─────────────────────────────────────────

def _done_rows_62(items: List[Tuple[int, Dict[str, Any]]], uid: int, *, repair: bool = True) -> List[Dict[str, Any]]:
    explanations_enabled = True
    with contextlib.suppress(Exception):
        explanations_enabled = explain_mode_on(uid) if uid else True
    rows: List[Dict[str, Any]] = []
    for _, raw in items or []:
        it = dict(raw or {})
        q = str(it.get("questions", "") or "")
        e = str(it.get("explanation", "") or "")
        with contextlib.suppress(Exception):
            q2, expl2 = split_inline_explain(q)
            q = q2.strip() or q
            if expl2 and not e.strip():
                e = expl2
        if explanations_enabled:
            e = _final_expl_62(e, it, allow_ai=repair)
        else:
            e = ""
        rows.append({
            "questions": q.strip(),
            "option1": str(it.get("option1", "") or "").strip(),
            "option2": str(it.get("option2", "") or "").strip(),
            "option3": str(it.get("option3", "") or "").strip(),
            "option4": str(it.get("option4", "") or "").strip(),
            "option5": str(it.get("option5", "") or "").strip(),
            "answer": int(it.get("answer", 0) or 0),
            "explanation": e,
            "type": it.get("type", 1),
            "section": it.get("section", 1),
        })
    return rows


def _quiz_json_62(rows: List[Dict[str, Any]], explanations_enabled: bool) -> List[Dict[str, Any]]:
    def _ans_to_letter(n: int) -> str:
        return {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}.get(int(n or 0), "")
    out = []
    for idx, r in enumerate(rows, start=1):
        opts_map = {"A": r.get("option1", ""), "B": r.get("option2", ""), "C": r.get("option3", ""), "D": r.get("option4", "")}
        if str(r.get("option5", "")).strip():
            opts_map["E"] = r.get("option5", "")
        out.append({
            "serial": idx,
            "question": r.get("questions", ""),
            "options": opts_map,
            "correct_answer": _ans_to_letter(r.get("answer", 0)),
            "explanation": r.get("explanation", "") if explanations_enabled else "",
        })
    return out


async def _send_done_export_62(context, chat_id: int, uid: int) -> int:
    items = buffer_list(uid, limit=99999) or []
    if not items:
        return 0
    explanations_enabled = True
    with contextlib.suppress(Exception):
        explanations_enabled = explain_mode_on(uid) if uid else True
    rows = _done_rows_62(items, uid, repair=True)
    cols = ["questions", "option1", "option2", "option3", "option4", "option5", "answer", "explanation", "type", "section"]
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = ""

    with tempfile.NamedTemporaryFile("w+b", suffix=".csv", delete=False) as f:
        csv_path = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as jf:
        json_path = jf.name
    try:
        df[cols].to_csv(csv_path, index=False, encoding="utf-8-sig")
        with open(json_path, "w", encoding="utf-8") as jf:
            _json62.dump(_quiz_json_62(rows, explanations_enabled), jf, ensure_ascii=False, indent=2)
        with open(csv_path, "rb") as rf:
            await context.bot.send_document(
                chat_id=chat_id,
                document=rf,
                filename="probaho_export.csv",
                caption=f"<b>✅ CSV Export</b>\n<i>{len(rows)} questions exported</i>",
                parse_mode=ParseMode.HTML,
            )
        with open(json_path, "rb") as jf2:
            await context.bot.send_document(
                chat_id=chat_id,
                document=jf2,
                filename="probaho_export.json",
                caption="<b>✅ JSON Export</b>",
                parse_mode=ParseMode.HTML,
            )
    finally:
        with contextlib.suppress(Exception):
            os.remove(csv_path)
        with contextlib.suppress(Exception):
            os.remove(json_path)
    return len(rows)


async def _cmd_done_impl_62(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    chat_id = update.effective_chat.id if update.effective_chat else uid
    if not (buffer_list(uid, limit=1) or []):
        await warn(update, "Buffer Empty", "No questions to export. Use /add or send quizzes first.")
        return
    n = await _send_done_export_62(context, chat_id, uid)
    if n <= 0:
        await warn(update, "Buffer Empty", "No questions to export. Use /add or send quizzes first.")
        return
    buffer_clear(uid)
    await ok_html(update, "Export Complete", f"CSV + JSON ready. <code>{h(n)}</code> questions exported.\nBuffer cleared.")


try:
    cmd_done = require_admin(_cmd_done_impl_62)  # noqa: F811
except Exception:
    cmd_done = _cmd_done_impl_62  # noqa: F811


# ─── High-priority CSV button handler: same as .d + delete action card ─────

async def cb_pba_csv_62(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) < 3 or parts[0] != "pba" or parts[1] != "csv":
        return
    token = parts[-1]
    store = _pb_store(context)
    entry = store.get(token)
    if not entry:
        with contextlib.suppress(Exception):
            await q.answer("Expired", show_alert=False)
        raise ApplicationHandlerStop
    uid = int(entry.get("uid") or 0)
    caller = q.from_user.id if q.from_user else 0
    if caller != uid:
        with contextlib.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        raise ApplicationHandlerStop
    chat_id = int(entry.get("chat_id") or (q.message.chat_id if q.message else 0))
    with contextlib.suppress(Exception):
        await q.answer("Exporting…")
    try:
        if not (buffer_list(uid, limit=1) or []):
            with contextlib.suppress(Exception):
                await q.edit_message_text(ui_box_html("Buffer Empty", "Nothing to export.", emoji="📂"), parse_mode=ParseMode.HTML)
            store.pop(token, None)
            raise ApplicationHandlerStop
        n = await _send_done_export_62(context, chat_id, uid)
        buffer_clear(uid)
        store.pop(token, None)
        with contextlib.suppress(Exception):
            await q.message.delete()
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                chat_id=chat_id,
                text=ui_box_html("Export Complete", f"CSV + JSON ready. <code>{n}</code> questions exported.\nBuffer cleared.", emoji="✅"),
                parse_mode=ParseMode.HTML,
            )
    except ApplicationHandlerStop:
        raise
    except Exception as e:
        db_log("ERROR", "pba_csv_failed_v62", {"user_id": uid, "error": str(e)})
        with contextlib.suppress(Exception):
            await q.answer("CSV failed", show_alert=True)
    raise ApplicationHandlerStop


_prev_build_app_62 = build_app

def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_62()
    with contextlib.suppress(Exception):
        app.add_handler(CallbackQueryHandler(cb_pba_csv_62, pattern=r"^pba:csv:[0-9a-f]+$"), group=-1000)
    with contextlib.suppress(Exception):
        if "_register_dual_command" in globals():
            _register_dual_command(app, "done", cmd_done, filters.ChatType.PRIVATE, group=-1000)
            _register_dual_command(app, "d", cmd_done, filters.ChatType.PRIVATE, group=-1000)
    return app

# ===== END SECTION 62 =====