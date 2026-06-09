# PF Executor Auto-Mode — Design

**Date:** 2026-06-08
**Status:** Draft
**Builds on:** [2026-06-07-order-links-extraction-design.md](2026-06-07-order-links-extraction-design.md)

## 1. Цель

Зажечь auto-режим в `services/order_links_dispatcher.py`: вместо текущих заглушек
(`classifier → manual`, `pf_executor_api → ExecutorAPIRejected`) — реально
отправлять пригодные ссылки заказа в API исполнителя
(`biznesklondaik.ru/fwdrjjkigor_new/api/`), без участия админа.

Логика классификации: смотрим, есть ли в **кэше известных объявлений** запись
по нашему `ad_id`. Если есть — берём оттуда last-used `search_link` (ключевую
фразу) и шлём в API. Если нет — отдаём админу в manual (как сейчас).

Кэш строится bulk-скрейпом дашборда исполнителя (`/pf-avito/dashboard.php`)
один раз в сутки. Это снимает потолок `limit=500` публичного `get-tasks.php`
и даёт hot-path без внешних HTTP при оплате заказа.

## 2. Скоуп

**В скоупе:**
- Реальный HTTP-клиент `services/pf_executor_api.py::submit_link` через
  `add-tasks.php` с X-API-KEY.
- Helper `services/avito_url.py::extract_ad_id(url)`.
- Локальный кэш `avito_ad_phrase_cache(ad_id PK, search_link, …)` в SQLite.
- Cookie-auth модуль `services/biznesklondaik_client.py` — fresh login каждый
  раз через POST формы → `requests.Session()` → выкидываем.
- Скрейпер `dashboard.php?daterange=…` чанками по 4 дня + BeautifulSoup-парсер
  табличных строк.
- Скрипт `scripts/backfill_avito_phrase_cache.py` — 90-дневный initial pull,
  идемпотентен.
- Cron-loop `daily_refresh_phrase_cache` — раз в сутки 2-дневное окно.
- Rewrite `services/order_links_classifier.py::classify` под cache lookup.
- Структурные логи каждого decision'а classifier'а.
- Hourly метрика `auto_rate = N_auto / N_total за последний час`.
- Два feature-flag'а:
  - `PF_PHRASE_CACHE_REFRESH_ENABLED` (default `false`)
  - `PF_AUTO_DISPATCH_ENABLED` (default `false`)

**Out of scope:**
- Cleanup старых записей кэша (не делаем сейчас — таблица растёт органически).
- Stop-task через API (только submit; остановка остаётся через админ-кнопку
  «failed»).
- Балансный мониторинг счёта у исполнителя (`get-balance.php`) — отдельной
  задачей.
- Real-time webhook от исполнителя о статусе задач (closure всё ещё по
  `deadline_at` через `close_expired_links`).
- Runtime-toggle флагов через админку (только env, требует рестарт).
- Self-invalidation кэша по сигналу о неверной фразе.

## 3. Модель данных

### 3.1. Таблица `avito_ad_phrase_cache`

```sql
CREATE TABLE avito_ad_phrase_cache(
    ad_id TEXT PRIMARY KEY,
    search_link TEXT NOT NULL,
        -- last-used ключевая фраза для этого объявления
    created_at TIMESTAMP NOT NULL,
        -- created_at той задачи у исполнителя (для merge: latest wins)
    cached_at TIMESTAMP NOT NULL
        -- наша метка последнего апсёрта (для health-check)
);
```

Индексов больше не нужно — PK покрывает все обращения hot-path'а.

### 3.2. Семантика

- Одна строка на `ad_id`. Если по объявлению несколько задач — храним только
  ту, у которой `created_at` максимальна (последняя версия фразы).
- `cached_at` пишем при каждом успешном апсёрте (merge MAX(cached_at)).
- Никакого TTL/staleness — пока. Все известные ad_id считаются «auto-годными».

### 3.3. Изменений в существующих таблицах нет

`order_links`, `orders` — без изменений. Auto-режим работает через те же
поля (`delivery_mode='auto'`, `external_id`, `started_at`, `deadline_at`).

## 4. Архитектура

### 4.1. Модули

- **`services/avito_url.py`** — pure helper, `extract_ad_id(url) -> str | None`.
- **`services/biznesklondaik_client.py`** — login flow + GET dashboard +
  парсер HTML. Stateless: каждый вызов = `requests.Session()` → login →
  fetch → return parsed rows → drop session.
- **`services/avito_phrase_cache.py`** — CRUD кэша: `lookup(ad_id)`,
  `upsert_many(rows)`, `last_refreshed_at()` (для health).
- **`services/pf_executor_api.py`** — переписать `submit_link` под реальный
  POST `add-tasks.php`. Контракт сигнатуры расширяется: добавляется
  именованный `search_phrase: str`.
- **`services/order_links_classifier.py`** — переписать `classify(url, order)`
  под cache lookup + feature-flag check.
- **`services/order_links_dispatcher.py`** — минимальная правка `_dispatch_one`,
  чтобы достать phrase и пробросить в `submit_link`.
- **`services/avito_phrase_cache_refresh.py`** — `refresh_recent(days=2)` +
  `run_refresh_loop()` (asyncio cron). По аналогии с `order_links_deadline.py`.
- **`scripts/backfill_avito_phrase_cache.py`** — 90-дневный initial pull
  чанками по 4 дня. Идемпотентен.

### 4.2. Источники данных

| Что | Откуда | Авторизация |
|---|---|---|
| Bulk история объявлений | `GET /pf-avito/dashboard.php?daterange=…` | cookies (login flow) |
| Отправка задачи в работу | `POST /api/add-tasks.php` | X-API-KEY (header) |
| (НЕ используем) `get-tasks.php` | — | — |

Cookie-auth используется **только на чтение**. Любая мутация (submit) — через
X-API-KEY на отдельном эндпоинте.

### 4.3. Конфиг

Новые env-переменные:

```env
# Biznesklondaik — auto-mode integration
BIZA_API_BASE_URL=https://biznesklondaik.ru/fwdrjjkigor_new/api
BIZA_DASHBOARD_BASE_URL=https://biznesklondaik.ru/fwdrjjkigor_new/pf-avito
BIZA_API_KEY=                       # для add-tasks.php
BIZA_LOGIN=                         # для login → dashboard scrape
BIZA_PASSWORD=                      # для login → dashboard scrape

# Feature flags
PF_PHRASE_CACHE_REFRESH_ENABLED=false
PF_AUTO_DISPATCH_ENABLED=false

# Tuning
PF_PHRASE_CACHE_CHUNK_DAYS=4          # размер окна при backfill
PF_PHRASE_CACHE_REFRESH_INTERVAL_H=24 # период refresh-cron'а
PF_DASHBOARD_REQUEST_DELAY_SEC=3      # пауза между чанками при backfill
```

Поля логина-формы (`username`/`password` или иные имена) определяются при
первом подключении и фиксируются в `biznesklondaik_client.py`.

## 5. Поведение по сценариям

### 5.1. Hot-path: оплата заказа

При `pay_with_balance` / `mark_paid` дёргается `dispatch_pending_links` (уже
существует). На каждой pending-ссылке:

```
1. mode = current_mode or classify(url, order)
2. classify(url, order):
   - if not PF_AUTO_DISPATCH_ENABLED: return ('manual', None)  ← log decision
   - ad_id = extract_ad_id(url)
   - if not ad_id: return ('manual', None)                     ← log decision
   - phrase = cache.lookup(ad_id)
   - if not phrase: return ('manual', None)                    ← log decision
   - return ('auto', phrase)                                   ← log decision
3. if mode == 'manual': delivery_mode='manual', stay pending
4. if mode == 'auto':
   - external_id = submit_link(url, order, search_phrase=phrase)
   - on success: mark_in_work(delivery_mode='auto',
                              deadline_at=compute_deadline(order),
                              external_id=external_id)
   - on ExecutorAPIRejected: fallback to manual
   - on ExecutorAPIError: leave pending+auto, cron retry
```

**Никаких внешних HTTP при classify** — только локальное `SELECT … FROM
avito_ad_phrase_cache WHERE ad_id=?` (миллисекунды).

### 5.2. Daily refresh

`run_refresh_loop()` (asyncio task в lifespan'е web/main.py):

1. Если `PF_PHRASE_CACHE_REFRESH_ENABLED == false`, спать
   `PF_PHRASE_CACHE_REFRESH_INTERVAL_H` часов и повторять.
2. Иначе: вычисляем окно `[now - 2 days, now]` в формате `YYYY_M_D`.
3. `BiznesklondaikClient(login, password).fetch_dashboard(date_from, date_to)`.
4. Парсим HTML, экстрактим `(ad_id, search_link, created_at)`.
5. Группируем by `ad_id`, берём latest по `created_at`.
6. `avito_phrase_cache.upsert_many(rows)` — апсёрт с `WHERE excluded.created_at
   > avito_ad_phrase_cache.created_at` (latest wins).
7. Лог: `refresh: N rows fetched, M unique ads, K upserted`.
8. Sleep до следующего тика.

Sleep-первое-итерация-потом-работа гарантирует, что флаг можно флипнуть в
`true` без рестарта (на следующий тик подхватит). Если хотим **мгновенно** —
рестарт контейнера.

### 5.3. Initial backfill (один раз, руками)

```bash
docker compose exec bot python -m scripts.backfill_avito_phrase_cache --days 90
```

Скрипт:
1. Вычисляет окна `[today-90d, today-86d], [today-86d, today-82d], …` —
   `PF_PHRASE_CACHE_CHUNK_DAYS=4`-дневные чанки.
2. Для каждого окна: login → fetch → parse → upsert.
3. Между чанками — `PF_DASHBOARD_REQUEST_DELAY_SEC` (по умолчанию 3 сек).
4. Идемпотентен: повторный запуск перезаливает кэш, упсёрт берёт latest.
5. Лог progress: `chunk X/23: N rows, M new ads, …`.

Запускается **после** деплоя кода, **до** включения `PF_AUTO_DISPATCH_ENABLED`.

### 5.4. Логи и метрики

**Decision-логи** в classifier (`logger.info`, structured):

```python
logger.info(
    "classifier.decision",
    extra={"link_id": link_id, "ad_id": ad_id or "none",
           "decision": "auto"|"manual",
           "reason": "feature_off"|"no_ad_id"|"cache_miss"|"cache_hit"}
)
```

Источники reason'ов:
- `feature_off` — `PF_AUTO_DISPATCH_ENABLED=false`
- `no_ad_id` — regex не выделил id из URL
- `cache_miss` — ad_id есть, но в кэше пусто
- `cache_hit` — auto, phrase подтянулась

**Метрика auto_rate** — отдельная asyncio-задача, раз в час:

```python
N_auto, N_total = SELECT
  SUM(CASE WHEN delivery_mode='auto' THEN 1 ELSE 0 END),
  COUNT(*)
FROM order_links
WHERE created_at >= datetime('now', '-1 hour')
  AND delivery_mode IS NOT NULL

logger.info("metric.auto_rate",
            extra={"auto": N_auto, "total": N_total,
                   "rate": N_auto / max(N_total, 1)})
```

Никакой отдельной таблицы — читаем из `order_links` напрямую.

## 6. Парсинг dashboard.php

### 6.1. URL

```
GET https://biznesklondaik.ru/fwdrjjkigor_new/pf-avito/dashboard.php
    ?filter=
    &daterange=YYYY_M_D+-+YYYY_M_D
```

Формат даты — без ведущих нулей (`2026_6_8`), пробелы вокруг дефиса
закодированы как `+`.

### 6.2. Структура HTML

Сервер отдаёт всю выборку одним ответом (без серверной пагинации). При
текущем масштабе одно 4-дневное окно ≈ 3 тыс строк / 7 МБ HTML.

Каждая строка таблицы `<tbody> <tr>…</tr> </tbody>`. Извлекаем:

| Поле | Источник в HTML |
|---|---|
| `ad_id` | regex `_(\d{8,})` из ссылки `dashboard-status.php?ad_link=…` |
| `search_link` | текст ячейки 3 (после чекбокса и даты) |
| `created_at` | текст ячейки 2 (формат `YYYY-MM-DD HH:MM`) |
| `sql_id` | `data[<id>][sql_id]` из hidden input (опционально, для дебага) |

Реализация — `BeautifulSoup` + явный обход `<tr>` строк. Robustness: если
одна строка не парсится — лог `warning`, остальные обрабатываются.

### 6.3. Логин-форма

POST на форму логина (URL и имена полей определяются при первом подключении
через DevTools). Скорее всего:

```
POST /fwdrjjkigor_new/login.php
Content-Type: application/x-www-form-urlencoded

username=...&password=...&remember=on
```

Возврат — `Set-Cookie: PHPSESSID=…; remember_user_id=…; …`.

`requests.Session` подхватывает cookies автоматически. Дальнейший GET
dashboard'а идёт по этой же сессии.

После работы — сессия не сохраняется, при следующем refresh — новый login.

## 7. Тестирование

### Unit-тесты

- **`test_avito_url.py`**: extract_ad_id для разных форм URL (с/без `www`,
  `m.avito.ru`, query-string, fragments, мусор, короткие промо-ссылки).
- **`test_biznesklondaik_client.py`**: login flow на mock (`responses`),
  fetch_dashboard на захардкоженом sample HTML (срез реальной выгрузки,
  ~10 строк). Парсер должен достать ad_id/phrase/created_at.
- **`test_avito_phrase_cache.py`**: lookup, upsert_many (latest wins по
  created_at), idempotency повторного upsert'а.
- **`test_pf_executor_api.py`**: формирование payload `add-tasks.php`
  (dates, fix_count, search_link, ad_link), маппинг ошибок (400→Rejected,
  401/429/5xx→Error). Mock HTTP.
- **`test_order_links_classifier.py`**: 4 reason'а decision'а (feature_off,
  no_ad_id, cache_miss, cache_hit). Проверяем что лог содержит правильный
  reason.
- **`test_avito_phrase_cache_refresh.py`**: skip когда feature off,
  правильный date-range, упсёрт после fetch.
- **`test_backfill_script.py`**: правильное разбиение на чанки,
  идемпотентность.

### Интеграционные тесты

- e2e dispatcher: оплата → classify (cache mock с фразой) → submit_link
  (mock возвращает external_id) → ассерт `link.status='in_work'`,
  `delivery_mode='auto'`, `external_id` записан.
- e2e с feature off: оплата → ничего из API не дёргается, всё уходит в manual.

### Что **не** тестируем автоматически

- Реальные HTTP-запросы к биза в CI (нужны live-креды).
- Структура их HTML — она снапшотится из реального ответа и хранится
  в `tests/fixtures/biznesklondaik_dashboard_sample.html`. Если они
  изменят вёрстку — упадут unit-тесты парсера, надо обновить fixture.

## 8. Открытые вопросы / Follow-up

1. **Имена полей логин-формы** — определяются при первом подключении к
   живому endpoint'у. Сейчас закладываемся на типовые `username`/`password`,
   корректируем при тесте.
2. **Cleanup кэша** — out of scope сейчас; решим когда (если) таблица
   станет ощутимо большой.
3. **Stale phrase** — если у объявления реально сменилась рабочая фраза,
   а старая в кэше → отправим устаревшую и она не сработает. Без
   self-invalidation сейчас — на проде увидим failed-ссылки, тогда
   подумаем (отдельной задачей).
4. **Балансный алерт** — нужен ли cron, который дёргает `get-balance.php` и
   алертит в support-thread при пороге? Отдельной задачей.
5. **Region для Avito** — публичное API не принимает `region_lr`, всё
   привязано к URL объявления. Никаких региональных полей в payload
   `add-tasks.php` не шлём.
6. **`fix_count` = `views_per_day`** — мапим один-в-один. Если бизнес
   поменяется (нелинейная связь) — отдельной задачей.
