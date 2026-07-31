# ──────────────────────────────────────────────────────────────────────────────
# Section: 26_final_command_log_persistence_03_18
# Original lines: 12952..13941
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL COMMAND / LOG / PERSISTENCE PATCH (2026-03-18) =====
LOG_FILE_PATH = os.getenv("PROBAHO_LOG_FILE", "probaho_runtime.log")
GITHUB_BACKUP_TOKEN = os.getenv("GITHUB_BACKUP_TOKEN", "").strip()
GITHUB_BACKUP_REPO = os.getenv("GITHUB_BACKUP_REPO", "").strip()  # owner/repo
GITHUB_BACKUP_PATH = os.getenv("GITHUB_BACKUP_PATH", "probaho_state/probaho_bot.sqlite3").strip() or "probaho_state/probaho_bot.sqlite3"
GITHUB_BACKUP_BRANCH = os.getenv("GITHUB_BACKUP_BRANCH", "main").strip() or "main"
GITHUB_BACKUP_SYNC_SECONDS = max(10, int(os.getenv("GITHUB_BACKUP_SYNC_SECONDS", "15") or "15"))
RESTART_NOTICE_KEY = "restart_notice_json"

PREFERRED_ALIASES = {
    "start": "start",
    "help": "help",
    "commands": "cmd",
    "ask": "q",
    "solve_on": "aion",
    "solve_off": "aioff",
    "himusai_on": "himuon",
    "himusai_off": "himuoff",
    "probaho_on": "pro",
    "probaho_off": "prf",
    "filter": "f",
    "clear": "c",
    "done": "d",
    "buffercount": "bc",
    "addchannel": "ac",
    "listchannels": "lc",
    "removechannel": "rc",
    "setprefix": "sp",
    "setexplink": "sx",
    "post": "p",
    "postemoji": "pe",
    "emojipost": "pe",
    "imgreact": "img",
    "broadcast": "bro",
    "adminpanel": "ap",
    "reply": "r",
    "close": "col",
    "ban": "ban",
    "unban": "uban",
    "banned": "banl",
    "private_send": "ps",
    "send_private": "ps",
    "usersd": "uid",
    "users": "us",
    "vision_on": "vo",
    "vision_off": "vf",
    "scanhelp": "sch",
    "explain_on": "exo",
    "explain_off": "exf",
    "addadmin": "add",
    "removeadmin": "rad",
    "grantall": "gra",
    "revokeall": "rea",
    "grantvision": "grvo",
    "revokevision": "revo",
    "addrequired": "addrc",
    "delrequired": "delrc",
    "listrequired": "listrc",
    "ownerstats": "logs",
    "quizprefix": "qp",
    "quizlink": "qex",
    "maintenance_on": "mo",
    "maintenance_off": "mf",
    "porag": "pg",
    "tutorial": "tut",
    "sh": "sh",
    "rp": "rp",
}

COMMAND_ALIAS_REGISTRY = {
    "commands": ["cmd"],
    "ask": ["q"],
    "solve_on": ["aion"],
    "solve_off": ["aioff"],
    "himusai_on": ["himuon"],
    "himusai_off": ["himuoff"],
    "probaho_on": ["pro"],
    "probaho_off": ["prf"],
    "filter": ["f"],
    "clear": ["c"],
    "done": ["d"],
    "buffercount": ["bc"],
    "addchannel": ["ac"],
    "listchannels": ["lc"],
    "removechannel": ["rc"],
    "setprefix": ["sp"],
    "setexplink": ["sx"],
    "post": ["p"],
    "postemoji": ["pe"],
    "emojipost": ["pe"],
    "imgreact": ["img"],
    "broadcast": ["bro"],
    "adminpanel": ["ap"],
    "reply": ["r"],
    "close": ["col"],
    "unban": ["uban"],
    "banned": ["banl"],
    "private_send": ["ps"],
    "send_private": ["ps"],
    "usersd": ["uid"],
    "users": ["us"],
    "vision_on": ["vo"],
    "vision_off": ["vf"],
    "scanhelp": ["sch"],
    "explain_on": ["exo"],
    "explain_off": ["exf"],
    "addadmin": ["add"],
    "removeadmin": ["rad"],
    "grantall": ["gra"],
    "revokeall": ["rea"],
    "grantvision": ["grvo"],
    "revokevision": ["revo"],
    "addrequired": ["addrc"],
    "delrequired": ["delrc"],
    "listrequired": ["listrc"],
    "ownerstats": ["logs"],
    "quizprefix": ["qp"],
    "quizlink": ["qex"],
    "maintenance_on": ["mo"],
    "maintenance_off": ["mf"],
    "porag": ["pg"],
    "tutorial": ["tut"],
    "rp": ["rp"],
}

PRIVATE_COMMAND_SECTIONS = {
    "user": [
        ("start", "Welcome / membership check"),
        ("help", "Show the detailed command guide"),
        ("commands", "Show all available commands"),
        ("ask", "Contact support by text or by replying to a file/photo"),
        ("solve_on", "Enable private AI solving"),
        ("solve_off", "Disable private AI solving"),
    ],
    "admin": [
        ("himusai_on", "Enable inbox AI mode for staff"),
        ("himusai_off", "Disable inbox AI mode for staff"),
        ("probaho_on", "Enable AI in the current group"),
        ("probaho_off", "Disable AI in the current group"),
        ("filter", "Add a parsing filter phrase"),
        ("clear", "Clear your current buffer"),
        ("done", "Export your buffered quizzes"),
        ("buffercount", "Show the total buffered quiz count"),
        ("addchannel", "Add a channel or group for posting"),
        ("listchannels", "List your channels or groups"),
        ("removechannel", "Remove a channel or group"),
        ("setprefix", "Set or clear a posting prefix"),
        ("setexplink", "Set or clear an explanation link"),
        ("post", "Post buffered quizzes to a channel"),
        ("postemoji", "Post buffered emoji quizzes to a channel"),
        ("imgreact", "Post an image reaction quiz by replying to a photo"),
        ("broadcast", "Broadcast a message to users"),
        ("adminpanel", "View posting and admin statistics"),
        ("reply", "Reply to a support ticket"),
        ("close", "Close a support ticket"),
        ("ban", "Ban a user"),
        ("unban", "Remove a user ban"),
        ("banned", "View banned users"),
        ("private_send", "Send a protected private message to a user"),
        ("usersd", "Show stored user details"),
        ("vision_on", "Enable image extraction mode"),
        ("vision_off", "Disable image extraction mode"),
        ("scanhelp", "Show image extraction help"),
        ("explain_on", "Enable explanations in quiz/export output"),
        ("explain_off", "Disable explanations in quiz/export output"),
    ],
    "owner": [
        ("addadmin", "Promote a user to admin"),
        ("removeadmin", "Remove admin access"),
        ("grantall", "Grant an admin all-channel access"),
        ("revokeall", "Revoke all-channel access from an admin"),
        ("grantvision", "Grant image extraction access"),
        ("revokevision", "Revoke image extraction access"),
        ("addrequired", "Add a required channel or group"),
        ("delrequired", "Remove a required channel or group"),
        ("listrequired", "List required channels or groups"),
        ("ownerstats", "View system logs and the owner dashboard"),
        ("users", "Export started users"),
        ("quizprefix", "Set the generated quiz prefix"),
        ("quizlink", "Set the generated quiz explanation link"),
        ("maintenance_on", "Enable maintenance mode"),
        ("maintenance_off", "Disable maintenance mode"),
        ("rp", "Restart the bot process"),
    ],
}

GROUP_COMMANDS = [
    ("probaho_on", "Enable AI in the current group"),
    ("probaho_off", "Disable AI in the current group"),
    ("sh", "Open group AI for a message or reply"),
    ("porag", "Delete a replied message range"),
    ("tutorial", "Show the group tutorial"),
    ("commands", "Show group commands"),
    ("help", "Show group help"),
]


def _menu_commands(items: List[Tuple[str, str]]):
    from telegram import BotCommand

    out = []
    seen = set()
    for cmd, desc in items:
        alias = _preferred_alias(cmd).strip().lower()
        alias = re.sub(r"[^a-z0-9_]", "", alias)[:32]
        if not alias or alias in seen:
            continue
        seen.add(alias)
        out.append(BotCommand(alias, (desc or "")[:256]))
    return out


def _private_menu_items(uid: int) -> List[Tuple[str, str]]:
    items = list(PRIVATE_COMMAND_SECTIONS["user"])
    if is_admin(uid) or is_owner(uid):
        admin_items = list(PRIVATE_COMMAND_SECTIONS["admin"])
        if not can_use_vision(uid):
            admin_items = [item for item in admin_items if item[0] not in {"vision_on", "vision_off", "scanhelp"}]
        items.extend(admin_items)
    if is_owner(uid):
        items.extend(PRIVATE_COMMAND_SECTIONS["owner"])
    return items


async def refresh_private_command_menu(context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    if not uid:
        return
    from telegram import BotCommandScopeChat

    with contextlib.suppress(Exception):
        await context.bot.set_my_commands(
            _menu_commands(_private_menu_items(uid)),
            scope=BotCommandScopeChat(chat_id=uid),
        )


async def refresh_group_command_menu(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    if not chat_id:
        return
    from telegram import BotCommandScopeChatAdministrators

    admin_items = list(GROUP_COMMANDS)
    with contextlib.suppress(Exception):
        await context.bot.set_my_commands(
            _menu_commands(admin_items),
            scope=BotCommandScopeChatAdministrators(chat_id=chat_id),
        )


async def install_default_command_scopes(app: Application) -> None:
    from telegram import BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats

    with contextlib.suppress(Exception):
        await app.bot.set_my_commands(
            _menu_commands(PRIVATE_COMMAND_SECTIONS["user"]),
            scope=BotCommandScopeAllPrivateChats(),
        )

    with contextlib.suppress(Exception):
        await app.bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())

_GITHUB_SYNC_THREAD = None
_GITHUB_SYNC_STOP = threading.Event()
_GITHUB_LAST_SHA = {"db": None}
_GITHUB_LAST_FINGERPRINT = {"db": ""}


def _ensure_runtime_log_file_handler() -> None:
    try:
        root = logging.getLogger()
        target = os.path.abspath(LOG_FILE_PATH)
        for handler in root.handlers:
            if isinstance(handler, logging.FileHandler):
                try:
                    if os.path.abspath(getattr(handler, "baseFilename", "")) == target:
                        return
                except Exception:
                    pass
        fh = logging.FileHandler(target, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        root.addHandler(fh)
    except Exception:
        logger.exception("runtime log file handler setup failed")


def _preferred_alias(command: str) -> str:
    return PREFERRED_ALIASES.get((command or "").lstrip("/.").lower(), (command or "").lstrip("/."))


def _display_command(command: str) -> str:
    alias = _preferred_alias(command)
    return f"/{alias} or .{alias}"


def _display_code(command: str) -> str:
    return f"<code>{h(_display_command(command))}</code>"


def _command_lines(items: List[Tuple[str, str]]) -> str:
    return "\n".join([f"{_display_code(cmd)} — {h(desc)}" for cmd, desc in items])


def usage_box(command: str, args: str = "", description: str = "") -> str:
    shown = _display_command(command)
    body = f"<code>{h(shown)}"
    if args:
        body += f" {h(args)}"
    body += "</code>"
    if description:
        body += f"\n\n{h(description)}"
    return ui_box_html("Usage", body, emoji="ℹ️")


def _unauthorized_staff_text() -> str:
    return (
        "This bot is currently restricted for staff operations. Please use <code>.q [message]</code> for support.\n"
        "If you want to enable private AI solving, use <code>.aion</code>.\n"
        f"If you genuinely need access, contact the owner: <code>{h(OWNER_CONTACT)}</code>"
    )


async def warn_unauthorized(update: Update, reason: str = "") -> None:
    body = _unauthorized_staff_text()
    extra = (reason or "").strip()
    if extra and extra not in body and "restricted for staff operations" not in extra.lower():
        body = f"{body}\n\n{h(extra)}"
    await warn_html(update, "Unauthorized", body)


def _private_help_text(uid: int) -> str:
    role = normalize_role(get_role(uid))
    intro = (
        f"Role: <code>{h(role)}</code>\n"
        f"Owner Contact: <code>{h(OWNER_CONTACT)}</code>"
    )
    if role == ROLE_ADMIN and can_view_all(uid):
        intro += "\nSpecial Access: <b>All-channel visibility is enabled.</b>"
    sections = [ui_box_html(f"{BOT_BRAND} Control Center", intro, emoji="📚")]
    sections.append(ui_box_html("User Commands", _command_lines(PRIVATE_COMMAND_SECTIONS["user"]), emoji="👤"))
    if role in (ROLE_ADMIN, ROLE_OWNER):
        sections.append(ui_box_html("Staff Commands", _command_lines(PRIVATE_COMMAND_SECTIONS["admin"]), emoji="🛠"))
        sections.append(ui_box_html("Group Commands", _command_lines(GROUP_COMMANDS), emoji="👥"))
    if role == ROLE_OWNER:
        sections.append(ui_box_html("Owner Commands", _command_lines(PRIVATE_COMMAND_SECTIONS["owner"]), emoji="👑"))
    return "\n\n".join(sections)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\n\nContact: {OWNER_CONTACT}")
        return
    role = get_role(uid)
    body_html = (
        f"Role: <code>{h(role)}</code>\n"
        f"Use {_display_code('help')} for the guide or {_display_code('commands')} for the command list."
    )
    await safe_reply(update, ui_box_html(f"Welcome to {BOT_BRAND}", body_html, emoji="👋"))


def help_for_role(role: str, requester_id: int) -> str:
    return _private_help_text(requester_id)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        await cmd_commands(update, context)
        return
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\n\nContact: {OWNER_CONTACT}")
        return
    await refresh_private_command_menu(context, uid)
    await safe_reply(update, _private_help_text(uid))


async def _group_commands_view_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    uid = update.effective_user.id if update.effective_user else 0
    if not chat or chat.type not in ("group", "supergroup"):
        return False
    return await _is_group_admin_user(context, chat.id, uid)


async def cmd_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        if not await _group_commands_view_allowed(update, context):
            with contextlib.suppress(Exception):
                await update.message.delete()
            await _dm_text(context, uid, ui_box_html("Unauthorized", "Only a group admin or the bot owner can view group commands.", emoji="⚠️"))
            return
        await refresh_group_command_menu(context, chat.id)
        body = _command_lines(GROUP_COMMANDS)
        text = ui_box_html("Group Commands", body, emoji="👥")
        if update.message:
            msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            asyncio.create_task(_auto_delete_after(context.bot, chat.id, [msg.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))
            with contextlib.suppress(Exception):
                await update.message.delete()
        return

    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\n\nContact: {OWNER_CONTACT}")
        return

    await refresh_private_command_menu(context, uid)
    sections = [ui_box_html("All Available Commands", "Choose a command below.", emoji="📋")]
    sections.append(ui_box_html("User Commands", _command_lines(PRIVATE_COMMAND_SECTIONS["user"]), emoji="👤"))
    if is_admin(uid) or is_owner(uid):
        admin_items = list(PRIVATE_COMMAND_SECTIONS["admin"])
        if not can_use_vision(uid):
            admin_items = [item for item in admin_items if item[0] not in {"vision_on", "vision_off", "scanhelp"}]
        sections.append(ui_box_html("Staff Commands", _command_lines(admin_items), emoji="🛠"))
        sections.append(ui_box_html("Group Commands", _command_lines(GROUP_COMMANDS), emoji="👥"))
    if is_owner(uid):
        sections.append(ui_box_html("Owner Commands", _command_lines(PRIVATE_COMMAND_SECTIONS["owner"]), emoji="👑"))
    await safe_reply(update, "\n\n".join(sections))


async def cmd_solve_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\n\nContact: {OWNER_CONTACT}")
        return
    if get_role(uid) != ROLE_USER:
        await warn(update, "Not Available", "Private AI solving is reserved for standard users. Staff workflows remain unchanged.")
        return
    set_solver_mode_on(uid, True)
    await ok_html(update, "AI Solving Enabled", "Private academic solving is now active. Send your question directly in inbox. Disable it anytime with <code>.aioff</code>.", emoji="🧠")


async def cmd_solve_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if not await enforce_required_memberships(update, context):
        return
    if is_banned(uid):
        await err(update, "Access Denied", f"You are banned.\n\nContact: {OWNER_CONTACT}")
        return
    if get_role(uid) != ROLE_USER:
        await warn(update, "Not Available", "Private AI solving is reserved for standard users.")
        return
    set_solver_mode_on(uid, False)
    await ok_html(update, "AI Solving Disabled", "Private academic solving has been turned off. Re-enable it anytime with <code>.aion</code>.", emoji="🧠")


async def cmd_probaho_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    uid = update.effective_user.id if update.effective_user else 0
    if not chat or chat.type not in ("group", "supergroup"):
        if update.message:
            await warn(update, "Group Only", "Use this command inside a group or supergroup.")
        return
    if not await _is_group_admin_user(context, chat.id, uid):
        await _dm_text(context, uid, ui_box_html("Unauthorized", "Only a group admin or the bot owner can use this command.", emoji="⚠️"))
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    set_group_ai_enabled(chat.id, True)
    with contextlib.suppress(Exception):
        await update.message.delete()
    await _dm_text(
        context,
        uid,
        ui_box_html(
            "Group AI Enabled",
            f"Group: <code>{h(chat.id)}</code>\nMode: members can use {_display_code('sh')} only. To enable this mode later again, use {_display_code('probaho_on')}.",
            emoji="✅",
        ),
    )


async def cmd_probaho_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    uid = update.effective_user.id if update.effective_user else 0
    if not chat or chat.type not in ("group", "supergroup"):
        if update.message:
            await warn(update, "Group Only", "Use this command inside a group or supergroup.")
        return
    if not await _is_group_admin_user(context, chat.id, uid):
        await _dm_text(context, uid, ui_box_html("Unauthorized", "Only a group admin or the bot owner can use this command.", emoji="⚠️"))
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    set_group_ai_enabled(chat.id, False)
    with contextlib.suppress(Exception):
        await update.message.delete()
    await _dm_text(context, uid, ui_box_html("Group AI Disabled", f"Group: <code>{h(chat.id)}</code>\nThe {_display_code('sh')} command is now disabled in this group. Re-enable it with {_display_code('probaho_on')}.", emoji="✅"))


_FINAL_TUTORIAL_ALERT = (
    "Group Commands\n"
    f"1) Use {_display_command('probaho_on')} to enable group AI.\n"
    f"2) Members can ask with {_display_command('sh')} or by replying to a message and using that command.\n"
    f"3) Use {_display_command('porag')} to delete a replied range.\n"
    f"4) Group replies auto-delete after 10 minutes."
)


async def cmd_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    uid = update.effective_user.id if update.effective_user else 0
    if not await _is_group_admin_user(context, update.effective_chat.id, uid):
        with contextlib.suppress(Exception):
            await update.message.delete()
        return
    text = (
        "Group Usage Guide:\n"
        f"1) Enable group AI with {_display_command('probaho_on')}.\n"
        f"2) Members can use {_display_command('sh')} for direct or reply-based AI access.\n"
        f"3) Delete a replied range with {_display_command('porag')}.\n"
        "4) Group replies auto-delete after 10 minutes.\n"
        f"5) Disable group AI with {_display_command('probaho_off')}."
    )
    msg = await update.message.reply_text(text, disable_web_page_preview=True)
    asyncio.create_task(_auto_delete_after(context.bot, update.effective_chat.id, [msg.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))
    with contextlib.suppress(Exception):
        await update.message.delete()


async def on_tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.message or not q.message.chat:
        return
    uid = q.from_user.id if q.from_user else 0
    if not await _is_group_admin_user(context, q.message.chat.id, uid):
        with contextlib.suppress(Exception):
            await q.answer("Only group admins can view this.", show_alert=True, cache_time=0)
        return
    try:
        await q.answer(_FINAL_TUTORIAL_ALERT[:180], show_alert=True, cache_time=0)
    except TelegramError:
        with contextlib.suppress(Exception):
            await q.answer("Use .pro/.prf in the group and /sh or .sh for AI replies.", show_alert=True, cache_time=0)


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = getattr(update, 'my_chat_member', None)
    if not cmu:
        return
    try:
        old_status = cmu.old_chat_member.status
        new_status = cmu.new_chat_member.status
        chat = cmu.chat
        actor = cmu.from_user
    except Exception:
        return

    if new_status in ("member", "administrator") and old_status in ("left", "kicked") and chat.type in ("group", "supergroup"):
        actor_name = actor.first_name if actor else "Admin"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📘 Tutorial", callback_data="tutorial:show")]])
        text = (
            f"Thank you, {h(actor_name)}, for adding {h(BOT_BRAND)}.\n"
            f"Enable group AI with {_display_code('probaho_on')}. Members can use {_display_code('sh')} after activation."
        )
        with contextlib.suppress(Exception):
            msg = await context.bot.send_message(
                chat_id=chat.id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            asyncio.create_task(_auto_delete_after(context.bot, chat.id, [msg.message_id], GROUP_BOT_MESSAGE_TTL_SECONDS))


def group_command_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    cmd = _extract_command_name(update.message.text or "")
    allowed = {"probaho_on", "probaho_off", "pro", "prf", "sh", "porag", "pg", "tutorial", "tut", "cmd", "commands", "help"}
    if cmd and (update.message.text or "").strip().startswith("/") and cmd not in allowed:
        raise ApplicationHandlerStop


def _github_backup_enabled() -> bool:
    return bool(GITHUB_BACKUP_TOKEN and GITHUB_BACKUP_REPO and GITHUB_BACKUP_PATH)


def _github_api_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {GITHUB_BACKUP_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_contents_url(path_in_repo: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_BACKUP_REPO}/contents/{path_in_repo.lstrip('/')}"


def restore_db_from_github(force: bool = False) -> bool:
    if not _github_backup_enabled():
        return False
    try:
        if (not force) and os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
            return False
    except Exception:
        pass
    try:
        res = requests.get(
            _github_contents_url(GITHUB_BACKUP_PATH),
            headers=_github_api_headers(),
            params={"ref": GITHUB_BACKUP_BRANCH},
            timeout=25,
        )
        if res.status_code != 200:
            logger.info("GitHub restore skipped: %s", res.status_code)
            return False
        data = res.json() or {}
        content_b64 = str(data.get("content") or "").replace("\n", "")
        if not content_b64:
            return False
        blob = base64.b64decode(content_b64)
        with open(DB_PATH, "wb") as f:
            f.write(blob)
        _GITHUB_LAST_SHA["db"] = str(data.get("sha") or "")
        logger.info("Database restored from GitHub backup")
        return True
    except Exception as e:
        logger.exception("GitHub restore failed: %s", e)
        return False


def upload_db_to_github(force: bool = False) -> bool:
    if not _github_backup_enabled() or not os.path.exists(DB_PATH):
        return False
    try:
        with open(DB_PATH, "rb") as f:
            blob = f.read()
        if not blob:
            return False
        local_fp = __import__("hashlib").sha256(blob).hexdigest()
        if (not force) and local_fp == (_GITHUB_LAST_FINGERPRINT.get("db") or ""):
            return False
        current_sha = None
        try:
            res = requests.get(
                _github_contents_url(GITHUB_BACKUP_PATH),
                headers=_github_api_headers(),
                params={"ref": GITHUB_BACKUP_BRANCH},
                timeout=20,
            )
            if res.status_code == 200:
                current_sha = str((res.json() or {}).get("sha") or "")
            elif res.status_code not in (404,):
                logger.info("GitHub preflight returned %s", res.status_code)
        except Exception:
            current_sha = _GITHUB_LAST_SHA.get("db")
        payload = {
            "message": f"Update bot state at {datetime.utcnow().isoformat()}Z",
            "content": base64.b64encode(blob).decode("ascii"),
            "branch": GITHUB_BACKUP_BRANCH,
        }
        if current_sha:
            payload["sha"] = current_sha
        res = requests.put(_github_contents_url(GITHUB_BACKUP_PATH), headers=_github_api_headers(), json=payload, timeout=45)
        if res.status_code not in (200, 201):
            logger.warning("GitHub backup failed: %s %s", res.status_code, res.text[:160])
            return False
        out = res.json() or {}
        content = out.get("content") or {}
        _GITHUB_LAST_SHA["db"] = str(content.get("sha") or current_sha or "")
        _GITHUB_LAST_FINGERPRINT["db"] = local_fp
        logger.info("Database backup pushed to GitHub")
        return True
    except Exception as e:
        logger.exception("GitHub backup failed: %s", e)
        return False


def _github_sync_worker() -> None:
    while not _GITHUB_SYNC_STOP.wait(GITHUB_BACKUP_SYNC_SECONDS):
        with contextlib.suppress(Exception):
            upload_db_to_github(force=False)


def start_github_backup_worker() -> None:
    global _GITHUB_SYNC_THREAD
    if not _github_backup_enabled() or (_GITHUB_SYNC_THREAD and _GITHUB_SYNC_THREAD.is_alive()):
        return
    _GITHUB_SYNC_STOP.clear()
    _GITHUB_SYNC_THREAD = threading.Thread(target=_github_sync_worker, name="github-backup-sync", daemon=True)
    _GITHUB_SYNC_THREAD.start()


def stop_github_backup_worker() -> None:
    _GITHUB_SYNC_STOP.set()


def _set_restart_notice(chat_id: int, requested_by: int) -> None:
    payload = {
        "chat_id": int(chat_id),
        "requested_by": int(requested_by),
        "created_at": now_iso(),
    }
    set_setting(RESTART_NOTICE_KEY, json.dumps(payload, ensure_ascii=False))


def _get_restart_notice() -> Dict[str, Any]:
    raw = get_setting(RESTART_NOTICE_KEY, "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _clear_restart_notice() -> None:
    set_setting(RESTART_NOTICE_KEY, "")


def _send_pending_restart_notice_via_http() -> None:
    notice = _get_restart_notice()
    chat_id = int(notice.get("chat_id") or 0)
    if not chat_id:
        return
    text = ui_box_html("Restart Successful", "The bot has restarted successfully and is operational again.", emoji="✅")
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": str(chat_id),
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=20,
        )
    except Exception as e:
        logger.exception("restart success notification failed: %s", e)
    finally:
        with contextlib.suppress(Exception):
            _clear_restart_notice()


def _write_combined_log_snapshot() -> str:
    fd, path = tempfile.mkstemp(prefix="probaho_logs_", suffix=".log")
    os.close(fd)
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT created_at, level, event, meta_json FROM bot_logs ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    with open(path, "w", encoding="utf-8") as f:
        f.write("=== PROBAHO RUNTIME LOG ===\n")
        if os.path.exists(LOG_FILE_PATH):
            try:
                with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="ignore") as rf:
                    f.write(rf.read())
            except Exception as e:
                f.write(f"[runtime log read failed] {e}\n")
        else:
            f.write("[runtime log file not found]\n")
        f.write("\n\n=== DATABASE EVENT LOG ===\n")
        for row in rows:
            ts = str(row["created_at"] or "")
            level = str(row["level"] or "INFO")
            event = str(row["event"] or "")
            meta = str(row["meta_json"] or "")
            f.write(f"{ts} | {level} | {event} | {meta}\n")
    return path


@require_owner
async def cmd_ownerstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM users")
    total_users = int(cur.fetchone()["c"] or 0)

    cur.execute("SELECT COUNT(*) AS c FROM users WHERE role IN ('OWNER','ADMIN')")
    staff_count = int(cur.fetchone()["c"] or 0)

    since_active_dt = dt.datetime.now(timezone.utc) - dt.timedelta(hours=24)
    since_active_iso = since_active_dt.replace(microsecond=0).isoformat()
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE last_seen_at IS NOT NULL AND last_seen_at >= ?", (since_active_iso,))
    active_24h = int(cur.fetchone()["c"] or 0)

    since_error_dt = dt.datetime.now(timezone.utc) - dt.timedelta(hours=1)
    since_error_iso = since_error_dt.replace(microsecond=0).isoformat()
    cur.execute("SELECT COUNT(*) AS c FROM bot_logs WHERE level='ERROR' AND created_at >= ?", (since_error_iso,))
    err_1h = int(cur.fetchone()["c"] or 0)

    cur.execute("SELECT created_at, event, meta_json FROM bot_logs WHERE level='ERROR' ORDER BY id DESC LIMIT 5")
    last_errors = cur.fetchall()
    conn.close()

    db_mb = 0.0
    try:
        if os.path.exists(DB_PATH):
            db_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    except Exception:
        db_mb = 0.0

    rss_mb = process_rss_mb()
    github_status = "Enabled" if _github_backup_enabled() else "Disabled"

    lines = [
        "<b>📑 System Log Summary</b>",
        f"⏱ Uptime: <code>{h(fmt_uptime())}</code>",
        "",
        f"👥 Total Users: <b>{h(total_users)}</b>",
        f"🛠 Staff Accounts: <b>{h(staff_count)}</b>",
        f"✅ Active Users (24h): <b>{h(active_24h)}</b>",
        "",
        f"💾 Database Size: <code>{h(fmt_mb(db_mb))}</code>",
        f"🧠 RAM (RSS): <code>{h(fmt_mb(rss_mb))}</code>",
        f"☁️ GitHub Backup: <code>{h(github_status)}</code>",
        "",
        f"🔴 Errors (Last 1 Hour): <b>{h(err_1h)}</b>",
    ]
    if last_errors:
        lines.append("")
        lines.append("<b>Recent Errors</b>")
        for row in last_errors:
            ts = str(row["created_at"] or "")[-8:]
            event = str(row["event"] or "")[:28]
            meta = ""
            try:
                meta = str((json.loads(row["meta_json"] or "{}") or {}).get("error") or "")
            except Exception:
                meta = ""
            meta = h(meta.replace("\n", " ")[:60]) if meta else ""
            if meta:
                lines.append(f"• <code>{h(ts)}</code> — {h(event)} — <i>{meta}</i>")
            else:
                lines.append(f"• <code>{h(ts)}</code> — {h(event)}")

    await safe_reply(update, "\n".join(lines))

    snapshot_path = _write_combined_log_snapshot()
    try:
        with open(snapshot_path, "rb") as rf:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=rf,
                filename="probaho_full_logs.log",
                caption="Complete runtime and database log snapshot",
            )
    finally:
        with contextlib.suppress(Exception):
            os.remove(snapshot_path)


@require_owner
async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    chat_id = update.effective_chat.id if update.effective_chat else uid
    _set_restart_notice(chat_id, uid)
    await ok_html(update, "Restart Initiated", "The bot is restarting now. A confirmation message will be sent after the service is back online.", emoji="♻️")
    await asyncio.sleep(0.6)
    with contextlib.suppress(Exception):
        upload_db_to_github(force=True)
    os.execv(sys.executable, [sys.executable] + sys.argv)


_old_build_app_20260318 = build_app


def build_app() -> Application:
    app = _old_build_app_20260318()
    private_filter = filters.ChatType.PRIVATE
    group_filter = (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)

    private_aliases = [
        ("cmd", cmd_commands),
        ("q", cmd_ask),
        ("aion", cmd_solve_on),
        ("aioff", cmd_solve_off),
        ("himuon", cmd_himusai_on),
        ("himuoff", cmd_himusai_off),
        ("f", cmd_filter),
        ("c", cmd_clear),
        ("d", cmd_done),
        ("bc", cmd_buffercount),
        ("ac", cmd_addchannel),
        ("lc", cmd_listchannels),
        ("rc", cmd_removechannel),
        ("sp", cmd_setprefix),
        ("sx", cmd_setexplink),
        ("p", cmd_post),
        ("pe", cmd_postemoji),
        ("img", cmd_imgreact),
        ("bro", cmd_broadcast),
        ("ap", cmd_adminpanel),
        ("r", cmd_reply),
        ("col", cmd_close),
        ("uban", cmd_unban),
        ("banl", cmd_banned),
        ("ps", cmd_private_send),
        ("uid", cmd_usersd),
        ("us", cmd_users),
        ("vo", cmd_vision_on),
        ("vf", cmd_vision_off),
        ("sch", cmd_scanhelp),
        ("exo", cmd_explain_on),
        ("exf", cmd_explain_off),
        ("add", cmd_addadmin),
        ("rad", cmd_removeadmin),
        ("gra", cmd_grantall),
        ("rea", cmd_revokeall),
        ("grvo", cmd_grantvision),
        ("revo", cmd_revokevision),
        ("addrc", cmd_addrequired),
        ("delrc", cmd_delrequired),
        ("listrc", cmd_listrequired),
        ("logs", cmd_ownerstats),
        ("qp", cmd_quizprefix),
        ("qex", cmd_quizlink),
        ("mo", cmd_maintenance_on),
        ("mf", cmd_maintenance_off),
        ("rp", cmd_restart),
    ]
    for alias, callback in private_aliases:
        _register_dual_command(app, alias, callback, private_filter)

    group_aliases = [
        ("pro", cmd_probaho_on),
        ("prf", cmd_probaho_off),
        ("pg", cmd_porag),
        ("tut", cmd_tutorial),
        ("cmd", cmd_commands),
        ("help", cmd_help),
    ]
    for alias, callback in group_aliases:
        _register_dual_command(app, alias, callback, group_filter)
    return app


def main():
    _ensure_runtime_log_file_handler()
    with contextlib.suppress(Exception):
        restore_db_from_github(force=False)
    with contextlib.suppress(Exception):
        threading.Thread(target=_run_render_health_server, daemon=True).start()
    app = build_app()
    start_github_backup_worker()
    with contextlib.suppress(Exception):
        _send_pending_restart_notice_via_http()
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        print(f"🤖 {BOT_BRAND} started. OWNER_ID={OWNER_ID} DB={DB_PATH}")
    except (UnicodeEncodeError, AttributeError, TypeError):
        try:
            print("[BOT] Started. OWNER_ID={} DB={}".format(OWNER_ID, DB_PATH))
        except Exception:
            logging.info("Bot started. OWNER_ID=%s DB=%s", OWNER_ID, DB_PATH)

    # ── OCR midnight reset (BST 00:00) ──
    async def _post_init_hook(application) -> None:
        with contextlib.suppress(Exception):
            asyncio.create_task(_ocr_midnight_reset_loop())
            logger.info("[MAIN] OCR midnight reset task started via post_init.")

    with contextlib.suppress(Exception):
        app.post_init = _post_init_hook

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        with contextlib.suppress(Exception):
            upload_db_to_github(force=True)
        stop_github_backup_worker()




