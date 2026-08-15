"""One-shot migration: convert legacy 'dd.mm.YYYY HH:MM:SS' dates to ISO+UTC.

Idempotent — safe to re-run. Treats legacy strings as Moscow (UTC+3) time
because historically the server ran in MSK.

Usage:
    python scripts/migrate_dates_to_iso.py                # apply
    python scripts/migrate_dates_to_iso.py --dry-run      # report only
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.config import path_database  # noqa: E402

_MSK = timezone(timedelta(hours=3))

TARGETS: list[tuple[str, str]] = [
    ("orders", "date"),
    ("reviews", "date"),
    ("delreviews", "date"),
    ("seo", "date"),
    ("guest_orders", "created_at"),
    ("refills", "date"),
    ("support_messages", "created_at"),
]


def _convert(value: str) -> str | None:
    """Returns new ISO string if conversion needed; None if already ISO; raises ValueError if unrecognised."""
    s = value.strip()
    try:
        legacy = datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
    except ValueError:
        pass
    else:
        moscow = legacy.replace(tzinfo=_MSK)
        return moscow.astimezone(timezone.utc).isoformat()
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return None
    except ValueError:
        raise


def migrate(db_path: Path | str, dry_run: bool = False) -> dict[str, dict[str, int]]:
    """Migrate all TARGETS in db_path. Returns per-table stats."""
    stats: dict[str, dict[str, int]] = {}
    con = sqlite3.connect(str(db_path))
    try:
        for table, col in TARGETS:
            table_stats = {"migrated": 0, "already_iso": 0, "skipped": 0, "null": 0}
            stats[table] = table_stats
            try:
                rows = con.execute(f"SELECT rowid, {col} FROM {table}").fetchall()
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc).lower():
                    continue
                raise
            for rowid, value in rows:
                if value is None or (isinstance(value, str) and not value.strip()):
                    table_stats["null"] += 1
                    continue
                try:
                    new_value = _convert(str(value))
                except ValueError:
                    table_stats["skipped"] += 1
                    print(f"  [skip] {table}.{col} rowid={rowid}: unrecognised value={value!r}")
                    continue
                if new_value is None:
                    table_stats["already_iso"] += 1
                    continue
                table_stats["migrated"] += 1
                if not dry_run:
                    con.execute(f"UPDATE {table} SET {col} = ? WHERE rowid = ?", (new_value, rowid))
        if not dry_run:
            con.commit()
    finally:
        con.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    stats = migrate(path_database, dry_run=args.dry_run)
    print(f"\nMigration {'(DRY-RUN) ' if args.dry_run else ''}summary:")
    for table, s in stats.items():
        print(f"  {table:25s} migrated={s['migrated']:4d}  already_iso={s['already_iso']:4d}  null={s['null']:4d}  skipped={s['skipped']:4d}")


if __name__ == "__main__":
    main()
