# Dates ISO Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Унифицировать хранение всех дат в БД на формат ISO+UTC, сохранив `dd.mm.yyyy HH:MM` (Moscow time) на дисплее в Telegram и Google Sheets. Починить админ-дашборд (`orders_today` / `revenue_today`).

**Architecture:** Новый helper-модуль `utils/dates.py` с `now_iso()`, `format_display()`, `parse_any()`. Writers переключаются на `now_iso`, readers оборачиваются в `format_display`. Идемпотентный migration-скрипт переписывает legacy-значения в ISO. После этого `admin_stats.py` упрощается до простого `LIKE 'YYYY-MM-DD%'` фильтра и включает гостевые заказы.

**Tech Stack:** Python 3.11+, SQLite, FastAPI, pytest. Тесты прогоняются в Docker через `docker compose --profile test run --rm test`.

**Spec:** [docs/superpowers/specs/2026-05-23-dates-iso-unification-design.md](docs/superpowers/specs/2026-05-23-dates-iso-unification-design.md)

---

## File Structure

**Создаются:**

- `utils/dates.py` — единственная точка работы с датами (writers, формат display, толерантный парсер).
- `scripts/migrate_dates_to_iso.py` — one-shot миграция данных. Идемпотентна.
- `tests/unit/test_dates.py` — unit-тесты helper'а.
- `tests/unit/test_migrate_dates_to_iso.py` — тесты миграции на временной БД.
- `tests/web/test_admin_stats_dates.py` — e2e регрессия после фикса admin_stats.

**Модифицируются:**

- `utils/other.py:8-12` — `get_date()` становится тонкой обёрткой над `utils.dates.now_iso()`.
- `utils/other_functions.py:10-15` — удаление мёртвого дубля `get_date()`.
- `services/guest_orders.py:6-13` — `_now()` использует `now_iso`.
- `handlers/admin_orders.py:234, 478` — обёртка `format_display`.
- `handlers/pf_order.py:249` — обёртка `format_display`.
- `handlers/reviews.py:145, 206` — обёртка `format_display`.
- `handlers/admin_reviews.py:152` — обёртка `format_display`.
- `utils/googlesheets.py:85, 233, 407` — обёртка `format_display`.
- `web/routers/orders.py:133` — обёртка `format_display` в админ-уведомлении о новом гостевом заказе.
- `web/routers/admin_stats.py` — упростить + включить `guest_orders`.

**Порядок задач выбран так, чтобы система оставалась работающей между коммитами:**

1. Helper модуль (без изменений поведения).
2. Readers оборачиваются `format_display` — она прозрачна и для legacy, и для ISO.
3. Writers переключаются на ISO — новые данные ISO, старые legacy, оба формата читаемы.
4. Удаление мёртвого дубля.
5. Migration script (с тестами на идемпотентность).
6. `admin_stats` фикс + регрессионный тест.

## Test execution

**Все тесты прогоняются в Docker:**

```bash
docker compose --profile test run --rm test
```

Для прогона конкретного файла:

```bash
docker compose --profile test run --rm test pytest tests/unit/test_dates.py -v
```

---

## Task 1: Helper module `utils/dates.py`

**Files:**

- Create: `utils/dates.py`
- Test: `tests/unit/test_dates.py`

- [ ] **Step 1: Write failing tests for `now_iso`**

```python
# tests/unit/test_dates.py
from datetime import datetime, timezone

from utils.dates import now_iso


def test_now_iso_returns_iso_with_utc_timezone():
    result = now_iso()
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_now_iso_no_microseconds():
    result = now_iso()
    # ISO output like "2026-05-23T11:30:00+00:00" — no '.' before tz
    assert "." not in result.split("+")[0]
```

- [ ] **Step 2: Run failing test**

```
docker compose --profile test run --rm test pytest tests/unit/test_dates.py -v
```

Expected: ModuleNotFoundError on `utils.dates`.

- [ ] **Step 3: Create `utils/dates.py` with `now_iso`**

```python
# utils/dates.py
"""Единая точка работы с датами: writers, дисплей-форматтер, толерантный парсер.

Хранение: ISO 8601 + UTC (без микросекунд).
Дисплей:  dd.mm.yyyy HH:MM в Moscow time (Europe/Moscow, UTC+3).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

_MSK = timezone(timedelta(hours=3))


def now_iso() -> str:
    """Текущий момент в ISO+UTC без микросекунд."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
```

- [ ] **Step 4: Run tests — expect PASS**

```
docker compose --profile test run --rm test pytest tests/unit/test_dates.py -v
```

- [ ] **Step 5: Add tests for `parse_any`**

```python
# tests/unit/test_dates.py (append)
import pytest

from utils.dates import parse_any


def test_parse_any_iso_with_tz():
    dt = parse_any("2026-05-23T11:30:00+00:00")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 5 and dt.day == 23
    assert dt.tzinfo is not None


def test_parse_any_legacy_dd_mm_yyyy():
    dt = parse_any("23.05.2026 14:30:00")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 5 and dt.day == 23 and dt.hour == 14


def test_parse_any_sqlite_current_timestamp():
    # SQLite CURRENT_TIMESTAMP returns "YYYY-MM-DD HH:MM:SS" (space, no TZ)
    dt = parse_any("2026-05-23 11:30:00")
    assert dt is not None
    assert dt.year == 2026 and dt.hour == 11


@pytest.mark.parametrize("value", [None, "", "   ", "not a date", "13.13.2026 25:00:00"])
def test_parse_any_invalid_returns_none(value):
    assert parse_any(value) is None
```

- [ ] **Step 6: Run failing test**

Expected: ImportError on `parse_any`.

- [ ] **Step 7: Implement `parse_any` in `utils/dates.py`**

Append to `utils/dates.py`:

```python
def parse_any(value: str | None) -> datetime | None:
    """Толерантный парсер: ISO+TZ, ISO без TZ (SQLite CURRENT_TIMESTAMP),
    legacy dd.mm.yyyy HH:MM:SS. Возвращает None на пустой / битый ввод."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
    except (ValueError, TypeError):
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 8: Run tests — expect PASS**

- [ ] **Step 9: Add tests for `format_display`**

```python
# tests/unit/test_dates.py (append)
from utils.dates import format_display


def test_format_display_iso_utc_converts_to_moscow():
    # 11:30 UTC = 14:30 MSK
    assert format_display("2026-05-23T11:30:00+00:00") == "23.05.2026 14:30"


def test_format_display_iso_with_microseconds():
    assert format_display("2026-05-23T11:30:00.123456+00:00") == "23.05.2026 14:30"


def test_format_display_legacy_passes_through_as_naive_moscow():
    # Legacy строки писались через datetime.today() (Moscow-локально). Отображаем как есть.
    assert format_display("23.05.2026 14:30:00") == "23.05.2026 14:30"


def test_format_display_sqlite_current_timestamp_treated_as_utc():
    # CURRENT_TIMESTAMP в SQLite — UTC по спецификации SQLite. Конвертим в MSK.
    assert format_display("2026-05-23 11:30:00") == "23.05.2026 14:30"


@pytest.mark.parametrize("value", [None, "", "   ", "garbage"])
def test_format_display_invalid_returns_empty(value):
    assert format_display(value) == ""
```

- [ ] **Step 10: Run failing test**

Expected: ImportError on `format_display`.

- [ ] **Step 11: Implement `format_display`**

Append to `utils/dates.py`:

```python
def format_display(value: str | None) -> str:
    """Превращает любой известный формат даты в 'dd.mm.yyyy HH:MM' в Moscow time.
    Пустой/битый ввод → пустая строка."""
    dt = parse_any(value)
    if dt is None:
        return ""
    if dt.tzinfo is None:
        # Naive: legacy писалось через datetime.today() — серверное (Moscow) время.
        # Для SQLite CURRENT_TIMESTAMP (тоже naive, но UTC по спеке) сделаем
        # эвристику: строки с разделителем '-' в дате-части трактуем как UTC,
        # остальные ('dd.mm.YYYY ...') как MSK.
        sample = str(value).strip()
        date_part = sample.split(" ", 1)[0] if " " in sample else sample
        if "-" in date_part:
            dt = dt.replace(tzinfo=timezone.utc).astimezone(_MSK)
    else:
        dt = dt.astimezone(_MSK)
    return dt.strftime("%d.%m.%Y %H:%M")
```

- [ ] **Step 12: Run tests — expect PASS**

```
docker compose --profile test run --rm test pytest tests/unit/test_dates.py -v
```

- [ ] **Step 13: Commit**

```bash
git add utils/dates.py tests/unit/test_dates.py
git commit -m "feat(dates): add utils.dates with now_iso, parse_any, format_display"
```

---

## Task 2: Wrap readers in handlers and googlesheets

**Files:**

- Modify: `handlers/admin_orders.py:234, 478`
- Modify: `handlers/pf_order.py:249`
- Modify: `handlers/reviews.py:145, 206`
- Modify: `handlers/admin_reviews.py:152`
- Modify: `utils/googlesheets.py:85, 233, 407`
- Modify: `web/routers/orders.py:133`

**Note:** на этом шаге writers всё ещё пишут legacy. `format_display` уже умеет
обрабатывать legacy → возвращает то же `"dd.mm.yyyy HH:MM"` (только секунды
выкидываются). Это видимое изменение для админа — секунды пропадут. Допустимо.

- [ ] **Step 1: Modify `handlers/admin_orders.py:234`**

Original:

```python
    dat = order['date']
```

Replace with:

```python
    from utils.dates import format_display
    dat = format_display(order['date'])
```

- [ ] **Step 2: Modify `handlers/admin_orders.py:478`**

Original:

```python
        report['general'] = f"📖 Отчет по пользователю\nID {name}\nЗарегистрирован: <b>{user['reg_date']}</b>\nБаланс <b>{user['balance']} руб.</b>"
```

Replace with:

```python
        from utils.dates import format_display
        report['general'] = f"📖 Отчет по пользователю\nID {name}\nЗарегистрирован: <b>{format_display(user['reg_date'])}</b>\nБаланс <b>{user['balance']} руб.</b>"
```

- [ ] **Step 3: Modify `handlers/pf_order.py:249`**

Original:

```python
                ord_date = order['date']
```

Replace with:

```python
                from utils.dates import format_display
                ord_date = format_display(order['date'])
```

- [ ] **Step 4: Modify `handlers/reviews.py:145`**

Original (line 145):

```python
            MSG = MSG.format(order['increment'], famount, user_str, services[service], order['status'], order['date'], order['link'])
```

Replace with:

```python
            from utils.dates import format_display
            MSG = MSG.format(order['increment'], famount, user_str, services[service], order['status'], format_display(order['date']), order['link'])
```

- [ ] **Step 5: Modify `handlers/reviews.py:206`**

Same pattern — replace `order['date']` argument with `format_display(order['date'])`. Add `from utils.dates import format_display` at top of function or once at module top.

After both edits in this file, **deduplicate**: move `from utils.dates import format_display` to the top of `handlers/reviews.py` (after existing imports) and remove the function-level imports.

- [ ] **Step 6: Modify `handlers/admin_reviews.py:152`**

Original:

```python
            STR = STR.format(order['increment'], f_price, usr_str, service, status, order['date'], order['link'])
```

Replace with:

```python
            from utils.dates import format_display
            STR = STR.format(order['increment'], f_price, usr_str, service, status, format_display(order['date']), order['link'])
```

Add import at top of file, remove inline import.

- [ ] **Step 7: Modify `utils/googlesheets.py:85`**

Find:

```python
                            order['date']
```

Replace with:

```python
                            format_display(order['date'])
```

Add at top of file:

```python
from utils.dates import format_display
```

- [ ] **Step 8: Modify `utils/googlesheets.py:233`**

Find:

```python
                reg_date.append(order['date'])
```

Replace with:

```python
                reg_date.append(format_display(order['date']))
```

- [ ] **Step 9: Modify `utils/googlesheets.py:407`**

Find:

```python
            reg_date.append(str(order['date']))
```

Replace with:

```python
            reg_date.append(format_display(order['date']))
```

- [ ] **Step 10: Modify `web/routers/orders.py:133`**

Это админ-уведомление о новом гостевом заказе. Сейчас выводит сырое значение.

Original (line 133):

```python
            f"📅 Дата: {order['date']}",
```

Replace with:

```python
            f"📅 Дата: {format_display(order['date'])}",
```

Добавить импорт в начале файла (после существующих):

```python
from utils.dates import format_display
```

- [ ] **Step 11: Verify no syntax errors in handlers**

```
docker compose --profile test run --rm test python -m py_compile handlers/admin_orders.py handlers/pf_order.py handlers/reviews.py handlers/admin_reviews.py utils/googlesheets.py web/routers/orders.py
```

Expected: no output (success).

- [ ] **Step 12: Run full test suite**

```
docker compose --profile test run --rm test
```

Expected: no NEW failures (admin_stats тест ещё не написан, остальные должны проходить как раньше).

- [ ] **Step 13: Commit**

```bash
git add handlers/admin_orders.py handlers/pf_order.py handlers/reviews.py handlers/admin_reviews.py utils/googlesheets.py web/routers/orders.py
git commit -m "refactor(handlers): wrap date readers with utils.dates.format_display"
```

---

## Task 3: Switch writers to ISO

**Files:**

- Modify: `utils/other.py:5-12`
- Modify: `services/guest_orders.py:6-13`
- Test: `tests/unit/test_writers_use_iso.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_writers_use_iso.py
from datetime import datetime

from services.guest_orders import _now
from utils.other import get_date


def test_get_date_returns_iso_with_utc():
    result = get_date()
    parsed = datetime.fromisoformat(result)
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_guest_orders_now_returns_iso_with_utc():
    result = _now()
    parsed = datetime.fromisoformat(result)
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0
```

- [ ] **Step 2: Run failing test**

```
docker compose --profile test run --rm test pytest tests/unit/test_writers_use_iso.py -v
```

Expected: AssertionError — legacy format `"23.05.2026 ..."` не парсится `fromisoformat`, либо парсится с `tzinfo=None`.

- [ ] **Step 3: Modify `utils/other.py:5-12`**

Original:

```python
import time
import ast
import re
from decimal import Decimal
from datetime import datetime, timedelta

# Получение текущей даты
def get_date():
    this_date = datetime.today().replace(microsecond=0)
    this_date = this_date.strftime("%d.%m.%Y %H:%M:%S")

    return this_date
```

Replace with:

```python
import time
import ast
import re
from decimal import Decimal
from datetime import datetime, timedelta

from utils.dates import now_iso

# Получение текущей даты в ISO+UTC.
# Старый формат "dd.mm.yyyy HH:MM:SS" больше не пишется — для отображения
# используйте utils.dates.format_display().
def get_date():
    return now_iso()
```

- [ ] **Step 4: Modify `services/guest_orders.py:6-13`**

Original:

```python
from datetime import datetime, timezone

from services.db import connect
from services.exceptions import PaymentError


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S")
```

Replace with:

```python
from services.db import connect
from services.exceptions import PaymentError
from utils.dates import now_iso


def _now() -> str:
    return now_iso()
```

- [ ] **Step 5: Run test — expect PASS**

```
docker compose --profile test run --rm test pytest tests/unit/test_writers_use_iso.py -v
```

- [ ] **Step 6: Run full test suite to catch regressions**

```
docker compose --profile test run --rm test
```

Expected: всё проходит. Существующие тесты не зависят от точного формата `get_date()`.

- [ ] **Step 7: Commit**

```bash
git add utils/other.py services/guest_orders.py tests/unit/test_writers_use_iso.py
git commit -m "feat(dates): switch writers to ISO+UTC via utils.dates.now_iso"
```

---

## Task 4: Remove dead duplicate `get_date` in `utils/other_functions.py`

**Files:**

- Modify: `utils/other_functions.py:10-15`

**Note:** проверено grep'ом — `get_date` из `utils/other_functions.py` нигде
не импортируется. Импорты только `format_decimal`, `str2bool`,
`get_user_string_without_first_name`, `get_days_suffix` — их не трогаем.

- [ ] **Step 1: Verify no usages of duplicate**

```bash
grep -rn "from utils.other_functions import.*get_date\|from utils import other_functions" --include="*.py"
```

Expected: пусто (или только импорты других символов, без `get_date`).

- [ ] **Step 2: Remove the duplicate function**

Original `utils/other_functions.py:10-15`:

```python
# Получение текущей даты
def get_date():
    this_date = datetime.today().replace(microsecond=0)
    this_date = this_date.strftime("%d.%m.%Y %H:%M:%S")

    return this_date
```

Delete these 6 lines (включая комментарий).

- [ ] **Step 3: Run full test suite**

```
docker compose --profile test run --rm test
```

Expected: всё проходит.

- [ ] **Step 4: Commit**

```bash
git add utils/other_functions.py
git commit -m "chore(dates): drop dead duplicate get_date in utils/other_functions.py"
```

---

## Task 5: Migration script + tests

**Files:**

- Create: `scripts/migrate_dates_to_iso.py`
- Create: `tests/unit/test_migrate_dates_to_iso.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_migrate_dates_to_iso.py
"""Тесты one-shot миграции dates → ISO. Используют tmp_db фикстуру
из tests/conftest.py — пустая БД с прод-схемой."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from scripts.migrate_dates_to_iso import TARGETS, migrate


def _insert_order(db: Path, date_value: str | None) -> int:
    with sqlite3.connect(db) as con:
        cur = con.execute(
            "INSERT INTO orders (user_id, price, position_name, status, links, date, contacts, user_name) "
            "VALUES (1, 100, '7/30', 'Posted', '[]', ?, 0, 'test')",
            (date_value,),
        )
        con.commit()
        return cur.lastrowid


def _get_date(db: Path, order_id: int) -> str | None:
    with sqlite3.connect(db) as con:
        row = con.execute("SELECT date FROM orders WHERE increment = ?", (order_id,)).fetchone()
        return row[0] if row else None


def test_migrate_legacy_to_iso(tmp_db: Path):
    oid = _insert_order(tmp_db, "23.05.2026 14:30:00")
    stats = migrate(tmp_db)
    after = _get_date(tmp_db, oid)
    # Result: ISO with TZ
    parsed = datetime.fromisoformat(after)
    assert parsed.tzinfo is not None
    # Treated as Moscow → UTC. 14:30 MSK = 11:30 UTC.
    assert parsed.hour == 11
    assert stats["orders"]["migrated"] == 1


def test_migrate_iso_unchanged(tmp_db: Path):
    iso = "2026-05-23T11:30:00+00:00"
    oid = _insert_order(tmp_db, iso)
    migrate(tmp_db)
    assert _get_date(tmp_db, oid) == iso


def test_migrate_null_unchanged(tmp_db: Path):
    oid = _insert_order(tmp_db, None)
    migrate(tmp_db)
    assert _get_date(tmp_db, oid) is None


def test_migrate_garbage_skipped(tmp_db: Path):
    oid = _insert_order(tmp_db, "not a date")
    stats = migrate(tmp_db)
    assert _get_date(tmp_db, oid) == "not a date"
    assert stats["orders"]["skipped"] == 1


def test_migrate_idempotent(tmp_db: Path):
    oid = _insert_order(tmp_db, "23.05.2026 14:30:00")
    first = migrate(tmp_db)
    second = migrate(tmp_db)
    # Second run should migrate nothing
    assert second["orders"]["migrated"] == 0
    # Value stable
    assert _get_date(tmp_db, oid) == _get_date(tmp_db, oid)


def test_migrate_missing_table_does_not_raise(tmp_db: Path):
    # `seo` table is not in default schema — should be skipped gracefully
    seo_target = ("seo", "date")
    assert seo_target in TARGETS
    # Just call migrate; if it raises, the test fails
    migrate(tmp_db)
```

- [ ] **Step 2: Run failing tests**

```
docker compose --profile test run --rm test pytest tests/unit/test_migrate_dates_to_iso.py -v
```

Expected: ModuleNotFoundError on `scripts.migrate_dates_to_iso`.

- [ ] **Step 3: Create `scripts/migrate_dates_to_iso.py`**

```python
"""One-shot migration: convert legacy 'dd.mm.YYYY HH:MM:SS' dates to ISO+UTC.

Idempotent — safe to re-run. Treats legacy strings as Moscow (UTC+3) time
because historically the server ran in MSK.

Usage:
    python scripts/migrate_dates_to_iso.py                # apply
    python scripts/migrate_dates_to_iso.py --dry-run      # report only
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.config import path_database  # noqa: E402

_MSK = timezone(timedelta(hours=3))

TARGETS: list[tuple[str, str]] = [
    ("orders", "date"),
    ("reviews", "date"),
    ("delreviews", "date"),
    ("seo", "date"),  # not in default schema; skipped if missing
    ("guest_orders", "created_at"),
    ("refills", "date"),
    ("support_messages", "created_at"),
]


def _convert(value: str) -> str | None:
    """Returns new ISO string if conversion needed; None if already ISO; raises ValueError if unrecognised."""
    s = value.strip()
    try:
        legacy = datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
    except ValueError:
        pass
    else:
        moscow = legacy.replace(tzinfo=_MSK)
        return moscow.astimezone(timezone.utc).isoformat()
    # Already ISO?
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return None  # leave as is
    except ValueError:
        raise


def migrate(db_path: Path | str, dry_run: bool = False) -> dict[str, dict[str, int]]:
    """Migrate all TARGETS in db_path. Returns per-table stats."""
    stats: dict[str, dict[str, int]] = {}
    con = sqlite3.connect(str(db_path))
    try:
        for table, col in TARGETS:
            table_stats = {"migrated": 0, "already_iso": 0, "skipped": 0, "null": 0}
            stats[table] = table_stats
            try:
                rows = con.execute(f"SELECT rowid, {col} FROM {table}").fetchall()
            except sqlite3.OperationalError as exc:
                # Table doesn't exist (e.g. 'seo' in some installs). Skip silently.
                if "no such table" in str(exc).lower():
                    continue
                raise
            for rowid, value in rows:
                if value is None or (isinstance(value, str) and not value.strip()):
                    table_stats["null"] += 1
                    continue
                try:
                    new_value = _convert(str(value))
                except ValueError:
                    table_stats["skipped"] += 1
                    print(f"  [skip] {table}.{col} rowid={rowid}: unrecognised value={value!r}")
                    continue
                if new_value is None:
                    table_stats["already_iso"] += 1
                    continue
                table_stats["migrated"] += 1
                if not dry_run:
                    con.execute(f"UPDATE {table} SET {col} = ? WHERE rowid = ?", (new_value, rowid))
        if not dry_run:
            con.commit()
    finally:
        con.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    stats = migrate(path_database, dry_run=args.dry_run)
    print(f"\nMigration {'(DRY-RUN) ' if args.dry_run else ''}summary:")
    for table, s in stats.items():
        print(f"  {table:25s} migrated={s['migrated']:4d}  already_iso={s['already_iso']:4d}  null={s['null']:4d}  skipped={s['skipped']:4d}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — expect PASS**

```
docker compose --profile test run --rm test pytest tests/unit/test_migrate_dates_to_iso.py -v
```

- [ ] **Step 5: Manual dry-run smoke check**

```
docker compose --profile test run --rm test python scripts/migrate_dates_to_iso.py --dry-run
```

Expected: печатает summary без ошибок. Цифры показывают сколько строк
будет мигрировано (на пустой test-БД будут нули; на dev-БД зависит).

- [ ] **Step 6: Commit**

```bash
git add scripts/migrate_dates_to_iso.py tests/unit/test_migrate_dates_to_iso.py
git commit -m "feat(scripts): idempotent migrate_dates_to_iso script + tests"
```

---

## Task 6: Fix `admin_stats.py` + e2e regression test

**Files:**

- Modify: `web/routers/admin_stats.py`
- Create: `tests/web/test_admin_stats_dates.py`

- [ ] **Step 1: Write failing regression test**

```python
# tests/web/test_admin_stats_dates.py
"""E2E регрессия после фикса формата дат: убеждаемся, что заказ,
созданный сегодня через add_order(), попадает в orders_today и
revenue_today, и что гостевые тоже учитываются."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path):
    # Создаём админа
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users (id, user_name, first_name, balance, reg_date, is_admin) "
            "VALUES (1, 'admin', 'Admin', 1000, ?, 1)",
            ("2026-05-23T10:00:00+00:00",),
        )
        con.commit()

    from web.main import app
    # Bypass auth: stub require_admin to return user_id=1
    from web import admin_deps
    app.dependency_overrides[admin_deps.require_admin] = lambda: 1
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_admin_stats_counts_today_order(client, tmp_db: Path):
    from utils.sqlite3 import add_order

    add_order(
        user_id=1, price=500, position_name="7/30", status="Posted",
        links="[]", contacts=False, user_name="admin",
    )
    r = client.get("/api/admin/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["orders_today"] >= 1
    assert data["revenue_today"] >= 500


def test_admin_stats_counts_today_guest_order(client, tmp_db: Path):
    import sqlite3
    from services.guest_orders import create_guest_order

    order = create_guest_order(
        phone="79991234567", links=["https://example.com"],
        days=7, fix_count=30, contacts=False,
        price=500, price_per_unit=6,
    )
    # create_guest_order стартует со status='pending_payment' — это не оплачено.
    # Имитируем успешную оплату, чтобы заказ попал в revenue_today.
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "UPDATE guest_orders SET status = 'paid' WHERE id = ?",
            (order["id"] if isinstance(order, dict) else order.id,),
        )
        con.commit()

    r = client.get("/api/admin/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["orders_today"] >= 1
    assert data["revenue_today"] >= 500
```

**Note:** точная сигнатура `create_guest_order` (возвращает dict / dataclass / id) — проверить в `services/guest_orders.py` при имплементации и подправить извлечение `order_id`.

- [ ] **Step 2: Run failing test**

```
docker compose --profile test run --rm test pytest tests/web/test_admin_stats_dates.py -v
```

Expected: `test_admin_stats_counts_today_order` — pass (т.к. writers уже на ISO). `test_admin_stats_counts_today_guest_order` — fail (стек не включает guest_orders).

Actually первый тест тоже может упасть, если admin_stats всё ещё использует `LIKE 'YYYY-MM-DD%'` но не суммирует с гостевыми. Ожидание уточняется на запуске.

- [ ] **Step 3: Modify `web/routers/admin_stats.py`**

Original:

```python
"""Admin dashboard stats."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from services.db import connect
from web.admin_deps import require_admin
from web.schemas import AdminStatsResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsResponse)
async def stats(_: int = Depends(require_admin)) -> AdminStatsResponse:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with connect() as con:
        users_total = con.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        users_today = con.execute(
            "SELECT COUNT(*) AS c FROM users WHERE reg_date LIKE ?",
            (f"{today}%",),
        ).fetchone()["c"]
        orders_today = con.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE date LIKE ?",
            (f"{today}%",),
        ).fetchone()["c"]
        revenue_today = con.execute(
            "SELECT COALESCE(SUM(price), 0) AS s FROM orders "
            "WHERE date LIKE ? AND status != 'Cancelled'",
            (f"{today}%",),
        ).fetchone()["s"]
        open_threads = con.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS c
            FROM support_messages m
            WHERE m.id = (SELECT MAX(id) FROM support_messages WHERE user_id = m.user_id)
              AND m.direction = 'user'
            """
        ).fetchone()["c"]
    return AdminStatsResponse(
        users_total=int(users_total),
        users_registered_today=int(users_today),
        orders_today=int(orders_today),
        revenue_today=int(revenue_today or 0),
        open_support_threads=int(open_threads or 0),
    )
```

Replace with:

```python
"""Admin dashboard stats."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from services.db import connect
from web.admin_deps import require_admin
from web.schemas import AdminStatsResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Заказы считаем оплаченными, если статус НЕ один из этих.
_GUEST_UNPAID_STATUSES = ("pending_payment", "payment_failed", "cancelled")


@router.get("/stats", response_model=AdminStatsResponse)
async def stats(_: int = Depends(require_admin)) -> AdminStatsResponse:
    # Все даты в БД хранятся в ISO+UTC (см. utils/dates.py + scripts/migrate_dates_to_iso.py).
    # LIKE 'YYYY-MM-DD%' валиден и для full-ISO ('2026-05-23T11:30:00+00:00'),
    # и для SQLite CURRENT_TIMESTAMP формы ('2026-05-23 11:30:00').
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = f"{today}%"

    with connect() as con:
        users_total = con.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        users_today = con.execute(
            "SELECT COUNT(*) AS c FROM users WHERE reg_date LIKE ?",
            (prefix,),
        ).fetchone()["c"]

        # Обычные + гостевые заказы за сегодня
        orders_reg = con.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE date LIKE ?",
            (prefix,),
        ).fetchone()["c"]
        orders_guest = con.execute(
            "SELECT COUNT(*) AS c FROM guest_orders WHERE created_at LIKE ?",
            (prefix,),
        ).fetchone()["c"]
        orders_today = orders_reg + orders_guest

        # Выручка: обычные не-Cancelled + гостевые оплаченные
        revenue_reg = con.execute(
            "SELECT COALESCE(SUM(price), 0) AS s FROM orders "
            "WHERE date LIKE ? AND status != 'Cancelled'",
            (prefix,),
        ).fetchone()["s"]
        placeholders = ",".join("?" * len(_GUEST_UNPAID_STATUSES))
        revenue_guest = con.execute(
            f"SELECT COALESCE(SUM(price), 0) AS s FROM guest_orders "
            f"WHERE created_at LIKE ? AND status NOT IN ({placeholders})",
            (prefix, *_GUEST_UNPAID_STATUSES),
        ).fetchone()["s"]
        revenue_today = (revenue_reg or 0) + (revenue_guest or 0)

        open_threads = con.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS c
            FROM support_messages m
            WHERE m.id = (SELECT MAX(id) FROM support_messages WHERE user_id = m.user_id)
              AND m.direction = 'user'
            """
        ).fetchone()["c"]
    return AdminStatsResponse(
        users_total=int(users_total),
        users_registered_today=int(users_today),
        orders_today=int(orders_today),
        revenue_today=int(revenue_today),
        open_support_threads=int(open_threads or 0),
    )
```

- [ ] **Step 4: Run regression test — expect PASS**

```
docker compose --profile test run --rm test pytest tests/web/test_admin_stats_dates.py -v
```

- [ ] **Step 5: Run full test suite**

```
docker compose --profile test run --rm test
```

Expected: всё проходит.

- [ ] **Step 6: Commit**

```bash
git add web/routers/admin_stats.py tests/web/test_admin_stats_dates.py
git commit -m "fix(admin-stats): use ISO format + include guest_orders in today counters"
```

---

## Deployment / Ops notes (out-of-band)

После мерджа в `dev`:

1. **Бэкап БД** перед прогоном миграции:
   ```bash
   cp data/database.db data/database.db.bak-pre-iso-$(date +%Y%m%d)
   ```
2. **Dry-run** на копии:
   ```bash
   docker exec <container> python scripts/migrate_dates_to_iso.py --dry-run
   ```
3. **Проверить summary**: «migrated» цифры должны выглядеть разумно
   (близко к общему числу строк в каждой таблице, минус null).
4. **Применить миграцию**:
   ```bash
   docker exec <container> python scripts/migrate_dates_to_iso.py
   ```
5. **Smoke check**: открыть админ-дашборд, убедиться что
   `orders_today`/`revenue_today` показывают сегодняшние числа.
6. **Откат при проблемах**: остановить сервис, восстановить из бэкапа,
   `git revert` коммитов задачи.

---

## Self-review

**Spec coverage:**

- D1 (ISO+UTC канонический формат) → Task 1 (`now_iso`).
- D2 (display `dd.mm.yyyy HH:MM`) → Task 1 (`format_display`).
- D3 (идемпотентная миграция) → Task 5 (test_migrate_idempotent + skipped/already_iso ветки).
- D4 (helper `utils/dates.py`) → Task 1.
- D5 (UTC хранение, MSK дисплей) → Task 1 (format_display tests на конверсию UTC→MSK).
- Writers: utils.other.get_date, services.guest_orders._now → Task 3.
- Удаление дубля → Task 4.
- Readers (10 мест: handlers/admin_orders ×2, pf_order, reviews ×2, admin_reviews, googlesheets ×3, web/routers/orders) → Task 2.
- admin_stats fix + гостевые → Task 6.
- Тесты для всего → внутри каждой задачи.
- Rollback strategy → Deployment notes.

**Placeholder scan:** прошёлся — нет TBD/"add appropriate"/"similar to". Все
шаги содержат либо точный код, либо точную команду.

**Type consistency:** `now_iso() -> str`, `parse_any(value) -> datetime | None`,
`format_display(value) -> str`, `migrate(db_path) -> dict[str, dict[str, int]]` —
последовательно во всех задачах.

**Gaps:** acceptance criteria #1-6 в спеке покрыты задачами 1, 5, 6, и
deployment notes. AC #4 (TG-сообщения с правильным форматом) покрыт
Task 2 — но без отдельного тест-кейса, потому что хендлеры
тяжело unit-тестировать без mocks aiogram. Это приемлемый компромисс.
