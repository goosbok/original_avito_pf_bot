# Password Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add change-password (authenticated) and forgot/reset-password UI (unauthenticated, backend already exists).

**Architecture:** Backend: one new service function `change_password()` in `services/auth_email.py` + one new endpoint in `web/routers/auth_email.py`. Frontend: Profile.jsx gets an inline change-password form inside the email provider card; Auth.jsx gets two new modes (`forgot`, `reset`); app.jsx detects `/reset-password?token=xxx` on mount and routes accordingly.

**Tech Stack:** Python/FastAPI, bcrypt (via `services/auth_password`), SQLite (`services/db`), React 18 (no-build, Babel in browser), existing `api.js` helper.

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `web/schemas.py` | Modify | Add `ChangePasswordRequest` |
| `services/auth_email.py` | Modify | Add `change_password()` |
| `web/routers/auth_email.py` | Modify | Add `POST /api/auth/change-password` |
| `tests/unit/test_auth_email.py` | Modify | Add 4 unit tests for `change_password` |
| `tests/web/test_routers_auth_email.py` | Modify | Add 4 router tests for `change-password` |
| `web/static/components/Profile.jsx` | Modify | Add change-password form in email card |
| `web/static/components/Auth.jsx` | Modify | Add `forgot` and `reset` modes |
| `web/static/app.jsx` | Modify | Detect `/reset-password` on mount, pass `resetToken` |

---

## Task 1: Schema + Unit Tests + Service for `change_password`

**Files:**
- Modify: `web/schemas.py`
- Modify: `services/auth_email.py`
- Modify: `tests/unit/test_auth_email.py`

- [ ] **Step 1: Add `ChangePasswordRequest` schema to `web/schemas.py`**

Open `web/schemas.py`. Add after the `LinkEmailVerifyRequest` class:

```python
class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirm: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def passwords_match(self) -> 'ChangePasswordRequest':
        if self.new_password != self.new_password_confirm:
            raise ValueError('passwords do not match')
        return self
```

- [ ] **Step 2: Write failing unit tests**

Open `tests/unit/test_auth_email.py`. Add at the end of the file:

```python
# ── change_password tests ──────────────────────────────────────────────────

def test_change_password_success(tmp_db: Path, fake_send_email):
    uid = _identity.get_or_create_user_by_telegram(9001)
    auth_email.link_email_request(uid, "changepw@example.com", "oldpass1")
    code = _extract_link_code(tmp_db, "changepw@example.com")
    auth_email.link_email_verify(uid, "changepw@example.com", code)

    auth_email.change_password(uid, "oldpass1", "newpass99")

    # Old password no longer works
    with pytest.raises(InvalidCredentials):
        auth_email.login("changepw@example.com", "oldpass1")
    # New password works
    assert auth_email.login("changepw@example.com", "newpass99") == uid


def test_change_password_wrong_current(tmp_db: Path, fake_send_email):
    uid = _identity.get_or_create_user_by_telegram(9002)
    auth_email.link_email_request(uid, "wrongcur@example.com", "rightpass1")
    code = _extract_link_code(tmp_db, "wrongcur@example.com")
    auth_email.link_email_verify(uid, "wrongcur@example.com", code)

    with pytest.raises(InvalidCredentials):
        auth_email.change_password(uid, "wrongpass1", "newpass99")


def test_change_password_same_as_current(tmp_db: Path, fake_send_email):
    uid = _identity.get_or_create_user_by_telegram(9003)
    auth_email.link_email_request(uid, "samepw@example.com", "samepass1")
    code = _extract_link_code(tmp_db, "samepw@example.com")
    auth_email.link_email_verify(uid, "samepw@example.com", code)

    with pytest.raises(ValueError, match="must differ"):
        auth_email.change_password(uid, "samepass1", "samepass1")


def test_change_password_no_email_provider(tmp_db: Path):
    uid = _identity.get_or_create_user_by_telegram(9004)
    # No email linked — only telegram
    with pytest.raises(InvalidCredentials):
        auth_email.change_password(uid, "any", "newpass99")
```

Also add to the imports at the top of the file (if not already present):
```python
from services.exceptions import InvalidCredentials
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_auth_email.py::test_change_password_success tests/unit/test_auth_email.py::test_change_password_wrong_current tests/unit/test_auth_email.py::test_change_password_same_as_current tests/unit/test_auth_email.py::test_change_password_no_email_provider -v
```

Expected: 4 × FAILED with `AttributeError: module 'services.auth_email' has no attribute 'change_password'`

- [ ] **Step 4: Implement `change_password()` in `services/auth_email.py`**

Open `services/auth_email.py`. Add after the `link_email_verify` function:

```python
def change_password(user_id: int, current_password: str, new_password: str) -> None:
    """Change password for an authenticated user who already has email linked.

    Raises:
      - InvalidCredentials: no email provider or current_password is wrong
      - ValueError: new password is the same as current
    """
    from services.db import connect
    with connect() as con:
        row = con.execute(
            "SELECT identifier, credential_hash FROM auth_providers "
            "WHERE user_id = ? AND provider = 'email'",
            (user_id,),
        ).fetchone()

    if row is None or not verify_password(current_password, row["credential_hash"] or ""):
        raise InvalidCredentials("wrong current password or no email provider")

    if verify_password(new_password, row["credential_hash"] or ""):
        raise ValueError("new password must differ from current")

    new_hash = hash_password(new_password)
    with connect() as con:
        con.execute(
            "UPDATE auth_providers SET credential_hash = ? "
            "WHERE user_id = ? AND provider = 'email'",
            (new_hash, user_id),
        )
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_auth_email.py::test_change_password_success tests/unit/test_auth_email.py::test_change_password_wrong_current tests/unit/test_auth_email.py::test_change_password_same_as_current tests/unit/test_auth_email.py::test_change_password_no_email_provider -v
```

Expected: 4 × PASSED

- [ ] **Step 6: Commit**

```bash
git add web/schemas.py services/auth_email.py tests/unit/test_auth_email.py
git commit -m "feat(auth): add change_password service + schema"
```

---

## Task 2: Router endpoint `POST /api/auth/change-password`

**Files:**
- Modify: `web/routers/auth_email.py`
- Modify: `tests/web/test_routers_auth_email.py`

- [ ] **Step 1: Write failing router tests**

Open `tests/web/test_routers_auth_email.py`. Add at the end:

```python
# ── /change-password ──────────────────────────────────────────────────────

def _link_email_for_user(uid: int, email: str, password: str, tmp_db, no_email_fixture=None) -> None:
    """Helper: fully link email to uid (request + verify)."""
    import sqlite3
    from services import auth_email
    auth_email.link_email_request(uid, email, password)
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT code FROM pending_email_links WHERE email = ?", (email,)
        ).fetchone()
    auth_email.link_email_verify(uid, email, row["code"])


def test_change_password_204(client, tmp_db, no_email):
    from services import identity
    uid = _identity.get_or_create_user_by_telegram(8001)
    _link_email_for_user(uid, "chpw@example.com", "oldpass1", tmp_db)

    r = client.post("/api/auth/change-password", json={
        "current_password": "oldpass1",
        "new_password": "newpass99",
        "new_password_confirm": "newpass99",
    }, headers=_make_headers(uid))
    assert r.status_code == 204


def test_change_password_wrong_current_401(client, tmp_db, no_email):
    from services import identity
    uid = _identity.get_or_create_user_by_telegram(8002)
    _link_email_for_user(uid, "chpw2@example.com", "rightpass1", tmp_db)

    r = client.post("/api/auth/change-password", json={
        "current_password": "wrongpass1",
        "new_password": "newpass99",
        "new_password_confirm": "newpass99",
    }, headers=_make_headers(uid))
    assert r.status_code == 401


def test_change_password_mismatch_422(client, tmp_db, no_email):
    from services import identity
    uid = _identity.get_or_create_user_by_telegram(8003)
    _link_email_for_user(uid, "chpw3@example.com", "oldpass1", tmp_db)

    r = client.post("/api/auth/change-password", json={
        "current_password": "oldpass1",
        "new_password": "newpass99",
        "new_password_confirm": "different99",
    }, headers=_make_headers(uid))
    assert r.status_code == 422


def test_change_password_requires_auth_401(client, tmp_db):
    r = client.post("/api/auth/change-password", json={
        "current_password": "any",
        "new_password": "newpass99",
        "new_password_confirm": "newpass99",
    })
    assert r.status_code == 401
```

Also check that `_make_headers` and `no_email` fixture are defined in `test_routers_auth_email.py`. If not, add:

```python
def _make_headers(uid: int) -> dict:
    from web.auth import create_jwt
    return {"Authorization": f"Bearer {create_jwt(uid)}"}

@pytest.fixture
def no_email(monkeypatch):
    import services.email_sender as es
    monkeypatch.setattr(es, "send_email", lambda *a, **kw: None)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
docker exec original_avito_pf_bot-api-1 python -m pytest tests/web/test_routers_auth_email.py::test_change_password_204 tests/web/test_routers_auth_email.py::test_change_password_wrong_current_401 tests/web/test_routers_auth_email.py::test_change_password_mismatch_422 tests/web/test_routers_auth_email.py::test_change_password_requires_auth_401 -v
```

Expected: 4 × FAILED with 404 or `ImportError`

- [ ] **Step 3: Add endpoint to `web/routers/auth_email.py`**

Open `web/routers/auth_email.py`. Add the import for `ChangePasswordRequest` to the existing imports from `web.schemas`:

```python
from web.schemas import (
    ...
    ChangePasswordRequest,
)
```

Then add the endpoint before the last function (or at the end):

```python
@router.post("/change-password", status_code=204, response_model=None)
async def change_password(
    body: ChangePasswordRequest,
    user_id: int = Depends(require_user),
) -> None:
    """Change password for authenticated user who has email linked."""
    try:
        _auth_email.change_password(user_id, body.current_password, body.new_password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

Make sure `InvalidCredentials` is imported at the top of the router file (it should already be there from existing code).

- [ ] **Step 4: Run tests to confirm they pass**

```bash
docker exec original_avito_pf_bot-api-1 python -m pytest tests/web/test_routers_auth_email.py::test_change_password_204 tests/web/test_routers_auth_email.py::test_change_password_wrong_current_401 tests/web/test_routers_auth_email.py::test_change_password_mismatch_422 tests/web/test_routers_auth_email.py::test_change_password_requires_auth_401 -v
```

Expected: 4 × PASSED

- [ ] **Step 5: Run full auth test suite to check no regressions**

```bash
docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_auth_email.py tests/unit/test_schemas.py tests/web/test_routers_auth_email.py tests/web/test_routers_auth_link.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add web/routers/auth_email.py tests/web/test_routers_auth_email.py
git commit -m "feat(router): add POST /api/auth/change-password endpoint"
```

---

## Task 3: Profile.jsx — change password UI

**Files:**
- Modify: `web/static/components/Profile.jsx`

- [ ] **Step 1: Add `linkedChildren` prop to `ProviderCard`**

`ProviderCard` currently hides `children` when `linked=true`. Add a `linkedChildren` prop that always renders when provided.

Find this block in `ProviderCard`:

```jsx
      {!linked && <div style={{ marginTop: 16 }}>{children}</div>}
```

Replace with:

```jsx
      {!linked && <div style={{ marginTop: 16 }}>{children}</div>}
      {linked && linkedChildren && <div style={{ marginTop: 16 }}>{linkedChildren}</div>}
```

Also add `linkedChildren` to the function signature:

```jsx
function ProviderCard({ title, icon, linked, linkedLabel, children, linkedChildren }) {
```

- [ ] **Step 2: Add change-password state variables**

In `ProfilePage`, add these state variables after the existing email states:

```jsx
  const [changePwOpen, setChangePwOpen] = useProfileState(false);
  const [changePwCurrent, setChangePwCurrent] = useProfileState('');
  const [changePwNew, setChangePwNew] = useProfileState('');
  const [changePwConfirm, setChangePwConfirm] = useProfileState('');
  const [changePwLoading, setChangePwLoading] = useProfileState(false);
  const [changePwError, setChangePwError] = useProfileState('');
  const [changePwSuccess, setChangePwSuccess] = useProfileState(false);
```

- [ ] **Step 3: Add `handleChangePassword` handler**

Add after `handleLinkEmailVerify`:

```jsx
  const handleChangePassword = async () => {
    if (!changePwCurrent || !changePwNew) return setChangePwError('Заполните все поля');
    if (changePwNew.length < 8) return setChangePwError('Новый пароль — минимум 8 символов');
    if (changePwNew !== changePwConfirm) return setChangePwError('Пароли не совпадают');
    setChangePwLoading(true); setChangePwError('');
    try {
      await api.post('/api/auth/change-password', {
        current_password: changePwCurrent,
        new_password: changePwNew,
        new_password_confirm: changePwConfirm,
      });
      setChangePwSuccess(true);
      setChangePwOpen(false);
      setChangePwCurrent(''); setChangePwNew(''); setChangePwConfirm('');
    } catch (e) {
      if (e.status === 401) setChangePwError('Неверный текущий пароль');
      else setChangePwError(e.message || 'Ошибка смены пароля');
    } finally {
      setChangePwLoading(false);
    }
  };
```

- [ ] **Step 4: Update the email ProviderCard to pass `linkedChildren`**

Find the `<ProviderCard` block for email (the one with `title="Email и пароль"`). It currently looks like:

```jsx
          <ProviderCard
            title="Email и пароль" icon="Em"
            linked={!!emailProvider}
            linkedLabel={emailProvider?.identifier || ''}
          >
```

Replace with:

```jsx
          <ProviderCard
            title="Email и пароль" icon="Em"
            linked={!!emailProvider}
            linkedLabel={emailProvider?.identifier || ''}
            linkedChildren={emailProvider && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {changePwSuccess && !changePwOpen && (
                  <div className="alert alert--success">Пароль изменён</div>
                )}
                {!changePwOpen ? (
                  <button className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start' }}
                    onClick={() => { setChangePwOpen(true); setChangePwSuccess(false); setChangePwError(''); }}>
                    Сменить пароль
                  </button>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {changePwError && <div className="alert alert--error">{changePwError}</div>}
                    <div className="form-field">
                      <label className="form-label">Текущий пароль</label>
                      <input className="input" type="password" placeholder="Текущий пароль"
                        value={changePwCurrent} onChange={e => setChangePwCurrent(e.target.value)} />
                    </div>
                    <div className="form-field">
                      <label className="form-label">Новый пароль</label>
                      <input className="input" type="password" placeholder="Минимум 8 символов"
                        value={changePwNew} onChange={e => setChangePwNew(e.target.value)} />
                    </div>
                    <div className="form-field">
                      <label className="form-label">Повторите новый пароль</label>
                      <input className="input" type="password" placeholder="Повторите пароль"
                        value={changePwConfirm} onChange={e => setChangePwConfirm(e.target.value)} />
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn btn--ghost btn--sm"
                        onClick={() => { setChangePwOpen(false); setChangePwError(''); }}>
                        Отмена
                      </button>
                      <button className="btn btn--primary" style={{ flex: 1 }}
                        onClick={handleChangePassword} disabled={changePwLoading}>
                        {changePwLoading ? 'Сохраняем...' : 'Сохранить'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          >
```

- [ ] **Step 5: Commit**

```bash
git add web/static/components/Profile.jsx
git commit -m "feat(profile): add change password inline form"
```

---

## Task 4: Auth.jsx — `forgot` password mode

**Files:**
- Modify: `web/static/components/Auth.jsx`

- [ ] **Step 1: Add state for forgot mode**

In `AuthPage`, find the existing state declarations. Add:

```jsx
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotSent, setForgotSent] = useState(false);
```

Also make sure the `useEffect` that resets state on mode change clears these:

```jsx
  useEffect(() => {
    setError(''); setSuccess('');
    setRegStep('form'); setRegCode('');
    setOtpSent(false); setOtpCode('');
    setNeedsConnect(false);
    setForgotEmail(''); setForgotSent(false);       // ← add this line
  }, [mode]);
```

- [ ] **Step 2: Add `handleForgotPassword` handler**

Add after the existing handlers (e.g., after `handleEmailLogin`):

```jsx
  const handleForgotPassword = async () => {
    if (!forgotEmail) return setError('Введите email');
    setLoading(true); setError('');
    try {
      await api.post('/api/auth/forgot-password', { email: forgotEmail });
    } catch (_) {
      // Always show success to prevent email enumeration
    } finally {
      setLoading(false);
    }
    setForgotSent(true);
  };
```

- [ ] **Step 3: Add "Забыл пароль?" link in the `login` mode render**

Find the `login` mode render block in the `return` of `AuthPage`. It renders email + password fields and a login button. Add the link immediately after the login button:

```jsx
              <div style={{ textAlign: 'center', marginTop: 4 }}>
                <button className="btn btn--ghost btn--sm"
                  onClick={() => onNavigate('forgot')}
                  style={{ fontSize: '0.85rem', color: 'var(--text-2)' }}>
                  Забыл пароль?
                </button>
              </div>
```

- [ ] **Step 4: Add `forgot` mode render block**

In the main render switch/conditional of `AuthPage`, add a case for `mode === 'forgot'`. Find where modes are rendered (typically a big if/else or switch) and add:

```jsx
  if (mode === 'forgot') return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h2 style={{ marginBottom: 6 }}>Восстановление пароля</h2>
        {forgotSent ? (
          <>
            <div className="alert alert--success" style={{ marginBottom: 16 }}>
              Если аккаунт существует, письмо с инструкцией отправлено
            </div>
            <button className="btn btn--ghost" onClick={() => onNavigate('login')}>
              ← Назад ко входу
            </button>
          </>
        ) : (
          <>
            {error && <div className="alert alert--error" style={{ marginBottom: 12 }}>{error}</div>}
            <div className="form-field" style={{ marginBottom: 12 }}>
              <label className="form-label">Email</label>
              <input className="input" type="email" placeholder="you@example.com"
                value={forgotEmail} onChange={e => setForgotEmail(e.target.value)} />
            </div>
            <button className="btn btn--primary" onClick={handleForgotPassword} disabled={loading}>
              {loading ? 'Отправляем...' : 'Отправить ссылку'}
            </button>
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <button className="btn btn--ghost btn--sm" onClick={() => onNavigate('login')}
                style={{ fontSize: '0.85rem', color: 'var(--text-2)' }}>
                ← Назад ко входу
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
```

- [ ] **Step 5: Commit**

```bash
git add web/static/components/Auth.jsx
git commit -m "feat(auth): add forgot-password mode to Auth.jsx"
```

---

## Task 5: app.jsx + Auth.jsx — `reset` password mode

**Files:**
- Modify: `web/static/app.jsx`
- Modify: `web/static/components/Auth.jsx`

- [ ] **Step 1: Detect reset token on SPA load in `app.jsx`**

In `app.jsx`, find the `useState` initializers at the top of `App()`. Change the `route` and `authMode` initial values to detect the reset-password URL:

```jsx
  const _resetToken = new URLSearchParams(window.location.search).get('token');
  const _isResetRoute = window.location.pathname === '/reset-password' && !!_resetToken;

  const [route, setRoute] = useState(_isResetRoute ? 'auth' : 'landing');
  const [authMode, setAuthMode] = useState(_isResetRoute ? 'reset' : 'login');
  const [resetToken] = useState(_isResetRoute ? _resetToken : null);
```

Then pass `resetToken` to `AuthPage` in the render:

Find:
```jsx
      case 'auth':     return <AuthPage mode={authMode} onLogin={handleLogin} onNavigate={handleNavigate} botConfig={botConfig} />;
```

Replace with:
```jsx
      case 'auth':     return <AuthPage mode={authMode} onLogin={handleLogin} onNavigate={handleNavigate} botConfig={botConfig} resetToken={resetToken} />;
```

- [ ] **Step 2: Add `reset` state to `Auth.jsx`**

In `AuthPage`, add `resetToken` to props and add state for the reset form:

```jsx
const AuthPage = ({ mode: initialMode, onLogin, onNavigate, botConfig, resetToken }) => {
```

Add state variables:

```jsx
  const [resetNew, setResetNew] = useState('');
  const [resetConfirm, setResetConfirm] = useState('');
  const [resetDone, setResetDone] = useState(false);
```

Add to the mode-change `useEffect` cleanup:

```jsx
    setResetNew(''); setResetConfirm(''); setResetDone(false);   // ← add this line
```

- [ ] **Step 3: Add `handleResetPassword` handler**

```jsx
  const handleResetPassword = async () => {
    if (!resetNew || resetNew.length < 8) return setError('Пароль — минимум 8 символов');
    if (resetNew !== resetConfirm) return setError('Пароли не совпадают');
    setLoading(true); setError('');
    try {
      await api.post('/api/auth/reset-password', {
        token: resetToken,
        new_password: resetNew,
        new_password_confirm: resetConfirm,
      });
      setResetDone(true);
      // Clear token from URL without reload
      window.history.replaceState({}, '', '/');
    } catch (e) {
      if (e.status === 410) setError('Ссылка истекла — запросите новую');
      else setError(e.message || 'Ошибка сброса пароля');
    } finally {
      setLoading(false);
    }
  };
```

- [ ] **Step 4: Add `reset` mode render block to `Auth.jsx`**

Add before or after the `forgot` mode block:

```jsx
  if (mode === 'reset') return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h2 style={{ marginBottom: 6 }}>Новый пароль</h2>
        {resetDone ? (
          <>
            <div className="alert alert--success" style={{ marginBottom: 16 }}>
              Пароль изменён — войдите с новым паролем
            </div>
            <button className="btn btn--primary" onClick={() => onNavigate('login')}>
              Войти
            </button>
          </>
        ) : (
          <>
            {error && <div className="alert alert--error" style={{ marginBottom: 12 }}>{error}</div>}
            <div className="form-field" style={{ marginBottom: 12 }}>
              <label className="form-label">Новый пароль</label>
              <input className="input" type="password" placeholder="Минимум 8 символов"
                value={resetNew} onChange={e => setResetNew(e.target.value)} />
            </div>
            <div className="form-field" style={{ marginBottom: 16 }}>
              <label className="form-label">Повторите пароль</label>
              <input className="input" type="password" placeholder="Повторите пароль"
                value={resetConfirm} onChange={e => setResetConfirm(e.target.value)} />
            </div>
            <button className="btn btn--primary" onClick={handleResetPassword} disabled={loading}>
              {loading ? 'Сохраняем...' : 'Сохранить'}
            </button>
          </>
        )}
      </div>
    </div>
  );
```

- [ ] **Step 5: Commit**

```bash
git add web/static/app.jsx web/static/components/Auth.jsx
git commit -m "feat(auth): add reset-password mode; detect /reset-password route on load"
```

---

## Task 6: Full regression test

- [ ] **Step 1: Run the full auth test suite in Docker**

```bash
docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_auth_email.py tests/unit/test_schemas.py tests/web/test_routers_auth_email.py tests/web/test_routers_auth_link.py -v
```

Expected: all PASSED

- [ ] **Step 2: Manual smoke test**

1. Log in as a user with email linked → Profile → "Сменить пароль" button appears → form expands → enter wrong current password → error 401 → enter correct current → success banner
2. Log out → login page → "Забыл пароль?" link → enter email → "письмо отправлено" banner
3. Open `/reset-password?token=FAKE` → reset form renders → submit → 410 error shown
