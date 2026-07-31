# ──────────────────────────────────────────────────────────────────────────────
# Section: 47_elevenlabs_voice_to_text_06_04
# Original lines: 25006..25599
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# END PROBAHO PATCH-R
# ═══════════════════════════════════════════════════════════════════════


# ╔══════════════════════════════════════════════════════════════════════╗
# ║   ELEVENLABS VOICE-TO-TEXT PATCH (2026-06-04)                       ║
# ║   - Owner only: /elevenlabs set KEY | status | on | off | delete    ║
# ║   - Users send voice → hidden STT → same AI response as text       ║
# ║   - Log shows key status + characters remaining                     ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ── ElevenLabs helpers ─────────────────────────────────────────────────

def get_elevenlabs_api_key() -> str:
    """Retrieve the active ElevenLabs API key from settings or env."""
    return (get_setting("elevenlabs_api_key", "") or
            os.getenv("ELEVENLABS_API_KEY", "") or "").strip()


def elevenlabs_runtime_enabled() -> bool:
    """Check if ElevenLabs voice processing is enabled."""
    return _setting_bool("elevenlabs_enabled", default=True)


def get_elevenlabs_quota_info(api_key: str) -> Dict[str, Any]:
    """
    Query ElevenLabs API for subscription info (quota / characters remaining).
    Returns dict with keys: character_count, character_limit, status, tier.
    Returns empty dict on failure.
    """
    if not api_key:
        return {}
    try:
        r = requests.get(
            "https://api.elevenlabs.io/v1/user/subscription",
            headers={"xi-api-key": api_key},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            used = int(data.get("character_count", 0) or 0)
            limit = int(data.get("character_limit", 0) or 0)
            remaining = max(0, limit - used)
            return {
                "character_count": used,
                "character_limit": limit,
                "character_remaining": remaining,
                "status": str(data.get("status", "unknown")),
                "tier": str(data.get("tier", "unknown")),
                "active": remaining > 0,
            }
    except Exception:
        pass
    return {}


def elevenlabs_speech_to_text(audio_path: str, api_key: str) -> str:
    """
    Transcribe an audio file using ElevenLabs Speech-to-Text API.
    Returns the transcribed text string.
    Raises RuntimeError on failure.
    """
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    # Detect mime type
    fname = os.path.basename(audio_path).lower()
    if fname.endswith(".ogg"):
        mime = "audio/ogg"
    elif fname.endswith(".mp3"):
        mime = "audio/mpeg"
    elif fname.endswith(".wav"):
        mime = "audio/wav"
    elif fname.endswith(".m4a"):
        mime = "audio/mp4"
    elif fname.endswith(".webm"):
        mime = "audio/webm"
    else:
        mime = "audio/ogg"  # Telegram voice default

    files = {
        "audio": (os.path.basename(audio_path), audio_bytes, mime),
        "model_id": (None, "scribe_v1"),
        # language_code omitted → ElevenLabs auto-detects (Bengali/English/etc.)
    }

    r = requests.post(
        "https://api.elevenlabs.io/v1/speech-to-text",
        headers={"xi-api-key": api_key},
        files=files,
        timeout=60,
    )

    if r.status_code != 200:
        raise RuntimeError(
            f"ElevenLabs STT error {r.status_code}: {r.text[:500]}"
        )

    data = r.json()
    text = str(data.get("text", "") or "").strip()
    if not text:
        raise RuntimeError("ElevenLabs returned empty transcription.")
    return text


# ── ElevenLabs /elevenlabs command (Owner only) ────────────────────────

@require_owner
async def cmd_elevenlabs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Owner-only: Manage ElevenLabs API key and voice-to-text toggle.

    Usage:
      /elevenlabs status   — Show key, quota, characters remaining
      /elevenlabs on       — Enable voice processing
      /elevenlabs off      — Disable voice processing
      /elevenlabs set KEY  — Save API key
      /elevenlabs delete   — Remove saved API key
    """
    if not update.message:
        return
    if not is_private_chat(update):
        await warn(update, "Private Only",
                   "Use this command in private chat with the bot.")
        return

    args = list(context.args or [])
    action = (args[0] if args else "status").strip().lower()
    remainder = " ".join(args[1:]).strip() if len(args) > 1 else ""
    if not remainder and update.message.reply_to_message:
        remainder = reply_text_or_caption(update)

    # ── STATUS ─────────────────────────────────────────────────────────
    if action in {"status", "info", "check"}:
        key = get_elevenlabs_api_key()
        enabled = elevenlabs_runtime_enabled()

        if not key:
            body = (
                f"Enabled: <code>{'ON' if enabled else 'OFF'}</code>\n"
                f"Key: <code>not set</code>\n\n"
                f"Use <code>/elevenlabs set YOUR_KEY</code> to add your key."
            )
            await ok_html(update, "ElevenLabs Voice Status", body, emoji="🎙️")
            return

        # Fetch quota from ElevenLabs API
        quota = get_elevenlabs_quota_info(key)
        if quota:
            remaining = quota.get("character_remaining", "?")
            limit = quota.get("character_limit", "?")
            used = quota.get("character_count", "?")
            tier = quota.get("tier", "?")
            status_label = quota.get("status", "?")
            active_tag = "✅ Active (quota available)" if quota.get("active") else "❌ Quota exhausted"
            body = (
                f"Enabled: <code>{'ON' if enabled else 'OFF'}</code>\n"
                f"Key: <code>{h(_mask_secret(key))}</code>\n\n"
                f"<b>📊 ElevenLabs Quota</b>\n"
                f"Status: <code>{h(status_label)}</code> — {active_tag}\n"
                f"Tier: <code>{h(tier)}</code>\n"
                f"Characters Used: <code>{h(str(used))}</code>\n"
                f"Characters Limit: <code>{h(str(limit))}</code>\n"
                f"Characters Remaining: <b><code>{h(str(remaining))}</code></b>"
            )
        else:
            body = (
                f"Enabled: <code>{'ON' if enabled else 'OFF'}</code>\n"
                f"Key: <code>{h(_mask_secret(key))}</code>\n\n"
                f"⚠️ Could not fetch quota info (check key validity)."
            )
        await ok_html(update, "ElevenLabs Voice Status", body, emoji="🎙️")
        return

    # ── ON ──────────────────────────────────────────────────────────────
    if action in {"on", "enable"}:
        _set_setting_bool("elevenlabs_enabled", True)
        await ok_html(
            update, "ElevenLabs Voice Enabled",
            "Users can now send voice messages and get AI responses — same as text.",
            emoji="✅",
        )
        return

    # ── OFF ─────────────────────────────────────────────────────────────
    if action in {"off", "disable"}:
        _set_setting_bool("elevenlabs_enabled", False)
        await ok_html(
            update, "ElevenLabs Voice Disabled",
            "Voice messages will no longer be processed by ElevenLabs STT.",
            emoji="✅",
        )
        return

    # ── DELETE ──────────────────────────────────────────────────────────
    if action in {"delete", "del", "remove", "clear"}:
        set_setting("elevenlabs_api_key", "")
        await ok_html(
            update, "ElevenLabs API Key Deleted",
            "The saved ElevenLabs API key has been removed from the database.",
            emoji="🗑️",
        )
        return

    # ── SET ─────────────────────────────────────────────────────────────
    if action in {"set", "add", "change", "update"}:
        candidate = str(remainder or "").strip()
        if not candidate:
            await safe_reply(
                update,
                usage_box(
                    "elevenlabs",
                    "<status|on|off|set KEY|delete>",
                    "Examples:\n/elevenlabs status\n/elevenlabs on\n"
                    "/elevenlabs set YOUR_ELEVENLABS_KEY\n/elevenlabs delete",
                ),
            )
            return
        set_setting("elevenlabs_api_key", candidate)
        # Verify key immediately
        quota = get_elevenlabs_quota_info(candidate)
        if quota:
            remaining = quota.get("character_remaining", "?")
            tier = quota.get("tier", "?")
            body = (
                f"Saved key: <code>{h(_mask_secret(candidate))}</code>\n\n"
                f"✅ Key verified!\n"
                f"Tier: <code>{h(tier)}</code>\n"
                f"Characters Remaining: <b><code>{h(str(remaining))}</code></b>"
            )
        else:
            body = (
                f"Saved key: <code>{h(_mask_secret(candidate))}</code>\n\n"
                f"⚠️ Could not verify key. Check it with <code>/elevenlabs status</code>."
            )
        await ok_html(update, "ElevenLabs API Key Saved", body, emoji="🔐")
        return

    await safe_reply(
        update,
        usage_box(
            "elevenlabs",
            "<status|on|off|set KEY|delete>",
            "Manage the ElevenLabs Voice-to-Text key and toggle.",
        ),
    )


# ── Voice message handler ──────────────────────────────────────────────

async def handle_voice_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Intercept Telegram voice messages (and audio files) for users/admins with
    solve_on enabled. Converts voice → text via ElevenLabs STT, then routes
    through the existing text solver — completely transparent to the user.

    The processing is 100% hidden: user sees only the AI answer, never
    any mention of STT or ElevenLabs.
    """
    if not update.effective_user or not update.message:
        return

    uid = update.effective_user.id
    if is_banned(uid):
        return

    # Must have at least solve_on (for users) or solver_mode (for admin/owner)
    role = get_role(uid)
    private = is_private_chat(update)

    if role == ROLE_USER:
        if not solver_mode_on(uid):
            return
        if not private and not is_group_ai_enabled(
            update.effective_chat.id
        ):
            return
        if not await enforce_required_memberships(update, context):
            return
    elif role in (ROLE_ADMIN, ROLE_OWNER):
        if not private or not solver_mode_on(uid):
            return
    else:
        return

    # ElevenLabs must be configured and enabled
    if not elevenlabs_runtime_enabled():
        return
    api_key = get_elevenlabs_api_key()
    if not api_key:
        return

    # Get the audio file from Telegram
    msg = update.message
    tg_file = None
    suffix = ".ogg"

    if msg.voice:
        tg_file = await msg.voice.get_file()
        suffix = ".ogg"
    elif msg.audio:
        tg_file = await msg.audio.get_file()
        fname = getattr(msg.audio, "file_name", "") or ""
        if fname.lower().endswith(".mp3"):
            suffix = ".mp3"
        elif fname.lower().endswith(".wav"):
            suffix = ".wav"
        elif fname.lower().endswith(".m4a"):
            suffix = ".m4a"
        else:
            suffix = ".ogg"
    else:
        return

    local_path = None
    spinner_msg = None
    spinner_task = None

    try:
        # Download audio to temp file
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False
        ) as f:
            local_path = f.name
        await tg_file.download_to_drive(local_path)

        # Show spinner (same as text solve — completely natural)
        spinner_msg = await msg.reply_text("🔎 Searching")
        spinner_task = asyncio.create_task(
            _spinner_task(
                context.bot, spinner_msg.chat_id, spinner_msg.message_id
            )
        )

        # ElevenLabs STT — blocking call in thread pool
        transcribed_text = await _run_blocking(
            _role_of(uid),
            elevenlabs_speech_to_text,
            local_path,
            api_key,
        )

        if not transcribed_text or not transcribed_text.strip():
            if spinner_task:
                spinner_task.cancel()
            if spinner_msg:
                with contextlib.suppress(Exception):
                    await context.bot.delete_message(
                        chat_id=spinner_msg.chat_id,
                        message_id=spinner_msg.message_id,
                    )
            # Notify user that voice could not be understood
            await err(update, "Voice Not Understood",
                      "Could not understand the voice message. Please send as text.")
            return

        # Route through existing solver — identical to text solver_picker
        # Stop spinner before sending solve picker (avoids double spinner)
        if spinner_task:
            spinner_task.cancel()
        if spinner_msg:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(
                    chat_id=spinner_msg.chat_id,
                    message_id=spinner_msg.message_id,
                )
        spinner_msg = None
        spinner_task = None

        # Directly solve via Gemini (same default as text) and show result
        # Use send_solver_picker so the user gets the model-choice buttons
        # Pass extra_payload so source_user_text is the transcribed text (not None from voice message)
        _transcribed = transcribed_text.strip()
        _voice_extra_payload: Dict[str, Any] = {
            "source_user_text": _transcribed,
            "source_message_id": int(update.message.message_id or 0),
            "source_reply_message_id": 0,
        }
        await send_solver_picker(update, context, _transcribed, extra_payload=_voice_extra_payload)

        db_log(
            "INFO",
            "voice_stt_success",
            {
                "user_id": uid,
                "chars": len(transcribed_text),
            },
        )

    except Exception as e:
        if spinner_task:
            spinner_task.cancel()
        if spinner_msg:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(
                    chat_id=spinner_msg.chat_id,
                    message_id=spinner_msg.message_id,
                )
        db_log(
            "ERROR",
            "voice_stt_failed",
            {"user_id": uid, "error": str(e)},
        )
        # Silent fail — user doesn't see internal error details
        await err(update, "Voice Processing Failed",
                  "Could not process voice. Please try sending as text.")
    finally:
        if local_path:
            with contextlib.suppress(Exception):
                os.remove(local_path)


# ── ElevenLabs log command (Owner only) ───────────────────────────────

@require_owner
async def cmd_el_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ellog — Show ElevenLabs STT usage stats from bot_logs + quota info.
    """
    if not is_private_chat(update):
        await warn(update, "Private Only",
                   "Use this command in private chat with the bot.")
        return

    api_key = get_elevenlabs_api_key()
    enabled = elevenlabs_runtime_enabled()

    # Fetch quota
    quota_block = ""
    if api_key:
        quota = get_elevenlabs_quota_info(api_key)
        if quota:
            remaining = quota.get("character_remaining", "?")
            limit = quota.get("character_limit", "?")
            used = quota.get("character_count", "?")
            tier = quota.get("tier", "?")
            active = quota.get("active", False)
            active_tag = "✅ Active" if active else "❌ Quota exhausted"
            quota_block = (
                f"\n<b>📊 Quota Info</b>\n"
                f"Status: {active_tag}\n"
                f"Tier: <code>{h(tier)}</code>\n"
                f"Used: <code>{h(str(used))}</code> / <code>{h(str(limit))}</code>\n"
                f"Remaining: <b><code>{h(str(remaining))}</code></b>"
            )
        else:
            quota_block = "\n⚠️ Could not fetch quota (invalid key?)"

    # Fetch recent STT logs from DB
    conn = db_connect()
    cur = conn.cursor()
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
             ).replace(microsecond=0).isoformat()
    cur.execute(
        "SELECT COUNT(*) AS c FROM bot_logs WHERE event='voice_stt_success' "
        "AND created_at >= ?",
        (since,),
    )
    success_24h = int((cur.fetchone() or {0: 0})["c"] or 0)

    cur.execute(
        "SELECT COUNT(*) AS c FROM bot_logs WHERE event='voice_stt_failed' "
        "AND created_at >= ?",
        (since,),
    )
    fail_24h = int((cur.fetchone() or {0: 0})["c"] or 0)

    cur.execute(
        "SELECT meta_json FROM bot_logs WHERE event='voice_stt_success' "
        "ORDER BY id DESC LIMIT 5"
    )
    recent = cur.fetchall()
    conn.close()

    total_chars = 0
    recent_lines = []
    for row in recent:
        try:
            meta = json.loads(row["meta_json"] or "{}")
            chars = int(meta.get("chars", 0) or 0)
            total_chars += chars
            uid_r = meta.get("user_id", "?")
            recent_lines.append(
                f"• user <code>{h(str(uid_r))}</code> — "
                f"<code>{h(str(chars))}</code> chars"
            )
        except Exception:
            pass

    lines = [
        f"Enabled: <code>{'ON' if enabled else 'OFF'}</code>",
        f"Key: <code>{h(_mask_secret(api_key)) if api_key else 'not set'}</code>",
        quota_block,
        "",
        f"<b>Last 24h</b>",
        f"✅ Successful: <code>{success_24h}</code>",
        f"❌ Failed: <code>{fail_24h}</code>",
    ]
    if recent_lines:
        lines += ["", "<b>Recent (last 5):</b>"] + recent_lines

    await ok_html(
        update,
        "ElevenLabs Voice Log",
        "\n".join(lines),
        emoji="🎙️",
    )


# ── Patch build_app to register ElevenLabs handlers ───────────────────

_prev_build_app_elevenlabs = build_app


def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_elevenlabs()
    private_filter = filters.ChatType.PRIVATE

    # Voice handler — group 2 so it runs AFTER admin poll/text handlers
    app.add_handler(
        MessageHandler(
            filters.VOICE | filters.AUDIO,
            handle_voice_message,
        ),
        group=2,
    )

    # /elevenlabs command (owner only, private + dot prefix)
    with contextlib.suppress(Exception):
        _register_dual_command(
            app, "elevenlabs", cmd_elevenlabs, private_filter
        )
    with contextlib.suppress(Exception):
        _register_dual_command(
            app, "el", cmd_elevenlabs, private_filter
        )
    with contextlib.suppress(Exception):
        _register_dual_command(
            app, "ellog", cmd_el_log, private_filter
        )

    logger.info(
        "[ELEVENLABS-PATCH] Registered: voice handler + /elevenlabs /el /ellog"
    )
    return app


_prev_main_elevenlabs = main


def main() -> None:  # noqa: F811
    """
    ElevenLabs final main() — wraps existing main, adds ElevenLabs startup log.
    """
    key = get_elevenlabs_api_key()
    enabled = elevenlabs_runtime_enabled()
    if key and enabled:
        quota = get_elevenlabs_quota_info(key)
        if quota:
            logger.info(
                "[ELEVENLABS] Voice STT active. Tier=%s Remaining=%s chars.",
                quota.get("tier", "?"),
                quota.get("character_remaining", "?"),
            )
        else:
            logger.info(
                "[ELEVENLABS] Voice STT enabled but quota fetch failed "
                "(check key)."
            )
    elif not key:
        logger.info(
            "[ELEVENLABS] No API key set. Voice STT inactive. "
            "Use /elevenlabs set YOUR_KEY to activate."
        )
    else:
        logger.info("[ELEVENLABS] Voice STT is disabled by owner.")

    _prev_main_elevenlabs()


logger.info(
    "[ELEVENLABS-PATCH 2026-06-04] ElevenLabs Voice-to-Text patch loaded. "
    "Commands: /elevenlabs /el /ellog | Voice handler: group=2"
)
# ══════════════════════════════════════════════════════════════════════
# END ELEVENLABS VOICE-TO-TEXT PATCH
# ══════════════════════════════════════════════════════════════════════


