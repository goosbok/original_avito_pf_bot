# Runbook — миграция юзеров из `main` БД на `dev`

**Дата:** 2026-06-07
**Контекст:** при переезде сервера/БД, где исходная БД от ветки `main` (легаси-бот), а целевой код от ветки `dev` (web + auth_providers + новые провайдеры).
**Спек:** [docs/superpowers/specs/2026-06-07-legacy-tg-users-auth-migration-design.md](../superpowers/specs/2026-06-07-legacy-tg-users-auth-migration-design.md)

## Почему это нужно

**Легаси-схема (`main`):** `users.id == tg_id`, таблицы `auth_providers` нет — связь юзера с Telegram только через `users.id`.

**Новая схема (`dev`):** `users.id` — авто-инкремент, связь с TG через строку в `auth_providers (provider='telegram', identifier=str(tg_id))`.

После переноса БД из `main` все 14K+ юзеров есть в `users`, но **ни у кого нет соответствующих `auth_providers`**. Middleware `exists_user` находит их через JOIN с `auth_providers` → не находит → считает каждого «новым» → создаёт **дубля с авто-id**, привязывает к нему telegram-провайдер, а старая строка `users.id == tg_id` остаётся **orphan'ом**. Юзер теряет баланс и заказы.

Каждое касание бота легаси-юзером плодит дубль. **Это деплой-блокер.**

Решение состоит из 3 частей:
1. **Backfill** — однократный SQL: создать `auth_providers (telegram, str(users.id))` для всех легаси без провайдера.
2. **Merge** — однократный скрипт: для всех уже созданных дублей слить их в их легаси-строку.
3. **Defensive fix в коде** (уже в dev HEAD ≥ `15843d0`): `get_or_create_user_by_telegram` теперь делает fallback на `users WHERE id=tg_id` перед созданием нового — страховка от пропущенных в backfill'е случаев или restore из старого бэкапа.

## Pre-flight checklist

```bash
ssh root@<PROD_IP>
cd /root/projects/original_avito_pf_bot

# 1. Зафиксировать SHA текущего кода + сделать снимок БД
git log -1 --format='%H %s' > /tmp/git_state.txt
BACKUP_DIR=/root/backups/pre-tg-auth-migration-$(date +%Y%m%d-%H%M%S)
mkdir -p $BACKUP_DIR
cp storage/database.db $BACKUP_DIR/database.db
cp .env $BACKUP_DIR/.env
md5sum $BACKUP_DIR/database.db
ls -la $BACKUP_DIR

# 2. Убедиться что код = dev и содержит фикс (commit ≥ 15843d0 или его потомки)
git log --oneline | grep -E "backfill\+merge\+fallback for legacy TG users"

# 3. Текущее состояние БД (запомни числа на потом):
docker compose exec -T api python <<'PY'
import sqlite3
con = sqlite3.connect('/app/storage/database.db')
print('users total:', con.execute('SELECT COUNT(*) FROM users').fetchone()[0])
print('auth_providers telegram:', con.execute(
    "SELECT COUNT(*) FROM auth_providers WHERE provider='telegram'"
).fetchone()[0])
print('orders total:', con.execute('SELECT COUNT(*) FROM orders').fetchone()[0])
PY
```

## Запуск миграции

### Шаг 1. Остановить бота

```bash
docker compose stop bot
```

API не останавливаем — он сам orphan'ов не плодит, web-логин по телефону создаёт нового юзера только при отсутствии телефона в `auth_providers` (а после backfill всё на месте).

Окно даунтайма бота: ~30 сек до завершения шага 3.

### Шаг 2. Backfill telegram-провайдеров

```bash
docker compose run --rm -T --no-deps api python -m scripts.backfill_telegram_providers
```

**Ожидаемый вывод:** `backfill: inserted N telegram providers`, где `N` примерно равно числу users из шага «Pre-flight». Логи:

```
backfill_telegram_providers: inserted N rows
```

**Свойства:**
- Один SQL `INSERT OR IGNORE` с подзапросом `WHERE NOT EXISTS`.
- Идемпотентен: второй прогон вставит 0.
- `verified=1` — сам факт строки в legacy `users` подтверждал реального TG-юзера.

### Шаг 3. Merge дублей

```bash
docker compose run --rm -T --no-deps api python -m scripts.merge_duplicate_tg_users
```

**Ожидаемый вывод:**
- `merge: merged M pairs`, где `M` = сколько юзеров уже успели создать дубль до миграции (обычно 0..несколько десятков).
- В логе на каждую пару: `merged duplicate <dup_id> into legacy <legacy_id>`.

**Что переносится в одной транзакции:**
- `orders`, `refills`, `notifications`, `funnel_events`, `support_messages`, `otp_codes` — `UPDATE ... SET user_id = legacy_id WHERE user_id = duplicate_id`
- `balance`: `legacy.balance += duplicate.balance`
- `user_name` / `first_name`: COALESCE — заполняются у legacy если пусты
- `auth_providers` дубля: переориентируются на legacy. При конфликте UNIQUE(provider, identifier) — legacy выигрывает, у дубля удаляется
- `DELETE FROM users WHERE id = duplicate_id`

Идемпотентен: повторный прогон не найдёт пар.

### Шаг 4. Запустить с пересозданием

```bash
docker compose up -d --force-recreate api bot
```

Важно `--force-recreate` если правил `.env` — иначе `restart` не подхватит переменные.

Подождать ~15 сек, проверить:

```bash
curl -sf http://127.0.0.1:8000/api/health
docker compose logs --tail 10 bot
```

Должно быть `{"status":"ok"}` и `Start polling`.

## Верификация

```bash
docker compose exec -T api python <<'PY'
import sqlite3
con = sqlite3.connect('/app/storage/database.db')
con.row_factory = sqlite3.Row

# 1. Каждый user должен иметь хотя бы один auth_provider
n_users = con.execute('SELECT COUNT(*) FROM users').fetchone()[0]
n_with_tg = con.execute(
    "SELECT COUNT(DISTINCT user_id) FROM auth_providers WHERE provider='telegram'"
).fetchone()[0]
print(f'users total: {n_users}')
print(f'users with telegram provider: {n_with_tg}')
print(f'без telegram-провайдера: {n_users - n_with_tg}')  # ожидаем 0 либо очень мало (web-only регистрации)

# 2. Дубли не должны находиться
n_dups = con.execute("""
  SELECT COUNT(*) FROM users u
  JOIN auth_providers ap
    ON ap.provider='telegram' AND ap.identifier = CAST(u.id AS TEXT)
  WHERE ap.user_id != u.id
""").fetchone()[0]
print(f'orphan duplicates: {n_dups}')   # MUST be 0

# 3. Orphan orders (на удалённых юзеров)
n_orphan_orders = con.execute("""
  SELECT COUNT(*) FROM orders o
  WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = o.user_id)
""").fetchone()[0]
print(f'orphan orders (легаси-мусор): {n_orphan_orders}')   # может быть >0 если в legacy уже был мусор

# 4. Конкретный юзер: вставь свой tg_id ниже
TG_ID = 295642149
u = con.execute('SELECT id, user_name, balance FROM users WHERE id=?', (TG_ID,)).fetchone()
print(f'\nuser {TG_ID}: {dict(u) if u else "NOT FOUND"}')
print(f'  orders: {con.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (TG_ID,)).fetchone()[0]}')
print(f'  providers:')
for r in con.execute('SELECT * FROM auth_providers WHERE user_id=?', (TG_ID,)).fetchall():
    print(f'    {dict(r)}')
PY
```

**Что должно сойтись:**
- `users total` ≈ `users with telegram provider`. Разница может быть только у юзеров, зарегистрированных через web по email/phone (без TG).
- `orphan duplicates: 0`
- `orphan orders` могут быть >0 — это legacy-мусор от удалённых в прошлом юзеров, не связан с этой миграцией.
- По конкретному юзеру: balance/orders сохранены, провайдер на месте.

## Real-world цифры (прод 167.233.52.85, 2026-06-07)

- В БД до миграции: 14773 users, 0 auth_providers(telegram).
- Backfill: **14769 строк** (4 уже имели какие-то auth_providers — web-only регистрации, не получили telegram-провайдер).
- Merge: **2 пары** — успели появиться дубли пока шёл деплой нового бота.

## Rollback

Если что-то пошло не так:

```bash
docker compose down
cp /root/backups/pre-tg-auth-migration-<DATE>/database.db storage/database.db
docker compose up -d
```

Сценарии когда нужен rollback:
- Скрипт `merge_duplicate_tg_users.py` упал в середине обработки пар (один merge с эксепшеном) — пары после него не обработаны. Backfill уже отработал, повторный запуск merge'а добьёт оставшихся, без rollback'а.
- Логи показывают что merge перенёс заказы не туда: rollback на backup и анализ.

## Будущие восстановления БД из старых бэкапов

Если в будущем понадобится восстанавливать БД из старого `pre-tg-auth-migration-*` бэкапа — после restore'а **обязательно** прогнать `backfill_telegram_providers` ещё раз. Defensive fix в `get_or_create_user_by_telegram` (commit `15843d0`+) подстрахует на лету, но lazy-разрешение хуже batched-backfill'а (в логах увидите `link_provider` на каждый legacy juicer'а отдельно).
