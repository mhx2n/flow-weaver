# ──────────────────────────────────────────────────────────────────────────────
# Section: 37_final_entrypoint_key_alias_fix_04_13
# Original lines: 20083..20182
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ===== FINAL ENTRYPOINT / KEY ALIAS FIX 2026-04-13 =====
# Problem solved here:
# - Earlier main() was called before the later patch sections loaded.
# - /addkey, /keys, /delkey were not exposed although Gemini key table support existed.
# - Group command guard was too strict for key management aliases.

def _acquire_single_instance_lock() -> None:
    """Prevent accidental double-start on the same filesystem (best-effort)."""
    lock_path = Path(DB_PATH).with_suffix(".lock")
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    except Exception:
        return
    try:
        try:
            import fcntl  # Linux/Unix only
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            raise SystemExit(
                "Another bot instance appears to be running with the same DB. "
                "Stop the duplicate process/service and start only one instance."
            )
    except BaseException:
        try:
            os.close(fd)
        except Exception:
            pass
        raise

async def _gemini_route_args(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]):
    old_args = getattr(context, "args", None)
    try:
        setattr(context, "args", args)
        return await cmd_gemini(update, context)
    finally:
        try:
            setattr(context, "args", old_args)
        except Exception:
            pass

async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        body_html = (
            _gemini_runtime_report_html()
            + "<br><br><b>Text model order</b>:<br>"
            + h(" → ".join(_all_text_model_candidates()))
            + "<br><br><b>Vision model order</b>:<br>"
            + h(" → ".join(_all_vision_model_candidates()))
        )
        await ok_html(update, "Gemini Rotation", body_html, emoji="🧠")
    except Exception as e:
        await err(update, "Models", str(e)[:250])

async def cmd_addkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        return await _gemini_route_args(update, context, ["add", *(context.args or [])])
    except Exception as e:
        await err(update, "Add Key Failed", str(e)[:250])

async def cmd_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        return await _gemini_route_args(update, context, ["list"])
    except Exception as e:
        await err(update, "Keys Failed", str(e)[:250])

async def cmd_delkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        return await _gemini_route_args(update, context, ["remove", *(context.args or [])])
    except Exception as e:
        await err(update, "Delete Key Failed", str(e)[:250])

_prev_build_app_key_alias_patch = build_app

def build_app() -> Application:  # noqa: F811
    app = _prev_build_app_key_alias_patch()
    _register_dual_command(app, "addkey", cmd_addkey, group=-100)
    _register_dual_command(app, "keys", cmd_keys, group=-100)
    _register_dual_command(app, "delkey", cmd_delkey, group=-100)
    _register_dual_command(app, "models", cmd_models, group=-100)
    return app

_prev_group_command_guard = group_command_guard

async def group_command_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
    if not update.message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    cmd = _extract_command_name(update.message.text or "")
    allowed = {
        "probaho_on", "probaho_off", "sh", "porag", "tutorial",
        "gemini", "gen", "pans", "ans",
        "addkey", "keys", "delkey", "models",
        "solve_on", "solve_off", "vision_on", "vision_off",
        "scanhelp", "help", "start"
    }
    if cmd and (update.message.text or "").strip().startswith("/") and cmd not in allowed:
        raise ApplicationHandlerStop

logger.info("[FINAL FIX] Entry-point moved to bottom, key aliases added, and group guard widened.")


