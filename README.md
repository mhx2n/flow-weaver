<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12&height=220&section=header&text=প্রবাহ%20Bot&fontSize=70&fontAlignY=38&desc=Professional%20Ultra%20Quiz%20Bot%20for%20Telegram&descAlignY=62&descSize=18&fontColor=ffffff&animation=fadeIn" alt="header" />

<a href="https://git.io/typing-svg">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=24&duration=2800&pause=900&color=22D3EE&center=true&vCenter=true&multiline=true&width=820&height=110&lines=⚡+Multi-AI+Quiz+Master+Bot;🧠+OCR+%2B+Auto+MCQ+Generation+%2B+Cascading+Failover;🚀+Render-Ready+%7C+MongoDB+Backup+%7C+Unlimited+Generation" alt="typing" />
</a>

<br/>

![Python](https://img.shields.io/badge/Python-3.11.9-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)
![Render](https://img.shields.io/badge/Render-Free%20Tier-46E3B7?style=for-the-badge&logo=render&logoColor=black)
![MongoDB](https://img.shields.io/badge/MongoDB-Backup-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![License](https://img.shields.io/badge/License-Private-FF4757?style=for-the-badge)

![Sections](https://img.shields.io/badge/dynamic-51%20Sections-8B5CF6?style=flat-square&logo=files&logoColor=white)
![AI Providers](https://img.shields.io/badge/AI%20Providers-7%2B-F59E0B?style=flat-square&logo=openai&logoColor=white)
![OCR](https://img.shields.io/badge/Mistral-OCR-FF7000?style=flat-square)
![Voice](https://img.shields.io/badge/ElevenLabs-Voice2Text-000000?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-success?style=flat-square)

</div>

---

<div align="center">
  <img src="https://user-images.githubusercontent.com/74038190/212284100-561aa473-3905-4a80-b561-0d28506553ee.gif" width="900" />
</div>

## 🌊 প্রবাহ — সংক্ষেপে

একটি **প্রফেশনাল, ৫১-সেকশনের মডুলার Telegram বট** — Render Free Web Service এ ডিপ্লয়যোগ্য। ছবি/PDF থেকে অটো MCQ এক্সট্রাকশন, আনলিমিটেড কুইজ জেনারেশন, multi-provider AI cascading failover, এবং MongoDB persistent backup সহ একটি **Master-Class Quiz Bot**।

> 💡 **এক লাইনে:** *"যেখানে অন্য বট থেমে যায়, প্রবাহ সেখান থেকে শুরু করে।"*

---

## ✨ মূল ফিচার

<table>
<tr>
<td width="50%" valign="top">

### 🤖 AI & Intelligence
- 🧠 **Multi-AI Routing** — Gemini, Mistral, Perplexity, Groq, OpenRouter, DeepSeek
- ⚡ **Cascading Failover** — একটা প্রোভাইডার ডাউন হলে অটো পরেরটায় switch
- 🔑 **Multi-Key Pool** — প্রতি প্রোভাইডারে আনলিমিটেড API key + auto rotation
- 📊 **Quota Alerts** — কোটা শেষ হওয়ার আগেই owner কে notification
- ♾️ **Unlimited Quiz Generation** — যত key/provider, তত unlimited

</td>
<td width="50%" valign="top">

### 📚 OCR & Quiz Engine
- 🖼️ **Mistral OCR** — ছবি + PDF (page-by-page processing)
- 🎯 **Master MCQ Extractor** — ক)খ)গ)ঘ), a)b)c)d), ⓐⓑⓒⓓ সব format সাপোর্ট
- 🎓 **Auto Question Generation** — Easy / Medium / Hard count preview সহ
- 📝 **Telegram-Friendly Format** — LaTeX strip, 200-char explanation limit
- 📄 **CSV Export** — Math এর জন্য LaTeX format preserved

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🎙️ Voice & Media
- 🎤 **ElevenLabs Voice-to-Text** — high-accuracy speech recognition
- 🖼️ **Image Analysis** — Gemini Vision integration
- 📑 **PDF Page-by-Page** — error-isolated processing
- 🔊 **Audio reply support** — voice messages handled natively

</td>
<td width="50%" valign="top">

### 👥 Groups & Access Control
- 🌐 **Group + Topic Support** — cross-chat reply routing
- 🔐 **Role-based Permissions** — Owner / Admin / User isolation
- 📋 **A→Z Owner Command Menu** — full command list in `/` menu
- 💾 **MongoDB Backup** — weekly auto-backup (Sunday 03:00 UTC)
- ❤️ **Render Health Page** — live status + uptime monitoring

</td>
</tr>
</table>

---

## 🚀 কুইক স্টার্ট

<details>
<summary><b>💻 লোকাল রান (Click to expand)</b></summary>

```bash
# 1️⃣ Clone the repo
git clone <your-repo-url>
cd probaho-bot

# 2️⃣ Install dependencies
pip install -r requirements.txt

# 3️⃣ Set environment variables
export BOT_TOKEN="123456:ABC..."
export OWNER_ID="123456789"
export MONGO_URI="mongodb+srv://..."
export GEMINI_API_KEY="AIzaSy..."
export MISTRAL_API_KEY="..."
export ELEVENLABS_API_KEY="..."

# 4️⃣ Run
python main.py
```

</details>

<details open>
<summary><b>☁️ Render Deploy (১ ক্লিকে) — Recommended</b></summary>

| Step | Action |
|:---:|---|
| **1** | Render Dashboard → **New +** → **Blueprint** |
| **2** | এই repo সিলেক্ট → **Apply** ক্লিক (`render.yaml` auto-detect) |
| **3** | Environment tab এ সবগুলো secret সেট করুন (নিচের টেবিল দেখুন) |
| **4** | Deploy শেষ হলে URL পাবেন: `https://<your-app>.onrender.com` |
| **5** | UptimeRobot এ `/healthz` ping সেট করুন (প্রতি 5 মিনিট) |

</details>

---

## 🔐 Environment Variables

| Variable | Required | বর্ণনা |
|---|:---:|---|
| `BOT_TOKEN` | ✅ | Telegram BotFather token |
| `OWNER_ID` | ✅ | Owner Telegram ID (comma-separated for multi-owner) |
| `MONGO_URI` | ✅ | MongoDB Atlas connection string (persistent backup) |
| `GEMINI_API_KEY` | ⚪ | Google AI Studio key (in-bot `/addkey` ও কাজ করে) |
| `MISTRAL_API_KEY` | ⚪ | Mistral OCR key (in-bot multi-key supported) |
| `ELEVENLABS_API_KEY` | ⚪ | Voice-to-text key |

> 💡 **Tip:** ⚪ optional keys গুলো in-bot `/addkey` কমান্ড দিয়েও add করা যায় — DB তে save হয়ে rotation চলবে।

---

## 🏥 Health Endpoints

<div align="center">

| Endpoint | Purpose | Response |
|:---:|:---:|:---:|
| 🟢 `/` | Rich HTML status page | `text/html` |
| 💓 `/healthz` | UptimeRobot ping (2 byte) | `OK` |
| 📊 `/status.json` | Programmatic JSON status | `application/json` |

</div>

> ⚠️ **Render Free Notice:** 15 মিনিট idle হলে service sleep হয়। **UptimeRobot** বা **cron-job.org** দিয়ে `/healthz` প্রতি 5 মিনিটে ping করুন।

---

## 🎯 Owner Commands (A → Z)

<details>
<summary><b>📋 Full Command List (Click to expand)</b></summary>

| Command | কাজ |
|---|---|
| `/addkey <provider> <key>` | নতুন AI API key add |
| `/keys` | সব saved key দেখা |
| `/delkey <id>` | নির্দিষ্ট key remove |
| `/advmode` | Advanced provider dashboard (interactive) |
| `/advadd <name> <kind> [model] [key]` | নতুন AI provider add |
| `/advrm <id>` | Provider remove |
| `/advprio <id> <n>` | Provider priority adjust |
| `/gemini`, `/mistral`, `/mk` | Model switch |
| `/gen` | Quiz generation start |
| `/ans`, `/pans`, `/qa`, `/qans` | Answer modes |
| `/info`, `/features` | Bot info |
| `/restart`, `/sh` | System control |
| `/tutorial`, `/porag` | Help & guides |

</details>

---

## 🗂️ প্রজেক্ট স্ট্রাকচার

```text
probaho-bot/
├── 📁 bot/
│   ├── __main__.py              # Entrypoint (loads all sections)
│   ├── config.py                # Env-based secrets/config
│   └── 📁 sections/             # ⚡ 51 modular sections
│       ├── 00_header_imports.py
│       ├── 01_config.py
│       ├── ...
│       ├── 48_render_health_page_06_13.py
│       ├── 49_owner_full_command_menu_06_13.py
│       ├── 50_master_ocr_quiz_extractor_06_13.py
│       └── 51_advanced_quiz_mode_06_13.py  ⭐ NEW
├── main.py                      # Render entry shim
├── render.yaml                  # Blueprint config
├── requirements.txt             # Python deps
├── runtime.txt                  # Python 3.11.9
├── Procfile                     # Process declaration
└── README.md                    # You are here 📍
```

---

## 🌟 Architecture Highlights

```mermaid
flowchart LR
    A[👤 User Message] --> B{Router}
    B -->|Image/PDF| C[🖼️ Mistral OCR]
    B -->|Text| D[🧠 AI Cascade]
    C --> E[📝 Master MCQ Extractor]
    E --> F{Has MCQs?}
    F -->|Yes| G[📤 Telegram Poll]
    F -->|No| H[🎓 Auto-Generate E/M/H]
    D --> I[Gemini → Mistral → Groq → OpenRouter]
    I -->|Quota Hit| J[⚠️ Owner Alert]
    I -->|Success| G
    G --> K[💾 MongoDB Backup]
```

---

## 📊 Stats

<div align="center">

![Sections](https://img.shields.io/badge/Total%20Sections-51-blueviolet?style=for-the-badge)
![AI Providers](https://img.shields.io/badge/AI%20Providers-7%2B-orange?style=for-the-badge)
![Commands](https://img.shields.io/badge/Owner%20Commands-20%2B-green?style=for-the-badge)
![Uptime](https://img.shields.io/badge/Render%20Free-Bandwidth%205GB-cyan?style=for-the-badge)

</div>

---

<div align="center">

## 💖 Credits

**Built with ❤️ by [@Your_Himus](https://t.me/Your_Himus)**

<img src="https://user-images.githubusercontent.com/74038190/212284115-f47cd8ff-2ffb-4b04-b5bf-4d1c14c0247f.gif" width="100%" />

<sub>© 2026 mhx2n — Private project. All rights reserved.</sub>

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12&height=120&section=footer" alt="footer" />

</div>
