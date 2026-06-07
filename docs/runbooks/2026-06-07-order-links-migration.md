# Migration Runbook — Order Links Extraction

**Дата:** 2026-06-07
**Ветка:** `claude/crazy-rubin-6424dc` (merge target: `dev`)
**Спек:** `docs/superpowers/specs/2026-06-07-order-links-extraction-design.md`
**План:** `docs/superpowers/plans/2026-06-07-order-links-extraction.md`

## Что меняется в проде

1. **Новая таблица `order_links`** — ссылки заказа хранятся построчно со статусной машиной `pending → in_work → done/failed` и полем `delivery_mode (auto/manual)`.
2. **`orders.status` становится derived** — пересчитывается агрегатом по `order_links` в той же транзакции что и мутация ссылки.
3. **Колонка `orders.links` НЕ дропается** в этом релизе. Новые заказы пишут туда NULL; backfill заполняет `order_links` из legacy данных. Дроп — отдельным PR через ~неделю.
4. **2 новых cron-loop'а** запускаются вместе с `payment_expiry`:
   - `run_dispatcher_loop` каждые 5 мин — добивает paid-заказы с нерасклассифицированными ссылками
   - `run_deadline_loop` каждые 15 мин — закрывает `in_work → done` по истечении дедлайна
5. **Stub'ы для классификатора и API исполнителя** — пока всё классифицируется как `manual`, API всегда отказывает (fallback в manual). Это намеренно — UX админа не меняется, ссылки уходят в шит, оттуда админ обрабатывает руками.
6. **Админка:**
   - Кнопка «✅ Выполнить» (`gotovoebat`) **удалена** — статус заказа теперь derived.
   - Новая кнопка «📤 Отправил все manual» — bulk-перевод `pending+manual → in_work`.
   - Новая кнопка «❌ Заказ failed» — FSM-флоу с причиной.
   - Карточка заказа показывает per-link статусы.
7. **Google Sheets:**
   - «Все заказы» переписан на JOIN, добавлены колонки link_status/delivery_mode/deadline.
   - «Заказы юзера» показывает статус каждой ссылки в ячейке.
   - **Новый таб «Manual задачи»** — основной рабочий инструмент админа.
8. **SQLite hardening** — WAL mode, busy_timeout=5s, foreign_keys=ON в `services/db.py::connect()`.

## Что НЕ меняется

- TG бот UX для юзера тот же (но теперь `confirm_order` идёт через `services.orders.create_unpaid + pay_with_balance` вместо legacy `add_order`).
- Платежи (YooKassa flow, балансы) — без изменений.
- Существующие notify-каналы (Telegram push + LK bell) переиспользуются.

---

## Pre-flight checklist

Запустить на prod-сервере перед началом деплоя:

```bash
ssh root@185.106.93.71
cd /root/original_avito_pf_bot

# 1. Бэкап БД
cp storage/database.db storage/database.db.bak-pre-order-links-$(date +%Y%m%d-%H%M%S)
ls -la storage/database.db*

# 2. Зафиксировать текущий код
git rev-parse HEAD

# 3. Проверить что есть свободное место (новая таблица ~10KB на 1000 ссылок)
df -h /root
```

## Шаги деплоя

### 1. Подтянуть код

```bash
ssh root@185.106.93.71
cd /root/original_avito_pf_bot
git fetch origin
git checkout dev
git pull origin dev
git log -1 --oneline  # должен быть merge commit с order-links изменениями
```

### 2. Пересобрать образ

```bash
docker compose build api bot
```

### 3. Поднять сервисы

```bash
docker compose up -d api bot
```

**Что происходит автоматически при старте:**
- `apply_phase2_migrations` идемпотентно создаст таблицу `order_links` + индексы (если не существуют).
- WAL mode включится при первом `connect()`.
- Cron-loop'ы `run_deadline_loop` и `run_dispatcher_loop` стартуют в lifespan FastAPI.

Подождать 30 сек, проверить логи:

```bash
docker compose logs --tail=50 api | grep -E "(deadline|dispatcher|expiry|order_links) loop started"
# Ожидаемые строки:
#   payment expiry loop started (interval=60s)
#   deadline loop started (interval=900s)
#   dispatcher loop started (interval=300s)
```

Если loop'ов нет в логах — что-то пошло не так с lifespan. **Stop, не двигаемся дальше.**

### 4. Запустить backfill

```bash
docker compose exec api python -m scripts.migrate_order_links 2>&1 | tee /tmp/backfill.log
```

**Ожидаемый вывод:** `backfill: processed N orders`, где N = число заказов с непустым `orders.links` (legacy).

**Проверка:**

```bash
docker compose exec api python -c "
import sqlite3
con = sqlite3.connect('/app/storage/database.db')
print('orders:', con.execute('SELECT COUNT(*) FROM orders WHERE links IS NOT NULL AND links != \"\"').fetchone()[0])
print('order_links rows:', con.execute('SELECT COUNT(*) FROM order_links').fetchone()[0])
print()
print('orders по статусам:')
for s, n in con.execute('SELECT status, COUNT(*) FROM orders GROUP BY status'):
    print(f'  {s}: {n}')
print()
print('order_links по статусам:')
for s, n in con.execute('SELECT status, COUNT(*) FROM order_links GROUP BY status'):
    print(f'  {s}: {n}')
"
```

Соотношение должно быть: каждый `done`/`failed`/`cancelled` заказ → соответствующие done/failed link'и; каждый `paid` → pending link'и.

### 5. Очистка corrupted URLs (legacy data quality)

```bash
# Сначала dry-run — посмотреть что будет тронуто
docker compose exec api python -m scripts.cleanup_corrupted_urls 2>&1 | tee /tmp/cleanup-dry.log

# Внимательно прочитать отчёт. Если изменения логичны:
docker compose exec api python -m scripts.cleanup_corrupted_urls --apply 2>&1 | tee /tmp/cleanup-apply.log
```

Этот скрипт находит URL с literal `\n`/`\r`/`\t`/leading/trailing whitespace (legacy data corruption) и:
- Нормализует URL (убирает мусор)
- Дедуплицирует в рамках одного заказа (если несколько ссылок имеют одинаковый нормализованный URL — оставляет одну с лучшим status'ом)

### 6. Прогнать dispatcher на накопленных pending

```bash
docker compose exec api python -c "
from services.order_links_dispatcher import dispatch_for_paid_orders
n = dispatch_for_paid_orders()
print(f'dispatched: {n} orders')
"
```

Это разово прогонит классификатор по всем backfill'нутым paid-заказам, расставит `delivery_mode='manual'` (stub-классификатор), чтобы они попали в выгрузку «Manual задачи». Cron всё равно сделает это раз в 5 минут, но руками быстрее.

### 7. Дымовая проверка через бот

В Telegram:
1. Открыть админку → «Заказы» → «📋 Manual задачи в шит» — должна сгенерироваться гугл-таблица с manual-ссылками.
2. Открыть какой-нибудь paid-заказ — карточка должна показать ссылки с их статусами.
3. Создать тестовый заказ с тестового аккаунта (если есть тестовая среда), проверить что:
   - Появилась запись в `orders` со status='paid'
   - Появились строки в `order_links` со status='pending', delivery_mode='manual'
   - Юзер получил Telegram-пуш «принят в работу»

### 8. Мониторинг 24 часа

```bash
# Логи cron-loops — не должно быть exceptions
docker compose logs api 2>&1 | grep -E "deadline|dispatcher" | tail -50

# Логи бота — не должно быть exceptions в pf_order
docker compose logs bot 2>&1 | grep -i "confirm_order\|pf_order" | tail -50

# Состояние БД
docker compose exec api python -c "
import sqlite3
con = sqlite3.connect('/app/storage/database.db')
con.row_factory = sqlite3.Row
print('orders by status:')
for r in con.execute('SELECT status, COUNT(*) c FROM orders GROUP BY status ORDER BY c DESC'):
    print(f'  {r[\"status\"]}: {r[\"c\"]}')
print()
print('order_links by status × delivery_mode:')
for r in con.execute('SELECT status, delivery_mode, COUNT(*) c FROM order_links GROUP BY status, delivery_mode ORDER BY status'):
    print(f'  {r[\"status\"]}/{r[\"delivery_mode\"]}: {r[\"c\"]}')
"
```

Что мониторить:
- Растёт ли `order_links` (новые заказы пишут туда)
- Уменьшается ли количество `pending+manual` после bulk-нажатий админа
- Закрываются ли заказы через deadline-cron (paid → done без ручного вмешательства)

---

## Откат

Если что-то пошло не так в первые часы:

```bash
# 1. Остановить сервисы
docker compose stop api bot

# 2. Восстановить БД
cp storage/database.db.bak-pre-order-links-* storage/database.db

# 3. Откатить код
git checkout <previous-commit-sha>

# 4. Пересобрать и поднять
docker compose build api bot
docker compose up -d api bot
```

**Важно:** код этого PR умеет работать с пустым `order_links` (graceful fallback на legacy `orders.links` через миграцию, но новые заказы пишут только в `order_links`). Откат БД + код безопасен.

---

## Финальный шаг — через ~неделю

Когда убедимся что новый flow стабилен:

```bash
docker compose exec api python -m scripts.drop_orders_links_column
```

Этот скрипт **не существует пока** — он создаётся отдельным PR в недельной перспективе. Содержание:

```python
# scripts/drop_orders_links_column.py (заготовка)
"""Phase 2: ALTER TABLE orders DROP COLUMN links.

Запускать ВРУЧНУЮ через ~неделю после деплоя order-links extraction
и только когда убедились что:
1. Все новые заказы пишут в order_links (orders.links=NULL).
2. Никакой код не читает orders.links.
3. Backfill для всех легаси заказов прошёл успешно.
"""
import sqlite3
from services.db import connect

with connect() as con:
    # Проверка: убедиться что есть order_links rows и orders.links не используется
    cnt_with_legacy_links = con.execute(
        "SELECT COUNT(*) FROM orders WHERE links IS NOT NULL AND links != ''"
    ).fetchone()[0]
    cnt_without_order_links = con.execute(
        "SELECT COUNT(*) FROM orders o "
        "WHERE NOT EXISTS (SELECT 1 FROM order_links ol WHERE ol.order_id=o.increment) "
        "AND o.status NOT IN ('unpaid','payment_failed','cancelled')"
    ).fetchone()[0]
    if cnt_without_order_links:
        raise SystemExit(
            f"Abort: {cnt_without_order_links} живых заказов без order_links. "
            f"Прогони backfill ещё раз."
        )
    print(f"safe to drop. legacy links column still has data for {cnt_with_legacy_links} rows (will be lost).")
    print("Proceeding to DROP COLUMN in 5s...")
    import time
    time.sleep(5)
    con.execute("ALTER TABLE orders DROP COLUMN links")
    con.commit()
    print("dropped.")
```

---

## Контакты при инциденте

- Спек: `docs/superpowers/specs/2026-06-07-order-links-extraction-design.md`
- Структура коммитов: смотри `git log claude/crazy-rubin-6424dc..dev --oneline` после мержа
- Тесты: `docker compose --profile test run --rm test` (466 unit tests, все зелёные)
