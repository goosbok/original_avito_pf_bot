"""One-shot миграция Phase 2: заполнить auth_providers для существующих юзеров.

Запускать ПОСЛЕ create_db() на проде. Идемпотентен — запуск второй раз ничего не делает.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.config import path_database


def main() -> None:
    con = sqlite3.connect(path_database)
    con.row_factory = sqlite3.Row
    try:
        users = con.execute("SELECT id FROM users").fetchall()
        now = datetime.now(timezone.utc).isoformat()

        inserted = 0
        skipped = 0
        for u in users:
            tg_id = u["id"]
            existing = con.execute(
                "SELECT 1 FROM auth_providers WHERE provider = 'telegram' AND identifier = ?",
                (str(tg_id),),
            ).fetchone()
            if existing:
                skipped += 1
                continue
            con.execute(
                "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
                "VALUES (?, 'telegram', ?, ?)",
                (tg_id, str(tg_id), now),
            )
            inserted += 1
        con.commit()
        print(f"users={len(users)}, auth_providers inserted={inserted}, skipped={skipped}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
