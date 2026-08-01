# ──────────────────────────────────────────────────────────────────────────────
# Section: 01_config
# Original lines: 68..188
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# =========================================================
# ✅ HARD-CODED CONFIG
# =========================================================
# BOT_TOKEN / OWNER_ID externalised to bot/config.py — see __main__.py
# (BOT_TOKEN, OWNER_ID injected into globals by runner)

# Accept a single int OR multiple IDs via tuple/list/set/comma-separated string.
def _normalize_owner_ids(raw):
    vals = []
    if isinstance(raw, int):
        vals = [raw]
    elif isinstance(raw, (tuple, list, set)):
        for v in raw:
            try:
                iv = int(str(v).strip())
                if iv > 0:
                    vals.append(iv)
            except Exception:
                pass
    elif isinstance(raw, str):
        for part in raw.replace(' ', '').split(','):
            if not part:
                continue
            try:
                iv = int(part)
                if iv > 0:
                    vals.append(iv)
            except Exception:
                pass
    dedup = []
    seen = set()
    for v in vals:
        if v not in seen:
            dedup.append(v)
            seen.add(v)
    return dedup

OWNER_IDS = tuple(_normalize_owner_ids(OWNER_ID))
OWNER_IDS_SET = set(OWNER_IDS)
OWNER_ID = OWNER_IDS[0] if OWNER_IDS else 0

def _is_owner_id(user_id) -> bool:
    try:
        return int(user_id or 0) in OWNER_IDS_SET
    except Exception:
        return False

OWNER_CONTACT = "@Your_Himus"
BOT_BRAND = "প্রবাহ"

DB_PATH = "probaho_bot.sqlite3"
MAX_BUFFERED_QUESTIONS = 500
POST_DELAY_SECONDS = 0.8
BROADCAST_DELAY_SECONDS = 0.05

START_TIME = time.time()  # process start time (uptime)

# ---------------------------
# GEMINI (Google AI Studio) — Image→Quiz extraction (HARDCODED)
# ---------------------------
# ⚠️ Security note: If you share this file, your keys can leak.
GEMINI3_HTTP_URL = "http://127.0.0.1:5000/api/ask"  # optional
GEMINI3_HTTP_TIMEOUT = 60
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()  # set in Render Environment
# Free & stable vision model
# ---------------------------
# MODEL CONFIGURATION (Switch here easily)
# ---------------------------

# অপশন ১: ফাস্ট এবং ফ্রি (Flash) - বর্তমানে লাল দাগ বা লিমিট শেষ হলে এটি বন্ধ রাখুন
# GEMINI_MODEL_VISION = "models/gemini-2.5-flash"
# GEMINI_MODEL_TEXT = "models/gemini-2.5-flash"

# অপশন ২: পাওয়ারফুল এবং হাই লিমিট (Pro) - আপনার স্ক্রিনশট অনুযায়ী এটি এখন ব্যবহার করা উচিত
GEMINI_MODEL_VISION = "models/gemini-2.0-flash"
GEMINI_MODEL_TEXT = "models/gemini-2.0-flash"
########-------------------------------------------
GEMINI_TIMEOUT_SECONDS = 60
GEMINI_TEXT_TIMEOUT_SECONDS = 25  # faster text responses





# ---------------------------
# ✅ Solver backend preference
# ---------------------------
# If you want NO Google API key usage for /solve_on (users), keep this False.
# When False, the bot will use only Gemini3 (Gemini3.py / web session) and will NOT call Google AI Studio REST.
USE_OFFICIAL_GEMINI_REST_FALLBACK = True

# Use official Gemini REST for Generate Quiz JSON (recommended). Works even if solve REST fallback is disabled.
USE_GEMINI_REST_FOR_GENQUIZ = True
os.environ.setdefault("GEMINI_TEXT_MODELS", "models/gemini-2.0-flash,models/gemini-2.5-flash,models/gemini-3-flash")
os.environ.setdefault("GEMINI_VISION_MODELS", "models/gemini-2.0-flash,models/gemini-2.5-flash")
# ---------------------------
# ✅ Perplexity (HTTP) — Text/MCQ solving fallback (from main.py)
# ---------------------------
# Used ONLY when Gemini3 fails (prevents "REST fallback disabled" error for math/solve).
PERPLEXITY_API = "https://pplxtyai.vercel.app/api/ask"
USE_PERPLEXITY_FALLBACK = True


# ---------------------------
# ✅ DeepSeek (OpenAI-compatible) — optional third AI
# ---------------------------
# NOTE: Keep empty if you don't want DeepSeek button to work.
#DEEPSEEK_API_KEY = ""  # set in Pella Env Vars
#DEEPSEEK_BASE_URL = "https://openrouter.ai/api/v1"
#DEEPSEEK_MODEL_TEXT = "deepseek/deepseek-r1-0528:free"

SHOW_DEEPSEEK_BUTTON = False 

# ---------------------------

if not BOT_TOKEN:
    raise SystemExit("Please set BOT_TOKEN inside the code first.")
if not OWNER_IDS:
    raise SystemExit("Please set OWNER_ID as a valid numeric user id (or comma-separated ids) inside the code first.")


