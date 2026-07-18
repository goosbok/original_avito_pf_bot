# Referral Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Партнерская программа по спеке `docs/superpowers/specs/2026-07-18-referral-program-design.md`: мультиссылки-кампании с реф-кодом `<user_id>-<slug>`, 10% с каждого пополнения (с per-link оверрайдом от админа), управление на сайте, атрибуция из бота и с сайта.

**Architecture:** Новый сервис `services/referral.py` — единственное место, где живут слаги, разбор реф-кодов, атрибуция и статистика. `services/refill.py` берет из него процент и пишет историю в `referral_bonuses`. Бот (`handlers/main_start.py`) и веб-регистрация (`auth_phone`/`auth_email`) зовут одну и ту же `referral.attribute()`. REST — новый роутер `web/routers/referral.py`. UI — новая страница `Referral.jsx` в SPA + секция в `AdminUserDrawer`.

**Tech Stack:** Python 3 / aiogram 2.25 / FastAPI / SQLite / React (JSX без сборки, глобальные window-компоненты).

**Как гонять тесты (правило проекта — только в Docker):**
```bash
docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/<file>.py -v
```
Контейнер должен быть запущен (`make up`). Полный прогон: `docker exec original_avito_pf_bot-api-1 python -m pytest -q`.

**Git:** ветка `feature/referral-program` от `dev`. Conventional Commits, английский, без Co-Authored-By и watermark-подписей.

---

## Карта файлов

| Файл | Действие | Ответственность |
|---|---|---|
| `utils/sqlite3.py` | Modify | DDL двух таблиц, `users.ref_link_id`, дефолт `ref_percent` |
| `services/referral.py` | Create | Слаги, ссылки, реф-коды, атрибуция, статистика, проценты |
| `services/refill.py` | Modify | `finalize_with_referral_bonus`: 10% с каждого, credit + история |
| `handlers/main_start.py` | Modify | Ветка `/start ref_<код>` |
| `handlers/profile.py` | Modify | Реф-ссылка из дефолтной ссылки, счетчик по `ref_id` |
| `services/identity.py` | Modify | Перенос `ref_id` при мердже phone-only |
| `web/routers/auth_phone.py` | Modify | `ref_code` в verify |
| `web/routers/auth_email.py` + `web/schemas.py` | Modify | `ref_code` в register-verify |
| `web/routers/referral.py` | Create | `/api/me/referral*`, `/api/referral/click`, админ-эндпоинты |
| `web/main.py` | Modify | Подключение роутера |
| `web/static/app.jsx` | Modify | Захват `?ref`, beacon, route `referral` |
| `web/static/components/PhoneLogin.jsx`, `Auth.jsx` | Modify | Передача `ref_code` |
| `web/static/components/Referral.jsx` | Create | Страница «Партнерка» |
| `web/static/components/AppHeader.jsx` | Modify | Пункт навигации |
| `web/static/index.html` | Modify | `<script>` для Referral.jsx |
| `web/static/components/AdminUsers.jsx` | Modify | Секция партнерки в drawer |
| `web/landing/index.html` | Modify | Проброс `?ref` в ссылки на ЛК |
| `tests/unit/test_referral_links.py` | Create | Слаги/ссылки |
| `tests/unit/test_referral_attribution.py` | Create | Разбор кода, атрибуция, клики |
| `tests/unit/test_refill.py` | Modify | Реф-бонусы по новой модели |
| `tests/unit/test_referral_api.py` | Create | REST API |
| `tests/unit/test_identity_phone.py` | Modify | Перенос ref при мердже |

---

### Task 0: Ветка

- [ ] **Step 1: Создать ветку от dev**

```bash
git checkout dev && git pull && git checkout -b feature/referral-program
```

---

### Task 1: Схема БД

**Files:**
- Modify: `utils/sqlite3.py` (`get_schema_statements` ~строка 769, `apply_phase2_migrations` ~строка 1010, `_SETTING_DEFAULTS` ~строка 179)
- Test: `tests/unit/test_referral_schema.py` (Create)

- [ ] **Step 1: Написать падающий тест на схему**

Создать `tests/unit/test_referral_schema.py`:

```python
"""Схема партнерской программы: таблицы referral_links/referral_bonuses, users.ref_link_id."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _columns(tmp_db: Path, table: str) -> set[str]:
    with sqlite3.connect(tmp_db) as con:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def test_referral_links_table_exists(tmp_db: Path) -> None:
    assert _columns(tmp_db, "referral_links") == {
        "id", "user_id", "slug", "clicks", "custom_percent", "created_at", "archived_at",
    }


def test_referral_bonuses_table_exists(tmp_db: Path) -> None:
    assert _columns(tmp_db, "referral_bonuses") == {
        "id", "referrer_id", "referred_user_id", "refill_id", "link_id",
        "amount", "percent", "created_at",
    }


def test_users_has_ref_link_id(tmp_db: Path) -> None:
    assert "ref_link_id" in _columns(tmp_db, "users")


def test_slug_unique_per_user_not_globally(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        con.execute("INSERT INTO users(id, balance) VALUES (2, 0)")
        con.execute(
            "INSERT INTO referral_links(user_id, slug, created_at) VALUES (1, 'promo', '2026-07-18')"
        )
        # Другой юзер — тот же слаг: ОК
        con.execute(
            "INSERT INTO referral_links(user_id, slug, created_at) VALUES (2, 'promo', '2026-07-18')"
        )
        # Тот же юзер — тот же слаг (регистр не важен): IntegrityError
        try:
            con.execute(
                "INSERT INTO referral_links(user_id, slug, created_at) VALUES (1, 'PROMO', '2026-07-18')"
            )
            assert False, "expected IntegrityError"
        except sqlite3.IntegrityError:
            pass
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_schema.py -v`
Expected: FAIL (`no such table: referral_links`)

- [ ] **Step 3: Добавить DDL в `get_schema_statements()`**

В `utils/sqlite3.py` в список из `get_schema_statements()` (перед закрывающей `]`) добавить два кортежа:

```python
        (
            "referral_links",
            "CREATE TABLE IF NOT EXISTS referral_links("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "slug TEXT NOT NULL COLLATE NOCASE,"
            "clicks INTEGER NOT NULL DEFAULT 0,"
            "custom_percent INTEGER,"
            "created_at TIMESTAMP NOT NULL,"
            "archived_at TIMESTAMP,"
            "UNIQUE (user_id, slug),"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            7,
        ),
        (
            "referral_bonuses",
            "CREATE TABLE IF NOT EXISTS referral_bonuses("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "referrer_id INTEGER NOT NULL,"
            "referred_user_id INTEGER NOT NULL,"
            "refill_id INTEGER,"
            "link_id INTEGER,"
            "amount INTEGER NOT NULL,"
            "percent INTEGER NOT NULL,"
            "created_at TIMESTAMP NOT NULL)",
            8,
        ),
```

В DDL таблицы `users` (тот же файл, ~строка 777) добавить колонку перед закрывающей скобкой и поднять счетчик колонок c 10 до 11:

```python
            "CREATE TABLE users("
            "id INTEGER PRIMARY KEY,"
            "user_name TEXT,"
            "first_name TEXT,"
            "balance INTEGER DEFAULT 0,"
            "reg_date TIMESTAMP,"
            "ref_user_name TEXT,"
            "ref_id INTEGER,"
            "is_vip BOOLEN,"
            "magic TEXT,"
            "referals TEXT,"
            "ref_link_id INTEGER)",
            11,
```

⚠️ Если `tests/unit/test_db_schema.py` ассертит число колонок users — поправить там ожидание на 11.

- [ ] **Step 4: Добавить guard-миграции в `apply_phase2_migrations()`**

Перед финальным `con.commit()` в `apply_phase2_migrations()`:

```python
        # === referral program (multi-link) ===
        existing_users = {row['name'] for row in con.execute("PRAGMA table_info(users)").fetchall()}
        if 'ref_link_id' not in existing_users:
            con.execute("ALTER TABLE users ADD COLUMN ref_link_id INTEGER")
            print("users.ref_link_id added")
        con.execute(
            "CREATE TABLE IF NOT EXISTS referral_links("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "slug TEXT NOT NULL COLLATE NOCASE,"
            "clicks INTEGER NOT NULL DEFAULT 0,"
            "custom_percent INTEGER,"
            "created_at TIMESTAMP NOT NULL,"
            "archived_at TIMESTAMP,"
            "UNIQUE (user_id, slug),"
            "FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS referral_bonuses("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "referrer_id INTEGER NOT NULL,"
            "referred_user_id INTEGER NOT NULL,"
            "refill_id INTEGER,"
            "link_id INTEGER,"
            "amount INTEGER NOT NULL,"
            "percent INTEGER NOT NULL,"
            "created_at TIMESTAMP NOT NULL)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_referral_links_user "
            "ON referral_links(user_id)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_referral_bonuses_referrer "
            "ON referral_bonuses(referrer_id, id DESC)"
        )
```

(Индексы кладем сюда, а не в `get_index_statements()`, по той же причине, что и refills-индексы — см. комментарий в `get_index_statements`.)

- [ ] **Step 5: Дефолт процента**

В `_SETTING_DEFAULTS` (utils/sqlite3.py ~строка 179) добавить:

```python
    "ref_percent": "10",
```

- [ ] **Step 6: Прогнать тест**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_schema.py tests/unit/test_db_schema.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add utils/sqlite3.py tests/unit/test_referral_schema.py tests/unit/test_db_schema.py
git commit -m "feat(referral): add referral_links/referral_bonuses tables and users.ref_link_id"
```

---

### Task 2: services/referral.py — слаги и ссылки

**Files:**
- Create: `services/referral.py`
- Test: `tests/unit/test_referral_links.py`

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_referral_links.py`:

```python
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


def test_get_or_create_default_link_lazy(tmp_db: Path) -> None:
    from services.referral import get_or_create_default_link
    _mk_user(tmp_db, 1)
    a = get_or_create_default_link(1)
    b = get_or_create_default_link(1)
    assert a["id"] == b["id"]
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_links.py -v`
Expected: FAIL (`ModuleNotFoundError: services.referral`)

- [ ] **Step 3: Реализовать `services/referral.py` (часть 1)**

```python
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
        for _attempt in range(5):
            try:
                cur = con.execute(
                    "INSERT INTO referral_links(user_id, slug, created_at) "
                    "VALUES (?, ?, ?)",
                    (user_id, norm, get_date()),
                )
                con.commit()
                break
            except _sqlite3.IntegrityError:
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


def get_or_create_default_link(user_id: int) -> dict:
    """Первая активная ссылка юзера; нет ни одной — создаем со случайным слагом.

    Используется ботом (кнопка «Показать реферальную ссылку»)."""
    with connect() as con:
        row = con.execute(
            "SELECT * FROM referral_links "
            "WHERE user_id = ? AND archived_at IS NULL ORDER BY id LIMIT 1",
            (user_id,),
        ).fetchone()
    if row is not None:
        return _row_to_link(row)
    return create_link(user_id, None)
```

- [ ] **Step 4: Прогнать тесты**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_links.py -v`
Expected: PASS (все)

- [ ] **Step 5: Commit**

```bash
git add services/referral.py tests/unit/test_referral_links.py
git commit -m "feat(referral): link CRUD with per-user slugs, limit and archive"
```

---

### Task 3: services/referral.py — реф-коды, атрибуция, клики, статистика

**Files:**
- Modify: `services/referral.py`
- Test: `tests/unit/test_referral_attribution.py`

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_referral_attribution.py`:

```python
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
    assert parse_ref_code("42-") == (None, None)
    assert parse_ref_code("abc") == (None, None)
    assert parse_ref_code("") == (None, None)
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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_attribution.py -v`
Expected: FAIL (`ImportError: cannot import name 'parse_ref_code'`)

- [ ] **Step 3: Дописать `services/referral.py` (часть 2)**

Добавить в конец файла:

```python
# ---------------------------------------------------------------- реф-коды

_CODE_RE = re.compile(r"^(\d+)(?:-(.+))?$")


def parse_ref_code(code: str) -> tuple[int | None, str | None]:
    """"42-youtube" → (42, "youtube"); "42" → (42, None); мусор → (None, None)."""
    m = _CODE_RE.match((code or "").strip())
    if m is None:
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
        con.execute(
            "UPDATE users SET ref_id = ?, ref_link_id = ?, ref_user_name = ? "
            "WHERE id = ? AND ref_id IS NULL",
            (referrer_id, link_id, ref_row["user_name"], user_id),
        )
        con.commit()
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
```

- [ ] **Step 4: Прогнать тесты**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_attribution.py tests/unit/test_referral_links.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/referral.py tests/unit/test_referral_attribution.py
git commit -m "feat(referral): ref-code parsing, attribution with fallback, clicks, stats"
```

---

### Task 4: Новый расчет бонуса в services/refill.py

**Files:**
- Modify: `services/refill.py:190-246` (`_get_user_for_referral`, `finalize_with_referral_bonus`)
- Modify: `tests/unit/test_refill.py:87-127` (реферальные тесты)

- [ ] **Step 1: Переписать реферальные тесты под новую модель**

В `tests/unit/test_refill.py` заменить тесты `test_referral_bonus_first_refill_credits_referrer`, `test_referral_bonus_only_first_refill`, `test_referral_bonus_skipped_for_vip`, `test_referral_bonus_skipped_when_no_referrer`, `test_referral_bonus_referrer_does_not_exist` на:

```python
def test_referral_bonus_every_refill_credits_referrer(tmp_db: Path) -> None:
    """10% с каждого пополнения, не только первого."""
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    r1 = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert r1.referrer_bonus == 100  # 10%
    assert r1.referrer_new_balance == 100
    r2 = finalize_with_referral_bonus(user_id=2, amount=2000)
    assert r2.referrer_bonus == 200
    assert r2.referrer_new_balance == 300


def test_referral_bonus_floor_and_zero(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    r = finalize_with_referral_bonus(user_id=2, amount=109)
    assert r.referrer_bonus == 10  # floor(10.9)
    r2 = finalize_with_referral_bonus(user_id=2, amount=9)
    assert r2.referrer_bonus == 0  # floor(0.9) → ничего не пишем
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM referral_bonuses WHERE amount = 0"
        ).fetchone()[0] == 0


def test_referral_bonus_uses_link_custom_percent(tmp_db: Path) -> None:
    from services.referral import create_link, set_custom_percent
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    link = create_link(1, "vip-deal")
    set_custom_percent(link["id"], 25)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE users SET ref_link_id = ? WHERE id = 2", (link["id"],))
    r = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert r.referrer_bonus == 250


def test_referral_bonus_recorded_in_history(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    finalize_with_referral_bonus(user_id=2, amount=1000)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT referrer_id, referred_user_id, amount, percent "
            "FROM referral_bonuses"
        ).fetchone()
    assert row == (1, 2, 100, 10)


def test_referral_bonus_does_not_create_referrer_refill(tmp_db: Path) -> None:
    """Бонус идет через credit(), а не finalize() — у рефера НЕ появляется запись в refills."""
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    finalize_with_referral_bonus(user_id=2, amount=1000)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM refills WHERE user_id = 1"
        ).fetchone()[0] == 0


def test_referral_bonus_skipped_for_vip(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1, is_vip=True)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_bonus == 0
    assert result.referrer_new_balance is None


def test_referral_bonus_skipped_when_no_referrer(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=None)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_id is None
    assert result.referrer_bonus == 0


def test_referral_bonus_referrer_does_not_exist(tmp_db: Path) -> None:
    """ref_id на несуществующего — бонус молча пропущен, не падаем."""
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=999)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_bonus == 0
```

(Хелпер `_make_user_full` уже существует в этом файле — не трогать. Если он не принимает `ref_link_id` — и не надо: тесты выставляют его прямым UPDATE.)

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_refill.py -v -k referral`
Expected: FAIL (бонус 300 вместо 100, нет таблички истории и т.д.)

- [ ] **Step 3: Переписать `finalize_with_referral_bonus`**

В `services/refill.py` заменить `_get_user_for_referral` и `finalize_with_referral_bonus` (строки ~190-246), удалить `_is_first_refill` (больше не нужен — проверить, что его никто больше не импортирует: `grep -rn _is_first_refill --include='*.py' .`):

```python
def _get_user_for_referral(user_id: int) -> dict:
    with connect() as con:
        row = con.execute(
            "SELECT id, ref_id, ref_link_id, is_vip FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")
    return row


def _record_referral_bonus(
    *,
    referrer_id: int,
    referred_user_id: int,
    payment_id: str | None,
    link_id: int | None,
    bonus: int,
    percent: int,
    referrer_new_balance: int,
) -> None:
    """История начисления + durable web-уведомление реферу."""
    from utils.other import format_decimal, get_date
    from utils.sqlite3 import get_string

    with connect() as con:
        refill_row = None
        if payment_id is not None:
            refill_row = con.execute(
                "SELECT increment FROM refills WHERE payment_id = ?",
                (payment_id,),
            ).fetchone()
        con.execute(
            "INSERT INTO referral_bonuses(referrer_id, referred_user_id, refill_id, "
            "link_id, amount, percent, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                referrer_id, referred_user_id,
                refill_row["increment"] if refill_row else None,
                link_id, bonus, percent, get_date(),
            ),
        )
        text = get_string("str_ref_balance_refil").format(
            format_decimal(bonus), format_decimal(referrer_new_balance)
        )
        con.execute(
            "INSERT INTO notifications(user_id, kind, text) VALUES (?, 'referral', ?)",
            (referrer_id, text),
        )
        con.commit()


def finalize_with_referral_bonus(
    user_id: int,
    amount: int,
    payment_id: str | None = None,
    *,
    source_type: str = "telegram",
    source_app_id: int | None = None,
) -> RefillResult:
    """Финализирует refill + начисляет реферу процент с КАЖДОГО пополнения.

    Процент: custom_percent ссылки, через которую атрибуцирован плательщик,
    иначе глобальный settings.ref_percent. Бонус — через credit() (НЕ finalize(),
    чтобы у рефера не появлялась фиктивная запись в refills).
    was_newly_finalized пробрасывается из finalize() — защита от двойного
    начисления при гонках (web-status / крон / TG-handler).
    """
    user = _get_user_for_referral(user_id)

    new_balance, was_newly_finalized = finalize(
        user_id, amount, payment_id=payment_id,
        source_type=source_type, source_app_id=source_app_id,
    )

    referrer_id: int | None = user["ref_id"]
    bonus = 0
    referrer_new_balance: int | None = None

    if was_newly_finalized and not user["is_vip"] and referrer_id is not None:
        from services.referral import get_bonus_percent
        percent = get_bonus_percent(user["ref_link_id"])
        bonus = amount * percent // 100
        if bonus > 0:
            try:
                referrer_new_balance = credit(int(referrer_id), bonus)
            except UserNotFound:
                referrer_new_balance = None
                bonus = 0
            else:
                _record_referral_bonus(
                    referrer_id=int(referrer_id),
                    referred_user_id=user_id,
                    payment_id=payment_id,
                    link_id=user["ref_link_id"],
                    bonus=bonus,
                    percent=percent,
                    referrer_new_balance=referrer_new_balance,
                )

    return RefillResult(
        user_balance=new_balance,
        referrer_id=int(referrer_id) if referrer_id is not None else None,
        referrer_bonus=bonus,
        referrer_new_balance=referrer_new_balance,
        was_newly_finalized=was_newly_finalized,
    )
```

- [ ] **Step 4: Прогнать тесты refill целиком**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_refill.py -v`
Expected: PASS. Если падают НЕреферальные тесты — чинить регресс, не тесты.

- [ ] **Step 5: Commit**

```bash
git add services/refill.py tests/unit/test_refill.py
git commit -m "feat(referral): pay percent on every refill via credit, honor per-link percent"
```

---

### Task 5: Бот — /start ref_<код>

**Files:**
- Modify: `handlers/main_start.py:47-52` (после ветки `connect`)

- [ ] **Step 1: Добавить ветку в хендлер**

В `main_start()` сразу после блока `if args == 'connect': ... return` вставить:

```python
    if args and args.startswith('ref_'):
        from services.referral import attribute
        code = args[4:]
        status_, referrer_id = attribute(user_id, code)
        if status_ == 'ok':
            ref_name = await get_refer_name(referrer_id)
            await message.answer(
                start_text_ref(ref_first_name=ref_name), reply_markup=get_menu_kb()
            )
        elif status_ == 'self':
            await message.answer(invite_yourself)
        elif status_ == 'already':
            ref_name = await get_refer_name(referrer_id)
            await message.answer(f"{yes_refer.format(name, ref_name)}")
        else:  # unknown
            await message.answer(f"{refer_not_in_base.format(name, code)}")
        return
```

Легаси-ветки (`args.isdigit()`, magic) не трогать — работают как раньше.

- [ ] **Step 2: Smoke-прогон и синтаксис**

Run: `docker exec original_avito_pf_bot-api-1 python -c "import handlers.main_start"`
Expected: без ошибок (атрибуция уже покрыта тестами сервиса в Task 3).

- [ ] **Step 3: Commit**

```bash
git add handlers/main_start.py
git commit -m "feat(referral): handle /start ref_<code> deep link in bot"
```

---

### Task 6: Веб-регистрация — ref_code

**Files:**
- Modify: `web/routers/auth_phone.py` (VerifyBody + verify)
- Modify: `web/schemas.py:41` (EmailRegisterVerifyRequest)
- Modify: `web/routers/auth_email.py:58-70` (register_verify_endpoint)
- Test: `tests/unit/test_referral_api.py` (первая часть)

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_referral_api.py`:

```python
"""REST партнерки + атрибуция при веб-регистрации."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from web.main import app
    return TestClient(app)


def _mk_user(tmp_db: Path, user_id: int) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (?, 0)", (user_id,))


def _token(user_id: int) -> str:
    from web.auth import create_jwt
    return create_jwt(user_id)


def _auth(user_id: int) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


# --------------------------------------------------- регистрация с ref_code

def _issue_phone_otp(phone: str) -> str:
    from services import otp
    return otp.issue(channel='sms', destination=phone, purpose='phone_login',
                     ttl_seconds=300, cooldown_seconds=0)


def test_phone_verify_new_user_attributed(tmp_db: Path) -> None:
    _mk_user(tmp_db, 42)
    code = _issue_phone_otp("+79990001122")
    r = _client().post("/api/auth/phone/verify", json={
        "phone": "+79990001122", "code": code, "ref_code": "42",
    })
    assert r.status_code == 200
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT u.ref_id FROM users u "
            "JOIN auth_providers ap ON ap.user_id = u.id "
            "WHERE ap.provider='phone' AND ap.identifier='+79990001122'"
        ).fetchone()
    assert row[0] == 42


def test_phone_verify_existing_user_not_reattributed(tmp_db: Path) -> None:
    from services import identity
    _mk_user(tmp_db, 42)
    existing = identity.find_or_create_user_by_phone("+79990001122", verified=True)
    code = _issue_phone_otp("+79990001122")
    r = _client().post("/api/auth/phone/verify", json={
        "phone": "+79990001122", "code": code, "ref_code": "42",
    })
    assert r.status_code == 200
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT ref_id FROM users WHERE id = ?", (existing,)
        ).fetchone()[0] is None


def test_phone_verify_bad_ref_code_ignored(tmp_db: Path) -> None:
    """Битый ref_code не должен ломать регистрацию."""
    code = _issue_phone_otp("+79990001133")
    r = _client().post("/api/auth/phone/verify", json={
        "phone": "+79990001133", "code": code, "ref_code": "999-nope",
    })
    assert r.status_code == 200
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_api.py -v`
Expected: первый тест FAIL — `ref_id` остался NULL (поле `ref_code` игнорируется).

- [ ] **Step 3: auth_phone — принять ref_code**

В `web/routers/auth_phone.py`:

```python
class VerifyBody(BaseModel):
    phone: str
    code: str
    ref_code: str | None = None
```

В конце `verify()` заменить последние две строки на:

```python
    # Phone verified via SMS-OTP → создаём user с verified=True или находим существующего.
    existing = identity.find_user_id_by_provider("phone", phone)
    user_id = identity.find_or_create_user_by_phone(phone, verified=True)
    if existing is None and body.ref_code:
        # Атрибуция ТОЛЬКО для реально нового юзера. Ошибки кода — молча.
        from services import referral
        referral.attribute(user_id, body.ref_code)
    return TokenResponse(access_token=create_jwt(user_id))
```

- [ ] **Step 4: auth_email — принять ref_code**

`web/schemas.py`, `EmailRegisterVerifyRequest`:

```python
class EmailRegisterVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    ref_code: str | None = None
```

`web/routers/auth_email.py`, `register_verify_endpoint` — после успешного `register_verify`:

```python
    try:
        user_id = auth_email.register_verify(body.email, body.code)
    except OTPExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except OTPInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (InvalidCredentials, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.ref_code:
        # register-verify существует только для новых регистраций — атрибуцируем.
        from services import referral
        referral.attribute(user_id, body.ref_code)
    return TokenResponse(access_token=create_jwt(user_id))
```

- [ ] **Step 5: Прогнать тесты**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_api.py tests/unit/test_auth_email.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/routers/auth_phone.py web/routers/auth_email.py web/schemas.py tests/unit/test_referral_api.py
git commit -m "feat(referral): accept ref_code on web registration (phone + email)"
```

---

### Task 7: REST API партнера + click

**Files:**
- Create: `web/routers/referral.py`
- Modify: `web/main.py` (после `app.include_router(notifications_router)`)
- Test: `tests/unit/test_referral_api.py` (дополнить)

- [ ] **Step 1: Дописать падающие тесты в `tests/unit/test_referral_api.py`**

```python
# --------------------------------------------------- /api/me/referral

def test_me_referral_requires_auth(tmp_db: Path) -> None:
    assert _client().get("/api/me/referral").status_code == 401


def test_create_and_list_links(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    c = _client()
    r = c.post("/api/me/referral/links", json={"slug": "youtube"}, headers=_auth(1))
    assert r.status_code == 201
    assert r.json()["slug"] == "youtube"
    r = c.post("/api/me/referral/links", json={}, headers=_auth(1))  # случайный
    assert r.status_code == 201
    summary = c.get("/api/me/referral", headers=_auth(1)).json()
    assert summary["percent"] == 10
    assert len(summary["links"]) == 2


def test_create_link_conflict_and_invalid(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    c = _client()
    c.post("/api/me/referral/links", json={"slug": "youtube"}, headers=_auth(1))
    assert c.post("/api/me/referral/links", json={"slug": "youtube"},
                  headers=_auth(1)).status_code == 409
    assert c.post("/api/me/referral/links", json={"slug": "БАД слаг"},
                  headers=_auth(1)).status_code == 422


def test_archive_link_endpoint(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    c = _client()
    link = c.post("/api/me/referral/links", json={"slug": "youtube"},
                  headers=_auth(1)).json()
    assert c.delete(f"/api/me/referral/links/{link['id']}",
                    headers=_auth(1)).status_code == 204
    assert c.delete(f"/api/me/referral/links/{link['id']}",
                    headers=_auth(1)).status_code == 404  # уже архивная


def test_click_endpoint_public_and_silent(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    c = _client()
    link = c.post("/api/me/referral/links", json={"slug": "youtube"},
                  headers=_auth(1)).json()
    assert c.post("/api/referral/click?code=1-youtube").status_code == 200
    assert c.post("/api/referral/click?code=мусор").status_code == 200
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT clicks FROM referral_links WHERE id = ?", (link["id"],)
        ).fetchone()[0] == 1


def test_bonuses_history_endpoint(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO referral_bonuses(referrer_id, referred_user_id, refill_id,"
            " link_id, amount, percent, created_at)"
            " VALUES (1, 2, NULL, NULL, 100, 10, '2026-07-18')"
        )
    rows = _client().get("/api/me/referral/bonuses", headers=_auth(1)).json()
    assert rows[0]["amount"] == 100
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_api.py -v -k "link or click or bonuses or me_referral"`
Expected: FAIL 404 (роутера нет)

- [ ] **Step 3: Создать `web/routers/referral.py`**

```python
"""Партнерская программа: ссылки, статистика, клики + админ-настройка процента."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import referral
from web.admin_deps import require_admin
from web.deps import require_user

router = APIRouter(prefix="/api", tags=["referral"])


class CreateLinkBody(BaseModel):
    slug: str | None = None


class AdminPercentBody(BaseModel):
    custom_percent: int | None = Field(None, ge=1, le=100)


@router.get("/me/referral")
async def my_referral(user_id: int = Depends(require_user)) -> dict:
    return referral.get_summary(user_id)


@router.post("/me/referral/links", status_code=201)
async def create_link(
    body: CreateLinkBody, user_id: int = Depends(require_user)
) -> dict:
    try:
        return referral.create_link(user_id, body.slug)
    except referral.SlugInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (referral.SlugTaken, referral.LinkLimitReached) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/me/referral/links/{link_id}", status_code=204)
async def archive_link(
    link_id: int, user_id: int = Depends(require_user)
) -> None:
    if not referral.archive_link(user_id, link_id):
        raise HTTPException(status_code=404, detail="ссылка не найдена")


@router.get("/me/referral/bonuses")
async def my_bonuses(
    limit: int = 50, offset: int = 0, user_id: int = Depends(require_user)
) -> list[dict]:
    return referral.list_bonuses(
        user_id, limit=max(1, min(limit, 200)), offset=max(0, offset)
    )


@router.post("/referral/click")
async def click(code: str = "") -> dict:
    """Публичный счетчик кликов (sendBeacon). Любой мусор — молча ok."""
    referral.register_click(code)
    return {"ok": True}


# ------------------------------------------------------------------ admin

@router.get("/admin/users/{target_user_id}/referral")
async def admin_user_referral(
    target_user_id: int, _admin: int = Depends(require_admin)
) -> dict:
    return referral.get_summary(target_user_id)


@router.patch("/admin/referral/links/{link_id}")
async def admin_set_percent(
    link_id: int, body: AdminPercentBody, _admin: int = Depends(require_admin)
) -> dict:
    if not referral.set_custom_percent(link_id, body.custom_percent):
        raise HTTPException(status_code=404, detail="ссылка не найдена")
    return {"ok": True}
```

- [ ] **Step 4: Подключить роутер**

В `web/main.py` после блока с `notifications_router`:

```python
from web.routers.referral import router as referral_router  # noqa: E402

app.include_router(referral_router)
```

- [ ] **Step 5: Прогнать тесты**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_api.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/routers/referral.py web/main.py tests/unit/test_referral_api.py
git commit -m "feat(referral): partner REST API (links, stats, bonuses, public click)"
```

---

### Task 8: Админ-эндпоинты — тесты

**Files:**
- Test: `tests/unit/test_referral_api.py` (дополнить; сами эндпоинты уже в Task 7)

- [ ] **Step 1: Дописать тесты**

```python
# --------------------------------------------------- admin

def _seed_admin(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', '1')"
        )


def test_admin_referral_requires_admin(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    _mk_user(tmp_db, 10)
    _seed_admin(tmp_db)
    c = _client()
    assert c.get("/api/admin/users/10/referral",
                 headers=_auth(10)).status_code == 403
    assert c.get("/api/admin/users/10/referral",
                 headers=_auth(1)).status_code == 200


def test_admin_sets_custom_percent(tmp_db: Path) -> None:
    from services.referral import create_link, get_bonus_percent
    _mk_user(tmp_db, 1)
    _mk_user(tmp_db, 10)
    _seed_admin(tmp_db)
    link = create_link(10, "vip-deal")
    c = _client()
    r = c.patch(f"/api/admin/referral/links/{link['id']}",
                json={"custom_percent": 30}, headers=_auth(1))
    assert r.status_code == 200
    assert get_bonus_percent(link["id"]) == 30
    # Сброс
    r = c.patch(f"/api/admin/referral/links/{link['id']}",
                json={"custom_percent": None}, headers=_auth(1))
    assert r.status_code == 200
    assert get_bonus_percent(link["id"]) == 10
    # Вне диапазона
    assert c.patch(f"/api/admin/referral/links/{link['id']}",
                   json={"custom_percent": 150}, headers=_auth(1)).status_code == 422
    # Не существует
    assert c.patch("/api/admin/referral/links/9999",
                   json={"custom_percent": 30}, headers=_auth(1)).status_code == 404
```

- [ ] **Step 2: Прогнать**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_api.py -v -k admin`
Expected: PASS (эндпоинты уже написаны). Если FAIL — чинить роутер.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_referral_api.py
git commit -m "test(referral): cover admin referral endpoints"
```

---

### Task 9: SPA — захват ?ref и передача при регистрации

**Files:**
- Modify: `web/static/app.jsx` (~строка 17, рядом с `const _qs = new URLSearchParams(...)`)
- Modify: `web/static/components/PhoneLogin.jsx:56`
- Modify: `web/static/components/Auth.jsx:120`

- [ ] **Step 1: app.jsx — захват и beacon**

Рядом с разбором `_qs` (до компонента App) добавить:

```jsx
// --- Реф-код партнерки: ловим ?ref=<user_id>-<slug>, храним 30 дней ---
const REF_TTL_MS = 30 * 24 * 3600 * 1000;
const _refParam = _qs.get('ref');
if (_refParam && /^\d+(-[a-z0-9_-]{3,32})?$/i.test(_refParam)) {
  let stored = null;
  try { stored = JSON.parse(localStorage.getItem('ref_code') || 'null'); } catch (e) {}
  const fresh = stored && stored.exp > Date.now();
  if (!fresh) {
    localStorage.setItem('ref_code',
      JSON.stringify({ code: _refParam, exp: Date.now() + REF_TTL_MS }));
    // Клик считаем один раз на первое касание (см. spec: клики считает SPA)
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/referral/click?code=' + encodeURIComponent(_refParam));
    }
  }
}
window.getRefCode = function () {
  try {
    const raw = JSON.parse(localStorage.getItem('ref_code') || 'null');
    if (raw && raw.exp > Date.now()) return raw.code;
  } catch (e) {}
  return null;
};
```

- [ ] **Step 2: PhoneLogin.jsx — передать ref_code**

Строка 56, было:
```jsx
      const data = await api.post('/api/auth/phone/verify', { phone, code });
```
стало:
```jsx
      const data = await api.post('/api/auth/phone/verify',
        { phone, code, ref_code: window.getRefCode ? window.getRefCode() : null });
```

- [ ] **Step 3: Auth.jsx — передать ref_code**

Строка 120: в объект тела `api.post('/api/auth/email/register-verify', {...})` добавить поле:
```jsx
        ref_code: window.getRefCode ? window.getRefCode() : null,
```

- [ ] **Step 4: Ручная проверка**

Открыть ЛК с `/?ref=1-test` — в DevTools Application → localStorage появился `ref_code`; в Network — beacon на `/api/referral/click`. Проверить **mobile и desktop** breakpoints (правило проекта).

- [ ] **Step 5: Commit**

```bash
git add web/static/app.jsx web/static/components/PhoneLogin.jsx web/static/components/Auth.jsx
git commit -m "feat(referral): capture ?ref in SPA, send click beacon, pass ref_code on signup"
```

---

### Task 10: SPA — страница «Партнерка»

**Files:**
- Create: `web/static/components/Referral.jsx`
- Modify: `web/static/app.jsx` (route), `web/static/components/AppHeader.jsx:60-63` (navItems), `web/static/index.html:50` (script)

- [ ] **Step 1: Создать `web/static/components/Referral.jsx`**

```jsx
// Referral — партнерская программа: ссылки-кампании, статистика, история начислений.
const { useState: useRefState, useEffect: useRefEffect } = React;

function ReferralPage({ user, botConfig, onNavigate }) {
  const [data, setData] = useRefState(null);
  const [bonuses, setBonuses] = useRefState([]);
  const [slug, setSlug] = useRefState('');
  const [busy, setBusy] = useRefState(false);
  const [error, setError] = useRefState('');
  const [copied, setCopied] = useRefState('');

  const load = async () => {
    try {
      const d = await api.get('/api/me/referral');
      if (d.__unauthorized) return onNavigate('auth');
      setData(d);
      const b = await api.get('/api/me/referral/bonuses');
      if (!b.__unauthorized) setBonuses(b);
    } catch (e) { setError(e.message || 'Ошибка загрузки'); }
  };
  useRefEffect(() => { load(); }, []);

  const refCode = (l) => `${user.user_id}-${l.slug}`;
  const siteLink = (l) => `${window.location.origin}/?ref=${refCode(l)}`;
  const botLink = (l) => `${(botConfig && botConfig.bot_url) || 'https://t.me/AVITOPF_bot'}?start=ref_${refCode(l)}`;

  const copy = async (text, key) => {
    try { await navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(''), 1500); }
    catch (e) { setError('Не удалось скопировать'); }
  };

  const createLink = async (random) => {
    setBusy(true); setError('');
    try {
      await api.post('/api/me/referral/links', random ? {} : { slug: slug.trim().toLowerCase() });
      setSlug('');
      await load();
    } catch (e) { setError(e.message || 'Ошибка'); }
    finally { setBusy(false); }
  };

  const archive = async (id) => {
    if (!confirm('Архивировать ссылку? Приведенные по ней рефералы сохранятся.')) return;
    setBusy(true); setError('');
    try { await api.delete('/api/me/referral/links/' + id); await load(); }
    catch (e) { setError(e.message || 'Ошибка'); }
    finally { setBusy(false); }
  };

  if (!data) return <div className="page"><div style={{ color: 'var(--text-3)' }}>Загрузка...</div></div>;

  const active = data.links.filter(l => !l.archived_at);

  return (
    <div className="page">
      <h1 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: 8 }}>🤝 Партнерка</h1>

      <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>Как это работает</div>
        <div style={{ fontSize: '0.875rem', color: 'var(--text-2)' }}>
          Делитесь ссылкой — получайте <strong>{data.percent}%</strong> с каждого
          пополнения приведенных пользователей на баланс сервиса. Пожизненно.
        </div>
        <div style={{ display: 'flex', gap: 24, marginTop: 12, fontSize: '0.875rem' }}>
          <div>Рефералов: <strong>{data.referrals_count}</strong></div>
          <div>Заработано: <strong style={{ color: 'var(--primary)' }}>{data.total_earned.toLocaleString('ru-RU')} ₽</strong></div>
        </div>
      </div>

      {error && <div className="alert alert--error" style={{ marginBottom: 12 }}>{error}</div>}

      <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>Новая ссылка</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input className="input" style={{ flex: '1 1 180px' }} placeholder="свой-слаг (латиница, 3-32)"
                 value={slug} onChange={e => setSlug(e.target.value)} disabled={busy} />
          <button className="btn btn--primary" onClick={() => createLink(false)}
                  disabled={busy || slug.trim().length < 3}>Создать</button>
          <button className="btn btn--ghost" onClick={() => createLink(true)}
                  disabled={busy}>🎲 Случайная</button>
        </div>
      </div>

      <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>Мои ссылки</h3>
        {active.length === 0
          ? <div style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>Пока нет — создайте первую выше.</div>
          : active.map(l => (
            <div key={l.id} style={{ borderTop: '1px solid var(--border)', padding: '12px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                <strong>{l.slug}</strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-3)' }}>
                  {l.effective_percent}% · клики: {l.clicks} · регистрации: {l.registrations} · заработано: {l.earned.toLocaleString('ru-RU')} ₽
                </span>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                <button className="btn btn--ghost btn--sm" onClick={() => copy(siteLink(l), 'site' + l.id)}>
                  {copied === 'site' + l.id ? '✓ Скопировано' : '🌐 Ссылка на сайт'}
                </button>
                <button className="btn btn--ghost btn--sm" onClick={() => copy(botLink(l), 'bot' + l.id)}>
                  {copied === 'bot' + l.id ? '✓ Скопировано' : '🤖 Ссылка на бота'}
                </button>
                <button className="btn btn--ghost btn--sm" onClick={() => archive(l.id)} disabled={busy}>Архив</button>
              </div>
            </div>
          ))}
      </div>

      <div className="card" style={{ padding: '16px 20px' }}>
        <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>История начислений</h3>
        {bonuses.length === 0
          ? <div style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>Начислений пока нет.</div>
          : bonuses.map(b => (
            <div key={b.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid var(--border)', fontSize: '0.875rem' }}>
              <span>{formatDate ? formatDate(b.created_at) : b.created_at} · реферал #{b.referred_user_id}{b.link_slug ? ` · ${b.link_slug}` : ''} · {b.percent}%</span>
              <strong style={{ color: 'var(--primary)' }}>+{b.amount.toLocaleString('ru-RU')} ₽</strong>
            </div>
          ))}
      </div>
    </div>
  );
}

Object.assign(window, { ReferralPage });
```

⚠️ `api.delete` — проверить, есть ли метод в `web/static/api.js`; если нет — добавить по образцу `api.post`:

```js
  async delete(path) {
    const token = this._token();
    const res = await fetch(path, {
      method: 'DELETE',
      headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    });
    if (res.status === 401) return { __unauthorized: true };
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const e = new Error(this._formatDetail(err.detail));
      e.status = res.status;
      throw e;
    }
    return res.status === 204 ? {} : res.json();
  },
```

⚠️ `user.user_id` — проверить поле в `/api/me` (`ProfileResponse` в `web/schemas.py`): если там `id`, а не `user_id`, поправить `refCode`.

- [ ] **Step 2: Маршрут и навигация**

`web/static/index.html` — после строки 50 (`Profile.jsx`):
```html
  <script type="text/babel" src="/components/Referral.jsx"></script>
```

`web/static/app.jsx` — в switch после `case 'profile'`:
```jsx
      case 'referral': return <ReferralPage user={user} botConfig={botConfig} onNavigate={handleNavigate} />;
```

`web/static/components/AppHeader.jsx` — в `navItems` (строка 60):
```jsx
  const navItems = [
    { label: 'Кабинет',   route: 'cabinet',  icon: '🏠' },
    { label: 'Заказы',    route: 'orders',   icon: '📋' },
    { label: 'Партнерка', route: 'referral', icon: '🤝' },
  ];
```

Также проверить в `app.jsx` список auth-gated routes (~строка 204) — добавить `'referral'` туда же, где `'orders'`.

- [ ] **Step 3: Ручная проверка обоих breakpoints**

Прогнать вручную: создать ссылку со слагом и случайную, скопировать обе формы, архивировать, посмотреть историю. Проверить **mobile И desktop** (правило проекта). Дубль слага → понятная ошибка 409.

- [ ] **Step 4: Commit**

```bash
git add web/static/components/Referral.jsx web/static/app.jsx web/static/components/AppHeader.jsx web/static/index.html web/static/api.js
git commit -m "feat(referral): partner page in web cabinet (links, stats, bonus history)"
```

---

### Task 11: Админка — секция партнерки в карточке пользователя

**Files:**
- Modify: `web/static/components/AdminUsers.jsx` (внутри `AdminUserDrawer`, после карточки «Последние заказы»)

- [ ] **Step 1: Состояние и загрузка**

В `AdminUserDrawer` добавить состояние и загрузку рядом с существующим `reload`:

```jsx
  const [refData, setRefData] = useAdmUState(null);
  const [pctDraft, setPctDraft] = useAdmUState({});

  const reloadReferral = async () => {
    try {
      const fresh = await api.get('/api/admin/users/' + userId + '/referral');
      if (!fresh.__unauthorized) setRefData(fresh);
    } catch (e) { /* партнерки может не быть — не валим drawer */ }
  };

  useAdmUEffect(() => { reload(); reloadReferral(); }, [userId]);
```

(существующий `useAdmUEffect(() => { reload(); }, [userId]);` заменить на строку выше)

```jsx
  const savePercent = async (linkId) => {
    const raw = pctDraft[linkId];
    const val = raw === '' || raw === undefined ? null : Number(raw);
    if (val !== null && (!Number.isInteger(val) || val < 1 || val > 100)) {
      return setError('Процент: целое 1-100 или пусто (глобальный)');
    }
    setBusy(true); setError('');
    try {
      await api.patch('/api/admin/referral/links/' + linkId, { custom_percent: val });
      await reloadReferral();
    } catch (e) { setError(e.message || 'Ошибка'); }
    finally { setBusy(false); }
  };
```

⚠️ `api.patch` — если метода нет в `web/static/api.js`, добавить по образцу `api.post` с `method: 'PATCH'`.

- [ ] **Step 2: Разметка секции**

После карточки «Последние заказы» (перед закрывающим `</>`):

```jsx
            <div className="card" style={{ padding: '16px 20px', marginTop: 16 }}>
              <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>Партнерка</h3>
              {!refData ? <div style={{ color: 'var(--text-3)', fontSize: '0.85rem' }}>Загрузка...</div> : (
                <>
                  <div style={{ fontSize: '0.85rem', marginBottom: 10 }}>
                    Рефералов: <strong>{refData.referrals_count}</strong> ·
                    заработано: <strong>{refData.total_earned.toLocaleString('ru-RU')} ₽</strong> ·
                    глобальный процент: {refData.percent}%
                  </div>
                  {refData.links.length === 0
                    ? <div style={{ color: 'var(--text-3)', fontSize: '0.85rem' }}>Ссылок нет</div>
                    : refData.links.map(l => (
                      <div key={l.id} style={{ borderTop: '1px solid var(--border)', padding: '10px 0', fontSize: '0.85rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
                          <span><strong>{l.slug}</strong>{l.archived_at ? ' (архив)' : ''}</span>
                          <span style={{ color: 'var(--text-3)' }}>
                            клики {l.clicks} · рег. {l.registrations} · {l.earned.toLocaleString('ru-RU')} ₽
                          </span>
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 6, alignItems: 'center' }}>
                          <input
                            className="input" type="number" min={1} max={100}
                            style={{ width: 110, padding: '4px 8px' }}
                            placeholder={`${refData.percent} — глоб.`}
                            value={pctDraft[l.id] !== undefined ? pctDraft[l.id]
                                   : (l.custom_percent === null ? '' : l.custom_percent)}
                            onChange={e => setPctDraft({ ...pctDraft, [l.id]: e.target.value })}
                          />
                          <span>%</span>
                          <button className="btn btn--ghost btn--sm" onClick={() => savePercent(l.id)} disabled={busy}>
                            Сохранить
                          </button>
                        </div>
                      </div>
                    ))}
                </>
              )}
            </div>
```

- [ ] **Step 3: Ручная проверка**

В админке открыть пользователя со ссылками: выставить 30%, сбросить (пустое поле), проверить невалидные значения. Оба breakpoints.

- [ ] **Step 4: Commit**

```bash
git add web/static/components/AdminUsers.jsx web/static/api.js
git commit -m "feat(referral): admin per-link percent override in user drawer"
```

---

### Task 12: Лендинг — проброс ?ref

**Files:**
- Modify: `web/landing/index.html` (перед `</body>`)
- Modify: `docs/superpowers/specs/2026-07-18-referral-program-design.md` (уточнение про клики)

- [ ] **Step 1: Вставить скрипт**

Перед `</body>` в `web/landing/index.html`:

```html
<script>
(function () {
  var ref = new URLSearchParams(location.search).get('ref');
  if (!ref || !/^\d+(-[a-z0-9_-]{3,32})?$/i.test(ref)) return;
  // Дописываем ref ко всем ссылкам на ЛК: localStorage между доменами не шарится.
  document.querySelectorAll('a[href*="lk."]').forEach(function (a) {
    try {
      var u = new URL(a.getAttribute('href'), location.href);
      u.searchParams.set('ref', ref);
      a.setAttribute('href', u.toString());
    } catch (e) { /* битые href пропускаем */ }
  });
})();
</script>
```

Клик здесь НЕ считаем — beacon шлет ЛК-SPA при первом касании (Task 9); двойной счет по цепочке лендинг→ЛК исключен.

- [ ] **Step 2: Синхронизировать спеку**

В `docs/superpowers/specs/2026-07-18-referral-program-design.md` пункт 2 раздела «Потоки» — заменить упоминание beacon с лендинга на:

```
   шлет клик НЕ лендинг, а ЛК-SPA при первом касании (?ref без свежего
   ref_code в localStorage) — так исключается двойной счет по цепочке
   лендинг → ЛК.
```

- [ ] **Step 3: Ручная проверка**

Открыть лендинг локально с `?ref=1-test` — все ссылки на `lk.*` получили `?ref=1-test`.

- [ ] **Step 4: Commit**

```bash
git add web/landing/index.html docs/superpowers/specs/2026-07-18-referral-program-design.md
git commit -m "feat(referral): propagate ref code from landing to cabinet links"
```

---

### Task 13: Бот — профиль и реферальная ссылка

**Files:**
- Modify: `handlers/profile.py:47-49`

- [ ] **Step 1: Показать реф-код дефолтной ссылки**

В `handlers/profile.py` (строки ~47-49) заменить:

```python
    profile_string = get_string('str_user_profile')
    ref_link = f"{config.botlink}?start={user_id}"
    rferals_count = get_referals_count(user)
```

на:

```python
    profile_string = get_string('str_user_profile')
    from services.referral import get_or_create_default_link, referrals_count
    _def_link = get_or_create_default_link(user_id)
    ref_link = f"{config.botlink}?start=ref_{user_id}-{_def_link['slug']}"
    rferals_count = referrals_count(user_id)
```

Импорт `get_referals_count` из `utils.other` в шапке файла удалить, если больше нигде в файле не используется (проверить grep-ом по файлу).

- [ ] **Step 2: Smoke**

Run: `docker exec original_avito_pf_bot-api-1 python -c "import handlers.profile"`
Expected: без ошибок. Легаси-ссылки `?start=<user_id>` из старых сообщений продолжают работать (ветка digit в main_start не тронута).

- [ ] **Step 3: Commit**

```bash
git add handlers/profile.py
git commit -m "feat(referral): bot profile shows default campaign ref link and live count"
```

---

### Task 14: Мердж аккаунтов — перенос ref

**Files:**
- Modify: `services/identity.py:233-277` (`_merge_phone_only_into`)
- Test: `tests/unit/test_identity_phone.py` (дополнить)

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/unit/test_identity_phone.py` (использовать существующие в файле хелперы создания юзеров/провайдеров — посмотреть соседние тесты merge и повторить их сетап):

```python
def test_merge_transfers_ref_when_target_has_none(tmp_db: Path) -> None:
    """У phone-only источника был реферер, у цели нет → ref переносится."""
    import sqlite3
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (42, 0)")          # реферер
        con.execute("INSERT INTO users(id, balance) VALUES (200, 0)")         # target
        con.execute(
            "INSERT INTO users(id, balance, ref_id, ref_link_id) VALUES (100, 0, 42, NULL)"
        )  # phone-only source с реферером
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (100, 'phone', '+79990009900', '2026-07-18', 0)"
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (200, 'telegram', '555', '2026-07-18', 1)"
        )
    identity.link_phone_provider(200, "+79990009900", set_verified=True)
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT ref_id FROM users WHERE id = 200"
        ).fetchone()[0] == 42


def test_merge_keeps_target_ref(tmp_db: Path) -> None:
    """У цели уже есть реферер → не перезаписываем."""
    import sqlite3
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (42, 0)")
        con.execute("INSERT INTO users(id, balance) VALUES (43, 0)")
        con.execute("INSERT INTO users(id, balance, ref_id) VALUES (200, 0, 43)")
        con.execute("INSERT INTO users(id, balance, ref_id) VALUES (100, 0, 42)")
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (100, 'phone', '+79990009901', '2026-07-18', 0)"
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (200, 'telegram', '556', '2026-07-18', 1)"
        )
    identity.link_phone_provider(200, "+79990009901", set_verified=True)
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT ref_id FROM users WHERE id = 200"
        ).fetchone()[0] == 43
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_identity_phone.py -v -k merge_transfers`
Expected: FAIL (`ref_id` = NULL)

- [ ] **Step 3: Реализовать перенос**

В `services/identity.py`, в `_merge_phone_only_into`, перед `con.execute("DELETE FROM users WHERE id=?", ...)`:

```python
    # Перенос реферера: если у source был ref_id, а у target нет — сохраняем атрибуцию.
    src_ref = con.execute(
        "SELECT ref_id, ref_link_id, ref_user_name FROM users WHERE id=?",
        (source_user_id,),
    ).fetchone()
    if src_ref and src_ref["ref_id"] is not None:
        con.execute(
            "UPDATE users SET ref_id=?, ref_link_id=?, ref_user_name=? "
            "WHERE id=? AND ref_id IS NULL",
            (src_ref["ref_id"], src_ref["ref_link_id"], src_ref["ref_user_name"],
             target_user_id),
        )
```

- [ ] **Step 4: Прогнать**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_identity_phone.py -v`
Expected: PASS (все, включая старые)

- [ ] **Step 5: Commit**

```bash
git add services/identity.py tests/unit/test_identity_phone.py
git commit -m "feat(referral): carry referrer over on phone-only account merge"
```

---

### Task 15: Финал — полный прогон и sanity

- [ ] **Step 1: Полный прогон тестов**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest -q`
Expected: все зеленые. Любой упавший тест — регресс, чинить код, а не тест (кроме явно переписанных в Task 4).

- [ ] **Step 2: Sanity-чеклист вручную**

- Бот: `/start ref_<id>-<slug>` от нового TG-аккаунта → «пришли по ссылке», в БД ref_id + ref_link_id.
- Бот: профиль → реф-ссылка формата `?start=ref_<id>-<slug>`.
- Сайт: `/?ref=<id>-<slug>` → регистрация по телефону → ref_id выставлен.
- Пополнение реферала → у партнера +10% на балансе, запись в истории на вкладке, TG-уведомление.
- Админка: выставить 25% на ссылку → следующее пополнение реферала этой ссылки дает 25%.

- [ ] **Step 3: Итоговый коммит (если были правки) и передача**

Ветка `feature/referral-program` готова к вливанию в `dev` (см. skill superpowers:finishing-a-development-branch).

---

## Замечания для исполнителя

- **Баланс в целых рублях** — никаких копеек и ×100 (правило проекта).
- **`services/db.connect()`** возвращает соединение с `dict_factory` — строки читаются как dict; в голых тестах через `sqlite3.connect(tmp_db)` — кортежи. Не путать.
- Легаси-поля `referals` (CSV) и старую ветку `/start <digits>` **не удалять** — обратная совместимость.
- Тексты в боте берутся из `get_string(...)` с дефолтами в `_STRING_DEFAULTS` — новые строки UI добавлять туда же, если понадобятся.
- Любая правка `web/static/*` проверяется на mobile И desktop breakpoints.
