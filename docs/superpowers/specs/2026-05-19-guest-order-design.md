# Гостевой заказ Авито ПФ (без регистрации)

**Дата:** 2026-05-19  
**Статус:** Approved

## Обзор

Добавить возможность сделать заказ Авито ПФ без создания аккаунта. На лендинге появляется кнопка «Заказать без регистрации», ведущая на страницу заказа с полем телефона и прямой оплатой через ЮКассу. Гостевые заказы хранятся отдельно от пользовательских и видны в admin-панели с фильтром.

## Пользовательский сценарий

1. Посетитель открывает лендинг
2. Видит кнопку «⚡ Заказать без регистрации» в Hero рядом с кнопками входа
3. Если ЮКасса отключена: кнопка серая, при наведении — тултип «Временно недоступно»
4. Кликает кнопку → переходит на страницу гостевого заказа (`guest-order-pf`)
5. Заполняет стандартные параметры (ссылки, просмотры, дни, контакты) + поле телефона
6. Нажимает «Перейти к оплате» → редирект на ЮКассу
7. После оплаты ЮКасса возвращает на `/?guest_order_id=X&payment_id=Y`
8. SPA обнаруживает параметры, поллит статус заказа, показывает страницу успеха
9. Страница успеха: номер заказа + инструкция «назови телефон в ТП»

## Архитектура

### База данных

Новая таблица `guest_orders` (SQLite миграция):

```sql
CREATE TABLE guest_orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    phone         TEXT NOT NULL,
    links         TEXT NOT NULL,     -- JSON-массив URL
    days          INTEGER NOT NULL,
    fix_count     INTEGER NOT NULL,
    contacts      INTEGER NOT NULL DEFAULT 0,
    price         INTEGER NOT NULL,  -- итоговая сумма в рублях
    price_per_unit INTEGER NOT NULL,
    payment_id    TEXT,              -- YooKassa payment ID
    status        TEXT NOT NULL DEFAULT 'pending_payment',
    -- статусы: pending_payment | paid | failed
    created_at    TEXT NOT NULL      -- ISO-8601
);
```

Таблица не связана с `users` — намеренная изоляция, без риска регрессий в существующем слое авторизации.

### Backend API (все эндпоинты публичные, без `require_user`)

**`GET /api/guest-orders/payment-available`**  
Возвращает `{"available": bool}`. Проверяет `is_yookassa_enabled()`.  
Вызывается при монтировании лендинга — определяет состояние кнопки.

**`POST /api/guest-orders/pf`**  
Body: `{links, days, fix_count, contacts, phone}`  
Действия:
1. Валидирует тело (те же правила что у `PFOrderRequest` + телефон непустой)
2. Получает `price_per_unit` через `orders_svc.get_pf_price_per_unit()`
3. Вычисляет `price = fix_count * days * len(links) * price_per_unit`
4. Создаёт запись в `guest_orders` со статусом `pending_payment`
5. Создаёт платёж YooKassa с `return_url = f"{SITE_URL}/?guest_order_id={id}&payment_id={pid}"` — `SITE_URL` берётся из `data/config.py` (env var `SITE_URL`)
6. Возвращает `{guest_order_id, payment_url}`

**`GET /api/guest-orders/{guest_order_id}/status`**  
Действия:
1. Загружает запись из `guest_orders`
2. Если уже `paid` — сразу возвращает `{status: "paid", order_id}`
3. Если `payment_id` есть — проверяет YooKassa:
   - `succeeded` → обновляет статус на `paid`, уведомляет админов в Telegram, возвращает `{status: "paid", order_id}`
   - `canceled`/`expired` → статус `failed`, возвращает `{status: "failed"}`
   - иначе → `{status: "pending"}`
4. Идемпотентен: повторный вызов при уже `paid` не создаёт дублей

Telegram-уведомление при `paid` (аналогично `_notify_new_order`):
```
🌐 Новый гостевой заказ #42
💰 Сумма: 1 260 ₽
📞 Телефон: +7 (999) 123-45-67
📋 Авито ПФ · 30 просм./д · 7 дн.
🔗 1 объявление
```

### Frontend

#### Landing.jsx

- При монтировании: `GET /api/guest-orders/payment-available` → сохраняет в стейт `paymentAvailable`
- Новая кнопка в Hero:
  ```jsx
  <button
    className="btn btn--outline btn--lg"
    onClick={() => paymentAvailable && onNavigate('guest-order-pf')}
    disabled={!paymentAvailable}
    title={!paymentAvailable ? 'Временно недоступно' : undefined}
  >
    ⚡ Заказать без регистрации
  </button>
  ```
- CSS `disabled` даёт серый цвет; `title` обеспечивает нативный тултип при наведении

#### GuestOrderForm.jsx (новый компонент)

Базируется на `OrderFormPage`, изменения:
- При монтировании проверяет `GET /api/guest-orders/payment-available`; если `available: false` — кнопка «Перейти к оплате» задизейблена, над ней hint «Онлайн-оплата временно недоступна»
- Убрать логику баланса (`balance`, `totalPrice > balance`)
- Добавить поле телефона (строковое, обязательное, с хинтом)
- Кнопка «Перейти к оплате» вместо «Разместить заказ»
- `handleSubmit`:
  1. Валидирует наличие ссылок и телефона
  2. `POST /api/guest-orders/pf` → получает `{guest_order_id, payment_url}`
  3. `window.location.href = payment_url` (редирект на ЮКассу)
- Бейдж «Без регистрации» рядом с заголовком
- Кнопка «← Назад на главную» ведёт на `landing`

#### app.jsx

При монтировании проверяет URL-параметры:
```js
const _guestOrderId = params.get('guest_order_id');
const _guestPaymentId = params.get('payment_id');
const _isGuestReturn = !!(guestOrderId && guestPaymentId);
```
Если `_isGuestReturn` → начальный роут `'guest-order-success'`.

Добавить роут в `renderScreen`:
```jsx
case 'guest-order-pf':      return <GuestOrderForm onNavigate={handleNavigate} />;
case 'guest-order-success':  return <GuestOrderSuccess guestOrderId={...} paymentId={...} onNavigate={handleNavigate} />;
```

#### GuestOrderSuccess.jsx (новый компонент)

При монтировании поллит `GET /api/guest-orders/{id}/status` каждые 2 секунды, максимум 30 попыток.

Состояния:
- **polling** — «Проверяем оплату...» + спиннер
- **paid** — номер заказа + 3-шаговая инструкция + кнопка «Написать в ТП» (ссылка на Telegram)
- **failed** — «Оплата не прошла» + кнопки «Попробовать снова» (→ `guest-order-pf`) и «Написать в ТП»
- **timeout** — то же что `failed`

Инструкция на экране успеха:
1. Напишите в **@avito_pf_otzizi**
2. Назовите ваш номер телефона (и номер заказа **#1042** при желании)
3. Мы найдём заказ и ответим в течение рабочего дня

### Admin

**`GET /api/admin/orders`** — добавить query-параметр `?is_guest=true|false` (по умолчанию — все).

Реализация: при `is_guest=false` запрос только к `orders`, при `is_guest=true` только к `guest_orders`, при отсутствии параметра — UNION обеих таблиц, сортировка `ORDER BY created_at DESC`, затем пагинация. `AdminOrderItem` расширяется полями `is_guest: bool` и `guest_phone: str | None`.

**AdminOrders.jsx** — добавить фильтр-чип «Обычные / Гостевые / Все» над таблицей. В строке гостевого заказа вместо имени пользователя отображается `📞 +7 (999) 123-45-67`.

## Схемы Pydantic (новые)

```python
class GuestPFOrderRequest(BaseModel):
    links: list[str] = Field(min_length=1)
    days: int = Field(gt=0)
    fix_count: int = Field(ge=5)
    contacts: bool
    phone: str = Field(min_length=5, max_length=32)

    @field_validator("links")
    @classmethod
    def links_must_be_avito(cls, v): ...  # та же валидация

class GuestPFOrderResponse(BaseModel):
    guest_order_id: int
    payment_url: str

class GuestOrderStatusResponse(BaseModel):
    status: str   # pending | paid | failed
    order_id: int | None = None

class PaymentAvailableResponse(BaseModel):
    available: bool
```

## Обработка ошибок

| Ситуация | Поведение |
|---|---|
| ЮКасса недоступна при POST | HTTP 503, фронт показывает alert с просьбой обратиться в ТП |
| YooKassa таймаут при поллинге | После 30 попыток → экран `timeout` (как `failed`) |
| Прямой URL `/guest-order-pf` когда касса выключена | Форма рендерится, но кнопка задизейблена (проверка `payment-available` на монтировании) |
| Дублирующий вызов `/status` при уже `paid` | Идемпотентный ответ, без повторного зачисления |

## Тесты

- `test_routers_guest_orders.py`: POST создаёт запись + payment_url; GET status переходит pending→paid; GET status идемпотентен; невалидные ссылки → 422; пустой телефон → 422
- `test_payment_available.py`: возвращает `false` когда yookassa отключена
- Существующие тесты `test_routers_orders.py` не затрагиваются (изолированная таблица)
