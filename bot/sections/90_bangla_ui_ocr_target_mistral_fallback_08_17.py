# ──────────────────────────────────────────────────────────────────────────────
# Section 90 (2026-08-17) — professional Bangla UX, strict OCR question
# targeting, richer explanations and a fast Mistral chat fallback.
#
# Everything here is a last-load overlay.  Commands, buffers, owner workflows,
# quiz posting and the rich transport built in sections 77-89 stay intact.
#
# DO NOT import directly — exec'd in the shared namespace by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx90
import re as _re90


def _log90(message: str) -> None:
    with _cx90.suppress(Exception):
        logger.info("[S90] %s", message)  # type: ignore[name-defined]


_BN_CHAR_90 = _re90.compile(r"[\u0980-\u09FF]")
_BD_DIGITS_90 = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


# ── 1) Answer language: always Bangla explanation unless English is requested ──

_ASK_EN_90 = _re90.compile(
    r"(?:\bin\s+english\b|\benglish\s+(?:only|version|language|te|e)\b|"
    r"\b(?:write|reply|answer|explain|say|tell)\s+(?:it\s+)?in\s+english\b|"
    r"ইংরেজি(?:তে|য়)?\s*(?:বল|বলো|লিখ|লিখো|দাও|উত্তর|ব্যাখ্যা|অনুবাদ))",
    _re90.I,
)

_prev_detect_language_90 = globals().get("_detect_language_89") or globals().get("_detect_language_87")
_latest_turn_90 = globals().get("_latest_user_turn_89") or globals().get("_latest_user_turn_87")


def _detect_language_90(text: str) -> str:
    """Bangla is the house language.  English output only on an explicit ask.

    The question itself may be English — terms and formulas are preserved by the
    prompt rules below — but the explanation a student reads stays Bangla.
    """
    current = str(text or "")
    if callable(_latest_turn_90):
        with _cx90.suppress(Exception):
            current = str(_latest_turn_90(text) or current)
    if _ASK_EN_90.search(current):
        return "en"
    return "bn"


for _alias90 in ("_detect_language_87", "_detect_language_89", "_detect_language_90",
                 "_detect_lang_86", "_detect_lang_81"):
    globals()[_alias90] = _detect_language_90


_BANGLA_STYLE_RULE_90 = (
    "\n\nউত্তরের ভাষা ও উপস্থাপনা (বাধ্যতামূলক):\n"
    "• পুরো ব্যাখ্যা সাবলীল, প্রফেশনাল বাংলায় লিখবে — যেন একজন অভিজ্ঞ শিক্ষক বোঝাচ্ছেন।\n"
    "• প্রশ্ন ইংরেজিতে থাকলে প্রশ্নের মূল লেখা, পরিভাষা, সংকেত ও সূত্র ইংরেজিতেই রাখবে, "
    "কিন্তু বোঝানোর অংশ বাংলায় লিখবে।\n"
    "• রোবটিক ভঙ্গি, 'AI হিসেবে', ভূমিকা, ক্ষমাপ্রার্থনা বা অপ্রয়োজনীয় ভণিতা লিখবে না।\n"
    "• উপযুক্ত হলে টেবিল, বুলেট, উদ্ধৃতি (blockquote), স্পয়লার ও কোড ব্লক ব্যবহার করবে।\n"
    "• ধাপগুলোর মাঝে ফাঁকা লাইন রাখবে যাতে পড়তে আরাম হয়; প্রতিটি গণিত সম্পূর্ণ ও "
    "সুষম LaTeX হিসেবে $...$-এর ভেতরে লিখবে।\n"
)


def _bangla_style_prompt_90(prompt: str) -> str:
    body = str(prompt or "")
    if _detect_language_90(body) == "en":
        return body
    if "উত্তরের ভাষা ও উপস্থাপনা" in body:
        return body
    return body + _BANGLA_STYLE_RULE_90


# ── 2) Fast Mistral chat fallback (reuses the owner's stored OCR keys) ────────

_MISTRAL_CHAT_URL_90 = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODELS_90 = ("mistral-large-latest", "mistral-small-latest")


def _mistral_keys_90():
    keys = []
    getter = globals().get("get_mistral_api_keys")
    if callable(getter):
        with _cx90.suppress(Exception):
            keys = [str(k.get("api_key") or "").strip() for k in (getter() or [])]
    env_key = str(os.getenv("MISTRAL_API_KEY", "") or "").strip()  # type: ignore[name-defined]
    if env_key:
        keys.append(env_key)
    out, seen = [], set()
    for key in keys:
        if key and key not in seen:
            out.append(key)
            seen.add(key)
    return out


def _mistral_chat_text_90(prompt: str, *, timeout_seconds: int = 20) -> str:
    """Single fast chat completion.  Raises when no key/model succeeds."""
    body_prompt = str(prompt or "").strip()
    if not body_prompt:
        raise RuntimeError("empty prompt")
    keys = _mistral_keys_90()
    if not keys:
        raise RuntimeError("no mistral key configured")
    last_error = "mistral unavailable"
    for key in keys[:4]:
        for model in _MISTRAL_MODELS_90:
            try:
                resp = requests.post(  # type: ignore[name-defined]
                    _MISTRAL_CHAT_URL_90,
                    headers={
                        "Authorization": "Bearer " + key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "temperature": 0.2,
                        "max_tokens": 1800,
                        "messages": [{"role": "user", "content": body_prompt[:24000]}],
                    },
                    timeout=max(8, int(timeout_seconds or 20)),
                )
                if resp.status_code != 200:
                    last_error = "mistral http " + str(resp.status_code)
                    continue
                data = resp.json()
                text = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                if text:
                    return text
                last_error = "mistral returned empty"
            except Exception as exc:  # noqa: BLE001 — try the next key/model
                last_error = str(exc)[:180]
    raise RuntimeError(last_error)


globals()["_mistral_chat_text_90"] = _mistral_chat_text_90


_prev_try_text_90 = globals().get("_try_gemini_text_backends")
if callable(_prev_try_text_90):
    def _try_gemini_text_backends(prompt: str, *, timeout_seconds: int = 18):  # noqa: F811
        shaped = _bangla_style_prompt_90(prompt)
        try:
            return _prev_try_text_90(shaped, timeout_seconds=timeout_seconds)
        except Exception as primary_error:
            try:
                return _mistral_chat_text_90(shaped, timeout_seconds=timeout_seconds), "Mistral"
            except Exception:
                raise primary_error

    globals()["_try_gemini_text_backends"] = _try_gemini_text_backends


_prev_solve_pref_90 = globals().get("_solve_text_with_preference")
if callable(_prev_solve_pref_90):
    def _solve_text_with_preference(model: str, problem_text: str, scope: str = "private_academic"):  # noqa: F811
        try:
            return _prev_solve_pref_90(model, problem_text, scope)
        except Exception as primary_error:
            base = str(globals().get("STRICT_SYSTEM_PROMPT") or "")
            prompt = _bangla_style_prompt_90(
                (base + "\n\nCurrent user message:\n" + str(problem_text or "")).strip()
            )
            try:
                return _mistral_chat_text_90(prompt, timeout_seconds=22), "Mistral"
            except Exception:
                raise primary_error

    globals()["_solve_text_with_preference"] = _solve_text_with_preference


# ── 3) Strict OCR question targeting ─────────────────────────────────────────

_QNO_PATTERNS_90 = (
    r"\b[Qq]\.?\s*(\d{1,3})\b",
    r"\b(\d{1,3})\s*(?:নম্বর|নাম্বার|নং|number|no\.?)\b",
    r"(?:question|প্রশ্ন)\s*\.?\s*(\d{1,3})\b",
    r"^\s*(\d{1,3})\s*(?:[.।)\-]|\s|$)",
)


def _requested_qno_90(text: str) -> str:
    raw = str(text or "").translate(_BD_DIGITS_90)
    for pattern in _QNO_PATTERNS_90:
        match = _re90.search(pattern, raw, _re90.I | _re90.M)
        if match:
            return str(int(match.group(1)))
    return ""


def _item_qno_90(item) -> str:
    getter = globals().get("_item_question_no")
    value = ""
    if callable(getter):
        with _cx90.suppress(Exception):
            value = str(getter(item) or "")
    if not value:
        head = str((item or {}).get("questions") or "").translate(_BD_DIGITS_90)
        match = _re90.match(r"\s*(\d{1,3})\s*[.।)\-]", head)
        value = match.group(1) if match else ""
    return str(int(value)) if str(value).isdigit() else ""


def _numbered_block_from_text_90(full_text: str, qno: str) -> str:
    """Slice the printed question block for `qno` straight out of the OCR text."""
    text = str(full_text or "")
    if not text or not qno:
        return ""
    normalised = text.translate(_BD_DIGITS_90)
    start = None
    for match in _re90.finditer(r"(?m)^\s*0?" + _re90.escape(qno) + r"\s*[.।)\-:]", normalised):
        start = match.start()
        break
    if start is None:
        return ""
    tail = normalised[start:]
    nxt = _re90.search(r"(?m)^\s*0?\d{1,3}\s*[.।)\-:]", tail[1:])
    end = (nxt.start() + 1) if nxt else min(len(tail), 2200)
    # Map back to the original (untranslated) text so Bengali digits survive.
    return text[start:start + end].strip()


_prev_smart_pick_90 = globals().get("_smart_pick_final")


def _smart_pick_final(items, user_text):  # noqa: F811
    pool = [dict(x) for x in (items or []) if str((x or {}).get("questions") or "").strip()]
    if not pool:
        return None
    qno = _requested_qno_90(user_text)
    if qno:
        for item in pool:
            if _item_qno_90(item) == qno:
                return item
        # A requested number that is not present must NEVER silently answer a
        # different question; the prompt builder falls back to the page text.
        return None
    if callable(_prev_smart_pick_90):
        with _cx90.suppress(Exception):
            return _prev_smart_pick_90(pool, user_text)
    return None


globals()["_smart_pick_final"] = _smart_pick_final


def _pick_first_mcq_item(items, extra_instruction: str = ""):  # noqa: F811
    picked = _smart_pick_final(items, extra_instruction)
    if picked is not None:
        return picked
    if _requested_qno_90(extra_instruction):
        return None
    pool = [x for x in (items or []) if str((x or {}).get("questions") or "").strip()]
    return pool[0] if pool else None


globals()["_pick_first_mcq_item"] = _pick_first_mcq_item


def _ocr_answer_prompt_90(ocr_ctx, user_question: str, previous_answer: str = "") -> str:
    ctx = dict(ocr_ctx or {})
    user_q = str(user_question or "").strip()
    prev = str(previous_answer or "").strip()
    items = list(ctx.get("items") or [])
    full_text = str(ctx.get("clean_text") or ctx.get("raw_markdown") or "").strip()
    qno = _requested_qno_90(user_q)
    picked = _smart_pick_final(items, user_q)

    header = (
        "তুমি বাংলাদেশি শিক্ষার্থীদের জন্য একজন অভিজ্ঞ শিক্ষক।\n"
        "শুধু নিচের বিশ্লেষণ করা পৃষ্ঠার বিষয়বস্তু থেকেই উত্তর দেবে।\n"
    )
    if qno:
        header += (
            "লক্ষ্য প্রশ্ন: " + qno + " নম্বর — অন্য কোনো প্রশ্নের ব্যাখ্যা দেবে না।\n"
            "যদি " + qno + " নম্বর প্রশ্নটি বিষয়বস্তুতে না থাকে, তবে স্পষ্টভাবে সেটাই জানাবে।\n"
        )
    parts = [header, "শিক্ষার্থীর অনুরোধ:\n" + user_q]
    if prev:
        parts.append("আগের উত্তর (প্রসঙ্গ):\n" + prev[:1500])

    if picked:
        options = [str(picked.get("option%d" % i) or "").strip() for i in range(1, 6)]
        options = [o for o in options if o]
        letters = ["A", "B", "C", "D", "E"]
        block = "প্রশ্ন " + (_item_qno_90(picked) or qno or "") + ":\n" + str(picked.get("questions") or "").strip()
        if options:
            block += "\n\nঅপশন:\n" + "\n".join(
                letters[i] + ") " + options[i] for i in range(min(len(options), 5))
            )
        marked = int(picked.get("answer", 0) or 0)
        if 1 <= marked <= len(options):
            block += "\n\nপৃষ্ঠায় চিহ্নিত উত্তর: " + letters[marked - 1] + ") " + options[marked - 1]
        parts.append(block)
    else:
        block = _numbered_block_from_text_90(full_text, qno) if qno else ""
        if block:
            parts.append("লক্ষ্য প্রশ্নের মূল লেখা (পৃষ্ঠা থেকে হুবহু):\n" + block)
        parts.append("সম্পূর্ণ পৃষ্ঠার বিষয়বস্তু:\n" + full_text[:12000])

    parts.append(
        "যা দিতে হবে:\n"
        "১) সঠিক উত্তর (অপশন থাকলে অক্ষরসহ)।\n"
        "২) ধাপে ধাপে পূর্ণ সমাধান — প্রতিটি ধাপের মাঝে ফাঁকা লাইন।\n"
        "৩) কোন সূত্র/নীতি কেন প্রযোজ্য, তার সংক্ষিপ্ত কারণ।\n"
        "৪) বাকি অপশনগুলো কেন ভুল, আলাদা বুলেটে।\n"
    )
    return _bangla_style_prompt_90("\n\n".join(p for p in parts if p).strip())


globals()["_ocr_answer_prompt_90"] = _ocr_answer_prompt_90
globals()["_build_ocr_answer_prompt"] = _ocr_answer_prompt_90


def _build_focused_ocr_prompt(ocr_ctx, user_question, previous_answer: str = ""):  # noqa: F811
    return _ocr_answer_prompt_90(ocr_ctx, user_question, previous_answer)


globals()["_build_focused_ocr_prompt"] = _build_focused_ocr_prompt


# ── 4) Professional Bangla user-facing copy ──────────────────────────────────

_UI_BN_90 = (
    ("Mistral OCR", "ছবি বিশ্লেষণ"),
    ("OCR Temporarily Unavailable", "সেবাটি এখন সাময়িকভাবে বন্ধ"),
    ("OCR Question Failed", "ছবি বিশ্লেষণ সম্পন্ন হয়নি"),
    ("OCR Unavailable", "ছবি বিশ্লেষণ সেবা এখন বন্ধ"),
    ("Preparing OCR Answer", "ছবি বিশ্লেষণ চলছে"),
    ("Running OCR and detecting marked answers...", "ছবি বিশ্লেষণ করে চিহ্নিত উত্তর খোঁজা হচ্ছে..."),
    ("Reading the replied content and preparing AI choices...",
     "ছবিটি বিশ্লেষণ করে উত্তরের প্রস্তুতি নেওয়া হচ্ছে..."),
    ("Scanning Image", "ছবি বিশ্লেষণ"),
    ("Scanning Page", "পৃষ্ঠা বিশ্লেষণ"),
    ("Extracting text", "ছবি বিশ্লেষণ"),
    ("Extracted text", "বিশ্লেষণ করা বিষয়বস্তু"),
    ("Text extraction", "ছবি বিশ্লেষণ"),
    ("OCR", "ছবি বিশ্লেষণ"),
    ("Choose AI Model", "উত্তরদাতা বেছে নিন"),
    ("Tap a model button below to answer from the replied OCR content.",
     "নিচের যেকোনো বাটনে চাপ দিলে বিশ্লেষণ করা বিষয়বস্তু থেকে উত্তর তৈরি হবে।"),
    ("Processing", "কাজ চলছে"),
    ("Please wait", "একটু অপেক্ষা করুন"),
    ("Generating", "তৈরি হচ্ছে"),
    ("Generate Quiz", "কুইজ তৈরি করুন"),
    ("Quiz Solution", "প্রশ্নের সমাধান"),
    ("Question + Options (copyable)", "প্রশ্ন ও অপশন (কপি করা যাবে)"),
    ("AI Response", "সঠিক উত্তর"),
    ("Given Answer", "প্রদত্ত উত্তর"),
    ("Explanation (Solved)", "বিস্তারিত ব্যাখ্যা"),
    ("Explanation (From Quiz)", "প্রশ্নপত্রের ব্যাখ্যা"),
    ("Why other options are wrong", "বাকি অপশনগুলো কেন ভুল"),
    ("Unauthorized", "অনুমতি নেই"),
    ("Failed", "ব্যর্থ হয়েছে"),
    ("Done", "সম্পন্ন"),
    ("Match", "মিলেছে"),
    ("Mismatch", "মেলেনি"),
)


def _ui_bn_90(text):
    value = str(text or "")
    if not value:
        return value
    for english, bangla in _UI_BN_90:
        if english in value:
            value = value.replace(english, bangla)
    return _re90.sub(r"\s{2,}", " ", value).strip()


globals()["_ui_bn_90"] = _ui_bn_90


_prev_proc_start_90 = globals().get("_processing_start")
_prev_proc_update_90 = globals().get("_processing_update")

if callable(_prev_proc_start_90):
    async def _processing_start(msg, title: str, detail: str):  # noqa: F811
        return await _prev_proc_start_90(msg, _ui_bn_90(title), _ui_bn_90(detail))

    globals()["_processing_start"] = _processing_start

if callable(_prev_proc_update_90):
    async def _processing_update(proc_msg, title: str, detail: str):  # noqa: F811
        return await _prev_proc_update_90(proc_msg, _ui_bn_90(title), _ui_bn_90(detail))

    globals()["_processing_update"] = _processing_update


def _wrap_notice_90(name, translate_body: bool):
    original = globals().get(name)
    if not callable(original):
        return

    async def wrapper(update, title, body, *args, **kwargs):
        return await original(update, _ui_bn_90(title),
                              _ui_bn_90(body) if translate_body else body,
                              *args, **kwargs)

    globals()[name] = wrapper


for _name90 in ("ok", "warn", "err"):
    _wrap_notice_90(_name90, True)
for _name90 in ("ok_html", "warn_html", "err_html", "info_html"):
    _wrap_notice_90(_name90, False)


# ── 5) Bigger, airier quiz solution card in Bangla ───────────────────────────

def _space_explanation_90(text: str) -> str:
    body = str(text or "").strip()
    if not body:
        return ""
    body = _re90.sub(r"\s*\n\s*", "\n", body)
    body = _re90.sub(r"(?m)^\s*[-*•]\s*", "• ", body)
    lines = [line.strip() for line in body.split("\n") if line.strip()]
    return "\n\n".join(lines)


globals()["_space_explanation_90"] = _space_explanation_90


_prev_solution_card_90 = globals().get("_format_user_poll_solution")


def _format_user_poll_solution(question, options, model_ans, official_ans,  # noqa: F811
                               model_expl, official_expl, why_not, conf):
    opts = [str(o or "").strip() for o in (options or []) if str(o or "").strip()][:5]
    letter = globals().get("_safe_letter") or (lambda i: chr(64 + int(i)))
    escape = globals().get("h") or (lambda v: str(v))
    copy_block = ""
    builder = globals().get("_copyable_quiz_block")
    if callable(builder):
        with _cx90.suppress(Exception):
            copy_block = builder(str(question or ""), opts)

    lines = ["<b>📊 প্রশ্নের সমাধান</b>", ""]
    if copy_block:
        lines += ["<b>প্রশ্ন ও অপশন (কপি করা যাবে):</b>", copy_block, ""]
    if 1 <= int(model_ans or 0) <= len(opts):
        lines.append("<b>✅ সঠিক উত্তর:</b> <b>%s</b>) %s" % (letter(model_ans), escape(opts[int(model_ans) - 1])))
    if 0 < int(official_ans or 0) <= len(opts):
        tag = "মিলেছে" if int(official_ans) == int(model_ans or 0) else "মেলেনি"
        lines.append("<b>📌 প্রদত্ত উত্তর:</b> <b>%s</b>) %s <i>(%s)</i>"
                     % (letter(official_ans), escape(opts[int(official_ans) - 1]), tag))
    if str(model_expl or "").strip():
        lines += ["", "<b>🧠 বিস্তারিত ব্যাখ্যা</b>",
                  "<blockquote>%s</blockquote>" % escape(_space_explanation_90(model_expl))]
    if str(official_expl or "").strip():
        lines += ["", "<b>📖 প্রশ্নপত্রের ব্যাখ্যা</b>",
                  "<blockquote>%s</blockquote>" % escape(_space_explanation_90(official_expl))]
    rows = []
    for key in ("A", "B", "C", "D", "E"):
        value = str((why_not or {}).get(key) or "").strip()
        if value:
            rows.append("• <b>%s</b> — %s" % (escape(key), escape(value)))
    if rows:
        lines += ["", "<b>❌ বাকি অপশনগুলো কেন ভুল</b>", "\n\n".join(rows)]
    card = "\n".join(lines).strip()
    if len(card) > 3900 and callable(_prev_solution_card_90):
        with _cx90.suppress(Exception):
            return _prev_solution_card_90(question, options, model_ans, official_ans,
                                          model_expl, official_expl, why_not, conf)
    return card


globals()["_format_user_poll_solution"] = _format_user_poll_solution


_log90("Bangla UX + strict OCR targeting + Mistral fallback + rich explanations active")

# ===== END SECTION 90 =====