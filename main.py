"""Render Free Web Service entry point.

Render runs ``python main.py`` by default for a Python web service. This
file simply boots the modular প্রবাহ bot package. The bot's own health
server (started as a daemon thread inside ``bot.main``) binds to
``$PORT`` so Render's health check succeeds and the public URL stays
responsive.
"""
from __future__ import annotations

from bot.__main__ import main as _run_bot


if __name__ == "__main__":
    _run_bot()