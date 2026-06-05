"""
One-shot load-test seeder/cleaner for orders table.

Usage (inside docker container):
    python /tmp/seed.py [COUNT] [--user-id ID]   # default COUNT=3000
    python /tmp/seed.py --cleanup                # removes rows with user_name='LOAD_TEST_3K'

The script is intentionally self-contained: it talks to SQLite directly via
DATABASE_PATH env (same path the bot uses) and only depends on utils.dates.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time

# Allow `from utils.dates import now_iso` when run from /tmp/seed.py inside the container.
sys.path.insert(0, "/app")

from utils.dates import now_iso  # noqa: E402

MARKER = "LOAD_TEST_3K"
DB_PATH = os.getenv("DATABASE_PATH", "/app/storage/database.db")

STATUS_CYCLE = ("paid", "done", "payment_failed")
POSITION_CYCLE = ("3 дня/200ПФ", "7 дней/500ПФ", "14 дней/1000ПФ")


def pick_user_id(con: sqlite3.Connection, requested: int | None) -> int:
    con.row_factory = sqlite3.Row
    if requested is not None:
        row = con.execute("SELECT id FROM users WHERE id = ?", (requested,)).fetchone()
        if row is None:
            print(f"[seed] FATAL: user_id={requested} not found in users", file=sys.stderr)
            sys.exit(1)
        return int(row["id"])
    row = con.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    if row is None:
        print("[seed] FATAL: users table is empty — cannot seed orders (FK)", file=sys.stderr)
        sys.exit(1)
    return int(row["id"])


def assert_not_excluded(con: sqlite3.Connection, user_id: int) -> None:
    row = con.execute(
        "SELECT value FROM settings WHERE parametr = 'report_exclude'"
    ).fetchone()
    if not row or not row[0]:
        return
    excluded = {x.strip() for x in row[0].split(",") if x.strip()}
    if str(user_id) in excluded:
        print(
            f"[seed] FATAL: user_id={user_id} is in report_exclude — "
            f"orders would not appear in create_sheet() output. Pick another --user-id.",
            file=sys.stderr,
        )
        sys.exit(1)


def seed(count: int, user_id_arg: int | None) -> None:
    with sqlite3.connect(DB_PATH) as con:
        user_id = pick_user_id(con, user_id_arg)
        assert_not_excluded(con, user_id)

        rows = []
        for i in range(count):
            rows.append(
                (
                    user_id,
                    100 + (i % 50) * 100,
                    POSITION_CYCLE[i % len(POSITION_CYCLE)],
                    STATUS_CYCLE[i % len(STATUS_CYCLE)],
                    f"https://avito.ru/test/ad_{i}",
                    now_iso(),
                    1 if i % 2 == 0 else 0,
                    MARKER,
                )
            )

        t0 = time.perf_counter()
        con.executemany(
            "INSERT INTO orders "
            "(user_id, price, position_name, status, links, date, contacts, user_name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.commit()
        dt = time.perf_counter() - t0

    print(f"[seed] inserted {count} rows in {dt:.2f} sec (user_id={user_id}, marker={MARKER!r})")


def cleanup() -> None:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("DELETE FROM orders WHERE user_name = ?", (MARKER,))
        deleted = cur.rowcount
        con.commit()
    print(f"[seed] cleanup: deleted {deleted} rows with marker {MARKER!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed/cleanup load-test orders.")
    parser.add_argument("count", nargs="?", type=int, default=3000)
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    if args.cleanup:
        cleanup()
    else:
        seed(args.count, args.user_id)


if __name__ == "__main__":
    main()
