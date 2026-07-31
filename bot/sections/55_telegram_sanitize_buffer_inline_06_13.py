# ──────────────────────────────────────────────────────────────────────────────
# Section: 55_telegram_sanitize_buffer_inline_06_13
# Fixes (all errorless / no-ops on failure):
#   1) Sanitize LaTeX-ish tokens (sqrt{}, hat{}, vec{}, &amp;, Rightarrow,
#      leftharpoons, begin{vmatrix}, text{}, frac{}, etc.) to clean
#      Telegram-friendly plain text — applied ONLY when sending polls.
#      CSV export keeps the raw LaTeX-style text (untouched buffer).
#   2) Do NOT auto-clear buffer after channel post — manual /clear via
#      the action card's 🧹 Clear Buffer button only.
#   3) "🔁 More Generate (+5)" edits the same offer card INLINE — no
#      flood of "More from Page 1" messages. Counts accumulate.
#   4) Stronger MCQ-extraction hint for right-column / side-box answers
#      (e.g. a lone "(b)" on the same row as the question end).
# DO NOT import this file directly — exec'd in shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────


# =========================================================================
# 1) Telegram-friendly text sanitizer (LaTeX / HTML-entity / token cleanup)
# =========================================================================

_GREEK_MAP = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
    "Alpha": "Α", "Beta": "Β", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ",
    "Lambda": "Λ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Omega": "Ω",
}

_SYMBOL_MAP = {
    "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔",
    "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔",
    "leftharpoons": "⇌", "rightharpoons": "⇌",
    "rightleftharpoons": "⇌", "leftrightharpoons": "⇌",
    "times": "×", "div": "÷", "cdot": "·", "ast": "∗",
    "pm": "±", "mp": "∓",
    "leq": "≤", "geq": "≥", "neq": "≠", "approx": "≈", "equiv": "≡",
    "ll": "≪", "gg": "≫",
    "infty": "∞", "partial": "∂", "nabla": "∇",
    "int": "∫", "sum": "Σ", "prod": "∏",
    "in": "∈", "notin": "∉", "subset": "⊂", "supset": "⊃",
    "cup": "∪", "cap": "∩", "emptyset": "∅",
    "forall": "∀", "exists": "∃",
    "to": "→", "iff": "⇔", "implies": "⇒",
    "circ": "°", "degree": "°",
    "ldots": "…", "cdots": "⋯", "vdots": "⋮", "dots": "…",
    "quad": " ", "qquad": "  ",
}

_HAT_MAP = {
    "i": "î", "j": "ĵ", "k": "k̂", "n": "n̂", "r": "r̂",
    "x": "x̂", "y": "ŷ", "z": "ẑ", "u": "û", "v": "v̂",
}


def _tg_plain_text(s: str) -> str:
    if not s:
        return ""
    t = str(s)
    # HTML entities first
    t = (t.replace("&amp;", "&")
           .replace("&lt;", "<")
           .replace("&gt;", ">")
           .replace("&quot;", '"')
           .replace("&apos;", "'")
           .replace("&nbsp;", " "))
    # Inline math delimiters $...$ and \( \)
    t = re.sub(r"\\\(|\\\)|\\\[|\\\]", "", t)
    t = re.sub(r"\$(.+?)\$", r"\1", t, flags=re.DOTALL)
    # \begin{...} ... \end{...}  → keep inner content, drop wrapper
    t = re.sub(r"\\?begin\s*\{[^}]*\}", "", t)
    t = re.sub(r"\\?end\s*\{[^}]*\}", "", t)
    # Common LaTeX wrappers
    t = re.sub(r"\\?sqrt\s*\{([^{}]*)\}", lambda m: f"√({m.group(1).strip()})", t)
    t = re.sub(r"\\?sqrt\s*\(([^()]*)\)", lambda m: f"√({m.group(1).strip()})", t)
    t = re.sub(r"\\?sqrt\s+([0-9A-Za-zα-ωΑ-Ω]+)", lambda m: f"√{m.group(1)}", t)
    t = re.sub(r"\\?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
               lambda m: f"({m.group(1).strip()})/({m.group(2).strip()})", t)
    t = re.sub(r"\\?hat\s*\{([^{}]*)\}",
               lambda m: _HAT_MAP.get(m.group(1).strip(), m.group(1).strip() + "\u0302"), t)
    t = re.sub(r"\\?vec\s*\{([^{}]*)\}", lambda m: m.group(1).strip() + "\u20d7", t)
    t = re.sub(r"\\?(?:text|mathrm|mathbf|mathit|operatorname)\s*\{([^{}]*)\}",
               lambda m: m.group(1), t)
    t = re.sub(r"\\?(?:overline|underline|bar)\s*\{([^{}]*)\}", lambda m: m.group(1), t)
    # Greek + symbols (with or without leading backslash, word-boundary safe)
    def _greek_repl(m):
        name = m.group(1)
        return _GREEK_MAP.get(name, m.group(0))
    t = re.sub(r"\\?\b(" + "|".join(re.escape(k) for k in _GREEK_MAP.keys()) + r")\b",
               _greek_repl, t)
    def _sym_repl(m):
        name = m.group(1)
        return _SYMBOL_MAP.get(name, m.group(0))
    t = re.sub(r"\\?\b(" + "|".join(re.escape(k) for k in _SYMBOL_MAP.keys()) + r")\b",
               _sym_repl, t)
    # Subscript/superscript braces  _{xyz} → _(xyz), ^{xyz} → ^(xyz)
    t = re.sub(r"_\{([^{}]*)\}", r"_(\1)", t)
    t = re.sub(r"\^\{([^{}]*)\}", r"^(\1)", t)
    # Strip any leftover \word backslash commands
    t = re.sub(r"\\([A-Za-z]+)\s*", r"\1 ", t)
    # Collapse single-token braces  {x} → x
    for _ in range(3):
        t = re.sub(r"\{([^{}]*)\}", r"\1", t)
    # Cleanup whitespace
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t).strip()
    return t


def _sanitize_item_for_poll(it: Dict[str, Any]) -> Dict[str, Any]:
    o = dict(it or {})
    for k in ("questions", "option1", "option2", "option3", "option4", "option5", "explanation"):
        if k in o and o[k] is not None:
            try:
                o[k] = _tg_plain_text(o.get(k) or "")
            except Exception:
                pass
    return o


# =========================================================================
# 1.5) OCR text → deterministic MCQ parser fallback
#      Fixes pages where OCR text is visible but AI extraction misses / shuffles
#      numbered MCQs (32,33,34...) with (a)(b)(c)(d), সমাধান:, [Ans: x].
# =========================================================================

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_OPT_LETTER_TO_ANS = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "ক": 1, "খ": 2, "গ": 3, "ঘ": 4, "ঙ": 5}


def _mcq_norm_for_match(text: str) -> str:
    try:
        s = _tg_plain_text(str(text or "")).translate(_BN_DIGITS).lower()
    except Exception:
        s = str(text or "").translate(_BN_DIGITS).lower()
    s = (s.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
           .replace("₍", "(").replace("₎", ")").replace("⁽", "(").replace("⁾", ")"))
    s = re.sub(r"[\s\u200b]+", " ", s)
    s = re.sub(r"[^0-9a-zঅ-ঔক-হড়ঢ়য়α-ω()+\-*/=<>^]+", "", s)
    return s.strip()


def _manual_mcq_blocks_from_text(text: str) -> List[Tuple[str, str]]:
    raw = str(text or "").replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    raw = raw.replace("\r", "\n")
    start_re = re.compile(r"(?m)^\s*([0-9০-৯]{1,3})\s*[.)।:-]\s+")
    starts = list(start_re.finditer(raw))
    blocks: List[Tuple[str, str]] = []
    for i, m in enumerate(starts):
        st = m.start()
        en = starts[i + 1].start() if i + 1 < len(starts) else len(raw)
        block = raw[st:en].strip()
        if re.search(r"(?i)(?:^|\n)\s*\(?[a-eকখগঘঙ]\)?\s*[.)।:-]", block):
            blocks.append((m.group(1).translate(_BN_DIGITS), block))
    return blocks


def _manual_parse_single_mcq(block_no: str, block: str) -> Optional[Dict[str, Any]]:
    b = re.sub(r"[ \t]+", " ", str(block or "")).strip()
    b = re.sub(r"^\s*[0-9০-৯]{1,3}\s*[.)।:-]\s*", "", b).strip()
    if not b:
        return None
    # Answer/explanation can be inline after সমাধান/উত্তর/Ans. Keep it, but remove from option parsing.
    ans = 0
    expl = ""
    ans_m = re.search(r"(?is)(?:সমাধান|উত্তর|সঠিক\s*উত্তর|answer|ans)\s*[:：]?\s*\(?\s*([a-eকখগঘঙ])\s*\)?\s*[;।:,-]?\s*(.*)$", b)
    if ans_m:
        ans = _OPT_LETTER_TO_ANS.get(ans_m.group(1).lower(), 0)
        expl = (ans_m.group(2) or "").strip()
        b = b[:ans_m.start()].strip()
    # Right-side answer boxes like [Ans: d] may be OCR'd at the end.
    side_m = re.search(r"(?is)\[\s*ans\s*[:：]\s*([a-eকখগঘঙ])\s*\]\s*$", b)
    if side_m:
        ans = ans or _OPT_LETTER_TO_ANS.get(side_m.group(1).lower(), 0)
        b = b[:side_m.start()].strip()
    opt_re = re.compile(r"(?is)(?:^|\n|\s{2,})\(?\s*([a-eকখগঘঙ])\s*\)?\s*[.)।:-]\s*")
    matches = list(opt_re.finditer(b))
    if len(matches) < 2:
        return None
    q = b[:matches[0].start()].strip(" \n:-—–")
    opts: List[str] = []
    letters: List[str] = []
    for i, m in enumerate(matches[:5]):
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(b)
        txt = b[m.end():nxt].strip(" \n;।")
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            letters.append(m.group(1).lower())
            opts.append(txt)
    if not q or len(opts) < 2:
        return None
    if ans and ans > len(opts):
        ans = 0
    return {
        "questions": q,
        "option1": opts[0] if len(opts) > 0 else "",
        "option2": opts[1] if len(opts) > 1 else "",
        "option3": opts[2] if len(opts) > 2 else "",
        "option4": opts[3] if len(opts) > 3 else "",
        "option5": opts[4] if len(opts) > 4 else "",
        "answer": ans,
        "explanation": _hard_trim_expl(expl) if "_hard_trim_expl" in globals() else expl[:180],
        "type": 1,
        "section": 1,
        "source_no": str(block_no or ""),
        "source": "ocr_checked",
    }


def _manual_extract_mcq_items(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for no, block in _manual_mcq_blocks_from_text(text):
        try:
            it = _manual_parse_single_mcq(no, block)
            if it:
                out.append(it)
        except Exception:
            continue
    return out


def _q_no_from_item(it: Dict[str, Any]) -> str:
    no = str((it or {}).get("source_no") or "").strip().translate(_BN_DIGITS)
    if no:
        return no
    q = str((it or {}).get("questions") or "")
    m = re.match(r"\s*([0-9০-৯]{1,3})\s*[.)।:-]", q)
    return m.group(1).translate(_BN_DIGITS) if m else ""


def _merge_manual_ai_items(manual_items: List[Dict[str, Any]], ai_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = [dict(x or {}) for x in (manual_items or [])]
    used_ai = set()
    for mi in out:
        mno = _q_no_from_item(mi)
        mkey = _mcq_norm_for_match(mi.get("questions") or "")
        best_idx, best_score = -1, 0.0
        for idx, ai in enumerate(ai_items or []):
            if idx in used_ai:
                continue
            ano = _q_no_from_item(ai)
            akey = _mcq_norm_for_match(ai.get("questions") or "")
            score = 1.0 if (mno and ano and mno == ano) else SequenceMatcher(None, mkey, akey).ratio()
            if score > best_score:
                best_idx, best_score = idx, score
        if best_idx >= 0 and best_score >= 0.62:
            ai = dict(ai_items[best_idx] or {})
            used_ai.add(best_idx)
            if not int(mi.get("answer", 0) or 0) and int(ai.get("answer", 0) or 0):
                mi["answer"] = int(ai.get("answer", 0) or 0)
            if not str(mi.get("explanation") or "").strip() and str(ai.get("explanation") or "").strip():
                mi["explanation"] = _hard_trim_expl(ai.get("explanation") or "") if "_hard_trim_expl" in globals() else str(ai.get("explanation") or "")[:180]
    for idx, ai in enumerate(ai_items or []):
        if idx in used_ai:
            continue
        akey = _mcq_norm_for_match((ai or {}).get("questions") or "")
        if not akey:
            continue
        if any(SequenceMatcher(None, akey, _mcq_norm_for_match((x or {}).get("questions") or "")).ratio() >= 0.82 for x in out):
            continue
        out.append(dict(ai or {}))
    try:
        out = _dedupe_mcq_items(out)
    except Exception:
        pass
    return out


def _csv_ready_rows(items: List[Tuple[int, Dict[str, Any]]], uid: int = 0) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    explanations_enabled = True
    with contextlib.suppress(Exception):
        explanations_enabled = explain_mode_on(uid) if uid else True
    for _, raw in items or []:
        it = dict(raw or {})
        q = str(it.get("questions") or "").strip()
        e = str(it.get("explanation") or "").strip()
        with contextlib.suppress(Exception):
            q2, expl2 = split_inline_explain(q)
            q = q2.strip() or q
            if expl2 and not e:
                e = expl2.strip()
        opts = [str(it.get(f"option{i}") or "").strip() for i in range(1, 6)]
        ans = int(it.get("answer", 0) or 0)
        answer_text = opts[ans - 1] if 1 <= ans <= len(opts) else ""
        rows.append({
            "questions": q,
            "option1": opts[0] if len(opts) > 0 else "",
            "option2": opts[1] if len(opts) > 1 else "",
            "option3": opts[2] if len(opts) > 2 else "",
            "option4": opts[3] if len(opts) > 3 else "",
            "option5": opts[4] if len(opts) > 4 else "",
            "answer": ans,
            "correct_answer": {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}.get(ans, ""),
            "answer_text": answer_text,
            "explanation": _hard_trim_expl(e) if explanations_enabled else "",
            "type": it.get("type", 1),
            "section": it.get("section", 1),
        })
    return rows


_prev_send_content_page_offer_55 = _send_content_page_offer


async def _send_content_page_offer(context, chat_id: int, uid: int, page_idx: int, text: str):  # noqa: F811
    # Fast path: do not wait for AI count-estimation after OCR. The first count is
    # the checked OCR MCQ count; 🔁 More Generate creates new unique questions.
    try:
        dedupe_key = hashlib.md5((str(uid) + "|" + str(page_idx) + "|" + (text or "")[:600]).encode("utf-8", "ignore")).hexdigest()
        store = _offer_dedupe_store() if "_offer_dedupe_store" in globals() else {}
        now = time.time()
        for k in list(store.keys()):
            if now - store[k] > 600:
                store.pop(k, None)
        if dedupe_key in store:
            return
        store[dedupe_key] = now
    except Exception:
        pass
    try:
        detected = len(_manual_extract_mcq_items(text or ""))
    except Exception:
        detected = 0
    token = uuid.uuid4().hex[:10]
    counts = {"easy": 0, "medium": 0, "hard": 0, "ocr_checked": int(detected or 0)}
    _genq_store(context)[token] = {
        "uid": uid, "chat_id": chat_id, "page": page_idx, "text": text,
        "counts": counts, "seen_fp": set(), "more_added": 0, "ts": time.time(),
    }
    body = (
        f"📄 Page <code>{page_idx}</code>\n"
        f"OCR checked MCQ: <code>{int(detected or 0)}</code>\n\n"
        "Use 🔁 More Generate to create additional NEW unique MCQs from this OCR text."
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=ui_box_html(f"Generate from Page {page_idx}?", body, emoji="🧠"),
        parse_mode=ParseMode.HTML,
        reply_markup=_genq_kb(token, counts),
        disable_web_page_preview=True,
    )


# =========================================================================
# 2) Replacement cb_pba — sanitizes polls; does NOT auto-clear buffer
# =========================================================================

_prev_cb_pba_55 = cb_pba


async def cb_pba(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) < 3 or parts[0] != "pba":
        return
    action = parts[1]
    # Intercept post + csv; delegate the rest to previous impl
    if action not in ("post", "csv"):
        await _prev_cb_pba_55(update, context)
        raise ApplicationHandlerStop

    token = parts[-1]
    store = _pb_store(context)
    entry = store.get(token)
    if not entry:
        with contextlib.suppress(Exception):
            await q.answer("Expired", show_alert=False)
        raise ApplicationHandlerStop
    uid = int(entry.get("uid") or 0)
    caller = q.from_user.id if q.from_user else 0
    if caller != uid:
        with contextlib.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        raise ApplicationHandlerStop
    chat_id = int(entry.get("chat_id") or q.message.chat_id)

    if action == "csv":
        with contextlib.suppress(Exception):
            await q.answer("Exporting CSV…")
        try:
            items = buffer_list(uid, limit=99999) or []
            if not items:
                with contextlib.suppress(Exception):
                    await q.edit_message_text(ui_box_html("Buffer Empty", "Nothing to export.", emoji="📂"), parse_mode=ParseMode.HTML)
                raise ApplicationHandlerStop
            rows = _csv_ready_rows(items, uid)
            df = pd.DataFrame(rows)
            cols = ["questions", "option1", "option2", "option3", "option4", "option5", "answer", "correct_answer", "answer_text", "explanation", "type", "section"]
            for c in cols:
                if c not in df.columns:
                    df[c] = ""
            with tempfile.NamedTemporaryFile("w+b", suffix=".csv", delete=False) as f:
                path = f.name
            df[cols].to_csv(path, index=False, encoding="utf-8-sig")
            with open(path, "rb") as rf:
                await context.bot.send_document(chat_id=chat_id, document=rf, filename=f"probaho_checked_buffer_{int(time.time())}.csv", caption=f"📂 Checked CSV — {len(rows)} questions")
            with contextlib.suppress(Exception):
                os.remove(path)
        except ApplicationHandlerStop:
            raise
        except Exception as e:
            db_log("ERROR", "pba_csv_failed_v55", {"user_id": uid, "error": str(e)})
            with contextlib.suppress(Exception):
                await q.answer("CSV failed", show_alert=True)
        raise ApplicationHandlerStop

    if len(parts) < 4:
        with contextlib.suppress(Exception):
            await q.answer("Bad data")
        raise ApplicationHandlerStop
    try:
        cid = int(parts[2])
    except Exception:
        with contextlib.suppress(Exception):
            await q.answer("Bad channel")
        raise ApplicationHandlerStop
    ch = None
    try:
        ch = channel_get_by_id_for_user(uid, cid)
    except Exception:
        pass
    if not ch:
        with contextlib.suppress(Exception):
            await q.answer("Channel not found", show_alert=True)
        raise ApplicationHandlerStop
    items = buffer_list(uid, limit=MAX_BUFFERED_QUESTIONS) or []
    if not items:
        with contextlib.suppress(Exception):
            await q.answer("Buffer empty", show_alert=True)
        raise ApplicationHandlerStop
    with contextlib.suppress(Exception):
        await q.answer(f"Posting {len(items)}…")
    with contextlib.suppress(Exception):
        await q.edit_message_text(
            ui_box_html("Posting to Channel",
                        f"<b>{h(ch.title)}</b>\nPosting <code>{len(items)}</code> quiz(es)…",
                        emoji="📤"),
            parse_mode=ParseMode.HTML,
        )
    target_chat_id = ch.channel_chat_id
    _reply_kw: Dict[str, Any] = {}
    try:
        _anchor_chat, _anchor_msg = _get_topic_anchor(uid)
        if _anchor_msg:
            if _anchor_chat == target_chat_id:
                _reply_kw = _make_reply_params(_anchor_msg)
            else:
                _reply_kw = _make_reply_params(_anchor_msg, chat_id=_anchor_chat)
    except Exception:
        _reply_kw = {}

    posted = 0
    failed = 0
    ch_prefix = (getattr(ch, "prefix", "") or "").strip()
    for _, raw_it in items:
        try:
            it = _sanitize_item_for_poll(raw_it)  # Telegram-friendly only
            opts: List[str] = []
            for k in ("option1", "option2", "option3", "option4", "option5"):
                v = str(it.get(k) or "").strip()
                if v:
                    opts.append(v)
            ans = int(it.get("answer", 0) or 0)
            if not (1 <= ans <= len(opts)):
                failed += 1
                continue
            qtext = str(it.get("questions") or "").strip()
            if ch_prefix and not qtext.startswith(ch_prefix):
                qtext = f"{ch_prefix}\n{qtext}"
            expl = ""
            if explain_mode_on(uid):
                expl = _trim_expl_for_poll(str(it.get("explanation") or ""))
            kw: Dict[str, Any] = dict(
                chat_id=target_chat_id,
                question=qtext[:300],
                options=opts[:10],
                type=Poll.QUIZ,
                correct_option_id=ans - 1,
                is_anonymous=True,
                explanation=expl if expl else None,
                explanation_parse_mode=ParseMode.HTML if expl else None,
            )
            if _reply_kw:
                kw.update(_reply_kw)
            await context.bot.send_poll(**kw)
            posted += 1
            await asyncio.sleep(0.4)
        except RetryAfter as ra:
            await asyncio.sleep(float(getattr(ra, "retry_after", 2)) + 1.0)
        except Exception as e:
            failed += 1
            db_log("WARN", "pba_post_failed_v55", {"user_id": uid, "error": str(e)})
    # IMPORTANT: do NOT clear buffer — manual clear via 🧹 button only.
    with contextlib.suppress(Exception):
        await context.bot.send_message(
            chat_id=chat_id,
            text=ui_box_html(
                "✅ Posted",
                f"Channel: <b>{h(ch.title)}</b>\n"
                f"Posted: <code>{posted}</code>\n"
                f"Failed: <code>{failed}</code>\n"
                f"Buffer kept: <code>{buffer_count(uid)}</code> (use 🧹 Clear Buffer to wipe).",
                emoji="📤",
            ),
            parse_mode=ParseMode.HTML,
        )
    raise ApplicationHandlerStop


# =========================================================================
# 3) "🔁 More Generate" → inline edit of the offer card (no message flood)
# =========================================================================

_prev_cb_genq_55 = cb_genq


async def cb_genq(update: Update, context: ContextTypes.DEFAULT_TYPE):  # noqa: F811
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":")
    if len(parts) != 3 or parts[0] != "genq" or parts[1] != "mo":
        return await _prev_cb_genq_55(update, context)

    token = parts[2]
    store = _genq_store(context)
    entry = store.get(token)
    if not entry:
        with contextlib.suppress(Exception):
            await q.answer("Expired", show_alert=False)
        raise ApplicationHandlerStop
    uid = int(entry.get("uid") or 0)
    caller = q.from_user.id if q.from_user else 0
    if caller != uid:
        with contextlib.suppress(Exception):
            await q.answer("Not for you", show_alert=False)
        raise ApplicationHandlerStop
    text = str(entry.get("text") or "")
    page_idx = int(entry.get("page") or 0)
    counts = entry.get("counts") or {"easy": 0, "medium": 0, "hard": 0}
    seen: set = set(entry.get("seen_fp") or set())
    total_added_so_far = int(entry.get("more_added", 0) or 0)

    hint = ""
    if seen:
        hint = ("\n\n[STRICT: generate ONLY NEW unique MCQs, do NOT repeat any prior "
                "question, vary angle/sub-topic/wording.]")
    seed_text = (text + hint)[:6000]

    with contextlib.suppress(Exception):
        await q.answer("Generating more…")
    # Inline status — edit the same card
    with contextlib.suppress(Exception):
        await q.edit_message_text(
            ui_box_html(
                f"Generating MORE — Page {page_idx}",
                f"Producing 5 new unique MCQ(s)…\nPrior unique added: <code>{total_added_so_far}</code>",
                emoji="🔁",
            ),
            parse_mode=ParseMode.HTML,
        )

    try:
        items = await _run_blocking(
            _role_of(uid),
            _generate_mcqs_from_content,
            seed_text,
            easy=2, medium=2, hard=1,
            timeout=120,
        )
    except Exception as e:
        db_log("ERROR", "genq_more_failed_v55", {"user_id": uid, "error": str(e)})
        items = []

    added = 0
    for p in items or []:
        try:
            fp = _fp_question(p)
        except Exception:
            fp = uuid.uuid4().hex
        if fp in seen:
            continue
        if buffer_count(uid) >= MAX_BUFFERED_QUESTIONS:
            break
        pp = dict(p)
        if not explain_mode_on(uid):
            pp["explanation"] = ""
        try:
            buffer_add(uid, pp)
        except Exception:
            continue
        seen.add(fp)
        added += 1
    total_added_so_far += added
    entry["seen_fp"] = seen
    entry["more_added"] = total_added_so_far
    store[token] = entry

    # Restore the offer card inline with updated stats + buttons
    body = (
        f"📄 Page <code>{page_idx}</code>\n\n"
        f"Last batch added: <code>{added}</code> new unique MCQ(s)\n"
        f"Total MORE generated: <code>{total_added_so_far}</code>\n"
        f"Buffered now: <code>{buffer_count(uid)}</code>\n\n"
        "Tap 🔁 More Generate again, or use the action card to post / export."
    )
    with contextlib.suppress(Exception):
        await q.edit_message_text(
            ui_box_html(f"Generate from Page {page_idx}?", body, emoji="🧠"),
            parse_mode=ParseMode.HTML,
            reply_markup=_genq_kb(token, counts),
        )
    raise ApplicationHandlerStop


# =========================================================================
# 4) Stronger MCQ extraction — side-column answer hint
# =========================================================================

_prev_extract_mcq_items_master_55 = _extract_mcq_items_master

_SIDE_BOX_HINT = (
    "\n[SIDE-COLUMN ANSWER HINT]\n"
    "The OCR text may include answers that originally appeared in small RIGHT-SIDE BOXES,\n"
    "or as a lone letter such as '(b)', '(d)', 'b', 'd', '⓭' on its own line\n"
    "immediately after a question's last option. Treat such isolated letters as the\n"
    "correct-answer marker for the IMMEDIATELY PRECEDING MCQ on the same row/page.\n"
    "Match them by position (top-to-bottom). Never invent an answer — only use the\n"
    "marker if visually plausible.\n"
)


def _extract_mcq_items_master(chunk_text: str) -> List[Dict[str, Any]]:  # noqa: F811
    try:
        augmented = (_SIDE_BOX_HINT + "\n" + (chunk_text or "")).strip()
    except Exception:
        augmented = chunk_text or ""
    ai_items = _prev_extract_mcq_items_master_55(augmented) or []
    try:
        manual_items = _manual_extract_mcq_items(chunk_text or "")
        if manual_items:
            return _merge_manual_ai_items(manual_items, ai_items)
    except Exception as e:
        db_log("WARN", "manual_mcq_merge_failed_v55", {"error": str(e)})
    return ai_items


# =========================================================================
# 4.5) OCR completion → action card immediately, with OCR-checked count.
#      This makes buttons appear right after detected MCQs are buffered.
# =========================================================================

_prev_run_staff_ocr_pipeline_55 = _run_staff_ocr_pipeline


async def _run_staff_ocr_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE, source_msg, local_path: str, *, source_label: str = "image") -> Dict[str, Any]:  # noqa: F811
    uid = int(update.effective_user.id if update and update.effective_user else 0)
    chat_id = int(getattr(source_msg, "chat_id", 0) or 0)
    before = 0
    with contextlib.suppress(Exception):
        before = int(buffer_count(uid))
    ctx_payload = await _prev_run_staff_ocr_pipeline_55(update, context, source_msg, local_path, source_label=source_label)
    try:
        after = int(buffer_count(uid))
        added = max(0, after - before)
        if uid > 0 and chat_id and added > 0:
            await _send_pb_action_card(context, chat_id, uid, added)
            text = str((ctx_payload or {}).get("clean_text") or (ctx_payload or {}).get("raw_markdown") or "")
            if text.strip():
                token = uuid.uuid4().hex[:10]
                counts = {"easy": 0, "medium": 0, "hard": 0, "ocr_checked": added}
                _genq_store(context)[token] = {
                    "uid": uid, "chat_id": chat_id, "page": 1, "text": text,
                    "counts": counts, "seen_fp": set(_fp_question(it) for _, it in (buffer_list(uid, limit=99999) or [])),
                    "more_added": 0, "ts": time.time(),
                }
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=ui_box_html(
                        "OCR Checked Quiz Ready",
                        f"Detected and buffered: <code>{added}</code> MCQ(s).\n"
                        "Use 🔁 More Generate to add new unique questions from the same OCR text.",
                        emoji="🧠",
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_genq_kb(token, counts),
                    disable_web_page_preview=True,
                )
    except Exception as e:
        db_log("WARN", "ocr_action_card_v55_failed", {"error": str(e)})
    return ctx_payload


# =========================================================================
# 5) Register handlers in a HIGH-PRIORITY group so they win over older ones
# =========================================================================

_prev_build_app_55 = build_app


def build_app() -> Application:
    app = _prev_build_app_55()
    # group=-1 → runs BEFORE the default group-0 handlers from sections 53/54.
    # Each new handler raises ApplicationHandlerStop after handling its case.
    with contextlib.suppress(Exception):
        app.add_handler(
            CallbackQueryHandler(cb_pba, pattern=r"^pba:(post|csv|clr|list|close):.+$"),
            group=-1,
        )
    with contextlib.suppress(Exception):
        app.add_handler(
            CallbackQueryHandler(cb_genq, pattern=r"^genq:(go|re|no|ge|gm|gh|mo):[0-9a-f]+$"),
            group=-1,
        )
    return app

# ===== END TELEGRAM SANITIZE + BUFFER + INLINE MORE-GENERATE =====