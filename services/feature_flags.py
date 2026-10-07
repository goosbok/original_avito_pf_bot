"""Runtime-фичефлаги: переключатели, которые админ может дёргать без рестарта.

Хранение — таблица `settings` (та же, что payment_work и способы оплаты).
Если строки в БД нет — fallback на env-конфиг (data/config.py), т.е. поведение
до появления кнопки сохраняется.

Первый флаг: auto-dispatch заказов в API исполнителя (биза). Гейт живёт в
services/order_links_classifier.classify — при выключенном флаге все ссылки
уходят в manual, на внешний сервис ничего не отправляется.
"""
from __future__ import annotations

from data import config
from utils.sqlite3 import add_setting_to_base, get_setting

_AUTO_DISPATCH_KEY = "pf_auto_dispatch_enabled"
_AUTO_DISPATCH_DESCR = "Автоотправка заданий исполнителю (биза): 1=вкл, 0=выкл"


def auto_dispatch_enabled() -> bool:
    """Включён ли auto-dispatch. Строка в БД приоритетнее env-конфига."""
    val = get_setting(_AUTO_DISPATCH_KEY)
    if val is None:
        return bool(config.PF_AUTO_DISPATCH_ENABLED)
    return val == "1"


def set_auto_dispatch_enabled(enabled: bool) -> None:
    add_setting_to_base(
        _AUTO_DISPATCH_KEY,
        _AUTO_DISPATCH_DESCR,
        "1" if enabled else "0",
    )
