"""Entry point: ``python -m bot``.

Loads every file in ``bot/sections/`` in lexical (== original) order and
executes them inside a single shared globals dict. This is a deliberate
design choice: the original 25k-line script relies on dozens of late
"PATCH" sections that monkey-patch earlier top-level functions. Splitting
them into normal Python modules would break those cross-references; the
shared-namespace loader preserves behaviour byte-for-byte while still
giving you a clean, browsable file layout.
"""
from __future__ import annotations

import pathlib
import sys
import traceback

from bot.config import as_runtime_globals

SECTIONS_DIR = pathlib.Path(__file__).parent / "sections"


def _ordered_section_files() -> list[pathlib.Path]:
    return sorted(
        p for p in SECTIONS_DIR.glob("*.py") if p.name != "__init__.py"
    )


def _build_runtime_namespace() -> dict:
    """Create the shared globals dict that every section will run in."""
    ns: dict = {
        "__name__": "__main__",     # so any `if __name__ == "__main__":` blocks fire
        "__file__": str(SECTIONS_DIR.parent / "probaho_bot.py"),
        "__package__": None,
        "__builtins__": __builtins__,
    }
    # Inject externalised config BEFORE the config section runs.
    ns.update(as_runtime_globals())
    return ns


def _load_all_sections(ns: dict) -> None:
    for path in _ordered_section_files():
        try:
            code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError:
            print(f"\n[bot] Syntax error while compiling section: {path.name}",
                  file=sys.stderr)
            raise
        try:
            exec(code, ns)
        except SystemExit:
            raise
        except Exception:
            print(f"\n[bot] Error while executing section: {path.name}",
                  file=sys.stderr)
            traceback.print_exc()
            raise


def main() -> None:
    ns = _build_runtime_namespace()
    _load_all_sections(ns)

    # The original script ended with:
    #     if __name__ == "__main__":
    #         _acquire_single_instance_lock()
    #         main()
    # We stripped that block from the last section file; call it here.
    lock_fn = ns.get("_acquire_single_instance_lock")
    if callable(lock_fn):
        lock_fn()
    bot_main = ns.get("main")
    if not callable(bot_main):
        raise RuntimeError(
            "[bot] No `main()` defined after loading all sections — "
            "something stripped or shadowed it."
        )
    bot_main()


if __name__ == "__main__":
    main()