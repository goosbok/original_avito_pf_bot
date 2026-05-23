# Cabinet Refill Card — Redesign

**Date:** 2026-05-23
**Scope:** UI/UX-редизайн карточки «Баланс» в кабинете (`Cabinet.jsx`). Бэкенд не меняем.

## Motivation

Текущая карточка перегружена: лейбл + сумма + 3 чипа + 2 строки legal-чекбоксов + инпут + кнопка + строка-подсказка = 8 визуальных рядов в узкой карточке 260px. Чекбоксы — нативные `<input type="checkbox">` со стилизацией только через `accentColor`, что выбивается из остального UI (где используются собственные стилизованные компоненты `.card`, `.btn`, `.balance-preset`). Disabled-кнопка как стартовое состояние читается как «сломанный CTA». Чипы пресетов и числовой инпут дублируют одну и ту же affordance — выбор суммы.

## Goals

- Сократить высоту resting-state карточки до 3–4 визуальных рядов.
- Убрать чекбоксы (legal consent) из refill-флоу — перейти на implicit consent через текст под кнопкой.
- Устранить дублирование «чипы + инпут»: использовать прогрессивное раскрытие через четвёртый чип «Другая».
- Не менять бэк, не трогать `LegalConsent` для гостевого флоу.

## Non-Goals

- Не меняем `GuestOrderForm` (там legal-чекбоксы остаются — это разовая регистрация-эквивалент, юридически другой контекст).
- Не меняем дефолтную сумму пополнения (1000 ₽) и пресеты (500/1000/2000).
- Не меняем поведение статусов pending/polling/success/error — визуально они в порядке.
- Не трогаем `/api/refill`, схему БД, миграции.

## Design

### Состояние 1 — Resting (пресеты)

```
┌───────────────────────────────┐
│ БАЛАНС              4 680 ₽   │
│                               │
│ [500] [1 000] [2 000] [Другая]│
│                               │
│ [   Пополнить 1 000 ₽    ]    │
│                               │
│ Нажимая, вы соглашаетесь с    │
│ Политикой и Офертой           │
└───────────────────────────────┘
```

- Чип `1 000` подсвечен (дефолт).
- Кнопка **«Пополнить N ₽»** — текст содержит выбранную сумму. Активна с самого начала, не disabled.
- Под кнопкой fine-print текст (~11px, `var(--text-3)`, centered) с inline-линками на `/privacy` и `/offer`. Текст: «Нажимая «Пополнить», вы соглашаетесь с Политикой конфиденциальности и Публичной офертой». Может переноситься на 2 строки на узких экранах.

### Состояние 2 — Active «Другая» (кастомная сумма)

```
┌───────────────────────────────┐
│ БАЛАНС              4 680 ₽   │
│                               │
│ [←]  [   Сумма от 100 ₽   ]   │
│                               │
│ [   Пополнить 5 000 ₽    ]    │
│                               │
│ Нажимая, вы соглашаетесь с    │
│ Политикой и Офертой           │
└───────────────────────────────┘
```

- Чипы заменяются (replace, не expand) на стрелку-возврат + `<input type="number">`.
- Инпут получает автофокус.
- Кнопка возврата `←` сбрасывает выбор обратно на дефолтный пресет (`1 000`) и возвращает чипы.
- Если введённая сумма < 100 или пусто → кнопка disabled, текст кнопки **«Введите сумму от 100 ₽»**.

### Состояния процесса оплаты

Без изменений — остаются текущие `.balance-status` блоки под кнопкой:
- `pending` → крутилка в кнопке (`...`).
- `polling` → блок «⏳ Ожидаем оплаты» + кнопка «Проверить».
- `success` → блок «✅ N ₽ зачислено!».
- `error` → блок с сообщением + опциональная кнопка «Пополнить через поддержку».

Fine-print под кнопкой при активных pending/polling/success/error можно скрывать (он уже не нужен — действие совершено).

## Component State

Новая структура локального state в `Cabinet.jsx`:

```js
const [refillAmount, setRefillAmount] = useState(1000);
const [customMode, setCustomMode] = useState(false);  // NEW
const [refillStatus, setRefillStatus] = useState(null);
const [refillPaymentId, setRefillPaymentId] = useState(null);
const [refillErrorMessage, setRefillErrorMessage] = useState(null);

// УДАЛЕНО:
// refillAgreedPrivacy, refillAgreedOffer, refillConsentOk
```

### Логика

- Клик по чипу пресета: `setRefillAmount(p); setCustomMode(false)`.
- Клик по чипу `Другая`: `setCustomMode(true)`. Не сбрасываем `refillAmount` — пользователь видит свой последний выбор в инпуте, может править.
- Клик по `←` в custom-mode: `setCustomMode(false); setRefillAmount(1000)`.
- Кнопка disabled только если: `refillStatus === 'pending'` ИЛИ `refillStatus === 'polling'` ИЛИ (`customMode && (!refillAmount || refillAmount < 100)`).

### Сабмит

`handleRefill` шлёт в `/api/refill` `agreed_privacy: true, agreed_offer: true` всегда. Это **вариант A** — бэк не меняем, факт нажатия кнопки = акцепт. Поля `agreed_privacy`/`agreed_offer` в схеме `RefillRequest` остаются required, фронт всегда отдаёт `true`.

## CSS

Новые/обновлённые классы в `platform.css`:

```css
.balance-presets {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}
.balance-presets .balance-preset {
  flex: 1;
}
.balance-custom-row {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  align-items: center;
}
.balance-custom-row .btn--back {
  flex: 0 0 auto;
  width: 32px;
  padding: 0;
}
.balance-cta {
  width: 100%;
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
```

Существующий `.balance-preset` (active-state стили) оставляем.

## Affected Files

- **`web/static/components/Cabinet.jsx`** — переписать секцию `cabinet-balance-card` (≈ строки 111–195). Удалить imports/использование `LegalConsent`, состояния согласий, подсказку `Для оплаты примите оба условия выше`.
- **`web/static/platform.css`** — добавить новые классы (см. выше), почистить inline-стили из карточки.
- **`web/static/components/LegalConsent.jsx`** — **без изменений**, продолжает использоваться в `GuestOrderForm`.
- **`web/routers/refill.py`, `web/schemas.py`** — **без изменений** (вариант A).

## Testing

Тестов на refill-карточку в UI нет (фронт без unit-тестов). Ручной чек-лист:

- [ ] Resting: дефолтная сумма 1000, чип подсвечен, кнопка «Пополнить 1 000 ₽» активна.
- [ ] Клик по 500 → подсветка перескакивает, кнопка показывает «Пополнить 500 ₽».
- [ ] Клик по «Другая» → чипы исчезают, появляется инпут с фокусом и стрелка `←`.
- [ ] Очистить инпут → кнопка disabled с текстом «Введите сумму от 100 ₽».
- [ ] Ввести 250 → кнопка `Пополнить 250 ₽`, активна.
- [ ] Ввести 50 → disabled.
- [ ] Клик по `←` → возврат к чипам, дефолт 1000.
- [ ] Сабмит → бэк получает `agreed_privacy: true, agreed_offer: true`, флоу pending/success работает как раньше.
- [ ] Линки в fine-print открывают `/privacy` и `/offer` в новой вкладке.
- [ ] Мобильная вёрстка ≤ 480px: чипы умещаются в одну строку или wrap, инпут не вылезает.
- [ ] Светлая и тёмная темы: контраст fine-print читаем.

## Risks

- **Implicit consent vs. РКН/152-ФЗ.** Юридически акцепт оферты конклюдентными действиями (оплатой) — стандарт RU e-commerce (Ozon, WB, Яндекс). Если у проекта есть прямые требования эквайра / банка / РКН на явные чекбоксы — этот редизайн отменяет ту галку. Спросить владельца перед мерджем. Если требование есть — откатываемся на вариант с одним объединённым чекбоксом.
- **`agreed_privacy/agreed_offer` в БД как audit trail.** Если эти флаги пишутся в `refill_requests` или payments как доказательство согласия — после редизайна они всегда `true`. Это снижает ценность audit trail, но не ломает данные. Если такое поведение нежелательно — переходим на вариант B (убрать поля из схемы) позже.

## Open Questions

Нет — все решения зафиксированы в брейншторме.
