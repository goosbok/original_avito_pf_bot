# Support topics routing + landing counter bump

**Date:** 2026-05-30
**Branch (worktree):** `claude/eager-cartwright-9e0839`

Три независимых изменения, объединённых в одну фичу:

1. На лендинге заменить `50 000+` → `100 000+` выполненных заказов.
2. Разнести админ-уведомления бота по разным forum-топикам в группе поддержки вместо одного общего чата.
3. Заблокировать обработку ответов ТП так, чтобы реплаи учитывались только в правильном топике и только на сообщения-обращения.

## Motivation

Сейчас в группу поддержки (`SUPPORT_CHAT_ID`) сваливается всё подряд: ответы юзеров, события заказов, ошибки рантайма, регистрации новых юзеров, события по отзывам. В одной ленте админы пропускают важное (вопросы ТП теряются среди ошибок). Telegram forum-режим (топики) решает это без кастомной маршрутизации — нужно лишь указать `message_thread_id` при отправке.

Дополнительно: текущий обработчик ответов ТП в `handlers/support_web.py` срабатывает на любой reply во всём чате, лишь бы regex `Вопрос из веб #(\d+)` нашёл совпадение в replied-text. После раскладки по топикам логично сузить триггер до целевого топика — это устранит ложные срабатывания, если кто-то процитирует старое сообщение или ответит в чужом топике.

## Configuration

Группа `-1003927517516` уже переведена в forum-режим, топики созданы пользователем:

| Переменная | Значение | Назначение |
|---|---|---|
| `SUPPORT_CHAT_ID` | `-1003927517516` | ID forum-группы (есть, не меняется) |
| `SUPPORT_THREAD_QUESTIONS` | `3` | Топик «Вопросы ТП» |
| `SUPPORT_THREAD_ORDERS` | `5` | Топик «Заказы» (включает refill и reviews) |
| `SUPPORT_THREAD_ERRORS` | `7` | Топик «Ошибки» |
| `SUPPORT_THREAD_NEW_USERS` | `9` | Топик «Новые пользователи» |

Все четыре переменные читаются в `data/config.py` как `int(os.getenv(..., "0"))`, аналогично существующему `SUPPORT_CHAT_ID`.

## Categorisation of message sources

| Источник | Категория | Тред |
|---|---|---|
| `web/routers/support.py` `_forward_to_admins` (вопросы юзеров с веба) | `questions` | 3 |
| `web/routers/orders.py` (платные заказы зарегистрированных юзеров) | `orders` | 5 |
| `web/routers/guest_orders.py` (гостевые заказы) | `orders` | 5 |
| `web/routers/refill.py` (пополнения баланса) | `orders` | 5 |
| `handlers/reviews.py` (платные размещения/удаления отзывов) | `orders` | 5 |
| `utils/error_handler.py` `report_handler_error` (runtime errors) | `errors` | 7 |
| `middlewares/exists_user.py` (новый юзер заходит в бот первый раз) | `new_users` | 9 |

Решение положить refill и reviews в `orders` принято осознанно: они тоже представляют собой денежные транзакции пользователя, отдельные топики для каждого подтипа размылили бы внимание админов.

## Startup validation

В `__main__.py` до вызова `executor.start_polling` добавляется функция-валидатор:

- Если `SUPPORT_THREAD_ERRORS == 0` (не задана) → `raise SystemExit("SUPPORT_THREAD_ERRORS must be configured")`. Логика: без этого топика бот не сможет сообщить про другие косяки, поэтому fail-fast лучше тихой потери алертов.
- Если любая из остальных трёх (`QUESTIONS`, `ORDERS`, `NEW_USERS`) не задана → отправляется одноразовое warning-сообщение в `SUPPORT_THREAD_ERRORS` в формате:
  ```
  ⚠️ <b>SUPPORT_THREAD_QUESTIONS не задан</b>
  Сообщения категории questions не будут отправляться в группу.
  ```
  Бот продолжает работать; сообщения соответствующей категории молча дропаются в `send_admins` (см. ниже), чтобы не флудить топик ошибок.

## API: `utils/sender.py`

Сигнатура `send_admins` расширяется:

```python
from typing import Literal, Optional
from aiogram.types import Message

Category = Literal["questions", "orders", "errors", "new_users"]

_CATEGORY_TO_THREAD: dict[Category, str] = {
    "questions": "SUPPORT_THREAD_QUESTIONS",
    "orders":    "SUPPORT_THREAD_ORDERS",
    "errors":    "SUPPORT_THREAD_ERRORS",
    "new_users": "SUPPORT_THREAD_NEW_USERS",
}

async def send_admins(
    msg: str,
    category: Category,
    *,
    parse_mode: Optional[str] = None,
) -> Optional[Message]:
    thread_id = _resolve_thread(category)
    if thread_id == 0:
        return None  # категория не сконфигурирована; warning уже был на старте
    return await bot.send_message(
        chat_id=config.SUPPORT_CHAT_ID,
        text=msg,
        message_thread_id=thread_id,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )
```

`_resolve_thread` читает соответствующий атрибут из `data.config` через `getattr`. Возврат `Message` нужен для `support.py`, который сохраняет `tg_message_id` в БД.

## Refactor: `web/routers/support.py`

`_forward_to_admins` сейчас делает `bot.send_message` напрямую, чтобы получить `sent.message_id` и записать его в `support_messages.tg_message_id`. После рефакторинга:

```python
from utils.sender import send_admins

sent = await send_admins(fwd_text, "questions", parse_mode="HTML")
if sent is not None:
    with db_connect() as con:
        con.execute(
            "UPDATE support_messages SET tg_message_id = ? WHERE id = ?",
            (sent.message_id, msg_id),
        )
        con.commit()
```

Если `sent is None` (топик `questions` не сконфигурирован), `tg_message_id` остаётся `NULL` — обработчик ответа всё равно не сможет сработать без topic-привязки, поэтому это согласованное поведение.

## Refactor: остальные точки вызова

В каждом месте, где сейчас `await send_admins(msg)`, дописывается категория:

- `web/routers/orders.py:139` → `await send_admins(adm_msg, "orders")`
- `web/routers/guest_orders.py:134` → `await send_admins(msg, "orders")`
- `web/routers/refill.py:65` → `await send_admins(msg, "orders")`
- `handlers/reviews.py:148, 209` → `await send_admins(MSG, "orders")`
- `utils/error_handler.py:63` → `await send_admins(alert, "errors")`
- `middlewares/exists_user.py:47` → `await send_admins(msg, "new_users")`

## Refactor: `handlers/support_web.py`

В начало `admin_reply_to_support` добавляется topic-фильтр **до** regex-сопоставления:

```python
@dp.message_handler(...)
async def admin_reply_to_support(message: Message) -> None:
    import data.config as _cfg
    if message.chat.id != _cfg.SUPPORT_CHAT_ID:
        return
    if message.message_thread_id != _cfg.SUPPORT_THREAD_QUESTIONS:
        return  # реплай в другом топике (или General) — игнорируем
    # ... admin allow-list + regex check остаются без изменений
```

Этим обеспечиваются оба требования из ТЗ:
- «ответили в другом топике → бот молчит» — `message_thread_id != SUPPORT_THREAD_QUESTIONS` блокирует обработку.
- «ответили на левое сообщение в правильном топике → бот молчит» — старая проверка `_SUPPORT_PATTERN.search(replied_text)` возвращает `None` и хендлер выходит.

Edge case: если `SUPPORT_THREAD_QUESTIONS == 0` (не сконфигурирован), сравнение `message.message_thread_id != 0` всегда True (для thread-сообщений) или False (для General), что эффективно отключает обработчик. Это безопасный default.

## Landing change

В `web/static/components/Landing.jsx:132`:

```diff
- { num: '50 000+', label: 'Выполненных заказов', color: '#0088cc' },
+ { num: '100 000+', label: 'Выполненных заказов', color: '#0088cc' },
```

Другие места с этим числом отсутствуют (grep по `50 000`, `50000`, `50_000` в `web/static` пуст).

## Testing

### Existing tests to update

- `tests/unit/test_sender.py` — все вызовы `send_admins("hello group")` → `send_admins("hello group", "errors")` (или любая валидная категория). Мокается `data.config.SUPPORT_THREAD_ERRORS`.
- `tests/unit/test_support_reply.py` — добавить `monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)` и поле `message.message_thread_id = 3` в фикстуры, чтобы тесты не сломались.
- `tests/unit/test_payment_probe.py`, `tests/unit/test_error_handler.py` — патчи `send_admins` не ломаются (сигнатура совместима через `**kwargs` в mock), но если есть assertions на аргументы — поправить.
- `tests/conftest.py` — добавить дефолты `SUPPORT_THREAD_*` = 0 в стабе конфига.

### New tests

1. **`test_sender.py::test_send_admins_routes_to_category_thread`** — для каждой категории проверить, что `bot.send_message` получает корректный `message_thread_id`.
2. **`test_sender.py::test_send_admins_drops_when_thread_unset`** — категория с `thread_id == 0` → `send_admins` возвращает `None`, `bot.send_message` не вызывается.
3. **`test_support_reply.py::test_ignores_reply_in_wrong_topic`** — `message.message_thread_id = 99` (не равен `SUPPORT_THREAD_QUESTIONS`) → обработчик return-ит без вызова `create_admin_reply`.
4. **`test_support_reply.py::test_ignores_reply_to_non_support_message`** — `message.message_thread_id = 3`, но replied_text без `Вопрос из веб #N` → return.
5. **`test_startup_validation.py`** (новый файл) — два кейса: `SUPPORT_THREAD_ERRORS == 0` → `SystemExit`; одна из остальных переменных == 0 → стартует, но шлёт warning в errors-топик.

Все тесты запускаются через `docker exec` согласно ранее зафиксированному правилу (memory: `feedback_docker_tests.md`).

## Deployment

После мержа в `dev`:

1. На проде в `.env` добавить четыре переменные (`SUPPORT_THREAD_QUESTIONS=3`, `SUPPORT_THREAD_ORDERS=5`, `SUPPORT_THREAD_ERRORS=7`, `SUPPORT_THREAD_NEW_USERS=9`).
2. SSH `root@185.106.93.71` → `git pull dev` → `docker compose build api bot` → `docker compose up -d` (см. memory: `deploy.md`).
3. Убедиться, что бот зашёл в группу `-1003927517516` как админ с правом писать во все топики (по умолчанию админ Telegram-группы это право имеет).
4. Smoke-check: триггернуть по одному событию каждой категории (новый юзер, тестовый refill, искусственная ошибка через `/error_test` если есть, вопрос с веба) — увидеть, что каждое падает в свой топик.

## Out of scope

- Миграция старых сообщений в group-чате в топики — невозможно через Bot API, остаются как есть.
- UI для переключения категорий из админки — нет необходимости, env-переменные стабильны.
- Алерты на «топик удалён» / «бот выкинут из группы» — handled общим error-handler-ом aiogram.
- Перевод на aiogram 3.x — отдельная история, не блокирует.
