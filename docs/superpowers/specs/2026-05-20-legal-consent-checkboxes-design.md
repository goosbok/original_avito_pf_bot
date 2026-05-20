# Обязательные чекбоксы согласия рядом с кнопкой оплаты

**Дата:** 2026-05-20
**Статус:** draft

## Контекст и цель

Перед каждой оплатой пользователь должен явно согласиться с двумя документами:
1. Политика конфиденциальности
2. Публичная оферта

Сейчас никакого согласия не запрашивается. Цель — закрыть юридический риск (152-ФЗ, требования платёжных провайдеров) минимальными изменениями.

## Охват

**В скоупе:**
- Веб-фронтенд: `web/static/components/Cabinet.jsx` (рефилл баланса) и `web/static/components/GuestOrderForm.jsx` (гостевой заказ ПФ).
- Бэкенд: `web/routers/refill.py`, `web/routers/guest_orders.py`, новый роутер `web/routers/legal.py`, регистрация в `web/main.py`.
- Статические страницы `/privacy` и `/offer`.

**Вне скоупа:**
- Telegram-бот (кнопка ЮКассы в `keyboards/users_menu.py:364-377`). Будет адресовано отдельной итерацией, если понадобится.
- Сохранение факта согласия в БД (никаких миграций).
- Реальный юридический текст политики и оферты — кладём плейсхолдеры, заказчик/юрист наполняет позже.

## Архитектура

**Frontend.** Новый переиспользуемый React-компонент `LegalConsent` принимает state двух чекбоксов через пропсы и вызывает callbacks при изменении. Встраивается в `Cabinet.jsx` и `GuestOrderForm.jsx`. Кнопка оплаты `disabled`, пока оба не отмечены. Состояние эфемерное — не сохраняется между сессиями. При сабмите оба флага явно передаются в body POST-запроса.

**Backend.** Существующие эндпойнты создания платежа расширяются двумя обязательными полями в Pydantic-моделях. Серверная валидация отклоняет запрос с `400`, если любое поле `False` или отсутствует (защита от обхода UI). Новый роутер `legal.py` отдаёт две статические HTML-страницы по `GET /privacy` и `GET /offer`. Файлы лежат в `web/static/legal/`.

**Поток данных:**
```
[user toggles checkboxes] → React state → submit
                                            ↓
                         POST /api/... { ..., agreed_privacy, agreed_offer }
                                            ↓
                         FastAPI Pydantic → 422 если нет полей
                                            ↓
                         handler → 400 если false → ЮКасса
```

## UI

**Расположение:** между формой и кнопкой оплаты. В `GuestOrderForm.jsx` чекбоксы кладутся в общую часть формы (один раз), чтобы desktop-кнопка и mobile-sticky-bar разделяли одно состояние.

**Тексты:**
- "Я согласен(на) с [Политикой конфиденциальности](/privacy)"
- "Я ознакомлен(а) и согласен(на) с условиями [Публичной оферты](/offer)"

**Ссылки:** `<a href="/privacy" target="_blank" rel="noopener noreferrer">` и `<a href="/offer" target="_blank" rel="noopener noreferrer">`. Открываются в новой вкладке, чтобы не терять состояние формы.

**Кнопка оплаты:**
- `disabled = !(privacyChecked && offerChecked) || existing_disabled_conditions`.
- Под кнопкой: подсказка "Для оплаты примите оба условия" — отображается только когда кнопка задизейблена именно по причине чекбоксов.

**Дефолт:** оба чекбокса unchecked. Pre-checked недопустим (152-ФЗ).

## Backend

**Новый файл `web/routers/legal.py`:**
- `GET /privacy` → `FileResponse("web/static/legal/privacy.html")` с заголовком `Cache-Control: public, max-age=300`.
- `GET /offer` → аналогично для `offer.html`.
- Роутер регистрируется в основном FastAPI-app до catch-all static handler'а, чтобы SPA fallback не перехватил эти пути.

**Изменения в `web/routers/guest_orders.py`:**
- Pydantic-модель запроса `create_guest_pf_order` получает `agreed_privacy: bool` и `agreed_offer: bool` (без default → обязательные).
- В начале handler'а: `if not (payload.agreed_privacy and payload.agreed_offer): raise HTTPException(400, "Необходимо принять политику конфиденциальности и оферту")`.

**Изменения в `web/routers/refill.py`:**
- Аналогичное расширение Pydantic-модели и handler'а `create_refill`.

## Файлы (план)

**Новые:**
- `web/static/legal/privacy.html` — статичная HTML-страница с минимальной вёрсткой и плейсхолдер-контентом.
- `web/static/legal/offer.html` — то же для оферты.
- `web/routers/legal.py` — FastAPI-роутер.
- `web/static/components/LegalConsent.jsx` — компонент двух чекбоксов.
- `tests/web/test_legal.py` — тесты роутов.

**Изменяются:**
- `web/static/components/GuestOrderForm.jsx` — встраиваем `LegalConsent`, передаём флаги в POST.
- `web/static/components/Cabinet.jsx` — то же.
- `web/routers/guest_orders.py` — Pydantic + валидация.
- `web/routers/refill.py` — Pydantic + валидация.
- `web/main.py` — регистрация нового роутера через `include_router`.
- `tests/web/test_guest_orders.py` — кейсы без согласия / false.
- `tests/web/test_refill.py` — то же.

## Edge cases

1. **Гонка состояний.** Кнопка disabled во время `loading`. Снятие чекбокса после отправки не отменяет запрос — сервер валидирует своё.
2. **Обход через DevTools.** Серверная валидация отклоняет `false`.
3. **Прямой POST мимо UI.** Pydantic делает поля обязательными → 422; false → 400.
4. **Закешированный старый JS.** Старый клиент отправит без полей и получит 422. Приемлемо — иначе создаст заказ без согласия.
5. **Telegram in-app browser.** `target="_blank"` интерпретируется Telegram — поведение нативное, не трогаем.
6. **SPA fallback.** `/privacy` и `/offer` должны разрешаться раньше catch-all SPA-роута. Проверить порядок регистрации.
7. **Кэширование статики.** `Cache-Control: public, max-age=300` — баланс между скоростью и возможностью править текст.

## Тестирование

Тесты запускаются внутри Docker (`docker exec ...`, см. memory: feedback_docker_tests). Frontend-тестов в проекте нет — фронтенд проверяется вручную в браузере (golden path + disabled-состояние).

**Backend-тесты:**
- `tests/web/test_legal.py`: 200 + content-type на `/privacy` и `/offer`.
- `tests/web/test_guest_orders.py`: 422 без полей, 400 при false, 200 при true (текущий happy-path).
- `tests/web/test_refill.py`: то же.

**Ручные проверки:**
- Кабинет: чекбоксы → кнопка "Пополнить" активируется → попап ЮКассы открывается.
- Гостевой заказ desktop + mobile: чекбоксы → кнопка "Перейти к оплате" активируется → редирект на ЮКассу.
- Открытие `/privacy` и `/offer` в новой вкладке.

## Что не делаем (YAGNI)

- ENV-переменные с URL-ами политики/оферты — обсудили, выбрали внутренние страницы.
- Запись согласия в БД с timestamp — можно добавить позже, если будут юр. споры.
- Версионирование документов — нет.
- Чекбокс в Telegram-боте — нет.
- localStorage/cookie с запоминанием согласия — нет, каждый платёж требует свежего согласия.
