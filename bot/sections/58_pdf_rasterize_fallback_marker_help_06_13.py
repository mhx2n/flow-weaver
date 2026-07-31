# ──────────────────────────────────────────────────────────────────────────────
# Section: 58_pdf_rasterize_fallback_marker_help_06_13
#
# Fixes:
#  (A) PDF "No module named 'fitz'" crash → overrides
#      _render_pdf_to_page_images() with a PyMuPDF → pypdfium2 → pdf2image
#      fallback chain so PDFs always rasterize regardless of which wheel
#      installed cleanly on the host (Render free tier sometimes drops
#      PyMuPDF binary wheels).
#  (B) `.howmark` / `.markhelp` command — tells the user EXACTLY how to mark
#      the correct answer on an image/PDF so Mistral OCR + the visual-marker
#      pipeline (`_visual_marked_items_from_image`) detects it reliably.
#  (C) Inline `.gen` count-picker safety net — clears stale pending entries
#      older than 10 minutes so the picker never "sticks" if the user
#      abandons it mid-flow.
# ──────────────────────────────────────────────────────────────────────────────

import os as _os58
import tempfile as _tf58
import contextlib as _cx58


def _render_pdf_pymupdf_58(pdf_path, tmp_dir):
    import fitz  # type: ignore
    paths = []
    doc = fitz.open(pdf_path)
    try:
        for idx in range(len(doc)):
            page = doc.load_page(idx)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
            out = _os58.path.join(tmp_dir, f"page_{idx+1}.png")
            pix.save(out)
            paths.append(out)
    finally:
        with _cx58.suppress(Exception):
            doc.close()
    return paths


def _render_pdf_pypdfium_58(pdf_path, tmp_dir):
    import pypdfium2 as pdfium  # type: ignore
    paths = []
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        for idx in range(len(pdf)):
            page = pdf[idx]
            pil_image = page.render(scale=2.0).to_pil()
            out = _os58.path.join(tmp_dir, f"page_{idx+1}.png")
            pil_image.save(out, format="PNG")
            paths.append(out)
            with _cx58.suppress(Exception):
                page.close()
    finally:
        with _cx58.suppress(Exception):
            pdf.close()
    return paths


def _render_pdf_pdf2image_58(pdf_path, tmp_dir):
    from pdf2image import convert_from_path  # type: ignore
    paths = []
    images = convert_from_path(pdf_path, dpi=170, output_folder=tmp_dir,
                               fmt="png", paths_only=True)
    for p in images:
        paths.append(str(p))
    return paths


def _render_pdf_to_page_images(pdf_path):  # noqa: F811  (override section 31)
    tmp_dir = _tf58.mkdtemp(prefix="probaho_pdf_pages_v58_")
    last_err = None
    for fn in (_render_pdf_pymupdf_58, _render_pdf_pypdfium_58, _render_pdf_pdf2image_58):
        try:
            paths = fn(pdf_path, tmp_dir)
            if paths:
                return paths
        except Exception as e:
            last_err = e
            continue
    with _cx58.suppress(Exception):
        db_log("WARN", "pdf_rasterize_all_backends_failed_v58", {"error": str(last_err)})
    with _cx58.suppress(Exception):
        _os58.rmdir(tmp_dir)
    return []


# Re-export so any module that captured the old symbol picks up the new impl
globals()["_render_pdf_to_page_images"] = _render_pdf_to_page_images


# =========================================================================
# (B) .howmark / .markhelp — explain the marking convention to the user
# =========================================================================

_MARKHELP_TEXT = (
    "🎯 <b>সঠিক উত্তর মার্ক করার নিয়ম</b>\n\n"
    "ছবি বা PDF এ MCQ-এর সঠিক উত্তর Mistral OCR কে বুঝাতে যেকোনো একটা করো:\n\n"
    "<b>১) টিক / রাউন্ড মার্ক</b>\n"
    "  • সঠিক অপশনের পাশে <code>✓</code> বা <code>(✓)</code> বসাও\n"
    "  • অথবা অপশনের bullet-কে <code>(c)</code> থেকে <b>⊙c</b> / "
    "<b>●c</b> / <b>✓c</b> এ পরিবর্তন করো\n\n"
    "<b>২) হাইলাইট / কালার</b>\n"
    "  • সঠিক অপশন <b>হলুদ / সবুজ</b> হাইলাইটার দিয়ে রাঙাও\n"
    "  • অথবা <b>লাল কালি</b> দিয়ে অপশনের চারপাশে গোল দাও\n\n"
    "<b>৩) আন্ডারলাইন</b>\n"
    "  • সঠিক অপশনের নিচে <b>সরাসরি দাগ</b> দাও (squiggly নয়)\n\n"
    "<b>৪) Ans: লেখা</b>\n"
    "  • প্রশ্নের শেষে যোগ করো: <code>Ans: b</code> বা <code>উত্তর: খ</code>\n\n"
    "যেকোনো একটা থাকলেই OCR + visual-marker pipeline সেটা ধরবে এবং কুইজ "
    "জেনারেট হওয়ার সময় সেই অপশনকেই সঠিক হিসেবে মার্ক করবে।\n\n"
    "ছবি যত পরিষ্কার এবং মার্ক যত স্পষ্ট, ধরা পড়ার সম্ভাবনা তত বেশি।"
)


async def cmd_markhelp_58(update, context):
    if not update.message:
        return
    with _cx58.suppress(Exception):
        await update.message.reply_text(_MARKHELP_TEXT, parse_mode=ParseMode.HTML)


# =========================================================================
# (C) Stale pending-gen state cleanup
# =========================================================================

async def _cleanup_stale_gen_state_58(context):
    try:
        bd = context.application.bot_data
        state = bd.get("_pending_gen_state_57") or {}
        now = time.time()
        stale = [k for k, v in state.items() if (now - float(v.get("ts") or 0)) > 600]
        for k in stale:
            state.pop(k, None)
    except Exception:
        pass


# =========================================================================
# Register
# =========================================================================

if "build_app" in globals():
    _prev_build_app_58 = build_app

    def build_app() -> Application:  # noqa: F811
        app = _prev_build_app_58()
        with _cx58.suppress(Exception):
            if "_register_dual_command" in globals():
                _register_dual_command(app, "howmark", cmd_markhelp_58, group=-50)
                _register_dual_command(app, "markhelp", cmd_markhelp_58, group=-50)
        # Hook stale cleanup into JobQueue if available
        with _cx58.suppress(Exception):
            jq = getattr(app, "job_queue", None)
            if jq is not None:
                jq.run_repeating(_cleanup_stale_gen_state_58, interval=300, first=300,
                                 name="cleanup_stale_gen_v58")
        return app

# ===== END SECTION 58 =====