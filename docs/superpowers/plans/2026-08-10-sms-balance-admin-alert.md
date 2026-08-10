# Админ-алерт на низкий баланс SMSPILOT — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Уведомлять админов в Telegram, когда баланс SMSPILOT опускается ниже
порога, и когда отправка SMS реально падает (например баланс кончился
совсем) — сейчас оба случая происходят молча.

**Architecture:** Проверка баланса — не отдельный периодический пробник, а
чтение поля `balance`, которое SMSPILOT и так возвращает в ответе на каждую
отправку. `SmspilotGateway` сохраняет его в `self.last_balance`;
`web/routers/auth_phone.py` после успешной отправки сравнивает с порогом и,
если нужно, шлёт алерт через существующий `send_admins()` (тот же канал, что
уже использует `services/payment_probe.py`). Второй, более срочный алерт —
когда сама отправка падает исключением. Оба алерта используют одну и ту же
таблицу `settings` для кулдауна (не спамить на каждую регистрацию).

**Tech Stack:** Python 3.11, FastAPI, existing `utils.sender.send_admins`,
`utils.sqlite3.get_setting`/`edit_setting`, pytest.

---

### Task 1: `SmspilotGateway.last_balance`

**Files:**
- Modify: `services/sms.py`
- Test: `tests/unit/test_sms.py`

Текущий `SmspilotGateway` (для контекста, не копировать целиком — меняем
только `__init__` и `send_code`):

```python
class SmspilotGateway:
    _ENDPOINT = "https://smspilot.ru/api.php"
    _TEMPLATE = "Code {code}"
    _TIMEOUT = 10.0

    def __init__(self) -> None:
        apikey = os.getenv("SMSPILOT_APIKEY")
        if not apikey:
            raise ValueError("SMSPILOT_APIKEY is not set")
        self._apikey = apikey

    def send_code(self, phone: str, code: str) -> None:
        to = phone.lstrip("+")
        text = self._TEMPLATE.format(code=code)
        try:
            resp = httpx.post(
                self._ENDPOINT,
                data={
                    "apikey": self._apikey,
                    "send": text,
                    "to": to,
                    "format": "json",
                    "charset": "utf-8",
                    "lang": "ru",
                },
                timeout=self._TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"SMSPILOT request failed: {exc}") from exc

        payload = resp.json()
        error = payload.get("error")
        if error:
            description = error.get("description_ru") or error.get("description")
            logger.error(
                "SMSPILOT send failed for %s: code=%s description=%s",
                phone, error.get("code"), description,
            )
            raise RuntimeError(f"SMSPILOT error {error.get('code')}: {description}")
```

- [ ] **Step 1: Write the failing tests**

Добавить в конец `tests/unit/test_sms.py`:

```python
def test_smspilot_gateway_captures_balance_on_success(monkeypatch):
    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "send": [{"server_id": "1", "phone": "79001234567", "status": "0"}],
                "balance": "187.50",
            }

    monkeypatch.setenv("SMSPILOT_APIKEY", "test-key")
    monkeypatch.setattr("httpx.post", lambda *a, **kw: _FakeResponse())

    from services.sms import SmspilotGateway
    gw = SmspilotGateway()
    assert gw.last_balance is None  # ничего не отправляли — баланс неизвестен
    gw.send_code("+79001234567", "4521")
    assert gw.last_balance == 187.50


def test_smspilot_gateway_balance_stays_none_when_absent(monkeypatch):
    """Ошибочный ответ без поля balance — last_balance не трогаем."""

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"error": {"code": "111", "description": "Invalid phone"}}

    monkeypatch.setenv("SMSPILOT_APIKEY", "test-key")
    monkeypatch.setattr("httpx.post", lambda *a, **kw: _FakeResponse())

    from services.sms import SmspilotGateway
    gw = SmspilotGateway()
    with pytest.raises(RuntimeError):
        gw.send_code("+79001234567", "4521")
    assert gw.last_balance is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose --profile test run --rm --build test pytest tests/unit/test_sms.py -v`
Expected: 2 новых теста FAIL — `AttributeError: 'SmspilotGateway' object has
no attribute 'last_balance'`.

- [ ] **Step 3: Implement `last_balance`**

В `services/sms.py`, в `SmspilotGateway.__init__`, после `self._apikey = apikey`:

```python
        self.last_balance: float | None = None
```

В `send_code`, сразу после `payload = resp.json()` и **до** проверки `error`:

```python
        payload = resp.json()
        balance = payload.get("balance")
        if balance is not None:
            try:
                self.last_balance = float(balance)
            except (TypeError, ValueError):
                logger.warning("SMSPILOT: could not parse balance %r", balance)

        error = payload.get("error")
```

(Остальной код `send_code` — включая `error`-ветку с `raise` — не меняется.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose --profile test run --rm --build test pytest tests/unit/test_sms.py -v`
Expected: все тесты (старые + 2 новых, итого 10) PASS.

- [ ] **Step 5: Commit**

```bash
git add services/sms.py tests/unit/test_sms.py
git commit -m "feat(sms): capture SMSPILOT balance from send response"
```

---

### Task 2: Конфигурация порога и кулдауна

**Files:**
- Modify: `data/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Добавить константы в `data/config.py`**

Найти строку `WELCOME_BONUS_RUB: int = int(os.getenv("WELCOME_BONUS_RUB", "0"))`
(строка 144) и добавить сразу после неё:

```python

# SMS-регистрация — единственный способ входа; если баланс SMSPILOT кончится,
# никто не сможет зарегистрироваться. Порог и кулдаун алертов админам —
# см. web/routers/auth_phone.py.
SMS_BALANCE_ALERT_THRESHOLD_RUB: int = int(os.getenv("SMS_BALANCE_ALERT_THRESHOLD_RUB", "200"))
SMS_BALANCE_ALERT_COOLDOWN_MIN: int = int(os.getenv("SMS_BALANCE_ALERT_COOLDOWN_MIN", "60"))
```

- [ ] **Step 2: Добавить в `.env.example`**

Найти блок про `SMSPILOT_APIKEY` (около строки 51-53):

```
# Нужен только при SMS_GATEWAY=smspilot. Ключ из личного кабинета:
# https://smspilot.ru/my-settings.php
SMSPILOT_APIKEY=
```

Добавить сразу после:

```

# Админ-алерт, если баланс SMSPILOT опустится ниже порога (регистрация —
# только по SMS, пустой баланс = никто не может зарегистрироваться).
# Кулдаун — не спамить один и тот же алерт чаще, чем раз в N минут.
SMS_BALANCE_ALERT_THRESHOLD_RUB=200
SMS_BALANCE_ALERT_COOLDOWN_MIN=60
```

- [ ] **Step 3: Проверить, что конфиг импортируется без ошибок**

Run: `docker compose --profile test run --rm --build test python -c "from data import config; print(config.SMS_BALANCE_ALERT_THRESHOLD_RUB, config.SMS_BALANCE_ALERT_COOLDOWN_MIN)"`
Expected: `200 60`

- [ ] **Step 4: Commit**

```bash
git add data/config.py .env.example
git commit -m "chore(sms): add SMS_BALANCE_ALERT_THRESHOLD_RUB / COOLDOWN_MIN config"
```

---

### Task 3: Алерты в `web/routers/auth_phone.py`

**Files:**
- Modify: `web/routers/auth_phone.py`
- Test: `tests/unit/test_auth_phone_balance_alert.py` (new)

Текущий файл целиком (для контекста):

```python
"""SMS-OTP логин по номеру телефона.

POST /api/auth/phone/request-code — выпускает SMS-код, шлёт через SmsGateway.
POST /api/auth/phone/verify — проверяет код, создаёт user если нужно
(через identity.find_or_create_user_by_phone(phone, verified=True)) и возвращает JWT.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import identity, otp, sms
from services.exceptions import OTPCooldown, OTPExpired
from utils.phones import normalize_phone
from web.auth import create_jwt
from web.schemas import TokenResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/phone", tags=["auth"])

OTP_TTL_SECONDS = 300         # 5 min
RESEND_COOLDOWN_SECONDS = 60  # 1 запрос в минуту


class RequestCodeBody(BaseModel):
    phone: str


class VerifyBody(BaseModel):
    phone: str
    code: str
    ref_code: str | None = Field(None, max_length=64)


@router.post("/request-code")
async def request_code(body: RequestCodeBody) -> dict:
    phone = normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status_code=400, detail="невалидный формат телефона")
    try:
        code = otp.issue(
            channel='sms', destination=phone,
            purpose='phone_login',
            ttl_seconds=OTP_TTL_SECONDS,
            cooldown_seconds=RESEND_COOLDOWN_SECONDS,
        )
    except OTPCooldown as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком частые запросы. Подождите {exc.retry_after_seconds} сек.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    try:
        gateway = sms.get_gateway()
        await asyncio.to_thread(gateway.send_code, phone, code)
    except Exception:
        logger.exception("SMS send failed for %s", phone)
        raise HTTPException(status_code=502, detail="Не удалось отправить SMS, попробуйте позже")
    return {"ok": True}


@router.post("/verify", response_model=TokenResponse)
async def verify(body: VerifyBody) -> TokenResponse:
    ... # без изменений, не копировать
```

(`verify` не трогаем вообще — только импорты и `request_code`.)

#### Step 1: Write the failing tests

Создать `tests/unit/test_auth_phone_balance_alert.py`:

```python
"""Алерты админам про баланс SMSPILOT — send_admins мокается на уровне
utils.sender.send_admins (тот же паттерн, что в test_payment_probe.py),
т.к. импортируется лениво внутри функции-алерта."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.sms import SmspilotGateway


class _FakeLowBalanceGateway:
    """Успешная отправка, баланс ниже порога."""

    def __init__(self, balance: float) -> None:
        self.last_balance = balance

    def send_code(self, phone: str, code: str) -> None:
        pass


class _FakeFailingGateway:
    def send_code(self, phone: str, code: str) -> None:
        raise RuntimeError("SMSPILOT error 8: Недостаточно средств")


async def test_low_balance_triggers_alert(tmp_db, monkeypatch):
    from services import sms
    from web.routers.auth_phone import RequestCodeBody, request_code

    monkeypatch.setattr(sms, "get_gateway", lambda: _FakeLowBalanceGateway(150.0))
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_THRESHOLD_RUB", 200)
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_COOLDOWN_MIN", 60)

    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await request_code(RequestCodeBody(phone="+79001234567"))

    mock_send.assert_called_once()
    alert: str = mock_send.call_args[0][0]
    assert "150.0" in alert or "150.00" in alert
    assert mock_send.call_args[0][1] == "errors"


async def test_low_balance_alert_suppressed_by_cooldown(tmp_db, monkeypatch):
    from services import sms
    from web.routers.auth_phone import RequestCodeBody, request_code

    monkeypatch.setattr(sms, "get_gateway", lambda: _FakeLowBalanceGateway(150.0))
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_THRESHOLD_RUB", 200)
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_COOLDOWN_MIN", 60)

    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await request_code(RequestCodeBody(phone="+79001234567"))
        await request_code(RequestCodeBody(phone="+79001234568"))

    mock_send.assert_called_once()  # второй вызов подавлен кулдауном


async def test_balance_above_threshold_does_not_alert(tmp_db, monkeypatch):
    from services import sms
    from web.routers.auth_phone import RequestCodeBody, request_code

    monkeypatch.setattr(sms, "get_gateway", lambda: _FakeLowBalanceGateway(500.0))
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_THRESHOLD_RUB", 200)

    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await request_code(RequestCodeBody(phone="+79001234567"))

    mock_send.assert_not_called()


async def test_send_failure_triggers_alert_and_still_returns_502(tmp_db, monkeypatch):
    from services import sms
    from web.routers.auth_phone import RequestCodeBody, request_code
    from fastapi import HTTPException

    monkeypatch.setattr(sms, "get_gateway", lambda: _FakeFailingGateway())
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_COOLDOWN_MIN", 60)

    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        with pytest.raises(HTTPException) as exc_info:
            await request_code(RequestCodeBody(phone="+79001234567"))

    assert exc_info.value.status_code == 502
    mock_send.assert_called_once()
    alert: str = mock_send.call_args[0][0]
    assert "Недостаточно средств" in alert
    assert "+799***4567" in alert  # телефон замаскирован


async def test_send_admins_failure_does_not_break_request_code(tmp_db, monkeypatch, caplog):
    """send_admins сам упал — эндпоинт всё равно должен доработать штатно."""
    import logging
    from services import sms
    from web.routers.auth_phone import RequestCodeBody, request_code

    monkeypatch.setattr(sms, "get_gateway", lambda: _FakeLowBalanceGateway(150.0))
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_THRESHOLD_RUB", 200)

    with patch("utils.sender.send_admins", side_effect=Exception("network down")):
        with caplog.at_level(logging.WARNING):
            result = await request_code(RequestCodeBody(phone="+79001234567"))

    assert result == {"ok": True}
    assert any("send_admins" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose --profile test run --rm --build test pytest tests/unit/test_auth_phone_balance_alert.py -v`
Expected: FAIL — `_FakeLowBalanceGateway`/`_FakeFailingGateway` не вызывают
никакого алерта, т.к. логики ещё нет (`mock_send.assert_called_once()`
провалится с "Expected 'send_admins' to have been called once. Called 0
times").

- [ ] **Step 3: Implement the alert helpers and wiring**

В `web/routers/auth_phone.py` заменить блок импортов:

```python
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from data import config
from services import identity, otp, sms
from services.exceptions import OTPCooldown, OTPExpired
from services.sms import SmspilotGateway
from utils.phones import normalize_phone
from utils.sqlite3 import edit_setting, get_setting
from web.auth import create_jwt
from web.schemas import TokenResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/phone", tags=["auth"])

OTP_TTL_SECONDS = 300         # 5 min
RESEND_COOLDOWN_SECONDS = 60  # 1 запрос в минуту

_LOW_BALANCE_ALERT_SETTING = "sms_balance_alert_last_sent"
_SEND_FAILURE_ALERT_SETTING = "sms_send_failure_alert_last_sent"
```

После блока `class VerifyBody(...)` и перед `@router.post("/request-code")`
добавить (это новый код — до этого в файле его не было):

```python
def _mask_phone(phone: str) -> str:
    """+79991234567 → +799***4567. Не светим номер целиком в служебном чате."""
    if len(phone) <= 8:
        return phone
    return f"{phone[:4]}***{phone[-4:]}"


def _cooldown_elapsed(setting_key: str, cooldown_minutes: int) -> bool:
    last = get_setting(setting_key)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - last_dt).total_seconds() >= cooldown_minutes * 60


def _mark_alert_sent(setting_key: str) -> None:
    edit_setting(setting_key, datetime.now(timezone.utc).isoformat())


async def _maybe_alert_low_balance(balance: float) -> None:
    if balance >= config.SMS_BALANCE_ALERT_THRESHOLD_RUB:
        return
    if not _cooldown_elapsed(_LOW_BALANCE_ALERT_SETTING, config.SMS_BALANCE_ALERT_COOLDOWN_MIN):
        logger.info("sms balance alert suppressed by cooldown, balance=%.2f", balance)
        return
    try:
        from utils.sender import send_admins
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await send_admins(
            f"⚠️ <b>Баланс SMSPILOT заканчивается</b>\n\n"
            f"Остаток: <code>{balance:.2f} ₽</code> "
            f"(порог: {config.SMS_BALANCE_ALERT_THRESHOLD_RUB} ₽)\n"
            f"Регистрация по SMS — единственный способ входа, скоро перестанет работать.\n"
            f"Пополнить: https://smspilot.ru/\n\n"
            f"Время: {ts}",
            "errors",
        )
        _mark_alert_sent(_LOW_BALANCE_ALERT_SETTING)
    except Exception:
        logger.warning("sms balance alert: send_admins failed", exc_info=True)


async def _maybe_alert_send_failure(phone: str, exc: Exception) -> None:
    if not _cooldown_elapsed(_SEND_FAILURE_ALERT_SETTING, config.SMS_BALANCE_ALERT_COOLDOWN_MIN):
        logger.info("sms send-failure alert suppressed by cooldown")
        return
    try:
        from utils.sender import send_admins
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await send_admins(
            f"🚨 <b>Отправка SMS не работает</b>\n\n"
            f"Ошибка: <code>{str(exc)[:400]}</code>\n"
            f"Телефон: <code>{_mask_phone(phone)}</code> "
            f"(регистрация не удалась, юзер получил 502)\n\n"
            f"Время: {ts}",
            "errors",
        )
        _mark_alert_sent(_SEND_FAILURE_ALERT_SETTING)
    except Exception:
        logger.warning("sms send-failure alert: send_admins failed", exc_info=True)
```

Заменить тело `request_code`:

```python
@router.post("/request-code")
async def request_code(body: RequestCodeBody) -> dict:
    phone = normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status_code=400, detail="невалидный формат телефона")
    try:
        code = otp.issue(
            channel='sms', destination=phone,
            purpose='phone_login',
            ttl_seconds=OTP_TTL_SECONDS,
            cooldown_seconds=RESEND_COOLDOWN_SECONDS,
        )
    except OTPCooldown as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком частые запросы. Подождите {exc.retry_after_seconds} сек.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    try:
        gateway = sms.get_gateway()
        await asyncio.to_thread(gateway.send_code, phone, code)
    except Exception as exc:
        logger.exception("SMS send failed for %s", phone)
        await _maybe_alert_send_failure(phone, exc)
        raise HTTPException(status_code=502, detail="Не удалось отправить SMS, попробуйте позже")

    if isinstance(gateway, SmspilotGateway) and gateway.last_balance is not None:
        await _maybe_alert_low_balance(gateway.last_balance)

    return {"ok": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose --profile test run --rm --build test pytest tests/unit/test_auth_phone_balance_alert.py -v`
Expected: все 5 тестов PASS.

- [ ] **Step 5: Run full test suite to catch regressions**

Run: `docker compose --profile test run --rm --build test pytest -v`
Expected: все тесты PASS, включая `tests/unit/test_sms.py`,
`tests/unit/test_auth_phone_offload.py`, весь остальной набор.

- [ ] **Step 6: Commit**

```bash
git add web/routers/auth_phone.py tests/unit/test_auth_phone_balance_alert.py
git commit -m "feat(sms): alert admins on low SMSPILOT balance and send failures"
```

---

### Task 4: Финальная проверка

**Files:** нет новых — верификационный проход.

- [ ] **Step 1: Полный прогон тестов**

Run: `docker compose --profile test run --rm --build test pytest -v`
Expected: все тесты PASS.

- [ ] **Step 2: Свериться со спекой**

Открыть `docs/superpowers/specs/2026-08-10-sms-balance-admin-alert-design.md`
и построчно сверить: оба алерта (низкий баланс / сбой отправки) реализованы,
кулдаун независим для каждого, номер телефона маскируется, порог и кулдаун
конфигурируемы через env, `SmsGateway` Protocol не менялся.

- [ ] **Step 3: git log обзор**

```bash
git log --oneline -5
```

Ожидается 3 новых коммита (Task 1, 2, 3) поверх спеки.
