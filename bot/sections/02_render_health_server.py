# ──────────────────────────────────────────────────────────────────────────────
# Section: 02_render_health_server
# Original lines: 189..222
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# =========================================================
# Render Free Web Service Health Server
# =========================================================
def _run_render_health_server():
    port = int(os.getenv("PORT", "10000"))

    class _HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, format, *args):
            return

    try:
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
        server.serve_forever()
    except Exception as e:
        logging.exception("Health server failed: %s", e)


# ---------------------------
# LOGGING
# ---------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("probaho")



