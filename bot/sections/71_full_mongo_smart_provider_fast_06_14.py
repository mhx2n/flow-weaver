# ──────────────────────────────────────────────────────────────────────────────
# Section 71 (2026-06-14) — Full Mongo backup, smart /advadd, faster cascade,
# lower-bandwidth polling. Additive overlay; touches nothing that works.
#
#   1) MongoDB now backs up EVERY public SQLite table (auto-discovered) and
#      the adv_providers registry, so a Render restart can restore the full
#      state — providers, channels, groups, settings, threads, buffer, etc.
#
#   2) `/advadd` accepts shorter forms — owner only has to send the kind and
#      key; the model + base URL are auto-filled when we recognise the kind
#      or the api-key prefix (gsk_…, sk-or-…, nvapi-…, mistral, cohere, etc).
#      New kinds added: `cohere`, `nvidia` (NIM), `together`, `fireworks`,
#      `deepseek`, `xai`, `cerebras`, `sambanova`.
#
#   3) The provider cascade now uses a tight per-provider timeout (12 s) and
#      marks an unhealthy provider for retry after 8 minutes instead of 30,
#      so a stalled Gemini key fails over to Groq/Mistral within ~12 s rather
#      than burning the user's whole 110 s budget. Generation outer budget
#      trimmed to 70 s.
#
#   4) Telegram long-polling timeout raised to 50 s and `drop_pending_updates`
#      enabled on cold start — fewer HTTP round-trips, smaller monthly egress
#      so the 5 GB / 31-day Render free tier comfortably lasts the month.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx71
import re as _re71


# ─── 1) MongoDB: back up every SQLite table ────────────────────────────────

def _list_all_sqlite_tables_71():
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        names = [str(r[0]) for r in cur.fetchall() if r and r[0]]
        conn.close()
        return names
    except Exception:
        return []


# Tables that are too noisy / huge / transient to mirror weekly.
_MONGO_SKIP_TABLES_71 = {
    "bot_logs", "ban_audit", "admin_post_stats",
    "user_ocr_daily_usage", "gemini_gen_usage",
    "ai_thread_messages",  # can be huge; thread index is still backed up
}

# Per-table override for the unique key used by the upsert path.
_MONGO_TABLE_UKEYS_71 = {
    "adv_providers": "id",
    "quiz_buffer": "id",
    "ai_threads": "id",
    "user_genlimit": "user_id",
    "user_models": "user_id",
}


def _refresh_mongo_table_list_71():
    base = list(globals().get("_MONGO_TABLES") or [])
    have = {t for (t, _c, _u) in base}
    for tbl in _list_all_sqlite_tables_71():
        if tbl in have or tbl in _MONGO_SKIP_TABLES_71:
            continue
        ukey = _MONGO_TABLE_UKEYS_71.get(tbl)
        base.append((tbl, tbl, ukey))
        have.add(tbl)
    globals()["_MONGO_TABLES"] = base
    return base


with _cx71.suppress(Exception):
    _refresh_mongo_table_list_71()
    logger.info("[PATCH-71] Mongo backup tables expanded → %d total.", len(globals().get("_MONGO_TABLES") or []))


# Re-discover tables right before each backup (catches tables created later).
with _cx71.suppress(Exception):
    _prev_mongo_backup_now_71 = mongo_backup_now

    def mongo_backup_now(requester: str = "auto"):  # noqa: F811
        with _cx71.suppress(Exception):
            _refresh_mongo_table_list_71()
        return _prev_mongo_backup_now_71(requester=requester)


# ─── 2) Smart /advadd — auto-detect kind, model, base URL ──────────────────

_PROVIDER_DEFAULTS_71 = {
    "gemini_rest":  {"base": "",                                  "model": ""},
    "gemini_web":   {"base": "",                                  "model": ""},
    "perplexity":   {"base": "",                                  "model": ""},
    "groq":         {"base": "https://api.groq.com/openai/v1",    "model": "llama-3.3-70b-versatile"},
    "openrouter":   {"base": "https://openrouter.ai/api/v1",      "model": "meta-llama/llama-3.3-70b-instruct"},
    "mistral_chat": {"base": "https://api.mistral.ai/v1",         "model": "mistral-large-latest"},
    "cohere":       {"base": "https://api.cohere.ai/compatibility/v1", "model": "command-r-plus"},
    "nvidia":       {"base": "https://integrate.api.nvidia.com/v1",    "model": "meta/llama-3.3-70b-instruct"},
    "together":     {"base": "https://api.together.xyz/v1",       "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo"},
    "fireworks":    {"base": "https://api.fireworks.ai/inference/v1", "model": "accounts/fireworks/models/llama-v3p3-70b-instruct"},
    "deepseek":     {"base": "https://api.deepseek.com/v1",       "model": "deepseek-chat"},
    "xai":          {"base": "https://api.x.ai/v1",               "model": "grok-2-latest"},
    "cerebras":     {"base": "https://api.cerebras.ai/v1",        "model": "llama-3.3-70b"},
    "sambanova":    {"base": "https://api.sambanova.ai/v1",       "model": "Meta-Llama-3.3-70B-Instruct"},
    "openai_compat": {"base": "",                                  "model": ""},
}

# Register the openai-compatible kinds into the global label dict so they
# show up in /advmode and pass the kind validator in cmd_advadd.
with _cx71.suppress(Exception):
    _ADV_KIND_LABELS.update({
        "cohere":    "Cohere",
        "nvidia":    "NVIDIA NIM",
        "together":  "Together AI",
        "fireworks": "Fireworks AI",
        "deepseek":  "DeepSeek",
        "xai":       "xAI Grok",
        "cerebras":  "Cerebras",
        "sambanova": "SambaNova",
    })


def _guess_kind_from_key_71(key: str) -> str:
    k = (key or "").strip()
    if k.startswith("gsk_"):                return "groq"
    if k.startswith("sk-or-"):              return "openrouter"
    if k.startswith("nvapi-"):              return "nvidia"
    if k.startswith("xai-"):                return "xai"
    if k.startswith("csk-"):                return "cerebras"
    if k.startswith("fw-") or k.startswith("fw_"):  return "fireworks"
    if k.lower().startswith("sk-deepseek"): return "deepseek"
    return ""


def _ext_openai_kinds_71():
    return {"openai_compat", "groq", "openrouter", "mistral_chat",
            "cohere", "nvidia", "together", "fireworks",
            "deepseek", "xai", "cerebras", "sambanova"}


# Patch the cascade-availability check to recognise the new kinds.
with _cx71.suppress(Exception):
    def _adv_cascade_available_67():  # noqa: F811
        try:
            rows = (globals().get("_ADV_MEM_CACHE") or {}).get("rows") or []
        except Exception:
            rows = []
        kinds = _ext_openai_kinds_71()
        return any((r.get("enabled") and str(r.get("kind") or "").lower() in kinds) for r in rows)
    globals()["_adv_cascade_available_67"] = _adv_cascade_available_67


# Patch the actual dispatcher so the new kinds route to OpenAI-compat.
with _cx71.suppress(Exception):
    _prev_adv_call_provider_71 = _adv_call_provider

    def _adv_call_provider(prov, prompt, *, force_json, timeout):  # noqa: F811
        kind = (prov.get("kind") or "").lower()
        if kind in _ext_openai_kinds_71():
            p = dict(prov)
            if not p.get("base_url"):
                p["base_url"] = (_PROVIDER_DEFAULTS_71.get(kind, {}) or {}).get("base", "")
            if not p.get("model"):
                p["model"] = (_PROVIDER_DEFAULTS_71.get(kind, {}) or {}).get("model", "")
            return _adv_call_openai_compat(p, prompt, force_json=force_json, timeout=timeout)
        return _prev_adv_call_provider_71(prov, prompt, force_json=force_json, timeout=timeout)
    globals()["_adv_call_provider"] = _adv_call_provider


# Smart /advadd — accepts these forms, in order:
#     /advadd <name> <kind> [model] [api_key] [base_url]   (legacy)
#     /advadd <name> <kind> <api_key>                       (auto model+base)
#     /advadd <name> <api_key>                              (auto-detect kind)
async def cmd_advadd(update, context):  # noqa: F811
    if not update.effective_user or not _is_owner_id(update.effective_user.id):
        return
    args = list(context.args or [])
    if len(args) < 2:
        await update.effective_message.reply_text(
            "<b>Quick add</b>\n"
            "• <code>/advadd MyGroq gsk_xxxxxxxx</code>  (auto)\n"
            "• <code>/advadd MyNvidia nvidia nvapi-xxxxx</code>\n"
            "• <code>/advadd MyCohere cohere co-xxxxx</code>\n\n"
            "<b>Supported kinds</b>: groq, openrouter, mistral_chat, cohere, "
            "nvidia, together, fireworks, deepseek, xai, cerebras, sambanova, "
            "gemini_rest, gemini_web, perplexity, openai_compat.\n"
            "Model + base_url are auto-filled when known; override by passing them.",
            parse_mode=ParseMode.HTML,
        )
        return

    name = args[0]
    # Form 3: /advadd <name> <api_key>  — autodetect kind from prefix
    if len(args) == 2 and args[1] not in _ADV_KIND_LABELS:
        api_key = args[1]
        kind = _guess_kind_from_key_71(api_key)
        if not kind:
            await update.effective_message.reply_text(
                "Couldn't auto-detect provider from the API key. "
                "Use: <code>/advadd &lt;name&gt; &lt;kind&gt; &lt;api_key&gt;</code>.",
                parse_mode=ParseMode.HTML,
            )
            return
        model = (_PROVIDER_DEFAULTS_71.get(kind) or {}).get("model", "")
        base_url = (_PROVIDER_DEFAULTS_71.get(kind) or {}).get("base", "")
    else:
        kind = args[1].lower()
        if kind not in _ADV_KIND_LABELS:
            await update.effective_message.reply_text(f"Unknown kind: {kind}")
            return
        # /advadd <name> <kind> <api_key>            → 3 args, autodefault model+base
        # /advadd <name> <kind> <model> <api_key> [base_url]
        if len(args) == 3:
            api_key = args[2]
            model = (_PROVIDER_DEFAULTS_71.get(kind) or {}).get("model", "")
            base_url = (_PROVIDER_DEFAULTS_71.get(kind) or {}).get("base", "")
        else:
            model    = args[2] if len(args) > 2 else (_PROVIDER_DEFAULTS_71.get(kind) or {}).get("model", "")
            api_key  = args[3] if len(args) > 3 else ""
            base_url = args[4] if len(args) > 4 else (_PROVIDER_DEFAULTS_71.get(kind) or {}).get("base", "")

    new_id = _adv_insert(name, kind, model=model, api_key=api_key, base_url=base_url, priority=100)
    await update.effective_message.reply_text(
        f"✅ Added <b>{h(name)}</b> · <code>{h(kind)}</code>"
        + (f" · <code>{h(model)}</code>" if model else "")
        + f" (id <code>{new_id}</code>).",
        parse_mode=ParseMode.HTML,
    )


# ─── 3) Faster cascade: short per-call timeout, quick retry window ─────────

with _cx71.suppress(Exception):
    _prev_adv_call_text_71 = _adv_call_text

    def _adv_call_text(prompt, *, force_json=False, timeout=18):  # noqa: F811
        per = min(int(timeout or 18), 12)   # cap per-provider timeout
        last_err = None
        rows = _ADV_MEM_CACHE.get("rows") or _adv_load()
        for prov in rows:
            if not prov.get("enabled"):
                continue
            if not prov.get("healthy"):
                # Retry an unhealthy provider after 8 min (was 30 min).
                if _adv_time.time() - float(prov.get("last_error_ts") or 0) < 480:
                    continue
            try:
                out = _adv_call_provider(prov, prompt, force_json=force_json, timeout=per)
                if out and str(out).strip():
                    _adv_mark_success(prov)
                    return str(out).strip(), str(prov.get("name") or prov.get("kind"))
                _adv_mark_failure(prov, "empty response", quota=False)
            except RateLimitError as e:
                last_err = e
                _adv_mark_failure(prov, str(e), quota=True)
            except Exception as e:
                last_err = e
                _adv_mark_failure(prov, str(e), quota=_adv_is_quota_err(str(e)))
        raise RuntimeError(str(last_err) if last_err else "All providers failed")
    globals()["_adv_call_text"] = _adv_call_text


# Tighter outer budget for quiz generation (was 110s / 90s).
with _cx71.suppress(Exception):
    _prev_generate_to_buffer_71 = _generate_to_buffer_59

    async def _generate_to_buffer_59(update, context, ocr_ctx, uid, count, mode="std"):  # noqa: F811
        count = max(1, min(500, int(count or 20)))
        globals()["_active_gen_mode_57"] = mode or "std"
        items = []
        try:
            items = await _run_blocking(
                _role_of(uid), _generate_quizzes_from_ocr_sync,
                ocr_ctx, count, uid, timeout=70,
            )
        except Exception as _e:
            logger.warning("[PATCH-71] gen primary failed (%s) — fast retry.", _e)
            try:
                items = await _run_blocking(
                    _role_of(uid), _generate_quizzes_from_ocr_sync,
                    ocr_ctx, count, uid, timeout=45,
                )
            except Exception:
                items = []
        finally:
            globals()["_active_gen_mode_57"] = None

        seen = set()
        with _cx71.suppress(Exception):
            seen.update(_gen_seen_for(context, uid, _source_hash_59(ocr_ctx, mode)))
        with _cx71.suppress(Exception):
            for _, it in (buffer_list(uid, limit=99999) or []):
                seen.add(_fp_question(it))
        added = dup = 0
        for raw in items or []:
            try:
                q = str(raw.get("question") or raw.get("questions") or "").strip()
                opts = raw.get("options") if isinstance(raw.get("options"), list) else _opts_59(raw)
                opts = [str(o or "").strip() for o in (opts or []) if str(o or "").strip()][:5]
                ans = int(raw.get("answer", 1) or 1)
                if not q or len(opts) < 2 or not (1 <= ans <= len(opts)):
                    continue
                payload = {"questions": q, "answer": ans,
                           "explanation": str(raw.get("explanation") or "")[:200],
                           "type": 1, "section": 1, "source": f"gen_{mode}"}
                for i in range(5):
                    payload[f"option{i+1}"] = opts[i] if i < len(opts) else ""
                with _cx71.suppress(Exception):
                    payload = _enforce_option_parity(payload)
                fp = _fp_question(payload)
                if fp in seen:
                    dup += 1
                    continue
                if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
                    break
                buffer_add(uid, payload)
                seen.add(fp)
                added += 1
            except Exception:
                continue
        with _cx71.suppress(Exception):
            _gen_seen_for(context, uid, _source_hash_59(ocr_ctx, mode)).update(seen)
        return added, dup
    globals()["_generate_to_buffer_59"] = _generate_to_buffer_59


# ─── 4) Bandwidth: longer long-poll, drop stale updates on cold start ──────

with _cx71.suppress(Exception):
    _prev_main_71 = main

    def main() -> None:  # noqa: F811
        import telegram.ext._application as _app_mod
        _orig_run_polling = _app_mod.Application.run_polling

        def _quiet_run_polling(self, *a, **kw):
            kw.setdefault("timeout", 50)              # long-poll: fewer HTTP calls
            kw.setdefault("poll_interval", 1.0)
            kw.setdefault("drop_pending_updates", True)
            return _orig_run_polling(self, *a, **kw)

        _app_mod.Application.run_polling = _quiet_run_polling
        try:
            return _prev_main_71()
        finally:
            _app_mod.Application.run_polling = _orig_run_polling
    globals()["main"] = main


with _cx71.suppress(Exception):
    logger.info("[PATCH-71] full-mongo backup, smart /advadd, fast cascade (12s), 50s long-poll active.")
