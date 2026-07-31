# ──────────────────────────────────────────────────────────────────────────────
# Section: 03_concurrency_pools
# Original lines: 223..263
# DO NOT import this file directly — it is exec'd in shared namespace by bot/__main__.py
# ──────────────────────────────────────────────────────────────────────────────
# =========================================================
# ✅ Concurrency: separate pools so USER কাজ করলে ADMIN/OWNER আটকে না যায়
# =========================================================
from concurrent.futures import ThreadPoolExecutor

# Pella / low-RAM safe defaults (tunable)
_OWNER_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="owner")
_ADMIN_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="admin")
_USER_EXECUTOR  = ThreadPoolExecutor(max_workers=8, thread_name_prefix="user")

# Limit how many heavy jobs can run at once per group
_OWNER_SEM = asyncio.Semaphore(2)
_ADMIN_SEM = asyncio.Semaphore(3)
_USER_SEM  = asyncio.Semaphore(6)

def _pick_executor_and_sem(role: str):
    r = (role or "").upper()
    if r == "OWNER":
        return _OWNER_EXECUTOR, _OWNER_SEM
    if r == "ADMIN":
        return _ADMIN_EXECUTOR, _ADMIN_SEM
    # default USER
    return _USER_EXECUTOR, _USER_SEM

async def _run_blocking(role: str, fn, *args, timeout: float | None = None, **kwargs):
    """Run a blocking function in a role-based thread pool.

    Why: Python-telegram-bot v20 runs handlers in asyncio. If we call blocking
    I/O (requests, AI calls, heavy parsing) directly, it blocks the event loop.
    This helper offloads the work while also preventing USER workload from
    starving ADMIN/OWNER tasks.
    """
    executor, sem = _pick_executor_and_sem(role)
    loop = asyncio.get_running_loop()

    async with sem:
        fut = loop.run_in_executor(executor, lambda: fn(*args, **kwargs))
        if timeout is not None:
            return await asyncio.wait_for(fut, timeout=timeout)
        return await fut

