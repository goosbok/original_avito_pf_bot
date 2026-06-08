"""Pytest configuration for e2e tests.

The e2e suite uses Telethon to drive a real Telegram client and requires
extra dependencies (`telethon`, `python-dotenv`) that are NOT installed in
the main project's Docker image (`original_avito_pf_bot-api`). The setup
is documented in `tests/e2e/README.md` — runs in a separate `.venv-test`.

Without these deps, pytest fails at collection with `ModuleNotFoundError`
on the first import, which blocks `pytest -v` from the project root.

Skip the entire e2e collection when the deps are missing — the e2e harness
runs separately by design.
"""
from __future__ import annotations

collect_ignore_glob: list[str] = []

try:
    import dotenv  # noqa: F401
    import telethon  # noqa: F401
except ImportError:
    # E2e deps missing → skip the suite. Pytest never imports these files.
    collect_ignore_glob.append("test_*.py")
