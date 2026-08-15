# Auth Login Accordion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить мешанину tabs+3-метода-в-одной-вкладке на единый accordion с 3 равными кнопками методов (Telegram, Email, SMS).

**Architecture:** Один React-компонент `Auth.jsx` (mode='login') рефакторится: вместо tab-полоски и трёх разных стилей входа — `activeMethod` state и 3 идентичные кнопки. При выборе одной кнопки она вырастает (primary border + halo), остальные сжимаются, форма метода раскрывается inline. Прежний отдельный экран `mode='login-tg'` сворачивается в TG-форму внутри accordion'а.

**Tech Stack:** React (через CDN, без сборщика — JSX парсится через Babel inline), CSS в `web/static/platform.css`. Backend не трогаем.

**Spec:** [docs/superpowers/specs/2026-06-06-auth-accordion-design.md](../specs/2026-06-06-auth-accordion-design.md)

---

## Файлы

| Файл | Что меняется |
|---|---|
| `web/static/platform.css` | + Правила `.method-row`, `.method-btn`, `.method-btn.active`, `.method-row.has-active .method-btn:not(.active)`, `.method-form`, `.method-form.show`, `@keyframes halo-pulse`, `@keyframes form-slide-in`. Никаких удалений. |
| `web/static/components/Auth.jsx` | (1) Удалить `loginTab` state и tab-полоску. (2) Удалить целиком `mode === 'login-tg'` блок (lines 249-324). (3) Перерисовать `return ()` login-режима (lines 455-540) под accordion. (4) В register-режиме (line 364) `setMode('login-tg')` → `setMode('login')`. (5) Добавить state `activeMethod` и хелпер `pickMethod`. |
| `web/static/components/PhoneLogin.jsx` | Без изменений. Условный рендер (`{activeMethod === 'sms' && <PhoneLogin .../>}`) автоматически unmount'ит компонент при переключении методов, его internal step-state сбрасывается естественно. |

---

## Подготовка к работе

Работаем на ветке `dev` (сейчас в её main-репо чекауте). Перед началом:

```bash
cd /Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot
git status                  # ожидаем clean
git rev-parse --abbrev-ref HEAD  # ожидаем dev
```

Docker не нужен для редактирования (это чистый client-side JSX/CSS), но для smoke-теста в браузере подними `api`-контейнер:

```bash
docker compose up -d api
# проверить что отвечает:
curl -sI http://localhost:8000/ | head -1   # → HTTP/1.1 200 OK
```

Тесты прогоняем тем же способом что в предыдущих чистках:

```bash
docker exec original_avito_pf_bot-api-1 pytest tests/unit tests/web -x -q
```

(имя контейнера зависит от basename текущей директории; если непонятно — `docker compose ps`).

---

## Task 1: Add accordion CSS rules

**Files:**
- Modify: `web/static/platform.css` (после `.input-mono` строки, найти где заканчивается секция `FORM ELEMENTS`)

CSS добавляется как новые независимые правила. Ничего не сломается — никто пока их не использует.

- [ ] **Step 1: Найти место вставки в platform.css**

```bash
grep -nE "^\.input-mono|^/\* Slider" web/static/platform.css | head -4
```

Ожидается:
- `143:.input-mono ...`
- `145:/* Slider */`

Вставка должна быть между line 143 и 145 (после `.input-mono`, до Slider-секции).

- [ ] **Step 2: Прочитать текущий контекст для уверенности**

Прочитать `web/static/platform.css` строки 128-170, чтобы видеть окружающий стиль и не сломать форматирование секций.

- [ ] **Step 3: Вставить CSS-блок**

Использовать Edit tool. Найти точную строку:

```
.input-mono { font-family: 'Menlo', 'Monaco', 'Consolas', monospace; font-size: 0.875rem; }
```

Заменить на:

```
.input-mono { font-family: 'Menlo', 'Monaco', 'Consolas', monospace; font-size: 0.875rem; }

/* ===== AUTH METHOD ACCORDION ===== */
.method-row { display: flex; flex-direction: column; }

.method-btn {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  padding: 13px 16px;
  border-radius: 10px;
  font-weight: 600; font-size: 14px;
  margin-bottom: 10px;
  background: #fff;
  color: var(--text-1);
  border: 1.5px solid var(--border);
  cursor: pointer;
  transition:
    padding 280ms cubic-bezier(0.34, 1.4, 0.64, 1),
    font-size 280ms cubic-bezier(0.34, 1.4, 0.64, 1),
    margin-bottom 280ms ease,
    transform 280ms cubic-bezier(0.34, 1.4, 0.64, 1),
    opacity 220ms ease,
    color 220ms ease,
    background 220ms ease,
    border-color 220ms ease,
    box-shadow 220ms ease;
}
.method-btn .method-btn__icon {
  width: 20px; height: 20px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 15px;
  transition: font-size 280ms cubic-bezier(0.34, 1.4, 0.64, 1);
}
.method-btn:hover { border-color: var(--text-3); }

.method-btn.active {
  color: var(--primary);
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(0,136,204,0.18);
  padding: 16px 18px;
  font-size: 15px;
  margin-bottom: 12px;
  transform: scale(1.025);
  transform-origin: center;
  animation: halo-pulse 1.6s ease-in-out 1;
}
.method-btn.active .method-btn__icon { font-size: 17px; }

.method-row.has-active .method-btn:not(.active) {
  padding: 6px 12px;
  font-size: 11.5px;
  margin-bottom: 6px;
  opacity: 0.5;
  color: var(--text-3);
  background: var(--surface);
  transform: scale(0.96);
  transform-origin: center;
}
.method-row.has-active .method-btn:not(.active) .method-btn__icon { font-size: 12px; }

.method-form {
  margin: -3px 0 14px;
  padding: 14px;
  background: var(--surface);
  border: 1px solid var(--border-soft, #f3f4f6);
  border-radius: 10px;
  animation: form-slide-in 320ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes halo-pulse {
  0%   { box-shadow: 0 0 0 0   rgba(0,136,204,0.35); }
  40%  { box-shadow: 0 0 0 8px rgba(0,136,204,0.08); }
  100% { box-shadow: 0 0 0 3px rgba(0,136,204,0.18); }
}

@keyframes form-slide-in {
  from { opacity: 0; transform: translateY(-8px); max-height: 0; }
  to   { opacity: 1; transform: translateY(0); max-height: 600px; }
}
/* =================================== */
```

- [ ] **Step 4: Проверить, что CSS-переменные существуют**

Использованы: `--primary`, `--text-1`, `--text-3`, `--border`, `--surface`, `--border-soft` (опциональный fallback на `#f3f4f6`). Грeпнуть:

```bash
grep -nE "^\s*--(primary|text-1|text-3|border|surface|border-soft):" web/static/platform.css
```

Ожидается: первые 5 переменных найдены. `--border-soft` может НЕ быть найдена — это OK, в CSS прописан fallback `#f3f4f6`. Если есть совпадение по `--border-soft` — оставить как есть, fallback просто не сработает.

- [ ] **Step 5: Smoke-проверка что страница не сломалась**

```bash
docker compose up -d api
sleep 2
curl -sI http://localhost:8000/platform.css | head -1
```

Ожидается: `HTTP/1.1 200 OK`. Это значит CSS-файл по-прежнему отдаётся (синтаксические ошибки не делают 500, но ломают парсер; если случилось — открой DevTools в браузере и поправь).

- [ ] **Step 6: Запустить pytest (не должен зацепиться)**

```bash
docker exec $(docker compose ps -q api) pytest tests/unit tests/web -x -q 2>&1 | tail -2
```

Ожидается: pass count (baseline дев — около 449).

- [ ] **Step 7: Commit**

```bash
git add web/static/platform.css
git commit -m "$(cat <<'EOF'
feat(auth): add accordion CSS for login method picker

Adds .method-row, .method-btn (idle/active/dim states), .method-form,
plus halo-pulse and form-slide-in keyframes. No JSX uses these yet —
follow-up commit wires them into Auth.jsx.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Refactor Auth.jsx — accordion login

**Files:**
- Modify: `web/static/components/Auth.jsx`
  - Удалить state `loginTab` (line ~41) и заменить на `activeMethod`
  - Удалить целиком блок `if (mode === 'login-tg') return (...)` (lines 249-324)
  - В register-режиме поменять `setMode('login-tg')` → `setMode('login')` (line ~364)
  - Полностью переписать `return ()` login-режима (lines 455-540) под accordion

Это один большой коммит — все правки настолько связаны, что промежуточное состояние было бы сломано.

- [ ] **Step 1: Прочитать текущий файл целиком (или ключевые куски)**

```bash
wc -l web/static/components/Auth.jsx
```

Ожидается: ~543 строки. Прочитать строки 1-50, 240-330, 360-420, 455-543, чтобы держать структуру в голове.

- [ ] **Step 2: Заменить state — `loginTab` → `activeMethod`**

В `Auth.jsx` найти строку 41:

```jsx
  const [loginTab, setLoginTab] = useState('email'); // 'email' | 'phone' — used in default login screen
```

Заменить на:

```jsx
  const [activeMethod, setActiveMethod] = useState(null); // null | 'tg' | 'email' | 'sms'

  function pickMethod(method) {
    setError('');
    setSuccess('');
    if (activeMethod === method) {
      // tap on the same method → collapse
      setActiveMethod(null);
      if (method === 'tg') { setOtpSent(false); setOtpCode(''); setNeedsConnect(false); }
      return;
    }
    // switching methods — reset state of the previously-active TG step machine
    if (activeMethod === 'tg') { setOtpSent(false); setOtpCode(''); setNeedsConnect(false); }
    setActiveMethod(method);
  }
```

- [ ] **Step 3: Удалить блок `mode === 'login-tg'`**

Найти строку 249 `if (mode === 'login-tg') return (` и удалить блок до `);` включительно — это строки 249-324 (примерно 76 строк).

После удаления должен остаться пробельный разделитель между блоком register (>= line 326) и блоком, который стоял до login-tg.

Проверь грепом, что ссылка осталась только в register-режиме (после следующего шага она тоже уйдёт):

```bash
grep -nE "login-tg" web/static/components/Auth.jsx
```

Ожидается: 1 совпадение (line 364 в register-режиме). Если больше — что-то пошло не так, остановись.

- [ ] **Step 4: В register-режиме поменять ссылку**

Найти строку:

```jsx
                onClick={() => { setRegStep('form'); setRegCode(''); setError(''); setSuccess(''); setMode('login-tg'); }}
```

Заменить на:

```jsx
                onClick={() => { setRegStep('form'); setRegCode(''); setError(''); setSuccess(''); setMode('login'); setActiveMethod('tg'); }}
```

(добавили `setActiveMethod('tg')` — после возврата на login юзер сразу видит активную TG-форму).

Проверь:

```bash
grep -nE "login-tg" web/static/components/Auth.jsx
```

Ожидается: пусто.

- [ ] **Step 5: Переписать `return ()` login-режима**

Текущий `return (` начинается на line 455 и заканчивается на line 540. Это весь login-mode.

Открыть файл в редакторе, найти строку:

```jsx
  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="auth-card__logo">{logoMark}</div>
        <h2 className="auth-card__title">Добро пожаловать</h2>
        <p className="auth-card__sub">Войдите в личный кабинет</p>
```

И до закрывающей `};` функции `AuthPage` (примерно line 541) заменить на:

```jsx
  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="auth-card__logo">{logoMark}</div>
        <h2 className="auth-card__title">Войти в кабинет</h2>
        <p className="auth-card__sub">Выберите способ входа</p>

        {error && <div className="alert alert--error">{error}</div>}
        {success && <div className="alert alert--success">{success}</div>}

        <div className={`method-row${activeMethod ? ' has-active' : ''}`}>
          {/* ── Telegram ─────────────────────────────────────────────────── */}
          <button
            type="button"
            className={`method-btn${activeMethod === 'tg' ? ' active' : ''}`}
            onClick={() => pickMethod('tg')}
          >
            <span className="method-btn__icon">✈</span>Войти через Telegram
          </button>
          {activeMethod === 'tg' && (
            <div className="method-form">
              {needsConnect && (() => {
                const botUrl = (botConfig && botConfig.bot_connect_url) || 'https://t.me/AVITOPF_bot?start=connect';
                const botName = (botConfig && botConfig.bot_username) || 'AVITOPF_bot';
                return (
                  <div className="alert alert--info">
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>Номер не привязан к боту</div>
                    <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8 }}>
                      <li><a href={botUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit', fontWeight: 600, textDecoration: 'underline' }}>Откройте @{botName} в Telegram</a></li>
                      <li>Нажмите «Поделиться контактом»</li>
                      <li>Вернитесь сюда и нажмите «Получить код»</li>
                    </ol>
                  </div>
                );
              })()}
              {!otpSent ? (
                <>
                  <div className="form-field">
                    <label className="form-label">Номер телефона</label>
                    <input
                      className="input"
                      type="tel"
                      inputMode="tel"
                      placeholder="+7 900 123-45-67"
                      value={tgId}
                      onChange={e => setTgId(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleRequestOtp()}
                    />
                  </div>
                  <button className="btn btn--primary btn--lg btn--full" onClick={handleRequestOtp} disabled={loading}>
                    {loading ? 'Отправка...' : 'Получить код в Telegram'}
                  </button>
                </>
              ) : (
                <>
                  <div className="form-field">
                    <label className="form-label">6-значный код из Telegram</label>
                    <input
                      className="input"
                      placeholder="123456"
                      value={otpCode}
                      maxLength={6}
                      onChange={e => setOtpCode(e.target.value.replace(/\D/g, ''))}
                      onKeyDown={e => e.key === 'Enter' && handleVerifyOtp()}
                      style={{ textAlign: 'center', fontSize: '1.5rem', letterSpacing: '0.2em', fontWeight: 700 }}
                      autoFocus
                    />
                    <div className="form-hint">Код действителен 10 минут</div>
                  </div>
                  <button className="btn btn--primary btn--lg btn--full" onClick={handleVerifyOtp} disabled={loading}>
                    {loading ? 'Проверка...' : 'Войти →'}
                  </button>
                  <button className="btn btn--ghost btn--sm btn--full" onClick={() => { setOtpSent(false); setOtpCode(''); setSuccess(''); }}>
                    ← Изменить номер
                  </button>
                </>
              )}
            </div>
          )}

          {/* ── Email ────────────────────────────────────────────────────── */}
          <button
            type="button"
            className={`method-btn${activeMethod === 'email' ? ' active' : ''}`}
            onClick={() => pickMethod('email')}
          >
            <span className="method-btn__icon">✉</span>Войти по Email
          </button>
          {activeMethod === 'email' && (
            <div className="method-form">
              <div className="form-field">
                <label className="form-label">Email</label>
                <input className="input" type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} />
              </div>
              <div className="form-field">
                <label className="form-label">Пароль</label>
                <input
                  className="input" type="password" placeholder="Ваш пароль"
                  value={password} onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleEmailLogin()}
                />
              </div>
              <button className="btn btn--primary btn--lg btn--full" onClick={handleEmailLogin} disabled={loading}>
                {loading ? 'Вход...' : 'Войти →'}
              </button>
              <div style={{ textAlign: 'center', marginTop: 8, fontSize: '0.85rem' }}>
                <span onClick={() => setMode('forgot')} style={{ color: 'var(--primary)', cursor: 'pointer' }}>
                  Забыл пароль?
                </span>
              </div>
            </div>
          )}

          {/* ── SMS ──────────────────────────────────────────────────────── */}
          <button
            type="button"
            className={`method-btn${activeMethod === 'sms' ? ' active' : ''}`}
            onClick={() => pickMethod('sms')}
          >
            <span className="method-btn__icon">📱</span>Войти по SMS
          </button>
          {activeMethod === 'sms' && (
            <div className="method-form">
              <PhoneLogin onSuccess={(jwt) => onLogin(jwt)} />
            </div>
          )}
        </div>

        <div className="auth-links">
          Нет аккаунта?{' '}
          <span
            onClick={() => { setRegStep('form'); setRegCode(''); setError(''); setSuccess(''); setMode('register'); }}
            style={{ color: 'var(--primary)', fontWeight: 600, cursor: 'pointer' }}
          >Зарегистрироваться</span>
        </div>
      </div>
    </div>
  );
};
```

**Важно:** убедись что после `};` закрывающей `AuthPage`-функцию идёт точно то, что было ниже в файле (если что-то было — например `Object.assign(window, ...)`). Грeпни:

```bash
grep -nE "^Object\.assign|^window\." web/static/components/Auth.jsx
```

Если есть — после `};` сохранить как есть, не удалять.

- [ ] **Step 6: Сравнить количество строк и убедиться что файл не сломан**

```bash
wc -l web/static/components/Auth.jsx
```

Ожидается: файл стал короче примерно на 60-80 строк (удалили login-tg блок ~76 строк, добавили чуть-чуть в pickMethod). Точное число неважно, главное чтобы файл валидный.

```bash
# Проверка незакрытых тегов / скобок через простую эвристику:
grep -c "^const AuthPage" web/static/components/Auth.jsx     # → 1
grep -c "^};\?$" web/static/components/Auth.jsx              # ≥ 1 (закрытие компонента)
```

- [ ] **Step 7: Запустить pytest — backend не трогали, должно пройти**

```bash
docker exec $(docker compose ps -q api) pytest tests/unit tests/web -x -q 2>&1 | tail -2
```

Ожидается: `449 passed` (или близко к baseline'у).

- [ ] **Step 8: Открыть страницу авторизации в браузере**

```bash
docker compose up -d api
```

Открыть `http://localhost:8000/` в Chrome. SPA по умолчанию рендерит order-form. Чтобы попасть на auth-экран:
- Нажми кнопку «Войти» в `AppHeader` (правый верхний угол на desktop, гамбургер-меню на mobile), ИЛИ
- В DevTools Console выполни: `sessionStorage.clear(); localStorage.clear(); location.reload();` и кликни «Войти» из footer'а order-form

**Smoke-чек (~30 сек):**
- Видны 3 равные кнопки (TG, Email, SMS)
- Тап по Email → email-кнопка вырастает с halo-pulse, форма раскрывается под ней, TG и SMS сжимаются и тускнеют
- Тап по SMS → email-форма сворачивается, появляется PhoneLogin
- Тап по TG → раскрывается phone-input
- Тап по уже активному методу → сворачивается, все возвращаются в равный размер
- DevTools Console — нет ошибок

Если что-то не отображается / падает — поправь и повтори шаг.

- [ ] **Step 9: Commit**

```bash
git add web/static/components/Auth.jsx
git commit -m "$(cat <<'EOF'
feat(auth): accordion-style method picker on login screen

Replaces the old tabs + nested Telegram button + extraneous divider with
a single accordion where Telegram, Email, and SMS are equal method
buttons. Tapping one grows it with primary border and halo-pulse, while
the others shrink + fade. The chosen method's form expands inline.

- Removes loginTab tab strip and the `mode === 'login-tg'` full screen
- Adds activeMethod state with pickMethod helper (collapse on re-tap,
  reset TG step-state on switch-away)
- Telegram link in register screen now returns to login + auto-opens TG

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Финальная верификация

После всех коммитов — ручной smoke на mobile + desktop (per memory rule про responsive).

- [ ] **Step 1: Desktop browser smoke**

Открыть Chrome (или любой браузер) в нормальном desktop-режиме (1280px+). Перейти на login-экран. Проверить:

| Чек | Ожидание |
|---|---|
| Начальный экран | 3 равные кнопки, все белые с серой обводкой |
| Тап по Email | Email-кнопка growet, halo-pulse 1 раз, форма раскрывается под ней. TG+SMS shrink+fade |
| Тап по TG | Email-форма сворачивается. TG growet, появляется phone-input. SMS остаётся dim |
| Тап по SMS | Phone-форма TG свёрнута. SMS growet, PhoneLogin рендерится |
| Тап по активному методу | Форма сворачивается. Все 3 кнопки возвращаются в равный размер |
| «Забыл пароль?» (в Email-форме) | Переход в forgot-режим работает |
| «Зарегистрироваться» (футер) | Переход в register-режим работает |
| Из register «Войти через Telegram» | Возврат на login + TG-метод авто-активирован |
| Реальный email-логин | Работает (если есть тестовый аккаунт) |
| Console errors | Нет |

- [ ] **Step 2: Mobile breakpoint smoke**

В Chrome DevTools → Toggle Device Toolbar → iPhone SE (375px) или вручную выставить viewport 375x812. Повторить чек-лист выше.

**Что особенно смотреть на мобильном:**
- Кнопки методов не уходят за края карточки
- Анимация роста/сжатия не вызывает скачка layout'а (страница не «прыгает»)
- При раскрытии формы текстовые поля доступны (клавиатура не закрывает submit-кнопку)

- [ ] **Step 3: Push в origin/dev**

Только если все чек-листы зелёные:

```bash
git push origin dev
```

После push — на проде применяется через nginx-pull без rebuild (CSS+JSX — static assets, отдаваемые nginx'ом из smartly `web/static/`).

---

## Что считать готовым

- В `web/static/platform.css` есть секция `AUTH METHOD ACCORDION` со всеми правилами
- В `web/static/components/Auth.jsx` нет `loginTab`, нет блока `mode === 'login-tg'`, нет строки `setMode('login-tg')`
- В `web/static/components/Auth.jsx` есть `activeMethod`-state и `pickMethod`-хелпер
- 3 кнопки методов в login-mode рендерятся одинакового размера в начальном состоянии
- При тапе одна кнопка увеличивается с halo-pulse, другие уменьшаются, форма открывается inline
- Реальный логин (Email / TG / SMS) работает как до рефактора
- Smoke на mobile + desktop — все пункты выше зелёные
- `pytest tests/unit tests/web` — без регрессий

## Известные риски (из спеки) + mitigation в плане

- **`needsConnect`-алерт может растянуть form** → max-height в `form-slide-in` уже 600px (не 500 как в спеке) — учтено в CSS-блоке Task 1
- **`PhoneLogin` internal step-state при переключении метода** → conditional render (`{activeMethod === 'sms' && <PhoneLogin />}`) автоматически unmount'ит и заново mount'ит компонент при возврате к SMS, ничего дополнительно делать не надо. Кей-trick из спеки не нужен.
- **Auto-active TG из register** → реализовано: `setMode('login') + setActiveMethod('tg')` в одном onClick'е
