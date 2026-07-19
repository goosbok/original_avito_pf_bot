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
            "метка: 3-32 символа, только латиница в нижнем регистре, цифры, '-' и '_'"
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
                    raise SlugTaken(f"метка '{norm}' уже занята у этого пользователя")
                norm = generate_slug()  # коллизия случайного — перегенерим
        else:
            raise SlugTaken("не удалось подобрать случайную метку")
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


# ---------------------------------------------------------------- реф-коды

_CODE_RE = re.compile(r"^(\d+)(?:-(.*))?$")
_MAX_ID_DIGITS = 12  # sqlite биндит только int64: длиннее — мусор, а не OverflowError


def parse_ref_code(code: str) -> tuple[int | None, str | None]:
    """"42-youtube" → (42, "youtube"); "42" и "42-" → (42, None); мусор → (None, None)."""
    m = _CODE_RE.match((code or "").strip())
    if m is None or len(m.group(1)) > _MAX_ID_DIGITS:
        return None, None
    slug = m.group(2)
    return int(m.group(1)), (slug.lower() if slug else None)


def resolve_ref_code(code: str) -> tuple[int, int | None] | None:
    """→ (referrer_id, link_id | None), или None если партнер не существует.

    Слаг битый/архивный/чужой → (referrer_id, None): атрибуция «в общем»."""
    referrer_id, slug = parse_ref_code(code)
    if referrer_id is None:
        return None
    with connect() as con:
        user = con.execute(
            "SELECT id FROM users WHERE id = ?", (referrer_id,)
        ).fetchone()
        if user is None:
            return None
        link_id = None
        if slug:
            row = con.execute(
                "SELECT id FROM referral_links "
                "WHERE user_id = ? AND slug = ? AND archived_at IS NULL",
                (referrer_id, slug),
            ).fetchone()
            if row is not None:
                link_id = int(row["id"])
    return referrer_id, link_id


def attribute(user_id: int, code: str) -> tuple[str, int | None]:
    """Одноразовая атрибуция реферала. → (status, referrer_id):

    - ("ok", referrer_id)     — привязали;
    - ("self", None)          — попытка привязать себя;
    - ("already", ref_id)     — у юзера уже есть реферер (не перезаписываем);
    - ("unknown", None)       — код битый или партнер не существует.
    """
    resolved = resolve_ref_code(code)
    if resolved is None:
        return "unknown", None
    referrer_id, link_id = resolved
    if referrer_id == user_id:
        return "self", None
    with connect() as con:
        row = con.execute(
            "SELECT ref_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return "unknown", None
        if row["ref_id"] is not None:
            return "already", int(row["ref_id"])
        ref_row = con.execute(
            "SELECT user_name FROM users WHERE id = ?", (referrer_id,)
        ).fetchone()
        cur = con.execute(
            "UPDATE users SET ref_id = ?, ref_link_id = ?, ref_user_name = ? "
            "WHERE id = ? AND ref_id IS NULL",
            (referrer_id, link_id, ref_row["user_name"], user_id),
        )
        con.commit()
        if cur.rowcount == 0:
            # Гонка: между SELECT и UPDATE другой процесс уже проставил ref_id
            # (бот и web — отдельные процессы на одном SQLite-файле). DB-инвариант
            # «одноразовая атрибуция» соблюдён; возвращаем честный статус, не ложный "ok".
            winner = con.execute(
                "SELECT ref_id FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            existing = winner["ref_id"] if winner else None
            if existing is not None:
                return "already", int(existing)
            return "unknown", None
    return "ok", referrer_id


def register_click(code: str) -> None:
    """+1 клик, если код указывает на живую ссылку. Иначе — молча ничего."""
    resolved = resolve_ref_code(code)
    if resolved is None or resolved[1] is None:
        return
    with connect() as con:
        con.execute(
            "UPDATE referral_links SET clicks = clicks + 1 WHERE id = ?",
            (resolved[1],),
        )
        con.commit()


# ---------------------------------------------------------------- проценты

def get_global_percent() -> int:
    from utils.sqlite3 import get_setting
    try:
        return int(get_setting("ref_percent"))
    except (TypeError, ValueError):
        return 10


def get_bonus_percent(link_id: int | None) -> int:
    """custom_percent ссылки, если задан; иначе глобальный ref_percent."""
    if link_id is not None:
        with connect() as con:
            row = con.execute(
                "SELECT custom_percent FROM referral_links WHERE id = ?",
                (link_id,),
            ).fetchone()
        if row is not None and row["custom_percent"] is not None:
            return int(row["custom_percent"])
    return get_global_percent()


def set_custom_percent(link_id: int, percent: int | None) -> bool:
    """Админ: индивидуальный процент ссылки (None — сброс). False — нет ссылки."""
    with connect() as con:
        cur = con.execute(
            "UPDATE referral_links SET custom_percent = ? WHERE id = ?",
            (percent, link_id),
        )
        con.commit()
    return cur.rowcount == 1


# ---------------------------------------------------------------- статистика

def referrals_count(user_id: int) -> int:
    with connect() as con:
        return con.execute(
            "SELECT COUNT(*) AS c FROM users WHERE ref_id = ?", (user_id,)
        ).fetchone()["c"]


def get_summary(user_id: int) -> dict:
    """Сводка для GET /api/me/referral и админской карточки."""
    g = get_global_percent()
    links = list_links(user_id)
    for link in links:
        link["effective_percent"] = (
            link["custom_percent"] if link["custom_percent"] is not None else g
        )
    with connect() as con:
        earned = con.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM referral_bonuses "
            "WHERE referrer_id = ?",
            (user_id,),
        ).fetchone()["s"]
    return {
        "percent": g,
        "links": links,
        "referrals_count": referrals_count(user_id),
        "total_earned": earned,
    }


def list_bonuses(user_id: int, *, limit: int = 50, offset: int = 0) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT b.id, b.referred_user_id, b.refill_id, b.link_id, b.amount, "
            " b.percent, b.created_at, l.slug AS link_slug "
            "FROM referral_bonuses b "
            "LEFT JOIN referral_links l ON l.id = b.link_id "
            "WHERE b.referrer_id = ? ORDER BY b.id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]
