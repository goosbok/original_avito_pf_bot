# Funnel Analytics — дизайн

**Дата:** 2026-05-18
**Автор:** Demyan Belikov + Claude

## Цель

Понимать, на каком шаге пайплайна заказа пользователи бросают процесс. Пример: «сколько юзеров увидели карточку ПФ, но не дошли до выбора срока». Решение должно быть универсальным — расширяться на будущие сервисы (отзывы, SEO и т.п.) без изменения схемы БД и без переработки архитектуры.

## Решение: event log + реестр шагов

Каждое продвижение пользователя по воронке записывается отдельной строкой в таблицу `funnel_events`. Каждый сервис декларирует свой упорядоченный список шагов в реестре `FUNNEL_STEPS`. Агрегация — `COUNT(DISTINCT user_id)` по шагу + фильтр по дате.

Альтернативы (хранение только `max_step` per user; трекинг через FSM middleware) отвергнуты — первая теряет фильтрацию по дате и timeline, вторая хрупка и завязана на технические имена FSM-стейтов.

## Архитектура

### Новый модуль `services/funnel.py`

```python
FUNNEL_STEPS: dict[str, list[str]] = {
    "pf_avito": [
        "view_tariff",
        "select_period",
        "select_count",
        "links_valid",
        "contact_chosen",
        "order_confirmed",
    ],
    # будущие сервисы добавляются сюда же
}

def track_step(user_id: int, service: str, step: str) -> None:
    """Записать событие воронки. Невалидный (service, step) → ValueError."""

def get_funnel_stats(
    service: str,
    *,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> list[dict]:
    """
    Вернуть [{"step": str, "users": int, "drop_off_pct": float | None}, ...]
    в порядке FUNNEL_STEPS[service]. Шаги без событий имеют users=0.
    drop_off_pct для первого шага = None, для остальных округляется до 0.1.
    Если prev.users == 0 → drop_off_pct = None.
    """

def render_chart(
    service: str,
    *,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    title: str,
) -> io.BytesIO:
    """Сгенерировать PNG bar chart воронки. Возвращает BytesIO в начале (seek(0))."""
```

### Новая таблица `funnel_events`

Добавляется в список таблиц `utils/sqlite3.py` (рядом со строками [903-983](../../../utils/sqlite3.py)):

```sql
CREATE TABLE IF NOT EXISTS funnel_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    service   TEXT NOT NULL,
    step      TEXT NOT NULL,
    ts        TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_funnel_service_ts
    ON funnel_events(service, ts);
CREATE INDEX IF NOT EXISTS idx_funnel_service_step_user
    ON funnel_events(service, step, user_id);
```

Создаётся при старте бота через существующий `create_db()`. На проде — `python -c "from utils.sqlite3 import create_db; create_db()"`.

### Идемпотентность

`track_step()` НЕ дедуплицирует — каждый вызов = новая строка. Если юзер возвращается назад и снова доходит до шага, в БД будет два события. Для `COUNT(DISTINCT user_id)` это не имеет значения.

### Таймзоны и `user_id`

- `ts` пишется в UTC (`datetime.now(timezone.utc).isoformat()`). Все границы периодов (today, 7d, 30d) тоже считаются в UTC — как уже принято в [admin_stats.py:18](../../../web/routers/admin_stats.py).
- `user_id`, передаваемый в `track_step()`, — внутренний PK из `users.id` (то, что middleware инжектит в `data["user_id"]`, см. [middlewares/exists_user.py:42](../../../middlewares/exists_user.py)). НЕ Telegram ID.

## Точки инструментации для ПФ

В `handlers/pf_order.py`:

| # | Шаг | Файл:строка | Триггер |
|---|---|---|---|
| 1 | `view_tariff` | `tarif()` после показа карточки ([pf_order.py:38](../../../handlers/pf_order.py)) | callback `tarifs:pf` |
| 2 | `select_period` | `pf()` ветка `call_data[1].isdigit()` ([pf_order.py:75](../../../handlers/pf_order.py)) и `enter_period_func` при валидном вводе ([pf_order.py:115](../../../handlers/pf_order.py)) | пользователь выбрал/ввёл срок |
| 3 | `select_count` | `pf()` else-ветка после установки `total_price` ([pf_order.py:92](../../../handlers/pf_order.py)) и `enter_pf_func` при валидном вводе ([pf_order.py:130](../../../handlers/pf_order.py)) | пользователь выбрал/ввёл количество |
| 4 | `links_valid` | `place_order()` после `if links:` ([pf_order.py:187](../../../handlers/pf_order.py)) | ссылки приняты, перед промптом контактов |
| 5 | `contact_chosen` | `order_contact_set()` после `data['contact'] = answer` ([pf_order.py:209](../../../handlers/pf_order.py)) | пользователь ответил yes/no |
| 6 | `order_confirmed` | `confirm_order()` сразу при входе, до проверки баланса ([pf_order.py:223](../../../handlers/pf_order.py)) | пользователь нажал «подтвердить» |

Невалидные пути (битый ввод, парсинг ссылок не нашёл avito.ru и т.п.) не трекаются.

**Сигнатуры хендлеров.** Большинство PF-хендлеров (`tarif`, `pf`, `enter_period_func`, `enter_pf_func`, `place_order`, `order_contact_set`) сейчас НЕ принимают `user_id: int`. Для трекинга в каждый из них нужно добавить параметр `user_id: int` — middleware его автоматически инжектит. `confirm_order` уже его принимает.

### Стандартизация: общая функция `tarif()`

`tarif()` ([pf_order.py:38](../../../handlers/pf_order.py)) — общая точка входа для всех тарифов (сейчас диспатчит на `tarifs:pf`). Здесь читаем `service = call.data.split(":")[1]` и трекаем `view_tariff` для нужного сервиса. Это и есть стандартизация: каждый новый тариф автоматически попадает в воронку, если у него есть запись в `FUNNEL_STEPS`.

## Админка в боте

### Точка входа

Новая кнопка `📊 Воронка` в `admin()` ([inline_keyboards.py:446](../../../keyboards/inline_keyboards.py)). Callback: `funnel_menu`.

### Поток UI

```
[admin panel] → 📊 Воронка
              ↓
   ┌─ Выбор сервиса ─────────────┐
   │  🚀 Накрутка ПФ Авито       │  callback: funnel:pf_avito
   │  ⬅️ Назад                   │
   └─────────────────────────────┘
              ↓
   ┌─ Выбор периода ─────────────┐
   │  Сегодня      7 дней        │  callback: funnel:pf_avito:today
   │  30 дней      Всё время     │           funnel:pf_avito:7d / 30d / all
   │  ⬅️ Назад                   │
   └─────────────────────────────┘
              ↓
   [send_photo: PNG + caption]
```

Список сервисов в клавиатуре строится из ключей `FUNNEL_STEPS` + статической карты `service → emoji + название`.

### Маппинг периодов

| Кнопка     | Callback suffix | from_dt          | to_dt |
|------------|-----------------|------------------|-------|
| Сегодня    | `today`         | `start_of_today` | `now` |
| 7 дней     | `7d`            | `now - 7d`       | `now` |
| 30 дней    | `30d`           | `now - 30d`      | `now` |
| Всё время  | `all`           | `None`           | `None` |

### Сообщение

**Фото:** горизонтальный bar chart matplotlib. Ось Y — шаги в порядке `FUNNEL_STEPS`. Ось X — кол-во уникальных юзеров. На каждом баре подпись `N (-XX.X%)`. Заголовок: `Воронка «{service_name}» за {period_label}`. Реализация по паттерну [admin_orders.py:830-838](../../../handlers/admin_orders.py) (figure → savefig в BytesIO → `plt.close()`).

**Caption:**

```
🚀 Накрутка ПФ Авито · 7 дней (2026-05-11 — 2026-05-18)

view_tariff      1240
select_period     980  (-21.0%)
select_count      870  (-11.2%)
links_valid       520  (-40.2%)
contact_chosen    480  (-7.7%)
order_confirmed   410  (-14.6%)

Конверсия в заказ: 33.1%
```

«Конверсия в заказ» = `users(last_step) / users(first_step) * 100`. Если первый шаг = 0 → строка не печатается.

### Авторизация

`if str(call.from_user.id) in get_admins():` — как в [admin_base.py:60](../../../handlers/admin_base.py). Для не-админов callback игнорируется молча.

### Размещение кода

- Хендлеры — новый файл `handlers/admin_funnel.py`, импортируется из `handlers/main_start.py` (или где импортируются остальные admin-хендлеры).
- Клавиатуры `funnel_service_kb()`, `funnel_period_kb(service)` — в `keyboards/inline_keyboards.py`.

## Тесты

### `tests/unit/test_funnel.py`

- `track_step()` пишет строку с правильными `user_id`, `service`, `step`, `ts`
- `get_funnel_stats()` возвращает шаги в порядке `FUNNEL_STEPS[service]` (шаги без событий имеют `users: 0`)
- `COUNT(DISTINCT)`: один юзер с двумя одинаковыми событиями = 1
- `drop_off_pct`: первый шаг = `None`, prev=0 → `None`, корректное округление до 0.1
- Фильтр `from_dt`/`to_dt`: события вне окна не учитываются (границы — `>=`/`<=` от/до полночи)
- Невалидный `service` в `track_step` или `get_funnel_stats` → `ValueError`
- `render_chart()` возвращает `BytesIO` с PNG-сигнатурой (`b"\x89PNG"` в начале)

### `tests/unit/test_admin_funnel.py`

- Callback `funnel_menu` от не-админа → бот ничего не отправляет
- Callback `funnel_menu` от админа → отправляется клавиатура выбора сервиса
- Callback `funnel:pf_avito` → клавиатура выбора периода
- Callback `funnel:pf_avito:7d` → `send_photo` мокается, проверяется что caption содержит правильные числа и шаги в правильном порядке

E2E-тест PF flow не расширяем — юнит-тестов `track_step` достаточно.

## Out of scope

- **Фронтенд/веб-эндпоинт.** Не делаем. Просмотр только в Telegram.
- **Кастомные периоды** (ввод дат вручную). Пока только пресеты.
- **Архивация / удаление старых событий.** Таблица растёт линейно. При сотнях тысяч строк SQLite справится; вернёмся при необходимости.
- **Per-user детализация.** Только агрегаты.
- **Графика «реальной» heatmap.** Bar chart покрывает запрос; настоящая heatmap по callback'ам — отдельная история, не входит в этот тикет.
