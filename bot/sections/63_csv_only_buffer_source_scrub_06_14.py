# ──────────────────────────────────────────────────────────────────────────────
# Section 63 (2026-06-14) — Surgical overlay for 4 user-reported fixes.
#
# 1) Export is CSV-only (JSON file is no longer sent). Same column format
#    as before: questions, option1..option5, answer, explanation, type, section.
# 2) Source MCQs (from Image/PDF) are auto-added to the user's buffer as soon
#    as the “📌 Source MCQ Actions” card is shown, and an explicit
#    “➕ Add to Buffer” button is also available.
# 3) Explanation scrubber strips extra boilerplate:
#       • “this option is correct because …”
#       • “Option B is correct because …”
#       • “উদ্দীপকে বর্ণিত …”, “টেক্সট অনুযায়ী …”, “তথ্য থেকে …”,
#         “প্রদত্ত টেক্সট অনুযায়ী …”, “পাঠ্য অনুযায়ী …”
#    Only the real academic reason remains.
# 4) “OCR Failed” / “OCR Unavailable” / “Mistral OCR …” messages are no longer
#    shown to normal users — they only see a generic friendly message. The
#    detailed wording (including any mention of “Mistral”) is reserved for
#    the bot owner.
#
# DO NOT import directly — exec'd in shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import re as _re63


# ─────────────────────────────────────────────────────────────────────────────
# 3) Stronger explanation scrub (English + Bengali boilerplate)
# ─────────────────────────────────────────────────────────────────────────────

_EXTRA_PREFIX_PATTERNS_63 = [
    # English: "This option is correct because …", "Option B is correct because …"
    _re63.compile(
        r"^\s*(?:this\s+(?:option|answer|choice)|option\s*[A-Ea-e0-9০-৯]+)\s*"
        r"(?:is|was)?\s*(?:the\s*)?(?:correct|right)\s*(?:answer|option|choice)?\s*"
        r"(?:because|as|since|due\s*to)?[\s:,.।;\-–—]*",
        _re63.I,
    ),
    # English: "Because …" / "Reason: …"
    _re63.compile(r"^\s*(?:because|since|as)\s*[:,\-–—]?\s*", _re63.I),

    # Bengali: "উদ্দীপকে বর্ণিত …", "উদ্দীপকে উল্লিখিত …"
    _re63.compile(
        r"^\s*উদ্দ[ীি]পক(?:ে|টিতে|টিতে)?\s*(?:বর্ণিত|উল্লিখিত|বর্নিত|বলা|দেখানো|প্রদত্ত)?\s*"
        r"(?:তথ্য|অনুচ্ছেদ|বিষয়|অংশ|ঘটনা)?\s*(?:অনুযায়ী|থেকে|হতে|মতে|আলোকে|এর\s*আলোকে)?"
        r"[\s:,.।;\-–—]*"
    ),
    # Bengali: "টেক্সট অনুযায়ী", "প্রদত্ত টেক্সট অনুযায়ী"
    _re63.compile(
        r"^\s*(?:প্রদত্ত\s*)?(?:টেক্সট|পাঠ্য|অনুচ্ছেদ|অধ্যায়|তথ্য|বিষয়|লেখা|নোট|বই)\s*"
        r"(?:অনুযায়ী|থেকে|হতে|মতে|আলোকে|এর\s*আলোকে)[\s:,.।;\-–—]*"
    ),
    # Bengali: "তথ্য থেকে …"
    _re63.compile(
        r"^\s*তথ্য\s*(?:থেকে|হতে|অনুযায়ী|মতে)[\s:,.।;\-–—]*"
    ),
    # Bengali: "উপরোক্ত / উল্লিখিত / প্রদত্ত …"
    _re63.compile(
        r"^\s*(?:উপরোক্ত|উল্লিখিত|প্রদত্ত|উপরে\s*উল্লিখিত)\s*"
        r"(?:তথ্য|অনুচ্ছেদ|টেক্সট|পাঠ্য|বিষয়|অংশ|উদ্দ[ীি]পক)?\s*"
        r"(?:অনুযায়ী|থেকে|হতে|মতে|আলোকে|এর\s*আলোকে)?[\s:,.।;\-–—]*"
    ),
]

_EXTRA_BAD_RE_63 = _re63.compile(
    r"(?i)(this\s+(?:option|answer|choice)\s+is\s+correct|option\s*[A-E0-9]+\s+is\s+correct|"
    r"উদ্দ[ীি]পকে\s*(?:বর্ণিত|উল্লিখিত|বর্নিত)|টেক্সট\s*অনুযায়ী|তথ্য\s*থেকে|"
    r"প্রদত্ত\s*টেক্সট|প্রদত্ত\s*পাঠ্য|পাঠ্য\s*অনুযায়ী)"
)


def _extra_scrub_63(text: str) -> str:
    t = str(text or "").strip()
    if not t:
        return ""
    t = _re63.sub(r"\s+", " ", t).strip()
    # Apply prefix patterns multiple passes (compound prefixes).
    for _ in range(6):
        before = t
        for pat in _EXTRA_PREFIX_PATTERNS_63:
            t = pat.sub("", t, count=1).strip()
        t = t.strip(" ।,:;.-–—\"'“”‘’")
        if t == before:
            break
    # If the bad pattern still appears mid-sentence, drop everything up to it.
    m = _EXTRA_BAD_RE_63.search(t)
    if m:
        t = t[m.end():].lstrip(" ।,:;.-–—\"'“”‘’").strip()
    return t


# Chain on top of _final_expl_62 (from section 62) if available.
_prev_final_expl_63 = globals().get("_final_expl_62")
if callable(_prev_final_expl_63):
    def _final_expl_62(text, item=None, *, allow_ai: bool = False):  # noqa: F811
        out = _prev_final_expl_63(text, item, allow_ai=allow_ai)
        out = _extra_scrub_63(out)
        if len(out) > 180:
            out = out[:177].rstrip() + "..."
        return out

# Also harden the lower-level strippers used by section 62.
_prev_strip_expl_noise_63 = globals().get("_strip_expl_noise_62")
if callable(_prev_strip_expl_noise_63):
    def _strip_expl_noise_62(text: str) -> str:  # noqa: F811
        return _extra_scrub_63(_prev_strip_expl_noise_63(text))

_prev_sanitize_expl_63 = globals().get("_sanitize_quiz_explanation_text")
if callable(_prev_sanitize_expl_63):
    def _sanitize_quiz_explanation_text(text: str) -> str:  # noqa: F811
        return _extra_scrub_63(_prev_sanitize_expl_63(text))


# ─────────────────────────────────────────────────────────────────────────────
# 1) CSV-only export (drop JSON file). Same columns as before.
# ─────────────────────────────────────────────────────────────────────────────

_prev_send_done_export_63 = globals().get("_send_done_export_62")

if callable(_prev_send_done_export_63):
    async def _send_done_export_62(context, chat_id: int, uid: int) -> int:  # noqa: F811
        items = buffer_list(uid, limit=99999) or []
        if not items:
            return 0
        rows = _done_rows_62(items, uid, repair=True)
        cols = ["questions", "option1", "option2", "option3", "option4", "option5",
                "answer", "explanation", "type", "section"]
        df = pd.DataFrame(rows)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        with tempfile.NamedTemporaryFile("w+b", suffix=".csv", delete=False) as f:
            csv_path = f.name
        try:
            df[cols].to_csv(csv_path, index=False, encoding="utf-8-sig")
            with open(csv_path, "rb") as rf:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=rf,
                    filename="probaho_export.csv",
                    caption=f"<b>✅ CSV Export</b>\n<i>{len(rows)} questions exported</i>",
                    parse_mode=ParseMode.HTML,
                )
        finally:
            with contextlib.suppress(Exception):
                os.remove(csv_path)
        return len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# 2) Source MCQ → auto-add to buffer + explicit “Add to Buffer” button.
# ─────────────────────────────────────────────────────────────────────────────

def _auto_buffer_source_items_63(uid: int, items: List[Dict[str, Any]]) -> int:
    """Add source MCQs to the user's buffer, skipping duplicates already buffered."""
    if not uid or not items:
        return 0
    added = 0
    try:
        existing = buffer_list(uid, limit=99999) or []
    except Exception:
        existing = []
    seen_fps: set = set()
    try:
        if "_fp_question" in globals():
            for _, raw in existing:
                with contextlib.suppress(Exception):
                    seen_fps.add(_fp_question(raw))
    except Exception:
        seen_fps = set()
    for it in items or []:
        try:
            if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
                break
            fp = None
            if "_fp_question" in globals():
                with contextlib.suppress(Exception):
                    fp = _fp_question(it)
            if fp is not None and fp in seen_fps:
                continue
            payload = dict(it or {})
            with contextlib.suppress(Exception):
                payload["explanation"] = _final_expl_62(payload.get("explanation") or "")
            if not explain_mode_on(uid):
                payload["explanation"] = ""
            buffer_add(uid, payload)
            if fp is not None:
                seen_fps.add(fp)
            added += 1
        except Exception:
            continue
    return added


_prev_src_action_kb_63 = globals().get("_src_action_kb_59")

if callable(_prev_src_action_kb_63):
    def _src_action_kb_59(token: str, channels):  # noqa: F811
        kb = _prev_src_action_kb_63(token, channels)
        rows = list(kb.inline_keyboard) if kb else []
        # Insert “➕ Add to Buffer” near the top so users notice it.
        rows.insert(0, [InlineKeyboardButton("➕ Add to Buffer", callback_data=f"src59:buf:{token}")])
        return InlineKeyboardMarkup(rows)


_prev_show_source_actions_63 = globals().get("_show_source_actions_59")

if callable(_prev_show_source_actions_63):
    async def _show_source_actions_59(q, context, token: str, entry):  # noqa: F811
        uid = int((entry or {}).get("uid") or 0)
        items = list((entry or {}).get("source_items") or [])
        added = 0
        with contextlib.suppress(Exception):
            added = _auto_buffer_source_items_63(uid, items)
        try:
            db_log("INFO", "source_mcq_auto_buffer_63", {"user_id": uid, "added": added})
        except Exception:
            pass
        await _prev_show_source_actions_63(q, context, token, entry)


# Extra handler for the explicit “➕ Add to Buffer” button.
async def cb_src59_buf_63(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) < 3 or parts[0] != "src59" or parts[1] != "buf":
        return
    token = parts[-1]
    store = _src_store_59(context)
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
    items = list(entry.get("items") or [])
    added = _auto_buffer_source_items_63(uid, items)
    total = 0
    with contextlib.suppress(Exception):
        total = int(buffer_count(uid))
    with contextlib.suppress(Exception):
        await q.answer(f"Added {added} → Buffer")
    with contextlib.suppress(Exception):
        await context.bot.send_message(
            chat_id=int(entry.get("chat_id") or q.message.chat_id),
            text=ui_box_html(
                "Source → Buffer",
                f"Added <code>{added}</code> source MCQ(s).\nBuffered total: <code>{total}</code>",
                emoji="➕",
            ),
            parse_mode=ParseMode.HTML,
        )
    raise ApplicationHandlerStop


# ─────────────────────────────────────────────────────────────────────────────
# 4) Hide OCR failure details from normal users (owner sees full info).
# ─────────────────────────────────────────────────────────────────────────────

_OCR_TITLE_RE_63 = _re63.compile(r"(?i)\b(ocr|mistral)\b")
_OCR_BODY_BLOCK_RE_63 = _re63.compile(r"(?i)\bmistral\b")

_GENERIC_OCR_USER_TITLE_63 = "Couldn't Read Image"
_GENERIC_OCR_USER_BODY_63 = (
    "Sorry, this image couldn't be read right now. "
    "Please try a clearer photo or send it again in a moment."
)


def _is_owner_update_63(update) -> bool:
    try:
        u = getattr(update, "effective_user", None)
        return bool(u and is_owner(int(u.id)))
    except Exception:
        return False


_prev_warn_63 = globals().get("warn")
_prev_err_63 = globals().get("err")

if callable(_prev_warn_63):
    async def warn(update, title: str, body: str):  # noqa: F811
        t = str(title or "")
        b = str(body or "")
        if _OCR_TITLE_RE_63.search(t) or _OCR_BODY_BLOCK_RE_63.search(b):
            if not _is_owner_update_63(update):
                return await _prev_warn_63(update, _GENERIC_OCR_USER_TITLE_63, _GENERIC_OCR_USER_BODY_63)
        return await _prev_warn_63(update, title, body)

if callable(_prev_err_63):
    async def err(update, title: str, body: str):  # noqa: F811
        t = str(title or "")
        b = str(body or "")
        if _OCR_TITLE_RE_63.search(t) or _OCR_BODY_BLOCK_RE_63.search(b):
            if not _is_owner_update_63(update):
                return await _prev_err_63(update, _GENERIC_OCR_USER_TITLE_63, _GENERIC_OCR_USER_BODY_63)
        return await _prev_err_63(update, title, body)


# Also intercept the direct reply path used by section 59's pipeline:
#   source_msg.reply_text(ui_box_html("OCR Failed", …))
# We can't easily hook that, but we can wrap _run_staff_ocr_pipeline to swallow
# the detailed error for non-owners.
_prev_run_staff_ocr_pipeline_63 = globals().get("_run_staff_ocr_pipeline")

if callable(_prev_run_staff_ocr_pipeline_63):
    async def _run_staff_ocr_pipeline(update, context, source_msg, local_path, *, source_label: str = "image"):  # noqa: F811
        uid = 0
        try:
            uid = int(update.effective_user.id) if (update and update.effective_user) else 0
        except Exception:
            uid = 0
        owner_call = False
        with contextlib.suppress(Exception):
            owner_call = bool(uid) and is_owner(uid)

        if not owner_call and source_msg is not None:
            # Intercept reply_text so any "OCR Failed" / "Mistral …" detail
            # never reaches a normal user.
            _orig_reply_text = source_msg.reply_text

            async def _filtered_reply_text(*args, **kwargs):
                try:
                    text = args[0] if args else kwargs.get("text", "")
                except Exception:
                    text = ""
                blob = str(text or "")
                if _re63.search(r"(?i)ocr\s*failed|mistral", blob):
                    safe = ui_box_html(
                        _GENERIC_OCR_USER_TITLE_63,
                        _GENERIC_OCR_USER_BODY_63,
                        emoji="⚠️",
                    )
                    new_kwargs = dict(kwargs)
                    new_kwargs["parse_mode"] = ParseMode.HTML
                    if args:
                        return await _orig_reply_text(safe, **{k: v for k, v in new_kwargs.items() if k != "text"})
                    new_kwargs["text"] = safe
                    return await _orig_reply_text(**new_kwargs)
                return await _orig_reply_text(*args, **kwargs)

            with contextlib.suppress(Exception):
                source_msg.reply_text = _filtered_reply_text  # type: ignore[assignment]

        try:
            return await _prev_run_staff_ocr_pipeline_63(
                update, context, source_msg, local_path, source_label=source_label
            )
        finally:
            if not owner_call and source_msg is not None:
                with contextlib.suppress(Exception):
                    # Restore original bound method if we replaced it.
                    del source_msg.reply_text


# Register the new “➕ Add to Buffer” handler.
_prev_build_app_63 = globals().get("build_app")

if callable(_prev_build_app_63):
    def build_app() -> Application:  # noqa: F811
        app = _prev_build_app_63()
        with contextlib.suppress(Exception):
            app.add_handler(
                CallbackQueryHandler(cb_src59_buf_63, pattern=r"^src59:buf:[0-9a-f]+$"),
                group=-1100,
            )
        return app

# ===== END SECTION 63 =====
