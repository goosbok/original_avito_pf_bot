from utils.sqlite3 import get_setting, add_setting_to_base

METHODS: dict = {
    "manual": "🧑‍💻 Ручная оплата (поддержка)",
    "yookassa": "💳 Юкасса",
}


def _key(method: str) -> str:
    return f"payment_method_{method}"


def is_enabled(method: str) -> bool:
    val = get_setting(_key(method))
    return val is None or val == "1"


def get_enabled() -> list:
    return [m for m in METHODS if is_enabled(m)]


def can_disable(method: str) -> bool:
    enabled = get_enabled()
    return not (len(enabled) <= 1 and method in enabled)


def set_enabled(method: str, enabled: bool) -> None:
    if not enabled and not can_disable(method):
        raise ValueError(
            "Нельзя отключить способ оплаты: это единственный активный способ"
        )
    add_setting_to_base(
        _key(method),
        f"Способ оплаты: {METHODS[method]}",
        "1" if enabled else "0",
    )
