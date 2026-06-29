import sqlite3
from pathlib import Path
import pytest


def test_pending_email_links_table_exists(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_email_links'"
        ).fetchone()
        assert row is not None


def test_pending_email_links_columns(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(pending_email_links)").fetchall()}
    assert cols == {"email", "user_id", "password_hash", "code", "expires_at", "created_at"}


def test_notifications_table_in_schema(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(notifications)")}
    assert cols == {
        "id", "user_id", "kind", "order_id", "new_status",
        "text", "created_at", "read_at",
    }


def test_notifications_indexes_present(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        idx = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='notifications'"
        )}
    assert "idx_notifications_user_unread" in idx
    assert "idx_notifications_user_created" in idx


def test_orders_has_new_payment_columns(tmp_db):
    from utils.sqlite3 import create_db
    create_db()
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(orders)").fetchall()}
    assert "payment_method" in cols
    assert "payment_expires_at" in cols
    assert "payment_id" in cols
    assert "phone" in cols


def test_auth_providers_has_verified_column(tmp_db):
    from utils.sqlite3 import create_db
    create_db()
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(auth_providers)").fetchall()}
    assert "verified" in cols


def test_otp_codes_has_channel_and_destination_columns(tmp_db):
    from utils.sqlite3 import create_db
    create_db()
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(otp_codes)").fetchall()}
    assert "channel" in cols
    assert "destination" in cols
    assert "telegram_id" not in cols  # переименовано


def test_order_links_table_in_schema(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(order_links)")}
    assert cols == {
        "id", "order_id", "url", "status", "delivery_mode",
        "deadline_at", "started_at", "done_at", "failed_at",
        "failure_reason", "external_id", "created_at",
        "dispatch_attempts",
    }


def test_order_links_indexes_present(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        idx = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='order_links'"
        )}
    assert "idx_order_links_order" in idx
    assert "idx_order_links_deadline" in idx


def test_avito_ad_phrase_cache_table(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute(
            "PRAGMA table_info(avito_ad_phrase_cache)"
        )}
    assert cols == {"ad_id", "search_link", "created_at", "cached_at"}

    with sqlite3.connect(tmp_db) as con:
        pk = [r[1] for r in con.execute(
            "PRAGMA table_info(avito_ad_phrase_cache)"
        ) if r[5] == 1]  # pk flag
    assert pk == ["ad_id"]


def test_avito_ad_phrase_cache_indexes_present(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        idx = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='avito_ad_phrase_cache'"
        )}
    assert "idx_apc_cached_at" in idx
