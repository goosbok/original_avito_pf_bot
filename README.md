# original_avito_pf_bot

## Топология

Проект развёрнут на двух поддоменах:

| Поддомен              | Что отдаёт                            | Источник                                            |
|-----------------------|---------------------------------------|-----------------------------------------------------|
| `avito-pf.com`        | Статический лендинг (HTML + CSS + JS) | `web/landing/` (отдаётся nginx напрямую)            |
| `lk.avito-pf.com`     | Личный кабинет (React SPA + API)      | FastAPI контейнер `api` (порт 8000) + `web/static/` |

Лендинг можно обновлять без рестарта FastAPI: `git pull` на сервере → nginx подхватывает свежий `index.html` сразу.

См. `nginx/avito-pf.conf` для деталей nginx-конфига.

## Telegram-бот

Отдельный контейнер `bot` (aiogram). Подключение номера телефона через `/connect` создаёт `auth_providers(provider='phone', verified=1)` и позволяет логиниться на сайте через SMS-OTP.

## SMS-OTP вход (lk.avito-pf.com)

Реализован через `services/sms.py`. Провайдер выбирается через env `SMS_GATEWAY` (по умолчанию `stub` — пишет код в лог, реальной отправки нет). Реальные провайдеры (SMSC.ru, Smsaero) добавляются по мере подключения.

## Order flow

Один путь для гостя и авторизованного: `unpaid → paid → done/failed`. Промежуточный статус `payment_failed` (TTL истёк или явный отказ). Все order-эндпоинты живут под `/api/orders/pf*`. Спека: [docs/superpowers/specs/2026-06-05-landing-lk-split-design.md](docs/superpowers/specs/2026-06-05-landing-lk-split-design.md).
