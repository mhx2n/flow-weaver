# ──────────────────────────────────────────────────────────────────────────────
# Section 75 (2026-06-15) — Smart photo size for OCR + persistent SQLite cache.
#
# দুটো সমস্যা একসাথে ঠিক করা হয়েছে:
#
#   1) SMART PHOTO SIZE:
#      বর্তমানে _resolve_ocr_ctx_59 সবসময় photo[-1] (সবচেয়ে বড় সাইজ) ডাউনলোড
#      করে। একটা সাধারণ ফোনের ছবি ১-৩ MB হতে পারে। OCR-এর জন্য ৮০০px যথেষ্ট,
#      যা সাধারণত photo[-2] — মাত্র ১০০-৩০০ KB।
#      নতুন লজিক: file_size দেখে সবচেয়ে ছোট কিন্তু OCR-উপযুক্ত (>80KB) সাইজ বেছে
#      নেয়। এতে প্রতি OCR-এ ৪০-৮০% ব্যান্ডউইথ বাঁচে।
#
#   2) SQLITE OCR RESULT CACHE:
#      বর্তমানে OCR context শুধু bot_data (RAM)-এ থাকে। Render প্রতিদিন restart
#      করলে সব মুছে যায়। পরের দিন একই ছবিতে .gen দিলে আবার পুরো Mistral OCR চলে।
#      নতুন লজিক: Telegram-এর file_unique_id দিয়ে SQLite-এ OCR result সেভ করা হয়।
#      পরেরবার একই ছবি দিলে Mistral API call ছাড়াই instant result পাওয়া যায়।
#      Cache TTL: ৩০ দিন। Max entries: ৩০০।
#
# Additive overlay — _resolve_ocr_ctx_59 wrap করা হয়, অন্য কিছু ছোঁয়া হয়নি।
# DO NOT import directly — exec'd by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────

import contextlib as _cx75
import json as _json75
import time as _time75

# ─── Constants ────────────────────────────────────────────────────────────────

_OCR_CACHE_TABLE_75    = "ocr_result_cache"
_OCR_CACHE_TTL_75      = 30 * 24 * 3600   # ৩০ দিন (seconds)
_OCR_CACHE_MAX_ROWS_75 = 300               # সর্বোচ্চ এন্ট্রি
_OCR_MIN_SIZE_BYTES_75 = 80_000            # ন্যূনতম ৮০ KB (এর কম = ঝাপসা, OCR খারাপ)
_OCR_TARGET_MAX_75     = 500_000           # ৫০০ KB-এর বেশি হলে ছোটটা নাও

# ─── 1) SQLite cache table তৈরি ───────────────────────────────────────────────

def _ocr_cache_init_75() -> None:
    """Bot start-এ একবার চলে। Table না থাকলে তৈরি করে।"""
    try:
        conn = db_connect()                                       # noqa: F821
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {_OCR_CACHE_TABLE_75} (
                file_unique_id  TEXT    PRIMARY KEY,
                ocr_ctx_json    TEXT    NOT NULL,
                created_at      INTEGER NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        logger.info("[PATCH-75] OCR result cache table ready.")  # noqa: F821
    except Exception as exc:
        logger.warning("[PATCH-75] Cache table init failed: %s", exc)  # noqa: F821


with _cx75.suppress(Exception):
    _ocr_cache_init_75()


# ─── 2) Cache read / write helpers ────────────────────────────────────────────

def _ocr_cache_get_75(file_unique_id: str):
    """
    Cache hit হলে dict return করে, না হলে None।
    Expired entries automatically skip করা হয়।
    """
    if not file_unique_id:
        return None
    try:
        conn = db_connect()                                       # noqa: F821
        cur = conn.cursor()
        cur.execute(
            f"SELECT ocr_ctx_json, created_at FROM {_OCR_CACHE_TABLE_75} "
            "WHERE file_unique_id = ?",
            (str(file_unique_id),),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        age = _time75.time() - int(row["created_at"] or 0)
        if age > _OCR_CACHE_TTL_75:
            # Expired — সরিয়ে ফেলো (lazy cleanup)
            with _cx75.suppress(Exception):
                c2 = db_connect()                                 # noqa: F821
                c2.execute(
                    f"DELETE FROM {_OCR_CACHE_TABLE_75} WHERE file_unique_id = ?",
                    (str(file_unique_id),),
                )
                c2.commit()
                c2.close()
            return None
        ctx = _json75.loads(str(row["ocr_ctx_json"]))
        return ctx if isinstance(ctx, dict) else None
    except Exception as exc:
        logger.debug("[PATCH-75] cache get error: %s", exc)      # noqa: F821
        return None


def _ocr_cache_set_75(file_unique_id: str, ocr_ctx: dict) -> None:
    """OCR result SQLite-এ সেভ করো। ৩০০ rows-এর বেশি হলে পুরনোটা মুছে ফেলো।"""
    if not file_unique_id or not isinstance(ocr_ctx, dict):
        return
    # items list অনেক বড় হতে পারে, JSON size যাচাই করো
    try:
        payload = _json75.dumps(ocr_ctx, ensure_ascii=False)
        if len(payload) > 500_000:
            # ৫০০ KB-এর বেশি — items বাদ দিয়ে ছোট করো
            slim = {k: v for k, v in ocr_ctx.items() if k != "items"}
            payload = _json75.dumps(slim, ensure_ascii=False)
    except Exception:
        return

    try:
        conn = db_connect()                                       # noqa: F821
        conn.execute(
            f"INSERT INTO {_OCR_CACHE_TABLE_75} (file_unique_id, ocr_ctx_json, created_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(file_unique_id) DO UPDATE SET "
            "ocr_ctx_json=excluded.ocr_ctx_json, created_at=excluded.created_at",
            (str(file_unique_id), payload, int(_time75.time())),
        )
        # Max rows enforcement
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {_OCR_CACHE_TABLE_75}")
        row_count = (cur.fetchone() or [0])[0]
        if row_count > _OCR_CACHE_MAX_ROWS_75:
            # সবচেয়ে পুরনো ১০০টা মুছে ফেলো
            conn.execute(
                f"DELETE FROM {_OCR_CACHE_TABLE_75} WHERE file_unique_id IN "
                f"(SELECT file_unique_id FROM {_OCR_CACHE_TABLE_75} "
                "ORDER BY created_at ASC LIMIT 100)"
            )
        conn.commit()
        conn.close()
        logger.debug("[PATCH-75] OCR cached for unique_id=%s", file_unique_id[:12])  # noqa: F821
    except Exception as exc:
        logger.debug("[PATCH-75] cache set error: %s", exc)      # noqa: F821


# ─── 3) Smart photo size selection ────────────────────────────────────────────

def _pick_ocr_photo_75(photos):
    """
    OCR-এর জন্য সেরা photo size বেছে নাও।

    Telegram photo array (ছোট থেকে বড়):
      photos[0]  → ~90px thumbnail   (~5-15 KB)   ← বাদ
      photos[1]  → ~320px            (~20-60 KB)  ← সাধারণত বাদ
      photos[2]  → ~800px            (~80-250 KB) ← OCR-এর জন্য ভালো ✓
      photos[-1] → original/largest  (~500KB-3MB) ← বড়, অপ্রয়োজনীয়

    লজিক:
      • file_size > 80KB এবং যতটা সম্ভব ছোট এমন সাইজ বেছে নাও
      • সব size 80KB-এর কম হলে সবচেয়ে বড়টা নাও (scan/whiteboard হতে পারে)
      • শুধু ১টা size থাকলে সেটাই নাও
    """
    if not photos:
        return None
    if len(photos) == 1:
        return photos[0]

    # file_size-সহ list তৈরি করো
    sized = [(getattr(p, "file_size", 0) or 0, i, p) for i, p in enumerate(photos)]

    # ন্যূনতম ৮০KB-এর চেয়ে বড় photos ফিল্টার করো
    adequate = [(s, i, p) for s, i, p in sized if s >= _OCR_MIN_SIZE_BYTES_75]

    if not adequate:
        # সব photo ছোট (হয়তো thumbnail-only situation) — সবচেয়ে বড়টা নাও
        return photos[-1]

    # সবচেয়ে ছোট adequate photo (ব্যান্ডউইথ বাঁচে, OCR কোয়ালিটি ঠিক থাকে)
    adequate.sort(key=lambda x: x[0])  # file_size ascending
    chosen_size, chosen_idx, chosen_photo = adequate[0]

    # কত বাঁচলো লগ করো
    original_size = sized[-1][0]
    if original_size > 0 and chosen_size < original_size:
        saved_pct = round((1 - chosen_size / original_size) * 100)
        logger.debug(
            "[PATCH-75] Photo size: %dKB → %dKB (saved %d%%, index %d/%d)",
            original_size // 1024,
            chosen_size // 1024,
            saved_pct,
            chosen_idx,
            len(photos) - 1,
        )                                                         # noqa: F821

    return chosen_photo


# ─── 4) _resolve_ocr_ctx_59 override ─────────────────────────────────────────

try:
    _prev_resolve_ocr_ctx_75 = _resolve_ocr_ctx_59              # type: ignore[name-defined]
except Exception:
    _prev_resolve_ocr_ctx_75 = None


async def _resolve_ocr_ctx_59(                                  # noqa: F811
    update, context, reply_msg, uid: int
):
    """
    Patched version:
      ① RAM cache চেক (আগের মতো — fastest)
      ② SQLite cache চেক by file_unique_id (নতুন — restart-proof)
      ③ Cache miss → original function চালাও (Telegram download + Mistral OCR)
      ④ Result SQLite-এ সেভ করো
    Also patches the photo selection inside to use smart size.
    """
    # ── ① RAM cache (সবচেয়ে দ্রুত) ────────────────────────────────────────
    with _cx75.suppress(Exception):
        if _has_ocr_context(context, reply_msg):                 # noqa: F821
            cached = _get_ocr_context(context, reply_msg.message_id)  # noqa: F821
            if cached:
                return cached

    # ── ② SQLite cache (restart-proof) ──────────────────────────────────────
    file_unique_id = None
    with _cx75.suppress(Exception):
        photos = getattr(reply_msg, "photo", None)
        if photos:
            # Telegram photo array-এর যেকোনো size-এর file_unique_id একই হয়
            file_unique_id = str(getattr(photos[-1], "file_unique_id", "") or "")
        elif getattr(reply_msg, "document", None):
            file_unique_id = str(
                getattr(reply_msg.document, "file_unique_id", "") or ""
            )

    if file_unique_id:
        db_cached = _ocr_cache_get_75(file_unique_id)
        if db_cached:
            logger.info(                                          # noqa: F821
                "[PATCH-75] OCR cache HIT for unique_id=%s", file_unique_id[:12]
            )
            # RAM-এও সেট করো পরের বার আরও দ্রুত পেতে
            with _cx75.suppress(Exception):
                _remember_ocr_context(context, reply_msg.message_id, db_cached)  # noqa: F821
            return db_cached

    # ── ③ Cache miss — original function-এর কাছে যাও ─────────────────────
    # photo[-1] → smart size patch: temporarily swap photo list so original
    # function picks the right size when it calls reply_msg.photo[-1]
    _orig_photo = None
    if getattr(reply_msg, "photo", None):
        photos_list = list(reply_msg.photo)
        best_photo = _pick_ocr_photo_75(photos_list)
        if best_photo is not None and best_photo is not photos_list[-1]:
            # photo tuple-এ সরাসরি লেখা যায় না, তাই বিকল্প পথ:
            # একটা slim wrapper তৈরি করো যেটা photo[-1]-এ best_photo দেয়
            class _PhotoProxy75:
                def __init__(self, orig, best):
                    self._orig = orig
                    self._best = best
                def __getitem__(self, idx):
                    if idx == -1 or idx == len(self._orig) - 1:
                        return self._best
                    return self._orig[idx]
                def __len__(self):
                    return len(self._orig)
                def __bool__(self):
                    return bool(self._orig)
            _orig_photo = reply_msg.photo
            try:
                reply_msg.photo = _PhotoProxy75(photos_list, best_photo)
            except (AttributeError, TypeError):
                # telegram object read-only হলে skip
                _orig_photo = None

    try:
        if _prev_resolve_ocr_ctx_75 is None:
            return None
        result = await _prev_resolve_ocr_ctx_75(update, context, reply_msg, uid)
    finally:
        # photo টা পুনরুদ্ধার করো
        if _orig_photo is not None:
            with _cx75.suppress(Exception):
                reply_msg.photo = _orig_photo

    # ── ④ Result পাওয়া গেলে SQLite-এ সেভ করো ───────────────────────────────
    if result and file_unique_id:
        with _cx75.suppress(Exception):
            _ocr_cache_set_75(file_unique_id, result)
            logger.info(                                          # noqa: F821
                "[PATCH-75] OCR result cached to SQLite for unique_id=%s",
                file_unique_id[:12],
            )

    return result


# ─── 5) Cache management commands (owner-only) ────────────────────────────────

async def _cmd_ocrcache_75(update, context):
    """
    .ocrcache          → কতটা cache আছে দেখাও
    .ocrcache clear    → সব cache মুছে ফেলো
    """
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_owner_id(uid):                                    # noqa: F821
        return
    args = list(context.args or [])
    try:
        conn = db_connect()                                       # noqa: F821
        cur = conn.cursor()
        if args and args[0].lower() == "clear":
            cur.execute(f"DELETE FROM {_OCR_CACHE_TABLE_75}")
            conn.commit()
            conn.close()
            with _cx75.suppress(Exception):
                await update.effective_message.reply_text(
                    "✅ OCR cache cleared."
                )
            return
        cur.execute(f"SELECT COUNT(*) FROM {_OCR_CACHE_TABLE_75}")
        total = (cur.fetchone() or [0])[0]
        cur.execute(
            f"SELECT COUNT(*) FROM {_OCR_CACHE_TABLE_75} WHERE created_at > ?",
            (int(_time75.time()) - 86400,),
        )
        last_24h = (cur.fetchone() or [0])[0]
        conn.close()
        with _cx75.suppress(Exception):
            await update.effective_message.reply_text(
                f"📦 OCR SQLite Cache\n"
                f"মোট entries: <b>{total}</b> / {_OCR_CACHE_MAX_ROWS_75}\n"
                f"গত ২৪ ঘণ্টায় cached: <b>{last_24h}</b>\n"
                f"TTL: {_OCR_CACHE_TTL_75 // 86400} দিন\n\n"
                f"মুছতে: <code>.ocrcache clear</code>",
                parse_mode="HTML",
            )
    except Exception as exc:
        with _cx75.suppress(Exception):
            await update.effective_message.reply_text(f"Error: {exc}")


# Dot-command dispatcher
_DOT_OCRCACHE_RE_75 = __import__("re").compile(
    r"^\.ocrcache\b\s*(.*)", __import__("re").IGNORECASE
)

async def _dot_dispatch_75(update, context):
    msg = update.effective_message
    if not msg or not msg.text:
        return
    m = _DOT_OCRCACHE_RE_75.match(msg.text.strip())
    if not m:
        return
    context.args = (m.group(1) or "").split()
    await _cmd_ocrcache_75(update, context)


# ─── 6) Register handlers ─────────────────────────────────────────────────────

_prev_build_app_75 = build_app                                   # type: ignore[name-defined]

def build_app():                                                 # noqa: F811
    app = _prev_build_app_75()
    import contextlib as _cx
    from telegram.ext import CommandHandler, MessageHandler, filters
    with _cx.suppress(Exception):
        app.add_handler(CommandHandler("ocrcache", _cmd_ocrcache_75))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, _dot_dispatch_75),
            group=-395,
        )
    return app


logger.info(                                                      # noqa: F821
    "[PATCH-75] Smart photo size + SQLite OCR cache active. "
    "Commands: .ocrcache / /ocrcache"
)
# ===== END SECTION 75 =====
