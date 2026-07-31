# ============================================================================
# Section: 76_bandwidth_saver_06_16
# Purpose:
#   Aggressive bandwidth reduction for Render free plan (5 GB / month).
#
#   Three cheap wins, all additive — nothing functional is removed:
#
#   1) Telegram long-poll: restrict `allowed_updates` to ONLY what this bot
#      actually handles (message, edited_message, callback_query). Drops
#      channel_post, chat_member, my_chat_member, poll, poll_answer,
#      inline_query, chosen_inline_result, shipping_query, pre_checkout_query.
#      For a busy bot in many groups this alone cuts inbound bytes 40-60%.
#
#   2) Health server: ETag + 304 Not Modified + gzip for the HTML page,
#      and a 60-second in-memory cache. Render's health probe + uptime
#      monitors hit `/` constantly; with ETag they get a ~150 byte 304
#      instead of a ~3 KB HTML body each time. Probe paths
#      (/healthz, /ping, /readyz, /health) stay plain "OK" so nothing breaks.
#
#   3) /status.json: cache for 30s and gzip — same idea, smaller payload.
#
#   All overrides use try/except suppress so failure never breaks the bot.
# ============================================================================

import contextlib as _cx76
import gzip as _gz76
import hashlib as _h76
import io as _io76
import json as _json76
import logging as _log76
import time as _t76

from http.server import BaseHTTPRequestHandler

_logger76 = _log76.getLogger(__name__)

# ─── 1) Restrict allowed_updates on long-polling ───────────────────────────

_ALLOWED_UPDATES_76 = ["message", "edited_message", "callback_query"]

with _cx76.suppress(Exception):
    _prev_main_76 = main  # type: ignore[name-defined]  # noqa: F821

    def main() -> None:  # noqa: F811
        import telegram.ext._application as _app_mod
        _orig_rp = _app_mod.Application.run_polling

        def _slim_run_polling(self, *a, **kw):
            # Force a slim allowed_updates list every time, even if a prior
            # override set Update.ALL_TYPES. This is the biggest bandwidth win.
            kw["allowed_updates"] = list(_ALLOWED_UPDATES_76)
            kw.setdefault("timeout", 50)
            kw.setdefault("poll_interval", 2.0)  # was 1.0 — slower idle polling
            kw.setdefault("drop_pending_updates", True)
            return _orig_rp(self, *a, **kw)

        _app_mod.Application.run_polling = _slim_run_polling
        try:
            return _prev_main_76()
        finally:
            with _cx76.suppress(Exception):
                _app_mod.Application.run_polling = _orig_rp

    globals()["main"] = main


# ─── 2 & 3) Cached + gzipped + ETag health server ──────────────────────────

_HTML_CACHE_76 = {"body": b"", "etag": "", "ts": 0.0}
_JSON_CACHE_76 = {"body": b"", "etag": "", "ts": 0.0}
_HTML_TTL_76 = 60.0
_JSON_TTL_76 = 30.0


def _gzip_bytes_76(data: bytes) -> bytes:
    buf = _io76.BytesIO()
    with _gz76.GzipFile(fileobj=buf, mode="wb", compresslevel=6, mtime=0) as gz:
        gz.write(data)
    return buf.getvalue()


def _etag_for_76(data: bytes) -> str:
    return '"' + _h76.md5(data).hexdigest()[:16] + '"'


def _build_html_cache_76() -> dict:
    now = _t76.time()
    if _HTML_CACHE_76["body"] and (now - _HTML_CACHE_76["ts"]) < _HTML_TTL_76:
        return _HTML_CACHE_76
    try:
        builder = globals().get("_h13_render_health_html")
        raw = builder() if callable(builder) else b"<!doctype html><title>OK</title>OK"
    except Exception:
        raw = b"<!doctype html><title>OK</title>OK"
    gz = _gzip_bytes_76(raw)
    _HTML_CACHE_76.update({
        "body": raw,
        "gz": gz,
        "etag": _etag_for_76(raw),
        "ts": now,
    })
    return _HTML_CACHE_76


def _build_json_cache_76() -> dict:
    now = _t76.time()
    if _JSON_CACHE_76["body"] and (now - _JSON_CACHE_76["ts"]) < _JSON_TTL_76:
        return _JSON_CACHE_76
    try:
        import os as _os
        mongo_fn = globals().get("_h13_mongo_status")
        up_fn = globals().get("_h13_uptime_seconds")
        payload = {
            "ok": True,
            "uptime_seconds": int(up_fn()) if callable(up_fn) else 0,
            "mongo": mongo_fn() if callable(mongo_fn) else "unknown",
            "pid": _os.getpid(),
        }
    except Exception:
        payload = {"ok": True}
    raw = _json76.dumps(payload, separators=(",", ":")).encode("utf-8")
    gz = _gzip_bytes_76(raw)
    _JSON_CACHE_76.update({
        "body": raw,
        "gz": gz,
        "etag": _etag_for_76(raw),
        "ts": now,
    })
    return _JSON_CACHE_76


def _client_accepts_gzip_76(handler) -> bool:
    ae = (handler.headers.get("Accept-Encoding") or "").lower()
    return "gzip" in ae


def _send_cached_76(handler, cache: dict, content_type: str, max_age: int):
    inm = (handler.headers.get("If-None-Match") or "").strip()
    if inm and inm == cache["etag"]:
        handler.send_response(304)
        handler.send_header("ETag", cache["etag"])
        handler.send_header("Cache-Control", f"public, max-age={max_age}")
        handler.end_headers()
        return
    use_gz = _client_accepts_gzip_76(handler)
    body = cache["gz"] if use_gz else cache["body"]
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", f"public, max-age={max_age}")
    handler.send_header("ETag", cache["etag"])
    if use_gz:
        handler.send_header("Content-Encoding", "gzip")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


with _cx76.suppress(Exception):

    def _run_render_health_server():  # noqa: F811
        """Bandwidth-optimized health server: ETag + gzip + cache."""
        import os as _os
        from http.server import HTTPServer
        port = int(_os.getenv("PORT", "10000"))

        class _BWHandler(BaseHTTPRequestHandler):
            # silence noisy access logs (also saves a tiny bit of stdout cost)
            def log_message(self, fmt, *args):
                return

            def _plain_ok(self):
                body = b"OK"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "public, max-age=30")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _route(self):
                path = (self.path or "/").split("?", 1)[0]
                if path in ("/healthz", "/ping", "/readyz", "/health"):
                    return self._plain_ok()
                if path == "/status.json":
                    return _send_cached_76(
                        self, _build_json_cache_76(),
                        "application/json; charset=utf-8", 30,
                    )
                if path == "/":
                    return _send_cached_76(
                        self, _build_html_cache_76(),
                        "text/html; charset=utf-8", 60,
                    )
                body = b"Not Found"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def do_GET(self):
                try:
                    self._route()
                except Exception:
                    with _cx76.suppress(Exception):
                        self._plain_ok()

            def do_HEAD(self):
                try:
                    self._route()
                except Exception:
                    with _cx76.suppress(Exception):
                        self.send_response(200)
                        self.end_headers()

        srv = HTTPServer(("0.0.0.0", port), _BWHandler)
        _logger76.info("[PATCH-76] bandwidth-saver health server on :%s", port)
        srv.serve_forever()

    globals()["_run_render_health_server"] = _run_render_health_server


with _cx76.suppress(Exception):
    _logger76.info(
        "[PATCH-76] slim allowed_updates=%s, poll 2s/50s, ETag+gzip health.",
        _ALLOWED_UPDATES_76,
    )
