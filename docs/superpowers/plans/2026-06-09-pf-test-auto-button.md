# Admin «Test auto-dispatch» Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-order safe-test button «🧪 Test auto» in the bot admin
`orders_kb()` submenu. Lets admin classify+submit one specific paid order
through the auto-mode path without flipping `PF_AUTO_DISPATCH_ENABLED`
globally — for safe rollout (try a few edge cases on prod before enabling
auto-mode for the whole stream).

**Architecture:** Two new helpers in `services/order_links_dispatcher.py`
(`classify_for_preview` for dry-run, `force_dispatch` for real submit on a
subset). One new keyword-only param `force=` on the classifier to bypass
the feature-flag gate. New FSM in `handlers/admin_orders.py` mirroring the
`MarkManual` pattern (inline confirm buttons). New row in `orders_kb()`.

**Tech Stack:** Python 3.11 · aiogram 2 · SQLite · pytest.

**Spec:** [docs/superpowers/specs/2026-06-09-pf-test-auto-button-design.md](../specs/2026-06-09-pf-test-auto-button-design.md)

**Tests:** All pytest runs go through the project's docker api image with
the worktree mounted (per MEMORY/feedback_docker_tests). Command:

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest <path> -v
```

The image name `pf-test-auto-button-api` is what `docker compose build api`
produces in this worktree (docker-compose derives image name from the
worktree directory name). If a different name is observed locally
(`docker images | grep -api`), substitute accordingly.

Before Task 1: build the image once:

```bash
cd /Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot/.claude/worktrees/pf-test-auto-button
docker compose build api
```

---

## File Structure

**Create:**
- `tests/unit/test_order_links_classifier_force.py` — `force=` kwarg coverage.
- `tests/unit/test_classify_for_preview.py` — dry-run helper.
- `tests/unit/test_force_dispatch.py` — real-dispatch helper.
- `tests/unit/test_test_auto_format.py` — preview/result text formatters.
- `tests/unit/test_admin_test_auto_dispatch.py` — handler/FSM tests.
- `utils/test_auto_format.py` — pure formatter functions (preview/result text).

**Modify:**
- `services/order_links_classifier.py` — add `force: bool = False` kwarg.
- `services/order_links_dispatcher.py` — add `LinkPreview`, `DispatchResult`,
  `classify_for_preview`, `force_dispatch`.
- `handlers/admin_orders.py` — add `TestAutoDispatch` states + 4 handlers
  (prompt / collect_id / confirm / cancel).
- `keyboards/inline_keyboards.py` — add «🧪 Test auto» row in `orders_kb()`.

---

## Task 1: `force=True` kwarg in classifier

**Files:**
- Modify: `services/order_links_classifier.py`
- Create: `tests/unit/test_order_links_classifier_force.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_order_links_classifier_force.py`:

```python
"""Classifier `force=True` kwarg — bypasses feature flag gate."""
from unittest.mock import patch
from services.order_links_classifier import classify


def _order():
    return {"position_name": "3/10"}


def test_force_true_bypasses_feature_off_when_cache_hit(tmp_db):
    """force=True + кэш есть → auto даже когда фича выключена."""
    from services.avito_phrase_cache import upsert_many
    upsert_many([{
        "ad_id": "1234567890",
        "search_link": "купить квартиру",
        "created_at": "2026-06-01 12:00",
    }])

    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               False):
        mode, phrase = classify(
            "https://avito.ru/x_1234567890",
            _order(), link_id=99, force=True,
        )

    assert mode == "auto"
    assert phrase == "купить квартиру"


def test_force_true_returns_manual_when_no_ad_id(tmp_db):
    """force=True не магически делает auto без ad_id."""
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               False):
        mode, phrase = classify(
            "https://example.com/no_ad", _order(),
            link_id=99, force=True,
        )

    assert mode == "manual"
    assert phrase is None


def test_force_true_returns_manual_when_cache_miss(tmp_db):
    """force=True + кэш пуст → manual (cache_miss)."""
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               False):
        mode, phrase = classify(
            "https://avito.ru/x_1234567890", _order(),
            link_id=99, force=True,
        )

    assert mode == "manual"
    assert phrase is None


def test_force_false_respects_feature_off(tmp_db):
    """force=False (дефолт) + фича выключена → manual независимо от кэша."""
    from services.avito_phrase_cache import upsert_many
    upsert_many([{
        "ad_id": "1234567890",
        "search_link": "купить",
        "created_at": "2026-06-01 12:00",
    }])

    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               False):
        mode, phrase = classify(
            "https://avito.ru/x_1234567890",
            _order(), link_id=99,  # force=False default
        )

    assert mode == "manual"
    assert phrase is None
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_order_links_classifier_force.py -v
```

Expected: 3 of 4 fail (the `force=True` keyword is not yet accepted, so
`TypeError: classify() got an unexpected keyword argument 'force'`). The
4th test (`force=False`) may pass by accident.

- [ ] **Step 3: Add the kwarg**

In `services/order_links_classifier.py`, change the `classify` signature
from:

```python
def classify(url: str, order: dict, *, link_id: int | None = None) \
        -> tuple[str, str | None]:
```

to:

```python
def classify(url: str, order: dict, *,
             link_id: int | None = None,
             force: bool = False) \
        -> tuple[str, str | None]:
```

And change the first guard from:

```python
    if not config.PF_AUTO_DISPATCH_ENABLED:
        _log(link_id, None, "manual", "feature_off")
        return "manual", None
```

to:

```python
    if not force and not config.PF_AUTO_DISPATCH_ENABLED:
        _log(link_id, None, "manual", "feature_off")
        return "manual", None
```

Update the docstring to mention `force`:

```python
    """Решает auto/manual для ссылки.

    Возвращает (mode, phrase | None).
    Phrase != None только когда mode='auto'.

    `link_id` — для логов; ничего не меняет в логике.
    `force` — игнорировать PF_AUTO_DISPATCH_ENABLED. Используется только
    админ-handler'ом «Test auto-dispatch». Штатный dispatcher всегда зовёт
    с force=False (дефолт).
    """
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_order_links_classifier_force.py -v
```

All 4 tests should pass.

Also re-run existing classifier tests to make sure nothing broke:

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_order_links_classifier_cache.py -v
```

All 4 pre-existing tests should still pass (`force` defaults to False).

- [ ] **Step 5: Commit**

```bash
git add services/order_links_classifier.py \
        tests/unit/test_order_links_classifier_force.py
git commit -m "$(cat <<'EOF'
feat(test-auto): classifier force=True bypasses feature flag

Adds keyword-only `force` param to classify(). When True, the
PF_AUTO_DISPATCH_ENABLED gate is ignored — used by the upcoming
admin "Test auto-dispatch" button to classify a specific order
without flipping the global flag.

Default False — all existing call sites are unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Dataclasses + `classify_for_preview`

**Files:**
- Modify: `services/order_links_dispatcher.py`
- Create: `tests/unit/test_classify_for_preview.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_classify_for_preview.py`:

```python
"""classify_for_preview — dry-run классификация заказа для admin Test auto."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed_paid_order(tmp_db, urls):
    """Создать paid-заказ с pending ссылками."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, "
            "start_date, date) VALUES (1, 100, '3/10', 'paid', NULL, ?)",
            (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=urls)
        con.commit()
    return order_id


def test_classify_for_preview_empty_order(tmp_db):
    """Заказ без pending-ссылок (например все done) → пустой list."""
    from services.order_links_dispatcher import classify_for_preview
    order_id = _seed_paid_order(tmp_db, urls=[])
    previews = classify_for_preview(order_id)
    assert previews == []


def test_classify_for_preview_mixed_cache(tmp_db):
    """Заказ с 2 ссылками: одна в кэше, одна нет."""
    from services.order_links_dispatcher import classify_for_preview
    from services.avito_phrase_cache import upsert_many

    upsert_many([{
        "ad_id": "1234567890",
        "search_link": "купить квартиру",
        "created_at": "2026-06-01 12:00",
    }])
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://avito.ru/x_1234567890",      # in cache
        "https://avito.ru/y_9999999999",      # not in cache
    ])

    previews = classify_for_preview(order_id)
    assert len(previews) == 2

    auto = next(p for p in previews if p.decision == "auto")
    assert auto.ad_id == "1234567890"
    assert auto.phrase == "купить квартиру"
    assert auto.reason == "cache_hit"
    assert auto.deadline_at is not None  # ISO string

    manual = next(p for p in previews if p.decision == "manual")
    assert manual.ad_id == "9999999999"
    assert manual.phrase is None
    assert manual.reason == "cache_miss"
    assert manual.deadline_at is None


def test_classify_for_preview_no_ad_id(tmp_db):
    """URL без извлекаемого ad_id → manual / no_ad_id."""
    from services.order_links_dispatcher import classify_for_preview
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://example.com/no_ad",
    ])

    previews = classify_for_preview(order_id)
    assert len(previews) == 1
    assert previews[0].decision == "manual"
    assert previews[0].reason == "no_ad_id"
    assert previews[0].ad_id is None


def test_classify_for_preview_ignores_feature_flag(tmp_db):
    """PF_AUTO_DISPATCH_ENABLED=False — всё равно классифицируем по кэшу."""
    from services.order_links_dispatcher import classify_for_preview
    from services.avito_phrase_cache import upsert_many

    upsert_many([{
        "ad_id": "1234567890",
        "search_link": "купить",
        "created_at": "2026-06-01 12:00",
    }])
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://avito.ru/x_1234567890",
    ])

    with patch(
        "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
        False,
    ):
        previews = classify_for_preview(order_id)

    assert previews[0].decision == "auto"
    assert previews[0].phrase == "купить"


def test_classify_for_preview_does_not_submit(tmp_db):
    """Не дёргает submit_link, mark_in_work и не меняет БД."""
    from services.order_links_dispatcher import classify_for_preview
    from services.avito_phrase_cache import upsert_many
    from services.order_links import list_links

    upsert_many([{
        "ad_id": "1234567890",
        "search_link": "x",
        "created_at": "2026-06-01 12:00",
    }])
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://avito.ru/x_1234567890",
    ])

    with patch("services.order_links_dispatcher.submit_link") as submit, \
         patch(
             "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
             True,
         ):
        classify_for_preview(order_id)

    submit.assert_not_called()

    # link остался pending+NULL (никаких mutations)
    links = list_links(order_id)
    assert links[0]["status"] == "pending"
    assert links[0]["delivery_mode"] is None


def test_classify_for_preview_raises_when_order_not_found(tmp_db):
    """Несуществующий order_id → OrderNotFound."""
    from services.order_links_dispatcher import classify_for_preview
    from services.exceptions import OrderNotFound
    import pytest
    with pytest.raises(OrderNotFound):
        classify_for_preview(99999)
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_classify_for_preview.py -v
```

Expected: 6 fails with `ImportError: cannot import name 'classify_for_preview'`.

- [ ] **Step 3: Implement the helper**

In `services/order_links_dispatcher.py` add at the top (after existing
imports):

```python
from dataclasses import dataclass
from services.avito_phrase_cache import lookup as cache_lookup
from services.avito_url import extract_ad_id
from services.exceptions import OrderNotFound
from services.order_links import compute_deadline
from services.order_links_classifier import classify
```

(some of these may already be imported — keep imports unique.)

Then add the dataclasses and helper near the end of the module (before
`run_dispatcher_loop`):

```python
@dataclass
class LinkPreview:
    """Per-link классификация для admin Test auto preview."""
    link_id: int
    url: str
    ad_id: str | None
    decision: str       # 'auto' | 'manual'
    reason: str         # 'cache_hit' | 'cache_miss' | 'no_ad_id'
    phrase: str | None  # set только когда decision='auto'
    deadline_at: str | None  # ISO; только для auto


def classify_for_preview(order_id: int) -> list[LinkPreview]:
    """Dry-run классификация всех pending-ссылок заказа.

    Не трогает БД, не шлёт HTTP. Игнорирует PF_AUTO_DISPATCH_ENABLED
    (всегда смотрит в кэш). Используется admin Test auto handler'ом для
    preview перед confirm.

    Raises OrderNotFound если order_id не существует.
    """
    with connect() as con:
        order_row = con.execute(
            "SELECT * FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
        if order_row is None:
            raise OrderNotFound(f"order_id={order_id}")
        order = dict(order_row)

        rows = con.execute(
            "SELECT id, url FROM order_links "
            "WHERE order_id=? AND status='pending' ORDER BY id",
            (order_id,),
        ).fetchall()
        link_rows = [(int(r["id"]), r["url"]) for r in rows]

    previews: list[LinkPreview] = []
    for link_id, url in link_rows:
        ad_id = extract_ad_id(url)
        if ad_id is None:
            previews.append(LinkPreview(
                link_id=link_id, url=url, ad_id=None,
                decision="manual", reason="no_ad_id",
                phrase=None, deadline_at=None,
            ))
            logger.info(
                "classifier.preview link=%s ad=none decision=manual reason=no_ad_id",
                link_id,
            )
            continue

        phrase = cache_lookup(ad_id)
        if not phrase:
            previews.append(LinkPreview(
                link_id=link_id, url=url, ad_id=ad_id,
                decision="manual", reason="cache_miss",
                phrase=None, deadline_at=None,
            ))
            logger.info(
                "classifier.preview link=%s ad=%s decision=manual reason=cache_miss",
                link_id, ad_id,
            )
            continue

        deadline = compute_deadline(order)
        previews.append(LinkPreview(
            link_id=link_id, url=url, ad_id=ad_id,
            decision="auto", reason="cache_hit",
            phrase=phrase, deadline_at=deadline,
        ))
        logger.info(
            "classifier.preview link=%s ad=%s decision=auto reason=cache_hit",
            link_id, ad_id,
        )

    return previews
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_classify_for_preview.py -v
```

All 6 tests pass.

Also re-run dispatcher tests:

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_order_links_dispatcher.py \
           tests/unit/test_order_links_dispatcher_retry.py -v
```

All existing dispatcher tests still pass.

- [ ] **Step 5: Commit**

```bash
git add services/order_links_dispatcher.py \
        tests/unit/test_classify_for_preview.py
git commit -m "$(cat <<'EOF'
feat(test-auto): classify_for_preview dry-run helper

LinkPreview dataclass + classify_for_preview(order_id) — used by
admin Test auto button to preview the per-link classifier decision
before any real submit. Ignores PF_AUTO_DISPATCH_ENABLED, never
mutates the DB, never calls submit_link.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `force_dispatch` real submit helper

**Files:**
- Modify: `services/order_links_dispatcher.py`
- Create: `tests/unit/test_force_dispatch.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_force_dispatch.py`:

```python
"""force_dispatch — реальный submit для admin Test auto confirm."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.exceptions import ExecutorAPIError, ExecutorAPIRejected
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_paid_order(tmp_db, urls):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, "
            "start_date, date) VALUES (1, 100, '3/10', 'paid', NULL, ?)",
            (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=urls)
        con.commit()
    return order_id


def _seed_phrase(ad_id, phrase):
    from services.avito_phrase_cache import upsert_many
    upsert_many([{
        "ad_id": ad_id, "search_link": phrase,
        "created_at": "2026-06-01 12:00",
    }])


def test_force_dispatch_empty_link_ids(tmp_db):
    """link_ids пуст → возвращает пустой list."""
    from services.order_links_dispatcher import force_dispatch
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    results = force_dispatch(order_id, link_ids=[])
    assert results == []


def test_force_dispatch_success_path(tmp_db):
    """Cache hit + submit OK → in_work, delivery_mode=auto, external_id."""
    from services.order_links_dispatcher import force_dispatch
    _seed_phrase("1234567890", "купить квартиру")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    with patch("services.order_links_dispatcher.submit_link",
               return_value="ext-42") as submit:
        results = force_dispatch(order_id, link_ids=[link_id])

    assert len(results) == 1
    r = results[0]
    assert r.success is True
    assert r.external_id == "ext-42"
    assert r.error is None

    # link мутировал в in_work / auto / external_id
    link = list_links(order_id)[0]
    assert link["status"] == "in_work"
    assert link["delivery_mode"] == "auto"
    assert link["external_id"] == "ext-42"

    # submit_link был вызван с правильной phrase
    args, kwargs = submit.call_args
    assert kwargs["search_phrase"] == "купить квартиру"


def test_force_dispatch_executor_rejected_keeps_pending(tmp_db):
    """API Rejected → success=False, link остаётся pending (не flip в manual)."""
    from services.order_links_dispatcher import force_dispatch
    _seed_phrase("1234567890", "x")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    with patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIRejected("400 invalid")):
        results = force_dispatch(order_id, link_ids=[link_id])

    assert len(results) == 1
    assert results[0].success is False
    assert "API отказал" in results[0].error
    assert results[0].external_id is None

    # link остался pending — Test auto осознанно не flip'ает
    link = list_links(order_id)[0]
    assert link["status"] == "pending"


def test_force_dispatch_executor_error_keeps_pending(tmp_db):
    """API временная ошибка → success=False, link не трогаем."""
    from services.order_links_dispatcher import force_dispatch
    _seed_phrase("1234567890", "x")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    with patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("429 rate")):
        results = force_dispatch(order_id, link_ids=[link_id])

    assert results[0].success is False
    assert "временная" in results[0].error
    assert list_links(order_id)[0]["status"] == "pending"


def test_force_dispatch_skips_non_pending(tmp_db):
    """Если ссылка уже in_work — success=False, error 'уже не pending'."""
    from services.order_links_dispatcher import force_dispatch
    from services.order_links import mark_in_work
    _seed_phrase("1234567890", "x")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    # transition link to in_work first
    mark_in_work(link_id, delivery_mode="manual",
                 deadline_at="2099-01-01T00:00:00+00:00")

    with patch("services.order_links_dispatcher.submit_link") as submit:
        results = force_dispatch(order_id, link_ids=[link_id])

    assert results[0].success is False
    assert "не pending" in results[0].error
    submit.assert_not_called()


def test_force_dispatch_ignores_feature_flag(tmp_db):
    """PF_AUTO_DISPATCH_ENABLED=False — всё равно отправляет."""
    from services.order_links_dispatcher import force_dispatch
    _seed_phrase("1234567890", "x")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    with patch(
        "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
        False,
    ), patch("services.order_links_dispatcher.submit_link",
             return_value="ext-77"):
        results = force_dispatch(order_id, link_ids=[link_id])

    assert results[0].success is True
    assert results[0].external_id == "ext-77"
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_force_dispatch.py -v
```

Expected: 6 fails with `ImportError: cannot import name 'force_dispatch'`.

- [ ] **Step 3: Implement the helper**

In `services/order_links_dispatcher.py` (after `classify_for_preview` from
Task 2) add:

```python
@dataclass
class DispatchResult:
    """Per-link результат admin Test auto-dispatch."""
    link_id: int
    success: bool
    external_id: str | None
    error: str | None   # human-readable, для admin message


def force_dispatch(
    order_id: int, link_ids: list[int]
) -> list[DispatchResult]:
    """Реальный dispatch выбранного subset'а pending-ссылок заказа.

    Использует штатные classify(force=True) → submit_link → mark_in_work.
    Игнорирует PF_AUTO_DISPATCH_ENABLED только в classifier-gate;
    submit_link и transaction guarantees — без изменений.

    Ошибки на отдельных ссылках не валят остальные. На Rejected/Error
    ссылка остаётся pending (не flip'аем в manual — Test auto это
    диагностика, не штатный flow).

    Raises OrderNotFound если order_id не существует.
    """
    if not link_ids:
        return []

    with connect() as con:
        order_row = con.execute(
            "SELECT * FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
        if order_row is None:
            raise OrderNotFound(f"order_id={order_id}")
        order = dict(order_row)

        placeholders = ",".join("?" for _ in link_ids)
        rows = con.execute(
            f"SELECT id, url, status FROM order_links "
            f"WHERE order_id=? AND id IN ({placeholders})",
            (order_id, *link_ids),
        ).fetchall()
        link_rows = [(int(r["id"]), r["url"], r["status"]) for r in rows]

    results: list[DispatchResult] = []

    for link_id, url, status in link_rows:
        if status != "pending":
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=None,
                error=f"уже не pending (текущий статус: {status})",
            ))
            continue

        mode, phrase = classify(url, order, link_id=link_id, force=True)
        if mode != "auto" or phrase is None:
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=None,
                error="classifier теперь manual (кэш изменился)",
            ))
            continue

        try:
            external_id = submit_link(url, order, search_phrase=phrase)
        except ExecutorAPIRejected as exc:
            logger.warning("force_dispatch.rejected link=%s err=%s",
                           link_id, exc)
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=None,
                error=f"API отказал: {exc}",
            ))
            continue
        except ExecutorAPIError as exc:
            logger.warning("force_dispatch.api_error link=%s err=%s",
                           link_id, exc)
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=None,
                error=f"API временная ошибка: {exc}",
            ))
            continue

        deadline = compute_deadline(order)
        from services.order_links import mark_in_work
        try:
            mark_in_work(link_id, delivery_mode="auto",
                         deadline_at=deadline, external_id=external_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "force_dispatch.mark_in_work_failed link=%s", link_id,
            )
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=external_id,
                error=f"submit прошёл, но mark_in_work упал: {exc}",
            ))
            continue

        results.append(DispatchResult(
            link_id=link_id, success=True, external_id=external_id,
            error=None,
        ))

    return results
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_force_dispatch.py -v
```

All 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/order_links_dispatcher.py \
        tests/unit/test_force_dispatch.py
git commit -m "$(cat <<'EOF'
feat(test-auto): force_dispatch real-submit helper

DispatchResult dataclass + force_dispatch(order_id, link_ids) —
admin Test auto confirm calls this with the auto-classified subset
of pending links from classify_for_preview. Uses canonical
submit_link + mark_in_work. Ignores PF_AUTO_DISPATCH_ENABLED.

On Rejected/Error the link stays pending (no flip to manual) —
Test auto is a diagnostic tool, not the steady-state dispatcher.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Preview/result text formatters

**Files:**
- Create: `utils/test_auto_format.py`
- Create: `tests/unit/test_test_auto_format.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_test_auto_format.py`:

```python
"""Чистые форматтеры preview/result сообщений для admin Test auto."""
from services.order_links_dispatcher import LinkPreview, DispatchResult


def test_format_preview_two_links_mixed():
    """2 ссылки: одна auto, одна manual."""
    from utils.test_auto_format import format_preview

    previews = [
        LinkPreview(
            link_id=11, url="https://avito.ru/bmw_8048793719",
            ad_id="8048793719", decision="auto", reason="cache_hit",
            phrase="купить квартиру москва",
            deadline_at="2026-06-12T00:00:00+00:00",
        ),
        LinkPreview(
            link_id=12, url="https://avito.ru/lada_2222333344",
            ad_id="2222333344", decision="manual", reason="cache_miss",
            phrase=None, deadline_at=None,
        ),
    ]
    text = format_preview(order_id=99431, previews=previews)

    # Структурные проверки
    assert "99431" in text
    assert "Будет обработано: 2 ссылки" in text
    assert "AUTO" in text
    assert "MANUAL" in text
    assert "8048793719" in text
    assert "2222333344" in text
    assert "купить квартиру москва" in text
    assert "2026-06-12" in text
    # Counter в footer
    assert "Будет реально отправлено 1 ссылка" in text


def test_format_preview_zero_auto():
    """Все ссылки manual → footer указывает что отправлять нечего."""
    from utils.test_auto_format import format_preview

    previews = [
        LinkPreview(
            link_id=11, url="https://avito.ru/x_1111111111",
            ad_id="1111111111", decision="manual", reason="cache_miss",
            phrase=None, deadline_at=None,
        ),
    ]
    text = format_preview(order_id=99432, previews=previews)
    assert "Все ссылки → MANUAL" in text
    assert "отправлять нечего" in text


def test_format_preview_no_ad_id_reason():
    """no_ad_id reason человекочитаемо."""
    from utils.test_auto_format import format_preview

    previews = [
        LinkPreview(
            link_id=11, url="https://example.com/foo",
            ad_id=None, decision="manual", reason="no_ad_id",
            phrase=None, deadline_at=None,
        ),
    ]
    text = format_preview(order_id=99433, previews=previews)
    assert "ad_id не выделился" in text or "no_ad_id" in text


def test_format_result_all_success():
    """Все отправки успешны."""
    from utils.test_auto_format import format_result

    previews = [
        LinkPreview(
            link_id=11, url="https://avito.ru/x_1234567890",
            ad_id="1234567890", decision="auto", reason="cache_hit",
            phrase="купить", deadline_at="2026-06-12T00:00:00+00:00",
        ),
    ]
    results = [
        DispatchResult(link_id=11, success=True,
                       external_id="357901", error=None),
    ]
    text = format_result(order_id=99431, previews=previews, results=results)

    assert "99431" in text
    assert "Отправлено: 1 / 1" in text
    assert "357901" in text
    assert "2026-06-12" in text
    assert "✅" in text


def test_format_result_with_failure():
    """Один success, один failure."""
    from utils.test_auto_format import format_result

    previews = [
        LinkPreview(
            link_id=11, url="https://avito.ru/x_1111111111",
            ad_id="1111111111", decision="auto", reason="cache_hit",
            phrase="a", deadline_at="2026-06-12T00:00:00+00:00",
        ),
        LinkPreview(
            link_id=12, url="https://avito.ru/x_2222222222",
            ad_id="2222222222", decision="auto", reason="cache_hit",
            phrase="b", deadline_at="2026-06-12T00:00:00+00:00",
        ),
    ]
    results = [
        DispatchResult(link_id=11, success=True,
                       external_id="100", error=None),
        DispatchResult(link_id=12, success=False, external_id=None,
                       error="API отказал: 400 invalid"),
    ]
    text = format_result(order_id=99431, previews=previews, results=results)

    assert "Отправлено: 1 / 2" in text
    assert "100" in text
    assert "API отказал" in text
    assert "❌" in text


def test_format_result_includes_manual_links():
    """MANUAL ссылки из preview показываются в результате как 'не отправлялось'."""
    from utils.test_auto_format import format_result

    previews = [
        LinkPreview(
            link_id=11, url="https://avito.ru/x_1111111111",
            ad_id="1111111111", decision="auto", reason="cache_hit",
            phrase="a", deadline_at="2026-06-12T00:00:00+00:00",
        ),
        LinkPreview(
            link_id=12, url="https://avito.ru/x_2222222222",
            ad_id="2222222222", decision="manual", reason="cache_miss",
            phrase=None, deadline_at=None,
        ),
    ]
    results = [
        DispatchResult(link_id=11, success=True,
                       external_id="100", error=None),
    ]
    text = format_result(order_id=99431, previews=previews, results=results)

    assert "MANUAL" in text or "не отправлялось" in text


def test_format_empty_cache_message():
    """Friendly fallback message при пустом кэше."""
    from utils.test_auto_format import format_empty_cache_message

    text = format_empty_cache_message(order_id=99431, link_count=2)
    assert "99431" in text
    assert "2 ссыл" in text  # 'ссылки' or 'ссылок'
    assert "backfill" in text
    assert "scripts.backfill_avito_phrase_cache" in text
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_test_auto_format.py -v
```

Expected: 7 fails with `ImportError: No module named 'utils.test_auto_format'`.

- [ ] **Step 3: Implement the formatters**

Create `utils/test_auto_format.py`:

```python
"""Pure text formatters для admin «🧪 Test auto-dispatch» сообщений.

Чистые функции — никаких I/O, БД, HTTP. Принимают LinkPreview /
DispatchResult из services.order_links_dispatcher, возвращают готовые
Telegram-сообщения.
"""
from __future__ import annotations

from datetime import datetime

from services.order_links_dispatcher import DispatchResult, LinkPreview

_REASON_RU = {
    "cache_hit": "есть в кэше",
    "cache_miss": "нет в кэше",
    "no_ad_id": "ad_id не выделился",
}


def _fmt_deadline(iso: str | None) -> str:
    """ISO timestamp → 'YYYY-MM-DD' (только день)."""
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(iso)
        return d.date().isoformat()
    except ValueError:
        return iso[:10]  # best-effort


def _short_url(url: str, limit: int = 80) -> str:
    """Урезаем длинный URL чтобы preview помещался в Telegram limit."""
    if len(url) <= limit:
        return url
    return url[:limit] + "…"


def format_preview(*, order_id: int, previews: list[LinkPreview]) -> str:
    """Сформировать preview-сообщение для admin Test auto."""
    n_auto = sum(1 for p in previews if p.decision == "auto")
    n_total = len(previews)
    word = "ссылок" if n_total in (0, 5, 6, 7, 8, 9, 10, 11, 12) else (
        "ссылка" if n_total == 1 else "ссылки"
    )

    lines = [
        f"🧪 Test auto-dispatch для #{order_id}",
        "",
        f"Будет обработано: {n_total} {word}",
        "",
    ]

    for i, p in enumerate(previews, 1):
        decision_icon = "✅ AUTO" if p.decision == "auto" else "❌ MANUAL"
        reason_ru = _REASON_RU.get(p.reason, p.reason)
        lines.append(f"{i}. <code>{_short_url(p.url)}</code>")
        lines.append(f"   ├ ad_id: {p.ad_id or '—'}")
        lines.append(f"   ├ classifier: {decision_icon} ({reason_ru})")
        if p.decision == "auto":
            phrase = _short_url(p.phrase or "", limit=150)
            lines.append(f"   ├ phrase: '{phrase}'")
            lines.append(f"   └ deadline: {_fmt_deadline(p.deadline_at)}")
        else:
            lines.append(f"   └ останется pending+manual")
        lines.append("")

    if n_auto == 0:
        lines.append("⚠️ Все ссылки → MANUAL, отправлять нечего.")
    else:
        word_a = "ссылка" if n_auto == 1 else (
            "ссылки" if 2 <= n_auto <= 4 else "ссылок"
        )
        lines.append(f"⚠️ Будет реально отправлено {n_auto} {word_a} в biza.")

    return "\n".join(lines)


def format_result(
    *,
    order_id: int,
    previews: list[LinkPreview],
    results: list[DispatchResult],
) -> str:
    """Сформировать result-сообщение после force_dispatch."""
    by_link = {r.link_id: r for r in results}
    n_success = sum(1 for r in results if r.success)
    n_attempted = len(results)

    status_icon = "✅" if n_success == n_attempted and n_attempted > 0 else "⚠️"
    lines = [
        f"{status_icon} Test auto-dispatch для #{order_id} завершён",
        "",
        f"Отправлено: {n_success} / {n_attempted}",
        "",
    ]

    for i, p in enumerate(previews, 1):
        lines.append(f"{i}. <code>{_short_url(p.url)}</code>")
        if p.decision == "manual":
            lines.append(f"   ⏸ MANUAL (не отправлялось)")
        else:
            r = by_link.get(p.link_id)
            if r is None:
                lines.append(f"   ⚠️ (нет результата — баг)")
            elif r.success:
                lines.append(
                    f"   ✅ AUTO, external_id={r.external_id}, "
                    f"in_work до {_fmt_deadline(p.deadline_at)}"
                )
            else:
                lines.append(f"   ❌ Ошибка: {r.error}")
                lines.append(
                    "   (ссылка осталась pending+auto; если "
                    "PF_AUTO_DISPATCH_ENABLED включён, dispatcher повторит)"
                )
        lines.append("")

    return "\n".join(lines).rstrip()


def format_empty_cache_message(*, order_id: int, link_count: int) -> str:
    """Friendly fallback когда кэш пуст."""
    word = "ссылки" if 2 <= link_count <= 4 else (
        "ссылка" if link_count == 1 else "ссылок"
    )
    return (
        f"📭 Кэш фраз пустой.\n\n"
        f"Все {link_count} {word} заказа #{order_id} ушли бы в MANUAL "
        f"потому что в локальной БД нет ни одной известной фразы для их "
        f"ad_id.\n\n"
        f"Запусти backfill один раз, потом попробуй снова:\n\n"
        f"  <code>docker compose exec api python -m "
        f"scripts.backfill_avito_phrase_cache --days 90</code>\n\n"
        f"После backfill дневной refresh-loop поддерживает кэш свежим."
    )
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_test_auto_format.py -v
```

All 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add utils/test_auto_format.py tests/unit/test_test_auto_format.py
git commit -m "$(cat <<'EOF'
feat(test-auto): preview/result text formatters

Pure functions in utils/test_auto_format.py — format_preview,
format_result, format_empty_cache_message. Take LinkPreview/
DispatchResult from order_links_dispatcher, return Telegram HTML
messages with per-link breakdown and counters.

Isolated from the handler so format logic is unit-tested
independently from aiogram I/O.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: FSM states + entry callback

**Files:**
- Modify: `handlers/admin_orders.py`
- Create: `tests/unit/test_admin_test_auto_dispatch.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_admin_test_auto_dispatch.py`:

```python
"""Админ-кнопка «🧪 Test auto-dispatch» — FSM handler tests."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _ensure_schema(tmp_db):
    """Подтянуть schema через tmp_db до import handlers."""
    pass


@pytest.mark.asyncio
async def test_prompt_resets_state_and_asks_for_id(tmp_db):
    """Callback test_auto_dispatch — сбрасывает state, спрашивает ID."""
    from handlers.admin_orders import test_auto_dispatch_prompt

    call = MagicMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    state = AsyncMock()

    with patch("handlers.admin_orders.TestAutoDispatch.order_id") as fsm_state:
        fsm_state.set = AsyncMock()
        await test_auto_dispatch_prompt(call, state)

    state.finish.assert_awaited()  # сначала сбрасывает любую висящую FSM
    call.message.answer.assert_awaited()
    # Проверяем что текст содержит «Введите ID»
    args, kwargs = call.message.answer.call_args
    assert "Введите ID" in (args[0] if args else kwargs.get("text", ""))
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_admin_test_auto_dispatch.py -v
```

Expected: `ImportError: cannot import name 'test_auto_dispatch_prompt'`.

- [ ] **Step 3: Add FSM states + entry callback**

In `handlers/admin_orders.py`, after the existing `FailOrder` StatesGroup
(near line 72), add:

```python
class TestAutoDispatch(StatesGroup):
    """FSM для админ-кнопки «🧪 Test auto-dispatch»."""
    order_id = State()    # ждём ввода ID
    confirm = State()     # preview показан, ждём кнопку
```

In the import block at the top of the file, add (or extend existing
imports):

```python
from services.order_links_dispatcher import (
    classify_for_preview,
    force_dispatch,
)
from services.avito_phrase_cache import last_refreshed_at
from utils.test_auto_format import (
    format_preview,
    format_result,
    format_empty_cache_message,
)
```

Add the entry handler near the existing `fail_order_prompt` (around
line 920):

```python
@dp.callback_query_handler(text="test_auto_dispatch", state='*')
async def test_auto_dispatch_prompt(call: types.CallbackQuery,
                                     state: FSMContext):
    """Шаг 1: спросить ID заказа."""
    await state.finish()
    await call.message.answer(
        "🧪 Введите ID заказа для тестовой auto-отправки:"
    )
    await TestAutoDispatch.order_id.set()
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_admin_test_auto_dispatch.py -v
```

The 1 test passes.

- [ ] **Step 5: Commit**

```bash
git add handlers/admin_orders.py tests/unit/test_admin_test_auto_dispatch.py
git commit -m "$(cat <<'EOF'
feat(test-auto): admin FSM states + entry callback

TestAutoDispatch StatesGroup (order_id, confirm) + entry handler
`test_auto_dispatch_prompt`. Asks for the order ID when the admin
clicks the upcoming «🧪 Test auto» button.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: ID-collect handler — preview generation

**Files:**
- Modify: `handlers/admin_orders.py`
- Modify: `tests/unit/test_admin_test_auto_dispatch.py`

- [ ] **Step 1: Add tests for collect_id**

Append to `tests/unit/test_admin_test_auto_dispatch.py`:

```python
def _seed_paid_order(tmp_db, urls, position_name="3/10"):
    """Заказ для тестов."""
    import sqlite3
    from services.db import connect
    from services.order_links import create_links
    from utils.dates import now_iso

    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, "
            "start_date, date) VALUES (1, 100, ?, 'paid', NULL, ?)",
            (position_name, now_iso()),
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=urls)
        con.commit()
    return order_id


def _seed_phrase(ad_id, phrase):
    from services.avito_phrase_cache import upsert_many
    upsert_many([{
        "ad_id": ad_id, "search_link": phrase,
        "created_at": "2026-06-01 12:00",
    }])


@pytest.mark.asyncio
async def test_collect_id_invalid_text_stays_in_state(tmp_db):
    """Невалидный ID (буквы) → reply ошибка, остаёмся в state."""
    from handlers.admin_orders import test_auto_dispatch_collect_id

    message = MagicMock()
    message.text = "не_число"
    message.answer = AsyncMock()
    state = AsyncMock()

    await test_auto_dispatch_collect_id(message, state)

    state.finish.assert_not_awaited()
    message.answer.assert_awaited()
    args, kwargs = message.answer.call_args
    assert "ID должен быть" in (args[0] if args else kwargs.get("text", ""))


@pytest.mark.asyncio
async def test_collect_id_order_not_found(tmp_db):
    """Несуществующий заказ → reply ошибка, state cleared."""
    from handlers.admin_orders import test_auto_dispatch_collect_id

    message = MagicMock()
    message.text = "99999"
    message.answer = AsyncMock()
    state = AsyncMock()

    await test_auto_dispatch_collect_id(message, state)

    state.finish.assert_awaited()
    message.answer.assert_awaited()
    args, kwargs = message.answer.call_args
    assert "не найден" in (args[0] if args else kwargs.get("text", ""))


@pytest.mark.asyncio
async def test_collect_id_order_not_paid(tmp_db):
    """Заказ в unpaid → reply ошибка."""
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, "
            "start_date, date) VALUES (1, 100, '3/10', 'unpaid', NULL, ?)",
            ("2026-06-09T00:00:00",),
        )
        order_id = int(cur.lastrowid)
        con.commit()

    from handlers.admin_orders import test_auto_dispatch_collect_id

    message = MagicMock()
    message.text = str(order_id)
    message.answer = AsyncMock()
    state = AsyncMock()

    await test_auto_dispatch_collect_id(message, state)

    state.finish.assert_awaited()
    message.answer.assert_awaited()
    text = message.answer.call_args[0][0]
    assert "unpaid" in text or "только paid" in text


@pytest.mark.asyncio
async def test_collect_id_no_pending_links(tmp_db):
    """Заказ paid но без pending-ссылок → 'нечего тестить'."""
    order_id = _seed_paid_order(tmp_db, urls=[])

    from handlers.admin_orders import test_auto_dispatch_collect_id

    message = MagicMock()
    message.text = str(order_id)
    message.answer = AsyncMock()
    state = AsyncMock()

    await test_auto_dispatch_collect_id(message, state)

    state.finish.assert_awaited()
    text = message.answer.call_args[0][0]
    assert "нечего" in text or "нет pending" in text


@pytest.mark.asyncio
async def test_collect_id_empty_cache_shows_fallback(tmp_db):
    """Все manual + пустой кэш → friendly fallback message."""
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://avito.ru/x_1234567890",
    ])
    # Кэш пуст — ничего не upsert'или

    from handlers.admin_orders import test_auto_dispatch_collect_id

    message = MagicMock()
    message.text = str(order_id)
    message.answer = AsyncMock()
    state = AsyncMock()

    await test_auto_dispatch_collect_id(message, state)

    state.finish.assert_awaited()
    text = message.answer.call_args[0][0]
    assert "backfill" in text
    assert "scripts.backfill_avito_phrase_cache" in text


@pytest.mark.asyncio
async def test_collect_id_happy_path_shows_preview_with_buttons(tmp_db):
    """Cache hit → preview + кнопки [Confirm] [Cancel], state → confirm."""
    _seed_phrase("1234567890", "купить квартиру")
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://avito.ru/x_1234567890",
    ])

    from handlers.admin_orders import test_auto_dispatch_collect_id

    message = MagicMock()
    message.text = str(order_id)
    message.answer = AsyncMock()
    state = AsyncMock()

    with patch("handlers.admin_orders.TestAutoDispatch.confirm") as confirm:
        confirm.set = AsyncMock()
        await test_auto_dispatch_collect_id(message, state)

    state.update_data.assert_awaited()
    # auto_link_ids сохранён в state
    args, kwargs = state.update_data.call_args
    assert "auto_link_ids" in kwargs or len(args) > 0

    message.answer.assert_awaited()
    text = message.answer.call_args[0][0]
    assert "Test auto-dispatch" in text
    assert "AUTO" in text
    # Reply markup — InlineKeyboardMarkup с двумя кнопками
    rm = message.answer.call_args.kwargs.get("reply_markup")
    assert rm is not None
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_admin_test_auto_dispatch.py -v
```

Expected: 6 fails on `cannot import name 'test_auto_dispatch_collect_id'`.

- [ ] **Step 3: Implement collect_id handler**

Append to `handlers/admin_orders.py` (after `test_auto_dispatch_prompt`):

```python
@dp.message_handler(state=TestAutoDispatch.order_id)
async def test_auto_dispatch_collect_id(message: types.Message,
                                         state: FSMContext):
    """Шаг 2: получили ID, классифицируем, показываем preview."""
    try:
        order_id = int(message.text.strip())
    except (TypeError, ValueError):
        await message.answer("⚠️ ID должен быть числом. Попробуйте снова.")
        return

    order = get_order(order_id)
    if order is None:
        await message.answer(
            f"⚠️ Заказ {order_id} не найден.",
            reply_markup=admin_back_kb('orders_man'),
        )
        await state.finish()
        return

    if order.get("status") != "paid":
        await message.answer(
            f"⚠️ Заказ {order_id} в статусе "
            f"{order.get('status')}, "
            f"тестировать можно только paid-заказы.",
            reply_markup=admin_back_kb('orders_man'),
        )
        await state.finish()
        return

    previews = classify_for_preview(order_id)
    if not previews:
        await message.answer(
            f"⚠️ У заказа {order_id} нет pending-ссылок — нечего тестить.",
            reply_markup=admin_back_kb('orders_man'),
        )
        await state.finish()
        return

    n_auto = sum(1 for p in previews if p.decision == "auto")
    cache_empty = last_refreshed_at() is None

    if n_auto == 0 and cache_empty:
        await message.answer(
            format_empty_cache_message(order_id=order_id,
                                        link_count=len(previews)),
            parse_mode="HTML",
            reply_markup=admin_back_kb('orders_man'),
        )
        await state.finish()
        return

    auto_link_ids = [p.link_id for p in previews if p.decision == "auto"]
    await state.update_data(order_id=order_id, auto_link_ids=auto_link_ids,
                             previews_serialized=_serialize_previews(previews))

    text = format_preview(order_id=order_id, previews=previews)

    if n_auto == 0:
        # Все manual + кэш не пуст — показываем preview но без confirm
        await message.answer(
            text + "\n\nНечего отправлять. Выйдите назад.",
            parse_mode="HTML",
            reply_markup=admin_back_kb('orders_man'),
        )
        await state.finish()
        return

    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(
            text="✅ Подтвердить и отправить",
            callback_data="test_auto_dispatch_confirm",
        ),
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="test_auto_dispatch_cancel",
        ),
    )
    await message.answer(text, parse_mode="HTML", reply_markup=kb)
    await TestAutoDispatch.confirm.set()


def _serialize_previews(previews):
    """LinkPreview → dict для FSM-state (json-сохранимо)."""
    return [
        {
            "link_id": p.link_id, "url": p.url, "ad_id": p.ad_id,
            "decision": p.decision, "reason": p.reason,
            "phrase": p.phrase, "deadline_at": p.deadline_at,
        }
        for p in previews
    ]


def _deserialize_previews(data):
    """Обратное преобразование dict → LinkPreview."""
    from services.order_links_dispatcher import LinkPreview
    return [LinkPreview(**d) for d in data]
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_admin_test_auto_dispatch.py -v
```

All 7 tests in the file pass (1 from Task 5 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add handlers/admin_orders.py tests/unit/test_admin_test_auto_dispatch.py
git commit -m "$(cat <<'EOF'
feat(test-auto): collect_id handler — preview + edge cases

Validates input ID, checks order exists + paid + has pending links,
classifies via classify_for_preview, then either:
  - shows empty-cache fallback message
  - shows MANUAL-only preview (nothing to send)
  - shows full preview with [Confirm][Cancel] inline buttons

Stores auto_link_ids + serialized previews in FSM state for the
confirm step.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Confirm callback — real submit

**Files:**
- Modify: `handlers/admin_orders.py`
- Modify: `tests/unit/test_admin_test_auto_dispatch.py`

- [ ] **Step 1: Add tests for confirm**

Append to `tests/unit/test_admin_test_auto_dispatch.py`:

```python
@pytest.mark.asyncio
async def test_confirm_runs_force_dispatch_and_edits_message(tmp_db):
    """Confirm → force_dispatch вызван, message edited с результатом."""
    _seed_phrase("1234567890", "купить")
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://avito.ru/x_1234567890",
    ])
    from services.order_links import list_links
    link_id = list_links(order_id)[0]["id"]

    from handlers.admin_orders import test_auto_dispatch_confirm

    call = MagicMock()
    call.message = MagicMock()
    call.message.edit_text = AsyncMock()
    call.message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "order_id": order_id,
        "auto_link_ids": [link_id],
        "previews_serialized": [{
            "link_id": link_id,
            "url": "https://avito.ru/x_1234567890",
            "ad_id": "1234567890",
            "decision": "auto", "reason": "cache_hit",
            "phrase": "купить",
            "deadline_at": "2026-06-12T00:00:00+00:00",
        }],
    })

    with patch("handlers.admin_orders.force_dispatch") as fd:
        from services.order_links_dispatcher import DispatchResult
        fd.return_value = [DispatchResult(
            link_id=link_id, success=True,
            external_id="357901", error=None,
        )]
        await test_auto_dispatch_confirm(call, state)

    fd.assert_called_once_with(order_id, link_ids=[link_id])
    call.message.edit_text.assert_awaited()
    text = call.message.edit_text.call_args[0][0]
    assert "357901" in text
    assert "1 / 1" in text
    state.finish.assert_awaited()


@pytest.mark.asyncio
async def test_confirm_shows_failure_message(tmp_db):
    """Confirm + force_dispatch вернул failure → result message с ❌."""
    _seed_phrase("1234567890", "x")
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://avito.ru/x_1234567890",
    ])
    from services.order_links import list_links
    link_id = list_links(order_id)[0]["id"]

    from handlers.admin_orders import test_auto_dispatch_confirm

    call = MagicMock()
    call.message = MagicMock()
    call.message.edit_text = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "order_id": order_id,
        "auto_link_ids": [link_id],
        "previews_serialized": [{
            "link_id": link_id,
            "url": "https://avito.ru/x_1234567890",
            "ad_id": "1234567890",
            "decision": "auto", "reason": "cache_hit",
            "phrase": "x",
            "deadline_at": "2026-06-12T00:00:00+00:00",
        }],
    })

    with patch("handlers.admin_orders.force_dispatch") as fd:
        from services.order_links_dispatcher import DispatchResult
        fd.return_value = [DispatchResult(
            link_id=link_id, success=False, external_id=None,
            error="API отказал: 400",
        )]
        await test_auto_dispatch_confirm(call, state)

    text = call.message.edit_text.call_args[0][0]
    assert "API отказал" in text
    assert "0 / 1" in text
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_admin_test_auto_dispatch.py -v
```

Expected: 2 new fails on `cannot import name 'test_auto_dispatch_confirm'`.

- [ ] **Step 3: Implement confirm callback**

Append to `handlers/admin_orders.py`:

```python
@dp.callback_query_handler(text="test_auto_dispatch_confirm",
                            state=TestAutoDispatch.confirm)
async def test_auto_dispatch_confirm(call: types.CallbackQuery,
                                      state: FSMContext):
    """Шаг 3: подтверждено — force_dispatch + result message."""
    data = await state.get_data()
    order_id = int(data["order_id"])
    auto_link_ids = list(data["auto_link_ids"])
    previews = _deserialize_previews(data["previews_serialized"])

    results = force_dispatch(order_id, link_ids=auto_link_ids)

    text = format_result(order_id=order_id, previews=previews, results=results)
    await call.message.edit_text(text, parse_mode="HTML")
    await state.finish()
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_admin_test_auto_dispatch.py -v
```

All 9 tests in the file pass.

- [ ] **Step 5: Commit**

```bash
git add handlers/admin_orders.py tests/unit/test_admin_test_auto_dispatch.py
git commit -m "$(cat <<'EOF'
feat(test-auto): confirm callback — real dispatch + result message

On admin clicking [✅ Подтвердить] the preview message is edited
in-place with the dispatch result (per-link external_id or error).
State cleared.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Cancel callback

**Files:**
- Modify: `handlers/admin_orders.py`
- Modify: `tests/unit/test_admin_test_auto_dispatch.py`

- [ ] **Step 1: Add test for cancel**

Append to `tests/unit/test_admin_test_auto_dispatch.py`:

```python
@pytest.mark.asyncio
async def test_cancel_clears_state_and_edits_message(tmp_db):
    """Cancel callback → preview edited на «Отменено», state cleared."""
    from handlers.admin_orders import test_auto_dispatch_cancel

    call = MagicMock()
    call.message = MagicMock()
    call.message.edit_text = AsyncMock()
    state = AsyncMock()

    await test_auto_dispatch_cancel(call, state)

    state.finish.assert_awaited()
    call.message.edit_text.assert_awaited()
    text = call.message.edit_text.call_args[0][0]
    assert "Отменено" in text
```

- [ ] **Step 2: Run — expect FAIL**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_admin_test_auto_dispatch.py -v
```

Expected: 1 new fail.

- [ ] **Step 3: Implement cancel**

Append to `handlers/admin_orders.py`:

```python
@dp.callback_query_handler(text="test_auto_dispatch_cancel",
                            state=TestAutoDispatch.confirm)
async def test_auto_dispatch_cancel(call: types.CallbackQuery,
                                     state: FSMContext):
    """Cancel — отменяет тестовую отправку, edit preview на короткое
    сообщение."""
    await state.finish()
    await call.message.edit_text("❌ Отменено.")
```

- [ ] **Step 4: Run — expect PASS**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_admin_test_auto_dispatch.py -v
```

All 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add handlers/admin_orders.py tests/unit/test_admin_test_auto_dispatch.py
git commit -m "$(cat <<'EOF'
feat(test-auto): cancel callback

Edits preview message in-place to 'Отменено' and clears FSM state.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Button in `orders_kb()`

**Files:**
- Modify: `keyboards/inline_keyboards.py`
- Modify: an existing keyboard test (or add a minimal one)

- [ ] **Step 1: Write a tiny test**

Append to `tests/unit/test_admin_test_auto_dispatch.py`:

```python
def test_orders_kb_has_test_auto_button():
    """В orders_kb должна появиться кнопка с callback_data='test_auto_dispatch'."""
    from keyboards.inline_keyboards import orders_kb
    kb = orders_kb()
    callbacks = {
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
    }
    assert "test_auto_dispatch" in callbacks
```

- [ ] **Step 2: Run — expect FAIL**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_admin_test_auto_dispatch.py::test_orders_kb_has_test_auto_button -v
```

- [ ] **Step 3: Add the button**

In `keyboards/inline_keyboards.py`, inside `orders_kb()`, find the row with
the «📋 Manual задачи в шит» button (around line 1046-1051) and add a new
row before the «Главное меню» row:

```python
        keyboard.row(
            InlineKeyboardButton(
                text="🧪 Test auto",
                callback_data="test_auto_dispatch",
            )
        )
```

The order in the function becomes:

```python
        ... # existing rows above
        keyboard.row(
            InlineKeyboardButton(
                text="📋 Manual задачи в шит",
                callback_data="gsheets_manual"
            )
        )
        keyboard.row(  # NEW
            InlineKeyboardButton(
                text="🧪 Test auto",
                callback_data="test_auto_dispatch",
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text=main_menu,
                callback_data='to_admin_menu'
            )
        )
```

- [ ] **Step 4: Run — expect PASS**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit/test_admin_test_auto_dispatch.py -v
```

All 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add keyboards/inline_keyboards.py tests/unit/test_admin_test_auto_dispatch.py
git commit -m "$(cat <<'EOF'
feat(test-auto): button in orders_kb

«🧪 Test auto» row appears in /admin → 📖 Заказы submenu after
the «📋 Manual задачи в шит» button. Callback_data='test_auto_dispatch'
hits the FSM entry handler added in Task 5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Final smoke

**Files:** — none

- [ ] **Step 1: Run the full suite**

```bash
docker run --rm -v "$(pwd):/app" -w /app pf-test-auto-button-api \
    pytest tests/unit tests/web -q --tb=short
```

Expected: all tests green (no regressions).

- [ ] **Step 2: Lint scan**

```bash
grep -rn "TODO\|FIXME\|XXX" services/order_links_dispatcher.py \
    services/order_links_classifier.py \
    handlers/admin_orders.py \
    utils/test_auto_format.py 2>/dev/null
```

Expected: no new TODO/FIXME from this work.

- [ ] **Step 3: Final commit (if anything stray)**

If nothing changed in this task — skip. Otherwise:

```bash
git add -A
git commit -m "chore(test-auto): cleanup after final smoke"
```

---

## Out of scope для этого плана

(consistent with spec §2 Out of scope)

1. **Backfill cache из админ-бота.** Скрипт уже есть из Task 9
   pf-auto-mode-spec плана — это разовая ops-операция.
2. **Cost estimation (₽).** Не показываем в preview, не считаем в коде.
3. **Веб-админка.** Только Telegram-бот.
4. **Per-link выбор галочками.** Confirm подтверждает всё auto.
5. **Расширение auto_rate метрики** под separate test-dispatch counter.

---

## Rollout protocol

1. Merge feature-branch в dev → push origin.
2. На проде: `git pull dev` + `docker compose build api bot` +
   `docker compose up -d --force-recreate api bot`.
3. Кнопка появится сразу после рестарта.
4. Если кэш пуст (типовой day-0) — Test auto покажет friendly fallback
   с командой backfill. Backfill запускается отдельным шагом руками
   когда админ решит включать auto-mode.
