"""Tests for funnel keyboards."""
from __future__ import annotations


def test_funnel_service_kb_has_button_per_service():
    from keyboards.inline_keyboards import funnel_service_kb

    kb = funnel_service_kb()
    flat = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = {b.callback_data for b in flat}
    assert "funnel:pf_avito" in callbacks
    assert any(b.callback_data == "to_admin_menu" for b in flat)


def test_funnel_period_kb_has_four_presets_and_back():
    from keyboards.inline_keyboards import funnel_period_kb

    kb = funnel_period_kb("pf_avito")
    callbacks = {
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
    }
    for suffix in ("today", "7d", "30d", "all"):
        assert f"funnel:pf_avito:{suffix}" in callbacks
    assert "funnel_menu" in callbacks  # back to service picker


def test_admin_kb_contains_funnel_button():
    from keyboards.inline_keyboards import admin

    kb = admin()
    callbacks = {
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
    }
    assert "funnel_menu" in callbacks
