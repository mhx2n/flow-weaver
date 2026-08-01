# ──────────────────────────────────────────────────────────────────────────────
# Section 69 (2026-06-14) — Fast OCR unblock overlay.
#
# Root cause fixed here:
#   Mistral OCR itself is usually fast, but the previous pipeline waited for
#   several extra AI passes after OCR:
#     • Gemini JSON MCQ extraction per page
#     • Gemini vision marked-answer scan (twice)
#     • Gemini content-count estimation cards
#   When any of those backends was slow/quota-limited, the chat stayed stuck at
#   “Running OCR — detecting questions and answers...” for 1–3 minutes.
#
# This section makes OCR-first paths return from Mistral text immediately and
# uses deterministic local parsing/counting for source MCQs. Heavy AI generation
# still happens only when the user explicitly taps/runs generation.
# DO NOT import directly — exec'd by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import base64 as _base64_69
import contextlib as _cx69
import json as _json69
import os as _os69
import re as _re69
import time as _time69
from pathlib import Path as _Path69
from typing import Any as _Any69, Dict as _Dict69, List as _List69, Tuple as _Tuple69

import requests as _requests69


_FAST_OCR_TOTAL_DEADLINE_IMAGE_69 = 48.0
_FAST_OCR_TOTAL_DEADLINE_PDF_69 = 78.0
_FAST_OCR_PER_KEY_IMAGE_69 = 22.0
_FAST_OCR_PER_KEY_PDF_69 = 34.0


def _fast_ocr_log_69(event: str, payload: _Dict69[str, _Any69] | None = None) -> None:
    with _cx69.suppress(Exception):
        db_log("INFO", event, payload or {})  # noqa: F821


def _ocr_visible_math_69(text: str) -> str:
    fn = globals().get("_math_to_visible_68") or globals().get("_light_latex_to_visible_66")
    if callable(fn):
        with _cx69.suppress(Exception):
            return str(fn(text))
    return str(text or "")


def _mistral_keys_fast_order_69() -> _List69[_Dict69[str, _Any69]]:
    keys = []
    with _cx69.suppress(Exception):
        keys = list(get_mistral_api_keys() or [])  # noqa: F821
    if not keys:
        single = str(_os69.getenv("MISTRAL_API_KEY", "") or "").strip()
        if single:
            keys = [{"id": 0, "api_key": single, "label": "env", "last_status": "", "last_error": "", "is_enabled": True}]
    good, weak = [], []
    for k in keys:
        status = str((k or {}).get("last_status") or "").lower()
        if status in {"ok", "", "ready", "migrated"}:
            good.append(k)
        else:
            weak.append(k)
    return good + weak


def _mistral_upload_file_fast_69(path: str, api_key: str, timeout_s: float) -> _Tuple69[bool, _Any69]:
    filename = _os69.path.basename(path)
    mime = _guess_mime_type(path)  # noqa: F821
    with open(path, "rb") as f:
        files = {"file": (filename, f, mime)}
        data = {"purpose": "ocr", "visibility": "user"}
        resp = _requests69.post(
            "https://api.mistral.ai/v1/files",
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
            timeout=(6, max(8, int(timeout_s))),
        )
    if resp.status_code != 200:
        return False, (resp.status_code, resp.text[:300])
    payload = resp.json()
    file_id = str(payload.get("id") or "").strip()
    if not file_id:
        return False, (500, "Mistral file upload did not return a file id.")
    return True, file_id


def _mistral_ocr_with_failover(path: str) -> _Dict69[str, _Any69]:  # noqa: F811
    keys = _mistral_keys_fast_order_69()
    if not keys:
        raise RuntimeError("No Mistral OCR key configured.")

    mime = _guess_mime_type(path)  # noqa: F821
    is_pdf = mime == "application/pdf"
    total_deadline = _FAST_OCR_TOTAL_DEADLINE_PDF_69 if is_pdf else _FAST_OCR_TOTAL_DEADLINE_IMAGE_69
    per_key_cap = _FAST_OCR_PER_KEY_PDF_69 if is_pdf else _FAST_OCR_PER_KEY_IMAGE_69
    deadline = _time69.monotonic() + total_deadline
    size_bytes = 0
    with _cx69.suppress(Exception):
        size_bytes = int(_os69.path.getsize(path) or 0)

    last_error = None
    limit_failures = []
    attempted = 0

    for key_info in keys:
        remaining = deadline - _time69.monotonic()
        if remaining <= 6:
            break
        key_id = int((key_info or {}).get("id") or 0)
        api_key = str((key_info or {}).get("api_key") or "").strip()
        if not api_key:
            continue
        attempted += 1
        this_timeout = max(8.0, min(per_key_cap, remaining - 2.0))
        try:
            if mime.startswith("image/") and size_bytes <= 6 * 1024 * 1024:
                raw_bytes = _Path69(path).read_bytes()
                b64 = _base64_69.b64encode(raw_bytes).decode("utf-8")
                doc_payload = {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"}
            else:
                ok, up_res = _mistral_upload_file_fast_69(path, api_key, min(this_timeout, 24.0))
                if not ok:
                    status_code, body = up_res
                    kind = _mistral_error_kind(int(status_code), str(body))  # noqa: F821
                    _mistral_mark_key_status(key_id, kind, f"upload: {body}")  # noqa: F821
                    last_error = RuntimeError(f"upload failed ({status_code})")
                    if kind == "limit":
                        limit_failures.append(_mask_secret(api_key))  # noqa: F821
                    continue
                doc_payload = {"type": "file", "file_id": str(up_res)}

            resp = _requests69.post(
                "https://api.mistral.ai/v1/ocr",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": MISTRAL_OCR_MODEL, "document": doc_payload, "include_image_base64": False},  # noqa: F821
                timeout=(6, int(this_timeout)),
            )
            if resp.status_code != 200:
                kind = _mistral_error_kind(resp.status_code, resp.text)  # noqa: F821
                _mistral_mark_key_status(key_id, kind, resp.text[:260])  # noqa: F821
                last_error = RuntimeError(f"ocr failed ({resp.status_code})")
                if kind == "limit":
                    limit_failures.append(_mask_secret(api_key))  # noqa: F821
                continue

            data = resp.json()
            if not isinstance(data, dict):
                _mistral_mark_key_status(key_id, "bad_response", "invalid JSON response")  # noqa: F821
                last_error = RuntimeError("Mistral OCR returned an invalid response.")
                continue
            pages = data.get("pages", []) or []
            chunks = []
            for page in pages:
                md = str((page or {}).get("markdown") or "").strip()
                if md:
                    chunks.append(md)
            raw_markdown = "\n\n".join(chunks).strip()
            _mistral_mark_key_status(key_id, "ok", "")  # noqa: F821
            _fast_ocr_log_69("fast_mistral_ocr_ok_69", {"mime": mime, "keys_attempted": attempted, "pages": len(pages)})
            return {
                "raw_markdown": raw_markdown,
                "pages": pages,
                "model": str(data.get("model") or MISTRAL_OCR_MODEL),  # noqa: F821
                "usage_info": data.get("usage_info") or {},
                "response": data,
                "used_key_mask": _mask_secret(api_key),  # noqa: F821
                "limit_failures": list(limit_failures),
            }
        except _requests69.exceptions.Timeout as e:
            _mistral_mark_key_status(key_id, "timeout", f"OCR timeout after {int(this_timeout)}s")  # noqa: F821
            last_error = e
            continue
        except Exception as e:
            _mistral_mark_key_status(key_id, "error", str(e)[:260])  # noqa: F821
            last_error = e
            continue

    if limit_failures:
        raise RuntimeError("All active Mistral keys are limited/exhausted right now. Failed keys: " + ", ".join(limit_failures[:8]))
    raise RuntimeError(str(last_error or "Mistral OCR timed out before returning text."))


globals()["_mistral_ocr_with_failover"] = _mistral_ocr_with_failover


_QSTART_69 = _re69.compile(r"^\s*([0-9\u09E6-\u09EF]{1,4})\s*[\.)\]:।-]?\s+(.+)$")
_OPT_MARK_69 = _re69.compile(r"(?<![\w\u0980-\u09FF])(?:\(([a-eA-Eকখগঘঙ])\)|([a-eA-Eকখগঘঙ])[\.)।:])\s*")
_ANS_MARK_69 = _re69.compile(r"(?i)(?:সমাধান|উত্তর|সঠিক\s*উত্তর|answer|ans|correct)\s*[:：]?\s*[\(\[]?\s*([a-eকখগঘঙ])\b")
_LETTER_TO_ANS_69 = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "ক": 1, "খ": 2, "গ": 3, "ঘ": 4, "ঙ": 5}


def _ans_letter_to_int_69(letter: str) -> int:
    return int(_LETTER_TO_ANS_69.get(str(letter or "").strip().lower(), 0) or 0)


def _clean_ocr_line_69(line: str) -> str:
    s = _ocr_visible_math_69(str(line or ""))
    s = _re69.sub(r"\s+", " ", s).strip()
    return s


def _split_fast_blocks_69(clean_text: str) -> _List69[_Tuple69[str, _List69[str]]]:
    blocks = []
    cur_qno = ""
    cur = []
    for raw in str(clean_text or "").splitlines():
        line = _clean_ocr_line_69(raw)
        if not line or _re69.match(r"^\[Page\s+\d+\]$", line, _re69.I):
            continue
        m = _QSTART_69.match(line)
        if m and cur:
            blocks.append((cur_qno, cur))
            cur = []
        if m:
            cur_qno = _normalize_question_no_token(m.group(1))  # noqa: F821
            cur.append(m.group(2).strip())
        elif cur:
            cur.append(line)
    if cur:
        blocks.append((cur_qno, cur))
    return blocks


def _extract_options_from_lines_69(lines: _List69[str]) -> _Tuple69[_List69[str], _List69[str], str, int]:
    q_lines: _List69[str] = []
    opts: _List69[str] = []
    expl_lines: _List69[str] = []
    answer = 0
    seen_opt = False
    seen_expl = False
    for line in lines:
        ans_m = _ANS_MARK_69.search(line)
        if ans_m and not answer:
            answer = _ans_letter_to_int_69(ans_m.group(1))
            seen_expl = True
        matches = list(_OPT_MARK_69.finditer(line))
        if matches and not seen_expl:
            if not seen_opt:
                prefix = line[:matches[0].start()].strip()
                if prefix:
                    q_lines.append(prefix)
            seen_opt = True
            for idx, m in enumerate(matches):
                start = m.end()
                end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
                opt = line[start:end].strip(" :-–—;।")
                if opt:
                    opts.append(opt)
            continue
        if seen_expl or ans_m:
            expl_lines.append(line)
        elif seen_opt:
            # Continuation of previous option if OCR wrapped it.
            if opts and len(line) <= 100:
                opts[-1] = (opts[-1] + " " + line).strip()
            else:
                expl_lines.append(line)
        else:
            q_lines.append(line)
    return q_lines, opts[:5], "\n".join(expl_lines).strip(), answer


def _fast_parse_mcq_block_69(qno: str, lines: _List69[str], user_id: int) -> _Dict69[str, _Any69] | None:
    if not lines:
        return None
    q_lines, opts, expl, answer = _extract_options_from_lines_69(lines)
    if len(opts) < 2:
        return None
    q = " ".join(q_lines).strip()
    if not q:
        return None
    with _cx69.suppress(Exception):
        q = clean_common(q, user_id)  # noqa: F821
    clean_opts = []
    for o in opts:
        oo = o.strip()
        with _cx69.suppress(Exception):
            oo = clean_option_text(oo)  # noqa: F821
        clean_opts.append(oo)
    clean_opts = [x for x in clean_opts if x]
    if len(clean_opts) < 2:
        return None
    if not (1 <= answer <= len(clean_opts)):
        answer = 0
    if expl:
        with _cx69.suppress(Exception):
            expl = _sanitize_quiz_explanation_text(expl)  # noqa: F821
        expl = _re69.sub(r"\s+", " ", str(expl or "")).strip()[:180]
    item = {
        "questions": q,
        "option1": clean_opts[0] if len(clean_opts) > 0 else "",
        "option2": clean_opts[1] if len(clean_opts) > 1 else "",
        "option3": clean_opts[2] if len(clean_opts) > 2 else "",
        "option4": clean_opts[3] if len(clean_opts) > 3 else "",
        "option5": clean_opts[4] if len(clean_opts) > 4 else "",
        "answer": int(answer or 0),
        "explanation": expl,
        "type": 1,
        "section": 1,
    }
    if qno:
        item["question_no"] = qno
    return item


def _extract_mcq_items_master(chunk_text: str) -> _List69[_Dict69[str, _Any69]]:  # noqa: F811
    body = _ocr_visible_math_69(str(chunk_text or "")).strip()
    if not body:
        return []
    out = []
    for qno, lines in _split_fast_blocks_69(body):
        item = _fast_parse_mcq_block_69(qno, lines, 0)
        if item:
            out.append(item)
    if not out:
        # Last-resort legacy parser is local/deterministic and cheap.
        with _cx69.suppress(Exception):
            for block in split_blocks(body):  # noqa: F821
                parsed = parse_text_block(block, 0)  # noqa: F821
                if parsed:
                    out.append(parsed)
    with _cx69.suppress(Exception):
        out = _dedupe_mcq_items(out)  # noqa: F821
    return list(out or [])[:120]


globals()["_extract_mcq_items_master"] = _extract_mcq_items_master


def _ocr_pages_to_clean_text_and_items(pages: _List69[_Dict69[str, _Any69]], user_id: int) -> _Tuple69[str, _List69[_Dict69[str, _Any69]]]:  # noqa: F811
    parts = []
    items = []
    for idx, page in enumerate(list(pages or []), start=1):
        md = str((page or {}).get("markdown") or "").strip()
        if not md:
            continue
        try:
            cleaned = _ocr_preserve_text_layout(md)  # noqa: F821
        except Exception:
            cleaned = md
        cleaned = _ocr_visible_math_69(cleaned).strip()
        if not cleaned:
            continue
        parts.append(f"[Page {idx}]\n{cleaned}")
        for it in _extract_mcq_items_master(cleaned):
            item = dict(it)
            item.setdefault("page", idx)
            items.append(item)
    clean_text = "\n\n".join(parts).strip()
    with _cx69.suppress(Exception):
        items = _assign_question_numbers_by_order(items, clean_text)  # noqa: F821
    with _cx69.suppress(Exception):
        items, _ = _merge_textual_answer_marks(items, clean_text)  # noqa: F821
    with _cx69.suppress(Exception):
        items = _drop_unclear_mcq_items(items)  # noqa: F821
    with _cx69.suppress(Exception):
        items = _dedupe_mcq_items(items)  # noqa: F821
    return clean_text, list(items or [])


globals()["_ocr_pages_to_clean_text_and_items"] = _ocr_pages_to_clean_text_and_items


def _extract_ocr_bundle_from_path(local_path: str, user_id: int) -> _Dict69[str, _Any69]:  # noqa: F811
    started = _time69.monotonic()
    ocr = _mistral_ocr_process_path(local_path)  # noqa: F821
    pages = list(ocr.get("pages") or [])
    clean_text, items = _ocr_pages_to_clean_text_and_items(pages, user_id)
    if not clean_text.strip() and str(ocr.get("raw_markdown") or "").strip():
        clean_text = _ocr_visible_math_69(str(ocr.get("raw_markdown") or "")).strip()
        items = _extract_mcq_items_master(clean_text)
    if not clean_text.strip():
        raise RuntimeError("No readable OCR text was returned from this file.")
    _fast_ocr_log_69("fast_ocr_bundle_done_69", {"seconds": round(_time69.monotonic() - started, 2), "items": len(items), "pages": len(pages)})
    return {
        "ocr": ocr,
        "clean_text": clean_text,
        "items": list(items or []),
        "visual_marked_count": 0,
        "source_extracted_count": len(items or []),
        "fast_ocr": True,
    }


globals()["_extract_ocr_bundle_from_path"] = _extract_ocr_bundle_from_path


def _estimate_generatable_counts(content_text: str) -> _Dict69[str, int]:  # noqa: F811
    """Instant heuristic; avoids an extra Gemini call immediately after OCR."""
    text = str(content_text or "").strip()
    if len(text) < 80:
        return {"easy": 0, "medium": 0, "hard": 0}
    extracted = len(_extract_mcq_items_master(text))
    if extracted >= 3:
        return {"easy": min(10, extracted), "medium": min(8, max(1, extracted // 2)), "hard": min(5, max(0, extracted // 4))}
    words = len(_re69.findall(r"[A-Za-z\u0980-\u09FF0-9]+", text))
    base = max(0, min(20, words // 85))
    return {"easy": min(8, base), "medium": min(8, max(0, base // 2)), "hard": min(4, max(0, base // 4))}


globals()["_estimate_generatable_counts"] = _estimate_generatable_counts


try:
    logger.info("[Section 69] Fast OCR unblock active: Mistral-first, local MCQ parse, no automatic Gemini post-processing.")  # noqa: F821
except Exception:
    pass