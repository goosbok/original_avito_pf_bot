# Унификация форматов дат: ISO внутри, dd.mm.yyyy на UI

**Дата:** 2026-05-23
**Статус:** draft → требует ревью

## Проблема

В БД сейчас сосуществуют два формата дат:

- **Legacy** — `"23.05.2026 14:30:00"` (`%d.%m.%Y %H:%M:%S`, локальное время сервера).
  Пишется в: `orders.date`, `reviews.date`, `delreviews.date`, `seo.date`
  (если таблица есть — CREATE для неё отсутствует, но `add_order_seo` пишет туда;
  миграция должна быть защищена от OperationalError), `guest_orders.created_at`,
  `refills.date`, `support_messages.created_at`.
- **ISO+UTC** — `"2026-05-23T11:30:00+00:00"`. Пишется в `users.reg_date`,
  `auth_providers.*`, `email_verification_tokens.*`, `password_reset_tokens.*`,
  `application_*.*`, `notifications.created_at` и т.д.

Это вызвало баг в админ-дашборде: `web/routers/admin_stats.py` строит
фильтр `WHERE date LIKE 'YYYY-MM-DD%'`, что никогда не матчит legacy-формат.
Из-за этого `orders_today` и `revenue_today` всегда возвращают 0.

## Цель

Привести **хранение** всех дат к единому формату — **ISO 8601 с UTC**.
Сохранить **отображение** в Telegram-сообщениях и Google Sheets в привычном
для пользователей виде `dd.mm.yyyy HH:MM`.

## Design decisions

### D1. ISO+UTC как канонический формат хранения

`datetime.now(timezone.utc).isoformat()` →
`"2026-05-23T11:30:00.123456+00:00"` (микросекунды).

**Почему:**
- Сравнения корректны лексикографически (`LIKE 'YYYY-MM-DD%'`, `>`, `<`).
- Часовой пояс эксплицитен — нет тихих ошибок около полуночи.
- Совместимо с `datetime.fromisoformat()` для парсинга.
- Уже используется в `users.reg_date` и аутентификационных таблицах — не
  вводим новый формат, унифицируем под существующий.

### D2. Display-формат `dd.mm.yyyy HH:MM` сохраняем

Пользователи в Telegram и админ-отчётах в Google Sheets привыкли видеть
русский формат. Меняем только внутреннее представление.

`format_display(iso_str) -> "23.05.2026 14:30"` — без секунд, как уже
часто делается в текущих сообщениях.

### D3. Одношаговая идемпотентная миграция

Скрипт `scripts/migrate_dates_to_iso.py` проходит по каждой колонке с
датами, для каждой строки:
- Если значение уже в ISO (или NULL/пустое) — пропустить.
- Если в legacy — распарсить и переписать.
- Иначе — залогировать и пропустить (не падать).

Запускается один раз вручную. После прогона все данные в ISO.

**Идемпотентность нужна** для повторного запуска при сбое и для
безопасной работы на dev-БД, которая может быть частично уже мигрирована.

### D4. Helper-модуль `utils/dates.py`

Единая точка для:
- `now_iso() -> str` — текущее время в ISO+UTC. Заменяет legacy `get_date()`.
- `format_display(value: str | None) -> str` — для UI. Принимает оба
  формата (для совместимости в переходный период и при чтении старых
  данных, если миграция пропустит строку). Возвращает `"dd.mm.yyyy HH:MM"`
  или `""`.
- `parse_any(value: str | None) -> datetime | None` — толерантный парсер
  для критичных мест (если где-то нужно сравнивать как datetime).
  Обобщение существующего `parse_refill_date`.

Старый `utils/other.get_date()` остаётся обёрткой над `now_iso()` для
обратной совместимости (на случай если где-то импортируется в неожиданном
месте), но deprecated в комментарии. Дубль `utils/other_functions.get_date()`
удаляется полностью после проверки, что не используется.

### D5. Часовой пояс — UTC, без исключений

`get_date()` сейчас использует `datetime.today()` — локальное время
сервера, что создаёт скрытые баги. Все новые записи — UTC. Display-форматтер
для пользователей конвертирует в Moscow time (Europe/Moscow, UTC+3) перед
форматированием — это видимая разница, но корректная.

## Архитектура

```
┌─────────────────────────────────────────┐
│ utils/dates.py                          │
│   now_iso()           — writer helper   │
│   format_display()    — UI helper       │
│   parse_any()         — tolerant parser │
└─────────────────────────────────────────┘
         │
         │ used by
         ▼
┌─────────────────────────────────────────┐    ┌─────────────────────────┐
│ Writers (now_iso)                       │    │ Readers (format_display)│
│  utils/other.get_date  → now_iso        │    │  handlers/admin_orders  │
│  services/guest_orders._now → now_iso   │    │  handlers/pf_order      │
│                                         │    │  handlers/reviews       │
└─────────────────────────────────────────┘    │  handlers/admin_reviews │
                                                │  utils/googlesheets     │
                                                └─────────────────────────┘

┌─────────────────────────────────────────┐
│ scripts/migrate_dates_to_iso.py         │
│   One-shot, idempotent.                 │
│   Targets 7 columns across 6 tables.    │
└─────────────────────────────────────────┘
```

## Изменения по файлам

### Новые файлы

- **`utils/dates.py`** — модуль с `now_iso`, `format_display`, `parse_any`.
- **`scripts/migrate_dates_to_iso.py`** — миграция данных.
- **`tests/test_dates.py`** — unit-тесты helper'а.
- **`tests/test_migrate_dates_to_iso.py`** — тест миграции на временной БД.

### Изменяемые файлы

#### Writers

- **`utils/other.py`** — `get_date()` становится тонкой обёрткой над
  `utils.dates.now_iso()` с deprecation-комментарием.
- **`utils/other_functions.py`** — удалить дубль `get_date()` после
  проверки grep'ом, что нигде не используется. Если используется — заменить
  импорты на `utils.other.get_date` (или сразу на `utils.dates.now_iso`).
- **`services/guest_orders.py`** — `_now()` → `now_iso()` из `utils.dates`.

#### Readers (добавить format_display)

- **`handlers/admin_orders.py:234`** — `dat = order['date']` → `dat = format_display(order['date'])`.
- **`handlers/admin_orders.py:478`** — `user['reg_date']` → `format_display(...)`.
- **`handlers/pf_order.py:249`** — `ord_date = order['date']` → `format_display(...)`.
- **`handlers/reviews.py:145, 206`** — `order['date']` → `format_display(...)`.
- **`handlers/admin_reviews.py:152`** — то же.
- **`utils/googlesheets.py:85, 233, 407`** — `order['date']` → `format_display(...)`.

#### Stats fix

- **`web/routers/admin_stats.py`** — упростить:
  - Все таблицы теперь в ISO → `LIKE 'YYYY-MM-DD%'` работает.
  - Добавить `guest_orders` в счёт `orders_today` и `revenue_today`.
  - `revenue_today` для guest — только статусы оплаченных.
- **`web/routers/admin_users.py:33, 112`** — `str(row["reg_date"])`
  возвращается в API; frontend уже умеет ISO — без изменений.

### Удаление дубля

В `utils/other_functions.py` есть `get_date()` (строки 11-13) — точная
копия `utils/other.get_date()`. Найти всех потребителей через
`grep -rn "from utils.other_functions import"`, заменить импорты, удалить
функцию (либо файл, если он был единственной целью).

## Migration script

`scripts/migrate_dates_to_iso.py`:

```python
"""Convert legacy 'dd.mm.YYYY HH:MM:SS' dates to ISO+UTC across all
affected columns. Idempotent — safe to re-run.

Usage: python scripts/migrate_dates_to_iso.py [--dry-run]
"""
TARGETS = [
    ("orders", "date"),
    ("reviews", "date"),
    ("delreviews", "date"),
    ("seo", "date"),                      # пропускается, если таблицы нет
    ("guest_orders", "created_at"),
    ("refills", "date"),
    ("support_messages", "created_at"),
]
```

Для каждой цели:
1. `SELECT rowid, <col> FROM <table> WHERE <col> IS NOT NULL`.
2. Для каждой строки пытаемся `datetime.strptime(value, "%d.%m.%Y %H:%M:%S")`.
   - Успех → конвертируем в UTC (наивные строки трактуем как Europe/Moscow,
     т.к. сервер исторически в этой зоне), сериализуем как ISO,
     `UPDATE <table> SET <col>=? WHERE rowid=?`.
   - `ValueError` → пробуем `datetime.fromisoformat(value)`:
     - Успех → уже мигрировано, пропустить.
     - Fail → залогировать `"unrecognized format: <value>"`, пропустить.
3. После прогона по всем таблицам — итоговая статистика:
   `Total: X rows migrated, Y already ISO, Z skipped (unrecognized).`

Скрипт защищён `--dry-run` для проверки без изменений.

**Trade-off:** трактуем legacy как Europe/Moscow на основании того, что
исторически бот деплоился на серверы в RU. Если когда-то записи делались
в другой TZ — будет ошибка на ±N часов. Альтернатива — трактовать как UTC,
но тогда заказы «съезжают» в прошлое относительно реального времени их
создания. Moscow более точно.

## Testing strategy

### Unit tests (новые)

`tests/test_dates.py`:
- `now_iso()` возвращает строку с `+00:00`, парсится обратно через
  `fromisoformat`.
- `format_display(ISO) == "dd.mm.yyyy HH:MM"` в Moscow time.
- `format_display(legacy)` тоже корректно (для совместимости).
- `format_display(None)`, `format_display("")` → `""`.
- `parse_any(ISO)`, `parse_any(legacy)`, `parse_any(invalid)` → ожидаемое.

`tests/test_migrate_dates_to_iso.py`:
- Создать временную БД, вставить смешанные данные (legacy + ISO + NULL +
  битые строки), запустить миграцию, проверить:
  - Legacy → ISO.
  - ISO неизменён.
  - NULL неизменён.
  - Битые залогированы, не упали.
  - Повторный запуск ничего не меняет (идемпотентность).

### Regression tests (расширить)

- Тест на `/api/admin/stats`, который вставляет сегодняшний заказ через
  `add_order()` (теперь пишет ISO) и проверяет, что `orders_today == 1`.
- Тест на `format_display` в `handlers/admin_orders.py` — мокать сообщение
  и проверить, что строка содержит `dd.mm.yyyy HH:MM`.

### Manual smoke

- Прогнать миграцию на копии prod-БД, проверить визуально несколько строк.
- Запустить бота локально, попросить отчёт по заказу — убедиться, что
  даты в TG-сообщении отображаются как `dd.mm.yyyy HH:MM`.
- Открыть админ-дашборд, проверить ненулевые значения.

### Запуск тестов

Все тесты прогоняются через docker:
```
docker exec <container> pytest tests/test_dates.py tests/test_migrate_dates_to_iso.py -v
```

## Rollback strategy

**До прогона миграции:** обязательный бэкап `cp data/db.sqlite data/db.sqlite.bak-pre-iso`.

**Если что-то пошло не так после миграции:**
1. Остановить сервис.
2. `mv data/db.sqlite.bak-pre-iso data/db.sqlite`.
3. Откатить код на коммит до миграции (`git revert`).
4. Перезапустить сервис.

**Если проблема обнаружена в коде, но миграция уже прошла:**
- Откат кода → опционально откат данных (новые записи будут в ISO, а
  старые потребители ожидают legacy). Безопаснее восстановить из бэкапа.

## Risks

1. **Telegram-сообщения сломанные**, если пропустим reader. Митигация:
   grep-обход всех `'date'`, `'reg_date'`, `'created_at'` в `handlers/` и
   `utils/googlesheets.py` перед коммитом.
2. **Google Sheets смешанный формат** — если миграция мигрировала БД, но
   старые строки в Sheets остались в legacy, новые — в ISO. Это
   нивелируется `format_display`, который к моменту записи в Sheets уже
   возвращает `dd.mm.yyyy HH:MM`. Поэтому новые строки в Sheets будут в
   старом формате — таблица консистентна.
3. **Часовой пояс legacy-данных** — трактуем как Moscow. Если в истории
   были записи из другой TZ — будет сдвиг. На текущей кодовой базе нет
   признаков смены TZ, риск низкий.
4. **`get_date()` импортируется напрямую** — если оставим обёртку, всё
   работает; если удалим — тесты упадут на импорте. Поэтому helper
   оставляем как deprecated alias.
5. **Тесты внутри docker** — нужно убедиться, что `utils/dates.py`
   импортируется в тестовом контейнере. Память подсказывает запускать
   через `docker exec`, локальный `python3` не работает.

## Out of scope

- Унификация TZ серверного процесса (Docker, cron). Сейчас базовая
  стратегия — всегда UTC в данных, конвертация в Moscow только на дисплее.
- Изменение схемы БД (типы колонок). Все колонки остаются `TIMESTAMP`/
  `TEXT` — SQLite толерантна.
- Расширение admin-дашборда на «за неделю / за месяц». Это отдельная
  задача.

## Acceptance criteria

1. `python scripts/migrate_dates_to_iso.py --dry-run` показывает план без
   ошибок.
2. Реальный прогон конвертирует все legacy-строки.
3. После миграции открытие админ-дашборда показывает корректные
   `orders_today` и `revenue_today` (включая гостевые).
4. Любой Telegram-отчёт с датой показывает формат `dd.mm.yyyy HH:MM`.
5. Все существующие тесты + новые проходят в docker.
6. Скрипт идемпотентен — повторный запуск возвращает «0 migrated».
