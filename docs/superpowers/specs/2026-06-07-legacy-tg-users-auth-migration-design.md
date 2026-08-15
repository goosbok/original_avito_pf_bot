# Legacy TG Users Auth Migration — Design

**Date:** 2026-06-07
**Status:** Draft → ожидает merge в dev → деплой

## 1. Цель

Закрыть deploy-блокер на проде: каждый старый юзер при первом обращении к новому боту получает дубль и теряет доступ к своему легаси-аккаунту (балансу, заказам).

Корень: легаси-схема хранила `users.id == tg_id` без таблицы `auth_providers`. Новая схема (dev) ищет TG-юзера через JOIN с `auth_providers`. Для 14773 легаси-юзеров записей в `auth_providers` нет — middleware считает их новыми и плодит дубли.

## 2. Скоуп

**В скоупе:**
- Скрипт `scripts/backfill_telegram_providers.py` — создать недостающие `auth_providers (telegram, str(users.id))` для всех legacy юзеров. Идемпотентно.
- Скрипт `scripts/merge_duplicate_tg_users.py` — найти и слить уже созданные дубли (legacy_id vs duplicate_id). Идемпотентно.
- Defensive fix в `services/identity.py::get_or_create_user_by_telegram` — fallback на существующего legacy юзера если в БД есть строка `users.id == tg_id` без telegram-провайдера.
- Юнит-тесты для всех трёх изменений.

**Out of scope:**
- Перенумерация `users.id` (нуклеарный вариант, не нужен).
- Миграция других провайдеров (email, password) — отдельная история.
- Backfill для других auth-источников.

## 3. Архитектура

### 3.1. Backfill

Один SQL за один проход:

```sql
INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified)
SELECT u.id, 'telegram', CAST(u.id AS TEXT), :now, 1
FROM users u
WHERE NOT EXISTS (
  SELECT 1 FROM auth_providers ap
  WHERE ap.user_id = u.id AND ap.provider = 'telegram'
);
```

- `verified=1` — факт строки в `users` в легаси-схеме подтверждал реального TG-юзера (только бот мог их создать).
- Идемпотентно через `NOT EXISTS`.
- Возвращает количество вставленных строк.

Edge cases:
- Юзеры с email/phone-only auth (без telegram-провайдера) — попадут в backfill и получат telegram-провайдер на свой `users.id`. Это безопасно: если их `users.id` случайно совпадёт с чьим-то реальным TG ID — будет конфликт в `UNIQUE(provider, identifier)`. Маловероятно (auto-increment начинается с 1, TG ID — 9-10 знаков), но защищаемся: `INSERT OR IGNORE` в реализации.

### 3.2. Merge дублей

Найти пары `(legacy_id, duplicate_id)`:

```sql
SELECT u.id AS legacy_id, ap.user_id AS duplicate_id
FROM users u
JOIN auth_providers ap
  ON ap.provider = 'telegram' AND ap.identifier = CAST(u.id AS TEXT)
WHERE ap.user_id != u.id;
```

Для каждой пары — переиспользовать логику merge'а из существующего `services/identity.py::_merge_phone_only_into` (приватная функция, ~70 строк). План: вынести её в публичный `merge_user_into(con, source_user_id, target_user_id)` и вызвать из обоих мест (старого и нового скрипта).

Что переносим из `duplicate` в `legacy` в одной транзакции:
- `orders.user_id = legacy_id WHERE user_id = duplicate_id`
- `refills.user_id = legacy_id WHERE user_id = duplicate_id`
- `notifications.user_id = legacy_id WHERE user_id = duplicate_id`
- `funnel_events.user_id = legacy_id WHERE user_id = duplicate_id`
- `support_messages.user_id = legacy_id WHERE user_id = duplicate_id`
- `otp_codes.user_id_to_link = legacy_id WHERE user_id_to_link = duplicate_id`
- `users SET balance = balance + (SELECT balance FROM users WHERE id=duplicate_id) WHERE id=legacy_id`
- `users SET user_name = COALESCE(user_name, дубля.user_name), first_name = COALESCE(first_name, дубля.first_name) WHERE id=legacy_id` (заполняем дырки)
- Все `auth_providers` дубля — переориентировать на legacy. С UNIQUE(provider, identifier) collisions: если у legacy уже есть phone/email — оставляем legacy, удаляем у дубля.
- `DELETE FROM users WHERE id = duplicate_id`

Идемпотентно: повторный запуск не найдёт пар.

### 3.3. Defensive fix

В `services/identity.py::get_or_create_user_by_telegram`:

```python
def get_or_create_user_by_telegram(tg_id, *, user_name=None, first_name=None, ref_id=None):
    user_id = find_user_id_by_provider("telegram", str(tg_id))
    if user_id is not None:
        return user_id

    # Legacy-safety: возможно это старый юзер с users.id == tg_id, для которого
    # backfill ещё не отработал (или восстанавливалась БД из старого бэкапа).
    # Привязываем telegram-провайдер к нему и НЕ создаём дубль.
    legacy = _find_legacy_user_by_id(tg_id)
    if legacy is not None:
        link_provider(legacy["id"], "telegram", str(tg_id))
        return int(legacy["id"])

    # Реально новый юзер
    new_id = _create_user(user_name=user_name, first_name=first_name, ref_id=ref_id)
    link_provider(new_id, "telegram", str(tg_id))
    return new_id


def _find_legacy_user_by_id(uid):
    """SELECT * FROM users WHERE id=uid. Используется как fallback в
    get_or_create_user_by_telegram (legacy bot хранил users.id == tg_id)."""
    with connect() as con:
        row = con.execute("SELECT id FROM users WHERE id = ?", (int(uid),)).fetchone()
    return dict(row) if row else None
```

Сложность O(1) — индекс PK.

### 3.4. Порядок применения

1. **Backfill** — закрывает 100% существующих legacy-юзеров (создаёт провайдеры).
2. **Merge** — собирает уже созданных дублей в одну legacy-строку.
3. **Defensive fix** — защита от любых пропущенных в backfill'е случаев (например после restore БД из старого бэкапа).

Defensive fix в коде — навсегда (часть кода ветки). Скрипты — однократно при выкатке.

## 4. Деплой

```bash
ssh root@167.233.52.85 'cd /root/projects/original_avito_pf_bot && \
  git pull origin dev && \
  docker compose build api bot && \
  docker compose stop bot && \
  docker compose run --rm api python -m scripts.backfill_telegram_providers && \
  docker compose run --rm api python -m scripts.merge_duplicate_tg_users && \
  docker compose up -d bot api'
```

Downtime бота: ~30 сек на время backfill+merge. API можно не останавливать (он не создаёт дублей).

## 5. Тесты

**Backfill:**
- Юзер без provider → создаётся `(telegram, str(id))` → вернулось count=1.
- Юзер с уже существующим provider → не дублируется.
- Юзер с phone-only provider, без telegram → создаётся telegram (на его users.id).
- Запуск второй раз → 0 вставок.

**Merge:**
- Пара legacy + duplicate с orders/refills/notifications/balance → всё перенесено в legacy, дубль удалён, провайдеры переориентированы.
- Конфликт UNIQUE: у legacy есть phone, у duplicate тоже phone → у legacy остаётся, у дубля удаляется.
- Запуск второй раз → 0 пар.

**Defensive fix:**
- tg_id такого, что в users есть row id=tg_id без telegram-провайдера → возвращается этот id, не создаётся новый.
- tg_id «нового» юзера (нет ни в users, ни в auth_providers) → создаётся новый.
- tg_id с уже существующим провайдером → возвращается его user_id (как раньше).

## 6. Открытые вопросы / Out of scope

- Что делать с email/phone-only юзерами, чей `users.id` случайно может пересечься с реальным TG ID? — Защищаемся через `INSERT OR IGNORE` в backfill. Маловероятно, но логируем.
- Уведомление юзеров о слиянии — не нужно (юзер не заметит, он просто увидит свои старые заказы при первом заходе).
