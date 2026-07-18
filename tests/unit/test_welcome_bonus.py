"""Тесты welcome-бонуса: services/welcome_bonus.py + интеграция с identity/refill."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services import balance, identity


def _welcome_rows(db_path: Path, user_id: int) -> list:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        return con.execute(
            "SELECT * FROM refills WHERE user_id=? AND source_type='welcome_bonus'",
            (user_id,),
        ).fetchall()


# ── grant_welcome_bonus (unit) ───────────────────────────────────────────────

def test_grant_credits_balance_and_writes_refill(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    from services.welcome_bonus import grant_welcome_bonus

    user_id = identity._create_user(first_name="test")
    granted = grant_welcome_bonus(user_id)

    assert granted == 100  # рубли, без конвертации
    assert balance.get_balance(user_id) == 100
    rows = _welcome_rows(tmp_db, user_id)
    assert len(rows) == 1
    assert rows[0]["amount"] == 100
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["payment_id"] is None


def test_grant_is_idempotent(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    from services.welcome_bonus import grant_welcome_bonus

    user_id = identity._create_user(first_name="test")
    grant_welcome_bonus(user_id)
    second = grant_welcome_bonus(user_id)

    assert second == 0
    assert balance.get_balance(user_id) == 100
    assert len(_welcome_rows(tmp_db, user_id)) == 1


def test_grant_disabled_when_zero(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 0, raising=False)
    from services.welcome_bonus import grant_welcome_bonus

    user_id = identity._create_user(first_name="test")
    assert grant_welcome_bonus(user_id) == 0
    assert balance.get_balance(user_id) == 0
    assert _welcome_rows(tmp_db, user_id) == []


# ── интеграция с identity (кто получает бонус) ──────────────────────────────

def test_new_telegram_user_gets_bonus(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    user_id = identity.get_or_create_user_by_telegram(tg_id=901, user_name="u1")
    assert balance.get_balance(user_id) == 100
    assert len(_welcome_rows(tmp_db, user_id)) == 1


def test_existing_telegram_user_no_second_bonus(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    first = identity.get_or_create_user_by_telegram(tg_id=902, user_name="u2")
    second = identity.get_or_create_user_by_telegram(tg_id=902, user_name="u2")
    assert first == second
    assert balance.get_balance(first) == 100
    assert len(_welcome_rows(tmp_db, first)) == 1


def test_new_email_user_gets_bonus(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    user_id = identity.get_or_create_user_by_email(
        "user@example.com", credential_hash="x" * 32
    )
    assert balance.get_balance(user_id) == 100


def test_new_verified_phone_user_gets_bonus(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    user_id = identity.find_or_create_user_by_phone("+79990000001", verified=True)
    assert balance.get_balance(user_id) == 100


def test_guest_phone_user_no_bonus(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    user_id = identity.find_or_create_user_by_phone("+79990000002")  # verified=False
    assert balance.get_balance(user_id) == 0
    assert _welcome_rows(tmp_db, user_id) == []


def test_raw_create_user_no_bonus(tmp_db, monkeypatch):
    """_create_user сам по себе не начисляет — этим покрыт и партнёрский API
    (services/auth_api.py вызывает _create_user напрямую)."""
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    user_id = identity._create_user(first_name="api-end-user")
    assert balance.get_balance(user_id) == 0
    assert _welcome_rows(tmp_db, user_id) == []


def test_merge_guest_into_registered_no_double_bonus(tmp_db, monkeypatch):
    """Гость (verified=False, без бонуса) мерджится в полноценный аккаунт —
    бонус не задваивается."""
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    identity.find_or_create_user_by_phone("+79990000003")  # guest, без бонуса
    target_id = identity.get_or_create_user_by_telegram(tg_id=903, user_name="u3")
    identity.link_phone_provider(target_id, "+79990000003", set_verified=True)
    assert balance.get_balance(target_id) == 100
    assert len(_welcome_rows(tmp_db, target_id)) == 1


# ── совместимость с реф-бонусом ─────────────────────────────────────────────

def test_referral_bonus_survives_welcome_bonus(tmp_db, monkeypatch):
    """Welcome-строка не должна занимать слот «первого пополнения»: реферер
    обязан получить 30% с первого РЕАЛЬНОГО депозита приглашённого."""
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    from services import refill
    from utils.sqlite3 import update_user

    referrer_id = identity.get_or_create_user_by_telegram(tg_id=910, user_name="ref")
    user_id = identity.get_or_create_user_by_telegram(tg_id=911, user_name="newbie")
    update_user(id=user_id, ref_id=referrer_id)

    res = refill.finalize_with_referral_bonus(user_id, 1_000)  # первый реальный депозит

    assert res.was_newly_finalized
    assert res.referrer_id == referrer_id
    assert res.referrer_bonus == 300  # 30% от 1 000 ₽
