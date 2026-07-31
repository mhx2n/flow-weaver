# ──────────────────────────────────────────────────────────────────────────────
# Section: 64_markup_revolution_bot_api_10_1_06_14
# Adds Telegram Bot API 10.1 "Markup Revolution" style rendering to AI text
# responses ONLY. Quiz answer rendering is left untouched.
#
# Telegram HTML supports a strict subset: <b><i><u><s><tg-spoiler><a>
# <code><pre><blockquote [expandable]>. Headings, lists, tables and LaTeX are
# emulated using safe equivalents so messages always parse cleanly.
# ──────────────────────────────────────────────────────────────────────────────

import re as _re64

_SUB_MAP_64 = str.maketrans("0123456789+-=()aeoxhklmnpst", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ")
_SUP_MAP_64 = str.maketrans(
    "0123456789+-=()abcdefghijklmnoprstuvwxyzABDEGHIJKLMNOPRTUVW",
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ",
)


def _h64(s):
    try:
        return h(str(s))  # noqa: F821 — provided by shared namespace
    except Exception:
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _placeholder_tokens_64(text):
    """Pull out fenced code blocks and inline code first so inline regex
    transforms don't run inside them. Returns (text_with_tokens, store)."""
    store = []

    def _save(html_fragment):
        store.append(html_fragment)
        return f"\x00CB{len(store)-1}\x00"

    # Fenced code blocks ```lang\n...\n```
    def _fence(m):
        lang = (m.group(1) or "").strip()
        body = m.group(2) or ""
        body_h = _h64(body.rstrip("\n"))
        if lang:
            return _save(f'<pre><code class="language-{_h64(lang)}">{body_h}</code></pre>')
        return _save(f"<pre>{body_h}</pre>")

    text = _re64.sub(r"```([A-Za-z0-9_+\-]*)\n([\s\S]*?)```", _fence, text)
    # Inline code `...`
    text = _re64.sub(r"`([^`\n]+)`", lambda m: _save(f"<code>{_h64(m.group(1))}</code>"), text)
    return text, store


def _restore_tokens_64(text, store):
    def _repl(m):
        idx = int(m.group(1))
        return store[idx] if 0 <= idx < len(store) else m.group(0)
    return _re64.sub(r"\x00CB(\d+)\x00", _repl, text)


def _inline_format_64(escaped):
    """Apply inline markup to an already HTML-escaped string."""
    s = escaped
    # LaTeX inline $...$ / \( ... \) -> <code>
    s = _re64.sub(r"\\\((.+?)\\\)", lambda m: f"<code>{m.group(1)}</code>", s)
    s = _re64.sub(r"(?<!\$)\$([^\$\n]{1,200}?)\$(?!\$)", lambda m: f"<code>{m.group(1)}</code>", s)
    # Links [text](url)
    def _link(m):
        txt = m.group(1)
        url = m.group(2).strip()
        if not _re64.match(r"^(https?://|tg://|mailto:)", url):
            return m.group(0)
        return f'<a href="{url}">{txt}</a>'
    s = _re64.sub(r"\[([^\]\n]+)\]\(([^)\s]+)\)", _link, s)
    # Bold **x** or __x__
    s = _re64.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", s)
    s = _re64.sub(r"(?<!_)__([^_\n]+)__(?!_)", r"<b>\1</b>", s)
    # Italic *x* / _x_  (avoid touching ** already replaced)
    s = _re64.sub(r"(?<![\*\w])\*([^*\n]+)\*(?![\*\w])", r"<i>\1</i>", s)
    s = _re64.sub(r"(?<![_\w])_([^_\n]+)_(?![_\w])", r"<i>\1</i>", s)
    # Strikethrough ~~x~~
    s = _re64.sub(r"~~([^~\n]+)~~", r"<s>\1</s>", s)
    # Spoiler ||x||
    s = _re64.sub(r"\|\|([^|\n]+)\|\|", r"<tg-spoiler>\1</tg-spoiler>", s)
    # Highlight ==x== -> bold underline (no native highlight)
    s = _re64.sub(r"==([^=\n]+)==", r"<b><u>\1</u></b>", s)
    # Superscript ^x^  (single token, no spaces)
    def _sup(m):
        return m.group(1).translate(_SUP_MAP_64)
    s = _re64.sub(r"\^([A-Za-z0-9+\-=()]{1,8})\^", _sup, s)
    # Subscript ~x~  (single token)
    def _sub(m):
        return m.group(1).translate(_SUB_MAP_64)
    s = _re64.sub(r"(?<!~)~([A-Za-z0-9+\-=()]{1,8})~(?!~)", _sub, s)
    return s


_HEAD_RE_64 = _re64.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_BULLET_RE_64 = _re64.compile(r"^[\-*•·]\s+(.*)$")
_NUM_RE_64 = _re64.compile(r"^(\d{1,3})[.)]\s+(.*)$")
_TASK_RE_64 = _re64.compile(r"^\[( |x|X|✓)\]\s+(.*)$")
_HR_RE_64 = _re64.compile(r"^[\-–—_*]{3,}$")
_TABLE_SEP_64 = _re64.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def _render_blocks_64(text):
    """Render block-level structures (blockquote, lists, tables, headings,
    dividers, LaTeX display). Returns final HTML string. `text` must already
    have fenced code + inline code replaced with placeholders."""
    lines = text.split("\n")
    out = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        # Blank line
        if not stripped:
            if out and out[-1] != "":
                out.append("")
            i += 1
            continue

        # Divider
        if _HR_RE_64.match(stripped):
            out.append("──────────")
            i += 1
            continue

        # Display LaTeX $$...$$ or \[ ... \]
        if stripped.startswith("$$") or stripped.startswith("\\["):
            end_tok = "$$" if stripped.startswith("$$") else "\\]"
            buf = [stripped.lstrip("$").lstrip("\\[")]
            i += 1
            while i < n and end_tok not in lines[i]:
                buf.append(lines[i])
                i += 1
            if i < n:
                buf.append(lines[i].split(end_tok, 1)[0])
                i += 1
            body = "\n".join([b for b in buf if b.strip()]).strip()
            out.append(f"<pre>{_h64(body)}</pre>")
            continue

        # Blockquote (>, >>, >!)
        if stripped.startswith(">"):
            expandable = False
            quote_lines = []
            while i < n and lines[i].lstrip().startswith(">"):
                ln = lines[i].lstrip()
                if ln.startswith(">!"):
                    expandable = True
                    ln = ln[2:].lstrip()
                else:
                    ln = ln[1:].lstrip()
                quote_lines.append(ln)
                i += 1
            inner = _render_blocks_64("\n".join(quote_lines))
            tag = "<blockquote expandable>" if expandable else "<blockquote>"
            out.append(f"{tag}{inner}</blockquote>")
            continue

        # Table  | a | b |
        if "|" in stripped and i + 1 < n and _TABLE_SEP_64.match(lines[i + 1]):
            table_lines = [stripped]
            i += 2  # skip header + separator
            while i < n and "|" in lines[i] and lines[i].strip():
                table_lines.append(lines[i].strip())
                i += 1
            # Render as monospace pre block
            rows = []
            for tl in table_lines:
                cells = [c.strip() for c in tl.strip().strip("|").split("|")]
                rows.append(cells)
            widths = [0] * max(len(r) for r in rows)
            for r in rows:
                for j, c in enumerate(r):
                    widths[j] = max(widths[j], len(c))
            buf = []
            for ridx, r in enumerate(rows):
                padded = " | ".join((c.ljust(widths[j]) for j, c in enumerate(r)))
                buf.append(padded)
                if ridx == 0:
                    buf.append("-+-".join("-" * w for w in widths))
            out.append(f"<pre>{_h64(chr(10).join(buf))}</pre>")
            continue

        # Heading
        m = _HEAD_RE_64.match(stripped)
        if m:
            level = len(m.group(1))
            title = _inline_format_64(_h64(m.group(2)))
            if level == 1:
                out.append(f"<b>━━ {title} ━━</b>")
            elif level == 2:
                out.append(f"<b>▎{title}</b>")
            else:
                out.append(f"<b><u>{title}</u></b>")
            i += 1
            continue

        # Task list
        m = _TASK_RE_64.match(stripped)
        if m:
            mark = "☑" if m.group(1) in ("x", "X", "✓") else "☐"
            body = _inline_format_64(_h64(m.group(2)))
            out.append(f"{mark} {body}")
            i += 1
            continue

        # Bullet list
        m = _BULLET_RE_64.match(stripped)
        if m:
            body = _inline_format_64(_h64(m.group(1)))
            out.append(f"• {body}")
            i += 1
            continue

        # Numbered list
        m = _NUM_RE_64.match(stripped)
        if m:
            num = m.group(1)
            body = _inline_format_64(_h64(m.group(2)))
            out.append(f"{num}. {body}")
            i += 1
            continue

        # Regular paragraph line
        out.append(_inline_format_64(_h64(stripped)))
        i += 1

    return "\n".join(out).strip()


def _answer_to_tg_html_64(answer, *, model_name="", preserve_code=False):
    raw = str(answer or "")
    try:
        raw = _trim_for_telegram(raw, 3500)  # noqa: F821
    except Exception:
        if len(raw) > 3500:
            raw = raw[:3497] + "..."
    try:
        raw = _sanitize_answer_text(raw)  # noqa: F821
    except Exception:
        pass

    if preserve_code:
        title = f"<b>{_h64(model_name)}</b>\n\n" if model_name else ""
        return title + f"<pre>{_h64(raw)}</pre>"

    # Light cleanup
    try:
        raw = clean_latex(raw)  # noqa: F821
    except Exception:
        pass
    raw = _re64.sub(r"\r\n?", "\n", raw)
    raw = _re64.sub(r"\n{3,}", "\n\n", raw).strip()

    tokenised, store = _placeholder_tokens_64(raw)
    body_html = _render_blocks_64(tokenised)
    body_html = _restore_tokens_64(body_html, store)
    body_html = _re64.sub(r"\n{3,}", "\n\n", body_html).strip()

    if model_name:
        body_html = f"<b>{_h64(model_name)}</b>\n\n{body_html}"
    return body_html or _h64(raw)


# Activate overrides — keep the legacy names so all upstream call sites switch
# to the new renderer automatically.
try:
    _answer_to_tg_html = _answer_to_tg_html_64  # noqa: F811
    globals()["_answer_to_tg_html"] = _answer_to_tg_html_64
    logger.info("[Markup Revolution 10.1] Rich AI HTML renderer active (headings/lists/tables/quotes/spoilers/sub-sup/LaTeX).")  # noqa: F821
except Exception:
    pass
