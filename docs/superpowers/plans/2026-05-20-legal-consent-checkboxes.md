# Legal Consent Checkboxes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-20-legal-consent-checkboxes-design.md`

**Goal:** Добавить два обязательных чекбокса согласия (политика конфиденциальности + оферта) рядом с каждой кнопкой оплаты на веб-фронте, с серверной валидацией и статичными страницами `/privacy` и `/offer`.

**Architecture:** Новый переиспользуемый React-компонент `LegalConsent` встраивается в `Cabinet.jsx` (рефилл) и `GuestOrderForm.jsx` (гостевой заказ ПФ). Состояние эфемерное, кнопка оплаты `disabled` пока оба чекбокса не отмечены. Бэкенд расширяет Pydantic-схемы `RefillRequest` и `GuestPFOrderRequest` обязательными полями `agreed_privacy: bool` и `agreed_offer: bool` + отклоняет запрос с `400` если любое `false`. Новый роутер `web/routers/legal.py` отдаёт статические HTML из `web/static/legal/`.

**Tech Stack:** FastAPI (Python), Pydantic v2, React 18 (через Babel-in-browser), pytest + TestClient. Тесты — внутри Docker (`docker exec <container> python -m pytest ...`).

---

## Pre-flight: Identify Docker container

Прежде чем запускать тесты, определите имя/id запущенного контейнера и используйте его во всех `docker exec` ниже:

```bash
docker compose ps --format '{{.Service}}\t{{.Name}}'
```

Возьмите контейнер сервиса `bot` (или аналог). В шагах ниже подставьте его имя вместо `<container>`. Если контейнер не поднят: `docker compose up -d` (НЕ запускайте тесты локальным `python3` — это нарушает правило проекта, см. `memory/feedback_docker_tests.md`).

---

## File Structure

**Создаются:**
- `web/static/legal/privacy.html` — статичная страница политики конфиденциальности (плейсхолдер-текст).
- `web/static/legal/offer.html` — статичная страница оферты (плейсхолдер-текст).
- `web/routers/legal.py` — FastAPI-роутер с `GET /privacy` и `GET /offer`.
- `web/static/components/LegalConsent.jsx` — React-компонент с двумя чекбоксами.
- `tests/web/test_routers_legal.py` — тесты для роутов `/privacy` и `/offer`.

**Изменяются:**
- `web/schemas.py` — добавление `agreed_privacy: bool` и `agreed_offer: bool` в `RefillRequest` и `GuestPFOrderRequest`.
- `web/routers/refill.py` — валидация согласий + возврат `400` при `false`.
- `web/routers/guest_orders.py` — то же самое.
- `web/main.py` — регистрация `legal_router` перед `StaticFiles` mount.
- `web/static/index.html` — добавление `<script>` для `LegalConsent.jsx`.
- `web/static/components/Cabinet.jsx` — встраивание `LegalConsent` + передача флагов в `POST /api/refill`.
- `web/static/components/GuestOrderForm.jsx` — то же для `POST /api/guest-orders/pf`.
- `tests/web/test_routers_refill.py` — добавить `agreed_privacy/agreed_offer` в существующие тесты + 2 новых кейса.
- `tests/web/test_routers_guest_orders.py` — то же.

---

## Task 1: Static legal pages + router

**Files:**
- Create: `web/static/legal/privacy.html`
- Create: `web/static/legal/offer.html`
- Create: `web/routers/legal.py`
- Modify: `web/main.py` (регистрация роутера)
- Create: `tests/web/test_routers_legal.py`

---

- [ ] **Step 1.1: Создать `web/static/legal/privacy.html`**

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Политика конфиденциальности</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           max-width: 760px; margin: 0 auto; padding: 32px 20px; line-height: 1.6;
           color: #1a1a1a; background: #fff; }
    h1 { font-size: 1.75rem; margin-bottom: 8px; }
    .updated { color: #777; font-size: 0.875rem; margin-bottom: 32px; }
    a { color: #0088cc; }
    .back { display: inline-block; margin-top: 32px; }
  </style>
</head>
<body>
  <h1>Политика конфиденциальности</h1>
  <p class="updated">Версия от 2026-05-20</p>

  <p>Текст политики конфиденциальности будет добавлен.</p>

  <p>Этот документ описывает, какие персональные данные мы собираем,
     как храним и обрабатываем их в соответствии с Федеральным законом
     от 27.07.2006 № 152-ФЗ «О персональных данных».</p>

  <a class="back" href="/">← На главную</a>
</body>
</html>
```

- [ ] **Step 1.2: Создать `web/static/legal/offer.html`**

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Публичная оферта</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           max-width: 760px; margin: 0 auto; padding: 32px 20px; line-height: 1.6;
           color: #1a1a1a; background: #fff; }
    h1 { font-size: 1.75rem; margin-bottom: 8px; }
    .updated { color: #777; font-size: 0.875rem; margin-bottom: 32px; }
    a { color: #0088cc; }
    .back { display: inline-block; margin-top: 32px; }
  </style>
</head>
<body>
  <h1>Публичная оферта</h1>
  <p class="updated">Версия от 2026-05-20</p>

  <p>Текст публичной оферты будет добавлен.</p>

  <p>Этот документ описывает условия оказания услуг по продвижению
     объявлений на платформе Авито и порядок взаиморасчётов.</p>

  <a class="back" href="/">← На главную</a>
</body>
</html>
```

- [ ] **Step 1.3: Написать падающий тест для роутера**

Создать `tests/web/test_routers_legal.py`:

```python
"""Tests for /privacy and /offer static legal pages."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path):
    from web.main import app
    return TestClient(app)


def test_privacy_returns_200_html(client):
    r = client.get("/privacy")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Политика конфиденциальности" in r.text


def test_offer_returns_200_html(client):
    r = client.get("/offer")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Публичная оферта" in r.text


def test_privacy_sets_cache_control(client):
    r = client.get("/privacy")
    assert "max-age=300" in r.headers.get("cache-control", "")


def test_offer_sets_cache_control(client):
    r = client.get("/offer")
    assert "max-age=300" in r.headers.get("cache-control", "")
```

- [ ] **Step 1.4: Запустить тесты, убедиться что падают**

Run: `docker exec <container> python -m pytest tests/web/test_routers_legal.py -v`

Expected: FAIL — все 4 теста должны вернуть 404 (или иной не-200), потому что роутера ещё нет, а `StaticFiles(html=True)` не маппит `/privacy` без расширения.

- [ ] **Step 1.5: Создать `web/routers/legal.py`**

```python
"""Static legal pages: privacy policy and public offer."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["legal"])

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "legal"
_CACHE_HEADERS = {"Cache-Control": "public, max-age=300"}


@router.get("/privacy", response_class=FileResponse)
async def privacy() -> FileResponse:
    return FileResponse(
        _STATIC_DIR / "privacy.html",
        media_type="text/html",
        headers=_CACHE_HEADERS,
    )


@router.get("/offer", response_class=FileResponse)
async def offer() -> FileResponse:
    return FileResponse(
        _STATIC_DIR / "offer.html",
        media_type="text/html",
        headers=_CACHE_HEADERS,
    )
```

- [ ] **Step 1.6: Зарегистрировать роутер в `web/main.py`**

Открыть `web/main.py`. Перед блоком `from pathlib import Path` (строка 65) и `app.mount("/", StaticFiles(...))` (строка 70) добавить регистрацию роутера. Изменение:

`web/main.py` — добавить после строки `app.include_router(admin_stats_router)` (строка 63), ПЕРЕД блоком `from pathlib import Path`:

```python
from web.routers.legal import router as legal_router  # noqa: E402

app.include_router(legal_router)
```

Критично: роутер должен быть зарегистрирован ДО `app.mount("/", StaticFiles(...))`, иначе StaticFiles перехватит `/privacy` (точнее, отдаст 404, потому что файла `web/static/privacy` нет).

- [ ] **Step 1.7: Запустить тесты — должны пройти**

Run: `docker exec <container> python -m pytest tests/web/test_routers_legal.py -v`

Expected: PASS — все 4 теста проходят.

- [ ] **Step 1.8: Проверить, что приложение импортируется**

Run: `docker exec <container> python -c "from web.main import app; print('OK')"`

Expected: `OK`.

- [ ] **Step 1.9: Commit**

```bash
git add web/static/legal/ web/routers/legal.py web/main.py tests/web/test_routers_legal.py
git commit -m "feat(web): add /privacy and /offer static legal pages"
```

---

## Task 2: GuestPFOrderRequest schema + server validation

**Files:**
- Modify: `web/schemas.py:173-186` (GuestPFOrderRequest)
- Modify: `web/routers/guest_orders.py:36-67` (create_guest_pf_order)
- Modify: `tests/web/test_routers_guest_orders.py:44-50` (VALID_BODY) + 2 новых теста

---

- [ ] **Step 2.1: Обновить VALID_BODY и добавить падающие тесты согласия в `tests/web/test_routers_guest_orders.py`**

Найти `VALID_BODY` в `tests/web/test_routers_guest_orders.py:44-50` и заменить на:

```python
VALID_BODY = {
    "links": ["https://www.avito.ru/item/123"],
    "days": 7,
    "fix_count": 30,
    "contacts": False,
    "phone": "+79991234567",
    "agreed_privacy": True,
    "agreed_offer": True,
}
```

В конец секции `# ── POST /api/guest-orders/pf ─` (перед `# ── GET ... status ─`, т.е. после `test_create_guest_order_price_calculated_correctly`), добавить:

```python
def test_create_guest_order_requires_agreed_privacy(client, enabled):
    body = {**VALID_BODY, "agreed_privacy": False}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 400
    assert "политику" in r.json()["detail"].lower() or "согласи" in r.json()["detail"].lower()


def test_create_guest_order_requires_agreed_offer(client, enabled):
    body = {**VALID_BODY, "agreed_offer": False}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 400


def test_create_guest_order_missing_agreed_fields_returns_422(client, enabled):
    body = {k: v for k, v in VALID_BODY.items() if k not in ("agreed_privacy", "agreed_offer")}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 422
```

- [ ] **Step 2.2: Запустить — должны падать**

Run: `docker exec <container> python -m pytest tests/web/test_routers_guest_orders.py -v`

Expected: новые 3 теста FAIL (поля не существуют в схеме → 422 везде; happy-path тесты тоже FAIL потому что body содержит неизвестные поля? — нет, Pydantic v2 по умолчанию `extra="ignore"`, но для defensive — посмотрим. Ожидаемо: `test_create_guest_order_requires_agreed_privacy` → 201 вместо 400; `test_create_guest_order_requires_agreed_offer` → 201 вместо 400; `test_create_guest_order_missing_agreed_fields_returns_422` → 201 вместо 422. Также happy-path тесты пока проходят.).

- [ ] **Step 2.3: Расширить `GuestPFOrderRequest` в `web/schemas.py`**

Найти класс `GuestPFOrderRequest` (`web/schemas.py:173-186`) и добавить два обязательных поля. После строки `phone: str = Field(min_length=5, max_length=32)`, перед декоратором `@field_validator("links")`:

```python
    agreed_privacy: bool
    agreed_offer: bool
```

Итоговый класс:

```python
class GuestPFOrderRequest(BaseModel):
    links: list[str] = Field(min_length=1)
    days: int = Field(gt=0)
    fix_count: int = Field(ge=5)
    contacts: bool
    phone: str = Field(min_length=5, max_length=32)
    agreed_privacy: bool
    agreed_offer: bool

    @field_validator("links")
    @classmethod
    def links_must_be_avito(cls, v: list[str]) -> list[str]:
        for link in v:
            if not _re.search(r'avito\.ru', link):
                raise ValueError(f"invalid avito link: {link}")
        return v
```

- [ ] **Step 2.4: Добавить серверную валидацию в `web/routers/guest_orders.py`**

В функции `create_guest_pf_order` (`web/routers/guest_orders.py:36-67`), сразу после `async def create_guest_pf_order(body: GuestPFOrderRequest) -> GuestPFOrderResponse:`, ДО проверки `is_yookassa_enabled()`, добавить:

```python
    if not (body.agreed_privacy and body.agreed_offer):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Необходимо принять политику конфиденциальности и оферту",
        )
```

- [ ] **Step 2.5: Запустить тесты — должны пройти**

Run: `docker exec <container> python -m pytest tests/web/test_routers_guest_orders.py -v`

Expected: PASS — все тесты (включая 3 новых и обновлённые happy-path).

- [ ] **Step 2.6: Commit**

```bash
git add web/schemas.py web/routers/guest_orders.py tests/web/test_routers_guest_orders.py
git commit -m "feat(web): require consent flags in POST /api/guest-orders/pf"
```

---

## Task 3: RefillRequest schema + server validation

**Files:**
- Modify: `web/schemas.py:7-8` (RefillRequest)
- Modify: `web/routers/refill.py:87-103` (create_refill)
- Modify: `tests/web/test_routers_refill.py` (apdate существующих тестов + 2 новых)

---

- [ ] **Step 3.1: Добавить падающие тесты в `tests/web/test_routers_refill.py`**

Найти существующий тест `test_create_refill_returns_payment_url` (`tests/web/test_routers_refill.py:35-44`) и обновить body, заменив `{"amount": 500}` на `{"amount": 500, "agreed_privacy": True, "agreed_offer": True}`. То же самое для `test_refill_endpoint_accepts_api_key_auth` (строка ~110) — `json={"amount": 500, "agreed_privacy": True, "agreed_offer": True}`.

Затем в конец файла добавить:

```python
def test_create_refill_requires_agreed_privacy(authed) -> None:
    response = authed.client.post(
        "/api/refill",
        json={"amount": 500, "agreed_privacy": False, "agreed_offer": True},
        headers=authed.headers,
    )
    assert response.status_code == 400
    assert "политику" in response.json()["detail"].lower() or "согласи" in response.json()["detail"].lower()


def test_create_refill_requires_agreed_offer(authed) -> None:
    response = authed.client.post(
        "/api/refill",
        json={"amount": 500, "agreed_privacy": True, "agreed_offer": False},
        headers=authed.headers,
    )
    assert response.status_code == 400


def test_create_refill_missing_agreed_fields_returns_422(authed) -> None:
    response = authed.client.post(
        "/api/refill", json={"amount": 500}, headers=authed.headers,
    )
    assert response.status_code == 422
```

- [ ] **Step 3.2: Запустить — должны падать**

Run: `docker exec <container> python -m pytest tests/web/test_routers_refill.py -v`

Expected: новые 3 теста FAIL — `test_create_refill_missing_agreed_fields_returns_422` сейчас вернёт 200 (поля не обязательны); 2 теста на false тоже вернут 200 (валидации нет).

- [ ] **Step 3.3: Расширить `RefillRequest` в `web/schemas.py`**

Найти класс `RefillRequest` (`web/schemas.py:7-8`) и заменить на:

```python
class RefillRequest(BaseModel):
    amount: int = Field(gt=0)
    agreed_privacy: bool
    agreed_offer: bool
```

- [ ] **Step 3.4: Добавить валидацию в `web/routers/refill.py`**

В функции `create_refill` (`web/routers/refill.py:87-103`), сразу после `async def create_refill(payload: RefillRequest, caller: CurrentCaller = Depends(current_caller),) -> RefillResponse:`, перед `try:`, добавить:

```python
    if not (payload.agreed_privacy and payload.agreed_offer):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Необходимо принять политику конфиденциальности и оферту",
        )
```

- [ ] **Step 3.5: Запустить тесты — должны пройти**

Run: `docker exec <container> python -m pytest tests/web/test_routers_refill.py -v`

Expected: PASS — все.

- [ ] **Step 3.6: Прогнать весь web-тест-сьют как sanity check**

Run: `docker exec <container> python -m pytest tests/web/ -v --tb=short`

Expected: PASS — все web-тесты (на случай если ещё где-то конструируется `RefillRequest`/`GuestPFOrderRequest` без новых полей).

- [ ] **Step 3.7: Commit**

```bash
git add web/schemas.py web/routers/refill.py tests/web/test_routers_refill.py
git commit -m "feat(web): require consent flags in POST /api/refill"
```

---

## Task 4: LegalConsent React component

**Files:**
- Create: `web/static/components/LegalConsent.jsx`
- Modify: `web/static/index.html` (добавить `<script>`)

---

- [ ] **Step 4.1: Создать `web/static/components/LegalConsent.jsx`**

```jsx
// Controlled component: two required consent checkboxes (privacy + offer).
// Parent owns state; component is pure.
function LegalConsent({
  privacyChecked,
  offerChecked,
  onPrivacyChange,
  onOfferChange,
  disabled = false,
  style = {},
}) {
  const rowStyle = {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 8,
    fontSize: '0.8125rem',
    color: 'var(--text-2)',
    lineHeight: 1.5,
    cursor: disabled ? 'not-allowed' : 'pointer',
    userSelect: 'none',
  };
  const boxStyle = {
    marginTop: 2,
    flexShrink: 0,
    cursor: disabled ? 'not-allowed' : 'pointer',
    accentColor: 'var(--primary)',
  };
  const linkStyle = { color: 'var(--primary)', fontWeight: 600 };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, ...style }}>
      <label style={rowStyle}>
        <input
          type="checkbox"
          checked={privacyChecked}
          onChange={e => onPrivacyChange(e.target.checked)}
          disabled={disabled}
          style={boxStyle}
        />
        <span>
          Я согласен(на) с{' '}
          <a href="/privacy" target="_blank" rel="noopener noreferrer" style={linkStyle}>
            Политикой конфиденциальности
          </a>
        </span>
      </label>
      <label style={rowStyle}>
        <input
          type="checkbox"
          checked={offerChecked}
          onChange={e => onOfferChange(e.target.checked)}
          disabled={disabled}
          style={boxStyle}
        />
        <span>
          Я ознакомлен(а) и согласен(на) с условиями{' '}
          <a href="/offer" target="_blank" rel="noopener noreferrer" style={linkStyle}>
            Публичной оферты
          </a>
        </span>
      </label>
    </div>
  );
}

Object.assign(window, { LegalConsent });
```

- [ ] **Step 4.2: Подключить компонент в `web/static/index.html`**

Открыть `web/static/index.html`. Найти блок `<!-- Components (dependency order — imported by app.jsx) -->`. Добавить новую строку с `LegalConsent.jsx` ПЕРЕД `Cabinet.jsx` и `GuestOrderForm.jsx` (поскольку они будут его использовать). После строки `<script type="text/babel" src="/components/Auth.jsx"></script>` (строка 29) добавить:

```html
  <script type="text/babel" src="/components/LegalConsent.jsx"></script>
```

Получится:

```html
  <!-- Components (dependency order — imported by app.jsx) -->
  <script type="text/babel" src="/components/AppHeader.jsx"></script>
  <script type="text/babel" src="/components/Landing.jsx"></script>
  <script type="text/babel" src="/components/Auth.jsx"></script>
  <script type="text/babel" src="/components/LegalConsent.jsx"></script>
  <script type="text/babel" src="/components/Cabinet.jsx"></script>
  ...
```

- [ ] **Step 4.3: Sanity check — приложение всё ещё стартует**

Run: `docker exec <container> python -c "from web.main import app; print('OK')"`

Expected: `OK` (изменений в Python нет, но проверяем что StaticFiles по-прежнему отдаёт компонент).

Run: `curl -sI http://localhost:8000/components/LegalConsent.jsx | head -3` (если приложение поднято; иначе пропустить).

Expected: `HTTP/1.1 200 OK`.

- [ ] **Step 4.4: Commit**

```bash
git add web/static/components/LegalConsent.jsx web/static/index.html
git commit -m "feat(web): add LegalConsent component"
```

---

## Task 5: Wire LegalConsent into GuestOrderForm

**Files:**
- Modify: `web/static/components/GuestOrderForm.jsx`

---

- [ ] **Step 5.1: Добавить state для согласий**

В `web/static/components/GuestOrderForm.jsx` найти блок объявлений useState (строки 16-28). После строки:

```jsx
  const [error, setError] = useGOFState('');
```

Добавить:

```jsx
  const [agreedPrivacy, setAgreedPrivacy] = useGOFState(false);
  const [agreedOffer, setAgreedOffer] = useGOFState(false);
  const consentOk = agreedPrivacy && agreedOffer;
```

- [ ] **Step 5.2: Передать флаги в `handleSubmit`**

В том же файле найти `handleSubmit` (строки 52-69). В вызове `api.post('/api/guest-orders/pf', { ... })` (строки 58-64) добавить два поля. Заменить блок:

```jsx
      const data = await api.post('/api/guest-orders/pf', {
        links,
        days,
        fix_count: views,
        contacts,
        phone: phone.trim(),
      });
```

на:

```jsx
      const data = await api.post('/api/guest-orders/pf', {
        links,
        days,
        fix_count: views,
        contacts,
        phone: phone.trim(),
        agreed_privacy: agreedPrivacy,
        agreed_offer: agreedOffer,
      });
```

Также в начало `handleSubmit`, перед `if (urlCount === 0)` (строка 53), добавить guard (защита от race conditions, на случай если кнопка как-то всё же доступна):

```jsx
    if (!consentOk) return setError('Необходимо принять политику конфиденциальности и оферту');
```

- [ ] **Step 5.3: Вставить `<LegalConsent />` в форму**

В правой колонке (right col) найти кнопку оплаты для desktop (строки 217-224). НЕПОСРЕДСТВЕННО перед `<button className="btn btn--primary btn--lg btn--full desktop-only" ... >` вставить:

```jsx
              <LegalConsent
                privacyChecked={agreedPrivacy}
                offerChecked={agreedOffer}
                onPrivacyChange={setAgreedPrivacy}
                onOfferChange={setAgreedOffer}
                disabled={loading}
                style={{ marginTop: 4 }}
              />
```

Результат — `<LegalConsent />` появляется в правой колонке прямо над кнопкой оплаты и сразу под price preview.

- [ ] **Step 5.4: Disable обеих кнопок при отсутствии согласия**

В строке 220 (десктопная кнопка) заменить:

```jsx
                disabled={loading || urlCount === 0 || !paymentAvailable}
```

на:

```jsx
                disabled={loading || urlCount === 0 || !paymentAvailable || !consentOk}
```

В строке 236 (мобильная sticky-кнопка) — то же изменение:

```jsx
            disabled={loading || urlCount === 0 || !paymentAvailable || !consentOk}
```

- [ ] **Step 5.5: Подсказка под мобильной кнопкой, если она задизейблена из-за согласий**

Внутри `<div className="order-sticky-footer">` (строки 230-239), после `</button>` (строка 238) и перед закрывающим `</div>` (строка 239), добавить:

```jsx
            {!consentOk && urlCount > 0 && paymentAvailable && (
              <div style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginTop: 6, textAlign: 'center' }}>
                Для оплаты примите оба условия выше
              </div>
            )}
```

- [ ] **Step 5.6: Ручная проверка в браузере**

Поднять приложение (`docker compose up -d` если ещё не) и открыть в браузере страницу гостевого заказа (`/?guest=1` или маршрут, который рендерит `GuestOrderForm` — посмотреть в `app.jsx` как маршрутится). Проверить:

- Чекбоксы видны под price preview / над кнопкой "Перейти к оплате".
- Изначально оба unchecked.
- Кликнуть на ссылки "Политикой конфиденциальности" и "Публичной оферты" — открываются в новой вкладке (`/privacy` и `/offer`).
- Заполнить форму корректно, но не отмечать чекбоксы → кнопки "Перейти к оплате" (и desktop, и mobile sticky) задизейблены.
- На mobile под sticky-кнопкой видна подсказка "Для оплаты примите оба условия выше".
- Отметить оба чекбокса → кнопки активируются.
- Снять один чекбокс → кнопка снова disabled.

Если что-то выглядит криво — поправить inline-стили в `LegalConsent.jsx`. Не запускать никакие фронт-тесты, их в проекте нет.

- [ ] **Step 5.7: Sanity check бэкенд-тестов**

Run: `docker exec <container> python -m pytest tests/web/test_routers_guest_orders.py -v`

Expected: PASS.

- [ ] **Step 5.8: Commit**

```bash
git add web/static/components/GuestOrderForm.jsx
git commit -m "feat(web): require consent checkboxes in GuestOrderForm"
```

---

## Task 6: Wire LegalConsent into Cabinet refill

**Files:**
- Modify: `web/static/components/Cabinet.jsx`

---

- [ ] **Step 6.1: Добавить state для согласий**

В `web/static/components/Cabinet.jsx` найти блок useState в `CabinetPage` (строки 30-33). После строки:

```jsx
  const [refillPaymentId, setRefillPaymentId] = useCabinetState(null);
```

Добавить:

```jsx
  const [refillAgreedPrivacy, setRefillAgreedPrivacy] = useCabinetState(false);
  const [refillAgreedOffer, setRefillAgreedOffer] = useCabinetState(false);
  const refillConsentOk = refillAgreedPrivacy && refillAgreedOffer;
```

- [ ] **Step 6.2: Передать флаги в `handleRefill`**

Найти `handleRefill` (строки 46-58). Заменить:

```jsx
      const data = await api.post('/api/refill', { amount: Number(refillAmount) });
```

на:

```jsx
      const data = await api.post('/api/refill', {
        amount: Number(refillAmount),
        agreed_privacy: refillAgreedPrivacy,
        agreed_offer: refillAgreedOffer,
      });
```

Также в начало `handleRefill`, после `if (!refillAmount || refillAmount < 100) return;` (строка 47), добавить defensive guard:

```jsx
    if (!refillConsentOk) return;
```

Это no-op в нормальном UX (кнопка disabled), но защищает от программных вызовов `handleRefill()` минуя кнопку.

- [ ] **Step 6.3: Вставить `<LegalConsent />` под полем ввода суммы**

Найти блок с inputом суммы и кнопкой "Пополнить" (строки 115-131). Сейчас это:

```jsx
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  className="input" type="number" min={100}
                  value={refillAmount}
                  onChange={e => setRefillAmount(Number(e.target.value))}
                  placeholder="Сумма"
                  style={{ flex: 1, padding: '8px 10px', fontSize: '0.875rem' }}
                />
                <button
                  className="btn btn--primary btn--sm"
                  onClick={handleRefill}
                  disabled={refillStatus === 'pending' || refillStatus === 'polling' || !refillAmount || refillAmount < 100}
                  style={{ whiteSpace: 'nowrap' }}
                >
                  {refillStatus === 'pending' ? '...' : 'Пополнить'}
                </button>
              </div>
```

Завернуть в обёртку и добавить `<LegalConsent />` ПЕРЕД этой строкой с input/button. Итог:

```jsx
              <LegalConsent
                privacyChecked={refillAgreedPrivacy}
                offerChecked={refillAgreedOffer}
                onPrivacyChange={setRefillAgreedPrivacy}
                onOfferChange={setRefillAgreedOffer}
                disabled={refillStatus === 'pending' || refillStatus === 'polling'}
                style={{ marginBottom: 10, fontSize: '0.75rem' }}
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  className="input" type="number" min={100}
                  value={refillAmount}
                  onChange={e => setRefillAmount(Number(e.target.value))}
                  placeholder="Сумма"
                  style={{ flex: 1, padding: '8px 10px', fontSize: '0.875rem' }}
                />
                <button
                  className="btn btn--primary btn--sm"
                  onClick={handleRefill}
                  disabled={refillStatus === 'pending' || refillStatus === 'polling' || !refillAmount || refillAmount < 100 || !refillConsentOk}
                  style={{ whiteSpace: 'nowrap' }}
                >
                  {refillStatus === 'pending' ? '...' : 'Пополнить'}
                </button>
              </div>
```

(`fontSize: '0.75rem'` в style — потому что balance-card компактная, текст чекбоксов нужно сделать чуть меньше.)

- [ ] **Step 6.4: Ручная проверка в браузере**

Открыть кабинет (`/cabinet` или маршрут, который рендерит `CabinetPage` — посмотреть в `app.jsx`). Залогиниться при необходимости. Проверить:

- В balance-card видны два чекбокса между preset-кнопками и input/button.
- Ссылки кликабельны, открывают `/privacy` и `/offer` в новой вкладке.
- Если хотя бы один чекбокс не отмечен — кнопка "Пополнить" disabled.
- Отметить оба → кнопка активна → клик → попап ЮКассы открывается.

Если чекбоксы выглядят слишком плотно — увеличить `marginBottom` и/или `fontSize`.

- [ ] **Step 6.5: Финальный прогон всех тестов**

Run: `docker exec <container> python -m pytest tests/ -v --tb=short`

Expected: PASS — все тесты проходят. Если что-то падает (например, какой-то ещё тест где конструируется `RefillRequest`/`GuestPFOrderRequest`) — пофиксить body в этом тесте, добавив `agreed_privacy: True, agreed_offer: True`.

- [ ] **Step 6.6: Commit**

```bash
git add web/static/components/Cabinet.jsx
git commit -m "feat(web): require consent checkboxes for Cabinet refill"
```

---

## Verification (overall)

После всех 6 тасков:

- [ ] **Step V.1: Полный прогон тестов**

Run: `docker exec <container> python -m pytest tests/ -v --tb=short`

Expected: PASS (никаких регрессий).

- [ ] **Step V.2: Ручная проверка флоу гостевого заказа**

В браузере:
1. Открыть страницу гостевого заказа.
2. Заполнить форму корректно.
3. Без согласий — обе кнопки оплаты disabled.
4. Отметить оба чекбокса → кнопки активны.
5. Кликнуть "Перейти к оплате" → реальный (или test-mode) редирект на ЮКассу.
6. Открыть `/privacy` и `/offer` в новой вкладке — отображаются.

- [ ] **Step V.3: Ручная проверка флоу рефилла**

В браузере:
1. Залогиниться, открыть кабинет.
2. В balance-card без согласий — кнопка "Пополнить" disabled.
3. Отметить оба → активна → клик → попап ЮКассы.

- [ ] **Step V.4: Проверка обхода через DevTools**

В DevTools на странице гостевого заказа: не отмечая чекбоксов, выполнить вручную:

```js
fetch('/api/guest-orders/pf', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    links: ['https://www.avito.ru/item/123'],
    days: 7, fix_count: 30, contacts: false,
    phone: '+79991234567',
    agreed_privacy: false, agreed_offer: true,
  })
}).then(r => r.json()).then(console.log);
```

Expected: ответ с `{"detail": "Необходимо принять политику конфиденциальности и оферту"}` и status 400.

То же самое для `/api/refill` (с авторизационным заголовком).
