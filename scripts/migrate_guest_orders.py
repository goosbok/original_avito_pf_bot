"""One-shot migration: create guest_orders table on existing prod DB.

Idempotent — safe to run multiple times.
Run: python scripts/migrate_guest_orders.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.config import path_database


DDL = (
    "CREATE TABLE IF NOT EXISTS guest_orders("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "phone TEXT NOT NULL,"
    "links TEXT NOT NULL,"
    "days INTEGER NOT NULL,"
    "fix_count INTEGER NOT NULL,"
    "contacts INTEGER NOT NULL DEFAULT 0,"
    "price INTEGER NOT NULL,"
    "price_per_unit INTEGER NOT NULL,"
    "payment_id TEXT,"
    "status TEXT NOT NULL DEFAULT 'pending_payment',"
    "created_at TEXT NOT NULL)"
)


def main() -> None:
    con = sqlite3.connect(path_database)
    try:
        con.execute(DDL)
        con.commit()
        print("guest_orders table created (or already existed).")
    finally:
        con.close()


if __name__ == "__main__":
    main()
