"""Tests for handlers.admin_funnel."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def _patch_admins(monkeypatch):
    """Make get_admins() return a fixed list inside handlers.admin_funnel."""
    import handlers.admin_funnel as mod  # ensure module loaded before patching

    monkeypatch.setattr(mod, "get_admins", lambda: ["100500"])


@pytest.fixture
def admin_call(_patch_admins):
    call = MagicMock()
    call.from_user.id = 100500
    call.data = "funnel_menu"
    call.answer = AsyncMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.answer_photo = AsyncMock()
    call.message.delete = AsyncMock()
    return call


@pytest.fixture
def non_admin_call(_patch_admins):
    call = MagicMock()
    call.from_user.id = 999
    call.data = "funnel_menu"
    call.answer = AsyncMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.answer_photo = AsyncMock()
    return call


@pytest.mark.asyncio
async def test_funnel_menu_shows_service_picker(admin_call, tmp_db: Path):
    from handlers.admin_funnel import funnel_menu

    await funnel_menu(admin_call, state=MagicMock())
    admin_call.message.answer.assert_awaited_once()
    args, kwargs = admin_call.message.answer.call_args
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_funnel_menu_ignores_non_admin(non_admin_call, tmp_db: Path):
    from handlers.admin_funnel import funnel_menu

    await funnel_menu(non_admin_call, state=MagicMock())
    non_admin_call.message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_funnel_service_callback_shows_period_picker(admin_call, tmp_db: Path):
    from handlers.admin_funnel import funnel_router

    admin_call.data = "funnel:pf_avito"
    await funnel_router(admin_call, state=MagicMock())
    admin_call.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_funnel_period_callback_sends_photo(admin_call, tmp_db: Path):
    from handlers.admin_funnel import funnel_router
    from services.funnel import track_step

    # Seed two distinct users, one of them progressing further
    track_step(user_id=1, service="pf_avito", step="view_tariff")
    track_step(user_id=2, service="pf_avito", step="view_tariff")
    track_step(user_id=1, service="pf_avito", step="select_period")

    admin_call.data = "funnel:pf_avito:all"
    await funnel_router(admin_call, state=MagicMock())
    admin_call.message.answer_photo.assert_awaited_once()
    _args, kwargs = admin_call.message.answer_photo.call_args
    caption = kwargs.get("caption", "")
    assert "view_tariff" in caption
    assert "2" in caption  # users at view_tariff
    assert "select_period" in caption


@pytest.mark.asyncio
async def test_funnel_router_ignores_non_admin(non_admin_call, tmp_db: Path):
    from handlers.admin_funnel import funnel_router

    non_admin_call.data = "funnel:pf_avito:all"
    await funnel_router(non_admin_call, state=MagicMock())
    non_admin_call.message.answer.assert_not_awaited()
    non_admin_call.message.answer_photo.assert_not_awaited()
