# Admin «Test auto-dispatch» Button — Design

**Date:** 2026-06-09
**Status:** Draft
**Builds on:** [2026-06-08-pf-executor-auto-mode-design.md](2026-06-08-pf-executor-auto-mode-design.md)

## 1. Цель

Дать админу способ **точечно** проверить, как auto-режим отработает на одном
конкретном заказе — без включения `PF_AUTO_DISPATCH_ENABLED` глобально и без
ожидания, пока новый заказ оплатится. Это нужно для безопасного rollout:
проверить пару пограничных кейсов (известный ad / неизвестный ad / разные
длительности) на проде до того, как трафик пойдёт через auto-mode для всех
заказов.

## 2. Скоуп

**В скоупе:**
- Новая кнопка `🧪 Test auto` в `orders_kb()` (подменю «📖 Заказы» в `/admin`).
- FSM-handler в `handlers/admin_orders.py` для flow
  `ID → preview → confirm → result`.
- Два публичных helper'а в `services/order_links_dispatcher.py`:
  - `classify_for_preview(order_id) -> list[LinkPreview]` — dry-run: классифицирует
    каждую pending-ссылку, **игнорируя** `PF_AUTO_DISPATCH_ENABLED`. Ничего не
    меняет в БД, ничего не шлёт в API.
  - `force_dispatch(order_id, link_ids) -> list[DispatchResult]` — реально шлёт
    отобранные ссылки в biza через штатный `submit_link` → `mark_in_work`.
    Игнорирует feature-flag только в части classifier-gate; submit_link и
    транзакционные гарантии — без изменений.
- Friendly-сообщение когда кэш пустой (с подсказкой как запустить backfill).
- Unit-тесты на оба helper'а + handler-тесты на FSM-переходы.

**Out of scope:**
- Backfill cache из админ-бота. Это разовая ops-операция через
  `scripts/backfill_avito_phrase_cache.py --days 90`, не кнопка.
- Cost-estimation (₽). Не показываем; админ сам знает прайс. Helper'ы тоже
  не считают.
- Веб-админка. Только Telegram-бот. Если веб-админка понадобится — отдельной
  задачей.
- Per-link выбор (админ галочками выбирает какие именно отправить).
  Подтверждаем всё что классификатор отметил `auto`, остальное оставляем в
  manual. Гранулярность можно добавить позже если потребуется.
- Расширение log-формата `metric.auto_rate` для отделения test-dispatch от
  органического трафика.

## 3. Архитектура

### 3.1. Сервисный слой

В `services/order_links_dispatcher.py` появляются два метода + dataclass для
структурированных результатов:

```python
@dataclass
class LinkPreview:
    link_id: int
    url: str
    ad_id: str | None
    decision: str       # 'auto' | 'manual'
    reason: str         # 'cache_hit' | 'cache_miss' | 'no_ad_id'
                        # (без 'feature_off' — мы его игнорируем)
    phrase: str | None  # set только когда decision='auto'
    deadline_at: str | None  # ISO; только для 'auto', через compute_deadline


@dataclass
class DispatchResult:
    link_id: int
    success: bool
    external_id: str | None
    error: str | None   # human-readable, для admin message


def classify_for_preview(order_id: int) -> list[LinkPreview]:
    """Dry-run классификация всех pending-ссылок заказа.

    Возвращает список с разбором каждой ссылки. НЕ трогает БД, НЕ шлёт
    HTTP. Игнорирует PF_AUTO_DISPATCH_ENABLED (всегда смотрит в кэш).

    Raises OrderNotFound если order_id не существует.
    """


def force_dispatch(order_id: int, link_ids: list[int]) -> list[DispatchResult]:
    """Реальный dispatch указанных ссылок (subset из classify_for_preview).

    Только pending-ссылки этого заказа из link_ids идут в API.
    Использует штатный submit_link + mark_in_work.

    Ошибки на отдельных ссылках не валят остальные.

    Raises OrderNotFound если order_id не существует.
    """
```

**`classify_for_preview` устроен так:**

1. SELECT order по id.
2. SELECT all `pending` order_links.
3. Для каждой:
   - `ad_id = extract_ad_id(url)`
   - `phrase = cache_lookup(ad_id)` (если ad_id не None)
   - Решение: `auto` если phrase найден, иначе `manual`. **Без** проверки
     feature-flag.
   - Если auto → `deadline_at = compute_deadline(order)` (статичен по
     order, не по link).
   - Reason: `no_ad_id` если ad_id не извлекся, `cache_miss` если ad_id
     есть но cache пустой, `cache_hit` если phrase найден.
4. Логи: не emit'ит `classifier.decision` (это не дисптачер call), но
   emit'ит `classifier.preview link=… ad=… decision=… reason=…` для
   аудита.

**`force_dispatch` устроен так:**

1. SELECT order + targeted pending links (with `link_id IN (...)`).
2. Для каждой ссылки:
   - `mode, phrase = classify(url, order, link_id=link_id, force=True)` —
     добавляем новый kwarg `force` в `classify` (см. 3.2).
   - Если `mode == 'manual'` — пропускаем (странный кейс: между preview и
     confirm кэш изменился; включаем в результат как `success=False,
     error='classifier теперь manual'`).
   - Если `mode == 'auto'`:
     - `external_id = submit_link(url, order, search_phrase=phrase)`
     - `mark_in_work(link_id, delivery_mode='auto', ...)`
     - Записываем `DispatchResult(success=True, external_id=...)`.
   - На `ExecutorAPIRejected` — `DispatchResult(success=False, error="API
     отказал: <текст>")`. **Не** flip'аем link в manual здесь — это
     осознанно: Test auto — диагностический инструмент, состояние ссылки
     остаётся как было (`pending` + `delivery_mode='auto'`). Если штатный
     dispatcher включат, он отработает по своим правилам (fallback в manual
     на Rejected).
   - На `ExecutorAPIError` — `DispatchResult(success=False, error="API
     временная ошибка: <текст>")`. Link не трогаем.

### 3.2. Расширение classifier'а

`services/order_links_classifier.py::classify` получает один новый
keyword-only параметр:

```python
def classify(
    url: str, order: dict, *,
    link_id: int | None = None,
    force: bool = False,  # NEW
) -> tuple[str, str | None]:
    """...
    force=True — игнорировать PF_AUTO_DISPATCH_ENABLED. Используется
    только админ-handler'ом 'Test auto-dispatch'; штатный dispatcher
    всегда зовёт с force=False.
    """
    if not force and not config.PF_AUTO_DISPATCH_ENABLED:
        _log(link_id, None, "manual", "feature_off")
        return "manual", None
    ...
```

Все существующие call-sites дёргают без `force` → дефолт `False` → старое
поведение.

### 3.3. Handler

Новый callback `test_auto_dispatch` в `handlers/admin_orders.py`. Структура
follows `fail_order` (паттерн уже принят в этом файле):

```
States.pf_test_auto_dispatch_id        — ждём order_id
States.pf_test_auto_dispatch_confirm   — preview показан, ждём кнопку
```

**Flow:**

1. Callback `test_auto_dispatch` → enter state `pf_test_auto_dispatch_id`,
   reply «Введите ID заказа:» с back-кнопкой.

2. На message в этом state:
   - Парсим order_id. Невалидно → «Невалидный ID, попробуй ещё раз»,
     остаёмся в state.
   - SELECT order. Не найден → «Заказ не найден», state cleared.
   - Order.status != 'paid' → «Заказ в статусе X, тестировать можно только
     paid-заказы», state cleared.
   - `previews = classify_for_preview(order_id)`
   - Если pending-ссылок нет → «У заказа нет pending-ссылок, нечего
     тестить», state cleared.
   - Считаем `n_auto = sum(1 for p in previews if p.decision=='auto')`.
   - Если `n_auto == 0` И кэш реально пуст (`last_refreshed_at() is
     None`) → friendly «Кэш пуст, запусти backfill: docker compose exec
     api python -m scripts.backfill_avito_phrase_cache --days 90». state
     cleared.
   - Иначе формируем preview-сообщение (см. 4.1) с кнопками
     `[✅ Подтвердить] [❌ Отмена]`.
   - Сохраняем `previews` в FSM-state (только `link_id`'ы auto-ссылок
     достаточно — `auto_link_ids: list[int]`).
   - Enter `pf_test_auto_dispatch_confirm`.

3. Callback `test_auto_dispatch_confirm`:
   - Берём `auto_link_ids` из state.
   - `results = force_dispatch(order_id, auto_link_ids)`
   - Формируем result-сообщение (см. 4.2).
   - Edit message в этом же chat (replace preview на result), убрать
     кнопки.
   - state cleared.

4. Callback `test_auto_dispatch_cancel`:
   - «Отменено».
   - state cleared.

### 3.4. Кнопка в `orders_kb()`

В `keyboards/inline_keyboards.py::orders_kb()` добавляется новый row перед
`main_menu`:

```python
keyboard.row(
    InlineKeyboardButton(
        text="🧪 Test auto",
        callback_data="test_auto_dispatch"
    )
)
```

## 4. UX

### 4.1. Preview-сообщение

```
🧪 Test auto-dispatch для #99431

Будет обработано: 2 ссылки

1. avito.ru/.../bmw_8048793719
   ├ ad_id: 8048793719
   ├ classifier: ✅ AUTO (cache hit)
   ├ phrase: 'купить квартиру москва'
   └ deadline: 2026-06-12

2. avito.ru/.../lada_2222333344
   ├ ad_id: 2222333344
   ├ classifier: ❌ MANUAL (cache_miss)
   └ останется pending+manual

⚠️ Будет реально отправлено 1 ссылка в biza.

[✅ Подтвердить и отправить] [❌ Отмена]
```

**Структура каждого блока:**
- 1-я строка: URL (полный — без обрезания, в `<code>` для не-кликабельности
  и компактности).
- `ad_id`: либо извлечённый id, либо `—` если не выделился.
- `classifier`: «✅ AUTO (cause)» или «❌ MANUAL (cause)». Cause = reason
  code, понятным русским словом.
- Третья строка зависит от decision:
  - AUTO: `phrase: '<text>'` (single-quoted, может быть длинным URL).
  - MANUAL: `останется pending+manual`.
- AUTO дополнительно: `deadline: <iso date>` (без времени, день).

**Длинные phrase-URL:** при попадании в Telegram message limit (4096 chars)
помечаем заметкой «(URL длинная, см. логи)» и логируем полную фразу. На
типичных кейсах помещается.

### 4.2. Result-сообщение

После confirm — edit preview в:

```
✅ Test auto-dispatch для #99431 завершён

Отправлено: 1 / 1

1. avito.ru/.../bmw_8048793719
   ✅ AUTO, external_id=357901, in_work до 2026-06-12

2. avito.ru/.../lada_2222333344
   ⏸ MANUAL (не отправлялось)
```

Если что-то упало:

```
⚠️ Test auto-dispatch для #99431 завершён

Отправлено: 0 / 1

1. avito.ru/.../bmw_8048793719
   ❌ Ошибка: API ответил 400 (invalid url)
   (ссылка осталась pending+auto; если PF_AUTO_DISPATCH_ENABLED
   включён, dispatcher повторит)
```

### 4.3. Пустой кэш — friendly fallback

```
📭 Кэш фраз пустой.

Все 2 ссылки заказа #99431 ушли бы в MANUAL потому что в локальной
БД нет ни одной известной фразы для их ad_id.

Запусти backfill один раз, потом попробуй снова:

  docker compose exec api python -m \
      scripts.backfill_avito_phrase_cache --days 90

После backfill дневной refresh-loop поддерживает кэш свежим.
```

### 4.4. Edge cases

| Сценарий | Поведение |
|---|---|
| ID невалидный (буквы и т.п.) | «Невалидный ID, попробуй ещё раз», state stays |
| Заказ не найден | «Заказ не найден», state cleared |
| Order.status ≠ paid | «Заказ в статусе X, тестировать можно только paid» |
| 0 pending-ссылок | «У заказа нет pending-ссылок, нечего тестить» |
| Все ссылки → manual И кэш пуст | Friendly fallback (4.3) |
| Все ссылки → manual И кэш не пуст | Показываем preview как обычно, но кнопка «Подтвердить» disabled и заметка «Все ссылки → MANUAL, отправлять нечего» (можно убрать confirm row совсем) |
| Между preview и confirm одна из ссылок успела стать in_work (race с штатным dispatcher) | `force_dispatch` skips её, `DispatchResult(success=False, error="уже не pending")` |
| `submit_link` поднимает `ExecutorAPIRejected` | `DispatchResult(success=False, error="API отказал")`; link остаётся pending+auto |

## 5. Тестирование

### Unit

**`tests/unit/test_classify_for_preview.py`:**
- Пустой заказ (0 pending) → пустой list.
- Заказ с 2 ссылками, одна в кэше, одна нет → один auto + один manual.
- Игнорит `PF_AUTO_DISPATCH_ENABLED=False` (mock'аем флаг false → всё равно
  смотрит в кэш).
- Логирует `classifier.preview` для каждой ссылки.
- Не вызывает `submit_link` (mock'аем — assert not called).

**`tests/unit/test_force_dispatch.py`:**
- Empty link_ids → empty list.
- Success path: 1 auto-ссылка → `submit_link` mock возвращает external_id
  → `mark_in_work` вызывается → результат success=True.
- `ExecutorAPIRejected` на одной из 2 ссылок → одна success, другая
  success=False с error.
- Race: ссылка уже in_work → success=False, error="уже не pending".
- Игнорирует `PF_AUTO_DISPATCH_ENABLED=False`.

**`tests/unit/test_order_links_classifier_force.py`:**
- `classify(force=True)` с `PF_AUTO_DISPATCH_ENABLED=False` → если кэш hit,
  возвращает auto.

### Handler тесты

**`tests/unit/test_admin_test_auto_dispatch.py`:**
- Callback `test_auto_dispatch` → state enter, ask for ID.
- Невалидный ID → error message, state stays.
- Order not found → error, state cleared.
- Order.status='unpaid' → error, state cleared.
- Successful preview (cache has phrase) → preview message с кнопками.
- Confirm callback → `force_dispatch` вызывается, result message.
- Cancel callback → cancelled.
- Empty cache fallback message.

Покрытие mock-style через `aiogram.test`-pattern, который уже используется
для других admin-handler'ов в проекте.

## 6. Migrations / Rollout

Никаких schema-миграций. Все таблицы (`order_links`, `avito_ad_phrase_cache`)
уже есть.

**Деплой:**
1. Merge feature-branch в dev → push origin.
2. Прод подтянет через `git pull dev` + `docker compose up -d
   --force-recreate api bot`.
3. Кнопка появится в админ-меню сразу после рестарта бота — никакого
   мигратора.
4. Если кэш пуст (типичный day-0 case) — Test auto покажет friendly
   fallback. Backfill запускается отдельным шагом руками когда админ
   решит включать auto-mode.

## 7. Открытые вопросы

1. **Длинный URL фразы.** Если фраза-URL длинная (>200 chars), preview
   message может стать на грани лимита Telegram. Решение: truncate URL
   до N chars в preview, полную фразу логировать. Покрывается в реализации
   очевидно.
2. **`fail_order`-стиль конфирма vs inline-кнопки.** Текущий `fail_order` в
   проекте использует FSM с текстовыми ответами, наш дизайн — inline
   кнопки. Это OK, ничего не ломает; но если хочешь единообразия — можно
   переписать на текстовые. Лично думаю inline кнопки удобнее для preview.
3. **Локализация reason codes.** В preview русские слова («cache hit»,
   «cache miss», «no_ad_id»). Можно сделать чисто русский («есть в кэше»,
   «нет в кэше», «ad_id не выделился»). Решим в плане.
