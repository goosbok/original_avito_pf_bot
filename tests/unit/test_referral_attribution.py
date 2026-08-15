"""Разбор реф-кода, атрибуция, клики, проценты, сводка."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _mk_user(tmp_db: Path, user_id: int, ref_id: int | None = None) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, balance, ref_id) VALUES (?, 0, ?)",
            (user_id, ref_id),
        )


def test_parse_ref_code() -> None:
    from services.referral import parse_ref_code
    assert parse_ref_code("42-youtube") == (42, "youtube")
    assert parse_ref_code("42") == (42, None)
    assert parse_ref_code("42-") == (42, None)  # пустой слаг → атрибуция без ссылки (спека, п.3)
    assert parse_ref_code("abc") == (None, None)
    assert parse_ref_code("") == (None, None)
    assert parse_ref_code("9" * 20) == (None, None)        # > int64 — иначе OverflowError в sqlite
    assert parse_ref_code("9" * 20 + "-x") == (None, None)
    assert parse_ref_code("42-YOU tube") == (42, "you tube")  # чистит регистр, валидность решает resolve


def test_resolve_full_code(tmp_db: Path) -> None:
    from services.referral import create_link, resolve_ref_code
    _mk_user(tmp_db, 42)
    link = create_link(42, "youtube")
    assert resolve_ref_code("42-youtube") == (42, link["id"])


def test_resolve_unknown_user(tmp_db: Path) -> None:
    from services.referral import resolve_ref_code
    assert resolve_ref_code("999-youtube") is None


def test_resolve_bad_slug_falls_back_to_user(tmp_db: Path) -> None:
    from services.referral import resolve_ref_code
    _mk_user(tmp_db, 42)
    assert resolve_ref_code("42-tyypo") == (42, None)
    assert resolve_ref_code("42") == (42, None)


def test_resolve_archived_link_falls_back(tmp_db: Path) -> None:
    from services.referral import archive_link, create_link, resolve_ref_code
    _mk_user(tmp_db, 42)
    link = create_link(42, "youtube")
    archive_link(42, link["id"])
    assert resolve_ref_code("42-youtube") == (42, None)


def test_attribute_ok(tmp_db: Path) -> None:
    from services.referral import attribute, create_link
    _mk_user(tmp_db, 42)
    _mk_user(tmp_db, 100)
    link = create_link(42, "youtube")
    assert attribute(100, "42-youtube") == ("ok", 42)
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT ref_id, ref_link_id FROM users WHERE id = 100"
        ).fetchone()
    assert row == (42, link["id"])


def test_attribute_self(tmp_db: Path) -> None:
    from services.referral import attribute
    _mk_user(tmp_db, 42)
    assert attribute(42, "42") == ("self", None)


def test_attribute_already(tmp_db: Path) -> None:
    from services.referral import attribute
    _mk_user(tmp_db, 42)
    _mk_user(tmp_db, 43)
    _mk_user(tmp_db, 100, ref_id=43)
    assert attribute(100, "42") == ("already", 43)
    with sqlite3.connect(tmp_db) as con:
        assert con.execute("SELECT ref_id FROM users WHERE id = 100").fetchone()[0] == 43


def test_attribute_unknown(tmp_db: Path) -> None:
    from services.referral import attribute
    _mk_user(tmp_db, 100)
    assert attribute(100, "999") == ("unknown", None)
    assert attribute(100, "мусор") == ("unknown", None)


def test_register_click(tmp_db: Path) -> None:
    from services.referral import create_link, register_click
    _mk_user(tmp_db, 42)
    link = create_link(42, "youtube")
    register_click("42-youtube")
    register_click("42-youtube")
    register_click("42-tyypo")   # нет ссылки — молча ничего
    register_click("мусор")      # мусор — молча ничего
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT clicks FROM referral_links WHERE id = ?", (link["id"],)
        ).fetchone()[0] == 2


def test_bonus_percent_global_and_custom(tmp_db: Path) -> None:
    from services.referral import create_link, get_bonus_percent, set_custom_percent
    _mk_user(tmp_db, 42)
    link = create_link(42, "youtube")
    assert get_bonus_percent(None) == 10          # дефолт из _SETTING_DEFAULTS
    assert get_bonus_percent(link["id"]) == 10    # custom не задан → глобальный
    assert set_custom_percent(link["id"], 25) is True
    assert get_bonus_percent(link["id"]) == 25
    assert set_custom_percent(link["id"], None) is True   # сброс
    assert get_bonus_percent(link["id"]) == 10
    assert set_custom_percent(9999, 25) is False


def test_summary(tmp_db: Path) -> None:
    from services.referral import create_link, get_summary
    _mk_user(tmp_db, 42)
    link = create_link(42, "youtube")
    _mk_user(tmp_db, 100)
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "UPDATE users SET ref_id = 42, ref_link_id = ? WHERE id = 100",
            (link["id"],),
        )
        con.execute(
            "INSERT INTO referral_bonuses(referrer_id, referred_user_id, refill_id,"
            " link_id, amount, percent, created_at)"
            " VALUES (42, 100, NULL, ?, 150, 10, '2026-07-18')",
            (link["id"],),
        )
    s = get_summary(42)
    assert s["percent"] == 10
    assert s["referrals_count"] == 1
    assert s["total_earned"] == 150
    assert s["links"][0]["registrations"] == 1
    assert s["links"][0]["earned"] == 150
    assert s["links"][0]["effective_percent"] == 10


def test_list_bonuses(tmp_db: Path) -> None:
    from services.referral import list_bonuses
    _mk_user(tmp_db, 42)
    with sqlite3.connect(tmp_db) as con:
        for i in range(3):
            con.execute(
                "INSERT INTO referral_bonuses(referrer_id, referred_user_id, refill_id,"
                " link_id, amount, percent, created_at)"
                " VALUES (42, 100, NULL, NULL, ?, 10, '2026-07-18')",
                (100 + i,),
            )
    rows = list_bonuses(42, limit=2, offset=0)
    assert len(rows) == 2
    assert rows[0]["amount"] == 102  # свежие первыми
