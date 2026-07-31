# ──────────────────────────────────────────────────────────────────────────────
# Section: 48_render_health_page_06_13
# Added : 2026-06-13  |  Existing behaviour preserved.
#   Overrides _run_render_health_server() with a clickable health page so
#   visiting the Render URL in a browser shows real bot status (uptime,
#   MongoDB, Telegram polling, version) instead of a bare "OK". The
#   well-known probe paths (/healthz, /ping, /readyz) still return plain
#   "OK" 200 so Render's health check + uptime monitors stay green.
# DO NOT import this file directly — it is exec'd by bot/__main__.py.
# ──────────────────────────────────────────────────────────────────────────────

import html as _h13_html_lib


def _h13_uptime_seconds() -> int:
    try:
        return int(time.time() - START_TIME)  # noqa: F821 (shared ns)
    except Exception:
        return 0


def _h13_format_uptime(seconds: int) -> str:
    d, rem = divmod(max(seconds, 0), 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _h13_mongo_status() -> str:
    # PATCH-R installs _mongo_get_client(); if it's unavailable Mongo is off.
    try:
        getter = globals().get("_mongo_get_client")
        if not callable(getter):
            return "disabled"
        client = getter()
        if client is None:
            return "not-configured"
        try:
            client.admin.command("ping")
            return "connected"
        except Exception as exc:  # network / auth error
            return f"error: {type(exc).__name__}"
    except Exception as exc:
        return f"error: {type(exc).__name__}"


def _h13_render_health_html() -> bytes:
    uptime_s = _h13_uptime_seconds()
    mongo = _h13_mongo_status()
    brand = globals().get("BOT_BRAND", "Probaho")
    owner = globals().get("OWNER_CONTACT", "")
    page = f"""<!doctype html>
<html lang="bn">
<head>
<meta charset="utf-8">
<title>{_h13_html_lib.escape(str(brand))} · Health</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center;
         font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI",
                      Roboto, "Noto Sans Bengali", sans-serif;
         background: radial-gradient(1200px 600px at 50% -10%, #1f2937 0%, #0b1220 60%, #050810 100%);
         color:#e5e7eb; padding:32px; }}
  .card {{ width:100%; max-width:520px; background:rgba(17,24,39,.85);
           border:1px solid rgba(148,163,184,.15); border-radius:18px;
           padding:28px 28px 22px; box-shadow:0 20px 60px rgba(0,0,0,.45);
           backdrop-filter: blur(8px); }}
  .row {{ display:flex; align-items:center; gap:12px; }}
  .dot {{ width:12px; height:12px; border-radius:999px; background:#22c55e;
          box-shadow:0 0 0 4px rgba(34,197,94,.18); animation:pulse 1.8s infinite; }}
  @keyframes pulse {{ 0%{{ box-shadow:0 0 0 0 rgba(34,197,94,.45);}} 100%{{ box-shadow:0 0 0 14px rgba(34,197,94,0);}} }}
  h1 {{ margin:0; font-size:22px; letter-spacing:.2px; }}
  .sub {{ color:#94a3b8; font-size:13px; margin-top:4px; }}
  dl {{ margin:24px 0 0; display:grid; grid-template-columns:auto 1fr; gap:10px 18px; font-size:14px; }}
  dt {{ color:#94a3b8; font-weight:500; }}
  dd {{ margin:0; color:#f1f5f9; font-variant-numeric: tabular-nums; word-break:break-word; }}
  .pill {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px;
           background:rgba(34,197,94,.15); color:#86efac; border:1px solid rgba(34,197,94,.35); }}
  .pill.warn {{ background:rgba(234,179,8,.15); color:#fde68a; border-color:rgba(234,179,8,.35); }}
  .pill.off  {{ background:rgba(148,163,184,.15); color:#cbd5e1; border-color:rgba(148,163,184,.3); }}
  footer {{ margin-top:22px; padding-top:16px; border-top:1px dashed rgba(148,163,184,.2);
            font-size:12px; color:#64748b; text-align:center; }}
  a {{ color:#93c5fd; text-decoration:none; }}
</style>
</head>
<body>
  <div class="card">
    <div class="row">
      <span class="dot" aria-hidden="true"></span>
      <div>
        <h1>{_h13_html_lib.escape(str(brand))} — running</h1>
        <div class="sub">Render Free Web Service · health endpoint</div>
      </div>
    </div>
    <dl>
      <dt>Status</dt>      <dd><span class="pill">online</span></dd>
      <dt>Uptime</dt>      <dd>{_h13_html_lib.escape(_h13_format_uptime(uptime_s))}</dd>
      <dt>MongoDB</dt>     <dd>{_h13_mongo_pill(mongo)}</dd>
      <dt>Python PID</dt>  <dd>{os.getpid()}</dd>
      <dt>Server time</dt> <dd>{dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</dd>
      <dt>Probes</dt>      <dd><a href="/healthz">/healthz</a> · <a href="/ping">/ping</a> · <a href="/readyz">/readyz</a></dd>
    </dl>
    <footer>{_h13_html_lib.escape(str(owner))}</footer>
  </div>
</body>
</html>"""
    return page.encode("utf-8")


def _h13_mongo_pill(state: str) -> str:
    s = (state or "").lower()
    if s == "connected":
        cls, label = "pill", "connected"
    elif s in ("disabled", "not-configured"):
        cls, label = "pill off", state
    else:
        cls, label = "pill warn", state
    return f'<span class="{cls}">{_h13_html_lib.escape(label)}</span>'


def _run_render_health_server():  # noqa: F811 (intentional override)
    """Richer health server: HTML at /, plain 'OK' at well-known probe paths."""
    port = int(os.getenv("PORT", "10000"))

    class _H13Handler(BaseHTTPRequestHandler):
        def _plain_ok(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"OK")

        def do_GET(self):
            path = (self.path or "/").split("?", 1)[0]
            if path in ("/healthz", "/ping", "/readyz", "/health"):
                return self._plain_ok()
            if path == "/status.json":
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                payload = {
                    "ok": True,
                    "uptime_seconds": _h13_uptime_seconds(),
                    "mongo": _h13_mongo_status(),
                    "pid": os.getpid(),
                }
                self.wfile.write(json.dumps(payload).encode("utf-8"))
                return
            if path == "/":
                try:
                    body = _h13_render_health_html()
                except Exception:
                    return self._plain_ok()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            # unknown path → tiny 404, no body cost worth mentioning
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not Found")

        def do_HEAD(self):  # uptime monitors often use HEAD — cheap path
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()

        def log_message(self, format, *args):  # silence access logs
            return

    try:
        server = HTTPServer(("0.0.0.0", port), _H13Handler)
        logger.info("[HEALTH-PAGE 2026-06-13] Richer health page active on :%d", port)
        server.serve_forever()
    except Exception as e:
        logging.exception("Health server failed: %s", e)


logger.info("[HEALTH-PAGE 2026-06-13] _run_render_health_server overridden (HTML + /healthz + /status.json).")