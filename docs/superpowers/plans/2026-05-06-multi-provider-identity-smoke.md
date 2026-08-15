# Phase 2 — E2E Smoke Checklist

## Подготовка
- [ ] `data/config.py` обновлён: OTP_TTL, OTP_MAX_ATTEMPTS, OTP_RESEND_COOLDOWN, BOT_HTTP_API_BASE.
- [ ] Применена миграция: `python scripts/migrate_phase2.py` на проде ПОСЛЕ бэкапа.

## Email auth
- [ ] Открыть /register.html → ввести email + пароль → редирект на cabinet.html, виден баланс=0.
- [ ] Logout (очистить localStorage), открыть /login.html → войти тем же email + пароль → cabinet.

## Telegram OTP
- [ ] /login_telegram.html → ввести username (или telegram_id) → "Код отправлен".
- [ ] Получить код в Telegram-боте → ввести → cabinet, баланс показывает реальный.

## Линковка
- [ ] Зарегистрировать через email → в cabinet привязать Telegram → проверить что в Telegram-боте теперь тот же баланс.
- [ ] (Обратная) Войти через Telegram → привязать email → выйти → войти через email → видим тот же ЛК.

## API-key flow
- [ ] В cabinet → "Создать приложение" → запомнить key (показывается один раз).
- [ ] curl POST /api/refill с `X-API-Key: sk_live_…` и `X-End-User-Id: testuser` → платёж проходит.
- [ ] В БД: `SELECT source_type, source_app_id FROM refills` → последняя запись `('api', <app.id>)`.

## Безопасность
- [ ] /api/me без токена → 401.
- [ ] /api/auth/email/login с неверным паролем → 401.
- [ ] /api/auth/telegram/verify-code с неверным кодом → 401, после 5 попыток код инвалидируется.
- [ ] Запрос /api/applications с X-API-Key (не JWT) → возвращает данные владельца ключа? (в Phase 2 — да; запретим в Phase 3).
- [ ] Revoke application → дальнейшие запросы с этим ключом → 401.
