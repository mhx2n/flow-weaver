# ──────────────────────────────────────────────────────────────────────────────
# Section: 49_owner_full_command_menu_06_13
# Purpose: Expose EVERY available owner-side command in the Telegram "/" menu
#          for the bot owner(s) — A→Z. Extends PRIVATE_COMMAND_SECTIONS["owner"]
#          built in section 26 without changing user/admin menus.
#          Re-pushes the menu to each owner on post_init so the chat shows
#          the full list immediately after deploy.
# ──────────────────────────────────────────────────────────────────────────────

# Extra owner-only commands that exist in the codebase but were not yet
# listed in section 26's owner menu. Keys MUST match real CommandHandler
# names. Aliases (in COMMAND_ALIASES from section 26) are applied
# automatically by _menu_commands().
_EXTRA_OWNER_COMMANDS = [
    # ── AI key management (in-bot, owner only) ───────────────────────
    ("addkey",       "Add a Gemini/Mistral API key (in-bot)"),
    ("keys",         "List configured AI keys"),
    ("delkey",       "Delete an AI key by id/label"),
    ("gemini",       "Manage Gemini key pool (add/list/del/on/off)"),
    ("mistral",      "Manage Mistral key pool (add/list/del/on/off)"),
    ("mk",           "Quick Mistral key shortcut"),
    ("models",       "List / switch Gemini & Mistral models"),
    ("elevenlabs",   "Manage ElevenLabs voice key"),
    ("el_log",       "Show ElevenLabs voice-to-text logs"),

    # ── Generation / answering ───────────────────────────────────────
    ("gen",          "Generate a quiz from text/image"),
    ("ans",          "Get an AI answer for a question"),
    ("pans",         "Picker-style answer for OCR questions"),
    ("qa",           "Quick Q&A"),
    ("qans",         "Question-answer extraction from OCR"),

    # ── Misc owner utilities ─────────────────────────────────────────
    ("info",         "Show bot/system info"),
    ("features",     "List enabled feature flags"),
    ("restart",      "Restart the bot process"),
    ("sh",           "Group AI shortcut"),
    ("tutorial",     "Show the tutorial"),
    ("porag",        "Delete a replied message range"),
]


def _install_full_owner_command_menu():
    sections = globals().get("PRIVATE_COMMAND_SECTIONS")
    if not isinstance(sections, dict) or "owner" not in sections:
        return

    existing = {name for (name, _desc) in sections["owner"]}
    user_admin_names = set()
    for bucket in ("user", "admin"):
        for (name, _desc) in sections.get(bucket, []):
            user_admin_names.add(name)

    # Append only entries not already shown to the owner anywhere.
    for name, desc in _EXTRA_OWNER_COMMANDS:
        if name in existing or name in user_admin_names:
            continue
        sections["owner"].append((name, desc))
        existing.add(name)

    # Sort owner section A→Z by command alias (visual stability).
    try:
        sections["owner"].sort(key=lambda item: item[0].lower())
    except Exception:
        pass


_install_full_owner_command_menu()


# ── Push the refreshed menu to every owner on startup ───────────────
_owner_menu_prev_post_init = globals().get("app", None)
_owner_menu_app = globals().get("app", None)


async def _owner_menu_post_init(application):
    # Chain previous post_init if any (PATCH-R / master set their own).
    prev = globals().get("_owner_menu_chained_prev")
    if callable(prev):
        try:
            await prev(application)
        except Exception:
            pass

    refresh = globals().get("refresh_private_command_menu")
    install_defaults = globals().get("install_default_command_scopes")
    owner_ids = globals().get("OWNER_IDS") or ()

    # Re-install default user/group scopes first.
    if callable(install_defaults):
        try:
            await install_defaults(application)
        except Exception:
            pass

    if not callable(refresh):
        return

    # Build a minimal context-like object: refresh_private_command_menu only
    # uses context.bot. Use the application's bot directly via a shim.
    class _Shim:
        def __init__(self, bot):
            self.bot = bot

    shim = _Shim(application.bot)
    for oid in owner_ids:
        try:
            await refresh(shim, int(oid))
        except Exception:
            pass


if _owner_menu_app is not None:
    _prev_pi = getattr(_owner_menu_app, "post_init", None)
    globals()["_owner_menu_chained_prev"] = _prev_pi
    _owner_menu_app.post_init = _owner_menu_post_init