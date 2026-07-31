# প্রবাহ — Professional Ultra Quiz Bot

The original `Pro_mongo_finalsexxes.py` (~25,600 lines) has been split into
an ordered set of section files under `bot/sections/`. **Behaviour is
identical** — sections are executed in the original order inside a single
shared globals namespace, so the dozens of late "FINAL OVERRIDE / PATCH"
sections still monkey-patch the earlier definitions exactly as before.

## Layout

```
bot/
├── config.py            # BOT_TOKEN, OWNER_ID — edit here (or use env vars)
├── __main__.py          # Entry point — `python -m bot`
├── __init__.py
├── requirements.txt
└── sections/
    ├── 00_header_imports.py
    ├── 01_config.py
    ├── 02_render_health_server.py
    ├── …                                (48 ordered files total)
    └── 47_elevenlabs_voice_to_text_06_04.py
```

Each section file maps to a clearly named chunk of the original script —
core router, OCR patches, group/topic patches, MongoDB backup, ElevenLabs
voice-to-text, etc. The filename prefix (`00_`, `01_`, …) **is** the load
order; do not rename without renumbering.

## Configuration

`bot/config.py` reads the following env vars (with the original hard-coded
values as fallbacks):

| Env var      | Purpose                              |
| ------------ | ------------------------------------ |
| `BOT_TOKEN`  | Telegram bot token from @BotFather   |
| `OWNER_ID`   | Numeric owner id (or comma-separated)|

All other runtime settings (Gemini / Perplexity / Mistral / ElevenLabs
keys, MongoDB URI, etc.) are still read from environment variables exactly
as in the original script — see the relevant section file or use the
matching in-bot `/setkey`, `/elevenlabs`, `/mistral`, … commands.

## Install & run

```bash
pip install -r bot/requirements.txt
# from the project root:
python -m bot
```

## Deploy to Render (Free Web Service)

The repo root has `main.py`, `requirements.txt`, `Procfile`, `runtime.txt`
and `render.yaml` ready to go.

1. Push to GitHub (already done via Lovable's GitHub integration).
2. On Render → **New + → Blueprint** → pick this repo → **Apply**.
   (Or **New + → Web Service**, runtime `Python`, build
   `pip install -r requirements.txt`, start `python main.py`.)
3. In the service's **Environment** tab set:
   - `BOT_TOKEN` — your Telegram bot token
   - `OWNER_ID`  — your numeric Telegram id
   - `MONGO_URI` — `mongodb+srv://…` (only if you want PATCH-R backup)
   - any AI keys you use: `GEMINI_API_KEY`, `MISTRAL_API_KEY`,
     `ELEVENLABS_API_KEY`
4. Render assigns a public URL like `https://probaho-bot.onrender.com`.
   - **`/`** — clickable browser health page (uptime, MongoDB, version)
   - **`/healthz`** · **`/ping`** · **`/readyz`** — tiny `OK` for monitors
   - **`/status.json`** — JSON for programmatic checks

### Free-tier bandwidth (≈ 5 GB friendly)

- HTML health page is ~3 KB, JSON ~70 B, probe ~2 B. Pinging
  `/healthz` every 5 min for a whole month uses ≈ 18 KB — negligible.
- Long-polling traffic with Telegram is the dominant cost; this is
  unchanged from your original single-file bot.

### Keeping the service awake

Render Free spins the service down after 15 min of HTTP inactivity.
Point a free uptime monitor (UptimeRobot, BetterStack, cron-job.org) at
`https://<your-service>.onrender.com/healthz` every 5 min to keep the
bot polling Telegram around the clock.

### MongoDB

PATCH-R is already wired in (`bot/sections/46_probaho_patch_r_*`). Set
`MONGO_URI` (and optional `MONGO_DB_NAME`, default `probaho_bot`) in
Render's environment and the bot will resume weekly Sunday 03:00 UTC
backup syncs exactly like before. Without `MONGO_URI` Mongo backup is
inert — every other feature still works.

## Why this layout instead of `handlers/`, `services/`, `db/`?

The original script defines the same function name up to 4–5 times across
chronological "PATCH" blocks; only the last redefinition wins at runtime,
and many patches wrap earlier definitions (e.g. `_prev_main_elevenlabs = main; def main(): …; _prev_main_elevenlabs()`).
Re-architecting that into conventional `handlers/services/db` modules
without a full test harness would silently break behaviour. The
section-based layout gives you a professional, browsable file structure
*and* a 100% behaviour-preserving execution model. Once you have a test
rig in place we can iteratively collapse the patches into clean modules.

## How to edit

- Tweak a feature: edit the **last** section file that touches it (later
  sections override earlier ones — that's how the original works too).
- Add a brand-new feature: create `bot/sections/48_<your_slug>.py`. It is
  exec'd after every existing patch, so it can safely reference (and
  override) anything defined earlier.
- Never `import` a section file directly — they share globals via the
  runner, not via Python's normal import system.