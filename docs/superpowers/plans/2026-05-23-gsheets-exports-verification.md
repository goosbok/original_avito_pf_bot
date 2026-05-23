# Google Sheets Exports Verification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Прогнать все 4 функции выгрузки в Google Sheets (включая нагрузочный тест `create_sheet()` на 3000 заказов) и зафиксировать результат в файле-отчёте.

**Architecture:** Двухфазная верификация. Фаза A — функциональная: 4 ручных прогона из Telegram-админки прод-Docker'а с проверкой выходных таблиц по чек-листу. Фаза B — нагрузочная: одноразовый Python-скрипт `scripts/seed_load_test_orders.py` инжектит 3000 заказов с маркером `LOAD_TEST_3K` через `docker cp` + `docker exec`, после чего запускается `create_sheet()` через UI, мониторится RSS, проверяется выходная таблица, и тот же скрипт чистит данные по маркеру.

**Tech Stack:** Python 3, SQLite (`utils/sqlite3.py`), `utils.dates.now_iso()`, Docker Compose, Google Sheets/Drive API (`utils/googlesheets.py`), Telegram (aiogram, существующая админка).

**Spec:** [docs/superpowers/specs/2026-05-23-gsheets-exports-verification-design.md](../specs/2026-05-23-gsheets-exports-verification-design.md)

---

## File Structure

**Создаются:**
- `scripts/seed_load_test_orders.py` — одноразовый CLI: вставляет N заказов с маркером и/или удаляет их (single-responsibility, легко удалить из репо после прогона)
- `docs/superpowers/specs/2026-05-23-gsheets-exports-verification-results.md` — отчёт по результатам прогона; чек-листы из спеки + найденные баги

**Не меняем:** `utils/googlesheets.py`, хендлеры, юзер-фейсинг — цель работы только верификация.

**Запуск из:** прод-worktree `/Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot`. Сам worktree этой ветки — для разработки скрипта; для прогона скрипт доставляется в контейнер через `docker cp`.

---

## Task 1: Скрипт-инжектор и cleanup в одном файле

**Files:**
- Create: `scripts/seed_load_test_orders.py`

Скрипт оперирует напрямую с SQLite через `path_db` (тот же, что и `utils/sqlite3.py`), использует `utils.dates.now_iso()` для дат, не зависит от aiogram/Telegram-конфига (чтобы можно было прокинуть `docker cp` и запустить без полной инициализации бота).

- [ ] **Step 1.1: Создать `scripts/seed_load_test_orders.py`**

```python
"""
One-shot load-test seeder/cleaner for orders table.

Usage (inside docker container):
    python /tmp/seed.py [COUNT] [--user-id ID]   # default COUNT=3000
    python /tmp/seed.py --cleanup                # removes rows with user_name='LOAD_TEST_3K'

The script is intentionally self-contained: it talks to SQLite directly via
DATABASE_PATH env (same path the bot uses) and only depends on utils.dates.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time

# Allow `from utils.dates import now_iso` when run from /tmp/seed.py inside the container.
sys.path.insert(0, "/app")

from utils.dates import now_iso  # noqa: E402

MARKER = "LOAD_TEST_3K"
DB_PATH = os.getenv("DATABASE_PATH", "/app/storage/database.db")

STATUS_CYCLE = ("Posted", "Completed", "Pending")
POSITION_CYCLE = ("3 дня/200ПФ", "7 дней/500ПФ", "14 дней/1000ПФ")


def pick_user_id(con: sqlite3.Connection, requested: int | None) -> int:
    con.row_factory = sqlite3.Row
    if requested is not None:
        row = con.execute("SELECT id FROM users WHERE id = ?", (requested,)).fetchone()
        if row is None:
            print(f"[seed] FATAL: user_id={requested} not found in users", file=sys.stderr)
            sys.exit(1)
        return int(row["id"])
    row = con.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    if row is None:
        print("[seed] FATAL: users table is empty — cannot seed orders (FK)", file=sys.stderr)
        sys.exit(1)
    return int(row["id"])


def assert_not_excluded(con: sqlite3.Connection, user_id: int) -> None:
    row = con.execute(
        "SELECT value FROM settings WHERE parametr = 'report_exclude'"
    ).fetchone()
    if not row or not row[0]:
        return
    excluded = {x.strip() for x in row[0].split(",") if x.strip()}
    if str(user_id) in excluded:
        print(
            f"[seed] FATAL: user_id={user_id} is in report_exclude — "
            f"orders would not appear in create_sheet() output. Pick another --user-id.",
            file=sys.stderr,
        )
        sys.exit(1)


def seed(count: int, user_id_arg: int | None) -> None:
    with sqlite3.connect(DB_PATH) as con:
        user_id = pick_user_id(con, user_id_arg)
        assert_not_excluded(con, user_id)

        rows = []
        for i in range(count):
            rows.append(
                (
                    user_id,
                    100 + (i % 50) * 100,
                    POSITION_CYCLE[i % len(POSITION_CYCLE)],
                    STATUS_CYCLE[i % len(STATUS_CYCLE)],
                    f"https://avito.ru/test/ad_{i}",
                    now_iso(),
                    1 if i % 2 == 0 else 0,
                    MARKER,
                )
            )

        t0 = time.perf_counter()
        con.executemany(
            "INSERT INTO orders "
            "(user_id, price, position_name, status, links, date, contacts, user_name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.commit()
        dt = time.perf_counter() - t0

    print(f"[seed] inserted {count} rows in {dt:.2f} sec (user_id={user_id}, marker={MARKER!r})")


def cleanup() -> None:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("DELETE FROM orders WHERE user_name = ?", (MARKER,))
        deleted = cur.rowcount
        con.commit()
    print(f"[seed] cleanup: deleted {deleted} rows with marker {MARKER!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed/cleanup load-test orders.")
    parser.add_argument("count", nargs="?", type=int, default=3000)
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    if args.cleanup:
        cleanup()
    else:
        seed(args.count, args.user_id)


if __name__ == "__main__":
    main()
```

- [ ] **Step 1.2: Smoke-проверка скрипта локально (synthesis check, без БД)**

Run:
```
python -c "import ast; ast.parse(open('scripts/seed_load_test_orders.py').read()); print('parse ok')"
```
Expected: `parse ok`

- [ ] **Step 1.3: Commit**

```bash
git add scripts/seed_load_test_orders.py
git commit -m "scripts: one-shot seeder/cleanup for gsheets load test"
```

---

## Task 2: Прогон фазы A — функциональная проверка (4 выгрузки из админки)

**Files:**
- Create: `docs/superpowers/specs/2026-05-23-gsheets-exports-verification-results.md`

Этот таск — *ручной прогон*. Скрипты не нужны, кроме `docker logs`. Параллельно заполняется отчёт-результат.

- [ ] **Step 2.1: Создать болванку отчёта**

Create `docs/superpowers/specs/2026-05-23-gsheets-exports-verification-results.md` со следующим содержимым:

```markdown
# Google Sheets Exports — Verification Results

**Дата прогона:** 2026-05-23
**Прогон:** Demyan Belikov
**Окружение:** prod-Docker (`/Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot`), контейнеры `original_avito_pf_bot-bot-1` и `original_avito_pf_bot-api-1` запущены.

## Phase A — функциональная проверка

### 1. `create_sheet()` — общий отчёт

| # | Пункт | Прошло | Коммент |
|---|-------|:------:|---------|
| 1 | Кнопка-ссылка пришла в чат |  |  |
| 2 | Таблица открывается публично |  |  |
| 3 | Имя файла `Заказы-DD-MM-YYYY-HH-MM-SS` |  |  |
| 4 | 9 колонок, заголовок серый/жирный/центр |  |  |
| 5 | Фильтр на заголовке |  |  |
| 6 | Ширины столбцов (40/100/100/500/80/140/80/80/140 px) |  |  |
| 7 | Колонка «Дата» — `dd.mm.yyyy HH:MM MSK` |  |  |
| 8 | Колонка «Статус» переведена |  |  |
| 9 | Колонка «Контакты» — Да/Нет |  |  |
| 10 | `report_exclude` отфильтрованы |  |  |
| 11 | В логах есть `🚀/📦/✅/📤/🎉`, нет traceback |  |  |

URL таблицы: _____

### 2. `create_orders_report(user_id)` — заказы юзера

| # | Пункт | Прошло | Коммент |
|---|-------|:------:|---------|
| 1 | Несколько вкладок у юзера с рефералами |  |  |
| 2 | Одна вкладка у юзера без рефералов |  |  |
| 3 | Колонка «Дата» — `dd.mm.yyyy HH:MM MSK` |  |  |
| 4 | Юзер без заказов → «⚠️ Пользователь не оставил заказов!», без падения |  |  |
| 5 | Форматирование (ширины, фильтр, заголовок) на каждой вкладке |  |  |

URL таблицы: _____
user_id: _____

### 3. `create_refills_report(user_id)` — пополнения юзера

| # | Пункт | Прошло | Коммент |
|---|-------|:------:|---------|
| 1 | Вкладки по рефералам |  |  |
| 2 | Колонка «Дата» — ожидаемая регрессия (ISO вместо dd.mm.yyyy)? |  |  |
| 3 | Юзер без пополнений → «⚠️ Пользователь не вносил деньги!» |  |  |
| 4 | Форматирование применено |  |  |

URL таблицы: _____
user_id: _____

### 4. `create_reviews_report(orders)` — отзывы

| # | Пункт | Прошло | Коммент |
|---|-------|:------:|---------|
| 1 | 8 колонок, форматирование, фильтр |  |  |
| 2 | Колонка «Дата» — `dd.mm.yyyy HH:MM MSK` |  |  |
| 3 | «Сервис» — русские названия |  |  |
| 4 | «Статус» переведён |  |  |
| 5 | `report_exclude` отфильтрованы |  |  |

URL таблицы: _____

## Phase B — нагрузочный прогон

См. Task 3.

## Найденные баги

- _(заполняется по ходу прогона)_
```

- [ ] **Step 2.2: Sanity-чек окружения**

Run (на хосте, в основном репозитории):
```
cd /Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot && docker compose ps
```
Expected: оба сервиса `bot` и `api` в статусе `Up`.

Run:
```
docker exec original_avito_pf_bot-bot-1 ls /app/utils/dev-trees-414317-e16633571d94.json
```
Expected: путь напечатан без ошибки.

- [ ] **Step 2.3: Прогон выгрузки 1 — общий отчёт `create_sheet()`**

В Telegram-админке: главное меню админа → раздел «Заказы» → кнопка «📊 Google Sheets» (callback `gsheets`).

В отдельном окне терминала перед нажатием:
```
docker logs -f original_avito_pf_bot-bot-1
```

После получения ссылки в чате:
1. Открыть таблицу в браузере, проверить пункты 1–10 чек-листа Phase A → 1.
2. В логе контейнера убедиться в наличии `🚀 / 📦 / ✅ / 📤 / 🎉` (пункт 11), отсутствии traceback.
3. Отметить пункты в `2026-05-23-gsheets-exports-verification-results.md`, вписать URL таблицы.

- [ ] **Step 2.4: Прогон выгрузки 2 — `create_orders_report(user_id)` с рефералами**

Подобрать в БД юзера с непустым полем `referals`:
```
docker exec original_avito_pf_bot-bot-1 sqlite3 /app/storage/database.db \
  "SELECT id, user_name, referals FROM users WHERE referals != '' AND referals IS NOT NULL LIMIT 3"
```

В админке: magic-команда `report` по этому юзеру → подменю «orders».

Заполнить пункт 1 чек-листа (несколько вкладок) и пункты 3, 5.

- [ ] **Step 2.5: Прогон выгрузки 2 — `create_orders_report(user_id)` без рефералов**

Подобрать юзера без рефералов, но с заказами:
```
docker exec original_avito_pf_bot-bot-1 sqlite3 /app/storage/database.db \
  "SELECT u.id, u.user_name FROM users u JOIN orders o ON o.user_id = u.id \
   WHERE (u.referals IS NULL OR u.referals = '') GROUP BY u.id LIMIT 3"
```

В админке: magic → этот юзер → orders. Заполнить пункт 2 чек-листа.

- [ ] **Step 2.6: Прогон выгрузки 2 — юзер без заказов и без рефералов**

Подобрать:
```
docker exec original_avito_pf_bot-bot-1 sqlite3 /app/storage/database.db \
  "SELECT u.id, u.user_name FROM users u \
   WHERE (u.referals IS NULL OR u.referals = '') \
     AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id) LIMIT 3"
```

В админке: magic → этот юзер → orders.
Expected: текст «⚠️ Пользователь не оставил заказов!», без падения.
Отметить пункт 4 чек-листа.

- [ ] **Step 2.7: Прогон выгрузки 3 — `create_refills_report(user_id)`**

Подобрать юзера с пополнениями:
```
docker exec original_avito_pf_bot-bot-1 sqlite3 /app/storage/database.db \
  "SELECT u.id FROM users u JOIN refills r ON r.user_id = u.id GROUP BY u.id LIMIT 3"
```

В админке: magic → юзер → refills.

При проверке колонки «Дата» специально посмотреть формат:
- Если рендерится как `2026-…T…Z` → отметить «регрессия подтверждена», добавить пункт в раздел «Найденные баги» с заголовком `create_refills_report: amount_date без format_display`.
- Если по какой-то причине отображается `dd.mm.yyyy HH:MM MSK` → пометить «нет регрессии (Google ISO-autoformat?)» и оставить URL для дальнейшего разбора.

Заполнить пункты 1, 3, 4. Подобрать юзера без пополнений для пункта 3.

- [ ] **Step 2.8: Прогон выгрузки 4 — `create_reviews_report(orders)`**

В админке открыть админ-меню отзывов; найти кнопку, которая ведёт к [handlers/admin_reviews.py:244](handlers/admin_reviews.py:244). Если кнопка не очевидна — посмотреть, какой callback её триггерит:
```
grep -n "report_url = create_reviews_report" handlers/admin_reviews.py
```
и вверх по файлу найти `@dp.callback_query_handler(...)`/`@dp.message_handler(...)`, чтобы понять, какую команду/кнопку нажать.

Прогнать, заполнить пункты 1–5 чек-листа.

- [ ] **Step 2.9: Commit отчёта (Phase A результаты)**

```bash
git add docs/superpowers/specs/2026-05-23-gsheets-exports-verification-results.md
git commit -m "docs: gsheets verification — phase A results"
```

---

## Task 3: Прогон фазы B — нагрузочный тест на 3000 заказов

**Files:**
- Modify: `docs/superpowers/specs/2026-05-23-gsheets-exports-verification-results.md`

- [ ] **Step 3.1: Доставить скрипт в контейнер**

Run (из worktree этой ветки):
```
docker cp scripts/seed_load_test_orders.py original_avito_pf_bot-bot-1:/tmp/seed.py
docker exec original_avito_pf_bot-bot-1 ls -la /tmp/seed.py
```
Expected: размер ~4–5 КБ, файл присутствует.

- [ ] **Step 3.2: Зафиксировать базовый RSS контейнера `bot`**

В отдельном окне терминала:
```
docker stats --no-stream original_avito_pf_bot-bot-1
```
Записать значение MEM USAGE как **baseline** в раздел «Phase B → исходный RSS» отчёта.

- [ ] **Step 3.3: Инжект 3000 заказов**

Run:
```
docker exec original_avito_pf_bot-bot-1 python /tmp/seed.py 3000
```
Expected: одна строка вида `[seed] inserted 3000 rows in <X>.<XX> sec (user_id=<N>, marker='LOAD_TEST_3K')`, без traceback.

Если скрипт упал с `users table is empty` или `user_id ... is in report_exclude` — починить (создать тест-юзера или передать `--user-id`), повторить.

- [ ] **Step 3.4: Sanity на БД**

Run:
```
docker exec original_avito_pf_bot-bot-1 sqlite3 /app/storage/database.db \
  "SELECT COUNT(*) FROM orders WHERE user_name = 'LOAD_TEST_3K'"
```
Expected: `3000`.

- [ ] **Step 3.5: Запустить мониторинг RSS и логов**

В одном окне:
```
docker stats original_avito_pf_bot-bot-1
```
В другом:
```
docker logs -f --tail 0 original_avito_pf_bot-bot-1
```

- [ ] **Step 3.6: Прогнать `create_sheet()` через админку**

В Telegram нажать «📊 Google Sheets». Засечь время от нажатия до получения ссылки в чате (по часам/секундомеру).

Во время выполнения:
- Следить за `docker stats` — записать **пиковое MEM USAGE**.
- В `docker logs` должны появиться строки `📦 Обработка заказов 0-1000 / 1000-2000 / 2000-3000` (вместе с existing orders).

Записать в отчёт:
- время выполнения (сек)
- baseline RSS, peak RSS, delta
- факт появления батч-логов

- [ ] **Step 3.7: Проверить выходную таблицу**

Открыть полученную ссылку. Проверить:
1. Все строки `LOAD_TEST_3K` присутствуют (фильтр по колонке «username» = `LOAD_TEST_3K`, либо по «id» = тест-юзер).
2. Их кол-во = 3000.
3. Даты `LOAD_TEST_3K` строк — `dd.mm.yyyy HH:MM MSK`, не ISO.
4. Форматирование (заголовок, фильтр, ширины) применилось.

Заполнить чек-лист Phase B в отчёте.

- [ ] **Step 3.8: Cleanup**

Run:
```
docker exec original_avito_pf_bot-bot-1 python /tmp/seed.py --cleanup
```
Expected: `[seed] cleanup: deleted 3000 rows with marker 'LOAD_TEST_3K'`.

Verify:
```
docker exec original_avito_pf_bot-bot-1 sqlite3 /app/storage/database.db \
  "SELECT COUNT(*) FROM orders WHERE user_name = 'LOAD_TEST_3K'"
```
Expected: `0`.

Также удалить скрипт из контейнера:
```
docker exec original_avito_pf_bot-bot-1 rm /tmp/seed.py
```

- [ ] **Step 3.9: Commit отчёта (Phase B результаты)**

```bash
git add docs/superpowers/specs/2026-05-23-gsheets-exports-verification-results.md
git commit -m "docs: gsheets verification — phase B (3k load test) results"
```

---

## Task 4: Финал — баги в виде отдельных тасков и итоговое резюме

**Files:**
- Modify: `docs/superpowers/specs/2026-05-23-gsheets-exports-verification-results.md`

- [ ] **Step 4.1: По каждому найденному багу — заполнить раздел отчёта**

Для каждого бага в разделе «Найденные баги» написать:
```markdown
### Bug: <короткий заголовок>
- **Где:** `path/to/file.py:LINE`
- **Симптом:** <что увидели в таблице/логе>
- **Воспроизведение:** <шаги>
- **Severity:** low / medium / high
- **Рекомендация:** <одно предложение>
```

Ожидаемый минимум — 1 баг: `create_refills_report: amount_date без format_display` (если регрессия подтвердилась в Step 2.7).

- [ ] **Step 4.2: Записать итоговое резюме в конец отчёта**

Добавить раздел:
```markdown
## Итоги

- Прогон выполнен: 2026-05-23
- Phase A: <N>/<всего> пунктов прошли
- Phase B: время выполнения <T> сек, RSS delta <Δ> МБ, OOM: нет/да
- Найдено багов: <K> (severity high: <X>, medium: <Y>, low: <Z>)
- Рекомендация по релизу: blocker / ok с фиксами / ok
```

- [ ] **Step 4.3: Commit финального отчёта**

```bash
git add docs/superpowers/specs/2026-05-23-gsheets-exports-verification-results.md
git commit -m "docs: gsheets verification — final summary"
```

- [ ] **Step 4.4: Открыть PR в dev**

Run:
```
gh pr create --base dev --title "verify(gsheets): manual + 3k load test of 4 export functions" --body "$(cat <<'EOF'
## Summary
- Прогон верификации 4 выгрузок Google Sheets (`utils/googlesheets.py`) после миграции дат на ISO+UTC.
- Phase A: ручной прогон 4 функций через Telegram-админку, чек-лист.
- Phase B: 3000 синтетических заказов через `scripts/seed_load_test_orders.py`, замер RSS и времени выполнения `create_sheet()`.
- Найденные баги задокументированы в `docs/superpowers/specs/2026-05-23-gsheets-exports-verification-results.md`.

## Test plan
- [ ] Спека и план в `docs/superpowers/specs/` и `docs/superpowers/plans/` читаются и согласованы.
- [ ] Отчёт-результат содержит заполненные чек-листы, URL таблиц, baseline/peak RSS.
- [ ] Скрипт `scripts/seed_load_test_orders.py` парсится и не имеет побочных эффектов кроме DB INSERT/DELETE.
- [ ] Cleanup подтверждён в отчёте (`COUNT(*) WHERE marker = 0`).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review (выполнено автором плана)

**Spec coverage:**
- 4 функции выгрузки → Tasks 2.3 / 2.4–2.6 / 2.7 / 2.8 ✓
- Нагрузочный прогон 3k → Task 3 ✓
- ISO → dd.mm проверка на каждой выгрузке → отдельные пункты в чек-листах ✓
- Не-цели (не чиним баги, не пишем тесты с моком) → Task 4.1 фиксирует только в отчёте ✓
- Доставка скрипта через `docker cp` → Step 3.1 ✓
- RSS delta ≤ ~500 МБ → Step 3.6 + чек-лист пункт записывает delta ✓
- Cleanup и проверка cleanup → Steps 3.8 + verify ✓
- Идемпотентность скрипта (повторный seed добавляет, не дубликатит) → cleanup отвечает за чистоту ✓

**Placeholders:** Прошёлся — нет «TBD», «дописать позже», «similar to», кода-плейсхолдеров. Команды и SQL приведены полностью.

**Type/name consistency:** `LOAD_TEST_3K` — единый литерал везде. `DATABASE_PATH=/app/storage/database.db` — единый путь. `scripts/seed_load_test_orders.py` (на хосте) ↔ `/tmp/seed.py` (в контейнере) — разделение явное в Step 3.1.

