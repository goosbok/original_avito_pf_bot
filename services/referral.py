"""Партнерская программа: ссылки-кампании, реф-коды, атрибуция, статистика.

Реф-код: "<user_id>-<slug>" (например "42-youtube"). Слаг уникален только
внутри одного пользователя. Битый слаг при валидном user_id — атрибуция
к партнеру без ссылки (ref_link_id NULL, глобальный процент).
"""
from __future__ import annotations

import re
import secrets
import sqlite3 as _sqlite3
import string

from services.db import connect
from utils.other import get_date

SLUG_RE = re.compile(r"^[a-z0-9_-]{3,32}$")
MAX_ACTIVE_LINKS = 10
_MAX_SLUG_RETRIES = 5
_RANDOM_ALPHABET = string.ascii_lowercase + string.digits


class SlugInvalid(ValueError):
    pass


class SlugTaken(ValueError):
    pass


class LinkLimitReached(ValueError):
    pass


def normalize_slug(slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise SlugInvalid(
            "слаг: 3-32 символа, только латиница в нижнем регистре, цифры, '-' и '_'"
        )
    return slug


def generate_slug() -> str:
    return "".join(secrets.choice(_RANDOM_ALPHABET) for _ in range(8))


def _row_to_link(row) -> dict:
    return dict(row)


def create_link(user_id: int, slug: str | None = None) -> dict:
    """Создать ссылку. slug=None → случайный. Бросает SlugInvalid/SlugTaken/LinkLimitReached."""
    explicit = slug is not None
    norm = normalize_slug(slug) if explicit else generate_slug()
    with connect() as con:
        active = con.execute(
            "SELECT COUNT(*) AS c FROM referral_links "
            "WHERE user_id = ? AND archived_at IS NULL",
            (user_id,),
        ).fetchone()["c"]
        if active >= MAX_ACTIVE_LINKS:
            raise LinkLimitReached(f"не больше {MAX_ACTIVE_LINKS} активных ссылок")
        # Проверка лимита и вставка не атомарны на одном соединении (SQLite
        # DEFERRED-транзакция берёт write-lock только на INSERT). Для трафика
        # бота (один юзер вряд ли шлёт параллельные create_link) это best-effort
        # UX-кап, а не жёсткий инвариант — гонка максимум даст +1 к лимиту.
        for _attempt in range(_MAX_SLUG_RETRIES):
            try:
                cur = con.execute(
                    "INSERT INTO referral_links(user_id, slug, created_at) "
                    "VALUES (?, ?, ?)",
                    (user_id, norm, get_date()),
                )
                con.commit()
                break
            except _sqlite3.IntegrityError as exc:
                # Только UNIQUE(user_id, slug) — это занятый слаг. Любой другой
                # IntegrityError (например FK на несуществующего user_id) — баг
                # вызывающего: пробрасываем как есть, а не выдаём фейковый SlugTaken.
                if "UNIQUE constraint failed" not in str(exc):
                    raise
                if explicit:
                    raise SlugTaken(f"слаг '{norm}' уже занят у этого пользователя")
                norm = generate_slug()  # коллизия случайного — перегенерим
        else:
            raise SlugTaken("не удалось подобрать случайный слаг")
        row = con.execute(
            "SELECT * FROM referral_links WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_link(row)


def archive_link(user_id: int, link_id: int) -> bool:
    """Архивировать свою ссылку. False — нет такой/чужая/уже архивная."""
    with connect() as con:
        cur = con.execute(
            "UPDATE referral_links SET archived_at = ? "
            "WHERE id = ? AND user_id = ? AND archived_at IS NULL",
            (get_date(), link_id, user_id),
        )
        con.commit()
    return cur.rowcount == 1


def list_links(user_id: int) -> list[dict]:
    """Все ссылки юзера (включая архивные) со статистикой."""
    with connect() as con:
        rows = con.execute(
            "SELECT l.*, "
            " (SELECT COUNT(*) FROM users u WHERE u.ref_link_id = l.id) AS registrations, "
            " (SELECT COALESCE(SUM(b.amount), 0) FROM referral_bonuses b "
            "  WHERE b.link_id = l.id) AS earned "
            "FROM referral_links l WHERE l.user_id = ? ORDER BY l.id",
            (user_id,),
        ).fetchall()
    return [_row_to_link(r) for r in rows]


def get_default_link(user_id: int) -> dict | None:
    """Первая активная ссылка юзера или None. Read-only: профиль бота ничего
    не создает — ссылки заводятся только явно (на сайте)."""
    with connect() as con:
        row = con.execute(
            "SELECT * FROM referral_links "
            "WHERE user_id = ? AND archived_at IS NULL ORDER BY id LIMIT 1",
            (user_id,),
        ).fetchone()
    return _row_to_link(row) if row is not None else None
