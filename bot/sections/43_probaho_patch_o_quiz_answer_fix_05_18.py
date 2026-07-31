# ──────────────────────────────────────────────────────────────────────────────
# Section: 43_probaho_patch_o_quiz_answer_fix_05_18
# Original lines: 23167..23657
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════
# END PROBAHO PATCH-N
# ═══════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════
# PATCH-O 2026-05-18 — Two critical fixes:
#   1. Quiz correct_option_id: answer was always the same option (prompt
#      hardcoded "answer": 1 example + bad Perplexity "verify" step).
#   2. Cross-chat / "Reply in Another Chat" posting: .pt / .pg couldn't
#      be used from group chats, and didn't read reply_to_message polls.
#      Now works from any chat; replying to a poll posts it to target group.
# ═══════════════════════════════════════════════════════════════════════

# ── FIX 1: Correct answer selection in Generate Quiz (genquiz button) ──

def generate_quiz_items_gemini_then_verify(  # noqa: F811
    seed_question: str, seed_options: List[str]
) -> List[Dict[str, Any]]:
    """
    PATCH-O FIXED version.
    Key changes vs old version:
    - Prompt NO LONGER shows 'answer: 1' hardcoded example (Gemini was copy-pasting it).
    - Explicitly instructs that answer MUST vary and MUST be verified against content.
    - Perplexity 'verification' now only used as FALLBACK when Gemini answer is 0/invalid,
      NOT as an override that could introduce its own errors.
    """
    sq = (seed_question or "").strip()
    so = _normalize_options(seed_options or [], max_n=4)

    is_bn = _is_bangla_text(sq + " " + " ".join(so))
    lang_rule = _quiz_language_rule_block(is_bn)
    schema_expl = _quiz_schema_example_explanation(is_bn)

    prompt = (
        "Return STRICT JSON only (no markdown, no extra text).\n"
        "Task: You are given a SEED quiz question (MCQ) with options.\n"
        "1) Infer the *MICRO-TOPIC / chapter concept* strictly from the seed.\n"
        "2) Generate exactly 3 NEW MCQs ONLY from that same micro-topic.\n"
        "   - Do NOT repeat the seed question or trivially rephrase it.\n"
        "   - Keep difficulty similar to admission-style questions.\n"
        "3) Each MCQ must have 4 options and exactly ONE correct answer.\n"
        "4) Keep language consistent with the seed question language.\n"
        f"5) {lang_rule}\n"
        "6) Explanation: 1-2 lines explaining WHY the correct option is right.\n\n"
        "CRITICAL — answer field rules:\n"
        "  • 'answer' MUST be the 1-based index (1,2,3,4) of the CORRECT option.\n"
        "  • The correct option MUST actually be the right answer to the question.\n"
        "  • Each of the 3 questions may have a DIFFERENT correct answer index.\n"
        "  • Do NOT always use answer:1. Vary the position of the correct answer.\n\n"
        "JSON format (output ONLY this):\n"
        "{\n"
        '  "topic": "<major topic>",\n'
        '  "microtopic": "<micro-topic>",\n'
        '  "items": [\n'
        "    {\n"
        '      "question": "First question text",\n'
        '      "options": ["option A","option B","option C","option D"],\n'
        '      "answer": 3,\n'
        f'      "explanation": "{schema_expl}"\n'
        "    },\n"
        "    {\n"
        '      "question": "Second question text",\n'
        '      "options": ["option A","option B","option C","option D"],\n'
        '      "answer": 1,\n'
        f'      "explanation": "{schema_expl}"\n'
        "    },\n"
        "    {\n"
        '      "question": "Third question text",\n'
        '      "options": ["option A","option B","option C","option D"],\n'
        '      "answer": 4,\n'
        f'      "explanation": "{schema_expl}"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"Seed Question:\n{sq}\n\n"
        "Seed Options:\n" + "\n".join([f"{_safe_letter(i+1)}. {so[i]}" for i in range(len(so))])
    )

    raw = None
    last_err = None

    if USE_GEMINI_REST_FOR_GENQUIZ and GEMINI_API_KEY:
        try:
            raw = call_gemini_text_rest(prompt, timeout_seconds=20, force_json=True)
        except Exception as e:
            last_err = e
            raw = None

    if not raw and USE_PERPLEXITY_FALLBACK:
        try:
            raw = query_ai(prompt)
        except Exception as e:
            last_err = e
            raw = None

    if not raw:
        try:
            raw = gemini3_solve(prompt)
        except Exception as e:
            last_err = e
            raw = None

    if not raw:
        raise RuntimeError(f"Quiz generation failed: {last_err or 'all backends unavailable'}")

    schema_hint = (
        '{"microtopic":"<micro>","items":[{"question":"...","options":["...","...","...","..."],'
        '"answer":2,"explanation":"..."}]}'
    )
    try:
        data = _extract_json_strict(raw)
    except Exception:
        repaired = _repair_to_json(raw, schema_hint=schema_hint, timeout_seconds=18)
        if not repaired:
            raise
        data = repaired

    if not isinstance(data, dict):
        raise RuntimeError("Quiz generation failed.")

    items = data.get("items", []) or []
    out: List[Dict[str, Any]] = []
    for it in items[:3]:
        q = str(it.get("question", "")).strip()
        opts = _normalize_options([str(x) for x in (it.get("options", []) or [])], max_n=4)
        ans = int(it.get("answer", 0) or 0)
        expl = str(it.get("explanation", "")).strip()

        # Only call Perplexity verify if the answer is missing/invalid (0 or out of range)
        # Do NOT override a valid Gemini answer — Perplexity can itself be wrong
        if not (1 <= ans <= 4):
            try:
                ver = perplexity_solve_mcq_json(q, opts)
                vans = int((ver or {}).get("answer", 0) or 0)
                vexpl = str((ver or {}).get("explanation", "") or "").strip()
                if 1 <= vans <= 4:
                    ans = vans
                if vexpl:
                    expl = vexpl
            except Exception:
                pass

        # Final safety: if still 0/invalid, default to 1 (least harmful)
        if not (1 <= ans <= 4):
            ans = 1

        if q and opts:
            out.append({"question": q, "options": opts, "answer": ans, "explanation": expl})

    return out[:3]


# ── FIX 2: Cross-chat "Reply in Another Chat" posting ──────────────────
#
# HOW IT WORKS (matches Telegram's own "Reply in Another Chat" concept):
#   1. Admin is in Group A, sees a quiz/question message.
#   2. Long-press → "Reply in Another Chat" → choose the bot's DM (or the bot
#      is present in another group).
#   3. Bot DM receives the message with reply_to_message = the original quiz.
#   4. Admin types  .pt <group#> [topic#]  or  .pg <group#>
#      → bot extracts the replied-to poll and posts it to the saved group.
#
# Also: both .pt and .pg are now registered for GROUP chats too, so they
# can be issued directly inside a group/supergroup if the admin is there.
# ───────────────────────────────────────────────────────────────────────

def _extract_poll_from_message(msg) -> Optional[Dict[str, Any]]:
    """
    Extract quiz/poll payload dict from a Telegram Message object.
    Returns None if the message has no poll.
    """
    poll = getattr(msg, "poll", None)
    if poll is None:
        return None
    opts = [str(o.text) for o in (poll.options or [])]
    correct_id = None
    if poll.type == "quiz" and poll.correct_option_id is not None:
        correct_id = int(poll.correct_option_id) + 1  # convert to 1-based
    expl = str(poll.explanation or "").strip()
    return {
        "question": str(poll.question or "").strip(),
        "options": opts,
        "answer": correct_id or 0,
        "explanation": expl,
    }


async def _post_reply_poll_to_group(
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
    grp,
    thread_id: Optional[int],
    payload: Dict[str, Any],
) -> bool:
    """
    Post a single poll payload (extracted from reply_to_message) to a saved group.
    Returns True on success.
    """
    q = str(payload.get("question") or "").strip()
    opts = list(payload.get("options") or [])
    ans = int(payload.get("answer") or 0)
    expl = str(payload.get("explanation") or "").strip()

    group_prefix = grp.prefix or ""
    group_expl_link = grp.expl_link or ""

    if not q or len(opts) < 2:
        return False

    SEP = "\n\u200b"
    q_final = f"{group_prefix}{SEP}{q}".strip() if group_prefix else q
    if len(q_final) > 300:
        q_final = q_final[:297] + "..."

    expl_trimmed = _trim_expl_for_poll(expl, group_expl_link)

    poll_kw: Dict[str, Any] = dict(
        chat_id=grp.group_chat_id,
        question=q_final,
        options=opts,
        is_anonymous=True,
        type=Poll.QUIZ,
    )
    if thread_id:
        poll_kw["message_thread_id"] = thread_id
    if expl_trimmed:
        poll_kw["explanation"] = expl_trimmed

    # Set correct_option_id only when we know the answer
    if 1 <= ans <= len(opts):
        poll_kw["correct_option_id"] = ans - 1
    else:
        # Forwarded quizzes often hide the answer; use 0 as safe fallback
        poll_kw["correct_option_id"] = 0

    try:
        await _send_poll_with_retry(context.bot, **poll_kw)
        return True
    except Exception as e:
        logger.warning("[PATCH-O] _post_reply_poll_to_group failed: %s", e)
        return False


@require_admin
async def _cmd_pt_o(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    PATCH-O: .pt <group#> [topic_id] [keep]

    Works from PRIVATE chat AND GROUP/SUPERGROUP chat.

    If the command is sent as a reply to a message that contains a poll/quiz:
      → that poll is directly posted to the saved group topic (no buffer needed).
    Otherwise (no reply-poll):
      → posts from buffer as before.
    """
    admin_id = update.effective_user.id
    args = list(context.args or [])

    if not args or not args[0].isdigit():
        await safe_reply(update, usage_box(
            "pt", "<group#> [topic_id] [keep]",
            "Post to a saved group topic.\n"
            "Reply to a quiz/poll message to post THAT quiz directly.\n"
            "Or omit reply to post from your buffer.\n"
            "Add 'keep' to keep buffer after posting.\n"
            "Works from any chat (DM, group, channel)."
        ))
        return

    group_serial = int(args[0])
    grp = _sg_get(group_serial, admin_id)
    if not grp:
        await warn_html(update, "Group Not Found",
            f"Group #{group_serial} not found. Use <code>.listgroups</code>.")
        return

    topics = _gt_list(grp.id)
    topic_id: Optional[int] = None
    keep = False
    for a in args[1:]:
        if a.lower() == 'keep':
            keep = True
        elif a.isdigit():
            topic_id = int(a)

    # Resolve thread_id
    thread_id: Optional[int] = None
    if topic_id is not None:
        topic = _gt_get(topic_id)
        if not topic or topic.group_id != grp.id:
            await warn_html(update, "Topic Not Found",
                f"Topic #{topic_id} not found under group #{group_serial}.")
            return
        thread_id = topic.thread_id
        topic_name = topic.topic_name
    else:
        topic_name = "(main)"

    # ── Check for reply_to_message with a poll ───────────────────────────
    replied = getattr(update.message, "reply_to_message", None) if update.message else None
    reply_payload = _extract_poll_from_message(replied) if replied else None

    if reply_payload:
        # "Reply in Another Chat" flow: post the replied-to poll to saved group
        pfx_note = f"\nPrefix: <code>{h(grp.prefix)}</code>" if grp.prefix else ""
        await info_html(update, "📤 Posting Replied Quiz",
            f"Group: <b>{h(grp.title)}</b>\n"
            f"Topic: <b>{h(topic_name)}</b>\n"
            f"Source: replied message poll{pfx_note}")
        ok_flag = await _post_reply_poll_to_group(context, admin_id, grp, thread_id, reply_payload)
        if ok_flag:
            inc_admin_post(admin_id, 1)
            await ok(update, "✅ Quiz Posted",
                f"1 quiz posted to {grp.title} → {topic_name}")
        else:
            await err(update, "Post Failed",
                "Could not post the replied quiz. Make sure the bot is an admin in that group.")
        return

    # ── No reply poll — fall back to buffer ─────────────────────────────
    if topic_id is None:
        # If no topic_id and no reply, show topic list
        if topics:
            lines = [
                f"<b>#{t.id}</b>  Thread: <code>{t.thread_id}</code>  <b>{h(t.topic_name)}</b>"
                for t in topics
            ]
            await info_html(update, f"Available Topics — {h(grp.title)}",
                "\n".join(lines) +
                f"\n\nUsage: <code>.pt {group_serial} &lt;topic_id&gt;</code>\n"
                "Or reply to a quiz/poll message and use <code>.pt</code> to post it directly.")
            return

    items = buffer_list(admin_id, limit=MAX_BUFFERED_QUESTIONS)
    if not items:
        await warn(update, "Buffer Empty",
            "No quizzes in buffer. Forward polls here first, or reply to a quiz message.")
        return

    chat_id = grp.group_chat_id
    pfx_note = f"\nPrefix: <code>{h(grp.prefix)}</code>" if grp.prefix else ""
    lnk_note = f"\nExp.Link: <code>{h(grp.expl_link)}</code>" if grp.expl_link else ""

    await info_html(update, "📤 Posting to Group Topic",
        f"Group: <b>{h(grp.title)}</b>\n"
        f"Topic: <b>{h(topic_name)}</b>\n"
        f"Questions: <code>{len(items)}</code>{pfx_note}{lnk_note}")

    ok_count, fail_count, first_msg_id = await _post_buffer_to_chat(
        context, admin_id, chat_id, items,
        thread_id=thread_id,
        group_prefix=grp.prefix,
        group_expl_link=grp.expl_link,
    )

    if ok_count > 0:
        await _send_score_msg(context, admin_id, chat_id, ok_count, first_msg_id, thread_id=thread_id)

    inc_admin_post(admin_id, ok_count)
    all_ids = [row_id for (row_id, _) in items]
    if all_ids and not keep:
        buffer_remove_ids(admin_id, all_ids[:ok_count])

    await ok(update, "✅ Posting Complete",
        f"Posted: {ok_count}\nFailed: {fail_count}\nBuffer remaining: {buffer_count(admin_id)}")


@require_admin
async def _cmd_pg_o(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    PATCH-O: .pg <group#> [keep]

    Works from PRIVATE chat AND GROUP/SUPERGROUP chat.

    If the command is sent as a reply to a message with a poll/quiz:
      → that poll is directly posted to the saved group (no buffer needed).
    Otherwise:
      → posts from buffer as before.
    """
    admin_id = update.effective_user.id
    args = list(context.args or [])

    if not args or not args[0].isdigit():
        await safe_reply(update, usage_box(
            "pg", "<group#> [keep]",
            "Post to a saved group (no topic).\n"
            "Reply to a quiz/poll message to post THAT quiz directly.\n"
            "Or omit reply to post from your buffer.\n"
            "Works from any chat (DM, group, channel)."
        ))
        return

    group_serial = int(args[0])
    keep = len(args) > 1 and args[1].lower() == 'keep'
    grp = _sg_get(group_serial, admin_id)
    if not grp:
        await warn_html(update, "Group Not Found",
            f"Group #{group_serial} not found. Use <code>.listgroups</code>.")
        return

    # ── Check for reply_to_message with a poll ───────────────────────────
    replied = getattr(update.message, "reply_to_message", None) if update.message else None
    reply_payload = _extract_poll_from_message(replied) if replied else None

    if reply_payload:
        pfx_note = f"\nPrefix: <code>{h(grp.prefix)}</code>" if grp.prefix else ""
        await info_html(update, "📤 Posting Replied Quiz",
            f"Group: <b>{h(grp.title)}</b>\n"
            f"Source: replied message poll{pfx_note}")
        ok_flag = await _post_reply_poll_to_group(context, admin_id, grp, None, reply_payload)
        if ok_flag:
            inc_admin_post(admin_id, 1)
            await ok(update, "✅ Quiz Posted",
                f"1 quiz posted to {grp.title}")
        else:
            await err(update, "Post Failed",
                "Could not post the replied quiz. Check that the bot is an admin in that group.")
        return

    # ── No reply poll — fall back to buffer ─────────────────────────────
    items = buffer_list(admin_id, limit=MAX_BUFFERED_QUESTIONS)
    if not items:
        await warn(update, "Buffer Empty",
            "No quizzes in buffer. Forward polls here first, or reply to a quiz message.")
        return

    chat_id = grp.group_chat_id
    pfx_note = f"\nPrefix: <code>{h(grp.prefix)}</code>" if grp.prefix else ""
    lnk_note = f"\nExp.Link: <code>{h(grp.expl_link)}</code>" if grp.expl_link else ""

    await info_html(update, "📤 Posting to Group",
        f"Group: <b>{h(grp.title)}</b>\n"
        f"Questions: <code>{len(items)}</code>{pfx_note}{lnk_note}")

    ok_count, fail_count, first_msg_id = await _post_buffer_to_chat(
        context, admin_id, chat_id, items,
        thread_id=None,
        group_prefix=grp.prefix,
        group_expl_link=grp.expl_link,
    )

    if ok_count > 0:
        await _send_score_msg(context, admin_id, chat_id, ok_count, first_msg_id, thread_id=None)

    inc_admin_post(admin_id, ok_count)
    all_ids = [row_id for (row_id, _) in items]
    if all_ids and not keep:
        buffer_remove_ids(admin_id, all_ids[:ok_count])

    await ok(update, "✅ Posting Complete",
        f"Posted: {ok_count}\nFailed: {fail_count}\nBuffer remaining: {buffer_count(admin_id)}")


# ── PATCH-O: Register updated commands ────────────────────────────────

_prev_build_app_patch_o = build_app

def build_app() -> Application:   # noqa: F811
    app = _prev_build_app_patch_o()

    private_filter = filters.ChatType.PRIVATE
    group_filter = filters.ChatType.GROUP | filters.ChatType.SUPERGROUP
    any_chat_filter = private_filter | group_filter  # works from DM, group, supergroup

    # Override .pt and .pg with PATCH-O versions, registered for ALL chat types
    override_cmds = [
        ("pt",  _cmd_pt_o),
        ("pg",  _cmd_pg_o),
    ]
    for alias, callback in override_cmds:
        # Remove any previously registered handlers for these commands to avoid duplicates
        for gid, handler_list in list(app.handlers.items()):
            to_del = [
                hh for hh in list(handler_list)
                if isinstance(hh, (CommandHandler, MessageHandler))
                and hasattr(hh, 'commands')
                and alias in (hh.commands or set())
            ]
            for hh in to_del:
                with contextlib.suppress(Exception):
                    app.remove_handler(hh, group=gid)
        # Re-register for any chat type
        with contextlib.suppress(Exception):
            _register_dual_command(app, alias, callback, any_chat_filter)

    logger.info("[PATCH-O] Registered .pt .pg for any-chat (private+group). Cross-chat reply-poll posting enabled.")
    return app


logger.info("[PATCH-O 2026-05-18] Fix: quiz answer always same option + cross-chat Reply-in-Another-Chat posting.")
