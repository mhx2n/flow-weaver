# ──────────────────────────────────────────────────────────────────────────────
# Section 86 (2026-08-02) — four additive fixes, nothing earlier replaced:
#
#   1) USER /help & .help lockdown.
#      Older sections (7, 10, 26, 68) each registered their own `help`
#      handler in group 0, so section 73's compact card was printed *and*
#      the legacy long guide right after it. This section registers help at
#      group -900 and raises ApplicationHandlerStop, so exactly ONE card is
#      delivered. Users get the short card only; admin/owner panels keep the
#      section-73 behaviour (including AI help for `/help <question>`).
#
#   2) AI answers mirror the user's language.
#      Bangla question -> Bangla answer, English question -> English answer,
#      Banglish -> Bangla. A LANGUAGE MIRROR block is injected into every
#      solver / OCR-answer prompt (explicit user requests still win).
#
#   3) Rich-format hinting: models are told to use Telegram-native tables,
#      blockquotes, expandable (collapsible) quotes and spoilers whenever the
#      content fits those shapes — so the rich transport (sec. 77/83/84) has
#      something to render.
#
#   4) Owner-settable PER-PAGE generation limit (alongside the daily limit):
#         .setpagelimit <N>              → global per-page cap
#         .setpagelimit <user_id> <N>    → per-user override
#         .getpagelimit [user_id]        → show effective cap
#         .resetpagelimit <user_id>      → drop the override
#      Enforced by clamping every single .gen / picker run.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx86
import re as _re86


def _log86(msg: str) -> None:
    with _cx86.suppress(Exception):
        logger.info("[S86] %s", msg)  # type: ignore[name-defined]


# ══════════════════════════════════════════════════════════════════════════
# 1) HELP LOCKDOWN
# ══════════════════════════════════════════════════════════════════════════

_USER_HELP_CARD_86 = (
    "📚 প্রবাহ Control Center\n"
    "│ Role: USER\n"
    "│ Owner Contact: @Your_Himus\n\n"
    "👤 User Commands\n"
    "│ /start or .start — Welcome / membership check\n"
    "│ /help or .help — Show the detailed command guide\n"
    "│ /cmd or .cmd — Show all available commands\n"
    "│ /q or .q — Contact support by text or by replying to a file/photo\n"
    "│ /aion or .aion — Enable private AI solving\n"
    "│ /aioff or .aioff — Disable private AI solving"
)


def _role86(uid: int) -> str:
    fn = globals().get("_help_role_73")
    if callable(fn):
        with _cx86.suppress(Exception):
            return str(fn(uid))
    with _cx86.suppress(Exception):
        if _is_owner_id(int(uid)):  # type: ignore[name-defined]
            return "owner"
    with _cx86.suppress(Exception):
        if is_admin(int(uid)):  # type: ignore[name-defined]
            return "admin"
    return "user"


async def cmd_help_86(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    msg = update.effective_message
    uid = update.effective_user.id if update.effective_user else 0
    role = _role86(uid)

    if role == "user":
        with _cx86.suppress(Exception):
            await msg.reply_text(_USER_HELP_CARD_86, disable_web_page_preview=True)
        raise ApplicationHandlerStop  # type: ignore[name-defined]

    prev = globals().get("cmd_help_73")
    if callable(prev):
        with _cx86.suppress(Exception):
            await prev(update, context)
        raise ApplicationHandlerStop  # type: ignore[name-defined]
    with _cx86.suppress(Exception):
        await msg.reply_text(_USER_HELP_CARD_86, disable_web_page_preview=True)
    raise ApplicationHandlerStop  # type: ignore[name-defined]


_DOT_HELP_RX_86 = _re86.compile(r"^[.\u06d4]\s*help\b\s*(.*)$", _re86.IGNORECASE)


async def _dot_help_86(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    m = update.effective_message
    if not m or not (m.text or "").strip():
        return
    mt = _DOT_HELP_RX_86.match(m.text.strip())
    if not mt:
        return
    rest = (mt.group(1) or "").strip()
    context.args = rest.split() if rest else []
    await cmd_help_86(update, context)


# ══════════════════════════════════════════════════════════════════════════
# 2 + 3) LANGUAGE MIRROR + RICH FORMAT HINTS
# ══════════════════════════════════════════════════════════════════════════

_BANGLA_RX_86 = _re86.compile(r"[\u0980-\u09FF]")
_BANGLISH_RX_86 = _re86.compile(
    r"\b(ki|kivabe|kemon|keno|kn|kore|korbo|bolo|bujhiye|dao|den|amake|ami|amar|"
    r"tumi|apni|hobe|hoy|na|nai|somadhan|proshno|uttor|onko|ongko|shomikoron)\b",
    _re86.IGNORECASE,
)
_WANT_EN_RX_86 = _re86.compile(
    r"(in\s+english|answer\s+in\s+english|ইংরেজি(তে)?\s*(বল|লিখ|উত্তর)?)", _re86.IGNORECASE
)
_WANT_BN_RX_86 = _re86.compile(
    r"(in\s+bangla|in\s+bengali|বাংলা(তে|য়)?\s*(বল|লিখ|উত্তর)?)", _re86.IGNORECASE
)


def _detect_lang_86(text: str) -> str:
    s = str(text or "")
    if not s.strip():
        return "bn"
    if _WANT_EN_RX_86.search(s):
        return "en"
    if _WANT_BN_RX_86.search(s):
        return "bn"
    bn_chars = len(_BANGLA_RX_86.findall(s))
    if bn_chars >= 2:
        return "bn"
    letters = len(_re86.findall(r"[A-Za-z\u0980-\u09FF]", s))
    if letters and bn_chars / max(1, letters) > 0.15:
        return "bn"
    if _BANGLISH_RX_86.search(s):
        return "bn"
    return "en"


_RICH_RULES_86 = (
    "\n\nTELEGRAM RICH-FORMAT RULES (follow strictly):\n"
    "- Comparisons, properties, data with 2+ columns MUST be a markdown table "
    "(| head | head |\\n|---|---|\\n| cell | cell |).\n"
    "- Important definitions/formulas/notes go inside a blockquote line starting with '> '.\n"
    "- Long side-explanations, derivations or extra background go inside an EXPANDABLE "
    "(collapsible) blockquote: start the block with '**> ' and end the last line with '||'.\n"
    "- Hide the final answer/spoiler-worthy value inside spoiler markers: ||answer||.\n"
    "- Use **bold** for key terms, `code` for symbols/units, and numbered/bulleted lists for steps.\n"
    "- Never emit HTML tags, never emit raw LaTeX with $ signs; keep math clean and complete.\n"
)


def _lang_block_86(lang: str) -> str:
    if lang == "bn":
        return (
            "\n\nLANGUAGE MIRROR (highest priority):\n"
            "- The user's message is Bangla (or Bangla written with English letters).\n"
            "- Answer ENTIRELY in Bangla script. Do NOT answer in English.\n"
            "- Keep technical terms, symbols, units and formulas as-is.\n"
            "- Do not translate the user's own quoted text.\n"
        )
    return (
        "\n\nLANGUAGE MIRROR (highest priority):\n"
        "- The user's message is English. Answer ENTIRELY in English.\n"
        "- Do not switch to Bangla unless the user asks for it.\n"
    )


def _augment_prompt_86(prompt: str, source_text: str) -> str:
    lang = _detect_lang_86(source_text)
    return str(prompt or "") + _lang_block_86(lang) + _RICH_RULES_86


# ── wrap the solver prompt builder ────────────────────────────────────────
_prev_build_solver_86 = globals().get("_build_solver_prompt")

if callable(_prev_build_solver_86):

    def _build_solver_prompt(problem_text: str, scope: str = "private_academic") -> str:  # noqa: F811
        base = _prev_build_solver_86(problem_text, scope)
        with _cx86.suppress(Exception):
            return _augment_prompt_86(base, problem_text)
        return base

    globals()["_build_solver_prompt"] = _build_solver_prompt
    _log86("solver prompt → language mirror + rich format rules")


# ── wrap the OCR / image-answer prompt builder ────────────────────────────
_prev_master_ocr_86 = globals().get("_build_master_ocr_prompt")

if callable(_prev_master_ocr_86):

    def _build_master_ocr_prompt(ocr_ctx, user_question: str, previous_answer: str = "") -> str:  # noqa: F811
        base = _prev_master_ocr_86(ocr_ctx, user_question, previous_answer)
        probe = str(user_question or "")
        if not probe.strip():
            with _cx86.suppress(Exception):
                probe = str((ocr_ctx or {}).get("clean_text") or "")[:1200]
        with _cx86.suppress(Exception):
            return _augment_prompt_86(base, probe)
        return base

    globals()["_build_master_ocr_prompt"] = _build_master_ocr_prompt
    _log86("OCR answer prompt → language mirror + rich format rules")


# ── academic rescue prompt (fallback path) ────────────────────────────────
_prev_rescue_86 = globals().get("_build_academic_rescue_prompt")

if callable(_prev_rescue_86):

    def _build_academic_rescue_prompt(problem_text: str, scope: str = "private_academic") -> str:  # noqa: F811
        base = _prev_rescue_86(problem_text, scope)
        with _cx86.suppress(Exception):
            return _augment_prompt_86(base, problem_text)
        return base

    globals()["_build_academic_rescue_prompt"] = _build_academic_rescue_prompt


# ── global system prompt gets the same standing rules ─────────────────────
with _cx86.suppress(Exception):
    _sp86 = globals().get("STRICT_SYSTEM_PROMPT") or ""
    if _sp86 and "LANGUAGE MIRROR" not in _sp86:
        globals()["STRICT_SYSTEM_PROMPT"] = (
            _sp86
            + "\n\nALWAYS reply in the SAME language the user wrote in "
              "(Bangla question → Bangla answer, English question → English answer; "
              "Bangla written in English letters → Bangla script answer)."
            + _RICH_RULES_86
        )
        _log86("STRICT_SYSTEM_PROMPT extended (language mirror + rich rules)")


# ══════════════════════════════════════════════════════════════════════════
# 4) PER-PAGE GENERATION LIMIT (owner controlled)
# ══════════════════════════════════════════════════════════════════════════

_PAGE_LIMIT_GLOBAL_KEY_86 = "gen_page_limit_global"
_PAGE_LIMIT_DEFAULT_86 = 30


def _page_limit_user_key_86(uid: int) -> str:
    return f"gen_page_limit_user_{int(uid)}"


def _get_global_page_limit_86() -> int:
    with _cx86.suppress(Exception):
        raw = (get_setting(_PAGE_LIMIT_GLOBAL_KEY_86, "") or "").strip()  # type: ignore[name-defined]
        if raw:
            return max(1, min(int(raw), 200))
    return _PAGE_LIMIT_DEFAULT_86


def _get_user_page_limit_86(uid: int) -> int:
    with _cx86.suppress(Exception):
        raw = (get_setting(_page_limit_user_key_86(uid), "") or "").strip()  # type: ignore[name-defined]
        if raw:
            return max(1, min(int(raw), 200))
    return _get_global_page_limit_86()


def _is_staff_86(uid: int) -> bool:
    fn = globals().get("_is_staff_60")
    if callable(fn):
        with _cx86.suppress(Exception):
            return bool(fn(uid))
    with _cx86.suppress(Exception):
        return bool(_is_owner_id(uid) or is_admin(uid))  # type: ignore[name-defined]
    return False


_prev_gen_buffer_86 = globals().get("_generate_to_buffer_59")

if callable(_prev_gen_buffer_86):

    async def _generate_to_buffer_59(update, context, ocr_ctx, uid, count, mode="std"):  # noqa: F811
        try:
            uid_i = int(uid or 0)
        except Exception:
            uid_i = 0
        want = max(0, int(count or 0))
        if uid_i and want and not _is_staff_86(uid_i):
            cap = _get_user_page_limit_86(uid_i)
            if want > cap:
                with _cx86.suppress(Exception):
                    await update.effective_message.reply_text(
                        ui_box_html(  # type: ignore[name-defined]
                            "Per-Page Limit",
                            f"একটি পৃষ্ঠা থেকে সর্বোচ্চ <b>{cap}</b> টি প্রশ্ন বানানো যাবে।\n"
                            f"তোমার চাওয়া: <b>{want}</b> → সমন্বয় করা হলো <b>{cap}</b>।",
                            emoji="📄",
                        ),
                        parse_mode=ParseMode.HTML,  # type: ignore[name-defined]
                    )
                want = cap
        return await _prev_gen_buffer_86(update, context, ocr_ctx, uid_i or uid, want, mode)

    globals()["_generate_to_buffer_59"] = _generate_to_buffer_59
    _log86("per-page generation cap active")


async def cmd_setpagelimit_86(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    msg = update.effective_message
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_owner_id(uid):  # type: ignore[name-defined]
        with _cx86.suppress(Exception):
            await msg.reply_text("Owner only.")
        return
    args = [a for a in (context.args or []) if str(a).strip()]
    if not args:
        with _cx86.suppress(Exception):
            await msg.reply_text(
                "Usage:\n"
                ".setpagelimit <N>             → global per-page cap\n"
                ".setpagelimit <user_id> <N>   → per-user override\n"
                ".getpagelimit [user_id]\n"
                ".resetpagelimit <user_id>"
            )
        return
    try:
        if len(args) == 1:
            n = max(1, min(int(args[0]), 200))
            set_setting(_PAGE_LIMIT_GLOBAL_KEY_86, str(n))  # type: ignore[name-defined]
            await msg.reply_text(f"✅ Global per-page limit = {n} MCQ/page.")
            return
        target = int(args[0])
        n = max(1, min(int(args[1]), 200))
        set_setting(_page_limit_user_key_86(target), str(n))  # type: ignore[name-defined]
        await msg.reply_text(f"✅ User {target} per-page limit = {n} MCQ/page.")
    except Exception as e:
        with _cx86.suppress(Exception):
            await msg.reply_text(f"Invalid value: {e}")


async def cmd_getpagelimit_86(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    msg = update.effective_message
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_owner_id(uid):  # type: ignore[name-defined]
        with _cx86.suppress(Exception):
            await msg.reply_text("Owner only.")
        return
    args = [a for a in (context.args or []) if str(a).strip()]
    if not args:
        with _cx86.suppress(Exception):
            await msg.reply_text(f"📄 Global per-page limit: {_get_global_page_limit_86()} MCQ/page.")
        return
    try:
        target = int(args[0])
    except Exception:
        with _cx86.suppress(Exception):
            await msg.reply_text("Usage: .getpagelimit <user_id>")
        return
    with _cx86.suppress(Exception):
        await msg.reply_text(
            f"📄 User {target}\n"
            f"Per-page limit: {_get_user_page_limit_86(target)}\n"
            f"Global default: {_get_global_page_limit_86()}"
        )


async def cmd_resetpagelimit_86(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    msg = update.effective_message
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_owner_id(uid):  # type: ignore[name-defined]
        with _cx86.suppress(Exception):
            await msg.reply_text("Owner only.")
        return
    args = [a for a in (context.args or []) if str(a).strip()]
    if not args:
        with _cx86.suppress(Exception):
            await msg.reply_text("Usage: .resetpagelimit <user_id>")
        return
    try:
        target = int(args[0])
        set_setting(_page_limit_user_key_86(target), "")  # type: ignore[name-defined]
        await msg.reply_text(f"♻️ User {target} per-page override removed (global default now).")
    except Exception as e:
        with _cx86.suppress(Exception):
            await msg.reply_text(f"Reset failed: {e}")


_DOT_PAGELIMIT_RX_86 = _re86.compile(
    r"^[.\u06d4]\s*(setpagelimit|getpagelimit|resetpagelimit)\b\s*(.*)$", _re86.IGNORECASE
)


async def _dot_pagelimit_86(update: Update, context: ContextTypes.DEFAULT_TYPE):  # type: ignore[name-defined]
    m = update.effective_message
    if not m or not (m.text or "").strip():
        return
    mt = _DOT_PAGELIMIT_RX_86.match(m.text.strip())
    if not mt:
        return
    name = mt.group(1).lower()
    rest = (mt.group(2) or "").strip()
    context.args = rest.split() if rest else []
    fn = {
        "setpagelimit": cmd_setpagelimit_86,
        "getpagelimit": cmd_getpagelimit_86,
        "resetpagelimit": cmd_resetpagelimit_86,
    }[name]
    await fn(update, context)


# ══════════════════════════════════════════════════════════════════════════
# 5) OWNER "/" MENU — expose every owner command after restart
# ══════════════════════════════════════════════════════════════════════════

_OWNER_MENU_EXTRA_86 = [
    ("setpagelimit",   "Per-page MCQ generation cap (global / per-user)"),
    ("getpagelimit",   "Show per-page generation cap"),
    ("resetpagelimit", "Remove a user's per-page cap override"),
    ("setgenlimit",    "Daily .gen limit (global / per-user)"),
    ("getgenlimit",    "Show daily .gen limit + usage"),
    ("resetgenlimit",  "Remove a user's daily limit override"),
    ("userlimit",      "Alias of setgenlimit"),
    ("advmode",        "Advanced-Mode AI provider registry"),
    ("advadd",         "Add an AI provider (paste API key)"),
    ("advrm",          "Remove an AI provider"),
    ("advprio",        "Set AI provider priority"),
    ("aiq",            "Generate quiz from plain text"),
    ("stopquiz",       "Stop the running quiz posting job"),
    ("linktopic",      "Use a post link as the quiz topic anchor"),
    ("topicimg",       "Attach slide images to the topic card"),
    ("postdelay",      "Delay between quiz posts (seconds)"),
    ("shuffle",        "Toggle option shuffling on/off"),
    ("mongobackup",    "Backup state to MongoDB now"),
    ("mongorestore",   "Restore state from MongoDB backup"),
    ("promote",        "Promote a user to admin"),
    ("demote",         "Demote an admin to user"),
]


def _install_owner_menu_86() -> None:
    sections = globals().get("PRIVATE_COMMAND_SECTIONS")
    if not isinstance(sections, dict) or "owner" not in sections:
        return
    known = {n for bucket in ("user", "admin", "owner") for (n, _d) in sections.get(bucket, [])}
    for name, desc in _OWNER_MENU_EXTRA_86:
        if name in known:
            continue
        sections["owner"].append((name, desc))
        known.add(name)
    with _cx86.suppress(Exception):
        sections["owner"].sort(key=lambda it: it[0].lower())


_install_owner_menu_86()


# ══════════════════════════════════════════════════════════════════════════
# 6) HANDLER REGISTRATION (high priority, single reply guaranteed)
# ══════════════════════════════════════════════════════════════════════════

_prev_build_app_86 = globals().get("build_app")


def build_app() -> "Application":  # noqa: F811  # type: ignore[name-defined]
    app = _prev_build_app_86() if callable(_prev_build_app_86) else None
    if app is None:
        return app
    with _cx86.suppress(Exception):
        app.add_handler(CommandHandler("help", cmd_help_86), group=-900)          # type: ignore[name-defined]
        app.add_handler(CommandHandler("setpagelimit", cmd_setpagelimit_86), group=-900)
        app.add_handler(CommandHandler("getpagelimit", cmd_getpagelimit_86), group=-900)
        app.add_handler(CommandHandler("resetpagelimit", cmd_resetpagelimit_86), group=-900)
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, _dot_help_86), group=-900  # type: ignore[name-defined]
        )
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, _dot_pagelimit_86), group=-899
        )
    return app


globals()["build_app"] = build_app
_log86("help lockdown + language mirror + page limit + owner menu ready")

# ===== END SECTION 86 =====
