from pathlib import Path

import pytest

from services import applications, auth_email
from services.exceptions import ApplicationNotFound


def test_create_returns_plaintext_key(tmp_db: Path):
    uid = auth_email.register("dev@example.com", "password123")
    result = applications.create(uid, "MyBot")
    assert result.api_key.startswith("sk_live_")
    assert len(result.api_key) > 20
    assert result.application.name == "MyBot"
    assert result.application.api_key_prefix == result.api_key[:12]


def test_find_by_api_key_returns_app(tmp_db: Path):
    uid = auth_email.register("dev@example.com", "password123")
    result = applications.create(uid, "MyBot")
    found = applications.find_by_api_key(result.api_key)
    assert found is not None
    assert found.id == result.application.id


def test_find_by_unknown_key_returns_none(tmp_db: Path):
    assert applications.find_by_api_key("sk_live_unknown") is None


def test_list_for_user(tmp_db: Path):
    uid = auth_email.register("dev@example.com", "password123")
    a = applications.create(uid, "App A")
    b = applications.create(uid, "App B")
    apps = applications.list_for_user(uid)
    assert {x.id for x in apps} == {a.application.id, b.application.id}


def test_revoke_soft_deletes(tmp_db: Path):
    uid = auth_email.register("dev@example.com", "password123")
    result = applications.create(uid, "Temp")
    applications.revoke(result.application.id, uid)
    assert applications.find_by_api_key(result.api_key) is None
    # Но GET всё равно вернёт (soft delete)
    app = applications.get(result.application.id)
    assert app.revoked_at is not None


def test_revoke_by_non_owner_raises(tmp_db: Path):
    uid_a = auth_email.register("a@example.com", "password123")
    uid_b = auth_email.register("b@example.com", "password123")
    result = applications.create(uid_a, "AppA")
    with pytest.raises(ApplicationNotFound):
        applications.revoke(result.application.id, uid_b)


def test_create_empty_name_raises(tmp_db: Path):
    uid = auth_email.register("dev@example.com", "password123")
    with pytest.raises(ValueError):
        applications.create(uid, "  ")
