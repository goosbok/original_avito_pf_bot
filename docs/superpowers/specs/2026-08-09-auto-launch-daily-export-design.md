# Ежедневная выгрузка авто-запусков ПФ — Design

**Дата:** 2026-08-09
**Статус:** Approved
**Опирается на:** [2026-06-08-pf-executor-auto-mode-design.md](2026-06-08-pf-executor-auto-mode-design.md),
[2026-05-23-gsheets-exports-verification-design.md](2026-05-23-gsheets-exports-verification-design.md)

## TL;DR

Каждый день в 06:00 МСК бот перезаписывает вкладку «Авто запуски» в рабочей
Google-таблице и кидает админам ссылку в TG. Во вкладке — все ссылки,
отправленные в биза в auto-режиме за последние 30 дней, со всеми данными
запуска. Чтобы отдать главную колонку («ссылка с поисковым запросом»),
в `order_links` добавляется `search_link`, заполняемая в момент dispatch'а;
исторические строки восстанавливаются бэкфиллом из `avito_ad_phrase_cache`.

## Контекст

Заказчик (Игорь) мониторит запуски вручную, чтобы ловить «отлёты и ненаходы» —
задачи, которые ушли в биза, но не встали в работу из-за битой ссылки или
снятого с публикации объявления. Сейчас у него нет ни одного среза по
auto-запускам: вкладка «Manual задачи» показывает ровно противоположное
множество (`delivery_mode='manual'`), а «Все заказы» — всё подряд, без
поисковой фразы.

### Что уже есть

| Требование заказчика | Источник в БД | Готово? |
|---|---|---|
| Ссылка на объявление | `order_links.url` | да |
| Контакты крутим или нет | `orders.contacts` | да |
| Количество ПФ | `orders.position_name` (`дни/ПФ`) | да |
| Дата, до какого крутим | `order_links.deadline_at` | да |
| Номер заказа | `orders.increment`, `order_links.external_id` | да |
| Идентификатор клиента | `orders.user_id` | да |
| Ссылка с поисковым запросом | — | **нет** |

Фраза берётся из `avito_ad_phrase_cache` в момент классификации
(`services/order_links_classifier.classify`), уходит в биза в поле
`search_link` payload'а (`services/pf_executor_api._build_avito_payload`) и
теряется. Кэш перетирается ежедневным скрейпом дашборда, поэтому «посмотреть
задним числом» ≠ «что реально отправили».

Инфраструктура выгрузок готова: одна общая таблица
(`GSHEETS_TARGET_SHEET_ID`), запись через `utils/googlesheets._write_tab()`,
близкий аналог — `create_manual_tasks_sheet()`.

## Goals

- Ежедневная (06:00 МСК) автоматическая перезапись вкладки «Авто запуски».
- Уведомление админам в TG со ссылкой на вкладку.
- Кнопка в админке для обновления вкладки по требованию.
- Сохранение реально отправленной поисковой фразы на каждой auto-ссылке.
- Восстановление фразы для уже отправленных задач (best-effort).

## Non-goals

- Сверка с дашбордом биза (кто «встал в работу», а кто нет) — выгрузка даёт
  Игорю данные для ручной сверки, автоматизация сверки отдельной задачей.
- История глубже 30 дней. Окно скользящее, старое вытесняется.
- Отдельный файл/таблица на каждый день.
- Выгрузка manual-ссылок — для них уже есть вкладка «Manual задачи».
- Runtime-переключение флагов через админку (только env + рестарт).

## Изменения схемы БД

### Миграция

В `utils/sqlite3.apply_phase2_migrations()`, по образцу `dispatch_attempts`
(строка ~1101):

```sql
ALTER TABLE order_links ADD COLUMN search_link TEXT
```

Guard — тот же `PRAGMA table_info(order_links)` + проверка наличия колонки.
В `get_table_statements()` DDL `order_links` дополняется `search_link TEXT`,
счётчик колонок 13 → 14.

### Семантика

- `NULL` — фраза неизвестна (manual-ссылка, либо auto-ссылка, отправленная до
  релиза и не покрытая бэкфиллом).
- Непустая строка — поисковая фраза (URL), с которой задача ушла в биза.
- Значение неизменяемо после установки: ни dispatch, ни бэкфилл не
  перезаписывают уже заполненное поле.

Отдельной колонки-признака «фраза восстановлена бэкфиллом, а не записана при
отправке» **нет** — сознательное решение заказчика, чтобы не зашумлять
таблицу. Практическое следствие: для строк, отправленных до релиза, фраза
может отличаться от фактически отправленной, если кэш успел обновиться.

## Архитектура

### Модули

| Модуль | Роль |
|---|---|
| `services/order_links.py` | `mark_in_work()` принимает и персистит `search_link` |
| `services/order_links_dispatcher.py` | пробрасывает фразу в три вызова `mark_in_work` |
| `utils/sqlite3.py` | миграция + запрос `get_auto_launched_links(days)` |
| `utils/googlesheets.py` | `create_auto_tasks_sheet()` → вкладка «Авто запуски» |
| `services/auto_launch_export.py` | **новый**: `export_auto_launches()` + `run_auto_export_loop()` |
| `handlers/admin_orders.py` | кнопка «Авто запуски» |
| `web/main.py` | старт лупа в lifespan |
| `scripts/backfill_order_links_search_link.py` | **новый**: одноразовый бэкфилл |

### Запись фразы

`mark_in_work(link_id, *, delivery_mode, deadline_at, external_id,
search_link=None)` — новый именованный аргумент, пишется в той же транзакции,
что и остальные поля перехода `pending → in_work`. `None` не затирает.

Три места вызова в `order_links_dispatcher.py`, во всех фраза уже на руках:

1. штатный успех `submit_link` (`_dispatch_one`, ~строка 164) — `phrase`;
2. adopt после `ExecutorAPIError` + `find_existing_task` (~строка 151) —
   `phrase` из того же `classify()`;
3. `force_dispatch` (~строка 397) — `phrase` из `classify(force=True)`.

### Бэкфилл

`scripts/backfill_order_links_search_link.py`, идемпотентный, без HTTP:

```
SELECT id, url FROM order_links
WHERE delivery_mode='auto' AND search_link IS NULL
```

для каждой строки `extract_ad_id(url)` → `avito_phrase_cache.lookup(ad_id)`;
при попадании — `UPDATE ... SET search_link=? WHERE id=? AND search_link IS NULL`.
Промахи кэша и ссылки без `ad_id` пропускаются и считаются в итоговый лог
(`processed / filled / no_ad_id / cache_miss`). Повторный прогон безопасен.

### Запрос выгрузки

`utils/sqlite3.get_auto_launched_links(days=30)`:

```sql
SELECT
  o.increment AS order_id, o.user_id, o.position_name, o.contacts,
  ol.url, ol.search_link, ol.status AS link_status,
  ol.started_at, ol.deadline_at, ol.external_id
FROM order_links ol
JOIN orders o ON o.increment = ol.order_id
WHERE ol.delivery_mode='auto'
  AND ol.started_at IS NOT NULL
  AND date(ol.started_at) >= date('now', ?)   -- '-30 days'
ORDER BY ol.started_at DESC, ol.id DESC
```

Фильтр по `started_at` (а не по дате заказа) — это и есть «когда запустили».
`delivery_mode='auto' AND started_at IS NOT NULL` отсекает и manual, и
pending-ссылки, которые до биза не доехали.

### Вкладка «Авто запуски»

`utils/googlesheets.create_auto_tasks_sheet()`, `TAB_AUTO_TASKS = 'Авто запуски'`,
запись через существующий `_write_tab()` (заголовок, фильтр, ширины — бесплатно).

| # | Колонка | Источник | Ширина |
|---|---|---|---|
| 1 | Ссылка с поисковым запросом | `search_link` или `''` | 500 |
| 2 | Ссылка на объявление | `url` | 500 |
| 3 | Контакты | `contacts` → `Да`/`Нет` | 90 |
| 4 | ПФ в день | `position_name.split('/')[1]` | 90 |
| 5 | Старт | `started_at` → `dd.mm.yyyy` | 100 |
| 6 | Крутим до | `deadline_at` → `dd.mm.yyyy` | 100 |
| 7 | Номер заказа | `order_id` | 110 |
| 8 | Задача в биза | `external_id` | 110 |
| 9 | ID клиента | `user_id` | 130 |
| 10 | Статус ссылки | `link_status` | 110 |

Колонки 7 и 8 обе нужны: заказчик просит «номер заказа», но в его
референсной таблице шестизначные числа — это ID задач биза, а не наши
инкременты.

Битый `position_name` (нет `/`, не число) → в колонку 4 пишется пустая
строка, строка не выпадает из выгрузки.

### Планировщик

`services/auto_launch_export.py`:

- `export_auto_launches() -> str` — синхронная, вызывает
  `create_auto_tasks_sheet()`, возвращает URL вкладки. Число строк не
  прокидывается наружу: `create_auto_tasks_sheet` уже пишет его в лог, а
  ломать симметрию с остальными `create_*_sheet()` ради строчки в сообщении
  не стоит.
- `next_run_at(now_msk) -> datetime` — ближайшие `PF_AUTO_EXPORT_HOUR_MSK:00`
  МСК строго в будущем.
- `run_auto_export_loop()` — asyncio-луп по образцу
  `avito_phrase_cache_refresh.run_refresh_loop`. Стартует в lifespan
  `web/main.py` рядом с остальными ПФ-лупами. Сам Sheets-вызов синхронный и
  блокирующий → выполняется через `asyncio.to_thread`.

Догон пропуска при старте: луп хранит дату последней успешной выгрузки в
таблице `settings` (`get_setting` / `edit_setting`, ключ
`auto_export_last_run_date`, значение — ISO-дата МСК). `edit_setting` —
UPSERT, отдельная инициализация не нужна; `get_setting` на отсутствующем
ключе вернёт `None`, что трактуется как «никогда не запускались». Если
сохранённая дата меньше сегодняшней МСК-даты и текущее время уже позже
`PF_AUTO_EXPORT_HOUR_MSK` — выгрузка выполняется сразу на старте, потом луп
уходит в обычное расписание.

Побочный эффект: ключ виден в админском списке настроек (`get_all_settings`).
Это приемлемо и даже полезно — дата последней выгрузки на виду.

### Конфиг

В `data/config.py`, по образцу `PF_AUTO_DISPATCH_ENABLED`:

```python
PF_AUTO_EXPORT_ENABLED: bool = (
    os.getenv("PF_AUTO_EXPORT_ENABLED", "false").lower() in ("1", "true", "yes")
)
PF_AUTO_EXPORT_HOUR_MSK: int = max(
    0, min(23, int(os.getenv("PF_AUTO_EXPORT_HOUR_MSK", "6")))
)
```

Флаг гейтит **только луп**. Кнопка в админке работает всегда — она не должна
зависеть от расписания. Значения дублируются в `.env.example`.

### Админ-кнопка

Хендлер `gsheets_auto` в `handlers/admin_orders.py` — копия `gsheets_manual`
(строка ~920): удалить сообщение, показать «⏳ Готовлю Авто запуски…» +
wait-стикер, вызвать `create_auto_tasks_sheet()`, отдать ссылку через
`gsheets_url(...)`, подчистить прогресс-сообщения в `finally`. Кнопка
добавляется в ту же клавиатуру, где живёт «Manual задачи».

## Обработка ошибок

| Сбой | Поведение |
|---|---|
| Google API упал в лупе | `logger.exception`, сообщение в топик `errors`, дата последней выгрузки **не** обновляется → следующий старт контейнера догонит |
| Google API упал по кнопке | сообщение «⚠️ Ошибка при генерации Авто запусков», как в `gsheets_manual` |
| `GSHEETS_TARGET_SHEET_ID` не задан | `_require_target()` кидает `RuntimeError` — существующее поведение |
| `send_admins` упал после успешной выгрузки | лог `exception`, дата **обновляется** (выгрузка-то сделана), повтора не будет |
| Бэкфилл: промах кэша | строка пропускается, считается в лог, не ошибка |
| `mark_in_work` без `search_link` | `NULL`, выгрузка покажет пустую ячейку — не падаем |

Логи: `auto_export.start`, `auto_export.done date=… url=…`,
`auto_export.failed`, `auto_export.catchup date=…`,
`auto_export.boot_check_failed`, `auto_export.loop_iter_failed`.

Число выгруженных строк пишет соседняя строка из `utils/googlesheets.py`
(`gsheets: 'Авто запуски' updated, N rows, url=…`) — дублировать его в
`auto_export.done` не стали.

## Тесты

Юнит, по образцу `tests/unit/test_gsheets_manual_tasks.py` (fixture `tmp_db`):

**`get_auto_launched_links`**
- берёт только `delivery_mode='auto'` со `started_at`; не берёт manual,
  pending и auto-без-`started_at`;
- отсекает строки старше окна, включает строку ровно на границе;
- порядок — новыми сверху.

**`mark_in_work` + `search_link`**
- фраза персистится вместе с `external_id`/`deadline_at`;
- вызов без `search_link` оставляет `NULL` и не падает;
- повторный `mark_in_work` не затирает уже записанную фразу.

**Dispatcher**
- штатный успех пишет фразу из `classify`;
- adopt-ветка после `ExecutorAPIError` пишет ту же фразу;
- `force_dispatch` пишет фразу.

**Бэкфилл**
- заполняет только `auto` + `NULL`;
- не трогает уже заполненные и manual-строки;
- повторный прогон — ноль изменений;
- ссылка без `ad_id` не роняет проход.

**`next_run_at`**
- до часа X сегодня → сегодня в X;
- ровно в X → завтра в X;
- после X → завтра в X.

**`create_auto_tasks_sheet`** (мок `_write_tab` / Sheets API)
- 10 колонок в заданном порядке, заголовки как в спеке;
- `contacts` → `Да`/`Нет`; битый `position_name` → пустая ячейка;
- пустая выборка даёт вкладку с одними заголовками.

Прогон — внутри Docker (`docker exec`), как принято в проекте.

## План выката

1. Мигрируем схему (миграция идемпотентна, применяется на старте).
2. Прогоняем `scripts/backfill_order_links_search_link.py` на проде.
3. Проверяем вкладку кнопкой в админке.
4. Включаем `PF_AUTO_EXPORT_ENABLED=true`, рестарт.
5. На следующее утро сверяем, что пришло сообщение в TG.

Откат: `PF_AUTO_EXPORT_ENABLED=false` + рестарт. Колонка `search_link`
остаётся — она безвредна и её наполнение продолжится.
