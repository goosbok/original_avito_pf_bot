# Legacy cleanup — sweep dead code, keep only what serves the PF-order flow

**Дата:** 2026-06-06
**Ветка:** `dev` (per memory rule: `main` = прод, `dev` = интеграция)
**Цель:** Удалить мёртвый код, который не относится к рабочему флоу заказа ПФ. Это **не** выпил рабочих фич (баланс / refill / промокоды / саппорт остаются — они часть флоу).

## Контекст и инвариант

- Прод сейчас живёт на ветке `main`. Ветка `dev` ещё не выкатывалась — релиз будет позже, накатом `dev` поверх `main`.
- Поэтому есть код, который технически «легаси сейчас», но **нужен для миграции** при ближайшем релизе. Такой код помечен как «Wave C — post-release» и в этом проходе **не трогается**.
- aiogram-2 обработчики регистрируются как побочный эффект импорта модуля. `__main__.py` делает `from handlers.main_start import *` → Python подгружает `handlers/__init__.py` → тот импортирует все хандлеры → декораторы `@dp.*_handler` срабатывают. Это значит: чтобы «удалить хандлер», недостаточно перестать его звать — нужно убрать его из `handlers/__init__.py` и удалить файл (или вырезать конкретный `@dp...` блок).

## Что НЕ трогаем

- Баланс, refill, промокоды, саппорт, нотификации, funnel-аналитика, admin-панель — это рабочие фичи.
- `Cabinet.jsx` остаётся (это рабочий дашборд LK, не легаси-лендинг).
- Migration-скрипты `scripts/migrate_*.py` и legacy-швы (sqlite drop, dd.mm.yyyy fallback) — нужны для предстоящего релиза.

## Wave A — нулевой риск (точечные удаления)

Это код, на который нет ни одного входящего вызова. Удаляется без правки чего-либо ещё.

### A1. `lending.html` в корне репо
- Файл 646 KB, 179 строк.
- Bundler-экспорт старого черновика лендинга (Claude.ai).
- Не упоминается в `nginx/avito-pf.conf`, `docker-compose.yml`, `Dockerfile`, ни в одном `*.py`, ни в одном html/jsx. Новый рабочий лендинг живёт в `web/landing/`.
- **Действие:** `git rm lending.html`.

### A2. Endpoint `POST /api/auth/email/register` ([web/routers/auth_email.py:35](web/routers/auth_email.py:35))
- В коде помечен `kept for backwards compatibility`.
- Фронт зовёт двухшаговый `/register-request` → `/register-verify`.
- Зовётся только из `tests/web/test_routers_auth_email.py` (того же auth-флоу теста).
- **Действие:** удалить эндпоинт + соответствующий тест-кейс. Прочие тесты этого файла остаются.

### A3. Закомментированные кнопки в клавиатурах
- `keyboards/inline_keyboards.py:42-47` — docstring-блок «Яндекс ПФ»
- `keyboards/inline_keyboards.py:48-59` — hash-блок «btn_reviews» и «btn_seo_boost»
- `keyboards/inline_keyboards.py:66-71` — docstring-блок «1.000₽ за отзыв»
- `keyboards/users_menu.py:38-49` — hash-блок «btn_reviews» и «btn_seo_boost»
- **Действие:** удалить эти блоки. Самостоятельная подсистема — Wave B7 трогает связанные хандлеры.

### A4. Два мёртвых callback-хандлера
- `handlers/commands.py:115-126` — `@dp.callback_query_handler(text_startswith="qna_avito", ...)` — Q&A callback_data строится динамически из БД (`qna['parametr']`), префикса `qna_avito` ни одна клавиатура не отправляет.
- `handlers/admin_orders.py:422` — `@dp.callback_query_handler(text="to_general_user_report", ...)` — строка используется как `page`-параметр маршрутизации, но в `callback_data=` нигде не пишется.
- **Действие:** удалить оба `@dp` блока вместе с телами функций. Импорты пересмотреть.

### A5. Legacy-alias `'order-pf'` в SPA
- [web/static/app.jsx:272](web/static/app.jsx:272) — `'order-pf'` оставлен как алиас на `'order-new'` (комментарий: «kept as alias for legacy callsites»).
- [web/static/app.jsx:221](web/static/app.jsx:221) — приём «full order object (legacy callsites)» вместо `{order_id}`.
- Внешних ссылок на `/order-pf` не выявлено.
- **Действие:** убрать алиас + ветку legacy-callsites. Все вызовы должны передавать `{order_id}`.

### A6. Неиспользуемые функции в `utils/other_functions.py`
Грепом подтверждено: импортируются извне только `get_user_string_without_first_name`, `get_days_suffix`, `format_decimal`. Удаляем:
- `str2dict`
- `link_cleaner`
- `str2bool`
- `declension_*` (все варианты)
- `decline_order`
- `conv_delta`
- `split_messages`
- `get_referals_count`

## Wave B — средний риск (целые фича-вешалки бота)

Кнопки этих фич давно закомментированы в главном меню (Wave A3), но сами хандлеры всё ещё загружаются и регистрируются на dispatcher'е. Они никогда не получат callback — это мёртвая ветка бота.

### B7. Выпил «Отзывы», «SEO-буст», «Яндекс ПФ», «Review bonus»

**Удалить файлы целиком:**
- `handlers/seo.py` (~153 строки)
- `handlers/reviews.py` (~230 строк)

**Из `handlers/__init__.py`** — убрать `seo`, `reviews` из списка импортов.

**Из `handlers/pf_order.py`** — вырезать:
- `@dp.callback_query_handler(text="yandex_pf", ...)` (lines 64+) — заглушка «Яндекс ПФ — скоро»
- `@dp.callback_query_handler(text="review_bonus", ...)` (lines 69+) — заглушка «бонус за отзыв»

**Из `keyboards/inline_keyboards.py`** — удалить:
- `seo_boost_kb()` (line 105) и все связанные клавиатуры (seo_months, seo_order_confirm)
- любые `*reviews*_kb`-функции (узнать в момент работы)

**Из `keyboards/users_menu.py`** — удалить:
- `seo_boost_kb()` (line 410) и компаньоны
- `tarifs_kb` / `pf_kb` остаются (они нужны для ПФ-флоу — проверить, какие тарифы они показывают, не выпилить случайно сам ПФ)

**Из `design.py`** — удалить строковые константы:
- `what_tasks`
- `new_refferal`
- `reviews_menu`
- `suppport_text` (старый FAQ-текст, не путать с саппорт-чатом!)
- `q1`, `q2`, `q3`, `q4`, `q1_text`, `q2_text`, `q3_text`, `q4_text`
- `moremoney`
- `nosuchorder`
- Любые `seo_*` константы

**Перед удалением `suppport_text`:** грепнуть, что эту строку (с тройным `p`!) никто не зовёт из активного кода. В Wave A это значение помечено как «старый FAQ», но имя путается с саппорт-чатом.

**Из `data/strings`** (или того места, где хранятся `get_string('btn_reviews')`, `get_string('btn_seo_boost')`, `get_string('btn_seo_howto')` и т.п.): удалить соответствующие ключи. Их точный набор определяется в момент работы — внутри `get_string()`.

**Сверка тестов:** в `tests/` нет специальных тестов на reviews/seo-флоу, но проверить, что после удаления `pytest` зелёный.

### B8. Чистка Cabinet placeholder-сервисов

[web/static/components/Cabinet.jsx:5-12](web/static/components/Cabinet.jsx:5) содержит каталог из 6 услуг, из которых работает только `pf`:

```js
const SERVICES = [
  { id: 'pf',      ...available: true,  route: 'order-pf' },
  { id: 'reviews', ...available: true,  route: null },           // ← удалить
  { id: 'ypf',     ...available: false, badge: 'В разработке' }, // ← удалить
  { id: 'seo',     ...available: false, badge: 'Скоро' },        // ← удалить
  { id: 'copy',    ...available: false, badge: 'Скоро' },        // ← удалить
  { id: 'smm',     ...available: false, badge: 'Скоро' },        // ← удалить
];
```

**Действие:** оставить только `pf`. И обновить `route: 'order-pf'` → `'order-new'` (потому что `'order-pf'` мы дропнули в A5).

**Проверить:** убедиться, что вёрстка каталога не ломается при единственной карточке (CSS grid с 1 элементом).

## Wave C — пост-релизный чек-лист (НЕ в этом проходе)

После того как `dev` зальётся в `main` и одношагово отработают миграции:

- [ ] Удалить `scripts/migrate_dates_to_iso.py`
- [ ] Удалить `scripts/migrate_guest_orders.py`
- [ ] Удалить `scripts/migrate_phase2.py`
- [ ] Удалить `scripts/migrate_phase3.py`
- [ ] Удалить `scripts/seed_load_test_orders.py` (если не используется на постоянке для load-тестов)
- [ ] Удалить legacy-drop старой таблицы в `utils/sqlite3.py:1023`
- [ ] Удалить legacy-парсер `dd.mm.yyyy` в `utils/dates.py:20-43` (после проверки `SELECT created_at FROM orders` на проде — все в ISO?)
- [ ] Удалить fallback `_parseLegacy` в `web/static/dates.js:56-57`
- [ ] Удалить legacy-комментарий в `web/admin_deps.py:3-5` (или подтвердить, что shared-with-bot settings table reading исчезло)

Этот раздел остаётся в репо как чеклист для будущего PR.

## Стратегия исполнения

- Работаем на ветке `dev`.
- **Один коммит — одна логическая единица.** Wave A1, A2, A3 ... B7, B8 — каждое атомарным коммитом. Это позволит откатить любой пункт без распутывания.
- **Порядок:** Wave A целиком, потом Wave B. Внутри волны — независимые пункты можно делать в любом порядке.
- **Верификация после каждого коммита:**
  - `docker exec api pytest` — все тесты зелёные (per memory rule)
  - `docker compose up` — бот стартует, веб-API стартует
  - Для Wave B8 (Cabinet) и A5 (order-pf alias) — проверить SPA в браузере на mobile + desktop (per memory rule про responsive)
- **PR:** один PR `dev` → ... (пока не в `main`) с серией атомарных коммитов; в описании — этот spec.

## Что считать готовым

- `lending.html` нет в репо.
- В `handlers/__init__.py` нет `seo`, `reviews`. Файлов `handlers/seo.py`, `handlers/reviews.py` нет.
- В `handlers/pf_order.py` нет хандлеров `yandex_pf`, `review_bonus`.
- В `handlers/commands.py` нет хандлера `qna_avito` (text_startswith).
- В `handlers/admin_orders.py` нет хандлера `to_general_user_report`.
- В `web/routers/auth_email.py` нет POST `/register` (только `/register-request` и `/register-verify`).
- В `web/static/app.jsx` нет `'order-pf'`-роута и legacy callsite handling.
- В `web/static/components/Cabinet.jsx` `SERVICES` содержит ровно один элемент (`pf`).
- В `keyboards/inline_keyboards.py` и `keyboards/users_menu.py` нет закомментированных кнопочных блоков и нет `seo_boost_kb`.
- В `utils/other_functions.py` остались только три используемые функции (`get_user_string_without_first_name`, `get_days_suffix`, `format_decimal`).
- В `design.py` нет перечисленных в B7 строковых констант.
- `docker exec api pytest` — зелёные.
- Бот стартует без `ImportError`.
- LK SPA рендерит каталог из одного элемента (ПФ), форма заказа открывается, оплата проходит.

## Известные риски

- **Risk:** `tarifs_kb`/`pf_kb` в `keyboards/users_menu.py` могут случайно содержать кнопки на не-ПФ услуги. Если механически удалить — может слететь основной флоу.
  - **Mitigation:** перед правкой прочитать эти функции, удалять только non-PF элементы.
- **Risk:** `get_string('btn_*')` тянет значения из `settings`-таблицы БД. Если ключ удалить из БД, но забыть из кода — `KeyError` в рантайме. И наоборот.
  - **Mitigation:** для каждой удаляемой кнопки сделать `grep get_string` по репо, убедиться что ключ нигде не зовётся; ключ из БД удалять отдельной миграцией, либо оставить (будут «осиротевшие настройки», но без падений).
- **Risk:** в `design.py` имена `q1`–`q4` слишком короткие — грeп даст ложные срабатывания.
  - **Mitigation:** грeпать с границами слова: `\bq1\b`, и проверять каждый матч глазами.
- **Risk:** удалить `handlers/seo.py` ломает что-то непрямое, например, поле БД `seo_*` (если такое есть).
  - **Mitigation:** после удаления — старт бота + старт API + прогон тестов. Если падает миграция БД — фиксим до коммита.

## Метрика результата

- `find . -name '*.py' -not -path './.*' -not -path '*/tests/*' | xargs wc -l` до/после.
- Ожидаемый объём — снос ≥2000 строк Python + 646 KB HTML.
