# Auth login — accordion-style method picker

**Дата:** 2026-06-06
**Ветка:** `dev` (per memory rule)
**Поверхность:** LK SPA (`lk.avito-pf.com` / `lk.pf-bot.com`), компонент `web/static/components/Auth.jsx`, режим `mode === 'login'`.

## Цель

Заменить «мешанину» текущего экрана входа на единый accordion-выбор метода:
- 3 равные кнопки методов (Telegram, Email, SMS), все нейтральные по дефолту
- При тапе выбранный метод вырастает + получает primary-обводку с halo, остальные сжимаются и тускнеют
- Форма выбранного метода раскрывается прямо под его кнопкой
- Одновременно открыт максимум один метод
- Повторный тап по активному методу — свёртывает форму

## Out of scope

- Регистрация (`mode === 'register'`) — отдельный экран, не трогаем
- Восстановление пароля (`mode === 'forgot'` / `mode === 'reset'`) — отдельные экраны, не трогаем
- Backend endpoints — не трогаем (`/api/auth/email/login`, `/api/auth/phone/request-code`, `/api/auth/phone/verify`, и аналогичные TG)

## Что удаляется из текущего кода

В `Auth.jsx` (login-режим, начиная ~line 455):
- State `loginTab` (`'email' | 'phone'`) и связанная tab-полоска
- Secondary-кнопка «Войти через Telegram» (~line 500) внутри Email-вкладки
- Divider `<div className="auth-divider"><span>или через email</span></div>` (~line 503)
- Нижняя ghost-кнопка «Забыл пароль?» (~lines 519-525) — превратится в inline-ссылку внутри Email-формы
- Inline-ссылка «· На главную» из footer (~lines 533-534 и аналогичная в phone-tab footer)

Отдельный режим `mode === 'login-tg'` (~lines 249-324) — **сворачивается** в inline TG-форму внутри accordion'а. После рефактора `setMode('login-tg')` больше нигде не зовётся, режим удаляется. Соответствующие callsite'ы (например, ссылка «Войти через Telegram» в phone-tab footer, в register-режиме «Войти через Telegram» — line ~366) переписываются на новый accordion (через сторонний state, см. ниже).

## Что остаётся

- Логика логина — функции `handleEmailLogin`, `handleRequestOtp`, `handleVerifyOtp` (TG-OTP), компонент `PhoneLogin` (SMS-OTP) — все остаются, только переезжают в accordion-формы
- `needsConnect`-алерт (когда телефон не привязан к боту) — рендерится внутри TG-формы
- `botConfig.bot_connect_url` / `bot_username` — используется как раньше, только UI-местоположение меняется
- Глобальные модальные стили `.auth-wrap`, `.auth-card`, `.auth-card__logo`, `.auth-card__title`, `.auth-card__sub` — остаются
- Кнопки и ссылки за пределами accordion: «Зарегистрироваться» (footer), «Забыл пароль?» (inline в Email-форме)

## Финальная структура экрана

```
┌─ auth-card ─────────────────────┐
│   [PB logo]                     │
│   Войти в кабинет               │
│   Выберите способ входа         │
│                                 │
│   [✈ Войти через Telegram]      │  ← method-btn
│   [✉ Войти по Email]            │  ← method-btn
│   [📱 Войти по SMS]              │  ← method-btn
│                                 │
│   Нет аккаунта? Зарегистрироваться │
└─────────────────────────────────┘
```

При активном Email:

```
┌─ auth-card ─────────────────────┐
│   [PB logo]                     │
│   Войти в кабинет               │
│   Выберите способ входа         │
│                                 │
│   [✈ Войти через Telegram]      │  ← dim
│                                 │
│   [✉ Войти по Email]            │  ← active (большая, halo)
│   ┌─ method-form ─────────────┐ │
│   │ Email: [you@example.com ] │ │
│   │ Пароль: [Ваш пароль     ] │ │
│   │ [    Войти →           ] │ │
│   │     Забыл пароль?         │ │
│   └─────────────────────────────┘ │
│                                 │
│   [📱 Войти по SMS]              │  ← dim
│                                 │
│   Нет аккаунта? Зарегистрироваться │
└─────────────────────────────────┘
```

## Состояние компонента

Добавляются:
- `activeMethod: null | 'tg' | 'email' | 'sms'` — какой метод сейчас раскрыт

Удаляется:
- `loginTab`

Переезжают (логически принадлежат tg-форме внутри accordion'а; имена остаются для минимальной правки):
- `tgId`, `otpSent`, `otpCode`, `needsConnect` — используются только когда `activeMethod === 'tg'`

Переезжают (Email-форма):
- `email`, `password` — используются только когда `activeMethod === 'email'`

SMS-форма — переиспользует `PhoneLogin`-компонент as-is.

## Поведение

1. **Начальное состояние:** `activeMethod = null`. Все 3 кнопки в равном «нейтральном» размере. Формы не показаны.
2. **Тап по неактивной кнопке метода:**
   - `setActiveMethod(method)`
   - Если был раньше другой активный метод — сбросить его внутренний state (TG: `otpSent=false, otpCode=''`; SMS: `PhoneLogin` дефолт; Email-state не сбрасывается потому что одношаговый)
3. **Тап по активной кнопке метода:** `setActiveMethod(null)`. Форма свёртывается. Внутренние state'ы метода сбрасываются как в п.2.
4. **Submit формы:**
   - Email: `handleEmailLogin()` — без изменений
   - TG step1: `handleRequestOtp()` → `setOtpSent(true)`, ре-рендер step2 inline
   - TG step2: `handleVerifyOtp()` → `onLogin(jwt)`
   - SMS: остаётся в `PhoneLogin`-компоненте, тот сам управляет 2-шагом
5. **Регистрация / forgot:** `setMode('register')` / `onNavigate('forgot')` — без изменений
6. **`needsConnect`:** алерт показывается **только** когда `activeMethod === 'tg' && needsConnect === true`

## Визуальные параметры

### Кнопка метода `.method-btn`

| Свойство | Default (idle) | Active | Dimmed |
|---|---|---|---|
| `padding` | `13px 16px` | `16px 18px` | `6px 12px` |
| `font-size` | `14px` | `15px` | `11.5px` |
| `margin-bottom` | `10px` | `12px` | `6px` |
| `background` | `#fff` | `#fff` | `#f9fafb` |
| `border` | `1.5px solid #d1d5db` | `1.5px solid #0088cc` | `1.5px solid #d1d5db` |
| `color` | `#374151` | `#0088cc` | `#9ca3af` |
| `transform` | `none` | `scale(1.025)` | `scale(0.96)` |
| `opacity` | `1` | `1` | `0.5` |
| `box-shadow` | none | `0 0 0 3px rgba(0,136,204,0.18)` | none |
| `.icon font-size` | `15px` | `17px` | `12px` |

### Анимация

- **На размер/transform:** `transition: padding 280ms cubic-bezier(0.34, 1.4, 0.64, 1), font-size 280ms cubic-bezier(0.34, 1.4, 0.64, 1), transform 280ms cubic-bezier(0.34, 1.4, 0.64, 1), margin-bottom 280ms ease, box-shadow 220ms ease;` — лёгкий overshoot 1.4 ощущается как springy-фокус.
- **На цвет/opacity:** `transition: opacity 220ms ease, color 220ms ease, background 220ms ease, border-color 220ms ease;`
- **Halo-pulse** (срабатывает один раз при переходе в active):
  ```css
  @keyframes halo-pulse {
    0%   { box-shadow: 0 0 0 0   rgba(0,136,204,0.35); }
    40%  { box-shadow: 0 0 0 8px rgba(0,136,204,0.08); }
    100% { box-shadow: 0 0 0 3px rgba(0,136,204,0.18); }
  }
  /* применяется через animation: halo-pulse 1.6s ease-in-out 1; — обновляется ре-стартом по trick'у с animation:none → reflow → animation:'' */
  ```

### Форма метода `.method-form`

- `margin: -3px 0 14px`
- `padding: 14px`
- `background: #f9fafb`
- `border: 1px solid #f3f4f6`
- `border-radius: 10px`
- Появление: `animation: form-slide-in 320ms cubic-bezier(0.16, 1, 0.3, 1) both`
  ```css
  @keyframes form-slide-in {
    from { opacity: 0; transform: translateY(-8px); max-height: 0; }
    to   { opacity: 1; transform: translateY(0); max-height: 500px; }
  }
  ```
- Submit-кнопка внутри формы (`Войти →`, `Получить код в Telegram`, `Получить код по SMS`) — стиль текущего `.btn--primary.btn--lg.btn--full` без изменений (синяя заливка, чтобы визуально отличаться от кнопок-методов)

### Текстовые элементы

- Заголовок: «Войти в кабинет» (короче, чем «Добро пожаловать»)
- Подзаголовок: «Выберите способ входа»
- Иконки: `✈` Telegram, `✉` Email, `📱` SMS — пока emoji. Если в будущем подключим SVG-иконки (Lucide / react-icons) — заменим точечно, не блокер для текущего рефактора.

## Файлы

| Файл | Что меняем |
|---|---|
| `web/static/components/Auth.jsx` | Удаляем `loginTab` и tab-полоску. Удаляем `mode === 'login-tg'` блок. Перерабатываем `return ()` логин-режима под accordion. Telegram-логика (`handleRequestOtp`, `handleVerifyOtp`) остаётся, рендер переезжает в inline TG-форму. |
| `web/static/platform.css` | Добавляем правила `.method-row`, `.method-btn`, `.method-btn.active`, `.method-row.has-active .method-btn:not(.active)`, `.method-form`, `.method-form.show`, `@keyframes halo-pulse`, `@keyframes form-slide-in`. |
| `web/static/components/PhoneLogin.jsx` | Без изменений (используется как есть внутри SMS-формы). |

## Тесты

- Существующие `tests/web/test_routers_auth_*` — не затрагиваются (backend без изменений).
- Существующие `tests/unit/test_routers_*` — не затрагиваются.
- Ручной smoke (per memory rule «mobile + desktop»):
  - Открыть `lk.pf-bot.com`, проверить что начальный экран — 3 равные кнопки
  - Тапнуть каждый метод → форма раскрывается → активный подсвечивается, остальные тускнеют
  - Заполнить Email-форму с реальным аккаунтом, убедиться что вход работает
  - Тапнуть TG → ввести телефон → получить код в боте → войти
  - Тапнуть SMS → ввести телефон → получить SMS → войти
  - На mobile (375px) и desktop (1280px+) — оба должны рендериться корректно

## Что считать готовым

- Файл `Auth.jsx` не содержит `loginTab`, не содержит `mode === 'login-tg'` блок, содержит `activeMethod`
- В CSS есть все указанные правила и анимации
- Live-демо в браузере выглядит как мокап `.superpowers/brainstorm/.../accordion-animated.html`
- Email/TG/SMS логин-флоу работают как до рефактора (просто в новом UI)
- На mobile (375px) и desktop (1280px+) — отрисовка одинаково чистая
- Тесты зелёные

## Риски

- **TG-флоу с `needsConnect`-алертом** — на старом экране был большой info-блок с инструкциями по привязке бота. Внутри accordion-формы тоже должен поместиться, но визуально это много текста — возможно потребуется ужать. **Mitigation:** оставляем содержимое алерта как есть; форма растягивается под него; max-height в form-slide-in поднять до 600px если 500 не хватит.
- **`PhoneLogin` имеет свой 2-шаговый internal state** — при переключении методов мы должны его сбросить, но компонент не экспортирует ref. **Mitigation:** при `setActiveMethod` обнулять SMS-форму через смену `key` prop на `PhoneLogin` (`<PhoneLogin key={smsKey} />` — изменение key пересоздаёт компонент).
- **`mode === 'login-tg'` callsite'ы в других режимах** — например, в `register`-режиме есть ссылка «Войти через Telegram» (line ~366). После рефактора этой ссылке некуда идти. **Mitigation:** ссылка ведёт на `setMode('login')` + `setActiveMethod('tg')` (понадобится прокинуть setter через prop или через ref). Альтернатива — просто `setMode('login')` без auto-active (юзер сам выберет TG из accordion'а). Идём по альтернативному варианту — проще.
