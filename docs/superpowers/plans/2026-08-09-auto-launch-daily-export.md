# Ежедневная выгрузка авто-запусков ПФ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Каждый день в 06:00 МСК автоматически перезаписывать вкладку «Авто запуски» в рабочей Google-таблице (auto-ссылки, отправленные в биза за последние 30 дней) и кидать админам ссылку в Telegram.

**Architecture:** В `order_links` добавляется колонка `search_link`, которую dispatcher пишет в момент перевода ссылки в `in_work`; исторические строки заполняются одноразовым бэкфиллом из `avito_ad_phrase_cache`. Выгрузка собирается новым запросом `get_auto_launched_links()` и пишется существующим механизмом `utils/googlesheets._write_tab()` в отдельную вкладку. Расписание — asyncio-луп в lifespan FastAPI, рядом с уже работающими ПФ-лупами.

**Tech Stack:** Python 3, SQLite (сырой `sqlite3`), aiogram 2, FastAPI, Google Sheets API v4 (`apiclient.discovery`), pytest, Docker Compose.

**Спека:** [docs/superpowers/specs/2026-08-09-auto-launch-daily-export-design.md](../specs/2026-08-09-auto-launch-daily-export-design.md)

---

## Что нужно знать перед стартом

**Тесты гоняются только в Docker.** Локальный `python3`/`pytest` в этом проекте не используется.

**Флаг `--build` обязателен.** `Dockerfile` копирует код внутрь образа
(`COPY . .`), а `docker compose run` без `--build` переиспользует старый образ —
твои правки просто не доедут до pytest, и ты будешь смотреть на результаты
предыдущей версии кода. Пересборка дешёвая: меняется только последний слой.

**Базовая линия — 799 passed** в `tests/unit` на момент старта плана.

Весь набор:

```bash
docker compose --profile test run --rm --build test
```

Один файл или один тест (команда контейнера переопределяется аргументами):

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_auto_launch_export.py -v
```

**Фикстура `tmp_db`** (`tests/conftest.py`) создаёт временную БД с продовой схемой, подменяет `path_database` и прогоняет `apply_phase2_migrations()`. Любой тест, который трогает БД, обязан принимать `tmp_db` первым аргументом.

**Схема в двух местах.** `get_schema_statements()` — DDL для чистой БД (её использует и `tmp_db`), `apply_phase2_migrations()` — ALTER'ы для уже существующих продовых БД. Новая колонка добавляется в оба, иначе либо прод, либо тесты останутся без неё.

**Комментарии и докстринги в этом проекте на русском.** Держись этого стиля.

---

## Структура файлов

| Файл | Что делает | Действие |
|---|---|---|
| `utils/sqlite3.py` | DDL `order_links` + миграция + запрос `get_auto_launched_links` | изменить |
| `services/order_links.py` | `mark_in_work` принимает и пишет `search_link` | изменить |
| `services/order_links_dispatcher.py` | пробрасывает фразу в три вызова `mark_in_work` | изменить |
| `scripts/backfill_order_links_search_link.py` | одноразовый идемпотентный бэкфилл фраз | создать |
| `utils/googlesheets.py` | `create_auto_tasks_sheet()` → вкладка «Авто запуски» | изменить |
| `data/config.py` | `PF_AUTO_EXPORT_ENABLED`, `PF_AUTO_EXPORT_HOUR_MSK` | изменить |
| `.env.example` | документация новых переменных | изменить |
| `services/auto_launch_export.py` | `next_run_at`, `export_auto_launches`, `run_auto_export_loop` | создать |
| `web/main.py` | старт лупа в lifespan | изменить |
| `handlers/admin_orders.py` | хендлер кнопки `gsheets_auto` | изменить |
| `keyboards/inline_keyboards.py` | кнопка «Авто запуски в шит» | изменить |
| `tests/unit/test_order_links_search_link.py` | миграция + персист фразы + dispatcher | создать |
| `tests/unit/test_backfill_search_link.py` | бэкфилл | создать |
| `tests/unit/test_gsheets_auto_tasks.py` | запрос выгрузки + сборка вкладки | создать |
| `tests/unit/test_auto_launch_export.py` | расписание + catch-up | создать |

---

## Task 1: Колонка `order_links.search_link`

**Files:**
- Modify: `utils/sqlite3.py` (DDL `order_links` ~957-975, `apply_phase2_migrations` ~1094)
- Test: `tests/unit/test_order_links_search_link.py`

- [ ] **Step 1: Написать падающий тест**

Создай `tests/unit/test_order_links_search_link.py`:

```python
"""Колонка order_links.search_link: схема, персист, dispatcher."""
import sqlite3

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed_order(tmp_db, position_name='3/100', contacts=0):
    """Создаёт юзера и paid-заказ, возвращает order_id."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name) VALUES (1, 100, ?, 'paid', ?, ?, 'user1')",
            (position_name, now_iso(), contacts),
        )
        order_id = int(cur.lastrowid)
        con.commit()
    return order_id


def test_order_links_has_search_link_column(tmp_db):
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(order_links)")}
    assert 'search_link' in cols


def test_search_link_defaults_to_null(tmp_db):
    oid = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=["https://avito.ru/a_1234567890"])
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT search_link FROM order_links").fetchone()
    assert row[0] is None
```

- [ ] **Step 2: Убедиться, что тест падает**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_order_links_search_link.py -v
```

Ожидается: `test_order_links_has_search_link_column` FAIL — `assert 'search_link' in cols`.

- [ ] **Step 3: Добавить колонку в DDL**

В `utils/sqlite3.py`, в `get_schema_statements()`, блок `order_links` — добавь колонку перед `FOREIGN KEY` и подними счётчик колонок с `13` на `14`:

```python
        (
            "order_links",
            "CREATE TABLE IF NOT EXISTS order_links("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "order_id INTEGER NOT NULL,"
            "url TEXT NOT NULL,"
            "status TEXT NOT NULL DEFAULT 'pending',"
            "delivery_mode TEXT,"
            "deadline_at TIMESTAMP,"
            "started_at TIMESTAMP,"
            "done_at TIMESTAMP,"
            "failed_at TIMESTAMP,"
            "failure_reason TEXT,"
            "external_id TEXT,"
            "created_at TIMESTAMP NOT NULL,"
            "dispatch_attempts INTEGER NOT NULL DEFAULT 0,"
            "search_link TEXT,"
            "FOREIGN KEY (order_id) REFERENCES orders(increment))",
            14,
        ),
```

- [ ] **Step 4: Добавить миграцию для существующих БД**

В `utils/sqlite3.py`, в `apply_phase2_migrations()`, сразу после блока `dispatch_attempts`:

```python
        # === order_links.search_link (поисковая фраза, отправленная в биза) ===
        # Заполняется dispatcher'ом при переводе ссылки в in_work. Для строк,
        # отправленных до релиза, восстанавливается скриптом
        # scripts/backfill_order_links_search_link.py из avito_ad_phrase_cache.
        if ol_exists:
            existing_ol_sl = {row['name'] for row in con.execute("PRAGMA table_info(order_links)").fetchall()}
            if 'search_link' not in existing_ol_sl:
                con.execute("ALTER TABLE order_links ADD COLUMN search_link TEXT")
                print("order_links.search_link added (existing rows default to NULL)")
```

`ol_exists` уже вычислен выше в блоке `dispatch_attempts` — переиспользуем его.

- [ ] **Step 5: Убедиться, что тесты проходят**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_order_links_search_link.py -v
```

Ожидается: 2 passed.

- [ ] **Step 6: Прогнать весь набор**

```bash
docker compose --profile test run --rm --build test
```

Ожидается: всё зелёное. Счётчик колонок `14` мог сломать тесты, сверяющие схему, — если что-то упало, чини в этом же шаге.

- [ ] **Step 7: Коммит**

```bash
git add utils/sqlite3.py tests/unit/test_order_links_search_link.py
git commit -m "feat(order-links): add search_link column with migration"
```

---

## Task 2: `mark_in_work` персистит фразу

**Files:**
- Modify: `services/order_links.py` (`_transition` ~103-125, `mark_in_work` ~213-233)
- Test: `tests/unit/test_order_links_search_link.py`

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/unit/test_order_links_search_link.py`:

```python
def test_mark_in_work_persists_search_link(tmp_db):
    from services.order_links import mark_in_work

    oid = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=["https://avito.ru/a_1234567890"])
        con.commit()
    with connect() as con:
        link_id = int(con.execute("SELECT id FROM order_links").fetchone()["id"])

    mark_in_work(link_id, delivery_mode="auto", deadline_at="2026-08-20T00:00:00+03:00",
                 external_id="777", search_link="https://avito.ru/search?q=диван")

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT status, external_id, search_link FROM order_links WHERE id=?",
            (link_id,),
        ).fetchone()
    assert row[0] == "in_work"
    assert row[1] == "777"
    assert row[2] == "https://avito.ru/search?q=диван"


def test_mark_in_work_without_search_link_leaves_null(tmp_db):
    from services.order_links import mark_in_work

    oid = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=["https://avito.ru/a_1234567890"])
        con.commit()
    with connect() as con:
        link_id = int(con.execute("SELECT id FROM order_links").fetchone()["id"])

    mark_in_work(link_id, delivery_mode="manual",
                 deadline_at="2026-08-20T00:00:00+03:00")

    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT search_link FROM order_links WHERE id=?",
                          (link_id,)).fetchone()
    assert row[0] is None


def test_repeated_mark_in_work_does_not_overwrite_phrase(tmp_db):
    """Повторный вызов — no-op по контракту _transition, фраза сохраняется."""
    from services.order_links import mark_in_work

    oid = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=["https://avito.ru/a_1234567890"])
        con.commit()
    with connect() as con:
        link_id = int(con.execute("SELECT id FROM order_links").fetchone()["id"])

    mark_in_work(link_id, delivery_mode="auto", deadline_at="2026-08-20T00:00:00+03:00",
                 search_link="первая-фраза")
    mark_in_work(link_id, delivery_mode="auto", deadline_at="2026-08-20T00:00:00+03:00",
                 search_link="вторая-фраза")

    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT search_link FROM order_links WHERE id=?",
                          (link_id,)).fetchone()
    assert row[0] == "первая-фраза"
```

- [ ] **Step 2: Убедиться, что тесты падают**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_order_links_search_link.py -v
```

Ожидается: три новых теста FAIL — `TypeError: mark_in_work() got an unexpected keyword argument 'search_link'`.

- [ ] **Step 3: Пробросить параметр через `_transition`**

В `services/order_links.py`, сигнатура `_transition` — добавь аргумент:

```python
def _transition(
    con,
    *,
    link_id: int,
    to_status: str,
    delivery_mode: str | None = None,
    deadline_at: str | None = None,
    external_id: str | None = None,
    failure_reason: str | None = None,
    search_link: str | None = None,
) -> None:
```

Внутри, в ветке `if to_status == "in_work":`, после блока `external_id`:

```python
            if search_link is not None:
                fields.append("search_link = ?")
                values.append(search_link)
```

- [ ] **Step 4: Пробросить параметр через `mark_in_work`**

```python
def mark_in_work(
    link_id: int,
    *,
    delivery_mode: str,
    deadline_at: str,
    external_id: str | None = None,
    search_link: str | None = None,
) -> tuple[str, str] | None:
    """pending → in_work. Пересчитывает order.status в той же транзакции.

    `search_link` — поисковая фраза, реально отправленная в биза. None
    оставляет колонку нетронутой (manual-ссылки, legacy-вызовы).

    Возвращает (old, new) если статус заказа сменился, иначе None.
    Caller отвечает за дёрнуть notify_order_status_changed при не-None возврате."""
    with connect() as con:
        order_id = _get_order_id(con, link_id)
        _transition(
            con, link_id=link_id, to_status="in_work",
            delivery_mode=delivery_mode, deadline_at=deadline_at,
            external_id=external_id, search_link=search_link,
        )
        result = _recompute_order_status(con, order_id)
        con.commit()
        return result
```

- [ ] **Step 5: Убедиться, что тесты проходят**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_order_links_search_link.py -v
```

Ожидается: 5 passed.

- [ ] **Step 6: Коммит**

```bash
git add services/order_links.py tests/unit/test_order_links_search_link.py
git commit -m "feat(order-links): persist search_link on mark_in_work"
```

---

## Task 3: Dispatcher пишет фразу во всех трёх ветках

**Files:**
- Modify: `services/order_links_dispatcher.py` (строки ~150-152, ~162-165, ~395-398)
- Test: `tests/unit/test_order_links_search_link.py`

Три места, где ссылка переходит в `in_work`, и во всех фраза уже на руках:
штатный успех `submit_link`, adopt существующей задачи после `ExecutorAPIError`,
и `force_dispatch` (кнопка «Test auto» в админке).

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/unit/test_order_links_search_link.py`:

```python
from unittest.mock import patch


def _seed_pending_auto_link(tmp_db, url="https://www.avito.ru/moskva/mebel/divan_1234567890"):
    """Заказ + одна pending-ссылка. Возвращает (order_id, link_id)."""
    oid = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=[url])
        con.commit()
    with connect() as con:
        link_id = int(con.execute("SELECT id FROM order_links").fetchone()["id"])
    return oid, link_id


def test_dispatch_one_writes_phrase_on_success(tmp_db):
    from services.order_links_dispatcher import _dispatch_one

    oid, link_id = _seed_pending_auto_link(tmp_db)
    with connect() as con:
        order = dict(con.execute("SELECT * FROM orders WHERE increment=?",
                                 (oid,)).fetchone())

    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "https://avito.ru/search?q=диван")), \
         patch("services.order_links_dispatcher.submit_link",
               return_value="ext-1"):
        _dispatch_one(link_id, order)

    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT status, external_id, search_link "
                          "FROM order_links WHERE id=?", (link_id,)).fetchone()
    assert row[0] == "in_work"
    assert row[1] == "ext-1"
    assert row[2] == "https://avito.ru/search?q=диван"


def test_dispatch_one_writes_phrase_on_adopt(tmp_db):
    """API упал, но задача у биза уже есть — усыновляем и всё равно пишем фразу."""
    from services.exceptions import ExecutorAPIError
    from services.order_links_dispatcher import _dispatch_one

    oid, link_id = _seed_pending_auto_link(tmp_db)
    with connect() as con:
        order = dict(con.execute("SELECT * FROM orders WHERE increment=?",
                                 (oid,)).fetchone())

    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "фраза-adopt")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("500")), \
         patch("services.order_links_dispatcher.find_existing_task",
               return_value="ext-adopted"):
        _dispatch_one(link_id, order)

    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT status, external_id, search_link "
                          "FROM order_links WHERE id=?", (link_id,)).fetchone()
    assert row[0] == "in_work"
    assert row[1] == "ext-adopted"
    assert row[2] == "фраза-adopt"


def test_force_dispatch_writes_phrase(tmp_db):
    from services.order_links_dispatcher import force_dispatch

    oid, link_id = _seed_pending_auto_link(tmp_db)

    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "фраза-force")), \
         patch("services.order_links_dispatcher.submit_link",
               return_value="ext-force"):
        results = force_dispatch(oid, [link_id])

    assert results[0].success is True
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT search_link FROM order_links WHERE id=?",
                          (link_id,)).fetchone()
    assert row[0] == "фраза-force"
```

- [ ] **Step 2: Убедиться, что тесты падают**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_order_links_search_link.py -v
```

Ожидается: три новых теста FAIL — `assert None == 'https://avito.ru/search?q=диван'` и аналоги.

- [ ] **Step 3: Пробросить фразу в трёх местах**

В `services/order_links_dispatcher.py`, ветка adopt внутри `except ExecutorAPIError` в `_dispatch_one`:

```python
        existing = find_existing_task(url, order)
        if existing is not None:
            _breaker.record_success()
            from services.order_links import mark_in_work
            mark_in_work(link_id, delivery_mode="auto",
                         deadline_at=compute_deadline(order),
                         external_id=existing, search_link=phrase)
```

Хвост `_dispatch_one` (штатный успех):

```python
    # API принял — в work
    _breaker.record_success()
    from services.order_links import mark_in_work
    deadline = compute_deadline(order)
    mark_in_work(link_id, delivery_mode="auto",
                 deadline_at=deadline, external_id=external_id,
                 search_link=phrase)
```

В `force_dispatch`, вызов `mark_in_work` внутри `try`:

```python
        from services.order_links import mark_in_work
        try:
            mark_in_work(link_id, delivery_mode="auto",
                         deadline_at=deadline_cached, external_id=external_id,
                         search_link=phrase)
```

- [ ] **Step 4: Убедиться, что тесты проходят**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_order_links_search_link.py -v
```

Ожидается: 8 passed.

- [ ] **Step 5: Прогнать существующие тесты dispatcher'а**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_order_links_dispatcher_auto.py tests/unit/test_dispatcher_dedup.py tests/unit/test_force_dispatch.py -v
```

Ожидается: всё зелёное — сигнатура расширена опциональным аргументом, старые вызовы не сломаны.

- [ ] **Step 6: Коммит**

```bash
git add services/order_links_dispatcher.py tests/unit/test_order_links_search_link.py
git commit -m "feat(dispatcher): record search phrase sent to biza on every in_work transition"
```

---

## Task 4: Бэкфилл фраз для старых ссылок

**Files:**
- Create: `scripts/backfill_order_links_search_link.py`
- Test: `tests/unit/test_backfill_search_link.py`

- [ ] **Step 1: Написать падающий тест**

Создай `tests/unit/test_backfill_search_link.py`:

```python
"""Бэкфилл order_links.search_link из avito_ad_phrase_cache."""
import sqlite3

from utils.dates import now_iso


def _seed(tmp_db, rows):
    """rows: список (url, delivery_mode, search_link). Возвращает список link_id."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name) VALUES (1, 100, '3/100', 'paid', ?, 0, 'user1')",
            (now_iso(),),
        )
        oid = int(cur.lastrowid)
        ids = []
        for url, mode, phrase in rows:
            c = con.execute(
                "INSERT INTO order_links(order_id, url, status, delivery_mode, "
                "search_link, created_at) VALUES (?, ?, 'in_work', ?, ?, ?)",
                (oid, url, mode, phrase, now_iso()),
            )
            ids.append(int(c.lastrowid))
        con.commit()
    return ids


def _seed_cache(tmp_db, ad_id, search_link):
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO avito_ad_phrase_cache(ad_id, search_link, created_at, "
            "cached_at) VALUES (?, ?, ?, ?)",
            (ad_id, search_link, now_iso(), now_iso()),
        )
        con.commit()


def test_backfill_fills_auto_links_with_null_phrase(tmp_db):
    from scripts.backfill_order_links_search_link import backfill

    _seed_cache(tmp_db, "1234567890", "https://avito.ru/search?q=диван")
    ids = _seed(tmp_db, [
        ("https://www.avito.ru/moskva/mebel/divan_1234567890", "auto", None),
    ])

    stats = backfill()

    assert stats["filled"] == 1
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT search_link FROM order_links WHERE id=?",
                          (ids[0],)).fetchone()
    assert row[0] == "https://avito.ru/search?q=диван"


def test_backfill_skips_manual_and_already_filled(tmp_db):
    from scripts.backfill_order_links_search_link import backfill

    _seed_cache(tmp_db, "1111111111", "новая-фраза")
    _seed_cache(tmp_db, "2222222222", "новая-фраза-2")
    ids = _seed(tmp_db, [
        ("https://www.avito.ru/a/x_1111111111", "manual", None),
        ("https://www.avito.ru/a/x_2222222222", "auto", "старая-фраза"),
    ])

    stats = backfill()

    assert stats["filled"] == 0
    with sqlite3.connect(tmp_db) as con:
        manual = con.execute("SELECT search_link FROM order_links WHERE id=?",
                             (ids[0],)).fetchone()
        filled = con.execute("SELECT search_link FROM order_links WHERE id=?",
                             (ids[1],)).fetchone()
    assert manual[0] is None
    assert filled[0] == "старая-фраза"


def test_backfill_is_idempotent(tmp_db):
    from scripts.backfill_order_links_search_link import backfill

    _seed_cache(tmp_db, "3333333333", "фраза")
    _seed(tmp_db, [("https://www.avito.ru/a/x_3333333333", "auto", None)])

    first = backfill()
    second = backfill()

    assert first["filled"] == 1
    assert second["filled"] == 0


def test_backfill_counts_misses_without_crashing(tmp_db):
    """Ссылка без ad_id и промах кэша не роняют проход."""
    from scripts.backfill_order_links_search_link import backfill

    _seed(tmp_db, [
        ("совсем-не-ссылка", "auto", None),
        ("https://www.avito.ru/a/x_9999999999", "auto", None),
    ])

    stats = backfill()

    assert stats["filled"] == 0
    assert stats["no_ad_id"] == 1
    assert stats["cache_miss"] == 1
    assert stats["processed"] == 2
```

- [ ] **Step 2: Убедиться, что тесты падают**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_backfill_search_link.py -v
```

Ожидается: 4 FAIL — `ModuleNotFoundError: No module named 'scripts.backfill_order_links_search_link'`.

- [ ] **Step 3: Написать скрипт**

Создай `scripts/backfill_order_links_search_link.py`:

```python
"""Backfill: восстанавливает order_links.search_link из avito_ad_phrase_cache.

Одноразовый прогон после релиза колонки search_link. Идемпотентен: трогает
только строки с delivery_mode='auto' и search_link IS NULL, уже заполненные
не перезаписывает.

Фраза берётся из кэша по ad_id, то есть это last-used фраза объявления, а не
гарантированно та, что реально ушла в биза. Для строк, отправленных до
релиза, точнее взять неоткуда.

Запуск:
    docker compose exec api python -m scripts.backfill_order_links_search_link
"""
from __future__ import annotations

import logging
import sys

from services.avito_phrase_cache import lookup
from services.avito_url import extract_ad_id
from services.db import connect

logger = logging.getLogger(__name__)


def backfill() -> dict[str, int]:
    """Проставить search_link всем auto-ссылкам без фразы.

    Возвращает счётчики: processed / filled / no_ad_id / cache_miss.
    """
    with connect() as con:
        rows = con.execute(
            "SELECT id, url FROM order_links "
            "WHERE delivery_mode='auto' AND search_link IS NULL"
        ).fetchall()
    candidates = [(int(r["id"]), r["url"]) for r in rows]

    stats = {"processed": 0, "filled": 0, "no_ad_id": 0, "cache_miss": 0}
    for link_id, url in candidates:
        stats["processed"] += 1
        ad_id = extract_ad_id(url)
        if not ad_id:
            stats["no_ad_id"] += 1
            continue
        phrase = lookup(ad_id)
        if not phrase:
            stats["cache_miss"] += 1
            continue
        with connect() as con:
            con.execute(
                "UPDATE order_links SET search_link=? "
                "WHERE id=? AND search_link IS NULL",
                (phrase, link_id),
            )
            con.commit()
        stats["filled"] += 1

    logger.info(
        "backfill.search_link.done processed=%d filled=%d no_ad_id=%d "
        "cache_miss=%d",
        stats["processed"], stats["filled"], stats["no_ad_id"],
        stats["cache_miss"],
    )
    return stats


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    backfill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Убедиться, что тесты проходят**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_backfill_search_link.py -v
```

Ожидается: 4 passed.

- [ ] **Step 5: Коммит**

```bash
git add scripts/backfill_order_links_search_link.py tests/unit/test_backfill_search_link.py
git commit -m "feat(scripts): backfill order_links.search_link from phrase cache"
```

---

## Task 5: Запрос `get_auto_launched_links`

**Files:**
- Modify: `utils/sqlite3.py` (рядом с `get_pending_manual_links_due_today`, ~598)
- Test: `tests/unit/test_gsheets_auto_tasks.py`

- [ ] **Step 1: Написать падающий тест**

Создай `tests/unit/test_gsheets_auto_tasks.py`:

```python
"""Вкладка 'Авто запуски': запрос выборки и сборка колонок."""
import sqlite3
from datetime import datetime, timedelta, timezone

from utils.dates import now_iso


def _iso_days_ago(days: int) -> str:
    """UTC ISO — тот же формат, что пишет utils.dates.now_iso в проде."""
    return (datetime.now(timezone.utc).replace(microsecond=0)
            - timedelta(days=days)).isoformat()


def _seed_link(tmp_db, *, delivery_mode, started_at, status='in_work',
               url='https://www.avito.ru/a/x_1234567890', search_link='фраза',
               external_id='ext-1', deadline_at=None, position_name='3/100',
               contacts=0):
    """Создаёт заказ с одной ссылкой. Возвращает order_id."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name) VALUES (1, 100, ?, 'paid', ?, ?, 'user1')",
            (position_name, now_iso(), contacts),
        )
        oid = int(cur.lastrowid)
        con.execute(
            "INSERT INTO order_links(order_id, url, status, delivery_mode, "
            "started_at, deadline_at, external_id, search_link, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (oid, url, status, delivery_mode, started_at, deadline_at,
             external_id, search_link, now_iso()),
        )
        con.commit()
    return oid


def test_returns_only_auto_started_links(tmp_db):
    from utils.sqlite3 import get_auto_launched_links

    auto_oid = _seed_link(tmp_db, delivery_mode='auto',
                          started_at=_iso_days_ago(1))
    _seed_link(tmp_db, delivery_mode='manual', started_at=_iso_days_ago(1))
    _seed_link(tmp_db, delivery_mode='auto', started_at=None, status='pending')

    rows = get_auto_launched_links(days=30)

    assert len(rows) == 1
    assert rows[0]['order_id'] == auto_oid


def test_window_boundary(tmp_db):
    from utils.sqlite3 import get_auto_launched_links

    inside = _seed_link(tmp_db, delivery_mode='auto',
                        started_at=_iso_days_ago(29))
    _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(45))

    rows = get_auto_launched_links(days=30)

    assert [r['order_id'] for r in rows] == [inside]


def test_newest_first(tmp_db):
    from utils.sqlite3 import get_auto_launched_links

    old = _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(10))
    fresh = _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(2))

    rows = get_auto_launched_links(days=30)

    assert [r['order_id'] for r in rows] == [fresh, old]


def test_row_carries_all_export_fields(tmp_db):
    from utils.sqlite3 import get_auto_launched_links

    _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(1),
               deadline_at='2026-09-01T00:00:00+03:00', contacts=1,
               position_name='5/20', external_id='biza-42',
               search_link='https://avito.ru/search?q=шкаф')

    row = get_auto_launched_links(days=30)[0]

    assert row['user_id'] == 1
    assert row['position_name'] == '5/20'
    assert row['contacts'] == 1
    assert row['url'] == 'https://www.avito.ru/a/x_1234567890'
    assert row['search_link'] == 'https://avito.ru/search?q=шкаф'
    assert row['link_status'] == 'in_work'
    assert row['deadline_at'] == '2026-09-01T00:00:00+03:00'
    assert row['external_id'] == 'biza-42'
```

- [ ] **Step 2: Убедиться, что тесты падают**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_gsheets_auto_tasks.py -v
```

Ожидается: 4 FAIL — `ImportError: cannot import name 'get_auto_launched_links'`.

- [ ] **Step 3: Написать запрос**

В `utils/sqlite3.py`, сразу после `get_pending_manual_links_due_today()`:

```python
def get_auto_launched_links(days: int = 30):
    """Auto-ссылки, отправленные в биза за последние `days` дней.

    Источник вкладки «Авто запуски». Фильтр по `started_at` — это момент,
    когда ссылка реально ушла исполнителю (проставляется mark_in_work).
    `delivery_mode='auto' AND started_at IS NOT NULL` отсекает и manual, и
    pending-ссылки, которые до биза не доехали.

    Порядок — новыми сверху, чтобы вчерашняя партия была на первом экране.
    """
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = (
            "SELECT "
            "  o.increment AS order_id, o.user_id, o.position_name, o.contacts, "
            "  ol.url, ol.search_link, ol.status AS link_status, "
            "  ol.started_at, ol.deadline_at, ol.external_id "
            "FROM order_links ol "
            "JOIN orders o ON o.increment = ol.order_id "
            "WHERE ol.delivery_mode='auto' "
            "AND ol.started_at IS NOT NULL "
            "AND date(ol.started_at) >= date('now', ?) "
            "ORDER BY ol.started_at DESC, ol.id DESC"
        )
        return con.execute(sql, (f"-{int(days)} days",)).fetchall()
```

- [ ] **Step 4: Убедиться, что тесты проходят**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_gsheets_auto_tasks.py -v
```

Ожидается: 4 passed.

- [ ] **Step 5: Коммит**

```bash
git add utils/sqlite3.py tests/unit/test_gsheets_auto_tasks.py
git commit -m "feat(db): add get_auto_launched_links query for auto export"
```

---

## Task 6: Вкладка «Авто запуски»

**Files:**
- Modify: `utils/googlesheets.py` (константы вкладок ~34-38, новая функция после `create_manual_tasks_sheet` ~501)
- Test: `tests/unit/test_gsheets_auto_tasks.py`

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/unit/test_gsheets_auto_tasks.py`:

```python
from unittest.mock import patch


def _capture_sheet():
    """Патчит Sheets API и возвращает (context manager, captured dict)."""
    captured = {}

    def _fake_write(tab, sid, cols, widths):
        captured["tab"] = tab
        captured["columns"] = cols
        captured["widths"] = widths
        return "https://example.test/auto"

    ctx = [
        patch("utils.googlesheets._init", return_value=None),
        patch("utils.googlesheets._require_target", return_value=None),
        patch("utils.googlesheets._get_or_create_tab", return_value=7),
        patch("utils.googlesheets._write_tab", side_effect=_fake_write),
    ]
    return ctx, captured


def _run_export():
    from utils import googlesheets as gs
    ctx, captured = _capture_sheet()
    for c in ctx:
        c.start()
    try:
        url = gs.create_auto_tasks_sheet()
    finally:
        for c in ctx:
            c.stop()
    return url, captured


def test_create_auto_tasks_sheet_headers_and_order(tmp_db):
    _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(1),
               deadline_at='2026-09-01T00:00:00+03:00', contacts=1,
               position_name='5/20', external_id='biza-42',
               search_link='фраза-1')

    url, captured = _run_export()

    assert url == "https://example.test/auto"
    assert captured["tab"] == "Авто запуски"
    headers = [col[0] for col in captured["columns"]]
    assert headers == [
        'Ссылка с поисковым запросом', 'Ссылка на объявление', 'Контакты',
        'ПФ в день', 'Старт', 'Крутим до', 'Номер заказа', 'Задача в биза',
        'ID клиента', 'Статус ссылки',
    ]
    assert captured["columns"][0][1] == 'фраза-1'
    assert captured["columns"][2][1] == 'Да'
    assert captured["columns"][3][1] == '20'
    assert captured["columns"][5][1] == '01.09.2026'
    assert captured["columns"][7][1] == 'biza-42'
    assert captured["columns"][8][1] == 1
    assert captured["columns"][9][1] == 'in_work'


def test_contacts_no_and_broken_position_name(tmp_db):
    _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(1),
               contacts=0, position_name='мусор')

    _, captured = _run_export()

    assert captured["columns"][2][1] == 'Нет'
    assert captured["columns"][3][1] == ''


def test_missing_phrase_renders_empty_cell(tmp_db):
    _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(1),
               search_link=None)

    _, captured = _run_export()

    assert captured["columns"][0][1] == ''


def test_empty_selection_writes_headers_only(tmp_db):
    _, captured = _run_export()

    for col in captured["columns"]:
        assert len(col) == 1
```

- [ ] **Step 2: Убедиться, что тесты падают**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_gsheets_auto_tasks.py -v
```

Ожидается: 4 новых теста FAIL — `AttributeError: module 'utils.googlesheets' has no attribute 'create_auto_tasks_sheet'`.

- [ ] **Step 3: Добавить константу вкладки**

В `utils/googlesheets.py`, рядом с остальными:

```python
TAB_AUTO_TASKS = 'Авто запуски'
```

И в докстринг модуля, в список вкладок, добавь строку:

```
    create_auto_tasks_sheet()   → "Авто запуски"
```

- [ ] **Step 4: Написать два хелпера**

В `utils/googlesheets.py`, рядом с `_fmt_date_only`:

```python
def _views_per_day(position_name):
    """`дни/ПФ` → строка с количеством ПФ в день. Битое значение → ''."""
    parts = str(position_name or '').split('/')
    if len(parts) < 2:
        return ''
    value = parts[1].strip()
    return value if value.isdigit() else ''


def _fmt_msk_date(value):
    """Любой известный формат даты → 'dd.mm.yyyy' в московском времени.

    `started_at`/`deadline_at` хранятся в UTC (utils.dates.now_iso), а
    заказчик сверяется с дашбордом биза по московским суткам — срезать
    первые 10 символов ISO-строки нельзя, будет сдвиг на день у вечерних
    запусков. `format_display` уже делает конверсию в МСК и возвращает ''
    на пустом/битом вводе.
    """
    return format_display(value)[:10]
```

`format_display` уже импортирован в модуле (`from utils.dates import format_display`).

- [ ] **Step 5: Написать функцию выгрузки**

В `utils/googlesheets.py`, после `create_manual_tasks_sheet()`:

```python
def create_auto_tasks_sheet(days=30):
    """Ссылки, отправленные в биза автоматом за последние `days` дней.

    Вкладка «Авто запуски» — рабочий инструмент заказчика для сверки с
    дашбордом исполнителя: видно, что улетело, с какой фразой и до какой
    даты крутим. Колонки 'Номер заказа' и 'Задача в биза' обе нужны —
    первое наш инкремент, второе id задачи на стороне исполнителя.
    """
    _init()
    _require_target()
    sheet_id = _get_or_create_tab(TAB_AUTO_TASKS)

    from utils.sqlite3 import get_auto_launched_links
    rows = get_auto_launched_links(days=days)

    search_links = ['Ссылка с поисковым запросом']
    ad_links = ['Ссылка на объявление']
    contacts = ['Контакты']
    views = ['ПФ в день']
    start = ['Старт']
    deadline = ['Крутим до']
    order_no = ['Номер заказа']
    biza_no = ['Задача в биза']
    client = ['ID клиента']
    link_status = ['Статус ссылки']

    for row in rows:
        search_links.append(row['search_link'] or '')
        ad_links.append(row['url'])
        contacts.append('Да' if row['contacts'] else 'Нет')
        views.append(_views_per_day(row['position_name']))
        start.append(_fmt_msk_date(row['started_at']))
        deadline.append(_fmt_msk_date(row['deadline_at']))
        order_no.append(row['order_id'])
        biza_no.append(row['external_id'] or '')
        client.append(row['user_id'])
        link_status.append(row['link_status'] or '')

    column_widths = [
        (0, 2, 500),    # обе ссылки
        (2, 4, 90),     # Контакты, ПФ в день
        (4, 6, 100),    # Старт, Крутим до
        (6, 8, 110),    # Номер заказа, Задача в биза
        (8, 9, 130),    # ID клиента
        (9, 10, 110),   # Статус ссылки
    ]
    url = _write_tab(
        TAB_AUTO_TASKS, sheet_id,
        [search_links, ad_links, contacts, views, start, deadline,
         order_no, biza_no, client, link_status],
        column_widths,
    )
    logger.info("gsheets: '%s' updated, %d rows, url=%s",
                TAB_AUTO_TASKS, len(search_links) - 1, url)
    return url
```

- [ ] **Step 6: Убедиться, что тесты проходят**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_gsheets_auto_tasks.py -v
```

Ожидается: 8 passed.

- [ ] **Step 7: Коммит**

```bash
git add utils/googlesheets.py tests/unit/test_gsheets_auto_tasks.py
git commit -m "feat(gsheets): add 'Авто запуски' export tab"
```

---

## Task 7: Конфиг-флаги

**Files:**
- Modify: `data/config.py` (рядом с `PF_AUTO_DISPATCH_ENABLED`, ~96)
- Modify: `.env.example` (блок `PF_*`, ~76-85)
- Modify: `tests/conftest.py` (стаб `data.config`)

Тестов на чтение env нет — это конфигурация, а не логика. Но стаб конфига в
тестах обязан знать новые атрибуты, иначе импорт `services.auto_launch_export`
в Task 8 упадёт с `AttributeError`.

- [ ] **Step 1: Добавить переменные в конфиг**

В `data/config.py`, сразу после `PF_AUTO_DISPATCH_ENABLED`:

```python
# Ежедневная выгрузка авто-запусков в Google Sheets. Флаг гейтит ТОЛЬКО
# фоновый луп — админская кнопка «Авто запуски в шит» работает всегда,
# чтобы выгрузку можно было дёрнуть руками до включения расписания.
PF_AUTO_EXPORT_ENABLED: bool = (
    os.getenv("PF_AUTO_EXPORT_ENABLED", "false").lower() in ("1", "true", "yes")
)
PF_AUTO_EXPORT_HOUR_MSK: int = max(
    0, min(23, int(os.getenv("PF_AUTO_EXPORT_HOUR_MSK", "6")))
)
```

- [ ] **Step 2: Задокументировать в `.env.example`**

В `.env.example`, после `PF_DEFAULT_START_HOUR`:

```
PF_AUTO_EXPORT_ENABLED=false          # ежедневная выгрузка авто-запусков в шит
PF_AUTO_EXPORT_HOUR_MSK=6             # час выгрузки (0-23 МСК)
```

- [ ] **Step 3: Синхронизировать стаб конфига в тестах**

В `tests/conftest.py`, в `_make_config_stub()`, рядом с остальными `PF_*`
(если их там нет — добавь в конец функции перед `return`):

```python
    stub.PF_AUTO_EXPORT_ENABLED = False
    stub.PF_AUTO_EXPORT_HOUR_MSK = 6
```

- [ ] **Step 4: Прогнать весь набор**

```bash
docker compose --profile test run --rm --build test
```

Ожидается: всё зелёное, регрессий нет.

- [ ] **Step 5: Коммит**

```bash
git add data/config.py .env.example tests/conftest.py
git commit -m "feat(config): add PF_AUTO_EXPORT_* flags for daily auto-launch export"
```

---

## Task 8: Планировщик выгрузки

**Files:**
- Create: `services/auto_launch_export.py`
- Test: `tests/unit/test_auto_launch_export.py`

- [ ] **Step 1: Написать падающий тест расписания**

Создай `tests/unit/test_auto_launch_export.py`:

```python
"""Планировщик ежедневной выгрузки авто-запусков."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

_MSK = timezone(timedelta(hours=3))


def test_next_run_before_hour_is_today():
    from services.auto_launch_export import next_run_at

    now = datetime(2026, 8, 9, 3, 15, tzinfo=_MSK)
    assert next_run_at(now, hour=6) == datetime(2026, 8, 9, 6, 0, tzinfo=_MSK)


def test_next_run_exactly_at_hour_is_tomorrow():
    from services.auto_launch_export import next_run_at

    now = datetime(2026, 8, 9, 6, 0, tzinfo=_MSK)
    assert next_run_at(now, hour=6) == datetime(2026, 8, 10, 6, 0, tzinfo=_MSK)


def test_next_run_after_hour_is_tomorrow():
    from services.auto_launch_export import next_run_at

    now = datetime(2026, 8, 9, 23, 59, tzinfo=_MSK)
    assert next_run_at(now, hour=6) == datetime(2026, 8, 10, 6, 0, tzinfo=_MSK)


def test_next_run_crosses_month_boundary():
    from services.auto_launch_export import next_run_at

    now = datetime(2026, 8, 31, 12, 0, tzinfo=_MSK)
    assert next_run_at(now, hour=6) == datetime(2026, 9, 1, 6, 0, tzinfo=_MSK)
```

- [ ] **Step 2: Убедиться, что тесты падают**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_auto_launch_export.py -v
```

Ожидается: 4 FAIL — `ModuleNotFoundError: No module named 'services.auto_launch_export'`.

- [ ] **Step 3: Написать модуль**

Создай `services/auto_launch_export.py`:

```python
"""Ежедневная выгрузка авто-запусков в Google Sheets.

Раз в сутки в PF_AUTO_EXPORT_HOUR_MSK перезаписывает вкладку «Авто запуски»
и кидает админам ссылку. Дата последней успешной выгрузки живёт в таблице
settings — по ней луп догоняет пропущенный день после рестарта контейнера.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from data import config
from utils.googlesheets import create_auto_tasks_sheet
from utils.sender import send_admins
from utils.sqlite3 import edit_setting, get_setting

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))

LAST_RUN_SETTING = "auto_export_last_run_date"


def now_msk() -> datetime:
    """Текущее время в МСК. Отдельная функция — чтобы патчить в тестах."""
    return datetime.now(timezone.utc).astimezone(_MSK)


def next_run_at(now: datetime, *, hour: int) -> datetime:
    """Ближайшие `hour`:00 МСК строго в будущем относительно `now`."""
    candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def export_auto_launches() -> str:
    """Перезаписать вкладку. Возвращает URL. Исключения не глотает."""
    return create_auto_tasks_sheet()


def _last_run_date() -> str | None:
    value = get_setting(LAST_RUN_SETTING)
    return str(value) if value else None


def _mark_run_done(day: str) -> None:
    edit_setting(LAST_RUN_SETTING, day)


def _is_due(now: datetime) -> bool:
    """Пропустили ли мы сегодняшнюю выгрузку."""
    if now.hour < config.PF_AUTO_EXPORT_HOUR_MSK:
        return False
    return _last_run_date() != now.date().isoformat()


async def run_once() -> None:
    """Одна выгрузка + уведомление. Ошибки логирует, наружу не пускает."""
    today = now_msk().date().isoformat()
    logger.info("auto_export.start date=%s", today)
    try:
        url = await asyncio.to_thread(export_auto_launches)
    except Exception:  # noqa: BLE001
        logger.exception("auto_export.failed date=%s", today)
        try:
            await send_admins(
                "⚠️ Не смог обновить выгрузку «Авто запуски». Подробности в логах.",
                category="errors",
            )
        except Exception:  # noqa: BLE001
            logger.exception("auto_export.error_notify_failed")
        return

    # Выгрузка сделана — фиксируем день до отправки сообщения. Упавшее
    # уведомление не повод гонять Sheets API повторно.
    _mark_run_done(today)
    logger.info("auto_export.done date=%s url=%s", today, url)
    try:
        await send_admins(
            f"📤 Выгрузка «Авто запуски» обновлена\n{url}",
            category="orders",
        )
    except Exception:  # noqa: BLE001
        logger.exception("auto_export.notify_failed date=%s", today)


# Фолбэк-пауза перед повторной попыткой, если итерация лупа упала до того,
# как успела заснуть сама (например, _is_due/next_run_at словили
# "database is locked"). Без него падение на вычислении задержки превратило
# бы while True в busy-loop, молотящий CPU без единой паузы.
_LOOP_ERROR_RETRY_DELAY_SEC = 300


async def run_auto_export_loop() -> None:
    """Cron-луп: догон пропуска при старте, дальше раз в сутки в час X.

    В отличие от соседних лупов (run_refresh_loop, run_deadline_loop), которые
    спят фиксированный интервал, этот спит до конкретного времени hour:00 МСК —
    так и должно быть для «запусти ровно в 06:00», а не «раз в 24 часа от
    произвольного момента старта контейнера». run_once() всегда берёт текущую
    дату заново в момент своего вызова (не из снапшота `now`, сделанного до
    sleep), поэтому скачок системных часов во время сна в худшем случае
    сдвинет фактический час запуска, но не приведёт ни к пропуску дня, ни к
    пометке в settings не той даты.

    Тело каждой итерации обёрнуто в try/except (по образцу run_refresh_loop):
    сырые вызовы sqlite3 в _is_due/_mark_run_done могут бросить
    OperationalError ("database is locked") в проекте с несколькими
    писателями, и без защиты это исключение выходило бы из корутины и
    молча убивало бы фоновую задачу до рестарта контейнера — без единого
    алерта, потому что send_admins на этом пути даже не вызывается.
    """
    if not config.PF_AUTO_EXPORT_ENABLED:
        logger.info("auto_export.loop disabled (PF_AUTO_EXPORT_ENABLED=false)")
        return

    hour = config.PF_AUTO_EXPORT_HOUR_MSK
    logger.info("auto_export.loop start hour=%s МСК", hour)

    try:
        now = now_msk()
        if _is_due(now):
            logger.info("auto_export.catchup date=%s", now.date().isoformat())
            await run_once()
    except Exception:  # noqa: BLE001
        logger.exception("auto_export.boot_check_failed")

    while True:
        try:
            now = now_msk()
            delay = (next_run_at(now, hour=hour) - now).total_seconds()
            await asyncio.sleep(max(delay, 1.0))
            await run_once()
        except Exception:  # noqa: BLE001
            logger.exception("auto_export.loop_iter_failed")
            # Падение могло случиться до asyncio.sleep выше (например, при
            # вычислении delay) — досыпаем фиксированную паузу, чтобы не
            # уйти в busy-loop, крутящийся без единой остановки.
            await asyncio.sleep(_LOOP_ERROR_RETRY_DELAY_SEC)
```

- [ ] **Step 4: Убедиться, что тесты расписания проходят**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_auto_launch_export.py -v
```

Ожидается: 4 passed.

- [ ] **Step 5: Написать падающие тесты catch-up и уведомления**

Дописать в `tests/unit/test_auto_launch_export.py`:

```python
import pytest


def test_is_due_false_before_hour(tmp_db):
    from services import auto_launch_export as ale

    now = datetime(2026, 8, 9, 5, 0, tzinfo=_MSK)
    assert ale._is_due(now) is False


def test_is_due_true_when_never_ran(tmp_db):
    from services import auto_launch_export as ale

    now = datetime(2026, 8, 9, 7, 0, tzinfo=_MSK)
    assert ale._is_due(now) is True


def test_is_due_false_after_successful_run(tmp_db):
    from services import auto_launch_export as ale

    ale._mark_run_done("2026-08-09")
    now = datetime(2026, 8, 9, 7, 0, tzinfo=_MSK)
    assert ale._is_due(now) is False


@pytest.mark.asyncio
async def test_run_once_marks_day_and_notifies(tmp_db):
    from services import auto_launch_export as ale

    sent = []

    async def _fake_send(msg, category):
        sent.append((msg, category))

    with patch.object(ale, "export_auto_launches",
                      return_value="https://example.test/auto"), \
         patch.object(ale, "send_admins", _fake_send), \
         patch.object(ale, "now_msk",
                      return_value=datetime(2026, 8, 9, 6, 1, tzinfo=_MSK)):
        await ale.run_once()

    assert ale._last_run_date() == "2026-08-09"
    assert len(sent) == 1
    assert "https://example.test/auto" in sent[0][0]
    assert sent[0][1] == "orders"


@pytest.mark.asyncio
async def test_run_once_on_failure_keeps_day_unmarked(tmp_db):
    from services import auto_launch_export as ale

    sent = []

    async def _fake_send(msg, category):
        sent.append((msg, category))

    with patch.object(ale, "export_auto_launches",
                      side_effect=RuntimeError("google down")), \
         patch.object(ale, "send_admins", _fake_send), \
         patch.object(ale, "now_msk",
                      return_value=datetime(2026, 8, 9, 6, 1, tzinfo=_MSK)):
        await ale.run_once()

    assert ale._last_run_date() is None
    assert sent[0][1] == "errors"
```

- [ ] **Step 6: Убедиться, что все тесты модуля проходят**

```bash
docker compose --profile test run --rm --build test pytest tests/unit/test_auto_launch_export.py -v
```

Ожидается: 9 passed. Тесты `_is_due` и `run_once` зелёные сразу — логика уже
написана в Step 3. `pytest-asyncio` в проекте стоит и работает в режиме
`asyncio_mode = "auto"` (`pyproject.toml`), так что async-тесты подхватятся.

- [ ] **Step 7: Коммит**

```bash
git add services/auto_launch_export.py tests/unit/test_auto_launch_export.py
git commit -m "feat(export): daily scheduler for auto-launch sheet export"
```

---

## Task 9: Старт лупа в lifespan

**Files:**
- Modify: `web/main.py` (импорты ~18-20, `lifespan` ~25-52)

- [ ] **Step 1: Добавить импорт**

В `web/main.py`, рядом с остальными импортами лупов:

```python
from services.auto_launch_export import run_auto_export_loop
```

- [ ] **Step 2: Запустить луп и погасить его при выключении**

В `lifespan`, после `metric_task`:

```python
    metric_task = asyncio.create_task(run_metric_loop())
    auto_export_task = asyncio.create_task(run_auto_export_loop())
```

И в `finally`, добавь задачу в списки отмены:

```python
        deadline_task.cancel()
        dispatcher_task.cancel()
        refresh_task.cancel()
        metric_task.cancel()
        auto_export_task.cancel()
        for task in (deadline_task, dispatcher_task, refresh_task, metric_task,
                     auto_export_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
```

- [ ] **Step 3: Проверить, что приложение импортируется**

```bash
docker compose --profile test run --rm --build test python -c "import web.main; print('ok')"
```

Ожидается: `ok`.

- [ ] **Step 4: Прогнать весь набор**

```bash
docker compose --profile test run --rm --build test
```

Ожидается: всё зелёное.

- [ ] **Step 5: Коммит**

```bash
git add web/main.py
git commit -m "feat(web): start auto-launch export loop in lifespan"
```

---

## Task 10: Кнопка в админке

**Files:**
- Modify: `keyboards/inline_keyboards.py` (~1046-1051)
- Modify: `handlers/admin_orders.py` (после `gsheets_manual`, ~947)

- [ ] **Step 1: Добавить кнопку**

В `keyboards/inline_keyboards.py`, сразу после ряда с `gsheets_manual`:

```python
        keyboard.row(
            InlineKeyboardButton(
                text="🤖 Авто запуски в шит",
                callback_data="gsheets_auto"
            )
        )
```

- [ ] **Step 2: Добавить хендлер**

В `handlers/admin_orders.py`, сразу после хендлера `gsheets_manual`:

```python
@dp.callback_query_handler(text="gsheets_auto", state='*')
async def gsheets_auto(call: types.CallbackQuery, state: FSMContext):
    """Обновить вкладку «Авто запуски» по требованию.

    Работает независимо от PF_AUTO_EXPORT_ENABLED — флаг гейтит только
    фоновый луп."""
    from utils.googlesheets import create_auto_tasks_sheet
    chat_id = call.message.chat.id
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    STICKER = get_setting('wait_sticker')
    msg = await bot.send_message(chat_id=chat_id,
                                 text="⏳ Готовлю Авто запуски...")
    stick = await bot.send_sticker(chat_id=chat_id, sticker=STICKER) if STICKER else None
    try:
        sheet_url = create_auto_tasks_sheet()
        await bot.send_message(chat_id=chat_id, text=sheet_complete,
                               reply_markup=gsheets_url(sheet_url))
    except Exception:
        logger.exception('googlesheets: auto tasks failed')
        await bot.send_message(chat_id=chat_id,
                               text="⚠️ Ошибка при генерации Авто запусков!")
    finally:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
            if stick:
                await bot.delete_message(chat_id=chat_id,
                                         message_id=stick.message_id)
        except Exception:
            logger.debug("could not delete progress messages")
    await state.finish()
```

- [ ] **Step 3: Проверить, что модуль импортируется**

```bash
docker compose --profile test run --rm --build test python -c "import handlers.admin_orders; print('ok')"
```

Ожидается: `ok`. Если ругается на неизвестное имя (`sheet_complete`,
`gsheets_url`, `get_setting`) — они уже импортированы в файле для
`gsheets_manual`, проверь, что копия хендлера лежит в том же модуле.

- [ ] **Step 4: Прогнать весь набор**

```bash
docker compose --profile test run --rm --build test
```

Ожидается: всё зелёное.

- [ ] **Step 5: Коммит**

```bash
git add keyboards/inline_keyboards.py handlers/admin_orders.py
git commit -m "feat(admin): add 'Авто запуски в шит' button"
```

---

## Task 11: Документация и финальная проверка

**Files:**
- Modify: `README.md` (новая секция в конце файла, после «Order flow»)

- [ ] **Step 1: Описать выгрузку в README**

В конец `README.md` добавь секцию:

```markdown
## Выгрузка авто-запусков

Вкладка «Авто запуски» в рабочей Google-таблице (`GSHEETS_TARGET_SHEET_ID`) —
все ссылки, отправленные в биза в auto-режиме за последние 30 дней: поисковая
фраза, ссылка на объявление, контакты, ПФ в день, старт, дедлайн, номер заказа,
id задачи у исполнителя, id клиента, статус ссылки.

Обновляется двумя путями: фоновым лупом `services/auto_launch_export.py`
(ежедневно в `PF_AUTO_EXPORT_HOUR_MSK`, гейтится `PF_AUTO_EXPORT_ENABLED`) и
кнопкой «🤖 Авто запуски в шит» в админке — кнопка работает независимо от флага.

Поисковая фраза берётся из `order_links.search_link`, которую dispatcher пишет
в момент отправки задачи. Для задач, отправленных до появления колонки, фраза
восстанавливается скриптом
`scripts/backfill_order_links_search_link.py` из `avito_ad_phrase_cache`.
Спека: [docs/superpowers/specs/2026-08-09-auto-launch-daily-export-design.md](docs/superpowers/specs/2026-08-09-auto-launch-daily-export-design.md).
```

- [ ] **Step 2: Прогнать весь набор тестов**

```bash
docker compose --profile test run --rm --build test
```

Ожидается: всё зелёное, ни одного skip по новым тестам.

- [ ] **Step 3: Проверить порядок выката вручную**

Порядок на проде (выполняет владелец, не агент):

1. `./deploy.sh` — миграция `search_link` применится на старте автоматически.
2. `docker compose exec api python -m scripts.backfill_order_links_search_link` —
   в логе будет `backfill.search_link.done processed=… filled=…`.
3. В админке нажать «🤖 Авто запуски в шит», открыть вкладку, глазами
   проверить, что колонка «Ссылка с поисковым запросом» заполнена.
4. Добавить в прод-`.env`: `PF_AUTO_EXPORT_ENABLED=true`, рестарт `api`.
5. На следующее утро после 06:00 МСК — проверить сообщение в топике `orders`.

Откат: `PF_AUTO_EXPORT_ENABLED=false` + рестарт. Колонка `search_link`
остаётся, её наполнение продолжается — это безвредно.

- [ ] **Step 4: Коммит**

```bash
git add README.md
git commit -m "docs: describe auto-launch daily export"
```
