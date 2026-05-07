# tests/unit/test_payment_methods.py
from pathlib import Path
import pytest
from services.payment_methods import (
    METHODS,
    get_enabled,
    is_enabled,
    can_disable,
    set_enabled,
)


def test_all_methods_enabled_by_default(tmp_db: Path) -> None:
    assert get_enabled() == list(METHODS.keys())


def test_is_enabled_returns_true_by_default(tmp_db: Path) -> None:
    assert is_enabled("manual") is True
    assert is_enabled("yookassa") is True


def test_disable_yookassa_leaves_manual_active(tmp_db: Path) -> None:
    set_enabled("yookassa", False)
    assert is_enabled("yookassa") is False
    assert get_enabled() == ["manual"]


def test_cannot_disable_last_active_method(tmp_db: Path) -> None:
    set_enabled("yookassa", False)
    with pytest.raises(ValueError):
        set_enabled("manual", False)


def test_can_disable_manual_returns_true_when_yookassa_active(tmp_db: Path) -> None:
    assert can_disable("manual") is True


def test_can_disable_returns_false_when_only_active(tmp_db: Path) -> None:
    set_enabled("yookassa", False)
    assert can_disable("manual") is False


def test_reenable_persists(tmp_db: Path) -> None:
    set_enabled("yookassa", False)
    set_enabled("yookassa", True)
    assert is_enabled("yookassa") is True
    assert get_enabled() == list(METHODS.keys())
