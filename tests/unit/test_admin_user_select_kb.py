"""Tests for user_select_kb keyboard."""
from __future__ import annotations
import pytest


@pytest.fixture(autouse=True)
def _tmp(tmp_db):
    """Ensure schema is loaded before importing keyboards."""


def test_single_result_no_nav_arrows(tmp_db):
    from keyboards.inline_keyboards import user_select_kb
    kb = user_select_kb(page=0, total=1)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    cb_data = {b.callback_data for b in all_buttons}
    assert "usel:prev" not in cb_data
    assert "usel:next" not in cb_data
    assert "usel:pick" in cb_data
    assert "usel:cancel" in cb_data


def test_middle_page_has_both_arrows(tmp_db):
    from keyboards.inline_keyboards import user_select_kb
    kb = user_select_kb(page=1, total=3)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    cb_data = {b.callback_data for b in all_buttons}
    assert "usel:prev" in cb_data
    assert "usel:next" in cb_data


def test_first_page_no_prev(tmp_db):
    from keyboards.inline_keyboards import user_select_kb
    kb = user_select_kb(page=0, total=3)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    cb_data = {b.callback_data for b in all_buttons}
    assert "usel:prev" not in cb_data
    assert "usel:next" in cb_data


def test_last_page_no_next(tmp_db):
    from keyboards.inline_keyboards import user_select_kb
    kb = user_select_kb(page=2, total=3)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    cb_data = {b.callback_data for b in all_buttons}
    assert "usel:prev" in cb_data
    assert "usel:next" not in cb_data


def test_counter_button_text(tmp_db):
    from keyboards.inline_keyboards import user_select_kb
    kb = user_select_kb(page=1, total=5)
    nav_row = kb.inline_keyboard[0]
    texts = [b.text for b in nav_row]
    assert "2/5" in texts
