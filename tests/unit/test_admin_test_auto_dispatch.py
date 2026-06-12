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

    state.finish.assert_awaited()
    call.message.answer.assert_awaited()
    args, kwargs = call.message.answer.call_args
    assert "Введите ID" in (args[0] if args else kwargs.get("text", ""))


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
    args, kwargs = state.update_data.call_args
    assert "auto_link_ids" in kwargs or len(args) > 0

    message.answer.assert_awaited()
    text = message.answer.call_args[0][0]
    assert "Test auto-dispatch" in text
    assert "AUTO" in text
    rm = message.answer.call_args.kwargs.get("reply_markup")
    assert rm is not None


@pytest.mark.asyncio
async def test_collect_id_handles_order_deleted_race(tmp_db):
    """Order был удалён между get_order и classify_for_preview → friendly msg."""
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])

    from handlers.admin_orders import test_auto_dispatch_collect_id
    from services.exceptions import OrderNotFound

    message = MagicMock()
    message.text = str(order_id)
    message.answer = AsyncMock()
    state = AsyncMock()

    with patch("handlers.admin_orders.classify_for_preview",
               side_effect=OrderNotFound(f"order_id={order_id}")):
        await test_auto_dispatch_collect_id(message, state)

    state.finish.assert_awaited()
    text = message.answer.call_args[0][0]
    assert "удалён" in text


def test_deserialize_previews_ignores_unknown_fields():
    """Storage может содержать поля от старой версии LinkPreview — не падаем."""
    from handlers.admin_orders import _deserialize_previews

    data = [{
        "link_id": 1, "url": "https://avito.ru/x_1234567890",
        "ad_id": "1234567890", "decision": "auto", "reason": "cache_hit",
        "phrase": "x", "deadline_at": "2026-06-12T00:00:00+00:00",
        # поле из будущей версии, которого ещё нет в LinkPreview
        "future_field_added_in_v2": "ignored",
    }]
    previews = _deserialize_previews(data)
    assert len(previews) == 1
    assert previews[0].link_id == 1
    assert previews[0].decision == "auto"


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
