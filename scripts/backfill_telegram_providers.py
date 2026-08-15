"""Backfill auth_providers(telegram) for legacy users.

Old bot stored users with users.id == tg_id and no auth_providers table.
After dev migration these users have no telegram-provider rows; the bot
treats them as new users on next contact, creating orphan duplicates.

Run once after deploying dev to a legacy DB. Idempotent — re-running is safe.
"""
from __future__ import annotations
import logging
from services.db import connect
from utils.dates import now_iso

logger = logging.getLogger(__name__)


def backfill() -> int:
    """Insert missing (telegram, str(users.id)) auth_providers for legacy users.
    Returns number of rows inserted."""
    with connect() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO auth_providers"
            "(user_id, provider, identifier, created_at, verified) "
            "SELECT u.id, 'telegram', CAST(u.id AS TEXT), ?, 1 "
            "FROM users u "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM auth_providers ap "
            "  WHERE ap.user_id = u.id AND ap.provider = 'telegram'"
            ")",
            (now_iso(),),
        )
        inserted = cur.rowcount
        con.commit()
    logger.info("backfill_telegram_providers: inserted %d rows", inserted)
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    n = backfill()
    print(f"backfill: inserted {n} telegram providers")
