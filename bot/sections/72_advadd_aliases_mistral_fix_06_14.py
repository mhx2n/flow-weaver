# ──────────────────────────────────────────────────────────────────────────────
# Section 72 (2026-06-14) — /advadd friendlier:
#   • Accept short kind aliases: `mistral` → mistral_chat, `grok` → xai, etc.
#   • If the 2nd arg is an API key that we can't auto-detect (e.g. Mistral keys
#     have no fixed prefix), tell the user the exact ready-to-send command
#     with `mistral` instead of a confusing "Unknown kind".
#   • Examples in help cover Mistral too.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx72

_KIND_ALIASES_72 = {
    "mistral":    "mistral_chat",
    "mistralai":  "mistral_chat",
    "grok":       "xai",
    "x":          "xai",
    "openai":     "openai_compat",
    "llama":      "groq",
    "or":         "openrouter",
    "router":     "openrouter",
    "nv":         "nvidia",
    "nim":        "nvidia",
    "ds":         "deepseek",
    "fw":         "fireworks",
    "sn":         "sambanova",
    "cb":         "cerebras",
    "tg":         "together",
    "co":         "cohere",
    "gem":        "gemini_rest",
    "gemini":     "gemini_rest",
    "pplx":       "perplexity",
}


async def cmd_advadd(update, context):  # noqa: F811
    if not update.effective_user or not _is_owner_id(update.effective_user.id):
        return
    args = list(context.args or [])
    if len(args) < 2:
        await update.effective_message.reply_text(
            "<b>Quick add</b>\n"
            "• <code>/advadd MyGroq gsk_xxxxxxxx</code>  (auto)\n"
            "• <code>/advadd MyMistral mistral &lt;api_key&gt;</code>\n"
            "• <code>/advadd MyNvidia nvidia nvapi-xxxxx</code>\n"
            "• <code>/advadd MyCohere cohere co-xxxxx</code>\n"
            "• <code>/advadd MyDeepSeek deepseek sk-xxxxx</code>\n\n"
            "<b>Supported kinds</b>: groq, openrouter, mistral (mistral_chat), "
            "cohere, nvidia, together, fireworks, deepseek, xai (grok), "
            "cerebras, sambanova, gemini_rest, gemini_web, perplexity, openai_compat.\n"
            "Model + base_url are auto-filled when known.",
            parse_mode=ParseMode.HTML,
        )
        return

    name = args[0]
    raw_kind = (args[1] or "").lower()
    kind_resolved = _KIND_ALIASES_72.get(raw_kind, raw_kind)

    # Form: /advadd <name> <api_key>   — try to autodetect from prefix
    if len(args) == 2 and kind_resolved not in _ADV_KIND_LABELS:
        api_key = args[1]
        kind = _guess_kind_from_key_71(api_key)
        if not kind:
            await update.effective_message.reply_text(
                "Couldn't auto-detect provider from the API key.\n"
                "Send it with the kind, e.g.:\n"
                f"<code>/advadd {h(name)} mistral {h(api_key)}</code>\n"
                f"<code>/advadd {h(name)} cohere {h(api_key)}</code>\n"
                f"<code>/advadd {h(name)} openrouter {h(api_key)}</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        model = (_PROVIDER_DEFAULTS_71.get(kind) or {}).get("model", "")
        base_url = (_PROVIDER_DEFAULTS_71.get(kind) or {}).get("base", "")
    else:
        kind = kind_resolved
        if kind not in _ADV_KIND_LABELS:
            await update.effective_message.reply_text(
                f"Unknown kind: <code>{h(raw_kind)}</code>. "
                "Try <code>mistral</code>, <code>groq</code>, <code>cohere</code>, "
                "<code>nvidia</code>, <code>openrouter</code>, <code>deepseek</code>, "
                "<code>xai</code>, <code>together</code>, <code>fireworks</code>, "
                "<code>cerebras</code>, <code>sambanova</code>.",
                parse_mode=ParseMode.HTML,
            )
            return
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


with _cx72.suppress(Exception):
    logger.info("[PATCH-72] /advadd accepts short aliases (mistral, grok, etc).")
