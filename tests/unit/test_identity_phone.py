"""Тесты identity-операций с phone-провайдером и резолвом merge-конфликтов.

Сценарий: гость делает быстрый заказ → создаётся phone-only user (provider='phone',
verified=0). Потом этот же гость регистрируется в боте/ЛК и шерит номер. Если phone
уже привязан к **phone-only** записи — мы её мерджим в реального юзера (orders,
refills, notifications, balance переезжают). Если phone привязан к полноценному
аккаунту (есть другие providers) — `AccountMergeConflict`.
"""
import sqlite3
from pathlib import Path

import pytest


def _make_user(con, balance=0):
    cur = con.execute(
        "INSERT INTO users(balance, user_name, first_name, reg_date) "
        "VALUES (?, NULL, NULL, '2026-01-01T00:00:00+00:00')",
        (balance,),
    )
    return cur.lastrowid


def _add_provider(con, user_id, provider, identifier, verified=1):
    con.execute(
        "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
        "VALUES (?, ?, ?, '2026-01-01T00:00:00+00:00', ?)",
        (user_id, provider, identifier, verified),
    )


def test_find_or_create_user_by_phone_creates_new_user_when_phone_unknown(tmp_db: Path):
    from services import identity
    user_id = identity.find_or_create_user_by_phone("+79991234567")
    assert user_id > 0
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT user_id, verified FROM auth_providers "
            "WHERE provider='phone' AND identifier=?",
            ("+79991234567",),
        ).fetchone()
    assert row == (user_id, 0)  # verified=0 — phone не подтверждён


def test_find_or_create_user_by_phone_returns_existing_when_phone_known(tmp_db: Path):
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        existing_id = _make_user(con)
        _add_provider(con, existing_id, "phone", "+79991234567", verified=1)
        con.commit()
    user_id = identity.find_or_create_user_by_phone("+79991234567")
    assert user_id == existing_id


def test_find_or_create_user_by_phone_verified_flag_persists(tmp_db: Path):
    """verified=True при создании нового user — phone сразу подтверждён
    (например, после прохождения SMS-OTP)."""
    from services import identity
    user_id = identity.find_or_create_user_by_phone("+79991234567", verified=True)
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT verified FROM auth_providers "
            "WHERE provider='phone' AND identifier=?",
            ("+79991234567",),
        ).fetchone()
    assert row == (1,)


def test_link_phone_provider_creates_new_when_phone_unknown(tmp_db: Path):
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        target_id = _make_user(con)
        _add_provider(con, target_id, "telegram", "555000111", verified=1)
        con.commit()

    identity.link_phone_provider(target_id, "+79991234567", set_verified=True)

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT user_id, verified FROM auth_providers "
            "WHERE provider='phone' AND identifier=?",
            ("+79991234567",),
        ).fetchone()
    assert row == (target_id, 1)


def test_link_phone_provider_idempotent_relink_to_same_user_just_sets_verified(tmp_db: Path):
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        user_id = _make_user(con)
        _add_provider(con, user_id, "phone", "+79991234567", verified=0)
        con.commit()

    identity.link_phone_provider(user_id, "+79991234567", set_verified=True)

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT user_id, verified FROM auth_providers "
            "WHERE provider='phone' AND identifier=?",
            ("+79991234567",),
        ).fetchone()
    assert row == (user_id, 1)


def test_link_phone_provider_merges_phone_only_into_target(tmp_db: Path):
    """Гость сделал быстрый заказ → phone-only user. Потом регистрируется TG.
    Должно: orders, refills, notifications, balance — у TG-юзера; phone-only удалён;
    phone-provider теперь у TG-юзера и verified=1."""
    from services import identity

    with sqlite3.connect(tmp_db) as con:
        # phone-only-user от быстрого заказа
        phone_only_id = _make_user(con, balance=50)
        _add_provider(con, phone_only_id, "phone", "+79991234567", verified=0)
        # его order
        con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, links, contacts, user_name) "
            "VALUES (?, 100, '1/1', 'paid', '[]', 0, NULL)",
            (phone_only_id,),
        )
        # его refill
        con.execute(
            "INSERT INTO refills(user_id, amount, date, payment_id) "
            "VALUES (?, 500, '2026-06-01T10:00:00', 'pay_xyz')",
            (phone_only_id,),
        )
        # его notification
        con.execute(
            "INSERT INTO notifications(user_id, kind, order_id, new_status, text) "
            "VALUES (?, 'order', 1, 'paid', 'test')",
            (phone_only_id,),
        )
        # TG-user (target)
        tg_id = _make_user(con, balance=0)
        _add_provider(con, tg_id, "telegram", "555000111", verified=1)
        con.commit()

    identity.link_phone_provider(tg_id, "+79991234567", set_verified=True)

    with sqlite3.connect(tmp_db) as con:
        # phone-only-user удалён
        assert con.execute(
            "SELECT id FROM users WHERE id=?", (phone_only_id,)
        ).fetchone() is None
        # phone-provider теперь у TG-юзера и verified=1
        ap = con.execute(
            "SELECT user_id, verified FROM auth_providers "
            "WHERE provider='phone' AND identifier=?",
            ("+79991234567",),
        ).fetchone()
        assert ap == (tg_id, 1)
        # order перенесён
        assert con.execute(
            "SELECT user_id FROM orders WHERE price=100"
        ).fetchone() == (tg_id,)
        # refill перенесён
        assert con.execute(
            "SELECT user_id FROM refills WHERE payment_id='pay_xyz'"
        ).fetchone() == (tg_id,)
        # notification перенесена
        assert con.execute(
            "SELECT user_id FROM notifications WHERE text='test'"
        ).fetchone() == (tg_id,)
        # баланс склеен (50 + 0 = 50)
        assert con.execute(
            "SELECT balance FROM users WHERE id=?", (tg_id,)
        ).fetchone() == (50,)


def test_link_phone_provider_raises_conflict_when_other_user_has_other_providers(tmp_db: Path):
    """Phone уже у юзера с другими providers (email). Два полноценных аккаунта —
    raise AccountMergeConflict, никаких автоматических merge'ей."""
    from services import identity
    from services.exceptions import AccountMergeConflict

    with sqlite3.connect(tmp_db) as con:
        full_user_id = _make_user(con)
        _add_provider(con, full_user_id, "phone", "+79991234567", verified=1)
        _add_provider(con, full_user_id, "email", "user@example.com", verified=1)
        target_id = _make_user(con)
        _add_provider(con, target_id, "telegram", "555000111", verified=1)
        con.commit()

    with pytest.raises(AccountMergeConflict) as exc:
        identity.link_phone_provider(target_id, "+79991234567", set_verified=True)
    assert exc.value.existing_user_id == full_user_id
    assert exc.value.target_user_id == target_id
    assert exc.value.phone == "+79991234567"


def test_link_phone_provider_raises_conflict_when_phone_verified_on_other_user(tmp_db: Path):
    """Phone привязан к другому user'у И верифицирован — это его «собственность»,
    даже если других provider'ов у того юзера нет (а вдруг скоро добавит)."""
    from services import identity
    from services.exceptions import AccountMergeConflict

    with sqlite3.connect(tmp_db) as con:
        owner_id = _make_user(con)
        _add_provider(con, owner_id, "phone", "+79991234567", verified=1)
        target_id = _make_user(con)
        _add_provider(con, target_id, "telegram", "555000111", verified=1)
        con.commit()

    with pytest.raises(AccountMergeConflict):
        identity.link_phone_provider(target_id, "+79991234567", set_verified=True)


def test_merge_transfers_ref_when_target_has_none(tmp_db: Path) -> None:
    """У phone-only источника был реферер, у цели нет → ref переносится."""
    import sqlite3
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (42, 0)")          # реферер
        con.execute("INSERT INTO users(id, balance) VALUES (200, 0)")         # target
        con.execute(
            "INSERT INTO users(id, balance, ref_id, ref_link_id) VALUES (100, 0, 42, NULL)"
        )  # phone-only source с реферером
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (100, 'phone', '+79990009900', '2026-07-18', 0)"
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (200, 'telegram', '555', '2026-07-18', 1)"
        )
    identity.link_phone_provider(200, "+79990009900", set_verified=True)
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT ref_id FROM users WHERE id = 200"
        ).fetchone()[0] == 42


def test_merge_keeps_target_ref(tmp_db: Path) -> None:
    """У цели уже есть реферер → не перезаписываем."""
    import sqlite3
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (42, 0)")
        con.execute("INSERT INTO users(id, balance) VALUES (43, 0)")
        con.execute("INSERT INTO users(id, balance, ref_id) VALUES (200, 0, 43)")
        con.execute("INSERT INTO users(id, balance, ref_id) VALUES (100, 0, 42)")
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (100, 'phone', '+79990009901', '2026-07-18', 0)"
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (200, 'telegram', '556', '2026-07-18', 1)"
        )
    identity.link_phone_provider(200, "+79990009901", set_verified=True)
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT ref_id FROM users WHERE id = 200"
        ).fetchone()[0] == 43


def test_merge_repoints_partner_data(tmp_db: Path) -> None:
    """source сам был партнером: его рефералы, ссылки и бонусы переезжают на target."""
    import sqlite3
    from services import identity
    from services.referral import create_link
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (100, 0)")   # source-партнер
        con.execute("INSERT INTO users(id, balance) VALUES (200, 0)")   # target
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (100, 'phone', '+79990009902', '2026-07-18', 0)"
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (200, 'telegram', '557', '2026-07-18', 1)"
        )
    link = create_link(100, "promo")
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, balance, ref_id, ref_link_id) VALUES (300, 0, 100, ?)",
            (link["id"],),
        )  # реферал source-партнера
        con.execute(
            "INSERT INTO referral_bonuses(referrer_id, referred_user_id, refill_id,"
            " link_id, amount, percent, created_at)"
            " VALUES (100, 300, NULL, ?, 50, 10, '2026-07-18')",
            (link["id"],),
        )
    identity.link_phone_provider(200, "+79990009902", set_verified=True)
    with sqlite3.connect(tmp_db) as con:
        assert con.execute("SELECT ref_id FROM users WHERE id = 300").fetchone()[0] == 200
        assert con.execute(
            "SELECT user_id FROM referral_links WHERE id = ?", (link["id"],)
        ).fetchone()[0] == 200
        assert con.execute(
            "SELECT referrer_id FROM referral_bonuses"
        ).fetchone()[0] == 200


def test_merge_link_slug_collision_resolved(tmp_db: Path) -> None:
    """source и target владеют ссылкой с одинаковым слагом → слаг source
    переименовывается на валидный, мердж НЕ падает, дублей слагов нет."""
    import sqlite3
    from services import identity
    from services.referral import create_link
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (100, 0)")   # source
        con.execute("INSERT INTO users(id, balance) VALUES (200, 0)")   # target
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (100, 'phone', '+79990009903', '2026-07-18', 0)"
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (200, 'telegram', '558', '2026-07-18', 1)"
        )
    create_link(100, "promo")   # source owns 'promo'
    create_link(200, "promo")   # target ALSO owns 'promo'
    identity.link_phone_provider(200, "+79990009903", set_verified=True)  # must NOT raise
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute("SELECT user_id, slug FROM referral_links").fetchall()
        assert all(r[0] == 200 for r in rows)                       # both links now target's
        slugs = [r[1].lower() for r in rows]
        assert len(slugs) == len(set(slugs))                        # no duplicate slugs
        assert "promo" in slugs                                     # target's original preserved
        assert con.execute("SELECT COUNT(*) FROM users WHERE id=100").fetchone()[0] == 0  # source gone


def test_merge_carries_referral_balance_and_repoints_withdrawals(tmp_db: Path) -> None:
    """source has referral_balance + a withdrawal row → merges without
    IntegrityError; referral_balance is summed into target, the withdrawal
    row is repointed to target (mirrors how balance/referral_bonuses merge)."""
    import sqlite3
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance, referral_balance) VALUES (100, 0, 500)")
        con.execute("INSERT INTO users(id, balance, referral_balance) VALUES (200, 0, 100)")
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (100, 'phone', '+79990009903', '2026-07-18', 0)"
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (200, 'telegram', '558', '2026-07-18', 1)"
        )
        con.execute(
            "INSERT INTO referral_withdrawals(user_id, amount, destination, created_at) "
            "VALUES (100, 500, 'main_balance', '2026-07-18')"
        )
        con.commit()
    identity.link_phone_provider(200, "+79990009903", set_verified=True)
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT referral_balance FROM users WHERE id = 200").fetchone()
        assert row[0] == 600  # 100 + 500
        withdrawal_row = con.execute("SELECT user_id FROM referral_withdrawals").fetchone()
        assert withdrawal_row[0] == 200
