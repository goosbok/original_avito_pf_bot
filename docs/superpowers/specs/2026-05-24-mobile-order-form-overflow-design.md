# Мобильная вёрстка — фикс horizontal overflow на форме заказа

**Дата:** 2026-05-24
**Автор:** ручная QA-сессия в Chrome MCP, viewport ~iPhone 14 Pro
**Статус:** проектирование фикса, готово к плану реализации

## Контекст

После вставки длинной ссылки на объявление Авито в форме `Авито ПФ`
страница на iPhone 14 Pro «съезжает»: правый край контента уходит
за пределы экрана, обрезаются текст рекомендации, бейдж счётчика,
слайдеры, поле даты и блок «Стоимость». На landing/кабинете/списке
заказов/auth вёрстка стабильна.

## Окружение тестирования

- Chrome MCP с обёрткой `MobileFrame` (iframe 390×844, эмулирует
  iPhone 12/13/14), фактический `innerWidth` внутри iframe = 386 px
  с учётом scrollbar — близко к iPhone 14 Pro 393 px.
- Авторизация: тестовый JWT через `POST /api/auth/email/register`
  (учётка `mobile-test+1@example.com`).
- Скрипты диагностики ищут DOM-элементы, у которых
  `scrollWidth > clientWidth + 1`, и собирают `tag/class/cw/sw`.

## Тест-план (флоу пользователя)

| #  | Сценарий                                                                | Где смотрим                                | Результат |
|----|-------------------------------------------------------------------------|---------------------------------------------|-----------|
| 1  | Landing неавторизованный                                                | `/`                                         | ✅ overflow=0 |
| 2  | Кнопка `Заказать без регистрации` (если оплата доступна)                | `LandingPage` → `guest-order-pf`            | ⚠ button disabled пока payment провайдер не сконфигурирован; код тот же баг что и в авторизованной форме (см. ниже) |
| 3  | Регистрация / логин по email                                            | `Auth`                                      | ✅ overflow=0 |
| 4  | Кабинет (балл/Услуги)                                                   | `Cabinet`                                   | ✅ overflow=0 (cabinet-balance-card корректно стэкается) |
| 5  | История заказов (пусто)                                                 | `Orders`                                    | ✅ overflow=0; фильтр-пиллы переносятся |
| 6  | Открытие `Авито ПФ` без ссылок                                          | `OrderForm`                                 | ✅ overflow=0 |
| 7  | **Вставка одной длинной ссылки Avito в textarea**                       | `OrderForm` после input                     | ❌ docScrollWidth=464 px, viewport=386 px — overflow 78 px |
| 8  | Гостевая форма (через `guest-order-pf`)                                 | `GuestOrderForm` (тот же шаблон)            | ❌ копия бага #7 — те же inline-стили |
| 9  | OrderForm после правки (CSS-инъекция `min-width:0` цепочкой)            | `OrderForm` тот же state                     | ✅ docScrollWidth=386, overflow только внутри ellipsis-ссылки (ожидаемо) |

## Корневая причина

В `web/static/components/OrderForm.jsx:167` и
`web/static/components/GuestOrderForm.jsx:142` ссылка из списка
«Добавленные объявления» задаёт жёсткие inline-стили:

```jsx
style={{ flex: 1, fontSize: '0.775rem', fontFamily: 'monospace',
         color: 'var(--primary)', overflow: 'hidden',
         textOverflow: 'ellipsis', whiteSpace: 'nowrap',
         maxWidth: 380, textDecoration: 'none' }}
```

Цепочка отказа:

1. `<a maxWidth: 380; whiteSpace: nowrap>` — ссылка требует ≥380 px
   как min-content (nowrap не позволяет шринк).
2. Родительский flex-div не задаёт `min-width: 0` для контейнера,
   поэтому шринк до меньшего значения не работает (default
   `min-width: auto`).
3. Grid-колонка `.order-two-col` на мобиле имеет
   `grid-template-columns: 1fr !important` (CSS строка 580). `1fr`
   эквивалентен `minmax(auto, 1fr)`, и `auto` = min-content всех
   дочерних, то есть ≥380 px.
4. На viewport 386 px после padding `.container` 16 px и `.card`
   18 px остаётся ≈ 318 px → колонка выходит за пределы экрана на
   ≈ 78 px. Все остальные элементы внутри (`textarea` с
   `width:100%`, slider, дата, бейджи) визуально «срезаются»,
   потому что родитель шире viewport.

То есть **один inline-стиль** на ссылке каскадно расширяет всю
колонку. Подтверждено: после инъекции CSS

```css
.order-two-col, .order-two-col > div, .order-two-col .card { min-width: 0; }
.order-two-col a[href*="avito"] {
  max-width: none !important; min-width: 0 !important;
  flex: 1 1 0 !important;
}
```

`documentScrollWidth` стал равен `viewport` (386 = 386).
Скриншот после фикса: все блоки укладываются в экран, бейдж
«✓ 1 объявление» виден целиком, textarea переносит URL по символам.

## Что НЕ нашлось (важно для scope)

Проверены и **не имеют overflow на 386 px**:

- `Landing` (`/`) — heading/CTA/landing-stats-grid стэкаются ок.
- `Cabinet` — `cabinet-top-row` уходит в column, `cabinet-balance-card` сбрасывает `max-width`.
- `Auth`, `Orders` (пустой), верхний `header` с burger.
- Все остальные места с inline `maxWidth: 4xx` (`OrderForm:91`
  submitted-state, `GuestOrderSuccess:51/91`) — там
  `padding: 0 20px; width: 100%`, что корректно ужимает контент.

## Дизайн фикса

### Принцип

Не вводить новый mobile-only override. Исправить inline-стили в
двух React-компонентах так, чтобы ссылка корректно шринкалась
внутри flex-родителя при любых viewport. Это лечит и старые
viewport <412 px, и потенциальные будущие узкие места.

### Изменения

**`web/static/components/OrderForm.jsx:167`** и
**`web/static/components/GuestOrderForm.jsx:142`** — заменить
inline-style ссылки:

```jsx
// до:
style={{ flex: 1, fontSize: '0.775rem', fontFamily: 'monospace',
         color: 'var(--primary)', overflow: 'hidden',
         textOverflow: 'ellipsis', whiteSpace: 'nowrap',
         maxWidth: 380, textDecoration: 'none' }}

// после:
style={{ flex: '1 1 0', minWidth: 0, fontSize: '0.775rem',
         fontFamily: 'monospace', color: 'var(--primary)',
         overflow: 'hidden', textOverflow: 'ellipsis',
         whiteSpace: 'nowrap', textDecoration: 'none' }}
```

Ключевое: `minWidth: 0` снимает default `min-width: auto`, который
блокировал шринк. `maxWidth: 380` убираем — `flex: '1 1 0'`
заполнит доступное место без принудительного 380.

Дополнительно тот же файл, контейнер строки-ссылки
(`OrderForm.jsx:163`, `GuestOrderForm.jsx:140`) — добавить
`minWidth: 0`, чтобы flex-обёртка пропускала шринк дочернего `<a>`:

```jsx
// до:
style={{ display: 'flex', alignItems: 'center', gap: 8,
         padding: '7px 0', borderBottom: ... }}

// после:
style={{ display: 'flex', alignItems: 'center', gap: 8,
         minWidth: 0, padding: '7px 0', borderBottom: ... }}
```

И сама grid-обёртка `.order-two-col` (CSS файл, два места
использования) — добавить общий `min-width: 0` для колонок:

```css
/* web/static/platform.css — в существующий @media (max-width: 768px) */
.order-two-col,
.order-two-col > * { min-width: 0; }
```

Это страхует от похожих регрессий, если кто-то снова положит
длинный неразрывный текст в ту же колонку.

### Что НЕ меняем

- `gridTemplateColumns: '1fr 340px'` inline на `.order-two-col`
  оставляем — на десктопе он нужен, на мобиле его перебивает
  CSS-override с `!important`.
- `textarea` `word-break` оставляем `normal` — после фикса
  ссылки она получает корректную ширину 318 px, а длинная строка
  внутри textarea и так оборачивается за счёт `overflow-wrap:
  break-word`. Менять на `break-all` не нужно, чтобы не ломать
  читаемость нормальных слов в случайном пользовательском вводе.

### Регресс-чек

После фикса вручную пройти кейсы #6–#8 на viewport 386 px:

1. textarea пустая → форма выглядит как до.
2. Вставка 1 длинного URL → бейдж счётчика, текст рекомендации,
   слайдеры, дата, sticky footer уложены в viewport.
3. Вставка 5 URL подряд → список ссылок шринкается с ellipsis,
   кнопка «−» не наезжает на текст.
4. На viewport 768 px и шире — двухколоночный layout сохранён.

## Скоуп

Только два JSX-файла + одна CSS-строка. Не трогаем backend,
не вводим новые пропсы, не рефакторим сетку. Один атомарный PR.

## Реализация и верификация

Все три правки применены 2026-05-24 в worktree
`hardcore-thompson-8f3e40` и `docker cp`-нуты в работающий
контейнер `original_avito_pf_bot-api-1` для live-проверки.

Файлы:
- `web/static/components/OrderForm.jsx:163,167`
- `web/static/components/GuestOrderForm.jsx:140,142`
- `web/static/platform.css:580+` (внутри `@media max-width:768px`)

**Результат браузерной проверки** на viewport 388 px после вставки
длинного Avito-URL:

| Метрика                  | До фикса | После фикса |
|--------------------------|----------|-------------|
| `documentScrollWidth`    | 464 px   | 388 px (= viewport) |
| Кол-во overflow-элементов| 7        | 1 (сам `<a>` с ellipsis, ожидаемо) |
| `<a>` `maxWidth` computed| `380px`  | `none`      |
| `<a>` `minWidth` computed| `auto`   | `0px`       |
| Бейдж «✓ 1 объявление»   | срезан   | виден целиком |
| Sticky footer «Итого»    | срезан   | виден целиком |

## Дополнительные находки из расширенного QA

Статический и браузерный аудит остальных экранов после фикса:

| Экран            | Состояние                                              |
|------------------|--------------------------------------------------------|
| `OrderDetail`    | ✅ ссылки рендерятся с `wordBreak: break-all` и `flex: 1` — overflow невозможен |
| `AdminOrders`    | ✅ `minWidth: 130` на кнопке умещается на 386 px |
| `AdminSupport`   | ⚠ потенциальный риск: превью сообщения `whiteSpace: nowrap; ellipsis` — нужна проверка в реальных данных (требует admin-учётки) |
| `AdminUsers`, `AdminPanel`, `AdminDashboard`, `SupportChat`, `Notifications` | ✅ без anti-pattern `maxWidth + nowrap` |
| `Profile`        | ⚠ **UX gap**: `Профиль` отсутствует в мобильном burger-меню `AppHeader.jsx:295-298`, доступен только из desktop-дропдауна. Сам компонент — `maxWidth: 600` на контейнере без overflow. Это отдельный тикет, не часть текущего фикса. |

## Итоги follow-up плана (2026-05-24)

План `docs/superpowers/plans/2026-05-24-mobile-qa-followup.md`
выполнен — 7 задач, 5 коммитов на ветке
`claude/hardcore-thompson-8f3e40` (поверх `dev`):

| Коммит | Цель | Статус |
|---|---|---|
| `f09cf8f` | T1: основной фикс `OrderForm/GuestOrderForm/platform.css` | ✅ live-проверено, docW=vw=388 |
| `d8b1af7` | T1-docs: спека + план | ✅ |
| `b5dc92b` | T2: `Профиль` в мобильный burger-menu | ✅ live: пункт виден, /profile открывается без overflow |
| `7c50420` | T5.1: первая попытка фикса `.bell__panel` | ⚠ заместить — недостаточно (см. T5.2) |
| `b07358d` | T5.2: `.bell__panel` через `position: fixed` + `!important` | ✅ live: panel x=16, right=372, top=62, внутри viewport |

Проверены без overflow и без правок:
- **T3 OrderDetail** (засижен order #9 с 2 длинными Avito URL) —
  ссылки рендерятся `wordBreak: break-all`, sw=cw=296.
- **T4 Refill «Другая сумма»** с экстремальным значением `99 999 999 ₽`
  — input 276 px, кнопка умещается, нет overflow.
- **T5 SupportChat overlay** — `.chat-panel` width=356, x=8 уже
  корректно с `width: calc(100vw - 32px)`.
- **T6 AdminSupport** (юзер 4 повышен в админы, засижен тикет 17 с
  632-символьным сообщением) — превью с ellipsis работает,
  страница docW=vw=388. Ранее зафиксированный риск снят.

## Открытые spinoffs (не блокеры)

- 💬 Кнопка «Связаться с поддержкой по этому заказу» в OrderDetail
  имеет 16 px inner-overflow на 388 px viewport (sw=303 vs cw=287).
  Текст всё ещё виден, но желательно укоротить лейбл или разрешить
  wrap. Отдельный chip-task создан через `spawn_task`.
- Пара `OrderForm.jsx` / `GuestOrderForm.jsx` дублирует ~50 строк
  JSX (список добавленных ссылок). Code-quality reviewer T1 отметил
  как known дублирование — кандидат на consolidation refactor.

## Что НЕ изменилось из изначального плана

- `body { overflow-x: hidden }` глобальный safety-net рассмотрен и
  отклонён — маскирует баги вместо их устранения. Точечные `min-width: 0`
  предпочтительнее.
