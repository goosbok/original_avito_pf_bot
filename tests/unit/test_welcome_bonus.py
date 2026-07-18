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
