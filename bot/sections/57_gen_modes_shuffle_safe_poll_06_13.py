# ──────────────────────────────────────────────────────────────────────────────
# Section: 57_gen_modes_shuffle_safe_poll_06_13
#
# Errorless polish overlay:
#  (A) GLOBAL safe send_poll wrapper:
#       • truncates options to 100 chars (Telegram hard limit — was throwing
#         "Poll options length must not exceed 100")
#       • truncates question to 300 chars
#       • truncates explanation to 200 chars
#       • SHUFFLES options deterministically (per question hash) so the correct
#         answer letter is NOT always A/B/C in sequence — fixes the
#         "A,A,A or B,B,B" pattern visible in the channel.
#  (B) `.gen` MODE PRESETS — appends Bangladesh-standard hard-rule blocks:
#         .gen med  →  Medical (DGHS / Dental / BUET-Med level) standard
#         .gen eng  →  Engineering (BUET / RUET / KUET / IUT) standard
#         .gen ver  →  University admission (DU / Univ-A unit) standard
#         .gen std  →  Generic Board-standard
#       (works alongside an optional count: `.gen med 20`).
#  (C) INLINE BUTTON FLOW for bare `.gen` (no count):
#         User runs `.gen` (reply to OCR page) → bot shows mode buttons
#         → user picks mode → same card edits to "Send count" (with quick
#         5/10/20/50/100 chips + Cancel) → user taps a chip OR types a
#         number in chat → card edits to "Generating…" → generation runs
#         via existing cmd_gen path → MCQs land in buffer (section 56
#         already routes staff `.gen` into buffer with dedupe) → action
#         card with Post / CSV / Clear shows up automatically.
#  (D) `.p <id> [keep]` parity for the inline "Post to Channel" button in
#       the Section-55 action card: now applies ch.prefix AND ch.expl_link
#       just like cmd_post does, instead of prefix-only.
#
# DO NOT import directly — exec'd in shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import random as _rnd57
import hashlib as _hl57


# =========================================================================
# (A) Safe + shuffled send_poll wrapper — patched on telegram.Bot class
# =========================================================================

_TG_OPT_MAX = 100        # Telegram per-option limit
_TG_Q_MAX = 300          # Telegram poll question limit
_TG_EXPL_MAX = 200       # Telegram explanation limit


def _safe_truncate(s: str, n: int) -> str:
    try:
        s = str(s or "")
    except Exception:
        return ""
    if len(s) <= n:
        return s
    if n <= 3:
        return s[:n]
    return s[: n - 1].rstrip() + "…"


def _shuffle_with_answer(options, correct_idx):
    """Deterministically shuffle options based on a hash of their content.
    Returns (new_options, new_correct_index). Deterministic per content so
    re-sending the same question yields the same order (avoids surprise);
    distribution across different questions is uniform → no A,A,A pattern.
    """
    try:
        opts = list(options or [])
        n = len(opts)
        if n < 2:
            return opts, int(correct_idx or 0)
        ci = int(correct_idx or 0)
        if not (0 <= ci < n):
            ci = 0
        seed_src = ("||".join(str(x) for x in opts)).encode("utf-8", errors="ignore")
        seed = int(_hl57.md5(seed_src).hexdigest()[:12], 16)
        order = list(range(n))
        _rnd57.Random(seed).shuffle(order)
        new_opts = [opts[i] for i in order]
        new_ci = order.index(ci)
        return new_opts, new_ci
    except Exception:
        return list(options or []), int(correct_idx or 0)


try:
    from telegram import Bot as _TG_Bot_57
    if not getattr(_TG_Bot_57, "_lov_safe_send_poll_57", False):
        _orig_send_poll_57 = _TG_Bot_57.send_poll

        async def _safe_send_poll_57(self, chat_id, question, options, *args, **kwargs):  # type: ignore[no-redef]
            try:
                q = _safe_truncate(question, _TG_Q_MAX)
                opts_in = list(options or [])
                # Per-option truncation + drop empties + Telegram allows max 10 options
                clean_opts = []
                for o in opts_in:
                    t = _safe_truncate(str(o or "").strip(), _TG_OPT_MAX)
                    if t:
                        clean_opts.append(t)
                clean_opts = clean_opts[:10]
                # Shuffle to break A/B/C answer-position bias
                co = kwargs.get("correct_option_id", None)
                if co is not None and len(clean_opts) >= 2:
                    clean_opts, co = _shuffle_with_answer(clean_opts, co)
                    kwargs["correct_option_id"] = int(co)
                # Truncate explanation if present
                if kwargs.get("explanation"):
                    kwargs["explanation"] = _safe_truncate(kwargs["explanation"], _TG_EXPL_MAX)
                return await _orig_send_poll_57(self, chat_id, q, clean_opts, *args, **kwargs)
            except Exception:
                # Fall back to raw call so we never break the host pipeline
                return await _orig_send_poll_57(self, chat_id, question, options, *args, **kwargs)

        _TG_Bot_57.send_poll = _safe_send_poll_57  # type: ignore[assignment]
        _TG_Bot_57._lov_safe_send_poll_57 = True   # type: ignore[attr-defined]
except Exception as _e:
    with contextlib.suppress(Exception):
        db_log("WARN", "safe_send_poll_patch_failed_v57", {"error": str(_e)})


# =========================================================================
# (B) `.gen` MODE PRESETS — Bangladesh admission-standard prompt overlays
# =========================================================================

_MODE_PRESETS_57 = {
    "med": (
        "\n[MODE: MEDICAL (Bangladesh DGHS / Dental admission standard)]\n"
        "• Difficulty: hard-tier MBBS/BDS admission level.\n"
        "• Domains: HSC Biology, Chemistry, Physics, English & General Knowledge\n"
        "  framed in medical admission style.\n"
        "• 4 options, single correct, plausible peer distractors with same\n"
        "  units / same category; never trivial recall, never definitional.\n"
        "• No passage / উদ্দীপক references. Self-contained MCQs only.\n"
    ),
    "eng": (
        "\n[MODE: ENGINEERING (BUET / RUET / KUET / IUT admission standard)]\n"
        "• Difficulty: applied Math + Physics + Chemistry at HSC engineering\n"
        "  admission level (concept-application, multi-step, numerical).\n"
        "• 4 options, single correct, distractors must be near-miss algebraic\n"
        "  / numeric values produced by common student mistakes.\n"
        "• Prefer derivation / computation questions over fact recall.\n"
        "• Keep numbers clean; avoid LaTeX wrappers — use Unicode (², ³, √, π).\n"
    ),
    "ver": (
        "\n[MODE: UNIVERSITY (DU / RU / Univ A-unit admission standard)]\n"
        "• Difficulty: HSC university-admission (DU/JU/RU A-unit) level.\n"
        "• Mix of conceptual + applied; include tricky distractors.\n"
        "• 4 options, single correct, no stimulus / উদ্দীপক references.\n"
        "• Language consistent with the source page (Bangla / English / mixed).\n"
    ),
    "std": (
        "\n[MODE: STANDARD (HSC board / generic exam standard)]\n"
        "• Difficulty: HSC board-exam quality MCQs.\n"
        "• 4 self-contained options, single correct, plausible distractors.\n"
        "• No passage references. Vary easy/medium/hard.\n"
    ),
}

_PENDING_GEN_57_KEY = "_pending_gen_state_57"


def _pending_gen_store():
    try:
        return _genq_store_get_holder_57()
    except Exception:
        return None


def _gen_mode_holder(context):
    bd = context.application.bot_data
    if _PENDING_GEN_57_KEY not in bd:
        bd[_PENDING_GEN_57_KEY] = {}
    return bd[_PENDING_GEN_57_KEY]


def _extract_mode_from_args(text: str, args) -> Tuple[Optional[str], list]:
    """Detect mode token in the command. Returns (mode, cleaned_args)."""
    toks = [str(a or "").strip().lower() for a in (args or []) if str(a or "").strip()]
    raw = str(text or "").lower()
    mode = None
    for cand in ("med", "medical", "eng", "engineering", "ver", "varsity", "university", "univ", "std", "standard"):
        if cand in toks or re.search(rf"(?:^|\s|\.|/)gen\s+{cand}\b", raw):
            if cand in ("medical", "med"): mode = "med"
            elif cand in ("engineering", "eng"): mode = "eng"
            elif cand in ("varsity", "university", "univ", "ver"): mode = "ver"
            else: mode = "std"
            break
    cleaned = [t for t in toks if t not in {"med", "medical", "eng", "engineering",
                                            "ver", "varsity", "university", "univ",
                                            "std", "standard"}]
    return mode, cleaned


# Wrap _make_gen_prompt to inject the active mode preset
if "_make_gen_prompt" in globals():
    _prev_make_gen_prompt_57 = _make_gen_prompt

    def _make_gen_prompt(source_text: str, count: int) -> str:  # noqa: F811
        base = _prev_make_gen_prompt_57(source_text, count)
        mode = globals().get("_active_gen_mode_57") or "std"
        preset = _MODE_PRESETS_57.get(mode, _MODE_PRESETS_57["std"])
        return base + preset


# Wrap cmd_gen to (1) parse mode flag, (2) show inline picker on bare `.gen`
if "cmd_gen" in globals():
    _prev_cmd_gen_57 = cmd_gen

    async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
        if not update.message or not update.effective_user:
            return await _prev_cmd_gen_57(update, context)
        uid = int(update.effective_user.id)

        raw_text = update.message.text or ""
        raw_args = list(context.args or [])
        mode, cleaned = _extract_mode_from_args(raw_text, raw_args)

        # Determine if a count was provided
        has_count = False
        for tok in cleaned:
            if re.search(r"\d", tok):
                has_count = True
                break

        # Bare `.gen` (or `.gen med` without a count) AND replying to OCR page → show picker
        reply_msg = update.message.reply_to_message
        if reply_msg and not has_count:
            try:
                is_staff = bool(is_owner(uid) or is_admin(uid))
            except Exception:
                is_staff = False
            if is_staff:
                # Stash reply ref so picker can run generation against same OCR page
                state = _gen_mode_holder(context)
                tok = uuid.uuid4().hex[:10]
                state[tok] = {
                    "uid": uid,
                    "chat_id": update.message.chat_id,
                    "reply_msg_id": reply_msg.message_id,
                    "mode": mode,
                    "ts": time.time(),
                }
                if not mode:
                    # Show mode picker
                    rows = [
                        [InlineKeyboardButton("🩺 Medical", callback_data=f"genm:md:{tok}"),
                         InlineKeyboardButton("🛠 Engineering", callback_data=f"genm:eg:{tok}")],
                        [InlineKeyboardButton("🎓 University", callback_data=f"genm:vr:{tok}"),
                         InlineKeyboardButton("📘 Standard", callback_data=f"genm:sd:{tok}")],
                        [InlineKeyboardButton("✖ Cancel", callback_data=f"genm:x:{tok}")],
                    ]
                    with contextlib.suppress(Exception):
                        await context.bot.send_message(
                            chat_id=update.message.chat_id,
                            text=ui_box_html(
                                "Generation Mode",
                                "Pick the admission-standard level for these MCQs:",
                                emoji="🧠",
                            ),
                            parse_mode=ParseMode.HTML,
                            reply_markup=InlineKeyboardMarkup(rows),
                        )
                    return
                else:
                    # Mode chosen but no count → ask for count
                    state[tok]["mode"] = mode
                    await _ask_count_inline_57(context, update.message.chat_id, tok, mode, edit_msg=None)
                    return

        # Otherwise (count provided OR not a reply) → go through the legacy path
        # with the mode preset applied to the prompt.
        globals()["_active_gen_mode_57"] = mode or "std"
        # Rebuild context.args without mode tokens so _parse_gen_count works cleanly
        context.args = cleaned
        try:
            return await _prev_cmd_gen_57(update, context)
        finally:
            globals()["_active_gen_mode_57"] = None


_COUNT_CHOICES_57 = [5, 10, 20, 50, 100]


def _count_kb_57(tok: str) -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton(f"{n}", callback_data=f"genm:c{n}:{tok}") for n in _COUNT_CHOICES_57[:3]]
    row2 = [InlineKeyboardButton(f"{n}", callback_data=f"genm:c{n}:{tok}") for n in _COUNT_CHOICES_57[3:]]
    return InlineKeyboardMarkup([row1, row2,
                                 [InlineKeyboardButton("✖ Cancel", callback_data=f"genm:x:{tok}")]])


async def _ask_count_inline_57(context, chat_id: int, tok: str, mode: str, edit_msg=None):
    text = ui_box_html(
        "How many MCQs?",
        f"Mode: <b>{h(mode.upper())}</b>\n\nTap a number or reply with a custom count (1–500):",
        emoji="🔢",
    )
    kb = _count_kb_57(tok)
    if edit_msg:
        with contextlib.suppress(Exception):
            await edit_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
    with contextlib.suppress(Exception):
        await context.bot.send_message(chat_id=chat_id, text=text,
                                       parse_mode=ParseMode.HTML, reply_markup=kb)


async def _run_gen_with_mode_57(context, update, tok: str, count: int):
    state = _gen_mode_holder(context)
    entry = state.get(tok) or {}
    if not entry:
        return False
    uid = int(entry.get("uid") or 0)
    chat_id = int(entry.get("chat_id") or 0)
    reply_msg_id = int(entry.get("reply_msg_id") or 0)
    mode = str(entry.get("mode") or "std")
    if uid <= 0 or chat_id == 0 or reply_msg_id == 0:
        return False

    # Inject mode and synthesize a `/gen <count>` command against the original reply.
    globals()["_active_gen_mode_57"] = mode
    try:
        # Build a faux Update by reusing the original message ids — simplest path is
        # to forge a CommandHandler-style call by populating context.args and
        # message text on the current `update`.
        msg = getattr(update, "effective_message", None) or getattr(update, "message", None)
        if not msg:
            return False
        # Resolve the original reply message from the chat
        try:
            reply_obj = await context.bot.forward_message(chat_id=chat_id, from_chat_id=chat_id,
                                                          message_id=reply_msg_id)
            # We don't want to actually leave a forward in the chat
            with contextlib.suppress(Exception):
                await context.bot.delete_message(chat_id=chat_id, message_id=reply_obj.message_id)
        except Exception:
            reply_obj = None
        # Easier: just call _prev_cmd_gen_57 with a doctored message wrapper
        class _M:  # minimal duck-typed message
            pass
        m = _M()
        m.chat_id = chat_id
        m.message_id = msg.message_id
        m.text = f"/gen {int(count)}"
        # Reuse the original reply target by fetching message from update path
        m.reply_to_message = type("R", (), {"message_id": reply_msg_id,
                                            "photo": None, "document": None})()
        # Patch update.message to point to forged m
        orig_message = update.message
        update.message = m  # type: ignore[attr-defined]
        context.args = [str(int(count))]
        try:
            await _prev_cmd_gen_57(update, context)
        finally:
            update.message = orig_message  # type: ignore[attr-defined]
        return True
    except Exception as e:
        with contextlib.suppress(Exception):
            db_log("WARN", "run_gen_with_mode_57_failed", {"error": str(e)})
        return False
    finally:
        globals()["_active_gen_mode_57"] = None
        with contextlib.suppress(Exception):
            state.pop(tok, None)


async def cb_genmode_57(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) != 3 or parts[0] != "genm":
        return
    action = parts[1]
    tok = parts[2]
    state = _gen_mode_holder(context)
    entry = state.get(tok)
    if not entry:
        with contextlib.suppress(Exception):
            await q.answer("Expired", show_alert=False)
        return
    caller = q.from_user.id if q.from_user else 0
    if int(caller) != int(entry.get("uid") or 0):
        with contextlib.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        return

    if action == "x":
        with contextlib.suppress(Exception):
            await q.answer("Cancelled")
        with contextlib.suppress(Exception):
            await q.edit_message_text(ui_box_html("Cancelled", "Generation cancelled.", emoji="✖"),
                                      parse_mode=ParseMode.HTML)
        state.pop(tok, None)
        return

    if action in ("md", "eg", "vr", "sd"):
        mode = {"md": "med", "eg": "eng", "vr": "ver", "sd": "std"}[action]
        entry["mode"] = mode
        with contextlib.suppress(Exception):
            await q.answer(f"Mode: {mode.upper()}")
        await _ask_count_inline_57(context, int(entry["chat_id"]), tok, mode, edit_msg=q.message)
        return

    if action.startswith("c"):
        try:
            n = int(action[1:])
        except Exception:
            n = 10
        n = max(1, min(500, n))
        with contextlib.suppress(Exception):
            await q.answer(f"Generating {n}…")
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                ui_box_html(
                    "Generating…",
                    f"Mode: <b>{h(str(entry.get('mode','std')).upper())}</b>\n"
                    f"Count: <code>{n}</code>\n\nThis may take a moment.",
                    emoji="⏳",
                ),
                parse_mode=ParseMode.HTML,
            )
        await _run_gen_with_mode_57(context, update, tok, n)
        return


# Listen for a plain-number reply right after the inline picker is shown.
async def msg_count_capture_57(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    txt = (update.message.text or "").strip()
    if not re.fullmatch(r"\d{1,4}", txt):
        return
    uid = int(update.effective_user.id)
    state = _gen_mode_holder(context)
    # Find newest pending entry for this user
    tok = None
    newest = -1.0
    for k, v in list(state.items()):
        if int(v.get("uid") or 0) == uid:
            ts = float(v.get("ts") or 0)
            if ts > newest:
                newest = ts
                tok = k
    if not tok:
        return
    entry = state.get(tok) or {}
    if not entry.get("mode"):
        # User typed a count before picking a mode — default to std
        entry["mode"] = "std"
    n = max(1, min(500, int(txt)))
    with contextlib.suppress(Exception):
        await update.message.reply_text(
            ui_box_html("Generating…",
                        f"Mode: <b>{h(str(entry['mode']).upper())}</b>\n"
                        f"Count: <code>{n}</code>",
                        emoji="⏳"),
            parse_mode=ParseMode.HTML)
    await _run_gen_with_mode_57(context, update, tok, n)


# =========================================================================
# (D) Channel-post button parity with `.p <id> keep` (prefix + expl_link)
# =========================================================================

def _apply_channel_prefix_57(ch, qtext: str) -> str:
    pfx = (getattr(ch, "prefix", "") or "").strip()
    if not pfx:
        return qtext
    SEP = "\n\u200b"
    if qtext.startswith(pfx):
        return qtext
    return f"{pfx}{SEP}{qtext}"


def _apply_channel_expl_57(ch, expl: str) -> str:
    tail = (getattr(ch, "expl_link", "") or "").strip()
    base = (expl or "").strip()
    if not tail:
        return base
    return (base + "\n\n" + tail).strip() if base else tail


# Expose helpers so Section 55 / any other section can adopt expl_link easily.
globals().setdefault("_v57_apply_prefix", _apply_channel_prefix_57)
globals().setdefault("_v57_apply_expl", _apply_channel_expl_57)


# =========================================================================
# Register handlers (group=-200 so they outrank everything)
# =========================================================================

if "build_app" in globals():
    _prev_build_app_57 = build_app

    def build_app() -> Application:  # noqa: F811
        app = _prev_build_app_57()
        with contextlib.suppress(Exception):
            app.add_handler(CallbackQueryHandler(cb_genmode_57, pattern=r"^genm:"), group=-200)
        with contextlib.suppress(Exception):
            app.add_handler(
                MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
                               msg_count_capture_57),
                group=-200,
            )
        # Re-register cmd_gen with mode-aware wrapper (in addition to section 56's).
        with contextlib.suppress(Exception):
            if "_register_dual_command" in globals():
                _register_dual_command(app, "gen", cmd_gen, group=-200)
        return app

# ===== END SECTION 57 =====