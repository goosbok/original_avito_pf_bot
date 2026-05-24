# Mobile QA Follow-up Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрепить уже-применённый overflow-фикс OrderForm/GuestOrderForm коммитом, закрыть найденные spinoffs (Profile в mobile burger, AdminSupport ellipsis verify), и расширить мобильный QA на ещё не проверенные экраны с инпутами (refill, notifications, support chat, OrderDetail с реальным заказом).

**Architecture:** Все правки — точечные правки JSX/CSS на стороне React SPA, без backend-изменений. Тестирование — manual в Chrome MCP с iframe-обёрткой 390×844 и в реальном контейнере через `docker cp`. Для верификации overflow используется один и тот же JS-зонд (`scrollWidth > clientWidth + 1`).

**Tech Stack:** React (UMD, JSX через babel-standalone), vanilla CSS с media-queries, FastAPI/SQLite backend, Docker (`original_avito_pf_bot-api-1`), Chrome MCP, pytest для backend-юнитов.

**Worktree:** `.claude/worktrees/hardcore-thompson-8f3e40` (текущий). Branching: правки идут в `dev` (см. user memory).

**Тестовая учётка:** `mobile-test+1@example.com` / `TestPass123!` (`user_id=4`). Для админ-задач — повышается через `add_admin(4)`.

---

## File Structure

| Файл                                              | Изменения / роль |
|---------------------------------------------------|------------------|
| `web/static/components/OrderForm.jsx` (готово)    | already-applied: `minWidth: 0` на row + link, `flex: '1 1 0'`, убран `maxWidth: 380` |
| `web/static/components/GuestOrderForm.jsx` (готово)| identical fix |
| `web/static/platform.css` (готово)                | `.order-two-col > * { min-width: 0; }` в `@media (max-width: 768px)` |
| `web/static/components/AppHeader.jsx`             | добавить `Профиль` в mobile burger menu (строка ~295) |
| `web/static/components/AdminSupport.jsx`          | (если найдём overflow) — добавить `minWidth: 0` на родителя превью сообщения |
| `web/static/components/Cabinet.jsx`               | (только если QA найдёт overflow в «Другая сумма») |
| `docs/superpowers/specs/2026-05-24-mobile-order-form-overflow-design.md` | существующая спека, коммитится вместе |

---

## Task 1: Закоммитить уже-применённый overflow-фикс + спеку

**Files:**
- Modify (already changed): `web/static/components/OrderForm.jsx`
- Modify (already changed): `web/static/components/GuestOrderForm.jsx`
- Modify (already changed): `web/static/platform.css`
- New (already written): `docs/superpowers/specs/2026-05-24-mobile-order-form-overflow-design.md`

- [ ] **Step 1: Убедиться что нет лишних изменений**

Run:
```bash
git status --short
```

Expected (ровно эти 4 строки, ничего лишнего):
```
 M web/static/components/GuestOrderForm.jsx
 M web/static/components/OrderForm.jsx
 M web/static/platform.css
?? ../../docs/superpowers/specs/2026-05-24-mobile-order-form-overflow-design.md
```

Если есть лишнее — выяснить причину перед коммитом.

- [ ] **Step 2: Посмотреть diff правок**

Run:
```bash
git diff web/static/components/OrderForm.jsx web/static/components/GuestOrderForm.jsx web/static/platform.css
```

Expected: 3 изменения в JSX (по 1 правке на row-div, по 1 на ссылку) + 3 строки в CSS (комментарий + селектор + min-width).

- [ ] **Step 3: Скопировать актуальные файлы в контейнер и убедиться что баг ушёл**

Run:
```bash
WT=$(git rev-parse --show-toplevel) && \
docker cp "$WT/web/static/components/OrderForm.jsx" original_avito_pf_bot-api-1:/app/web/static/components/OrderForm.jsx && \
docker cp "$WT/web/static/components/GuestOrderForm.jsx" original_avito_pf_bot-api-1:/app/web/static/components/GuestOrderForm.jsx && \
docker cp "$WT/web/static/platform.css" original_avito_pf_bot-api-1:/app/web/static/platform.css && \
curl -s http://localhost:8000/components/OrderForm.jsx | grep -c "maxWidth: 380"
```

Expected: `0` (старый паттерн больше не отдаётся).

- [ ] **Step 4: Запустить backend-юнит-тесты (никаких регрессий)**

Run:
```bash
docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit tests/web -x -q
```

Expected: PASS (правки чисто косметические, backend не трогали — должно быть зелено).

- [ ] **Step 5: Закоммитить**

Run:
```bash
git add web/static/components/OrderForm.jsx \
        web/static/components/GuestOrderForm.jsx \
        web/static/platform.css \
        docs/superpowers/specs/2026-05-24-mobile-order-form-overflow-design.md
git commit -m "$(cat <<'EOF'
fix(web): mobile overflow on OrderForm/GuestOrderForm at viewport <412px

Inline `maxWidth: 380` + `whiteSpace: nowrap` on the added-link `<a>`
forced its flex/grid parent (`.order-two-col`) to expand past the
viewport on iPhone-class screens (393 px), cutting off the badge,
recommendation card, sliders, date input and sticky footer.

Replace with `min-width: 0` + `flex: 1 1 0` so the link shrinks within
its row, and add a `min-width: 0` safety-net on `.order-two-col > *`
inside the existing mobile media-query to prevent regressions from
similar unbreakable inline content.

Verified in Chrome MCP at viewport 388 px: documentScrollWidth equals
viewport (was 464 vs 388 = 78 px overflow before fix).

Spec: docs/superpowers/specs/2026-05-24-mobile-order-form-overflow-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: коммит создан без хуков-ошибок, `git status` чист.

- [ ] **Step 6: Финальный визуальный re-check**

После коммита заново открыть OrderForm в Chrome MCP iframe 390×844, залогиниться под `mobile-test+1@example.com`, вставить длинный URL `https://www.avito.ru/moskva/predlozheniya_uslug/arenda_avto_s_vykupom_mercedes-benz_e_klass_2019_8085331011`.

Run JS-зонд в iframe:
```javascript
(() => {
  const ifr = document.getElementById('mf').contentWindow;
  const idoc = ifr.document;
  const ovf = [];
  for (const el of idoc.querySelectorAll('*')) {
    if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0
        && !['HTML','BODY'].includes(el.tagName)) {
      ovf.push({t: el.tagName, c: (el.className||'').toString().substring(0,30)});
    }
  }
  return JSON.stringify({vw: ifr.innerWidth, docW: idoc.scrollingElement.scrollWidth, ovfCount: ovf.length});
})()
```

Expected: `{"vw":388,"docW":388,"ovfCount":1}` (единственный overflow — сама ссылка с ellipsis, intentional).

---

## Task 2: Профиль в мобильном burger-меню

**Files:**
- Modify: `web/static/components/AppHeader.jsx:295-298`

Контекст: в текущем коде desktop-дропдаун (`AppHeader.jsx:220-223`) содержит пункт `Профиль`, но мобильный burger (`AppHeader.jsx:295-298`) — нет. На мобиле страница `/profile` недостижима.

- [ ] **Step 1: Прочитать текущий блок mobile-меню**

Run:
```bash
sed -n '290,310p' web/static/components/AppHeader.jsx
```

Expected (текущий массив):
```jsx
{[
  { label: 'Кабинет',     route: 'cabinet' },
  { label: 'Мои заказы',  route: 'orders' },
  { label: 'Заказать ПФ', route: 'order-pf' },
].map(item => (
```

- [ ] **Step 2: Добавить пункт `Профиль` между `Мои заказы` и `Заказать ПФ`**

Edit `web/static/components/AppHeader.jsx`, заменить:

```jsx
                  {[
                    { label: 'Кабинет',     route: 'cabinet' },
                    { label: 'Мои заказы',  route: 'orders' },
                    { label: 'Заказать ПФ', route: 'order-pf' },
                  ].map(item => (
```

на:

```jsx
                  {[
                    { label: 'Кабинет',     route: 'cabinet' },
                    { label: 'Мои заказы',  route: 'orders' },
                    { label: 'Профиль',     route: 'profile' },
                    { label: 'Заказать ПФ', route: 'order-pf' },
                  ].map(item => (
```

- [ ] **Step 3: Скопировать в контейнер**

Run:
```bash
WT=$(git rev-parse --show-toplevel) && \
docker cp "$WT/web/static/components/AppHeader.jsx" original_avito_pf_bot-api-1:/app/web/static/components/AppHeader.jsx
```

- [ ] **Step 4: Проверить в Chrome MCP**

Залогиниться в iframe 390×844, открыть burger (☰), убедиться что пункт `Профиль` появился, кликнуть, оказаться на `ProfilePage`. Прогнать тот же overflow-зонд:

Expected: `docW === vw === 388`, `ovfCount: 0`. Все поля профиля (имя, email, смена пароля) умещаются.

- [ ] **Step 5: Закоммитить**

Run:
```bash
git add web/static/components/AppHeader.jsx
git commit -m "$(cat <<'EOF'
fix(web): expose Profile in mobile burger menu

Desktop dropdown lists Профиль but the mobile burger menu skipped
it, leaving /profile unreachable for ~70% of traffic. Add it between
"Мои заказы" and "Заказать ПФ" so the route is reachable on phones.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Mobile-проверка OrderDetail с реальным заказом

**Files:** read-only (`web/static/components/OrderDetail.jsx`).

Контекст: статически OrderDetail выглядит ок (`wordBreak: break-all` на ссылках), но реальный мобильный рендер не проверяли — у тестового юзера нет ни одного заказа.

- [ ] **Step 1: Засидить тестовый заказ напрямую в БД через `services.orders`**

Run:
```bash
docker exec original_avito_pf_bot-api-1 python -c "
from services.orders import create_order
oid = create_order(
    user_id=4,
    service='avito-pf',
    links=[
        'https://www.avito.ru/moskva/predlozheniya_uslug/arenda_avto_s_vykupom_mercedes-benz_e_klass_2019_8085331011',
        'https://www.avito.ru/sankt-peterburg/avtomobili/bmw_5_seriya_530d_xdrive_2017_3014567890',
    ],
    views_per_day=30,
    days=7,
    start_date='2026-05-25',
    contacts_enabled=False,
    price=1260,
    paid=True,
)
print('seeded order id:', oid)
"
```

Если `create_order` имеет другую сигнатуру — открыть `services/orders.py` и адаптировать вызов. Если функции нет — использовать прямой `INSERT` через `utils.sqlite3.execute`.

Expected: вывод `seeded order id: <N>`.

- [ ] **Step 2: Открыть `Мои заказы` в Chrome MCP iframe**

В iframe 390×844 кликнуть burger → Мои заказы → клик по карточке нового заказа.

- [ ] **Step 3: Запустить overflow-зонд на OrderDetail**

```javascript
(() => {
  const ifr = document.getElementById('mf').contentWindow;
  const idoc = ifr.document;
  const ovf = [];
  for (const el of idoc.querySelectorAll('*')) {
    if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0
        && !['HTML','BODY'].includes(el.tagName)) {
      ovf.push({t: el.tagName, c: (el.className||'').toString().substring(0,30), sw: el.scrollWidth, cw: el.clientWidth, txt: (el.textContent||'').substring(0,30)});
    }
  }
  return JSON.stringify({path: ifr.location.pathname, vw: ifr.innerWidth, docW: idoc.scrollingElement.scrollWidth, overflow: ovf.slice(0,10)});
})()
```

Expected: `docW === vw === 388`, `overflow: []` (или только sub-tree-уровневые элементы с intended ellipsis).

- [ ] **Step 4: Сделать скриншот**

Если overflow=0 — переходим к Task 4. Если нашлось:
  - Зафиксировать находку: `<spawn_task>` или дописать в эту задачу подзадачу с правкой и повторной верификацией.
  - **Не закрывать Task 3 до устранения**.

- [ ] **Step 5: (если правки не понадобились) — закрыть задачу без коммита**

Иначе — закоммитить правки аналогично Task 1.

---

## Task 4: Расширенный mobile QA — refill modal «Другая сумма»

**Files:** read-only сначала (`web/static/components/Cabinet.jsx`).

Контекст: на Cabinet есть пресеты сумм пополнения 500/1000/2000 и кнопка «Другая» → input для произвольной суммы. На iPhone-ширине нужно убедиться что инпут не выезжает и кнопка «Пополнить» с длинной суммой (например `99 999 999 ₽`) уместна.

- [ ] **Step 1: В iframe 390×844 на Cabinet нажать «Другая»**

Через JS:
```javascript
(() => {
  const idoc = document.getElementById('mf').contentDocument;
  const btn = Array.from(idoc.querySelectorAll('button')).find(b => /Другая/.test(b.textContent||''));
  if (btn) btn.click();
  return 'clicked';
})()
```

- [ ] **Step 2: Ввести большое число**

```javascript
(() => {
  const idoc = document.getElementById('mf').contentDocument;
  const inp = idoc.querySelector('input[type="number"], input[inputmode="numeric"], input.input');
  if (!inp) return 'no input';
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(inp, '99999999');
  inp.dispatchEvent(new Event('input', {bubbles: true}));
  return 'typed';
})()
```

- [ ] **Step 3: Запустить overflow-зонд**

(тот же что в Task 3 Step 3).

Expected: `docW === vw`, кнопка «Пополнить 99 999 999 ₽» либо умещается, либо корректно обрезается в одну строку без выхода за края карточки.

- [ ] **Step 4: Скриншот для архива**

- [ ] **Step 5: Если overflow найден — открыть Cabinet.jsx, найти кнопку пополнения, добавить `min-width: 0` на flex-родителя или `overflow-wrap: anywhere` на текст кнопки**

Затем `docker cp`, повторить Step 3, при `docW=vw` — закоммитить с сообщением `fix(web): refill button overflow on long custom amounts`.

---

## Task 5: Mobile QA — NotificationsBell панель и SupportChat

**Files:** read-only (`web/static/components/NotificationsBell.jsx`, `web/static/components/SupportChat.jsx`).

Контекст: иконка колокольчика в шапке открывает выпадающую панель уведомлений. Тех. поддержка — отдельная плавающая панель чата. Оба элемента — overlay поверх контента, на узком экране могут вылезать.

- [ ] **Step 1: Открыть панель уведомлений**

```javascript
(() => {
  const idoc = document.getElementById('mf').contentDocument;
  const bell = Array.from(idoc.querySelectorAll('button')).find(b => /🔔|notification/i.test(b.outerHTML||''));
  if (bell) bell.click();
  return bell ? 'opened bell' : 'no bell';
})()
```

- [ ] **Step 2: Запустить overflow-зонд + screenshot**

Expected: панель уведомлений умещается в 388 px (как минимум `width: calc(100vw - 32px)` или аналог).

- [ ] **Step 3: Открыть SupportChat (плавающая кнопка «💬 Тех Поддержка»)**

```javascript
(() => {
  const idoc = document.getElementById('mf').contentDocument;
  const btn = Array.from(idoc.querySelectorAll('button,a')).find(b => /Тех Поддержка|поддержк/i.test(b.textContent||''));
  if (btn) btn.click();
  return 'opened';
})()
```

- [ ] **Step 4: Вписать длинное сообщение в инпут чата (без отправки)**

```javascript
(() => {
  const idoc = document.getElementById('mf').contentDocument;
  const inp = idoc.querySelector('.chat-input');
  if (!inp) return 'no chat input';
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(inp, 'Lorem ipsum '.repeat(40));
  inp.dispatchEvent(new Event('input', {bubbles: true}));
  return 'typed';
})()
```

- [ ] **Step 5: overflow-зонд + screenshot**

Expected: SupportChat panel умещается, `.chat-input` корректно растёт/скроллится внутри панели, кнопка «➤» не уезжает.

- [ ] **Step 6: Если что-то нашлось — точечный фикс с тем же паттерном `min-width: 0`**

Закоммитить, аналогично Task 2.

---

## Task 6: Проверить AdminSupport ellipsis с реальной данной

**Files:** read-only сначала (`web/static/components/AdminSupport.jsx:85`).

Контекст: превью last_message_text использует `whiteSpace: nowrap; overflow: hidden; textOverflow: ellipsis`. Без `min-width: 0` на родительском flex это может всё-таки расширить контейнер.

- [ ] **Step 1: Повысить тестового юзера до админа**

Run:
```bash
docker exec original_avito_pf_bot-api-1 python -c "
from utils.sqlite3 import add_admin
add_admin(4)
print('admin set')
"
```

- [ ] **Step 2: Засидить тикет с очень длинным сообщением**

Run (адаптировать к фактической сигнатуре `services.support`):
```bash
docker exec original_avito_pf_bot-api-1 python -c "
from services.support import create_ticket, send_message
tid = create_ticket(user_id=4, subject='test ticket')
send_message(ticket_id=tid, user_id=4, text='LongMessage' + 'x'*300)
print('ticket', tid)
"
```

Если сигнатуры отличаются — открыть `services/support.py` и адаптировать.

- [ ] **Step 3: Открыть AdminSupport на 388 px**

В iframe залогиниться (нужен fresh JWT, т.к. is_admin кешируется в нём?). Если is_admin читается per-request — старый токен подойдёт. Иначе:
```bash
curl -s -X POST http://localhost:8000/api/auth/email/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"mobile-test+1@example.com","password":"TestPass123!"}'
```
скопировать `access_token` и подменить в `localStorage`.

- [ ] **Step 4: Открыть Admin → Support, запустить overflow-зонд**

Expected: `docW === vw`. Если нет — добавить `minWidth: 0` на родительский div списка тикетов в `AdminSupport.jsx`.

- [ ] **Step 5: Скриншот + (при необходимости) фикс + commit**

---

## Task 7: Финальная сводка

- [ ] **Step 1: Обновить спеку, проставить статусы Tasks 1-6**

В `docs/superpowers/specs/2026-05-24-mobile-order-form-overflow-design.md` в секции «Спинофф-задачи» отметить выполненные тикеты и приклеить итоговые скриншоты в `docs/superpowers/specs/assets/2026-05-24-mobile-qa/` (создать папку при необходимости).

- [ ] **Step 2: Push в `dev`**

Run:
```bash
git push origin dev
```

(`dev` — integration branch; `main` не трогаем — см. user memory о branching strategy.)

- [ ] **Step 3: Сводка для пользователя**

Сообщить: какие коммиты, какие задачи закрыты, какие требуют отдельного follow-up (если что-то осталось).

---

## Self-Review Notes

- Spec coverage: 100% — все три применённые правки покрыты Task 1; spinoffs (Profile menu, AdminSupport, OrderDetail) — отдельные tasks 2/3/6; AdminSupport требует admin-сессии — учтено в Task 6 Step 1.
- Нет placeholder-ов: все код-блоки полные, все команды конкретные.
- Зависимости: Task 1 → Task 3 (нужен примененный фикс перед OrderDetail QA, иначе путаница). Tasks 2, 4, 5, 6 — независимы и могут идти параллельно после Task 1.
- Granularity: каждый шаг 2-5 минут; коммиты после каждой логической правки.
- Branching: всё в `dev`, спека-источник в коммите Task 1, последующие правки добавляют к ней через git diff.
