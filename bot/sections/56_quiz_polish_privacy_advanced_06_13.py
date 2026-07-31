# ──────────────────────────────────────────────────────────────────────────────
# Section: 56_quiz_polish_privacy_advanced_06_13
#
# Final polish patch (errorless overrides — no-op on any failure):
#   1) Generation prompt hard-rules to eliminate "উদ্দীপক/তথ্যের আলোকে/নিচের"
#      stimulus-referencing questions and to force OPTION-LENGTH PARITY so the
#      correct option cannot be guessed by visual length / structure.
#   2) Hide Mistral / OCR text preview / .txt file from non-owner users
#      (admins now get only a compact "OCR Done" message). Owners see the
#      full Mistral OCR Complete card + .txt file unchanged.
#   3) Restore ADVANCED first-card after OCR with OCR-checked count +
#      Easy/Medium/Hard generatable estimate + 🔁 More Generate (+5).
#   4) `.gen N` (for owner + admin with full access) now routes the
#      generated MCQs INTO THE BUFFER (not direct channel post) with
#      strict per-source fingerprint de-duplication so repeated `.gen` calls
#      keep producing UNIQUE MCQs, and shows the post/CSV action card.
#
# DO NOT import directly — exec'd in shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────


# =========================================================================
# 1) Anti-stimulus + option-parity rules on the generation prompt
# =========================================================================

_QUIZ_GEN_HARD_RULES = (
    "\n[STRICT GENERATION RULES — must follow]\n"
    "• Do NOT reference any passage / উদ্দীপক / উদ্দীপকের তথ্য / নিম্নের তথ্য / "
    "নিচের উদ্দীপক / 'উপরের আলোকে' / 'উদ্দীপকের আলোকে' / 'নিচের চিত্রের'.\n"
    "• Each MCQ must be SELF-CONTAINED — readable without any external context.\n"
    "• If a fact is too narrow to ask alone, skip it. Never invent a passage.\n"
    "• OPTION PARITY: all 4 options MUST have similar length (±25%), similar\n"
    "  grammatical structure, and similar level of detail. The correct option\n"
    "  must NOT be the longest, most specific, or most technical-looking one.\n"
    "• Distractors must be plausible peers (same units, same category, same\n"
    "  form) so the answer is not visually obvious.\n"
    "• Vary difficulty: prefer MEDIUM + HARD (apply concept / multi-step /\n"
    "  tricky distractors). Avoid trivial recall unless explicitly requested.\n"
    "• Keep the language consistent with the source (Bangla / English / mixed).\n"
    "• Keep explanation under 180 chars, exam-style, no LaTeX wrappers.\n"
)


def _enforce_option_parity(it: Dict[str, Any]) -> Dict[str, Any]:
    """Trim correct option (or pad distractors) so all 4 options have similar
    length. Cannot fix semantic distractor weakness but blocks the most
    common "obvious-by-length" giveaway."""
    try:
        opts = [str(it.get(f"option{i}") or "").strip() for i in range(1, 6)]
        opts = [o for o in opts if o]
        if len(opts) < 2:
            return it
        ans = int(it.get("answer", 0) or 0)
        # Find median (or non-correct) length
        lengths = [len(o) for o in opts]
        if 1 <= ans <= len(opts):
            correct_len = len(opts[ans - 1])
            other_lens = [l for i, l in enumerate(lengths) if i != (ans - 1)]
            if other_lens:
                tgt = int(sorted(other_lens)[len(other_lens) // 2])
                # If the correct option is >40% longer than median other, trim trailing
                # qualifiers (everything after the last ',', '(', ';', '—', '-').
                if correct_len > tgt * 1.4 and tgt >= 4:
                    raw = opts[ans - 1]
                    cut = raw
                    for sep in [" — ", " - ", "; ", ", ", " (", "("]:
                        if sep in raw:
                            cand = raw.split(sep, 1)[0].strip(" .,:;")
                            if len(cand) >= max(3, int(tgt * 0.7)):
                                cut = cand
                                break
                    if cut and cut != raw:
                        opts[ans - 1] = cut
        for i in range(5):
            it[f"option{i+1}"] = opts[i] if i < len(opts) else ""
    except Exception:
        pass
    return it


# Wrap content generator to inject hard rules + parity enforcement
if "_generate_mcqs_from_content" in globals():
    _prev_gen_mcqs_from_content_56 = _generate_mcqs_from_content

    def _generate_mcqs_from_content(content_text: str, *, easy: int, medium: int, hard: int) -> List[Dict[str, Any]]:  # noqa: F811
        seeded = (str(content_text or "") + "\n\n" + _QUIZ_GEN_HARD_RULES).strip()
        items = _prev_gen_mcqs_from_content_56(seeded, easy=easy, medium=medium, hard=hard) or []
        out: List[Dict[str, Any]] = []
        for it in items:
            q = str((it or {}).get("questions") or "").strip()
            if not q:
                continue
            # Skip stimulus-referencing questions outright
            if re.search(r"(উদ্দীপক|উদ্দীপকের|তথ্যের\s*আলোকে|নিম্নের\s*তথ্য|নিচের\s*উদ্দীপক|উপরের\s*আলোকে|নিচের\s*চিত্র|নিম্নলিখিত)", q):
                continue
            out.append(_enforce_option_parity(dict(it)))
        return out


# Wrap the .gen prompt builder (section 35) to add the same hard rules
if "_make_gen_prompt" in globals():
    _prev_make_gen_prompt_56 = _make_gen_prompt

    def _make_gen_prompt(source_text: str, count: int) -> str:  # noqa: F811
        base = _prev_make_gen_prompt_56(source_text, count)
        return base + _QUIZ_GEN_HARD_RULES


# =========================================================================
# 2) ADVANCED first-card after OCR: OCR-checked + E/M/H estimate + more-btn
# =========================================================================

def _genq_kb_advanced(token: str, counts: Dict[str, int]) -> InlineKeyboardMarkup:
    e = int(counts.get("easy", 0))
    m = int(counts.get("medium", 0))
    hd = int(counts.get("hard", 0))
    chk = int(counts.get("ocr_checked", 0))
    total = e + m + hd
    rows: List[List[InlineKeyboardButton]] = []
    if total > 0:
        rows.append([InlineKeyboardButton(f"✅ Generate ALL ({total})", callback_data=f"genq:go:{token}")])
    diff_row: List[InlineKeyboardButton] = []
    if e > 0:
        diff_row.append(InlineKeyboardButton(f"🟢 Easy ({e})", callback_data=f"genq:ge:{token}"))
    if m > 0:
        diff_row.append(InlineKeyboardButton(f"🟡 Medium ({m})", callback_data=f"genq:gm:{token}"))
    if hd > 0:
        diff_row.append(InlineKeyboardButton(f"🔴 Hard ({hd})", callback_data=f"genq:gh:{token}"))
    if diff_row:
        rows.append(diff_row)
    rows.append([InlineKeyboardButton("🔁 More Generate (+5)", callback_data=f"genq:mo:{token}")])
    rows.append([
        InlineKeyboardButton("🔄 Re-estimate", callback_data=f"genq:re:{token}"),
        InlineKeyboardButton("🚫 Skip", callback_data=f"genq:no:{token}"),
    ])
    return InlineKeyboardMarkup(rows)


# Override _genq_kb to ALWAYS include the More Generate button
def _genq_kb(token: str, counts: Dict[str, int]) -> InlineKeyboardMarkup:  # noqa: F811
    return _genq_kb_advanced(token, counts)


# Replace OCR-completion action card to also include E/M/H estimate
if "_run_staff_ocr_pipeline" in globals():
    _prev_run_staff_ocr_pipeline_56 = _run_staff_ocr_pipeline

    async def _run_staff_ocr_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE, source_msg, local_path: str, *, source_label: str = "image") -> Dict[str, Any]:  # noqa: F811
        uid = int(update.effective_user.id if update and update.effective_user else 0)
        chat_id = int(getattr(source_msg, "chat_id", 0) or 0)
        before = 0
        with contextlib.suppress(Exception):
            before = int(buffer_count(uid))
        ctx_payload = await _prev_run_staff_ocr_pipeline_56(update, context, source_msg, local_path, source_label=source_label)
        try:
            after = int(buffer_count(uid))
            added = max(0, after - before)
            if uid <= 0 or not chat_id:
                return ctx_payload
            text = str((ctx_payload or {}).get("clean_text") or (ctx_payload or {}).get("raw_markdown") or "")
            if not text.strip():
                return ctx_payload
            # Estimate generatable counts (best-effort)
            try:
                est = await _run_blocking(_role_of(uid), _estimate_generatable_counts, text, timeout=30) or {}
            except Exception:
                est = {}
            counts = {
                "easy": int(est.get("easy", 0) or 0),
                "medium": int(est.get("medium", 0) or 0),
                "hard": int(est.get("hard", 0) or 0),
                "ocr_checked": int(added or 0),
            }
            token = uuid.uuid4().hex[:10]
            seen_fp: set = set()
            try:
                seen_fp = set(_fp_question(it) for _, it in (buffer_list(uid, limit=99999) or []))
            except Exception:
                seen_fp = set()
            _genq_store(context)[token] = {
                "uid": uid, "chat_id": chat_id, "page": 1, "text": text,
                "counts": counts, "seen_fp": seen_fp, "more_added": 0, "ts": time.time(),
            }
            total = counts["easy"] + counts["medium"] + counts["hard"]
            body = (
                f"📄 OCR Page Ready\n\n"
                f"  • OCR Checked MCQ: <code>{counts['ocr_checked']}</code> (added to buffer)\n"
                f"  • Easy generatable: <code>{counts['easy']}</code>\n"
                f"  • Medium generatable: <code>{counts['medium']}</code>\n"
                f"  • Hard generatable: <code>{counts['hard']}</code>\n"
                f"  • Total generatable: <code>{total}</code>\n\n"
                "Pick a difficulty, generate all, or tap 🔁 More Generate to keep adding NEW unique MCQs."
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=ui_box_html("Quiz Generation Options", body, emoji="🧠"),
                parse_mode=ParseMode.HTML,
                reply_markup=_genq_kb_advanced(token, counts),
                disable_web_page_preview=True,
            )
            if added > 0:
                with contextlib.suppress(Exception):
                    await _send_pb_action_card(context, chat_id, uid, added)
        except Exception as e:
            db_log("WARN", "advanced_ocr_card_v56_failed", {"error": str(e)})
        return ctx_payload


# =========================================================================
# 3) Privacy: hide Mistral / OCR text preview / .txt file for non-owners
#    Admins now get ONLY a compact "OCR Done" message (no model name,
#    no text preview, no file). Owners get the full Mistral OCR Complete card.
# =========================================================================

_ORIG_REPLY_TEXT_56 = None
_ORIG_REPLY_DOCUMENT_56 = None


def _is_full_access(uid: int) -> bool:
    try:
        return bool(is_owner(int(uid or 0)))
    except Exception:
        return False


if "_run_staff_ocr_pipeline" in globals():
    _prev_run_staff_ocr_pipeline_56b = _run_staff_ocr_pipeline

    async def _run_staff_ocr_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE, source_msg, local_path: str, *, source_label: str = "image") -> Dict[str, Any]:  # noqa: F811
        uid = int(update.effective_user.id if update and update.effective_user else 0)
        full = _is_full_access(uid)
        if full:
            return await _prev_run_staff_ocr_pipeline_56b(update, context, source_msg, local_path, source_label=source_label)

        # Monkey-patch the source_msg's reply_text / reply_document so the
        # legacy "Mistral OCR Complete" preview card + .txt document are
        # suppressed for non-owners. Buffer + action card still works because
        # those go through context.bot.send_message, not source_msg.reply_*.
        orig_reply_text = getattr(source_msg, "reply_text", None)
        orig_reply_document = getattr(source_msg, "reply_document", None)

        async def _muted_reply_text(text: str = "", *args, **kwargs):
            t = str(text or "")
            # Block any message that exposes Mistral / OCR raw preview
            if ("Mistral" in t) or ("mistral-ocr" in t) or ("OCR model" in t) or ("OCR Text Extracted" in t):
                return None
            if orig_reply_text:
                return await orig_reply_text(text, *args, **kwargs)
            return None

        async def _muted_reply_document(*args, **kwargs):
            # Suppress the raw OCR .txt dump entirely for non-owners
            return None

        with contextlib.suppress(Exception):
            source_msg.reply_text = _muted_reply_text  # type: ignore[attr-defined]
        with contextlib.suppress(Exception):
            source_msg.reply_document = _muted_reply_document  # type: ignore[attr-defined]

        try:
            ctx_payload = await _prev_run_staff_ocr_pipeline_56b(update, context, source_msg, local_path, source_label=source_label)
        finally:
            with contextlib.suppress(Exception):
                if orig_reply_text is not None:
                    source_msg.reply_text = orig_reply_text  # type: ignore[attr-defined]
                if orig_reply_document is not None:
                    source_msg.reply_document = orig_reply_document  # type: ignore[attr-defined]

        # Send the compact privacy-safe message instead
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                chat_id=source_msg.chat_id,
                text=ui_box_html(
                    "OCR Done",
                    "Text extracted successfully.\nQuiz generation options are below.",
                    emoji="✅",
                ),
                parse_mode=ParseMode.HTML,
            )
        return ctx_payload


# =========================================================================
# 4) .gen N for owner+admin → BUFFER instead of direct post; unique each call
# =========================================================================

_GEN_BUFFER_STATE_KEY = "_gen_buffer_state_56"


def _gen_state(context) -> Dict[str, Any]:
    bd = context.application.bot_data
    if _GEN_BUFFER_STATE_KEY not in bd:
        bd[_GEN_BUFFER_STATE_KEY] = {}
    return bd[_GEN_BUFFER_STATE_KEY]


def _gen_seen_for(context, uid: int, source_hash: str) -> set:
    st = _gen_state(context)
    key = f"{uid}:{source_hash}"
    s = st.get(key)
    if not isinstance(s, set):
        s = set()
        st[key] = s
    # Seed from current buffer fingerprints (best-effort)
    try:
        for _, it in (buffer_list(uid, limit=99999) or []):
            with contextlib.suppress(Exception):
                s.add(_fp_question(it))
    except Exception:
        pass
    return s


if "cmd_gen" in globals():
    _prev_cmd_gen_56 = cmd_gen

    async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
        ensure_user(update)
        if not update.message or not update.effective_user:
            return
        uid = int(update.effective_user.id)
        is_staff = False
        with contextlib.suppress(Exception):
            is_staff = bool(is_owner(uid) or is_admin(uid))
        if not is_staff:
            # Non-staff: keep original direct-post behaviour
            return await _prev_cmd_gen_56(update, context)

        # Need OCR context from replied message
        reply_msg = update.message.reply_to_message
        if not reply_msg:
            await safe_reply(update, usage_box("gen", "[count]", "Reply to an OCR'd image/page and run .gen <count>."))
            return
        ocr_ctx = None
        with contextlib.suppress(Exception):
            if "_has_ocr_context" in globals() and _has_ocr_context(context, reply_msg):
                ocr_ctx = _get_ocr_context(context, reply_msg.message_id)
        if not ocr_ctx:
            # Fall through to legacy path so it does OCR if needed,
            # but we still want buffer routing — wrap _send_poll_with_retry.
            pass

        requested = _parse_gen_count(update.message.text or "", list(context.args or []))
        requested = max(1, min(500, requested))

        # Redirect generated polls to the buffer instead of sending them.
        added_holder = {"n": 0, "skipped_dup": 0}
        orig_send_poll = globals().get("_send_poll_with_retry")
        seen: set = set()

        async def _buffer_capture(_bot, *, chat_id, question, options, is_anonymous=True,
                                   type=None, correct_option_id=0, explanation=None, **kwargs):
            try:
                q = str(question or "").strip()
                # Strip prefixed "প্রবাহ\n\u200b" header so buffer holds clean text
                q = re.sub(r"^প্রবাহ\s*\n\u200b?", "", q).strip()
                opts = [str(o or "").strip() for o in (options or []) if str(o or "").strip()]
                ans = int(correct_option_id or 0) + 1
                if not q or len(opts) < 2 or not (1 <= ans <= len(opts)):
                    return
                payload = {
                    "questions": q,
                    "option1": opts[0] if len(opts) > 0 else "",
                    "option2": opts[1] if len(opts) > 1 else "",
                    "option3": opts[2] if len(opts) > 2 else "",
                    "option4": opts[3] if len(opts) > 3 else "",
                    "option5": opts[4] if len(opts) > 4 else "",
                    "answer": ans,
                    "explanation": str(explanation or "")[:200],
                    "type": 1, "section": 1,
                }
                payload = _enforce_option_parity(payload)
                fp = _fp_question(payload)
                if fp in seen:
                    added_holder["skipped_dup"] += 1
                    return
                if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
                    return
                buffer_add(uid, payload)
                seen.add(fp)
                added_holder["n"] += 1
            except Exception:
                pass

        # Seed seen with current buffer + per-source seen-set so repeated .gen
        # calls do not produce duplicates.
        with contextlib.suppress(Exception):
            if ocr_ctx:
                sh = _ocr_source_hash(ocr_ctx)
                seen.update(_gen_seen_for(context, uid, sh))
        with contextlib.suppress(Exception):
            for _, it in (buffer_list(uid, limit=99999) or []):
                seen.add(_fp_question(it))

        if orig_send_poll:
            globals()["_send_poll_with_retry"] = _buffer_capture
        try:
            await _prev_cmd_gen_56(update, context)
        finally:
            if orig_send_poll:
                globals()["_send_poll_with_retry"] = orig_send_poll

        # Persist seen for this source
        with contextlib.suppress(Exception):
            if ocr_ctx:
                _gen_seen_for(context, uid, _ocr_source_hash(ocr_ctx)).update(seen)

        added = int(added_holder["n"])
        dup = int(added_holder["skipped_dup"])
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=ui_box_html(
                    "Generated → Buffer",
                    f"Added <code>{added}</code> unique MCQ(s) to your buffer.\n"
                    f"Duplicates skipped: <code>{dup}</code>\n"
                    f"Buffered total: <code>{buffer_count(uid)}</code>\n\n"
                    "Use the action card below to 📤 Post to Channel or 📂 Export CSV.",
                    emoji="✅",
                ),
                parse_mode=ParseMode.HTML,
            )
        with contextlib.suppress(Exception):
            await _send_pb_action_card(context, update.message.chat_id, uid, added)


# Re-register cmd_gen so .gen and /gen pick up the new behaviour after restart
if "build_app" in globals():
    _prev_build_app_56 = build_app

    def build_app() -> Application:  # noqa: F811
        app = _prev_build_app_56()
        with contextlib.suppress(Exception):
            if "_register_dual_command" in globals():
                _register_dual_command(app, "gen", cmd_gen, group=-100)
        return app

# ===== END POLISH + PRIVACY + ADVANCED CARD =====