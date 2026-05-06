from pathlib import Path

import pytest

from services import applications, auth_api, auth_email, identity
from services.exceptions import InvalidAPIKey


def test_authorize_creates_internal_user(tmp_db: Path):
    dev = auth_email.register("dev@example.com", "password123")
    app = applications.create(dev, "MyBot")
    result = auth_api.authorize(app.api_key, "external-user-1")
    assert result.application_id == app.application.id
    assert result.end_user_internal_id != dev  # отдельный юзер
    assert identity.find_user_id_by_provider(f"api:{app.application.id}", "external-user-1") \
        == result.end_user_internal_id


def test_authorize_idempotent_for_same_end_user(tmp_db: Path):
    dev = auth_email.register("dev@example.com", "password123")
    app = applications.create(dev, "MyBot")
    r1 = auth_api.authorize(app.api_key, "user-X")
    r2 = auth_api.authorize(app.api_key, "user-X")
    assert r1.end_user_internal_id == r2.end_user_internal_id


def test_authorize_different_apps_create_different_users(tmp_db: Path):
    dev = auth_email.register("dev@example.com", "password123")
    app1 = applications.create(dev, "Bot1")
    app2 = applications.create(dev, "Bot2")
    r1 = auth_api.authorize(app1.api_key, "user-X")
    r2 = auth_api.authorize(app2.api_key, "user-X")
    assert r1.end_user_internal_id != r2.end_user_internal_id


def test_authorize_invalid_key(tmp_db: Path):
    with pytest.raises(InvalidAPIKey):
        auth_api.authorize("sk_live_bogus", "user-1")


def test_authorize_revoked_key(tmp_db: Path):
    dev = auth_email.register("dev@example.com", "password123")
    app = applications.create(dev, "MyBot")
    applications.revoke(app.application.id, dev)
    with pytest.raises(InvalidAPIKey):
        auth_api.authorize(app.api_key, "user-1")


def test_authorize_missing_inputs(tmp_db: Path):
    with pytest.raises(InvalidAPIKey):
        auth_api.authorize("", "user-1")
    with pytest.raises(InvalidAPIKey):
        auth_api.authorize("sk_live_x", "")
