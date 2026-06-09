# Payment reconciler — надёжное зачисление YooKassa-платежей

## TL;DR

YooKassa-платежи иногда не доходят до баланса: за 14 дней по выгрузке из YK выявлено 7 «застрявших» успешных платежей на 5 760 ₽. Корневая причина — у нас нет webhook'а и нет ни одного фонового механизма сверки; единственный путь зачисления — синхронный пуллинг бота в течение 6 минут после нажатия кнопки оплаты. Если клиент платит дольше или отваливается между этапами — деньги остаются в YK, у нас о них даже нет записи.

Решение: ввести **state machine** платежа (`pending → succeeded | canceled | expired`) прямо в таблице `refills`, и фоновый **reconciliation-крон** в bot-контейнере (раз в 60 сек), который сам опрашивает YK по нашим pending платежам и завершает их.

Webhook сознательно НЕ делаем: лишний публичный endpoint, проверка подписи, тестирование — а крон даёт такую же гарантию с задержкой ≤60 сек.

## Контекст и root cause

### Текущее устройство (что есть)

- **TG-флоу** (`handlers/refill.py:_handle_yookassa_payment`): после `Payment.create` блокирующий цикл `check_payment_status` — 12 попыток `Payment.find_one` с интервалом 30 сек = 6 минут. По успеху — `finalize_with_referral_bonus(..., БЕЗ payment_id, source_type="telegram")`. По таймауту — отправляется «оплата не прошла».
- **Web-флоу** (`web/routers/refill.py`): `POST /api/refill` создаёт инвойс. Финализация — только если фронт сам вызовет `GET /api/refill/{pid}/status`. `return_url=botlink` — клиента YooKassa редиректит в TG-бот, фронт лендинга /status НИКОГДА не дёргается → web-зачисление полностью сломано.
- **БД таблица `refills`**: журнал успешных пополнений. Все 11 294 строки имеют неявный статус «succeeded». Колонка `payment_id` — у TG-flow всегда NULL (баг: не передаётся в finalize), у web-flow заполняется. Колонка `date` — в смешанном формате: старые записи в `DD.MM.YYYY HH:MM:SS`, новые в `YYYY-MM-DDTHH:MM:SS+00:00`.
- Финализация (`services/refill.finalize`) идемпотентна через `payment_id`, но идемпотентность не работает в TG-flow (payment_id всегда NULL).
- `services/payment_probe.py` — это health-probe API YooKassa (создаёт-отменяет тестовые 1₽-платежи каждые 15 мин), НЕ reconciliation.

### Что обнаружили в диагностике

На проде 2026-06-09 (после ручной сверки `Payment.list(succeeded)` за 14 дней с учётом обоих форматов дат в refills и окна ±5ч):
- Всего успешных платежей в YK: 162 (5 страниц по 100).
- Из них **7 НЕ зачислены** на сумму **5 760 ₽**:
    1. `31ba1e1a-...` 300 ₽ Никита (8794553642, web) — 2026-06-09 12:43 UTC
    2. `31ba1d6c-...` 500 ₽ Дмитрий (8794553640, web) — 2026-06-09 12:41 UTC
    3. `31b76e2e-...` 500 ₽ user 8794553630 (web) — 2026-06-07 11:49 UTC
    4. `31b76c4f-...` 1000 ₽ staleksfoto (2137600714) — 2026-06-07 11:41 UTC
    5. `31af5380-...` 1260 ₽ horusgor (468390610) — 2026-06-01 08:21 UTC
    6. `31ad3b38-...` 1900 ₽ 24shina.moscow (6741171042) — 2026-05-30 18:13 UTC
    7. `31abe6d3-...` 300 ₽ kochevnik15 (996225380) — 2026-05-29 18:01 UTC
- Из них 2 (Никита и Дмитрий) — сегодняшние, web-флоу: лендинг не вызвал `/status` после оплаты.
- 2 (07.06 ~11:41-11:49) — в момент миграции прода 2026-06-07 11:27, когда бот был перезапускался.
- 3 (29.05-01.06) — ещё на старом боте до миграции; те же причины (6-минутное окно, return_url, нет фоновой сверки).
- В `database.db.pre-migration` они тоже отсутствуют → миграция БД переноса данных НЕ повредила. Это утечка, которая существовала и на старом боте.

### Root cause (один из двух классов)

1. **Нет фонового зачисления**: единственный путь — синхронный 6-минутный пуллинг (TG) или явный вызов клиентом `/status` (web). Если оба не сработали — деньги «застревают» в YK.
2. **Web-флоу полностью сломан**: `return_url=botlink` ([utils/yookassa_refil.py:51](utils/yookassa_refil.py:51)) → клиент после оплаты попадает в TG-бот, фронт /status не дёргает. Доказательство: в БД 0 записей с `source_type='web'` и 0 с заполненным `payment_id` среди 11 294 строк.

## Goals

- Любой `succeeded` платёж в YooKassa зачисляется на баланс не позже ~60 сек.
- Решение работает независимо от того, дождался ли клиент окна пуллинга и вернулся ли он на страницу статуса.
- Покрытие даунтайма бота до 24 часов (стандартное окно).
- 7 текущих застрявших платежей зачисляются разовым backfill-скриптом после релиза.

## Non-goals

- НЕ внедряем webhook от YooKassa (сознательный отказ: лишний публичный endpoint, IP-allowlist, подпись, отдельное тестирование).
- НЕ меняем `return_url` (явно: «не светить ни сайт, ни бот перед YooKassa»). Клиент после оплаты остаётся на странице YK или сам закрывает вкладку; деньги поступят на баланс через крон в течение минуты.
- НЕ переписываем синхронный TG-пуллинг (он остаётся как UX-ускорение: клиент получает «оплата успешна!» сразу, а не через минуту).
- НЕ унифицируем формат `refills.date` (старые `DD.MM.YYYY` остаются — крон работает только с новыми pending-записями в ISO).
- НЕ перепиливаем существующие отчёты целиком — только дописываем `AND status='succeeded'` в WHERE-частях.

## Архитектура

### State machine платежа

```
[нет записи]    ┌── pending ──> succeeded   (баланс +amount, atomic UPDATE+credit)
     │          │
     │          ├── pending ──> canceled    (баланс не меняется)
     │  create  │
     └──────────┴── pending ──> expired     (баланс не меняется, YK auto после ~24ч)
```

- Все переходы — **в одной таблице `refills`**, в поле `status`.
- Переход `pending → succeeded` — атомарный `UPDATE ... WHERE status='pending'`. `rowcount==1` ровно у одного победителя в гонке, и он же делает `credit(balance)`.

### Три источника финализации (один и тот же `finalize_with_referral_bonus`)

1. **Синхронный TG-пуллинг** (быстрый путь для TG-юзеров в первые 6 мин) — остаётся, но **передаёт `payment_id`** для корректной идемпотентности.
2. **Web-флоу `GET /api/refill/{pid}/status`** — остаётся как есть. Уже работает с `payment_id`. Останется неиспользованным на практике (фронт лендинга так и не возвращается, return_url=botlink), но не мешает.
3. **Reconciliation-крон** в bot-контейнере (новый компонент) — главный источник надёжности.

### Reconciliation-крон — алгоритм

```
APScheduler interval=60s, max_instances=1, misfire_grace_time=30:

rows = SELECT payment_id, user_id, amount, source_type, source_app_id
       FROM refills
       WHERE status='pending' AND date >= now_iso() - 24h

for row in rows:
    try:
        p = Payment.find_one(row.payment_id)   # YK API
    except Exception:
        logger.exception(...); continue

    match p.status:
        case 'succeeded':
            result = finalize_with_referral_bonus(
                row.user_id, row.amount,
                payment_id=row.payment_id,
                source_type=row.source_type,
                source_app_id=row.source_app_id,
            )
            if result.was_newly_finalized:
                await notify_user_success(...)
                await notify_admins(...)
                if result.referrer_bonus > 0:
                    await notify_referrer(...)
        case 'waiting_for_capture':
            Payment.capture(row.payment_id)    # next tick увидит succeeded
        case 'canceled' | 'rejected':
            UPDATE refills SET status='canceled' WHERE payment_id=row.payment_id
        case 'expired':
            UPDATE refills SET status='expired' WHERE payment_id=row.payment_id
        case 'pending':
            pass  # ждём следующий тик
```

### Где живёт крон

- В **bot-контейнере**, рядом с существующим `payment_probe` в `__main__.py:106-117`.
- Использует уже работающий APScheduler.
- В bot-контейнере живёт `bot` instance — удобно отправлять TG-уведомления из крона.

## Изменения схемы БД

### Миграция

```sql
ALTER TABLE refills ADD COLUMN status TEXT NOT NULL DEFAULT 'succeeded';
CREATE INDEX IF NOT EXISTS idx_refills_status_date ON refills (status, date);
CREATE UNIQUE INDEX IF NOT EXISTS uq_refills_payment_id
    ON refills (payment_id) WHERE payment_id IS NOT NULL;
```

- `DEFAULT 'succeeded'` → все 11 294 существующих записи мгновенно получают `succeeded` (фактическая правда: они уже зачислены).
- Индекс `(status, date)` — крон фильтрует по `status='pending' AND date >= ...`.
- Уникальный индекс по `payment_id` (только для NOT NULL — SQLite допускает множественные NULL в UNIQUE):
    - Защита от двойного INSERT pending для одного и того же платежа.
    - Старые 11 294 записи с `payment_id=NULL` уникальности не нарушают.

### Семантика `status`

| status | смысл | баланс |
|---|---|---|
| `pending` | инвойс создан, оплата ждётся | НЕ тронут |
| `succeeded` | оплата прошла, зачислено | +amount (уже инкрементирован) |
| `canceled` | клиент отменил или YK отклонил | НЕ тронут |
| `expired` | YK истёк срок платежа (~24ч) | НЕ тронут |

### Запросы в коде — фильтр `status='succeeded'`

Все SELECT/SUM по `refills` для агрегатов и проверок надо дополнить `AND status='succeeded'`. Точный список соберём через `grep -rn "FROM refills\\|JOIN refills"` на этапе плана. Известные точки:

- `services/refill._is_first_refill()` — важно для реф-бонуса, иначе pending запись «съест» первый бонус.
- `utils/sqlite3.get_user_all_refills()` — пользовательская история.
- `web/routers/admin_users.py` и админские отчёты (`web/routers/admin_*.py`).

Однотипное изменение: добавить `AND status='succeeded'` в `WHERE`.

## Изменения в коде — файл за файлом

### `services/refill.py`

**`create_invoice(user_id, amount, *, source_type, source_app_id)`** — сейчас возвращает `(url, pid)` и НЕ пишет в БД. Меняем:
1. Вызов `Payment.create(...)` в YK (как было).
2. После получения `payment_id` — `INSERT INTO refills (payment_id, user_id, amount, date, source_type, source_app_id, status='pending')`.
3. Если INSERT падает (БД залочена, повтор payment_id и т.п.) — логируем + admin alert через `send_admins`, возвращаем 502 клиенту. Платёж в YK висит, но мы о нём знаем по логу для ручного восстановления.

Сигнатура расширяется: добавляются `source_type` и `source_app_id` параметры (обязательно или с дефолтами — решит план).

**`finalize_with_referral_bonus(user_id, amount, payment_id, *, source_type, source_app_id)`** — атомарный переход:

```python
cur = con.execute(
    "UPDATE refills SET status='succeeded' WHERE payment_id=? AND status='pending'",
    (payment_id,)
)
if cur.rowcount == 1:
    credit(user_id, amount)
    was_newly_finalized = True
elif row := con.execute("SELECT status FROM refills WHERE payment_id=?", (payment_id,)).fetchone():
    if row['status'] == 'succeeded':
        was_newly_finalized = False  # already finalized, no-op
    else:
        raise UnexpectedStatus(f"refill {payment_id} is {row['status']}")
else:
    # Backfill: pending row отсутствует (например, для 7 текущих stuck или гонок где
    # синхронный TG-пуллинг успел до того, как create_invoice INSERT'нул pending).
    con.execute("INSERT INTO refills(...) VALUES (..., 'succeeded')", ...)
    credit(user_id, amount)
    was_newly_finalized = True
```

**`RefillResult`** обзаводится новым полем `was_newly_finalized: bool` — нужно ВСЕМ трём финализаторам (TG-handler, web-status, крон), чтобы отправлять уведомление ТОЛЬКО при реальном переходе и не задваивать их в гонках. Если синхронный TG-пуллинг успел завершить раньше крона, то крон увидит уже-succeeded → `was_newly_finalized=False` → уведомления не шлёт.

### `services/payment_reconciler.py` (новый)

Содержит `async def reconcile_pending() -> None` по алгоритму выше. Зависимости: `services.refill.finalize_with_referral_bonus`, `services.payment_notifications.*`, `yookassa.Payment`.

### `services/payment_notifications.py` (новый или часть `services/refill.py`)

Извлечь три функции из `handlers/refill.py:_handle_yookassa_payment` (строки 139-154):
- `notify_user_success(user_id, amount, balance)` — STR2.
- `notify_admins_success(user_string, amount, balance)` — STR3.
- `notify_referrer(referrer_id, bonus, new_balance)` — STR4.

Вызовут и TG-handler, и крон, и web-flow (последний сейчас уведомлений не шлёт вовсе — отдельный bug, фиксим заодно для консистентности).

### `handlers/refill.py` (TG-flow)

В `_handle_yookassa_payment`:
- Передавать `payment_id=payment_id` в `finalize_with_referral_bonus`.
- При `success=False` от 6-минутного пуллинга — заменить сообщение об ошибке на нейтральное: «Платёж не подтвердился банком за 6 минут. Если оплата прошла — баланс пополнится автоматически в течение минуты». Без этого клиент паникует на «ошибку», а через 30 сек крон зачислит — диссонанс UX.

### `web/routers/refill.py` (Web-flow)

- `POST /api/refill` — без правок снаружи. Внутри: `create_invoice(caller.user_id, payload.amount, source_type=caller.source_type, source_app_id=caller.source_app_id)` — добавляются параметры из `CurrentCaller` (они там уже есть). `create_invoice` сам INSERT'нет pending.
- `GET /api/refill/{pid}/status` — без правок. `finalize_with_referral_bonus` останется идемпотентным.
- Дополнительно: вызывать `notify_user_success`/`notify_admins_success` при успехе, но **только при `was_newly_finalized=True`** (защита от двойных уведомлений, если крон/пуллинг уже завершили этот же платёж). Сейчас web-flow не уведомляет — мелочь, попадает в scope, так как функции уже выделены.

### `__main__.py` (bot-контейнер)

```python
scheduler.add_job(
    reconcile_pending, 'interval', seconds=60,
    id='payment_reconciler', max_instances=1, misfire_grace_time=30,
)
```
Регистрация рядом с существующим `payment_probe`.

## Обработка ошибок и гонки

1. **Гонка TG-пуллинг ↔ крон ↔ web-status** для одного `payment_id` → атомарный `UPDATE...WHERE status='pending'` + `rowcount` проверка. Победитель ровно один.
2. **`INSERT pending` падает после `Payment.create` (БД заблокирована)** → лог + admin alert с `payment_id`. Клиенту 502. YK-платёж висит, восстанавливаем руками или скриптом по логам.
3. **YK API недоступен в моменте крона** → `logger.exception` + `continue` к следующему. Следующий тик повторит.
4. **`bot.send_message` падает** (юзер заблокировал бота) → `try/except`, лог, продолжаем. Деньги уже на балансе — главное.
5. **Pending старше 24ч** → выпадает из выборки крона. В YK уже `expired`. Принимаем как известный риск (эквивалент webhook-retry window).
6. **Два экземпляра крона** (ошибочный запуск второго контейнера) → `UNIQUE INDEX` по `payment_id` + `max_instances=1` в APScheduler.
7. **YK rate limit** при >100 pending в выборке → последовательно, без concurrency. ~100 req/min — далеко от лимита.
8. **Старый код где-то создал инвойс без INSERT pending** → крон не увидит, но `finalize` через TG-пуллинг или web-status сработает через ветку backfill INSERT succeeded напрямую.
9. **`waiting_for_capture` от YK** (двухстадийный платёж) → вызываем `Payment.capture()`, следующий тик увидит `succeeded`.

### Логирование

- Все переходы status (`pending → succeeded/canceled/expired`) → INFO в `storage/log.txt`.
- Все исключения в reconcile loop → `logger.exception` (stacktrace).
- При первой неудаче INSERT pending → admin alert. При множественных подряд (>3) ошибках `Payment.find_one` → admin alert.

## Тесты

### Unit `services/refill.finalize_with_referral_bonus`

1. **Pending → succeeded** (happy path): создать pending → finalize → `status='succeeded'`, `balance += amount`, `was_newly_finalized=True`.
2. **Идемпотентность**: повторный finalize того же `payment_id` → `balance` не меняется, `was_newly_finalized=False`.
3. **Backfill** (нет pending row): finalize → INSERT succeeded напрямую + credit.
4. **Реф-бонус начисляется** при первом успешном пополнении user с `ref_id`.
5. **Реф-бонус не дублируется** при повторном finalize (через `_is_first_refill()` + фильтр `status='succeeded'`).
6. **Гонка**: два параллельных finalize одного `payment_id` → ровно один credit, один `was_newly_finalized=True`.

### Unit `services/payment_notifications`

1. `notify_user_success` отправляет `bot.send_message` с правильным chat_id (из `auth_providers`), правильным текстом STR2.
2. Если у user_id нет `auth_providers.telegram` — функция не падает, лог-warning, возвращает silently.
3. Если `bot.send_message` бросает (юзер заблокировал бота) — функция не падает, лог-warning.

### Unit `services/payment_reconciler.reconcile_pending` (моки `yookassa.Payment.find_one`)

1. **YK succeeded** → finalize вызван, notify-функции вызваны.
2. **YK canceled** → `UPDATE status='canceled'`, finalize **не** вызван.
3. **YK waiting_for_capture** → `Payment.capture()` вызван, status остаётся pending.
4. **YK API exception на одном из pending** → loop продолжается с остальными.
5. **Пустой список pending** → no-op, нет вызовов find_one.
6. **Старые pending (>24h)** → выпадают из выборки.

### Integration (тестовая БД, моки YK SDK)

1. **Web E2E**: POST `/api/refill` → видим pending в refills → tick reconciler с моком `succeeded` → `users.balance` увеличен, `refills.status='succeeded'`.
2. **TG E2E**: handler создаёт инвойс → видим pending → мок `check_payment_status=True` → handler сам финализирует с `payment_id` → балас увеличен. Следующий тик reconciler → no-op (already succeeded).

### Регрессионные

- `SUM(amount) FROM refills WHERE user_id=X AND status='succeeded'` для отчётов — отдельный тест что фильтр `status='succeeded'` присутствует в обновлённых SELECT-ах.
- `_is_first_refill()` возвращает True если у юзера только pending записи (бонус ещё положен).

### Миграция

Создать БД со старой схемой (без `status`), залить N записей, прогнать миграцию → все записи имеют `status='succeeded'`, индексы созданы.

### Не тестируем

- Реальное YK API — только моки. Smoke-тест на проде после деплоя.
- Реальное Telegram API — моки на `bot.send_message`.

## Backfill 7 текущих застрявших платежей

Разовый management-скрипт `scripts/backfill_stuck_payments.py` с явным списком (известным из диагностики 2026-06-09):

```python
STUCK = [
    # (payment_id, user_id, amount, source_type)
    ('31ba1e1a-000f-5000-b000-1934f8b49a52', 8794553642, 300,  'web'),       # Никита
    ('31ba1d6c-000f-5000-b000-18ed29b434ee', 8794553640, 500,  'web'),       # Дмитрий
    ('31b76e2e-000f-5001-8000-137bad08104d', 8794553630, 500,  'web'),
    ('31b76c4f-000f-5000-8000-1b0b50f48647', 2137600714, 1000, 'telegram'),  # staleksfoto
    ('31af5380-000f-5001-9000-1571d32e7c8f', 468390610,  1260, 'telegram'),  # horusgor
    ('31ad3b38-000f-5001-8000-1d0e2d17940d', 6741171042, 1900, 'telegram'),  # 24shina
    ('31abe6d3-000f-5000-8000-165673068025', 996225380,  300,  'telegram'),  # kochevnik15
]
```

Для каждого payment_id:
1. `Payment.find_one(pid)` → подтвердить, что в YK всё ещё `succeeded`. Защита от ошибочного зачисления отменённых.
2. Если в `refills` уже есть запись с этим `payment_id` со `status='succeeded'` — пропустить.
3. Вызвать `finalize_with_referral_bonus(uid, amount, payment_id=pid, source_type=...)`. Сработает ветка backfill — INSERT succeeded напрямую.
4. Уведомить пользователя через TG: получить chat_id из `SELECT identifier FROM auth_providers WHERE user_id=? AND provider='telegram'` и `bot.send_message(chat_id, STR2)`. Если для user_id нет записи в `auth_providers` (web-only клиент — Никита, Дмитрий, 8794553630) — пропустить TG-уведомление, добавить лог-запись с пометкой «web-only»: им ответим вручную через support-чат, в котором они уже жалуются.
5. Уведомить админов в канале «orders».

Скрипт запускается **разово после деплоя**.

## Rollout-план

| Шаг | Команда / действие | Где |
|---|---|---|
| 1 | Backup БД: `cp storage/database.db storage/database.db.pre-status-mig` | прод |
| 2 | PR в `dev`, code review, merge | github |
| 3 | `./deploy.sh` — `docker compose build && up -d --force-recreate` | прод |
| 4 | Миграция применяется на старте контейнера (alembic/встроенный migrate) | автоматически |
| 5 | Проверить `storage/log.txt` — крон стартанул, нет ошибок | прод |
| 6 | `docker compose exec bot python -m scripts.backfill_stuck_payments` | прод |
| 7 | Smoke-test: создать 1 ₽ платёж через лендинг, оплатить, через 60-90с проверить баланс | прод |
| 8 | Мониторинг логов 30 минут после деплоя | прод |

### Откат

- `docker compose down`
- `cp storage/database.db.pre-status-mig storage/database.db`
- `git checkout <предыдущий коммит>` → `./deploy.sh`
- Бэкап `database.db.pre-status-mig` храним минимум 7 дней.

## Что НЕ входит в этот milestone

- **Webhook** от YooKassa — явный отказ.
- **Изменение `return_url`** — явный отказ («не светить ни сайт, ни бот перед YK»).
- **Унификация формата `refills.date`** — старые `DD.MM.YYYY` остаются. Крон работает только с новыми pending в ISO.
- **Перенос синхронного TG-пуллинга на async-задачу** — он остаётся как UX-ускорение, не блокер для корректности.
- **Унификация `_handle_yookassa_payment` и крона до одной кодовой точки** — оба используют общий `finalize_with_referral_bonus` + общие `notify_*`, этого достаточно.
