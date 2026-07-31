"""Centralised configuration for প্রবাহ bot.

Edit values here (or set the matching environment variables) instead of
touching the section files. Values defined here are injected into the
shared runtime namespace by ``bot/__main__.py`` *before* any section is
executed, so every section sees the same ``BOT_TOKEN`` / ``OWNER_ID``.
"""
from __future__ import annotations

import os

# ─── Required (Render Environment Variables) ─────────────────────────────────
# Telegram bot token from @BotFather. MUST be set in Render → Environment.
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

# Numeric Telegram user id of the bot owner. Accepts single id or
# comma-separated multiple ids. MUST be set in Render → Environment.
OWNER_ID: int | str = os.getenv("OWNER_ID", "").strip()
try:
    OWNER_ID = int(OWNER_ID)  # keep as int when possible
except (TypeError, ValueError):
    pass  # leave as comma-separated string; section 01 will normalise


def as_runtime_globals() -> dict:
    """Return the config values that must be present in the shared
    namespace before any section executes."""
    return {
        "BOT_TOKEN": BOT_TOKEN,
        "OWNER_ID": OWNER_ID,
    }