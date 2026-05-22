# Order Status Notifications — Design

**Date:** 2026-05-22
**Status:** Draft

## 1. Цель

Когда меняется статус заказа, пользователь должен узнать об этом по двум каналам:

1. **Telegram-пуш** — сообщение от бота со ссылкой на главное меню.
2. **Колокольчик в ЛК** — бейдж с числом непрочитанных и лента уведомлений.

Источники смены статуса покрываем оба: веб-админка (`POST /api/admin/orders/{id}/status`) и Telegram-админка (`handlers/admin_orders.py`).

## 2. Скоуп

**Уведомляем при переходе в статусы:**
- `Posted` — заказ размещён
- `Completed` — заказ выполнен
- `Cancelled` — заказ отменён

Остальные (`Pending`, legacy `In progress`) — молчим.

**Условия:**
- Не уведомляем, если `old_status == new_status` (защита от двойных кликов).
- Гостевые заказы вне скоупа (нет `user_id`, нет ЛК).
- Доставка best-effort: падение Telegram не блокирует смену статуса и не теряет запись в ленте ЛК.

## 3. Архитектура

Доменное событие материализуется в БД как запись в `notifications`. Из одной записи доставляем в два канала.

**Новые модули:**
- `services/notifications.py` — таблица + публичные функции (нотификация, чтение ленты, mark-as-read).
- `web/routers/notifications.py` — HTTP API для веб-фронта.
- `web/static/components/NotificationsBell.jsx` — колокольчик с бейджем и дропдауном.

**Изменения в существующих файлах:**
- `web/routers/admin_orders.py:change_status` — после `UPDATE` зовёт `asyncio.create_task(notify_order_status_changed(...))`.
- `handlers/admin_orders.py:order_finish` — заменяет ad-hoc `bot.send_message("✅ Ваш заказ №... выполнен.")` на `await notify_order_status_changed(...)`.
- `web/static/components/AppHeader.jsx` — монтирует `<NotificationsBell />` в `header__actions` для авторизованного юзера в non-admin режиме.
- `web/main.py` — регистрация роутера уведомлений.
- `web/static/platform.css` — стили `.bell`, `.bell__btn`, `.bell__badge`, `.bell__panel`, `.bell__item`, `.bell__item--unread`, `.bell__empty`.
- `utils/sqlite3.py` (блок `CREATE TABLE ...` начиная с ~строки 824) — добавить `CREATE TABLE IF NOT EXISTS notifications` и два индекса.

**Что НЕ меняем:**
- `utils/sqlite3.edit_order` остаётся «тупым» мутатором.
- Гостевые заказы.
- Существующие тексты других уведомлений (поддержка, VIP-статус).

## 4. Схема БД

Новая таблица `notifications`:

```sql
CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    kind        TEXT    NOT NULL,
    order_id    INTEGER,
    new_status  TEXT,
    text        TEXT    NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at     TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
    ON notifications(user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_notifications_user_created
    ON notifications(user_id, created_at DESC);
```

**Решения:**
- `text` хранится готовый: канал TG и лента ЛК должны показывать одно и то же содержимое; иначе пришлось бы реконструировать на каждой выдаче.
- `read_at TIMESTAMP NULL` вместо boolean — позволяет различать «непрочитанное» (`IS NULL`) и фиксирует время прочтения.
- `kind` сейчас всегда `'order_status'`, но колонка оставляет дверь для будущих типов без миграции структуры.
- `order_id` nullable — задел на будущие kind'ы.
- Индексы покрывают два горячих запроса: подсчёт непрочитанных и лента в обратном хронологическом порядке.
- Чистка старых записей не делается сейчас (YAGNI).

## 5. Сервис уведомлений (`services/notifications.py`)

### Публичный API

```python
async def notify_order_status_changed(
    order_id: int,
    user_id: int,
    old_status: str,
    new_status: str,
) -> None

def list_notifications(user_id: int, limit: int = 50) -> list[dict]
def unread_count(user_id: int) -> int
def mark_all_read(user_id: int) -> int  # rowcount
```

### Поведение `notify_order_status_changed`

```python
_TEMPLATES = {
    "Posted":    "📌 Заказ №{order_id} размещён.",
    "Completed": "✅ Заказ №{order_id} выполнен.",
    "Cancelled": "❌ Заказ №{order_id} отменён.",
}

def _build_text(order_id: int, new_status: str) -> str | None:
    tpl = _TEMPLATES.get(new_status)
    return tpl.format(order_id=order_id) if tpl else None


async def notify_order_status_changed(order_id, user_id, old_status, new_status):
    if old_status == new_status:
        return
    text = _build_text(order_id, new_status)
    if text is None:
        return  # статус вне whitelist'а

    # 1. durable: insert в БД (для ленты ЛК)
    with connect() as con:
        con.execute(
            "INSERT INTO notifications(user_id, kind, order_id, new_status, text) "
            "VALUES (?, 'order_status', ?, ?, ?)",
            (user_id, order_id, new_status, text),
        )
        con.commit()

    # 2. best-effort: TG push
    try:
        from utils.sqlite3 import get_tg_id_for_user
        from data.loader import bot
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        tg_id = get_tg_id_for_user(user_id)
        if not tg_id:
            return
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(text="🏠 Главное меню", callback_data="to_main_menu"))
        await bot.send_message(chat_id=tg_id, text=text, reply_markup=kb)
    except Exception:
        logger.exception("TG notify failed for user_id=%s order=%s", user_id, order_id)
```

**Решения:**
- БД-вставка идёт **первой**: если TG упадёт, в ленте ЛК запись уже есть.
- `callback_data="to_main_menu"` переиспользует существующий хендлер в `handlers/commands.py:144` — дополнительной правки в боте не нужно.
- Импорты внутри функции (паттерн как в `web/routers/admin_support._forward_reply_to_user`) — избегаем циклов при загрузке модулей.
- `_build_text` приватный: знание о whitelist'е статусов и шаблонах в одном месте.

## 6. HTTP API

Роутер `web/routers/notifications.py`, авторизация — `Depends(require_user)` из `web.deps` (возвращает `user_id: int`), как в `web/routers/orders.py`.

### `GET /api/notifications`

Ответ:
```json
{
  "items": [
    {
      "id": 42,
      "kind": "order_status",
      "order_id": 5,
      "new_status": "Completed",
      "text": "✅ Заказ №5 выполнен.",
      "created_at": "2026-05-22T15:19:18",
      "read_at": null
    }
  ],
  "unread_count": 3
}
```

- `ORDER BY id DESC LIMIT 50`. Пагинации нет (YAGNI).
- `unread_count` включён в ответ, чтобы UI обновлял бейдж одним запросом.

### `POST /api/notifications/mark-all-read`

Ответ: `{ "marked": N }`. Идемпотентен: повторный вызов вернёт `marked: 0`. Действует на весь скоуп текущего юзера.

### Сознательно нет

- Отдельной ручки `GET /unread-count` — `list_notifications` уже её содержит.
- `mark-one-read` — UX-решение: отметка пачкой при открытии панели.
- `POST /notifications` — записи создаются только сервисом из доменных событий.
- WebSocket / SSE — `Cabinet` уже опросный, используем поллинг.

## 7. Callsite-ы

### Веб-админка (`web/routers/admin_orders.py:change_status`)

```python
with connect() as con:
    row = con.execute(
        "SELECT increment, user_id, status FROM orders WHERE increment = ?",
        (order_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "order not found")
    old_status = str(row["status"] or "")
    user_id = int(row["user_id"])
    if old_status != body.status:
        con.execute(
            "UPDATE orders SET status = ? WHERE increment = ?",
            (body.status, order_id),
        )
        con.commit()

if old_status != body.status:
    asyncio.create_task(
        notify_order_status_changed(order_id, user_id, old_status, body.status)
    )
return {"order_id": order_id, "status": body.status}
```

Чтение `status` и `user_id` идёт в той же сессии, что и `UPDATE` — race-окна нет. Отправка нотификации после `commit`, чтобы не уведомлять об изменении, которое откатилось бы. `asyncio.create_task` — fire-and-forget.

### Telegram-админка (`handlers/admin_orders.py:order_finish`, ~строка 264)

```python
order1 = get_order(order)
if not order1:
    ...
    return
old_status = str(order1.get('status') or '')
edit_order(status="Completed", order=order)
await notify_order_status_changed(
    order_id=int(order),
    user_id=int(order1['user_id']),
    old_status=old_status,
    new_status="Completed",
)
await bot.send_message(chat_id=message.from_user.id, text="✅ Успешно")
```

Удаляется существующий ручной `bot.send_message(chat_id=tg_id, text=f"✅ Ваш заказ №{order} выполнен.")` — теперь это уходит через общий сервис. В этом контексте `await`, а не `create_task`: уже внутри aiogram-хендлера; сервис проглатывает свои исключения.

## 8. UI колокольчика

### Размещение

`web/static/components/AppHeader.jsx`, в блоке `header__actions` (между балансом и user-dropdown'ом). Показываем только когда `user && !adminMode`.

### Компонент `NotificationsBell.jsx`

```jsx
function NotificationsBell({ pollMs = 30000 }) {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const fetchNow = async () => {
      try {
        const data = await apiGet('/api/notifications');
        if (cancelled) return;
        setItems(data.items);
        setUnread(data.unread_count);
      } catch {}
    };
    fetchNow();
    const t = setInterval(fetchNow, pollMs);
    return () => { cancelled = true; clearInterval(t); };
  }, [pollMs]);

  const onToggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && unread > 0) {
      try {
        await apiPost('/api/notifications/mark-all-read');
        setUnread(0);
        setItems(items.map(i => i.read_at
          ? i
          : { ...i, read_at: new Date().toISOString() }
        ));
      } catch {}
    }
  };

  return (
    <div className="bell">
      <button className="bell__btn" onClick={onToggle} aria-label="Уведомления">
        🔔
        {unread > 0 && (
          <span className="bell__badge">{unread > 99 ? '99+' : unread}</span>
        )}
      </button>
      {open && (
        <div className="bell__panel">
          {items.length === 0 ? (
            <div className="bell__empty">Уведомлений пока нет</div>
          ) : items.map(n => (
            <div
              key={n.id}
              className={`bell__item ${n.read_at ? '' : 'bell__item--unread'}`}
            >
              <div className="bell__item-text">{n.text}</div>
              <div className="bell__item-time">{formatTime(n.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

### Поведение

- Поллинг каждые 30s — синхронизируется с ритмом `Cabinet` (баланс/заказы там тоже опросные).
- Открытие панели → POST `mark-all-read`, бейдж в 0, локальное оптимистичное обновление `items`.
- Закрытие — клик мимо панели (через backdrop, как у user-dropdown в шапке).
- Пустое состояние: «Уведомлений пока нет».

### Стили (`platform.css`)

- `.bell` — relative-обёртка.
- `.bell__btn` — круглая кнопка в стиле остальных в `header__actions`.
- `.bell__badge` — красный кружок в правом верхнем углу иконки.
- `.bell__panel` — абсолютный дропдаун под иконкой, фон `var(--surface)`, тень, скролл при длинной ленте.
- `.bell__item--unread` — лёгкий акцент (левая полоска `var(--primary)`).
- На мобилке (`mobile-only`) панель занимает ~90vw, текст не обрезается.

### Сознательно нет

- Toast-всплывашек на новые уведомления — достаточно бейджа.
- Группировки по дням, фильтров — YAGNI.
- Звукового сигнала.

## 9. Обработка ошибок

| Сценарий | Поведение |
|---|---|
| `old_status == new_status` | Раннее возвращение, ничего не пишется |
| Статус не в whitelist | Раннее возвращение |
| INSERT в `notifications` упал | Исключение всплывает; в админ-роуте → 500. `UPDATE` уже закоммичен — это сигнал кривой миграции. |
| `get_tg_id_for_user` вернул None | INSERT прошёл, push пропущен, INFO-лог |
| `bot.send_message` упал (`BotBlocked`, `ChatNotFound`, 5xx) | INSERT прошёл, `logger.exception`, без re-raise |
| `mark-all-read` без непрочитанных | 200, `{ marked: 0 }` |
| `GET /api/notifications` без авторизации | 401 (стандартный `Depends`) |

## 10. Тестирование

### Юнит-тесты (`tests/unit/test_notifications.py`)

- `_build_text`: возвращает строку для Posted/Completed/Cancelled, `None` для Pending и неизвестных.
- `list_notifications` / `unread_count` / `mark_all_read`: in-memory SQLite, фильтр по `user_id`, упорядоченность `ORDER BY id DESC`, идемпотентность `mark_all_read`.
- `notify_order_status_changed`:
  - no-op при `old == new` (нет вставки в БД, нет вызова бота, бот замокан);
  - whitelist: для `Pending` нет вставки;
  - happy path: вставка в БД + `bot.send_message` вызван с inline-кнопкой;
  - TG-провал (мок райзит исключение): запись в БД остаётся, исключение проглочено, лог зафиксирован;
  - нет `tg_id`: запись в БД остаётся, `bot.send_message` НЕ вызван.

### Интеграционные тесты (`tests/web/`)

- `test_admin_orders.py` дополняем:
  - `POST /api/admin/orders/{id}/status` со сменой статуса → запись в `notifications`;
  - повторный вызов с тем же статусом → новой записи нет.
- `test_notifications.py` (новый):
  - `GET /api/notifications` — только записи текущего юзера;
  - `POST /mark-all-read` — обновляет `read_at`, возвращает `marked` count;
  - 401 без авторизации.

Запуск — через `docker exec` (репо-конвенция).

### Ручные тесты

Предусловия: dev-Docker поднят, БД мигрирована, есть заказ юзера `@yamagruh` (`tg_id=7050873595`). Два окна: (а) Telegram + ЛК под `@yamagruh`; (б) админка под admin.

**TC-1. Posted → пуш в TG и запись в ленте**
1. Меняем статус заказа #N в админке `Pending` → `Posted`.
2. В TG приходит `📌 Заказ №N размещён.` + кнопка `🏠 Главное меню`.
3. Кнопка ведёт в главное меню бота.
4. В ЛК через ≤30s бейдж колокольчика `1`.
5. Открываем панель — запись с подсветкой непрочитанного, бейдж исчезает.
6. Перезагружаем ЛК → бейджа нет, запись без подсветки.

**TC-2. Completed → второй пуш, инкремент бейджа**
1. Тот же заказ `Posted` → `Completed`.
2. ≤30s — бейдж `1`, в TG `✅ Заказ №N выполнен.`
3. В панели две записи, новая сверху.

**TC-3. Идемпотентность**
1. Снова выбрать `Completed` для уже-Completed заказа.
2. 200, никаких новых сообщений, бейдж и `SELECT COUNT(*) FROM notifications WHERE order_id = N` не меняются.

**TC-4. Cancelled**
1. Другой заказ → `Cancelled`.
2. В TG: `❌ Заказ №N отменён.` + кнопка `🏠 Главное меню`.
3. В ленте — новая запись.

**TC-5. Pending — молчим**
1. Любой заказ → `Pending`.
2. Ни в TG, ни в `notifications` — ничего. Бейдж не меняется.

**TC-6. TG упал, ЛК работает**
1. `@yamagruh` блокирует бота (`/stop`).
2. В админке меняем её заказ → `Posted`.
3. В TG ничего (бот заблокирован).
4. В ЛК ≤30s — бейдж и запись появляются.
5. Сервер пишет `logger.exception` про TG.

**TC-7. Канал смены статуса из TG-админки**
1. Через `/admin → готовоебать → ввести ID заказа` ставим `Completed`.
2. Юзер получает стандартное сообщение (с кнопкой), а не старый текст `«Ваш заказ № выполнен.»`.
3. В ЛК — запись в ленте.

**TC-8. Изоляция ленты по юзерам**
1. Логин в ЛК под другим юзером (например, `@u1tra_zalupa`).
2. Колокольчик пуст или со своими записями, ничего чужого.
3. `GET /api/notifications` в DevTools — только записи текущего юзера.

**TC-9. Адаптив**
1. На мобиле (375px) колокольчик в шапке, бейдж читаемый.
2. Открытая панель не вылезает за экран, текст не обрезается.

**Авто-сценарий через Telethon** (опционально): TC-1/TC-2 можно автоматизировать через `.test_session.session` (см. memory `project_test_data.md`).

## 11. Не входит в скоуп

- Гостевые заказы (`guest_orders`) — нет `user_id`/ЛК.
- Outbox-таблица + воркер с ретраями (отдельный спек, если потребуется).
- Email/SMS-каналы.
- WebSocket / SSE-доставка в ЛК.
- Группировка, фильтры, пагинация ленты.
- Тосты на новые уведомления.
- Чистка старых записей.
