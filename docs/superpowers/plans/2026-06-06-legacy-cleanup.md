# Legacy Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Удалить мёртвый код (легаси), не относящийся к рабочему флоу заказа ПФ. Не выпиливаем рабочие фичи (баланс, refill, промокоды, саппорт остаются).

**Architecture:** Удаление по принципу «один логический кусок = один атомарный коммит» на ветке `dev`. Восемь задач: Wave A (6 пунктов, нулевой риск — точечные удаления) → Wave B (2 пункта, средний риск — удаление фич бота без UI-входа). Wave C из spec'а — только чек-лист в репо, не исполняется в этом проходе.

**Tech Stack:** Python 3, aiogram-2, FastAPI, React (SPA в `<script>` тегах через CDN, без сборщика), pytest, Docker Compose.

**Spec:** [docs/superpowers/specs/2026-06-06-legacy-cleanup-design.md](../specs/2026-06-06-legacy-cleanup-design.md)

---

## Подготовка к работе

Все задачи делаются на ветке `dev` (или текущей рабочей ветке, по умолчанию `claude/practical-brahmagupta-945fd9` в worktree).

**Команды верификации** (используются после каждой задачи):

```bash
# 1. Тесты в Docker (per memory rule — никогда не через локальный python3)
docker exec api pytest tests/ -x -q

# 2. Проверка что бот стартует (импорт-тайм фейлы)
docker exec bot python -c "from handlers.main_start import *; print('bot imports OK')"

# 3. Проверка что web стартует
docker exec api python -c "from web.main import app; print('web imports OK')"
```

Если на машине разработчика нет запущенных `api`/`bot` контейнеров, поднять перед началом работы:

```bash
docker compose up -d api bot
```

**Ручная проверка LK** (только для задач, трогающих `web/static/`):
- Открыть `http://localhost:8000` в браузере
- Проверить на mobile viewport (375px) и desktop (1280px+) — обе резолюции (per memory rule)
- Открыть форму заказа, убедиться что флоу `unpaid → yookassa redirect` работает (без реальной оплаты — достаточно получить redirect URL)

---

## Wave A — нулевой риск

### Task A1: Удалить `lending.html`

**Files:**
- Delete: `lending.html`

- [ ] **Step 1: Подтвердить отсутствие ссылок**

```bash
grep -rn "lending\.html" --include="*.py" --include="*.html" --include="*.js" --include="*.jsx" --include="*.conf" --include="*.yml" --include="Dockerfile*" --include="Makefile" --include="*.sh" --include="*.md" .
```

Expected output: пусто (no matches).

- [ ] **Step 2: Удалить файл**

```bash
git rm lending.html
```

- [ ] **Step 3: Запустить тесты**

```bash
docker exec api pytest tests/ -x -q
```

Expected: PASS.

- [ ] **Step 4: Коммит**

```bash
git commit -m "$(cat <<'EOF'
chore(cleanup): remove orphan lending.html (646KB)

Bundler export of an old landing draft. Not referenced from nginx,
docker-compose, or any source file. The current landing lives in
web/landing/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A2: Удалить endpoint `POST /api/auth/email/register`

**Files:**
- Modify: `web/routers/auth_email.py:35-47`
- Modify: `tests/web/test_routers_auth_email.py` (удалить только тест-кейс на legacy `/register`)

- [ ] **Step 1: Найти тест-кейсы legacy endpoint'а**

```bash
grep -nE "post.*['\"]/api/auth/email/register['\"]|post.*['\"]/register['\"]" tests/web/test_routers_auth_email.py
```

Expected: одна или несколько строк с `client.post("/api/auth/email/register", ...)` (БЕЗ `-request`/`-verify`).

- [ ] **Step 2: Удалить endpoint из роутера**

Открыть [web/routers/auth_email.py](web/routers/auth_email.py). Найти и удалить блок (примерно lines 33–47, ориентируйся на содержимое — пустая строка перед, потом endpoint, потом пустая строка):

```python
@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: EmailRegisterRequest) -> TokenResponse:
    """Register a new user with email and password (legacy: immediate registration).

    Kept for backwards compatibility. New flow is /register-request → /register-verify.
    """
    try:
        user_id = auth_email.register(body.email, body.password, first_name=body.first_name)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (InvalidCredentials, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TokenResponse(access_token=create_jwt(user_id))
```

- [ ] **Step 3: Проверить, что в `services/auth_email.py` функция `register` всё ещё используется**

Эта функция может звать `register_request` и `register_verify`. Грeп:

```bash
grep -nE "auth_email\.register\b" --include="*.py" -r . | grep -v "register_request\|register_verify"
```

Если только что был удалённый endpoint — `auth_email.register` тоже неиспользуем, помечаем для возможного удаления. Если ещё где-то зовётся — оставить.

- [ ] **Step 4: Удалить тест-кейс`/register` в test_routers_auth_email.py**

Открыть `tests/web/test_routers_auth_email.py`, найти все тесты, которые делают `client.post("/api/auth/email/register", ...)` (НЕ путать с `register-request`/`register-verify`!). Удалить только эти тест-функции целиком, включая их декораторы (`@pytest.fixture` если есть).

- [ ] **Step 5: Запустить тесты**

```bash
docker exec api pytest tests/web/test_routers_auth_email.py -v
docker exec api pytest tests/ -x -q
```

Expected: PASS.

- [ ] **Step 6: Старт api**

```bash
docker exec api python -c "from web.main import app; print('OK')"
```

Expected: `OK`.

- [ ] **Step 7: Коммит**

```bash
git add web/routers/auth_email.py tests/web/test_routers_auth_email.py
git commit -m "$(cat <<'EOF'
chore(cleanup): drop legacy /api/auth/email/register endpoint

Replaced by two-step /register-request → /register-verify. No frontend
caller; only its own legacy test referenced it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A3: Удалить закомментированные кнопки в клавиатурах

**Files:**
- Modify: `keyboards/inline_keyboards.py:42-71` (3 закомментированных блока)
- Modify: `keyboards/users_menu.py:38-49` (1 закомментированный блок)

- [ ] **Step 1: Открыть `keyboards/inline_keyboards.py`** и удалить три блока:

**Блок 1 — Яндекс ПФ (lines 42-47):**

```python
    """keyboard.add(
        InlineKeyboardButton(
            text=f"🚀 Заказать ПФ Яндекс",
            callback_data='yandex_pf'
        )
    ),"""
```

**Блок 2 — btn_reviews + btn_seo_boost (lines 48-59):**

```python
    # keyboard.add(
    #     InlineKeyboardButton(
    #         text=get_string('btn_reviews'),
    #         callback_data="reviews"
    #     )
    # ),
    # keyboard.add(
    #     InlineKeyboardButton(
    #         text=get_string('btn_seo_boost'),
    #         callback_data="seo_boost"
    #     )
    # )
```

**Блок 3 — review_bonus (lines 66-71):**

```python
    """keyboard.add(
        InlineKeyboardButton(
            text=f"❗️Получи 1.000₽ баланса за отзыв❗️",
            callback_data='review_bonus'
        )
    ),"""
```

После удаления: оставшиеся `keyboard.add(...)` блоки должны корректно разделяться запятыми и пустыми строками. Если нужна косметика — добавь одну пустую строку между смежными `keyboard.add`.

- [ ] **Step 2: Открыть `keyboards/users_menu.py`** и удалить блок (lines 38-49):

```python
    # keyboard.add(
    #     InlineKeyboardButton(
    #         text=get_string('btn_reviews'),
    #         callback_data="reviews"
    #     )
    # ),
    # keyboard.add(
    #     InlineKeyboardButton(
    #         text=get_string('btn_seo_boost'),
    #         callback_data="seo_boost"
    #     )
    # )
```

- [ ] **Step 3: Проверить синтаксис Python**

```bash
docker exec bot python -m py_compile keyboards/inline_keyboards.py keyboards/users_menu.py
```

Expected: тишина (нет ошибок).

- [ ] **Step 4: Старт бота**

```bash
docker exec bot python -c "from keyboards.inline_keyboards import get_menu_kb; from keyboards.users_menu import get_menu_kb as gm2; print('keyboards OK')"
```

Expected: `keyboards OK`.

- [ ] **Step 5: Тесты**

```bash
docker exec api pytest tests/ -x -q
```

Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add keyboards/inline_keyboards.py keyboards/users_menu.py
git commit -m "$(cat <<'EOF'
chore(cleanup): remove commented-out menu buttons (reviews/seo/yandex_pf)

These services were UI-disabled long ago; the underlying handlers go
in Wave B.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A4: Удалить мёртвый callback-хандлер `qna_avito`

**Files:**
- Modify: `handlers/commands.py:115-126`

- [ ] **Step 1: Подтвердить, что callback_data с префиксом `qna_avito` нигде не отправляется**

```bash
grep -rn "callback_data.*qna_avito\|callback_data=['\"]qna_avito" --include="*.py" .
```

Expected: пусто.

- [ ] **Step 2: Удалить блок lines 115-126 в `handlers/commands.py`**:

```python
@dp.callback_query_handler(text_startswith="qna_avito", state='*')
async def user_call_qna_avito(call: CallbackQuery, state: FSMContext):
    logger.info("qna_avito callback: tg_id=%s data=%s", call.from_user.id, call.data)
    all_qna = get_all_qna_avito()
    try:
        await call.message.delete()
    except Exception:
        logger.debug("qna_avito: could not delete message")
    for qna in all_qna:
        if qna['parametr'] == call.data:
            await call.message.answer(qna['value'], reply_markup=qna_avito_kb())
```

**Важно:** импорты `qna_avito_kb` и `get_all_qna_avito` в шапке `commands.py` (lines 12 и 19) **не трогать** — они используются в другом хандлере (`commands.py:94 — await call.message.answer(STR, reply_markup=qna_avito_kb())`).

- [ ] **Step 3: Проверка импортов**

```bash
docker exec bot python -c "from handlers.commands import *; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Тесты**

```bash
docker exec api pytest tests/ -x -q
```

Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add handlers/commands.py
git commit -m "$(cat <<'EOF'
chore(cleanup): drop dead qna_avito callback handler

The handler listened for callback_data starting with 'qna_avito', but no
keyboard sends such a value — Q&A buttons use the dynamic value from
qna['parametr']. The other qna handler (info:qna entry) keeps using
qna_avito_kb so its imports stay.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A5: Убрать legacy alias `'order-pf'` в SPA

**Files:**
- Modify: `web/static/app.jsx` (lines ~197, ~221-228, ~272-274)

- [ ] **Step 1: В `web/static/app.jsx` найти строку с роутом 'order-pf' (около line 272-274) и заменить**

Найти:

```jsx
      // 'order-new' is the new unified form. 'order-pf' kept as alias for legacy callsites.
      case 'order-new':
      case 'order-pf':
        return <OrderFormPage
```

Заменить на:

```jsx
      case 'order-new':
        return <OrderFormPage
```

- [ ] **Step 2: В `app.jsx` найти комментарий «legacy callsites» в `handleNavigate` (около line 221)**

Найти:

```jsx
    if (target === 'order-detail') {
      // Accept either a full order object (legacy callsites) or { order_id }.
      if (payload && (payload.order_id != null || payload.increment != null)) {
        setSelectedOrder(payload);
        setDetailOrderId(payload.order_id != null ? payload.order_id : payload.increment);
      } else if (typeof payload === 'number') {
        setSelectedOrder(null);
        setDetailOrderId(payload);
      } else {
        setSelectedOrder(payload || null);
        setDetailOrderId(null);
      }
    }
```

Перед удалением проверить грeпом, что во всех callsite'ах `onNavigate('order-detail', X)` передаётся объект `{order_id: N}` или просто число `N`, **не** полный объект заказа:

```bash
grep -rn "onNavigate(['\"]order-detail['\"]" web/static/ | head -20
```

Если все вызовы передают `{order_id}` или число — упростить блок до:

```jsx
    if (target === 'order-detail') {
      if (payload && payload.order_id != null) {
        setSelectedOrder(null);
        setDetailOrderId(payload.order_id);
      } else if (typeof payload === 'number') {
        setSelectedOrder(null);
        setDetailOrderId(payload);
      } else {
        setSelectedOrder(null);
        setDetailOrderId(null);
      }
    }
```

Если есть хоть один вызов с полным объектом заказа (`onNavigate('order-detail', orderObj)` где orderObj содержит больше полей) — НЕ упрощать, оставить как есть, добавить TODO-комментарий и пропустить этот шаг.

- [ ] **Step 3: Удалить упоминание `'order-pf'` из комментария на line 197**

Найти:

```jsx
    // Auth-gated routes. 'order-new' / 'order-pf' / 'order-detail' are PUBLIC now
```

Заменить на:

```jsx
    // Auth-gated routes. 'order-new' / 'order-detail' are PUBLIC now
```

- [ ] **Step 4: Грeп — убедиться что `'order-pf'` больше нигде не осталось в коде**

```bash
grep -rn "'order-pf'\|\"order-pf\"" web/static/
```

Expected: пусто (если что-то осталось — поправить, кроме комментариев в коммитах).

- [ ] **Step 5: Старт API + ручная проверка**

```bash
docker compose up -d api
```

Открыть в браузере `http://localhost:8000/order-new` (если SPA это handle'ит) и `http://localhost:8000` — убедиться что форма заказа рендерится корректно. Проверить mobile (375px) и desktop (1280px).

- [ ] **Step 6: Тесты**

```bash
docker exec api pytest tests/ -x -q
```

Expected: PASS.

- [ ] **Step 7: Коммит**

```bash
git add web/static/app.jsx
git commit -m "$(cat <<'EOF'
chore(cleanup): drop 'order-pf' SPA alias + legacy callsite handling

'order-new' is the only entry. No external links to /order-pf were found;
all onNavigate('order-detail', ...) callsites pass { order_id } or a
number, never a full order object.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A6: Удалить дубликат `str2dict` в `utils/other_functions.py`

**Files:**
- Modify: `utils/other_functions.py:36-40`

- [ ] **Step 1: Подтвердить, что определения идентичны**

```bash
sed -n '15,18p' utils/other_functions.py && echo "---" && sed -n '36,39p' utils/other_functions.py
```

Expected: оба блока выглядят как:

```python
def str2dict(str_value):
    result_dict = ast.literal_eval(str_value)

    return result_dict
```

Если тела отличаются — остановиться, разобраться, какое из них «правильное» (по callsite'ам в `grep -rn '\\bstr2dict\\b'`). В этом плане мы предполагаем идентичность.

- [ ] **Step 2: Удалить второе определение**

Открыть `utils/other_functions.py` и удалить блок line 36-40 (включая trailing blank line, чтобы не остался пустой пробел перед `# Падежи для слова день`):

```python
def str2dict(str_value):
    result_dict = ast.literal_eval(str_value)

    return result_dict

```

- [ ] **Step 3: Проверить, что осталось одно определение**

```bash
grep -nE "^def str2dict" utils/other_functions.py
```

Expected: одна строка (line 15).

- [ ] **Step 4: Тесты**

```bash
docker exec api pytest tests/ -x -q
```

Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add utils/other_functions.py
git commit -m "$(cat <<'EOF'
chore(cleanup): drop duplicate str2dict definition

The function was defined twice with identical bodies — the second def
silently overwrote the first.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Wave B — средний риск

### Task B7a: Выпил «Яндекс ПФ» и «Review bonus» хандлеров из `handlers/pf_order.py`

**Files:**
- Modify: `handlers/pf_order.py:64-72`

Эти 2 хандлера — заглушки, отвечающие «Данная функция в разработке». Кнопки удалены в A3.

- [ ] **Step 1: Открыть `handlers/pf_order.py` и удалить блок lines 64-72**:

```python
@dp.callback_query_handler(text="yandex_pf", state='*')
async def yandex_pf(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🧑🏻‍💻 Данная функция в разработке")


@dp.callback_query_handler(text="review_bonus", state='*')
async def call_review_bonus(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🧑🏻‍💻 Данная функция в разработке")
```

Оставить пустую строку (одну) перед следующим хандлером (`pf` на line ~74).

- [ ] **Step 2: Проверить импорт**

```bash
docker exec bot python -c "import handlers.pf_order; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Тесты**

```bash
docker exec api pytest tests/ -x -q
```

Expected: PASS.

- [ ] **Step 4: Коммит**

```bash
git add handlers/pf_order.py
git commit -m "$(cat <<'EOF'
chore(cleanup): drop yandex_pf & review_bonus stub handlers

Both were 'функция в разработке' placeholders. Their menu buttons
were already removed in commit b5917cd's predecessor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B7b: Выпил `handlers/seo.py` и связанных артефактов

**Files:**
- Delete: `handlers/seo.py` (153 строки)
- Modify: `handlers/__init__.py` — убрать `seo` из импорта
- Modify: `keyboards/inline_keyboards.py` — удалить `seo_boost_kb` (line 105+), `seo_months` (line 140+), `seo_order_confirm` (line 173+)
- Modify: `keyboards/users_menu.py` — удалить `seo_boost_kb` (line 410+), `seo_months` (line 445+), `seo_order_confirm` (line 478+)
- Modify: `utils/sqlite3.py:68-71` — удалить ключи `btn_seo_*`
- Modify: `design.py` — удалить `btn_seo_howto` константу

- [ ] **Step 1: Найти точные диапазоны функций seo в keyboards**

```bash
echo "=== inline_keyboards.py seo functions ===" && awk '/^def seo_boost_kb|^def seo_months|^def seo_order_confirm|^def [a-z]/' keyboards/inline_keyboards.py | head
grep -nE "^def " keyboards/inline_keyboards.py | sed -n '/seo/,/^def [^s]/p' | head -10
```

Используй этот список границ (line N до line следующего `def`) для аккуратного удаления.

- [ ] **Step 2: Удалить файл `handlers/seo.py`**

```bash
git rm handlers/seo.py
```

- [ ] **Step 3: Удалить `seo` из `handlers/__init__.py`**

Открыть `handlers/__init__.py`, найти:

```python
from . import (
    main_start,
    profile, promocodes, pf_order, reviews, seo, refill,
    admin_base, admin_promos, admin_users, admin_broadcast,
    admin_orders, admin_reviews, admin_settings, admin_funnel,
    support_web,
    connect,
    commands,  # commands.py has unhandled_callback LAST
)
```

Заменить на:

```python
from . import (
    main_start,
    profile, promocodes, pf_order, reviews, refill,
    admin_base, admin_promos, admin_users, admin_broadcast,
    admin_orders, admin_reviews, admin_settings, admin_funnel,
    support_web,
    connect,
    commands,  # commands.py has unhandled_callback LAST
)
```

(удалили `seo` из второй строки списка). `reviews` оставляем — выпил `reviews` отдельной задачей B7c.

- [ ] **Step 4: Удалить функции `seo_boost_kb`, `seo_months`, `seo_order_confirm` из `keyboards/inline_keyboards.py`**

Удалить три функции с их телами. Найти каждую по `def seo_boost_kb(`, `def seo_months(`, `def seo_order_confirm(` и удалить до следующего `def `-определения (не включая его).

После удаления — также удалить комментарий-заголовок над каждой функцией (если есть `#############... SEO BOOST ...#############` декоративный блок) — это маркер удалённой секции.

- [ ] **Step 5: То же самое для `keyboards/users_menu.py`** — удалить функции `seo_boost_kb`, `seo_months`, `seo_order_confirm`.

- [ ] **Step 6: Удалить ключи `btn_seo_*` в `utils/sqlite3.py:68-71`**

Найти:

```python
    "btn_seo_howto": "❓ Как работает",
    "btn_seo_why": "💡 Зачем нужно",
    "btn_seo_result": "📊 Результат",
    "btn_seo_order": "🚀 Заказать",
```

Удалить эти 4 строки.

- [ ] **Step 7: Удалить `btn_seo_howto` в `design.py:94`**

```bash
grep -n "btn_seo_howto\|seo_text\|seo_why\|seo_result" design.py
```

Удалить все попавшиеся строки.

- [ ] **Step 8: Грeп — убедиться что `seo` нигде в коде больше не упоминается (кроме служебных контекстов)**

```bash
grep -rnE "seo_boost|seo_howto|seo_why|seo_result|seo_order|seo_months|btn_seo" --include="*.py" .
```

Expected: пусто. Если что-то осталось — поправить.

```bash
grep -rn "handlers\.seo\|handlers/seo" --include="*.py" .
```

Expected: пусто.

- [ ] **Step 9: Тесты**

```bash
docker exec api pytest tests/ -x -q
```

Если падает `tests/unit/test_string_defaults.py` (он тестирует наличие ключей `btn_seo_howto`) — открыть этот тест, удалить упоминания `btn_seo_*` из списка ожидаемых ключей. Запустить ещё раз.

- [ ] **Step 10: Старт бота**

```bash
docker exec bot python -c "from handlers.main_start import *; print('bot imports OK')"
```

Expected: `bot imports OK`.

- [ ] **Step 11: Коммит**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore(cleanup): remove SEO-boost feature (dead since UI button removed)

- Delete handlers/seo.py (153 lines) and the seo_* keyboards
- Drop btn_seo_* settings keys from sqlite3 defaults and design.py
- Drop seo from handlers/__init__.py imports

The 'SEO-буст' menu button was already commented out; the handler was
registered but unreachable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B7c: Выпил `handlers/reviews.py` и связанных артефактов

**Files:**
- Delete: `handlers/reviews.py` (230 строк)
- Modify: `handlers/__init__.py` — убрать `reviews`
- Modify: `keyboards/inline_keyboards.py` — удалить `reviews_kb` (~line 1547), `reviews_count` (~line 1589), `reviews_man_kb` (~line 1655)
- Modify: `keyboards/users_menu.py` — удалить `reviews_kb` (~line 548), `reviews_count` (~line 590)
- Modify: `design.py` — удалить `what_tasks`, `new_refferal`, `reviews_menu`, `suppport_text`, `q1`, `q2`, `q3`, `q4`, `q1_text`, `q2_text`, `q3_text`, `q4_text`, `moremoney`, `nosuchorder`
- Modify: `utils/sqlite3.py` — удалить ключ `btn_reviews` если есть

- [ ] **Step 1: Удалить файл**

```bash
git rm handlers/reviews.py
```

- [ ] **Step 2: Убрать `reviews` из `handlers/__init__.py`**

Открыть, в строке `profile, promocodes, pf_order, reviews, refill,` удалить `reviews,`.

- [ ] **Step 3: Удалить `reviews_*` функции из `keyboards/inline_keyboards.py`**

```bash
grep -nE "^def reviews_" keyboards/inline_keyboards.py
```

Удалить три функции с их телами. Заодно удалить декоративные `#####... REVIEWS ...#####` блоки-заголовки если есть.

- [ ] **Step 4: То же для `keyboards/users_menu.py`** — удалить `reviews_kb` и `reviews_count`.

- [ ] **Step 5: Удалить строковые константы в `design.py`**

Грeп каждой константы, чтобы убедиться что её нигде не зовут (после удаления хандлера reviews):

```bash
for name in what_tasks new_refferal reviews_menu suppport_text q1 q2 q3 q4 q1_text q2_text q3_text q4_text moremoney nosuchorder; do
  count=$(grep -rn "\\b$name\\b" --include="*.py" . | grep -v "^design.py" | wc -l | tr -d ' ')
  echo "$name: $count callsites"
done
```

Удалить ТОЛЬКО те, у которых `0 callsites`. Если у какой-то > 0 — оставить (и в комментарии PR указать что не дропали).

**Внимание для `q1`–`q4`:** короткие имена — могут давать ложные срабатывания (в SQL-запросах, в локальных переменных). Если grep даёт результат — открыть каждый файл и проверить руками, что это реально `q1` константа из `design.py`, а не переменная.

**Внимание для `suppport_text`** (три «p»!): не путать с саппорт-чатом (`services/support.py`, `handlers/support_web.py`). Это старый FAQ-текст.

- [ ] **Step 6: Удалить `btn_reviews` из `utils/sqlite3.py`** (если есть)

```bash
grep -n "btn_reviews" utils/sqlite3.py
```

Если есть — удалить строку.

- [ ] **Step 7: Грeп — `reviews` не должно остаться вне саппорт-флоу и admin_reviews**

```bash
grep -rnE "callback_data=['\"]reviews['\"]|callback_data=['\"]reviews_" --include="*.py" .
```

Expected: пусто (admin_reviews живёт под другими callback_data — `admin_show_all_reviews` и т.п., их не трогаем).

- [ ] **Step 8: Тесты**

```bash
docker exec api pytest tests/ -x -q
```

Если упадёт `tests/unit/test_string_defaults.py` — удалить из его ожидаемого списка ключи `btn_reviews`, и константы которые мы удалили из `design.py`. Запустить ещё раз.

- [ ] **Step 9: Старт бота + api**

```bash
docker exec bot python -c "from handlers.main_start import *; print('bot imports OK')"
docker exec api python -c "from web.main import app; print('web imports OK')"
```

Expected: оба `OK`.

- [ ] **Step 10: Коммит**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore(cleanup): remove reviews feature (dead since UI button removed)

- Delete handlers/reviews.py (230 lines) and the reviews_* keyboards
- Drop design.py FAQ constants tied to the old reviews flow
  (what_tasks, q1-q4, q1_text-q4_text, moremoney, nosuchorder, etc.)
- Drop reviews from handlers/__init__.py imports

admin_reviews (handlers/admin_reviews.py) is kept — it manages real
review records and is reachable via admin_show_all_reviews callback.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B8: Чистка Cabinet placeholder-сервисов

**Files:**
- Modify: `web/static/components/Cabinet.jsx:5-12`

- [ ] **Step 1: В `web/static/components/Cabinet.jsx`** найти массив `SERVICES` (строки 5-12) и заменить:

Найти:

```js
const SERVICES = [
  { id: 'pf',      abbr: 'ПФ',  name: 'Авито ПФ',    desc: 'Просмотры, лайки, контакты для объявлений', price: 'от 6 ₽/ПФ', available: true,  route: 'order-pf' },
  { id: 'reviews', abbr: 'ОТЗ', name: 'Отзывы',       desc: 'Накрутка / удаление: Авито, ВК, Яндекс, 2ГИС, Google', price: 'по тарифу', available: true,  route: null },
  { id: 'ypf',     abbr: 'ЯПФ', name: 'Яндекс ПФ',   desc: 'Поведенческие факторы для Яндекс', price: null, badge: 'В разработке', available: false, route: null },
  { id: 'seo',     abbr: 'SEO', name: 'SEO-буст',     desc: 'Ссылочное продвижение и рост позиций', price: null, badge: 'Скоро', available: false, route: null },
  { id: 'copy',    abbr: 'КП',  name: 'Копирайтинг', desc: 'Тексты для объявлений и карточек', price: null, badge: 'Скоро', available: false, route: null },
  { id: 'smm',     abbr: 'SMM', name: 'SMM',          desc: 'Ведение соцсетей и создание контента', price: null, badge: 'Скоро', available: false, route: null },
];
```

Заменить на:

```js
const SERVICES = [
  { id: 'pf',      abbr: 'ПФ',  name: 'Авито ПФ',    desc: 'Просмотры, лайки, контакты для объявлений', price: 'от 6 ₽/ПФ', available: true,  route: 'order-new' },
];
```

(заменили `route: 'order-pf'` → `'order-new'`, потому что `'order-pf'` был дропнут в A5; удалили 5 placeholder-карточек)

- [ ] **Step 2: Проверить, что вёрстка каталога нормально рендерится с одной карточкой**

В `Cabinet.jsx` найти JSX, где итерируется `SERVICES` (обычно через `.map(...)`). Убедиться, что CSS-grid/flex-контейнер не «ломается» при единственной карточке (не растягивается на всю ширину, не сжимается).

Открыть `http://localhost:8000` в браузере, залогиниться (или подменить state, если нет тестового юзера), посмотреть Cabinet — проверить mobile (375px) и desktop (1280px) viewports (per memory rule).

Если карточка выглядит криво (например, растягивается из-за `grid-template-columns: 1fr 1fr 1fr`) — добавить inline-стиль или класс, чтобы при единственной карточке она шла обычной ширины. Если не критично — оставить как есть, но проверить визуально.

- [ ] **Step 3: Грeп — больше нет ссылок на 'order-pf' route**

```bash
grep -rn "'order-pf'\|\"order-pf\"" web/static/
```

Expected: пусто.

- [ ] **Step 4: Тесты**

```bash
docker exec api pytest tests/ -x -q
```

Expected: PASS (тесты, относящиеся к Cabinet, есть только косвенные — если что-то упадёт, посмотреть лог).

- [ ] **Step 5: Коммит**

```bash
git add web/static/components/Cabinet.jsx
git commit -m "$(cat <<'EOF'
chore(cleanup): strip Cabinet placeholder services (only PF works)

SERVICES had 5 unavailable placeholders (reviews, yandex pf, SEO,
copywriting, SMM) plus PF. The placeholders never linked anywhere
(route: null). Now only the working PF service is shown.

Also update route 'order-pf' → 'order-new' to match the alias removal
in A5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Финальная верификация (после всех задач)

- [ ] **Step 1: Полный прогон тестов**

```bash
docker exec api pytest tests/ -v
```

Expected: PASS, без skipped (если skipped — внимательно прочесть, не вызвано ли это удалением).

- [ ] **Step 2: Метрика результата**

```bash
echo "Python LOC (без tests):"
find . -name '*.py' -not -path './.*' -not -path '*/tests/*' -not -path '*/__pycache__/*' | xargs wc -l | tail -1
```

Сравнить с до-метрикой (можно посмотреть `git show HEAD~10:...` или просто отметить в PR-описании что удалили ~2000 строк Python + 646KB HTML.

- [ ] **Step 3: Старт обоих контейнеров с нуля**

```bash
docker compose down
docker compose up -d
docker compose logs --tail=50 api bot
```

Expected: ни `ImportError`, ни `KeyError`, бот регистрирует polling, api отвечает на `GET /api/config`.

- [ ] **Step 4: Ручная проверка LK на mobile + desktop** (per memory rule)

- Открыть `http://localhost:8000` в браузере
- Mobile (375px): главная (Cabinet или auth-redirect), форма заказа, история заказов, профиль
- Desktop (1280px): то же
- Залогиниться → попасть в Cabinet → увидеть **одну** ПФ-карточку
- Открыть форму заказа, ввести ссылку на тестовое объявление Авито (из памяти: `project_test_data.md`), дойти до момента yookassa redirect — НЕ оплачивать
- Зайти в `/orders`, `/profile`, `/notifications` — убедиться что навигация работает

- [ ] **Step 5: Push в origin (но не merge в main)**

```bash
git push origin claude/practical-brahmagupta-945fd9
```

PR создавать ТОЛЬКО по явному запросу пользователя.

---

## Wave C — отложенный legacy (НЕ исполнять в этом проходе)

Эти пункты вынесены в чек-лист в spec'е для следующего PR — после релиза `dev → main`. Они зависят от состояния прода и не должны делаться в текущем проходе:

- Удалить `scripts/migrate_*.py`
- Удалить legacy-drop старой таблицы в `utils/sqlite3.py:1023`
- Удалить fallback `dd.mm.yyyy` в `utils/dates.py:20-43` и `web/static/dates.js:56-57`
- Удалить legacy-комментарий в `web/admin_deps.py:3-5`

Полный чек-лист — в [spec'е, секция «Wave C»](../specs/2026-06-06-legacy-cleanup-design.md).
