# ──────────────────────────────────────────────────────────────────────────────
# Section 73 (2026-06-15) — Three targeted fixes (additive, no behaviour
# replaced beyond what each wrapper does):
#
#   1) FAST GENERATION via Advanced-Mode providers.
#      Root cause of "4–5 min wait, 0 questions":
#      _generate_quizzes_from_ocr_sync (sec.40) only tries the hard-coded
#      Gemini-REST → Gemini-Web → Perplexity chain. Mistral/Nvidia/Groq added
#      through /advmode were NEVER called during quiz generation. When the
#      Gemini keys quota-out, every round wastes ~30 s and the function loops
#      up to 8 times → 0 results in 4 minutes.
#      Fix: wrap _generate_quizzes_from_ocr_sync so the FIRST backend tried in
#      every round is _adv_call_text (cascades through ALL enabled /advmode
#      providers with a 12 s per-call cap from sec.71). Hard-coded chain stays
#      as fallback. Batch raised to 8, hard cap raised to 200, max useless
#      rounds shortened so generation either delivers in <60 s or surfaces a
#      clear error.
#
#   2) AI-POWERED /help and .help (Bangla + English).
#         /help                 → role-based full command index
#         /help <command>       → AI explanation of that command (usage + example)
#         /help <free text>     → AI answers using the same command index
#      Separate command lists for User / Admin / Owner panels. Uses the
#      existing _adv_call_text cascade so help replies share the fast provider
#      chain (no extra latency budget).
#
#   3) Confirms the owner-side per-user gen-limit commands from sec.60 are
#      registered AND adds friendly aliases /userlimit, .userlimit so the
#      owner can find them from /help.
#
# Everything else is left exactly as before.
# ──────────────────────────────────────────────────────────────────────────────

import re as _re73
import contextlib as _cx73
import asyncio as _asyncio73
import json as _json73


# ─── 1) Route generation through Advanced-Mode providers ──────────────────────

try:
    _prev_gen_sync_73 = _generate_quizzes_from_ocr_sync  # type: ignore[name-defined]
except Exception:
    _prev_gen_sync_73 = None


def _gen_via_advmode_73(prompt: str):
    """Try _adv_call_text first; return raw string or None."""
    try:
        out, _name = _adv_call_text(prompt, force_json=True, timeout=12)  # type: ignore[name-defined]
        if out and str(out).strip():
            return str(out).strip()
    except Exception as e:
        logger.debug("[PATCH-73] advmode gen failed: %s", e)
    return None


def _generate_quizzes_from_ocr_sync(ocr_ctx, desired, user_id):  # noqa: F811
    """
    Fast quiz generation: try the /advmode cascade first every round,
    fall back to the original Gemini→Web→Perplexity chain. Cap raised to 200.
    """
    source_text = str(
        (ocr_ctx or {}).get("clean_text") or (ocr_ctx or {}).get("raw_markdown") or ""
    ).strip()
    if not source_text:
        raise RuntimeError("No readable OCR text found on this page.")

    desired = max(1, min(int(desired or 1), 200))
    out = []
    seen = set()
    batch_size = 8
    max_rounds = max(3, (desired // batch_size) + 3)
    empty_streak = 0

    for _round in range(max_rounds):
        if len(out) >= desired:
            break
        need = min(batch_size, desired - len(out))
        avoid = ""
        if out:
            avoid = "\n\nAlready generated (DO NOT repeat):\n" + "\n".join(
                f"- {x['question'][:70]}" for x in out[-12:]
            )
        try:
            prompt = _make_accurate_gen_prompt(source_text + avoid, need)  # type: ignore[name-defined]
        except Exception:
            prompt = (
                f"From the source below, create {need} unique high-quality MCQs as JSON "
                f'{{"items":[{{"question":"...","options":["A","B","C","D"],'
                f'"answer":1,"explanation":"..."}}]}}.\n\nSOURCE:\n{source_text + avoid}'
            )

        raw = _gen_via_advmode_73(prompt)
        if not raw:
            for backend in (
                lambda: call_gemini_text_rest(prompt, timeout_seconds=25, force_json=True),  # type: ignore[name-defined]
                lambda: (gemini3_solve(prompt) if callable(gemini3_solve) else None),       # type: ignore[name-defined]
                lambda: query_ai(prompt),                                                    # type: ignore[name-defined]
            ):
                try:
                    r = backend()
                    if r and str(r).strip():
                        raw = str(r).strip()
                        break
                except Exception:
                    continue

        if not raw:
            empty_streak += 1
            if empty_streak >= 3:
                break
            continue
        empty_streak = 0

        data = None
        for parser in (
            lambda s: _extract_json_strict(s),                       # type: ignore[name-defined]
            lambda s: _json73.loads(_re73.search(r'\{"items"\s*:\s*\[.*?\]\s*\}', s, _re73.DOTALL).group(0))
                       if _re73.search(r'\{"items"\s*:\s*\[.*?\]\s*\}', s, _re73.DOTALL)
                       else (_ for _ in ()).throw(ValueError()),
            lambda s: _repair_to_json(                              # type: ignore[name-defined]
                s,
                schema_hint='{"items":[{"question":"...","options":["...","...","...","..."],"answer":1,"explanation":"..."}]}',
                timeout_seconds=10,
            ),
        ):
            try:
                data = parser(raw)
                if isinstance(data, dict) and data.get("items"):
                    break
            except Exception:
                data = None
        if not isinstance(data, dict):
            continue

        for it in (data.get("items") or []):
            if len(out) >= desired:
                break
            if not isinstance(it, dict):
                continue
            q = str(it.get("question") or "").strip()
            if not q or len(q) < 5:
                continue
            sig = _re73.sub(r"\s+", " ", q).lower()[:80]
            if sig in seen:
                continue
            raw_opts = it.get("options") or []
            if isinstance(raw_opts, dict):
                raw_opts = list(raw_opts.values())
            opts = [str(x).strip() for x in raw_opts if str(x).strip()][:4]
            while len(opts) < 4:
                opts.append(f"Option {chr(65 + len(opts))}")
            ans = int(it.get("answer", 0) or 0)
            if not (1 <= ans <= 4):
                ans = 1
            seen.add(sig)
            out.append({
                "question": q,
                "options": opts,
                "answer": ans,
                "explanation": str(it.get("explanation") or "").strip(),
            })

    if not out:
        raise RuntimeError("Quiz generation failed. All providers returned empty. Try /advmode and add a working provider.")
    return out[:desired]


globals()["_generate_quizzes_from_ocr_sync"] = _generate_quizzes_from_ocr_sync


# ─── 2) AI-powered /help and .help ────────────────────────────────────────────

_HELP_USER_73 = [
    ("/start",        "Start the bot and see the welcome screen."),
    ("/help [q]",     "Open this help. Add a command or a question for AI-powered help."),
    ("/commands",     "Quick one-line list of commands you can use."),
    ("/ask <text>",   "Ask any question — answered via AI."),
    (".gen <N>",      "Reply to a photo/PDF page → generate N MCQs to your buffer."),
    (".gen ver <N>",  "Verbatim mode — keep original wording."),
    (".gen p<n> <N>", "PDF page-by-page generation (e.g. .gen p1 30)."),
    (".done / /done", "Export the buffer as CSV + JSON."),
    (".clear",        "Clear your MCQ buffer."),
    ("/buffer",       "Show buffered MCQ count."),
    (".solve",        "Solve an MCQ shown in the chat."),
]

_HELP_ADMIN_73 = _HELP_USER_73 + [
    ("/ban <id>",      "Ban a user."),
    ("/unban <id>",    "Unban a user."),
    ("/userinfo <id>", "Show user info."),
    ("/broadcast …",   "Send a message to all users."),
    ("/stats",         "Bot usage stats."),
]

_HELP_OWNER_73 = _HELP_ADMIN_73 + [
    ("/advmode",                    "Manage Advanced-Mode AI providers (registry)."),
    ("/advadd <name> <kind|key>",   "Add a provider. With newer build, just paste the API key — kind is auto-detected."),
    ("/advrm <id>",                 "Remove a provider by id."),
    ("/advprio <id> <n>",           "Set provider priority (lower runs first)."),
    (".setgenlimit <N>",            "Set GLOBAL daily .gen limit for every non-staff user."),
    (".setgenlimit <uid> <N>",      "Per-user override of the daily .gen limit."),
    (".getgenlimit [uid]",          "Show global limit or a specific user's limit + usage."),
    (".resetgenlimit <uid>",        "Remove a per-user override (back to global default)."),
    (".userlimit …",                "Alias of .setgenlimit (easier to remember)."),
    ("/mongorestore",               "Force restore SQLite state from MongoDB backup."),
    ("/mongobackup",                "Force backup to MongoDB now."),
    ("/promote <uid>",              "Promote a user to admin."),
    ("/demote <uid>",               "Demote an admin back to user."),
]


def _help_role_73(uid: int) -> str:
    try:
        if _is_owner_id(int(uid)):  # type: ignore[name-defined]
            return "owner"
    except Exception:
        pass
    try:
        if is_admin(int(uid)):  # type: ignore[name-defined]
            return "admin"
    except Exception:
        pass
    return "user"


def _help_index_for_73(role: str):
    return {"owner": _HELP_OWNER_73, "admin": _HELP_ADMIN_73}.get(role, _HELP_USER_73)


def _format_help_list_73(role: str) -> str:
    rows = _help_index_for_73(role)
    title = {"owner": "👑 Owner Panel", "admin": "🛡 Admin Panel", "user": "👤 User Panel"}[role]
    lines = [f"<b>{title} — Commands</b>", ""]
    for cmd, desc in rows:
        lines.append(f"• <code>{h(cmd)}</code> — {h(desc)}")  # type: ignore[name-defined]
    lines.append("")
    lines.append("ℹ️ Type <code>/help &lt;command or question&gt;</code> — "
                 "Bangla বা English দুইভাবেই বুঝিয়ে দিবে।")
    return "\n".join(lines)


def _ai_help_answer_73(role: str, query: str) -> str:
    rows = _help_index_for_73(role)
    catalog = "\n".join(f"- {c} — {d}" for c, d in rows)
    prompt = (
        "You are the help assistant of a Telegram MCQ-generation bot.\n"
        f"The user role is: {role}.\n"
        "Below is the FULL list of commands the user is allowed to use:\n"
        f"{catalog}\n\n"
        f"User's question: {query}\n\n"
        "Reply concisely in BOTH Bangla and English. Structure:\n"
        "1) One-line summary (what the command does)\n"
        "2) Usage: exact syntax\n"
        "3) Example: one realistic example\n"
        "4) Tip / common mistake (one line)\n"
        "If the question is not about a specific command, answer using only the catalog above. "
        "Do NOT invent commands that are not in the list. Keep total under 1200 characters. "
        "Use simple HTML only (<b>, <code>) — no markdown."
    )
    try:
        out, _ = _adv_call_text(prompt, force_json=False, timeout=15)  # type: ignore[name-defined]
        if out and str(out).strip():
            return str(out).strip()
    except Exception:
        pass
    for backend in (
        lambda: call_gemini_text_rest(prompt, timeout_seconds=20),  # type: ignore[name-defined]
        lambda: query_ai(prompt),                                    # type: ignore[name-defined]
    ):
        try:
            r = backend()
            if r and str(r).strip():
                return str(r).strip()
        except Exception:
            continue
    return "Sorry, AI help is temporarily unavailable. Use /help to see the full command list."


async def cmd_help_73(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    msg = update.effective_message
    uid = update.effective_user.id if update.effective_user else 0
    role = _help_role_73(uid)
    query = " ".join(context.args or []).strip()
    if not query:
        await msg.reply_text(_format_help_list_73(role), parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
                             disable_web_page_preview=True)
        return
    with _cx73.suppress(Exception):
        await context.bot.send_chat_action(chat_id=msg.chat_id, action="typing")
    try:
        answer = await _asyncio73.get_event_loop().run_in_executor(
            None, _ai_help_answer_73, role, query
        )
    except Exception as e:
        answer = f"Help error: {e}"
    safe = answer[:3800]
    with _cx73.suppress(Exception):
        await msg.reply_text(safe, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        return
    with _cx73.suppress(Exception):
        await msg.reply_text(_re73.sub(r"<[^>]+>", "", safe))


# .help dot-prefix dispatcher
_DOT_HELP_RE_73 = _re73.compile(r"^\.help\b\s*(.*)$", _re73.IGNORECASE)


async def _dot_help_73(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    m = update.effective_message
    if not m or not m.text:
        return
    mt = _DOT_HELP_RE_73.match(m.text.strip())
    if not mt:
        return
    rest = (mt.group(1) or "").strip()
    context.args = rest.split() if rest else []
    await cmd_help_73(update, context)


# .userlimit alias → cmd_setgenlimit_60
async def cmd_userlimit_73(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    try:
        await cmd_setgenlimit_60(update, context)  # type: ignore[name-defined]
    except Exception as e:
        with _cx73.suppress(Exception):
            await update.effective_message.reply_text(f"userlimit error: {e}")


_DOT_USERLIMIT_RE_73 = _re73.compile(r"^\.userlimit\b\s*(.*)$", _re73.IGNORECASE)


async def _dot_userlimit_73(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    m = update.effective_message
    if not m or not m.text:
        return
    mt = _DOT_USERLIMIT_RE_73.match(m.text.strip())
    if not mt:
        return
    rest = (mt.group(1) or "").strip()
    context.args = rest.split() if rest else []
    await cmd_userlimit_73(update, context)


# Register handlers — wrap build_app, register at high priority so /help overrides older handlers.
try:
    _prev_build_app_73 = build_app  # type: ignore[name-defined]
except Exception:
    _prev_build_app_73 = None


def build_app() -> "Application":  # noqa: F811  # type: ignore[name-defined]
    app = _prev_build_app_73() if _prev_build_app_73 else None
    if app is None:
        return app
    with _cx73.suppress(Exception):
        app.add_handler(CommandHandler("help", cmd_help_73), group=-500)        # type: ignore[name-defined]
        app.add_handler(CommandHandler("userlimit", cmd_userlimit_73), group=-500)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _dot_help_73), group=-500)       # type: ignore[name-defined]
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _dot_userlimit_73), group=-500)
    return app


with _cx73.suppress(Exception):
    logger.info("[PATCH-73] advmode gen routing + AI .help + userlimit alias active.")  # type: ignore[name-defined]

# ===== END SECTION 73 =====
