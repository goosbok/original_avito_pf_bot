# Order Links Extraction — Design

**Date:** 2026-06-07
**Status:** Draft

## 1. Цель

Вынести ссылки заказа из `orders.links TEXT` (где сейчас три разных формата записи: `json.dumps`, `str(list)`, CSV) в отдельную таблицу `order_links` с явным жизненным циклом каждой ссылки. Статус заказа становится агрегатом по статусам ссылок, что позволяет:

1. Корректно отслеживать, какие ссылки уже запущены в работу, а какие ещё нет.
2. Различать ссылки, которые отправляются через API исполнителя автоматически, и те, которые админ обрабатывает вручную.
3. Автоматически закрывать заказ в `done` через cron по истечении срока работы, без ручного клика админа по кнопке «Выполнен».
4. Дать админу понятную выгрузку «что прокручивать сегодня» в Google Sheets.

## 2. Скоуп

**В скоупе:**
- Новая таблица `order_links` со статусной машиной.
- Миграция legacy `orders.links` в `order_links` (парсер трёх форматов + backfill).
- Сервисный слой `services/order_links.py` с единственной точкой мутации и пересчётом `orders.status` в той же транзакции.
- Stub-классификатор auto/manual и stub-клиент API исполнителя (с правильными интерфейсами под будущую реализацию).
- Cron-job: `in_work → done` по истечении `deadline_at`.
- Админ-кнопка «Отправил все manual-ссылки» с двойным подтверждением.
- Админ-кнопка «Отметить заказ failed» с указанием причины.
- Удаление текущей кнопки «Выполнен» из `handlers/admin_orders.py`.
- Обновление Google Sheets экспортов: «Все заказы», «Заказы юзера», новый таб «Manual задачи».

**Out of scope:**
- Реальная классификация auto/manual (заглушка возвращает `manual`).
- Реальный API-клиент исполнителя (заглушка отказывает, fallback в manual).
- Автоматический рефанд при `failed` заказа — отдельной задачей.
- Cutoff 4:00 МСК для `start_date` при создании заказа — отдельной задачей.
- 2-way синхронизация с Google Sheets — выгрузка остаётся read-only.

## 3. Модель данных

### 3.1. Таблица `order_links`

```sql
CREATE TABLE order_links(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
        -- pending | in_work | done | failed
    delivery_mode TEXT,
        -- NULL (ещё не классифицирована) | 'auto' | 'manual'
    deadline_at TIMESTAMP,
        -- когда cron должен попытаться in_work → done
    started_at TIMESTAMP,     -- переход pending → in_work
    done_at TIMESTAMP,
    failed_at TIMESTAMP,
    failure_reason TEXT,
    external_id TEXT,         -- id у API исполнителя
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(increment)
);

CREATE INDEX idx_order_links_order ON order_links(order_id);
CREATE INDEX idx_order_links_deadline
    ON order_links(status, deadline_at) WHERE status = 'in_work';
```

### 3.2. Статусная машина ссылки

```
pending ──────► in_work ──────► done
   │               │
   └──────► failed ◄
```

| from \ to | in_work | done | failed |
|---|---|---|---|
| pending | ✓ | ✗ | ✓ |
| in_work | ✗ | ✓ | ✓ |
| done | — terminal — |
| failed | — terminal — |

Повторный переход в текущий статус — no-op (идемпотентность для cron/webhook retry).

### 3.3. Семантика `status` × `delivery_mode`

| status | delivery_mode | смысл |
|---|---|---|
| pending | NULL | оплата только что прошла, ждёт классификатора |
| pending | auto | API временно отказал, retry в cron'е |
| pending | manual | ждёт админской кнопки «Отправил» — попадает в выгрузку шита |
| in_work | auto | в API |
| in_work | manual | админ нажал «Отправил» |
| done / failed | (любое) | terminal |

### 3.4. Изменения в `orders`

- `links TEXT` — удаляется в две фазы:
  1. Phase 1 (этот спек): backfill в `order_links`, новые заказы пишут `NULL` в `orders.links`.
  2. Phase 2 (через ~неделю после деплоя, отдельным скриптом): `ALTER TABLE orders DROP COLUMN links` (SQLite 3.35+).
- Набор `status`: `unpaid → paid → done | failed | cancelled | payment_failed`. Новых значений не добавляется.

## 4. Архитектура

### 4.1. Источник правды и агрегация

`orders.status` — **кешированная агрегация** по `order_links`. Источник правды — `order_links`. При любой мутации ссылок выполняется `_recompute_order_status(con, order_id)` в той же транзакции:

```python
counts = COUNT(*) BY status FROM order_links WHERE order_id=?

if counts.pending + counts.in_work > 0:
    остаётся 'paid'        # ещё есть работа
elif counts.failed > 0:
    'failed'               # все terminal, ≥1 failed
else:
    'done'                 # все done
```

Guard: если `orders.status ∈ {unpaid, payment_failed, cancelled}` — `_recompute` **не трогает заказ** (нельзя перейти из неоплаченного в `done` через ссылки).

### 4.2. Модули

- **`services/order_links.py`** — единственный владелец таблицы. CRUD, переходы статусов, пересчёт `orders.status`.
- **`services/order_links_dispatcher.py`** — классифицирует `pending` ссылки, пытается отправить `auto` в API, fallback в `manual`.
- **`services/order_links_deadline.py`** — cron-job для `in_work → done` по `deadline_at`.
- **`services/order_links_classifier.py`** — stub: всегда возвращает `manual`.
- **`services/pf_executor_api.py`** — stub: всегда `raises ExecutorAPIRejected`.
- **`services/exceptions.py`** — новые `LinkNotFound`, `InvalidLinkTransition`, `ExecutorAPIError`, `ExecutorAPIRejected`.

### 4.3. Сервисный API (публичный)

```python
# CRUD
def create_links(con, *, order_id: int, urls: list[str]) -> None
def list_links(order_id: int) -> list[dict]
def get_link(link_id: int) -> dict  # raises LinkNotFound

# Переходы (все идут через приватный _transition с валидацией)
def mark_in_work(link_id, *, delivery_mode: str, deadline_at: str,
                 external_id: str | None = None) -> None
def mark_done(link_id) -> None
def mark_failed(link_id, *, reason: str) -> None

# Bulk-операции
def mark_all_manual_in_work(*, admin_id: int) -> int
def fail_remaining_links(*, order_id: int, reason: str, admin_id: int) -> int
```

Каждый метод вызывает `_recompute_order_status` в той же транзакции и возвращает `(old_status, new_status)` если статус заказа сменился — caller отвечает за `notify_order_status_changed`.

## 5. Поведение по сценариям

### 5.1. Оплата заказа (auto-классификация)

1. `services.orders.pay_with_balance` / `mark_paid` → `orders.status = 'paid'`.
2. В той же транзакции: `dispatch_pending_links(order_id)`:
   - для каждой `pending` ссылки: `classify(url, order) → 'auto' | 'manual'`;
   - `auto` → `submit_link(url, order)`:
     - успех → `mark_in_work(delivery_mode='auto', external_id=...)`, `deadline_at = max(start_date, today) + days`;
     - `ExecutorAPIRejected` → fallback в `manual`: ставим `delivery_mode='manual'`, статус остаётся `pending`;
     - `ExecutorAPIError` (временный сбой) → статус и `delivery_mode` не меняются, retry в cron.
   - `manual` → `delivery_mode='manual'`, статус остаётся `pending`.
3. С текущими stub'ами все ссылки в итоге `pending / manual`.

### 5.2. Админ обрабатывает manual-ссылки

1. Админ открывает Google Sheets таб «Manual задачи» — read-only выгрузка ссылок `pending / manual` с `start_date <= today`.
2. Прокручивает каждую через API исполнителя руками (вне нашей системы).
3. Возвращается в бот, открывает админ-меню → жмёт «📤 Отправил все manual-ссылки».
4. Бот: «Будет переведено в работу: N ссылок. Точно?» `[Да] [Отмена]`.
5. Подтверждение → `mark_all_manual_in_work(admin_id=...)`:
   - SELECT все `pending / manual` с `(start_date IS NULL OR date(start_date) <= date('now'))`;
   - bulk: каждая → `in_work`, `deadline_at = max(start_date, today) + days`;
   - `_recompute_order_status` для каждого затронутого заказа.
6. Сообщение «N ссылок отмечено как отправленные».

### 5.3. Закрытие по deadline

Cron каждые 15 минут вызывает `close_expired_links()`:

```sql
SELECT id, order_id FROM order_links
WHERE status = 'in_work' AND deadline_at < datetime('now')
```

Для каждой `mark_done(link_id)`. Когда последняя ссылка заказа становится terminal — `_recompute_order_status` переводит `orders.status='paid' → 'done'` (или `'failed'`, если есть failed-ссылки). Caller (`close_expired_links`) собирает изменившиеся order_id и вызывает `notify_order_status_changed`.

### 5.4. Админ помечает заказ failed

1. В карточке заказа в админке (только если `order.status == 'paid'`) — кнопка «❌ Отметить failed».
2. FSM: запрашивает причину текстом.
3. Превью: «Будет помечено failed: N ссылок (из M в работе). Юзер получит уведомление. Подтвердить?» `[Да] [Отмена]`.
4. Подтверждение → `fail_remaining_links(order_id, reason, admin_id)`:
   - bulk перевод `pending + in_work` → `failed`;
   - `done` ссылки остаются `done`;
   - `_recompute_order_status` переводит заказ в `failed`.
5. Если в момент клика заказ уже не `paid` (race) — `OrderStatusConflict`, сообщение «Заказ уже в статусе X».

## 6. Миграция

### 6.1. Schema migration

В `utils/sqlite3.py::apply_phase2_migrations` (идемпотентно при каждом старте):
- `CREATE TABLE IF NOT EXISTS order_links(...)` + индексы.
- Колонка `orders.links` пока остаётся (drop в Phase 2).

### 6.2. Backfill

Отдельный скрипт `scripts/migrate_order_links.py`, запускается вручную после деплоя, идемпотентен:

1. SELECT all orders WHERE NOT EXISTS (SELECT 1 FROM order_links WHERE order_id=orders.increment).
2. Парсер `links TEXT`:
   - сначала `json.loads`;
   - при ошибке — `ast.literal_eval`;
   - при ошибке — split по запятым/whitespace.
   - Невалидные значения логируются с `order_id` и пропускаются.
3. Маппинг `orders.status` → начальный `order_links.status`:

| order.status | link.status | timestamps |
|---|---|---|
| `done` | `done` (все) | `done_at = orders.date` |
| `failed` | `failed` (все) | `failed_at = orders.date`, reason='legacy: order failed' |
| `cancelled` | `failed` (все) | `failed_at = orders.date`, reason='legacy: order cancelled' |
| `paid` | `pending` (все) | — |
| `unpaid` / `payment_failed` | `pending` (все) | — |

`delivery_mode` и `deadline_at` у legacy = NULL.

### 6.3. Phase 2: drop колонки

Отдельный скрипт `scripts/drop_orders_links_column.py`, запускается **вручную через ~неделю** после деплоя:
- `ALTER TABLE orders DROP COLUMN links` (SQLite 3.35+).
- К моменту запуска новый код уже не читает/пишет в `orders.links`.

## 7. Google Sheets экспорт

### 7.1. Источник данных

Вместо парсинга `order.links` Python-кодом — SQL с `JOIN`:

```sql
SELECT
    o.increment AS order_id, o.user_id, o.position_name, o.status AS order_status,
    o.date, o.contacts, o.phone, o.start_date,
    ol.url, ol.status AS link_status, ol.delivery_mode, ol.deadline_at,
    u.user_name
FROM orders o
JOIN order_links ol ON ol.order_id = o.increment
JOIN users u ON u.id = o.user_id
WHERE <filter>
ORDER BY <order>
```

Результат — «строка на ссылку», готовый для шита.

### 7.2. Табы

**«Все заказы»** — фильтр `(none)`. Колонки расширяются на `link_status`, `delivery_mode`, `deadline_at`. Структура — как сейчас + новые колонки.

**«Manual задачи»** — фильтр:
```sql
WHERE ol.status = 'pending' AND ol.delivery_mode = 'manual'
  AND (o.start_date IS NULL OR date(o.start_date) <= date('now'))
ORDER BY o.start_date ASC NULLS FIRST, o.date ASC
```
Та же структура колонок, что и в «Все заказы».

**«Заказы юзера»** — то же что сейчас, но статус ссылки добавляется к URL в ячейке:
```
avito.ru/abc  [done]
avito.ru/def  [in_work · manual · до 14.06]
```

### 7.3. Технический долг

Текущие функции `create_orders_report` / `create_user_orders` собирают колонки через множественные `.append`. При добавлении новых полей это тяжелеет. **В скоупе** этой работы — выделить helper `_build_columns(rows, column_specs)` для табов, которые мы и так трогаем. Полный рефакторинг `googlesheets.py` — out of scope.

## 8. Cron-инфраструктура

В проекте уже есть `services/payment_expiry.py` с периодической работой. Новые cron-задачи подключаем по тому же паттерну:

- `close_expired_links` — каждые 15 минут.
- `dispatch_pending_links_for_paid_orders` — каждые 5 минут (добивает `paid` заказы с оставшимися `pending` ссылками — на случай если dispatch при оплате упал).

Если scheduler-инфраструктуры по факту нет — добавим минимальный launcher в `__main__.py` через `asyncio.create_task` с `asyncio.sleep(interval)`.

## 9. Тестирование

### Unit-тесты

- Матрица переходов `_transition` (включая no-op и запреты).
- Агрегация `_recompute_order_status` — все комбинации `{pending, in_work, done, failed}` × counts.
- Guard: `unpaid` order не апается в `done` даже если все ссылки done.
- Парсер легаси-форматов: `json`, `repr`, `csv`, битые данные.
- Маппинг `orders.status` → `link.status` при backfill.
- `dispatch_pending_links`: classifier→manual / classifier→auto + API success / classifier→auto + API rejected / classifier→auto + API error.
- `close_expired_links`: deadline в прошлом / будущем / уже done.
- `compute_deadline`: разные форматы `position_name`, NULL `start_date`.
- `mark_all_manual_in_work`: фильтрация по `start_date`, idempotency.
- `fail_remaining_links`: смесь pending/in_work/done → переводит только pending+in_work; повтор — no-op; guard на не-`paid`.
- Новый SQL для «Manual задачи»: фильтр по in_work+manual+start_date.

### Интеграционные тесты

- paid order → dispatch → все manual → кнопка «Отправил» → пройти время → close_expired → `order.status='done'` + notify юзеру.
- paid order → admin failed → `order.status='failed'` + notify юзеру.
- Backfill: создать legacy БД с разными статусами → прогнать → ассерт корректности.
- Smoke-тест gspread с моком: вызов create_*_report не падает, передаются ожидаемые данные.

## 10. Открытые вопросы / Follow-up

1. **Cutoff 4:00 МСК для `start_date`** — UX для юзера при создании заказа («стартует сегодня/завтра»). На lifecycle ссылок не влияет, отдельной задачей.
2. **Автоматический рефанд при `failed` заказа** — сейчас даже `cancelled` не рефандит. Решается отдельной бизнес-задачей.
3. **Реальный классификатор auto/manual** — стаб в этом спеке, бизнес-логику пишем после.
4. **Реальный API-клиент исполнителя** — стаб в этом спеке, контракт прописываем после уточнения у исполнителя.
5. **Cron-выгрузка в Google Sheets** — сейчас вручную из админки. Можно автоматизировать раз в N минут — отдельной задачей.
