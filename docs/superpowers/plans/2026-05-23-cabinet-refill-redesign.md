# Cabinet Refill Card Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести карточку «Баланс» в кабинете на новый дизайн: implicit consent (без чекбоксов), 3 чипа пресетов + чип «Другая» с replace-режимом инпута, кнопка с суммой в тексте.

**Architecture:** Изменения только во фронте — один JSX файл (`Cabinet.jsx`) и CSS (`platform.css`). Бэк не трогаем: фронт всегда шлёт `agreed_privacy: true, agreed_offer: true` в `/api/refill`. Компонент `LegalConsent` сохраняется для гостевого флоу. Старая разметка карточки с inline-стилями заменяется на CSS-классы.

**Tech Stack:** React 18 через Babel-in-browser, vanilla CSS (`web/static/platform.css`), без сборки. Тестов на UI в репо нет — верификация ручная через запуск дев-сервера и осмотр в браузере.

**Reference spec:** [docs/superpowers/specs/2026-05-23-cabinet-refill-redesign-design.md](../specs/2026-05-23-cabinet-refill-redesign-design.md)

---

## File Structure

**Modified:**
- `web/static/components/Cabinet.jsx` — переписать секцию `cabinet-balance-card` (≈ строки 31–37 для state, 111–195 для JSX). Удалить `refillAgreedPrivacy`, `refillAgreedOffer`, `refillConsentOk`. Добавить `customMode` state. Упростить `handleRefill`. Заменить inline-styles на классы.
- `web/static/platform.css` — добавить классы `.balance-cta`, `.balance-fineprint`, `.balance-custom-row`, `.balance-back-btn` (~ после строки 382, в секции «Balance»).

**Unchanged:**
- `web/static/components/LegalConsent.jsx` — используется `GuestOrderForm`.
- `web/routers/refill.py`, `web/schemas.py`, БД — вариант A, бэк требует флаги, фронт всегда отдаёт `true`.
- `tests/web/test_routers_refill.py` — не трогаем, тесты бэка остаются.

---

## Task 1: Add CSS classes (additive, no breakage)

**Files:**
- Modify: `web/static/platform.css` (после блока `/* Balance */`, после строки 382)

CSS добавляется до изменений в JSX — после этой задачи карточка должна выглядеть так же, как сейчас (новые классы пока не используются).

- [ ] **Step 1: Open `web/static/platform.css` and locate the Balance section**

Найти блок начинающийся с `/* Balance */` (строка ~370). Конец блока — пустая строка перед `/* ===== SUPPORT CHAT WIDGET ===== */`.

- [ ] **Step 2: Append new classes after `.balance-status--success`**

Вставить блок ПОСЛЕ строки `.balance-status--success { ... }` и ПЕРЕД `/* ===== SUPPORT CHAT WIDGET ===== */`:

```css
.balance-cta {
  width: 100%;
  margin-top: 12px;
}
.balance-fineprint {
  font-size: 0.7rem;
  color: var(--text-3);
  margin-top: 8px;
  line-height: 1.4;
  text-align: center;
}
.balance-fineprint a {
  color: var(--text-2);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.balance-fineprint a:hover { color: var(--primary); }
.balance-custom-row {
  display: flex;
  gap: 6px;
  align-items: stretch;
  margin-bottom: 0;
}
.balance-back-btn {
  flex: 0 0 auto;
  width: 32px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-2);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  color: var(--text-2);
  cursor: pointer;
  font-size: 1rem;
  transition: border-color 0.15s, color 0.15s;
}
.balance-back-btn:hover { border-color: var(--primary); color: var(--primary); }
```

- [ ] **Step 3: Verify CSS file parses**

Run: `python -c "open('web/static/platform.css').read()"` (просто чтение, парсинг CSS-валидатором не нужен — браузер простит).

Лучше визуально открыть файл и убедиться что фигурные скобки сбалансированы.

- [ ] **Step 4: Commit**

```bash
git add web/static/platform.css
git commit -m "style(web): add CSS classes for refill card redesign"
```

---

## Task 2: Refactor Cabinet.jsx — state and submit logic

**Files:**
- Modify: `web/static/components/Cabinet.jsx` (строки 14, 31–37, 50–71)

Чистим state и логику до того как менять JSX. После этой задачи карточка временно будет рендериться через старую разметку (со старыми отсылками к удалённым state) — поэтому **Task 2 и Task 3 коммитятся одним коммитом**. Между шагами не пушим.

- [ ] **Step 1: Update PRESETS constant**

В `Cabinet.jsx` строка 14, заменить:

```js
const PRESETS = [500, 1000, 2000, 5000];
```

на:

```js
const PRESETS = [500, 1000, 2000];
```

- [ ] **Step 2: Replace state declarations**

Найти блок (строки 31–37):

```js
  const [refillAmount, setRefillAmount] = useCabinetState(1000);
  const [refillStatus, setRefillStatus] = useCabinetState(null);
  const [refillPaymentId, setRefillPaymentId] = useCabinetState(null);
  const [refillAgreedPrivacy, setRefillAgreedPrivacy] = useCabinetState(false);
  const [refillAgreedOffer, setRefillAgreedOffer] = useCabinetState(false);
  const [refillErrorMessage, setRefillErrorMessage] = useCabinetState(null);
  const refillConsentOk = refillAgreedPrivacy && refillAgreedOffer;
```

Заменить на:

```js
  const [refillAmount, setRefillAmount] = useCabinetState(1000);
  const [customMode, setCustomMode] = useCabinetState(false);
  const [refillStatus, setRefillStatus] = useCabinetState(null);
  const [refillPaymentId, setRefillPaymentId] = useCabinetState(null);
  const [refillErrorMessage, setRefillErrorMessage] = useCabinetState(null);
  const refillBusy = refillStatus === 'pending' || refillStatus === 'polling';
  const refillAmountValid = Number(refillAmount) >= 100;
```

- [ ] **Step 3: Simplify handleRefill**

Заменить функцию `handleRefill` (строки 50–71) на:

```js
  const handleRefill = async () => {
    if (!refillAmountValid) return;
    setRefillErrorMessage(null);
    setRefillStatus('pending');
    try {
      const data = await api.post('/api/refill', {
        amount: Number(refillAmount),
        agreed_privacy: true,
        agreed_offer: true,
      });
      setRefillPaymentId(data.payment_id);
      window.open(data.payment_url, '_blank');
      setRefillStatus('polling');
    } catch (e) {
      if (e.status >= 400 && e.status < 500 && e.message) {
        setRefillErrorMessage(e.message);
      }
      setRefillStatus('error');
    }
  };
```

- [ ] **Step 4: Add chip-select and back-to-presets helpers**

Прямо после `handleRefill` добавить:

```js
  const selectPreset = (p) => {
    setRefillAmount(p);
    setCustomMode(false);
  };

  const enterCustomMode = () => {
    setCustomMode(true);
  };

  const exitCustomMode = () => {
    setCustomMode(false);
    setRefillAmount(1000);
  };
```

Файл сейчас не работает (JSX всё ещё ссылается на удалённые state). Это нормально — фиксим в Task 3 и коммитим вместе.

---

## Task 3: Rewrite Cabinet.jsx — balance card JSX

**Files:**
- Modify: `web/static/components/Cabinet.jsx` (строки ≈111–195, секция `.cabinet-balance-card`)

- [ ] **Step 1: Replace the entire balance card JSX**

Найти открывающий `<div className="card cabinet-balance-card" ...>` (строка 111) и закрывающий `</div>` секции (строка 195 — последний `</div>` перед `</div>` строки 196 `</div>` блока `.cabinet-top-row`).

Полностью заменить содержимое (всю карточку от `<div className="card cabinet-balance-card"` до её закрывающего `</div>`) на:

```jsx
            <div className="card cabinet-balance-card" style={{ padding: '16px 20px', minWidth: 260, flex: '0 0 auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Баланс</span>
                <span style={{ fontSize: '1.375rem', fontWeight: 800, color: 'var(--primary)' }}>{balance.toLocaleString('ru-RU')} ₽</span>
              </div>

              {!customMode ? (
                <div className="balance-presets">
                  {PRESETS.map(p => (
                    <button
                      key={p}
                      className={`balance-preset${refillAmount === p && !customMode ? ' active' : ''}`}
                      style={{ flex: 1 }}
                      onClick={() => selectPreset(p)}
                      disabled={refillBusy}
                    >
                      {p.toLocaleString('ru-RU')}
                    </button>
                  ))}
                  <button
                    className="balance-preset"
                    style={{ flex: 1 }}
                    onClick={enterCustomMode}
                    disabled={refillBusy}
                  >
                    Другая
                  </button>
                </div>
              ) : (
                <div className="balance-custom-row">
                  <button
                    className="balance-back-btn"
                    onClick={exitCustomMode}
                    disabled={refillBusy}
                    aria-label="К пресетам"
                    title="К пресетам"
                  >
                    ←
                  </button>
                  <input
                    className="input"
                    type="number"
                    min={100}
                    autoFocus
                    value={refillAmount}
                    onChange={e => setRefillAmount(Number(e.target.value))}
                    placeholder="Сумма от 100 ₽"
                    disabled={refillBusy}
                    style={{ flex: 1, padding: '8px 10px', fontSize: '0.875rem' }}
                  />
                </div>
              )}

              <button
                className="btn btn--primary balance-cta"
                onClick={handleRefill}
                disabled={refillBusy || !refillAmountValid}
              >
                {refillStatus === 'pending'
                  ? '...'
                  : refillAmountValid
                    ? `Пополнить ${Number(refillAmount).toLocaleString('ru-RU')} ₽`
                    : 'Введите сумму от 100 ₽'}
              </button>

              {!refillStatus && (
                <div className="balance-fineprint">
                  Нажимая «Пополнить», вы соглашаетесь с{' '}
                  <a href="/privacy" target="_blank" rel="noopener noreferrer">Политикой конфиденциальности</a>
                  {' '}и{' '}
                  <a href="/offer" target="_blank" rel="noopener noreferrer">Публичной офертой</a>
                </div>
              )}

              {refillStatus === 'polling' && (
                <div className="balance-status balance-status--pending" style={{ marginTop: 8, padding: '8px 12px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>⏳ Ожидаем оплаты</span>
                  <button
                    className="btn btn--ghost btn--sm"
                    onClick={checkRefillStatus}
                    style={{ fontSize: '0.75rem', padding: '3px 8px' }}
                  >Проверить</button>
                </div>
              )}
              {refillStatus === 'success' && (
                <div className="balance-status balance-status--success" style={{ marginTop: 8, padding: '8px 12px', fontSize: '0.8rem' }}>
                  ✅ {refillAmount.toLocaleString('ru-RU')} ₽ зачислено!
                </div>
              )}
              {refillStatus === 'error' && (
                <div
                  className="balance-status"
                  style={{
                    marginTop: 8, padding: '8px 12px', fontSize: '0.8rem',
                    background: 'var(--status-cancel-bg)', color: 'var(--status-cancel-text)',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
                  }}
                >
                  <span>❌ {refillErrorMessage || 'Произошла ошибка'}</span>
                  {!refillErrorMessage && (
                    <button
                      className="btn btn--sm"
                      onClick={openSupportForRefill}
                      style={{
                        fontSize: '0.7rem', padding: '3px 10px', whiteSpace: 'nowrap',
                        background: 'var(--status-cancel-text)', color: '#fff', borderColor: 'transparent',
                      }}
                    >Пополнить через поддержку</button>
                  )}
                </div>
              )}
            </div>
```

- [ ] **Step 2: Verify file syntactically valid**

Run: `node -e "const fs=require('fs');const c=fs.readFileSync('web/static/components/Cabinet.jsx','utf8');console.log('len:',c.length)"`

(Не запускаем babel — простая проверка что файл читается.)

Если есть `node` — лучше через babel-cli, но в репо нет node-тулинга. Достаточно открыть страницу `/cabinet` в браузере в Task 4 и убедиться что нет ошибок в консоли.

- [ ] **Step 3: Commit Task 2 + Task 3 together**

```bash
git add web/static/components/Cabinet.jsx
git commit -m "feat(web): redesign refill card — implicit consent, presets + Другая, amount in CTA"
```

---

## Task 4: Manual smoke test

**Files:** None — verification only.

- [ ] **Step 1: Start dev environment**

Согласно [memory: docker_tests](/Users/belikov/.claude/projects/-Users-belikov-Documents-pets-bots-telegram-original-avito-pf-bot/memory/feedback_docker_tests.md) проект работает в Docker. Проверить что контейнер веба запущен:

```bash
docker ps | grep -i web
```

Если не запущен — поднять (команда зависит от docker-compose файла проекта):

```bash
docker compose up -d web
```

- [ ] **Step 2: Open `/cabinet` in browser**

Открыть страницу личного кабинета. Авторизоваться если нужно.

- [ ] **Step 3: Verify resting state**

Ожидаемое:
- Видны 4 чипа в одной строке: `500`, `1 000`, `2 000`, `Другая`
- Чип `1 000` подсвечен (активный)
- Под чипами кнопка **«Пополнить 1 000 ₽»** — синяя, активная (не disabled)
- Под кнопкой мелкий серый текст: «Нажимая «Пополнить», вы соглашаетесь с Политикой конфиденциальности и Публичной офертой» — две ссылки кликабельны
- НЕТ чекбоксов
- НЕТ подсказки «Для оплаты примите оба условия выше»

- [ ] **Step 4: Verify preset selection**

- Кликнуть `500` → подсветка перескочила, кнопка `Пополнить 500 ₽`
- Кликнуть `2 000` → подсветка на `2 000`, кнопка `Пополнить 2 000 ₽`

- [ ] **Step 5: Verify custom mode**

- Кликнуть `Другая` → чипы исчезли, появилась стрелка `←` + инпут с фокусом
- Инпут содержит `2000` (последнее значение)
- Кнопка: `Пополнить 2 000 ₽`, активна
- Очистить инпут → кнопка disabled, текст «Введите сумму от 100 ₽»
- Ввести `50` → кнопка по-прежнему disabled (< 100)
- Ввести `250` → кнопка `Пополнить 250 ₽`, активна
- Ввести `7500` → кнопка `Пополнить 7 500 ₽`, активна

- [ ] **Step 6: Verify back navigation**

- Кликнуть `←` → инпут исчез, вернулись чипы, подсвечен `1 000`, кнопка `Пополнить 1 000 ₽`

- [ ] **Step 7: Verify submit**

- Открыть DevTools → Network
- Кликнуть `Пополнить 1 000 ₽`
- В запросе на `POST /api/refill`: body содержит `{"amount": 1000, "agreed_privacy": true, "agreed_offer": true}`
- Открылась вкладка YooKassa (или статус `pending`/`polling` — зависит от тестового окружения)

- [ ] **Step 8: Verify status states**

Если есть возможность — проверить, что под кнопкой появляются блоки:
- `polling` → ⏳ + кнопка «Проверить»
- `success` → ✅ + сумма
- `error` → ❌ + сообщение или кнопка «Пополнить через поддержку»

В этих состояниях fine-print под кнопкой скрыт.

- [ ] **Step 9: Verify mobile layout (≤ 480px)**

- Открыть DevTools, переключить на мобильное представление (iPhone SE: 375px)
- Чипы умещаются (4 штуки в строку или wrap — оба варианта приемлемы при сохранении читаемости)
- Кнопка `balance-cta` full-width
- Fine-print центрирован, переносится на 2 строки

- [ ] **Step 10: Verify dark theme**

- Переключить тему через toggle в хедере (`☀/🌙`)
- Карточка читается в обоих режимах
- Fine-print имеет достаточный контраст (не растворяется в фоне)

- [ ] **Step 11: Verify backend tests still pass**

Бэк тесты на refill не должны зависеть от фронта, но проверим:

```bash
docker exec <web-container> pytest tests/web/test_routers_refill.py tests/unit/test_refill.py -v
```

Все тесты должны зелёные — бэк не менялся.

- [ ] **Step 12: Mark Task 4 done**

Если все шаги выше прошли — задача выполнена. Если что-то сломалось — записать в Open Issues ниже и не мерджить.

---

## Open Issues

(Заполнять при возникновении проблем в Task 4)

- (нет)

---

## Out of Scope

- Бэк-вариант B (удаление `agreed_privacy/agreed_offer` из схемы) — обсуждался в спеке как опция, но решили не делать.
- Изменения в `GuestOrderForm` — там legal consent остаётся.
- Изменения в значениях пресетов (500/1000/2000) — оставляем как было.
- Анимации перехода чипы↔инпут — пока без transitions, при необходимости можно добавить отдельной задачей.

---

## Self-Review Notes

Сделан skim:

**Spec coverage:**
- Resting state с чипами + «Другая» + CTA с суммой + fine-print → Task 3 Step 1 (JSX блок).
- Active «Другая» state → Task 3 Step 1 (ветка `customMode`).
- Возврат к пресетам со сбросом на 1000 → Task 2 Step 4 (`exitCustomMode`).
- Состояния pending/polling/success/error без изменений → Task 3 Step 1 (сохранены `.balance-status` блоки).
- `agreed_privacy: true, agreed_offer: true` всегда → Task 2 Step 3 (новый `handleRefill`).
- CSS классы `.balance-cta`, `.balance-fineprint`, `.balance-custom-row`, `.balance-back-btn` → Task 1.
- `LegalConsent` не трогаем → подтверждено в File Structure.

**Placeholder scan:** нет `TBD/TODO`, все коды JSX/CSS/JS полные. Каждый шаг имеет либо код, либо команду, либо чёткую проверку.

**Type consistency:** `customMode`, `refillBusy`, `refillAmountValid` определены в Task 2 Step 2 и используются в Task 3. `selectPreset`, `enterCustomMode`, `exitCustomMode` определены в Task 2 Step 4 и используются в Task 3. Имена совпадают.

**Ambiguity:** В Task 3 Step 1 указан диапазон строк ≈111–195 для замены. Точный диапазон может сдвинуться после Task 2. Engineer должен ориентироваться на содержимое (`<div className="card cabinet-balance-card"` … закрывающий `</div>` перед `</div>` блока `.cabinet-top-row`), а не на номера строк.
