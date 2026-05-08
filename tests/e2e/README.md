# E2E Tests (Telethon)

## Настройка

Требует `.env` в корне проекта:
```
TEST_TG_API_ID=...
TEST_TG_API_HASH=...
TEST_AVITO_URL=https://www.avito.ru/...
```

Сессия `.test_session.session` — создаётся один раз вручную, не коммитится.

## Запуск

```bash
cd <project_root>
.venv-test/bin/pip install telethon python-dotenv pytest pytest-asyncio
.venv-test/bin/python -m pytest tests/e2e/ -v -s
```

## Файлы

| Файл | Назначение |
|---|---|
| `client.py` | Переиспользуемый Telethon-клиент, хелперы |
| `test_basic_flow.py` | /start, профиль, ПФ Авито, как начать |
