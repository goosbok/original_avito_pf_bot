"""One-shot migration Phase 3: add pending_email_links.

Idempotent — safe to run multiple times.
Run AFTER deploying the new code: python scripts/migrate_phase3.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.config import path_database


def main() -> None:
    con = sqlite3.connect(path_database)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS pending_email_links("
            "email TEXT PRIMARY KEY,"
            "user_id INTEGER NOT NULL,"
            "password_hash TEXT NOT NULL,"
            "code TEXT NOT NULL,"
            "expires_at TIMESTAMP NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        con.commit()
        print("migrate_phase3: done — pending_email_links created")
    finally:
        con.close()


if __name__ == "__main__":
    main()
