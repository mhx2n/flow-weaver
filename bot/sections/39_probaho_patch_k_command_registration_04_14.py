# ──────────────────────────────────────────────────────────────────────────────
# Section: 39_probaho_patch_k_command_registration_04_14
# Original lines: 20950..21129
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════
# ===== PROBAHO PATCH-K: COMMAND REGISTRATION FIX (2026-04-14) =====
#
# Root Cause Fixed:
# - group_command_guard এ OLD function object registered → নতুন allowed list কাজ করছিল না
# - /gen, /gemini group-এ blocked হচ্ছিল
# - /gen duplicate registration conflict
# - Private chat-এও /gemini কাজ করছিল না (handler chain issue)
#
# Solution:
# - Dispatcher wrapper: সবসময় current group_command_guard কল করে
# - সব command গুলো clean single registration
# - Private + Group উভয় জায়গায় কাজ করবে
# ═══════════════════════════════════════════════════════════════════════════

# ── Step 1: Dynamic dispatcher wrapper ──
# এটা registered হবে একবার, কিন্তু সবসময় current group_command_guard দেখবে
async def _dynamic_group_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Always calls the CURRENT group_command_guard (not the old captured one)."""
    fn = globals().get("group_command_guard")
    if fn and callable(fn):
        return await fn(update, context)


# ── Step 2: Final group_command_guard with all allowed commands ──
async def group_command_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Final version: blocks unknown group commands, allows all registered ones."""
    if not update.message or not update.effective_chat:
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        return
    text = str(update.message.text or "").strip()
    if not text.startswith("/"):
        return
    cmd = _extract_command_name(text)
    if not cmd:
        return
    allowed = {
        # Core
        "probaho_on", "probaho_off", "sh", "porag", "tutorial",
        "help", "start", "commands",
        # AI/Solving
        "solve_on", "solve_off", "vision_on", "vision_off",
        "gen", "pans", "ans", "qans",
        # Staff key management
        "gemini", "addkey", "keys", "delkey", "models",
        "mistral", "mk",
        # Misc
        "scanhelp",
    }
    if cmd not in allowed:
        raise ApplicationHandlerStop


# ── Step 3: Clean final build_app ──
_prev_build_app_k = build_app

def build_app() -> Application:
    app = _prev_build_app_k()

    private_f = filters.ChatType.PRIVATE
    group_f = filters.ChatType.GROUP | filters.ChatType.SUPERGROUP
    any_f = filters.ALL  # no filter = works everywhere

    # ── Remove ALL existing group_command_guard handlers ──
    # They're registered at group=-90 pointing to OLD function objects
    for gid, handler_list in list(app.handlers.items()):
        to_del = []
        for h_ in list(handler_list):
            if isinstance(h_, MessageHandler):
                # Check if this handler is a group guard (heuristic: filter includes COMMAND + group)
                try:
                    fn = h_.callback
                    fname = getattr(fn, "__name__", "")
                    if "group_command_guard" in fname or "_dynamic_group_guard" in fname:
                        to_del.append(h_)
                except Exception:
                    pass
        for h_ in to_del:
            with contextlib.suppress(Exception):
                app.remove_handler(h_, gid)

    # ── Re-register the dynamic wrapper (works for all future redefinitions) ──
    app.add_handler(
        MessageHandler(
            (group_f) & filters.COMMAND,
            _dynamic_group_guard,
        ),
        group=-90,
    )

    # ── Remove duplicate solve: callback handlers ──
    seen_solve = False
    for gid, handler_list in list(app.handlers.items()):
        to_del = []
        for h_ in list(handler_list):
            if isinstance(h_, CallbackQueryHandler):
                p = str(getattr(getattr(h_, "pattern", None), "pattern", "") or "")
                if "solve:" in p:
                    if seen_solve:
                        to_del.append(h_)
                    else:
                        seen_solve = True
        for h_ in to_del:
            with contextlib.suppress(Exception):
                app.remove_handler(h_, gid)

    # ── Register /gemini (private + owner only) ──
    # Remove old registrations first
    for gid, handler_list in list(app.handlers.items()):
        to_del = []
        for h_ in list(handler_list):
            if isinstance(h_, (CommandHandler, MessageHandler)):
                try:
                    fn = h_.callback
                    fname = getattr(fn, "__name__", "")
                    if fname in ("cmd_gemini", "cmd_gen", "cmd_pans", "cmd_addkey",
                                 "cmd_keys", "cmd_delkey", "cmd_models", "cmd_qans"):
                        to_del.append(h_)
                except Exception:
                    pass
        for h_ in to_del:
            with contextlib.suppress(Exception):
                app.remove_handler(h_, gid)

    # ── Fresh registration of all key commands ──
    _OWNER_CMDS = [
        ("gemini", globals().get("cmd_gemini")),
        ("addkey", globals().get("cmd_addkey")),
        ("keys", globals().get("cmd_keys")),
        ("delkey", globals().get("cmd_delkey")),
        ("models", globals().get("cmd_models")),
    ]
    _STAFF_CMDS = [
        ("gen", globals().get("cmd_gen")),
        ("pans", globals().get("cmd_pans")),
        ("ans", globals().get("cmd_pans")),
    ]
    _USER_CMDS = [
        ("qans", globals().get("cmd_qans")),
    ]

    for cmd_name, fn in _OWNER_CMDS:
        if not fn:
            continue
        # Owner commands: private only
        app.add_handler(CommandHandler(cmd_name, fn, filters=private_f), group=-200)
        # Also support .cmd syntax in private
        try:
            app.add_handler(_build_dot_command_handler(cmd_name, fn, base_filter=private_f), group=-200)
        except Exception:
            pass

    for cmd_name, fn in _STAFF_CMDS:
        if not fn:
            continue
        # Staff commands: work everywhere (private + group)
        app.add_handler(CommandHandler(cmd_name, fn), group=-200)
        try:
            app.add_handler(_build_dot_command_handler(cmd_name, fn), group=-200)
        except Exception:
            pass

    for cmd_name, fn in _USER_CMDS:
        if not fn:
            continue
        app.add_handler(CommandHandler(cmd_name, fn), group=-200)
        try:
            app.add_handler(_build_dot_command_handler(cmd_name, fn), group=-200)
        except Exception:
            pass

    logger.info("[PATCH-K] group_command_guard dynamic wrapper active. /gemini /gen /pans /qans freshly registered.")
    return app


logger.info("[PATCH-K 2026-04-14] Command registration fix loaded.")

# ===== END PROBAHO PATCH-K =====

