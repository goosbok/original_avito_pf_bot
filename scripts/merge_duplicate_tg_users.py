"""Merge orphan TG-user duplicates back into their legacy records.

Caused by: legacy users had users.id == tg_id without auth_providers; when
they touched the new bot, middleware created a duplicate user with new
auto-id and an auth_providers(telegram, str(tg_id)) row pointing to the
duplicate. The legacy user became orphaned.

This script finds pairs (legacy_id, duplicate_id) where:
  - users.id = legacy_id exists
  - auth_providers(telegram, str(legacy_id)) -> duplicate_id (and duplicate_id != legacy_id)
and merges duplicate -> legacy in one transaction.

Run AFTER backfill_telegram_providers. Idempotent — re-running finds nothing.
"""
from __future__ import annotations
import logging
import sqlite3
from services.db import connect

logger = logging.getLogger(__name__)


_OWNED_TABLES_USER_ID = [
    ("orders", "user_id"),
    ("refills", "user_id"),
    ("notifications", "user_id"),
    ("funnel_events", "user_id"),
    ("support_messages", "user_id"),
    ("otp_codes", "user_id_to_link"),
]


def _merge_one(con, *, legacy_id: int, duplicate_id: int) -> None:
    # 1. Re-parent rows in owned tables
    for table, col in _OWNED_TABLES_USER_ID:
        con.execute(
            f"UPDATE {table} SET {col} = ? WHERE {col} = ?",
            (legacy_id, duplicate_id),
        )

    # 2. Balance + names
    dup_row = con.execute(
        "SELECT balance, user_name, first_name FROM users WHERE id = ?",
        (duplicate_id,),
    ).fetchone()
    if dup_row:
        dup_balance = int(dup_row["balance"] or 0) if hasattr(dup_row, "keys") else int(dup_row[0] or 0)
        dup_user_name = dup_row["user_name"] if hasattr(dup_row, "keys") else dup_row[1]
        dup_first_name = dup_row["first_name"] if hasattr(dup_row, "keys") else dup_row[2]
        con.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ?, "
            "  user_name = COALESCE(user_name, ?), "
            "  first_name = COALESCE(first_name, ?) "
            "WHERE id = ?",
            (dup_balance, dup_user_name, dup_first_name, legacy_id),
        )

    # 3. Re-target auth_providers; on UNIQUE conflict drop duplicate's row
    dup_providers = con.execute(
        "SELECT id, provider, identifier FROM auth_providers WHERE user_id = ?",
        (duplicate_id,),
    ).fetchall()
    for r in dup_providers:
        ap_id = r["id"] if hasattr(r, "keys") else r[0]
        try:
            con.execute(
                "UPDATE auth_providers SET user_id = ? WHERE id = ?",
                (legacy_id, ap_id),
            )
        except sqlite3.IntegrityError:
            # Legacy already owns this (provider, identifier) — drop duplicate's
            con.execute("DELETE FROM auth_providers WHERE id = ?", (ap_id,))

    # 4. Delete duplicate users row
    con.execute("DELETE FROM users WHERE id = ?", (duplicate_id,))


def merge_duplicates() -> int:
    """Find and merge all (legacy_id, duplicate_id) pairs.

    Returns number of pairs merged.
    """
    with connect() as con:
        rows = con.execute(
            "SELECT u.id AS legacy_id, ap.user_id AS duplicate_id "
            "FROM users u "
            "JOIN auth_providers ap "
            "  ON ap.provider = 'telegram' AND ap.identifier = CAST(u.id AS TEXT) "
            "WHERE ap.user_id != u.id"
        ).fetchall()
    pairs = [(int(r["legacy_id"]), int(r["duplicate_id"])) for r in rows]

    merged = 0
    for legacy_id, duplicate_id in pairs:
        try:
            with connect() as con:
                _merge_one(con, legacy_id=legacy_id, duplicate_id=duplicate_id)
                con.commit()
            logger.info(
                "merged duplicate %s into legacy %s", duplicate_id, legacy_id
            )
            merged += 1
        except Exception:  # noqa: BLE001
            logger.exception(
                "merge failed for pair legacy=%s duplicate=%s",
                legacy_id, duplicate_id,
            )

    logger.info("merge_duplicate_tg_users: merged %d pairs", merged)
    return merged


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    n = merge_duplicates()
    print(f"merge: merged {n} pairs")
