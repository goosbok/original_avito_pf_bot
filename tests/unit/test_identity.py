import pytest
from pathlib import Path

from services import identity
from services.exceptions import (
    EmailAlreadyRegistered,
    ProviderAlreadyLinked,
    UserNotFound,
)


def test_get_or_create_user_by_telegram_creates_new(tmp_db: Path) -> None:
    uid = identity.get_or_create_user_by_telegram(123456, user_name="alice", first_name="Alice")
    assert uid > 0
    user = identity.get_user(uid)
    assert user.user_name == "alice"
    assert user.first_name == "Alice"


def test_get_or_create_user_by_telegram_idempotent(tmp_db: Path) -> None:
    uid1 = identity.get_or_create_user_by_telegram(123456, user_name="alice")
    uid2 = identity.get_or_create_user_by_telegram(123456, user_name="alice")
    assert uid1 == uid2


def test_find_user_id_by_provider_returns_none_when_missing(tmp_db: Path) -> None:
    assert identity.find_user_id_by_provider("telegram", "999") is None


def test_link_provider_to_existing_user(tmp_db: Path) -> None:
    uid = identity.get_or_create_user_by_telegram(111, user_name="u1")
    identity.link_provider(uid, "email", "u1@example.com", credential_hash="hash")
    assert identity.find_user_id_by_provider("email", "u1@example.com") == uid


def test_link_provider_conflict_raises(tmp_db: Path) -> None:
    uid_a = identity.get_or_create_user_by_telegram(111)
    uid_b = identity.get_or_create_user_by_telegram(222)
    identity.link_provider(uid_a, "email", "shared@example.com", credential_hash="h")
    with pytest.raises(ProviderAlreadyLinked) as exc:
        identity.link_provider(uid_b, "email", "shared@example.com", credential_hash="h2")
    assert exc.value.existing_user_id == uid_a


def test_link_provider_idempotent_for_same_user(tmp_db: Path) -> None:
    uid = identity.get_or_create_user_by_telegram(111)
    identity.link_provider(uid, "email", "x@y.com", credential_hash="h")
    identity.link_provider(uid, "email", "x@y.com", credential_hash="h")  # должно не падать
    providers = identity.list_providers(uid)
    assert len([p for p in providers if p["provider"] == "email"]) == 1


def test_register_email_creates_user(tmp_db: Path) -> None:
    uid = identity.get_or_create_user_by_email(
        "alice@example.com", credential_hash="bcrypt-hash", first_name="Alice"
    )
    user = identity.get_user(uid)
    assert user.first_name == "Alice"
    providers = identity.list_providers(uid)
    assert any(p["provider"] == "email" and p["identifier"] == "alice@example.com" for p in providers)


def test_register_email_duplicate_raises(tmp_db: Path) -> None:
    identity.get_or_create_user_by_email("dup@example.com", credential_hash="h")
    with pytest.raises(EmailAlreadyRegistered):
        identity.get_or_create_user_by_email("dup@example.com", credential_hash="h2")


def test_get_user_unknown_raises(tmp_db: Path) -> None:
    with pytest.raises(UserNotFound):
        identity.get_user(99999)


def test_unlink_and_relink(tmp_db: Path) -> None:
    uid = identity.get_or_create_user_by_telegram(111)
    identity.link_provider(uid, "email", "a@b.com", credential_hash="h")
    identity.unlink_provider(uid, "email", "a@b.com")
    assert identity.find_user_id_by_provider("email", "a@b.com") is None
    identity.link_provider(uid, "email", "a@b.com", credential_hash="h")
    assert identity.find_user_id_by_provider("email", "a@b.com") == uid


def test_legacy_telegram_user_picked_up_when_users_row_exists(tmp_db: Path) -> None:
    """Симулируем юзера, который остался без auth_providers (миграция не зацепила)."""
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (777, "legacy", "L", 100, "2026-01-01"),
        )
        con.commit()
    uid = identity.get_or_create_user_by_telegram(777, user_name="legacy")
    assert uid == 777
    assert identity.find_user_id_by_provider("telegram", "777") == 777
