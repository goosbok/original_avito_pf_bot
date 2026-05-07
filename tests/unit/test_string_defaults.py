"""Verify that every button key used in get_menu_kb() has a non-None fallback.

Rationale: get_string() in inline_keyboards.py falls back to globals() of that
module (which includes from design import *). If a constant is missing from
design.py AND missing from the DB, the button's text will be None, and Telegram
will reject the whole keyboard with 'can't find field text'.
"""
import re
from pathlib import Path

import pytest


REQUIRED_BUTTON_KEYS = [
    "btn_how_to_start",
    "btn_avito",
    "btn_profile",
    "btn_channel",
    "btn_main_menu",
    "btn_yes",
    "btn_no",
    "btn_all_completed",
    "btn_all_posted",
    "btn_avito_cases",
    "btn_seo_howto",
    "btn_seo_why",
    "btn_seo_result",
    "btn_seo_order",
    "btn_rules",
    "btn_support",
    "btn_qna",
    "btn_promocodes",
]


def _extract_design_constants() -> dict[str, str]:
    """Parse design.py to extract btn_* constants (avoiding full import)."""
    design_path = Path(__file__).parent.parent.parent / "design.py"
    content = design_path.read_text(encoding="utf-8")

    constants = {}
    # Match lines like: btn_name = "..."
    pattern = r'^\s*(btn_\w+)\s*=\s*"([^"]*)"\s*$'
    for line in content.split("\n"):
        match = re.match(pattern, line)
        if match:
            key, value = match.groups()
            constants[key] = value

    return constants


@pytest.mark.parametrize("key", REQUIRED_BUTTON_KEYS)
def test_design_has_fallback_for_button_key(key):
    """Every btn_* key used in keyboards must have a non-empty string in design.py."""
    constants = _extract_design_constants()
    value = constants.get(key)
    assert value is not None, f"design.py is missing fallback for button key '{key}'"
    assert isinstance(value, str) and value.strip(), (
        f"design.py fallback for '{key}' is empty or not a string"
    )


@pytest.mark.parametrize("key", REQUIRED_BUTTON_KEYS)
def test_sqlite3_get_string_returns_fallback_without_db(key, tmp_path, monkeypatch):
    """get_string() from utils.sqlite3 must return a non-None value for all btn_* keys
    even when the strings table is empty (fresh volume / new deploy).
    """
    import sqlite3 as _sqlite3
    import importlib
    import utils.sqlite3 as m

    db_path = str(tmp_path / "test.db")
    with _sqlite3.connect(db_path) as con:
        con.execute(
            "CREATE TABLE strings (parametr TEXT PRIMARY KEY, description TEXT, value TEXT)"
        )
        con.commit()

    monkeypatch.setattr(m, "path_db", db_path)

    value = m.get_string(key)
    assert value is not None, (
        f"utils.sqlite3.get_string('{key}') returned None with empty strings table"
    )
    assert isinstance(value, str) and value.strip()
