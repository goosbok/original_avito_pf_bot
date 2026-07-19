"""Ссылки партнерки: валидация слагов, создание, лимит, архив."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _mk_user(tmp_db: Path, user_id: int) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (?, 0)", (user_id,))


def test_normalize_slug_valid() -> None:
    from services.referral import normalize_slug
    assert normalize_slug("  YouTube_1 ") == "youtube_1"


@pytest.mark.parametrize("bad", ["ab", "x" * 33, "про-мо", "has space", "a.b", ""])
def test_normalize_slug_invalid(bad: str) -> None:
    from services.referral import SlugInvalid, normalize_slug
    with pytest.raises(SlugInvalid):
        normalize_slug(bad)


def test_generate_slug_shape() -> None:
    from services.referral import generate_slug
    s = generate_slug()
    assert len(s) == 8 and s == s.lower()


def test_create_link_custom_and_random(tmp_db: Path) -> None:
    from services.referral import create_link
    _mk_user(tmp_db, 1)
    link = create_link(1, "youtube")
    assert link["slug"] == "youtube" and link["user_id"] == 1
    rnd = create_link(1, None)
    assert len(rnd["slug"]) == 8


def test_create_link_duplicate_same_user(tmp_db: Path) -> None:
    from services.referral import SlugTaken, create_link
    _mk_user(tmp_db, 1)
    create_link(1, "promo")
    with pytest.raises(SlugTaken):
        create_link(1, "PROMO")


def test_create_link_same_slug_other_user_ok(tmp_db: Path) -> None:
    from services.referral import create_link
    _mk_user(tmp_db, 1)
    _mk_user(tmp_db, 2)
    create_link(1, "promo")
    assert create_link(2, "promo")["slug"] == "promo"


def test_create_link_limit(tmp_db: Path) -> None:
    from services.referral import LinkLimitReached, MAX_ACTIVE_LINKS, create_link
    _mk_user(tmp_db, 1)
    for i in range(MAX_ACTIVE_LINKS):
        create_link(1, f"slug-{i}")
    with pytest.raises(LinkLimitReached):
        create_link(1, "one-more")


def test_archive_link_frees_limit_but_not_slug(tmp_db: Path) -> None:
    from services.referral import SlugTaken, archive_link, create_link, list_links
    import pytest as _pytest
    _mk_user(tmp_db, 1)
    link = create_link(1, "promo")
    assert archive_link(1, link["id"]) is True
    assert list_links(1)[0]["archived_at"] is not None
    # Слаг остается занятым (UNIQUE в таблице) — переиспользовать нельзя
    with _pytest.raises(SlugTaken):
        create_link(1, "promo")


def test_archive_foreign_link_fails(tmp_db: Path) -> None:
    from services.referral import archive_link, create_link
    _mk_user(tmp_db, 1)
    _mk_user(tmp_db, 2)
    link = create_link(1, "promo")
    assert archive_link(2, link["id"]) is False


def test_restore_link(tmp_db: Path) -> None:
    from services.referral import archive_link, create_link, list_links, restore_link
    _mk_user(tmp_db, 1)
    link = create_link(1, "promo")
    assert archive_link(1, link["id"]) is True
    assert list_links(1)[0]["archived_at"] is not None
    assert restore_link(1, link["id"]) is True
    assert list_links(1)[0]["archived_at"] is None
    # повторный restore на уже активную → False
    assert restore_link(1, link["id"]) is False


def test_restore_foreign_link_fails(tmp_db: Path) -> None:
    from services.referral import archive_link, create_link, restore_link
    _mk_user(tmp_db, 1)
    _mk_user(tmp_db, 2)
    link = create_link(1, "promo")
    archive_link(1, link["id"])
    assert restore_link(2, link["id"]) is False


def test_create_link_unknown_user_raises_integrity_not_slugtaken(tmp_db: Path) -> None:
    """FK на несуществующего user_id — это баг вызывающего, НЕ SlugTaken."""
    import sqlite3
    from services.referral import create_link
    with pytest.raises(sqlite3.IntegrityError):   # explicit-slug path
        create_link(999, "whatever")
    with pytest.raises(sqlite3.IntegrityError):   # random-slug path (must not burn 5 retries)
        create_link(999, None)


def test_get_default_link_readonly(tmp_db: Path) -> None:
    """Ничего не создает: профиль бота — read-only путь."""
    from services.referral import create_link, get_default_link
    _mk_user(tmp_db, 1)
    assert get_default_link(1) is None
    link = create_link(1, "promo")
    assert get_default_link(1)["id"] == link["id"]
