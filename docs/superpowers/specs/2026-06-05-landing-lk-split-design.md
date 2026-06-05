# Landing / LK split + унификация order flow

**Дата:** 2026-06-05
**Ветка:** `claude/busy-feynman-1b53c6` (от `dev`)
**Статус:** Design (требует одобрения)

## 1. Цели

1. Развести лендинг и личный кабинет на разные поддомены, чтобы лендинг можно было обновлять часто и без риска уронить ЛК.
2. Унифицировать order flow: один путь "создать → выбрать оплату → оплатить → исполнить" для гостей и авторизованных. Удалить дублирующую логику `guest_orders`.
3. Сделать вход в ЛК по СМС-коду, чтобы юзер, сделавший быстрый заказ по телефону, мог потом вернуться и увидеть свою историю.

## 2. Принятые решения

| Тема | Решение |
|------|---------|
| Топология | `avito-pf.com` — статический лендинг через nginx; `lk.avito-pf.com` — FastAPI + SPA. |
| Источник лендинга | `web/landing/` в этой же репе. Деплой = `git pull` + nginx подхватывает на лету. |
| Контракт лендинга с ЛК | Только href-ссылки на `lk.avito-pf.com/...`. Никакого JS, обращающегося к API. |
| Корень `lk.avito-pf.com/` | Для незалогиненного — редирект на `/order/new`. |
| Форма заказа | Единая `OrderForm`. На шаге 2 — развилка "быстрый заказ по телефону / войти". |
| Быстрый заказ | Создаёт user с `phone-provider(verified=0)` если телефон не привязан; иначе использует существующего user. |
| Вход по телефону | OTP-код по SMS, отдельная вкладка в `/login`. Верификация — только в момент входа, при быстром заказе СМС не уходит. |
| Order flow | Один пайплайн: `unpaid → paid → done/failed`. Старый "сразу с баланса" удалён. |
| Autostart | Всегда: `paid` сразу исполняется executor'ом. Гостевая ручная модерация админа уходит. |
| TTL `unpaid` | 10 мин для юкассы, 30 мин для баланса. После — `payment_failed` + `Payment.cancel(...)` в юкассе. |
| Действия над `unpaid` | Нет. Юзер выбрал способ оплаты — ждёт или истекает. |
| Видимость `payment_failed` | Видны в истории с пометкой "не оплачен". Кнопка "Повторить" работает. |
| Повтор заказа | Кнопка на `/order/{id}` (для терминальных статусов) клонирует параметры кроме дат. |
| Anti-fraud для битых ссылок | Ничего — наблюдаем статистику, добавим позже. |
| SMS-шлюз | Абстрактный `SmsGateway` интерфейс. Конкретный провайдер выбирается при реализации (на разработку — stub). |
| Стратегия миграции | Big-bang в одном PR. Проект не в проде, даунтайм допустим. |

## 3. Архитектура

### 3.1 Топология deploy

```
                              ┌──────────────┐
              avito-pf.com ───┤              │
                              │              │
                              │   nginx      │
                              │              │
           lk.avito-pf.com ───┤              │
                              └──┬─────────┬─┘
                                 │         │
                  ┌──────────────┘         └──────────────┐
                  │                                       │
                  ▼                                       ▼
          ┌──────────────┐                       ┌─────────────────┐
          │ web/landing/ │                       │ FastAPI :8000   │
          │ (static)     │                       │ (контейнер api) │
          └──────────────┘                       └─────────────────┘
```

- `web/landing/index.html` — standalone HTML (присланный артефакт). Никакого JS, обращающегося к бэку.
- nginx-конфиг: два `server { }` блока. `server_name avito-pf.com; root /app/web/landing;` и `server_name lk.avito-pf.com; proxy_pass http://api:8000;`.
- DNS: `avito-pf.com` и `lk.avito-pf.com` — оба A/CNAME на тот же IP (`185.106.93.71` по памяти).
- TLS: certbot покрывает оба домена (multi-domain cert или два отдельных — решается в инфраструктурной части).

### 3.2 Контейнеры

- Контейнер `api` (FastAPI) — без изменений (тот же `web/main.py`).
- Контейнер `nginx` (или nginx на хосте) — обновлённый конфиг.
- Контейнер `bot` (aiogram) — без изменений в рамках этой работы.

### 3.3 Background job

- `services/payment_expiry.py::run_expiry_loop()` — asyncio task, запускается на FastAPI startup. Раз в 60 сек:
  1. `SELECT id, payment_id, payment_method FROM orders WHERE status='unpaid' AND payment_expires_at < now()`.
  2. Для каждой — если `payment_method='yookassa'`, дёргаем `Payment.cancel(payment_id)` (best-effort, ошибки логируются).
  3. `UPDATE orders SET status='payment_failed' WHERE id=?`.

## 4. Схема БД

### 4.1 `orders` — изменения

**Новые статусы** (`status`) — все строчные snake_case:
- `unpaid` — заказ создан, ждёт оплаты.
- `paid` — оплачен, помещён в очередь на накрутку. (Сам процесс накрутки — вне репы; внешний процесс/админ читает `status='paid'` и обрабатывает.)
- `done` — накрутка успешно завершена.
- `failed` — накрутка упала (плохая ссылка, нет сессий, ошибка Авито).
- `payment_failed` — TTL истёк, оплата не пришла.
- `cancelled` — админ отменил.

**Mapping старых статусов** (используются в 17+ местах: handlers, admin, googlesheets, frontend constants):

| Старый | Новый | Смысл |
|--------|-------|-------|
| `Posted` | `paid` | "размещён, в очереди на работу" → "оплачен, в очереди" |
| `Completed` | `done` | Без изменений семантики |
| `Cancelled` | `cancelled` | Без изменений |
| `Pending` | `payment_failed` | Legacy, нигде в logic не выставляется. Если в БД встретится — мигрируем сюда. |

При big-bang переименовываем повсюду: `services/`, `handlers/`, `web/routers/`, `web/schemas.py::_ORDER_STATUSES`, `web/static/components/Orders.jsx`, `web/static/components/AdminOrders.jsx`, `utils/googlesheets.py`, `scripts/seed_load_test_orders.py`, `services/notifications.py`. Конкретные строки см. в имплементационном плане.

**Новые колонки:**
```sql
ALTER TABLE orders ADD COLUMN payment_method     TEXT;       -- 'balance' | 'yookassa'
ALTER TABLE orders ADD COLUMN payment_expires_at TIMESTAMP;
ALTER TABLE orders ADD COLUMN payment_id         TEXT;       -- yookassa payment_id
ALTER TABLE orders ADD COLUMN phone              TEXT;       -- денормализация
```

### 4.2 `auth_providers` — изменения

```sql
ALTER TABLE auth_providers ADD COLUMN verified INTEGER NOT NULL DEFAULT 1;
-- Существующие записи: verified=1 (TG-контакты, email с подтверждением).
-- Новые phone-провайдеры из быстрого заказа: verified=0.
-- После успешного SMS-OTP: verified=1.
```

### 4.3 `otp_codes` — обобщение под SMS

```sql
ALTER TABLE otp_codes RENAME COLUMN telegram_id TO destination;
ALTER TABLE otp_codes ADD COLUMN channel TEXT NOT NULL DEFAULT 'telegram';
-- destination: для channel='telegram' — строковый tg_id; для channel='sms' — нормализованный E.164.
-- purpose: для SMS-логина — 'phone_login'.
```

### 4.4 `guest_orders` — удаление

```sql
-- Миграция данных: при наличии записей с status='paid' переносим в orders;
-- ищем/создаём user через phone-provider, привязываем order.user_id.
-- Записи pending_payment/failed — мигрируем в payment_failed.

DROP TABLE guest_orders;
```

Если на момент миграции в БД пусто (проект не в проде) — просто `DROP TABLE`.

## 5. Order state machine

```
                          (POST /api/orders/pf)
                                  │
                                  ▼
                              ┌──────┐
                              │unpaid│ ◄─────────────────────┐
                              └───┬──┘                       │
                                  │                          │ ("Повторить" из терминального
              ┌───────────────────┼─────────────────────┐    │   статуса → новый unpaid)
              │                   │                     │    │
        (pay balance)        (pay yookassa)         (TTL)    │
              │                   │                     │    │
              ▼                   ▼                     ▼    │
        списать с баланса   yookassa.Payment       Payment.cancel()
        атомарно            confirmation_url       status='payment_failed' ───┐
              │                   │                                            │
        status='paid'        webhook/polling → mark_paid                       │
              │                   │                                            │
              └─────────┬─────────┘                                            │
                        │                                                      │
                  (внешний процесс накрутки)                                  │
                        │                                                      │
                  ┌─────┴─────┐                                                │
                  ▼           ▼                                                │
              ┌────┐      ┌──────┐                                             │
              │done│      │failed│ ────────────────────────────────────────────┤
              └────┘      └──────┘                                             │
                                  ▲                                            │
                                  │                                            │
                              cancelled (admin) ◄────────────────────────────  ┘
```

**Кто переводит `paid → done/failed`?** Сам процесс накрутки ПФ находится за пределами этой репы (ручная работа или внешний скрипт, читающий `status='paid'` из БД). С точки зрения данной работы — чёрный ящик. Поэтому в коде мы отвечаем только за `unpaid → paid` и `unpaid → payment_failed`. Финальные `done/failed/cancelled` ставит кто-то другой.

## 6. Сценарии

### 6.1 Гость с лендинга → быстрый заказ

```
1. avito-pf.com → клик "Заказать ПФ" → lk.avito-pf.com/order/new
2. Заполнение формы (links, days, fix_count, contacts, согласия)
3. Клик "Далее" → шаг 2: выбор "Быстрый заказ" / "Войти"
4. "Быстрый заказ" → ввод телефона
5. POST /api/orders/pf
   body: {links, days, fix_count, contacts, agreed_*, phone}
   backend:
     - identity.find_or_create_user_by_phone(phone) → user_id
     - INSERT orders(user_id=..., status='unpaid', payment_expires_at=NULL)
   response: {order_id, price, available_methods: ["yookassa"]}
   (для анонима баланса нет → только yookassa)
6. Юзер видит экран "Способ оплаты", выбирает yookassa
7. POST /api/orders/pf/{id}/pay  body: {"method": "yookassa"}
   backend:
     - yookassa.Payment.create(...)
     - UPDATE orders SET payment_method='yookassa', payment_id=..., payment_expires_at=now()+10min
   response: {confirmation_url}
8. Юзер на yookassa оплачивает → возвращается на /order/{id}
9. Frontend polling: GET /api/orders/pf/{id}/payment-status
   backend (если webhook ещё не пришёл): Payment.find_one(payment_id),
   если succeeded → mark_paid (status='paid').
10. Заказ остаётся в paid, пока внешний процесс накрутки не выставит done/failed.
```

### 6.2 Авторизованный юзер → заказ через ЛК

Идентично 6.1 с отличиями:
- Шаг 3 пропускается (выбор "быстрый/войти" не показывается).
- Шаг 5: `phone` не передаётся, `user_id` берётся из сессии.
- Шаг 6: `available_methods` включает `balance` (если хватает) + `yookassa`.

### 6.3 Гость возвращается за историей

```
1. lk.avito-pf.com → редирект на /order/new — но юзер кликает "У меня уже есть аккаунт"
2. /login → вкладка "По телефону"
3. Ввод номера → POST /api/auth/phone/request-code  body: {phone}
   backend:
     - rate-limit checks (см. 9.2)
     - otp.issue(channel='sms', destination=phone, purpose='phone_login', ttl=5min)
     - SmsGateway.send_code(phone, code)
   response: 200
4. Юзер вводит код → POST /api/auth/phone/verify  body: {phone, code}
   backend:
     - otp.verify(...) — макс 3 попытки, иначе сжигаем
     - success: identity.find_or_create_user_by_phone(phone) → user_id
                UPDATE auth_providers SET verified=1 WHERE provider='phone' AND identifier=phone
                выпуск session-cookie (тот же механизм что email/TG)
   response: {user_id}
5. Юзер залогинен, видит все свои заказы (привязанные через phone-provider).
```

### 6.4 Повторить заказ

```
1. /order/{id}, статус терминальный (done/failed/payment_failed/cancelled)
2. Клик "Повторить заказ"
3. Frontend читает поля старого заказа, формирует prefill (всё кроме `days`)
4. Редирект на /order/new?prefill=<sessionStorage_key>
5. Юзер видит заполненную форму, выбирает `days`, нажимает "Далее"
6. Дальше — обычный flow (6.1 или 6.2)
```

## 7. Frontend изменения

### 7.1 Удаляемые компоненты

- `web/static/components/Landing.jsx` — лендинг переезжает на отдельный домен.
- `web/static/components/GuestOrderForm.jsx` — мерджится в `OrderForm`.
- `web/static/components/GuestOrderSuccess.jsx` — мерджится в `OrderDetail`.

### 7.2 Изменяемые компоненты

**`OrderForm.jsx`:**
- Принимает опциональный `prefilledFrom` (для "Повторить заказ").
- Шаг 1: параметры + согласия.
- Шаг 2: для незалогиненного — `<AuthChoice>` ("Быстрый заказ" / "Войти"). Для залогиненного — пропускается.
- Шаг 3: `<PaymentMethodPicker>` — баланс (disabled если не хватает или у юзера нет баланса) + юкасса.

**`OrderDetail.jsx`:**
- Универсальная страница заказа для всех статусов.
- Для `unpaid` — таймер обратного отсчёта TTL, polling статуса каждые 5 сек.
- Кнопка "Повторить" для терминальных.

**`Orders.jsx`:**
- Цветные бейджи для новых статусов.

### 7.3 Новые компоненты

**`PhoneLogin.jsx`** (вкладка в `Auth.jsx`):
- Шаг 1: ввод номера → `POST /api/auth/phone/request-code` → запуск 60с таймера на повтор.
- Шаг 2: ввод 4-6-значного кода → `POST /api/auth/phone/verify`.
- Ошибки: невалидный формат, rate-limit ответ от бэка, 3+ неверных кода — "запросите код заново".

### 7.4 Маршрутизация (`app.jsx`)

```
/                    → if user: /cabinet, else: redirect /order/new
/order/new           → OrderForm (универсальная)
/order/{id}          → OrderDetail
/orders              → Orders
/cabinet             → Cabinet
/login               → Auth (вкладки: email / phone / telegram)
/admin/*             → как есть
```

## 8. Backend API

### 8.1 Удаляемые эндпоинты

- `POST /api/guest-orders/pf`
- `GET /api/guest-orders/{id}/status`
- `GET /api/guest-orders/payment-available`

### 8.2 Новые / изменённые эндпоинты

```
POST /api/orders/pf
  body: {links, days, fix_count, contacts, agreed_privacy, agreed_offer, phone?}
  response: {order_id, price, available_methods}
  — phone опционален: для залогиненного из сессии, для гостя обязателен

POST /api/orders/pf/{id}/pay
  body: {method: "balance" | "yookassa"}
  response:
    method=balance → 200 {status: "paid"}
    method=yookassa → 200 {confirmation_url, expires_at}

GET /api/orders/pf/{id}
  response: {order details + current status}

GET /api/orders/pf/{id}/payment-status
  — polling для юкассы: проверяет webhook или дёргает YooKassa API
  response: {status: "unpaid"|"paid"|"payment_failed", time_remaining?}

POST /api/auth/phone/request-code
  body: {phone}
  response: 200 OK | 429 (rate-limit)

POST /api/auth/phone/verify
  body: {phone, code}
  response: 200 {user_id} | 400 (invalid) | 429 (too many attempts)
```

### 8.3 SmsGateway

```python
# services/sms.py
from typing import Protocol

class SmsGateway(Protocol):
    def send_code(self, phone: str, code: str) -> None: ...

class StubSmsGateway:
    """Логирует код вместо реальной отправки. Для разработки и тестов."""
    last_codes: dict[str, str] = {}
    def send_code(self, phone, code):
        self.last_codes[phone] = code
        logger.info("STUB SMS to %s: code=%s", phone, code)

def get_gateway() -> SmsGateway:
    # читает SMS_GATEWAY из env: "stub" | "smsc" | "smsaero"
    ...
```

Конкретные реализации (`SmscGateway`, `SmsaeroGateway`) добавляются позже при подключении провайдера.

## 9. Edge cases & error handling

### 9.1 Late yookassa payment (после expiry)

Сценарий: TTL истёк, expiry-job дёрнул `Payment.cancel(payment_id)`, поставил `payment_failed`. Юкасса должна отказать в дальнейших оплатах. Но если cancel не сработал и пришёл `succeeded` webhook позже — статус уже `payment_failed`, реактивации не делаем (политика "выбрал способ — всё идёт до конца, expired = всё"). Логируем как аномалию для ручного refund админом.

### 9.2 Rate limiting для SMS-OTP

- Не более 1 запроса в 60 сек на phone (защита от слива через повторы).
- Не более 5 запросов в час на phone (защита от полной долбёжки одного номера).
- Не более 20 запросов в час с одного IP (защита от перебора чужих номеров).

Реализация — в `services/otp.py::issue()`, проверяет `otp_codes` за период.

### 9.3 Race condition: одновременная оплата с баланса и из юкассы

Невозможен: после клика "оплатить с баланса" → atomic SQL: `UPDATE orders SET status='paid', payment_method='balance' WHERE id=? AND status='unpaid'`. Если RETURNING 0 rows — уже оплачено или истекло, показываем ошибку. Юкассовый путь приходит к тому же `UPDATE ... WHERE status='unpaid'` через webhook/polling.

### 9.4 Битая ссылка Авито → накрутка не работает

Per принятому решению — никакой pre-validation. Внешний процесс накрутки выставит `status='failed'` (если он умеет диагностировать причину) или оставит в `paid` если упадёт без обработки исключения. Юзер видит "не получилось" в истории, может "Повторить" с другой ссылкой. Refund пока вручную админом по запросу. Если в будущем будет реализован executor внутри репы — добавим поле `orders.error` с причиной.

### 9.5 Юзер не сделал клик "оплатить" вообще

Создан unpaid, payment_method=NULL, payment_expires_at=NULL. Юзер бросил вкладку. **TTL такого заказа** = 1 час (отдельный default для случая "так и не выбрал способ"). По истечении — `payment_failed`.

## 10. Стратегия миграции

**Big-bang в одном PR.** Проект не в проде, даунтайм допустим.

Порядок коммитов внутри PR (для review-friendly):
1. Миграция схемы БД (новые колонки в `orders`, `verified` в `auth_providers`, обобщение `otp_codes`, миграция данных из `guest_orders` + drop, миграция статусов `Posted/Completed/Cancelled/Pending` → `paid/done/cancelled/payment_failed` в существующих записях).
2. Переименование старых статусов на новые во всех модулях кода: `services/orders.py`, `services/notifications.py`, `handlers/pf_order.py`, `handlers/profile.py`, `handlers/reviews.py`, `handlers/admin_orders.py`, `handlers/admin_reviews.py`, `web/schemas.py`, `web/static/components/Orders.jsx`, `web/static/components/AdminOrders.jsx`, `utils/googlesheets.py`, `scripts/seed_load_test_orders.py`.
3. `services/sms.py` (gateway interface + StubGateway) и обобщённый `services/otp.py` под `channel`/`destination`.
4. `services/orders.py`: новые операции `create_unpaid`, `pay_with_balance`, `pay_with_yookassa`, `mark_paid`, `mark_payment_failed`. Удаление `create_pf_order` (старый "сразу с баланса").
5. `services/payment_expiry.py` + регистрация asyncio task на FastAPI startup (`web/main.py`).
6. `web/routers/orders.py`: новые эндпоинты (`POST /api/orders/pf`, `POST /api/orders/pf/{id}/pay`, `GET /api/orders/pf/{id}/payment-status`).
7. `web/routers/auth_phone.py`: новый router для `/api/auth/phone/*`.
8. Удаление `services/guest_orders.py`, `web/routers/guest_orders.py`, регистрация в `web/main.py`.
9. Frontend: переделка `OrderForm`, `OrderDetail`, удаление `Landing.jsx` / `GuestOrderForm.jsx` / `GuestOrderSuccess.jsx`, добавление `PhoneLogin.jsx`, переработка маршрутизации в `app.jsx`.
10. `web/landing/` — копирование `index.html` (присланного артефакта) + ассеты как статика.
11. nginx-конфиг для двух поддоменов (отдельный файл, путь зависит от инфры).
12. Обновление `.env.example`, `docker-compose.yml` (если меняются переменные), README.

## 11. Стратегия тестирования

**Unit tests:**
- `tests/services/test_orders_new_flow.py` — `create_unpaid`, `pay_with_balance` (с проверкой атомарности), `mark_payment_failed` (с моком юкассы), TTL вычисление.
- `tests/services/test_otp_unified.py` — issue/verify для channel='sms' и channel='telegram', rate-limits, expiry.
- `tests/services/test_identity_phone.py` — `find_or_create_user_by_phone` — три кейса (новый, существующий phone, существующий TG-юзер с phone).

**Integration tests (FastAPI TestClient):**
- `tests/web/test_order_pf_flow.py` — полный цикл: create unpaid → pay balance → done.
- `tests/web/test_order_yookassa.py` — с моком YooKassa: create → /pay yookassa → webhook → done.
- `tests/web/test_payment_expiry.py` — создать unpaid, симулировать прошедшее время, дёрнуть expiry-job, проверить payment_failed.
- `tests/web/test_phone_login.py` — request-code (со StubSmsGateway) → verify → проверка session-cookie.

**Manual smoke test после деплоя:**
- Лендинг открывается на `avito-pf.com`, клик "Заказать" ведёт на `lk.avito-pf.com/order/new`.
- Полный flow быстрого заказа на тестовом юкассовом ключе.
- Вход по телефону через StubSmsGateway (код из логов).

## 12. Open questions (не блокирующие)

Решаются при имплементации, не блокируют старт.

- **Auto-refund при failed-исполнении:** что делать с деньгами, если `paid → failed`? (Сейчас — ничего, ручной refund админом. Возможно стоит добавить автоматический refund через юкассу/возврат на баланс для авторизованных.)
- **Уведомление гостю об оплате:** SMS юзеру при `paid` с ссылкой на `/order/{id}`? (Сейчас он на странице polling'a, но если бросил вкладку — потеряется.)
- **Старый `pf-bot.com` домен:** что с ним? (Парковать на `lk.avito-pf.com` редиректом, или оставить как третий алиас.)
- **Конкретный SMS-провайдер:** SMSC.ru / Smsaero / другой.
- **TTL "не выбрал способ оплаты" (1 час)** — оставлять или короче (15 мин)?
- **Очистка протухших unpaid из истории юзера:** через N дней `payment_failed` скрывать?

## 13. Out of scope

- Pre-validation ссылок Авито (наблюдаем, добавим позже).
- Multi-payment (часть с баланса + часть юкассой).
- Cart-recovery email/SMS-рассылки для брошенных unpaid.
- Изменения Telegram-бота (aiogram, отдельный контейнер) — он остаётся как есть.
- Полная переработка дизайн-системы фронта — только точечные изменения в названных компонентах.
- CDN/кэширование лендинга — для MVP nginx-static достаточно.
