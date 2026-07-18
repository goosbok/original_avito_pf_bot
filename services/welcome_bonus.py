"""Welcome-бонус новым пользователям.

Начисляется один раз при регистрации (telegram / email / phone-verified) —
вызовы в services/identity.py. Сумма — env WELCOME_BONUS_RUB (рубли),
0 = выключено. Операция пишется в refills строкой source_type='welcome_bonus',
status='succeeded', payment_id=NULL.

Сознательно НЕ через services.refill.finalize(): normalize() пускает только
source ∈ {telegram, web, api}, а welcome-бонус — внутренняя операция, не платёж.
_is_first_refill() исключает 'welcome_bonus', чтобы реф-бонус 30% по-прежнему
срабатывал на первом реальном депозите.
"""
from __future__ import annotations

from data import config
from services.balance import credit
from services.db import connect
from utils.other import get_date

SOURCE_TYPE = "welcome_bonus"


def grant_welcome_bonus(user_id: int) -> int:
    """Начислить welcome-бонус, если включён и ещё не начислялся.

    Возвращает начисленную сумму в рублях (0 — выключено или уже был).
    Порядок INSERT→credit как в refill.finalize(): строка в refills — гард
    от повторного начисления, поэтому создаётся первой. Принятое ограничение:
    если процесс умрёт между INSERT и credit(), бонус потерян навсегда
    (guard-строка блокирует повтор) — осознанный компромисс по образцу
    refill.finalize() (см. комментарий в refill.py:124-129).
    """
    rub = int(getattr(config, "WELCOME_BONUS_RUB", 0) or 0)
    if rub <= 0:
        return 0
    amount = rub  # users.balance и refills.amount хранятся в целых рублях

    with connect() as con:
        already = con.execute(
            "SELECT 1 FROM refills WHERE user_id = ? AND source_type = ? LIMIT 1",
            (user_id, SOURCE_TYPE),
        ).fetchone()
        if already is not None:
            return 0
        con.execute(
            "INSERT INTO refills(amount, date, user_id, payment_id, source_type, source_app_id, status) "
            "VALUES (?, ?, ?, NULL, ?, NULL, 'succeeded')",
            (amount, get_date(), user_id, SOURCE_TYPE),
        )
        con.commit()

    credit(user_id, amount)
    return amount
