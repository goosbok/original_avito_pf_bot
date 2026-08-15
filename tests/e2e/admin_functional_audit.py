"""Functional admin E2E audit.

Each scenario does click→input→assert-DB-state. Unlike admin_button_audit.py
(which only checked that nothing crashed), this one verifies the bot's
"✅ Done!" messages are not lying.

Run from repo root:
    .venv-test/bin/python tests/e2e/admin_functional_audit.py
"""
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from client import get_client, button_texts, BOT


def db_query(sql, *params):
    """Run a query inside the bot container and return JSON-decodable rows.
    Commits after the statement so INSERT/DELETE/UPDATE actually persist."""
    py = (
        "import sqlite3, json, sys; "
        "con = sqlite3.connect('/app/storage/database.db'); "
        "con.row_factory = sqlite3.Row; "
        f"cur = con.execute({sql!r}, {list(params)!r}); "
        "rows = cur.fetchall(); "
        "con.commit(); "
        "print(json.dumps([dict(r) for r in rows]))"
    )
    out = subprocess.run(
        ["docker", "exec", "original_avito_pf_bot-bot-1", "python", "-c", py],
        capture_output=True, text=True, timeout=10,
    )
    if out.returncode != 0:
        return [{"_error": out.stderr}]
    import json
    return json.loads(out.stdout.strip() or "[]")


def db_setting(parametr):
    rows = db_query("SELECT value FROM settings WHERE parametr = ?", parametr)
    return rows[0]["value"] if rows else None


def db_user(internal_id):
    rows = db_query("SELECT id, balance, is_vip FROM users WHERE id = ?", internal_id)
    return rows[0] if rows else None


async def wait_reply(client, timeout=2.5):
    await asyncio.sleep(timeout)
    msgs = await client.get_messages(BOT, limit=1)
    return msgs[0] if msgs else None


async def fresh_menu(client):
    await client.send_message(BOT, "/admin")
    return await wait_reply(client)


async def click(client, msg, label, t=2.0):
    try:
        await msg.click(text=label)
    except Exception as e:
        return None, f"click_failed: {e}"
    return await wait_reply(client, t), None


async def click_pattern(client, msg, pattern, t=2.0):
    """Click first button whose text contains *pattern*."""
    if not msg or not msg.reply_markup:
        return None
    for i, row in enumerate(msg.reply_markup.rows):
        for j, btn in enumerate(row.buttons):
            if pattern in btn.text:
                await msg.click(i, j)
                return await wait_reply(client, t)
    return None


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

async def scenario_min_amount(client, results):
    """Change min_amount → verify DB row updated → verify bot shows new value."""
    NEW = "777"
    before = db_setting("min_amount")
    menu = await fresh_menu(client)
    settings = (await click(client, menu, "⚙️ Настройки"))[0]
    price = (await click(client, settings, "💰 Касса/цены"))[0]
    min_amo = await click_pattern(client, price, "Минимальный платеж")
    if not min_amo:
        results.append({"name": "min_amount", "status": "BUTTON_NOT_FOUND", "detail": ""})
        return
    await client.send_message(BOT, NEW)
    await asyncio.sleep(2.5)
    after_db = db_setting("min_amount")
    # Reopen the min_amount screen and read displayed number
    menu2 = await fresh_menu(client)
    settings2 = (await click(client, menu2, "⚙️ Настройки"))[0]
    price2 = (await click(client, settings2, "💰 Касса/цены"))[0]
    reopened = await click_pattern(client, price2, "Минимальный платеж")
    displayed_ok = NEW in (reopened.text if reopened else "")
    ok = (after_db == NEW) and displayed_ok
    results.append({
        "name": "min_amount",
        "status": "OK" if ok else "FAIL",
        "detail": f"before={before!r} → set {NEW!r} → db_after={after_db!r}, displayed_ok={displayed_ok}",
    })


async def scenario_payment_toggle(client, results):
    """Toggle payment_work → DB value flipped."""
    before = db_setting("payment_work")
    menu = await fresh_menu(client)
    settings = (await click(client, menu, "⚙️ Настройки"))[0]
    price = (await click(client, settings, "💰 Касса/цены"))[0]
    # The toggle button is either "❎Отключить" or "✅Включить"
    toggled = await click_pattern(client, price, "ключить")
    after = db_setting("payment_work")
    ok = before != after
    results.append({
        "name": "payment_toggle",
        "status": "OK" if ok else "FAIL",
        "detail": f"before={before!r} → after={after!r}",
    })
    # Toggle back
    if toggled:
        await click_pattern(client, toggled, "ключить")


async def scenario_balance_change(client, results):
    """Set test user balance to 12345 → assert users.balance updated."""
    TARGET_USER = "yamagruh"  # test account, id=1
    NEW_BAL = "12345"
    before = db_user(1)
    menu = await fresh_menu(client)
    bal_btn = (await click(client, menu, "💳 Баланс"))[0]
    await client.send_message(BOT, TARGET_USER)
    await asyncio.sleep(2.5)
    await client.send_message(BOT, NEW_BAL)
    await asyncio.sleep(2.5)
    after = db_user(1)
    ok = after and str(after["balance"]) == NEW_BAL
    results.append({
        "name": "balance_change",
        "status": "OK" if ok else "FAIL",
        "detail": f"before_balance={before['balance'] if before else None} → after={after['balance'] if after else None}",
    })
    # Restore
    db_query("UPDATE users SET balance=? WHERE id=?", before["balance"] if before else 0, 1)


async def scenario_vip_set_unset(client, results):
    """Set then unset VIP → assert users.is_vip toggles."""
    before = db_user(1)
    # Set VIP
    menu = await fresh_menu(client)
    users = (await click(client, menu, "🐹 Юзеры"))[0]
    set_vip = await click_pattern(client, users, "уст. VIP")
    await client.send_message(BOT, "yamagruh")
    await asyncio.sleep(2.5)
    after_set = db_user(1)
    set_ok = after_set and after_set["is_vip"] == 1

    # Unset VIP
    menu2 = await fresh_menu(client)
    users2 = (await click(client, menu2, "🐹 Юзеры"))[0]
    unset_vip = await click_pattern(client, users2, "снять VIP")
    await client.send_message(BOT, "yamagruh")
    await asyncio.sleep(2.5)
    after_unset = db_user(1)
    unset_ok = after_unset and after_unset["is_vip"] == 0

    results.append({
        "name": "vip_set",
        "status": "OK" if set_ok else "FAIL",
        "detail": f"before_vip={before['is_vip'] if before else None} → after_vip={after_set['is_vip'] if after_set else None}",
    })
    results.append({
        "name": "vip_unset",
        "status": "OK" if unset_ok else "FAIL",
        "detail": f"after_set={after_set['is_vip'] if after_set else None} → after_unset={after_unset['is_vip'] if after_unset else None}",
    })


async def scenario_promocode_create(client, results):
    """Create auto-promocode → DB row exists."""
    before_rows = db_query("SELECT COUNT(*) AS c FROM promocodes")
    before_n = before_rows[0]["c"] if before_rows else 0
    menu = await fresh_menu(client)
    promo = (await click(client, menu, "🔮 Промокоды"))[0]
    created = await click_pattern(client, promo, "Создать")
    after_rows = db_query("SELECT COUNT(*) AS c FROM promocodes")
    after_n = after_rows[0]["c"] if after_rows else 0
    ok = after_n == before_n + 1
    # Fetch the newest promo code straight from DB (more reliable than parsing bot text)
    code = None
    if ok:
        newest = db_query("SELECT code FROM promocodes ORDER BY increment DESC LIMIT 1")
        code = newest[0]["code"] if newest else None
    results.append({
        "name": "promo_create",
        "status": "OK" if ok else "FAIL",
        "detail": f"count {before_n} → {after_n}, new_code={code}",
    })
    return code


async def scenario_promo_delete(client, results, code):
    """Delete promocode → DB row removed."""
    if not code:
        results.append({"name": "promo_delete", "status": "SKIPPED", "detail": "no code from create step"})
        return
    before_rows = db_query("SELECT COUNT(*) AS c FROM promocodes WHERE code=?", code)
    before_n = before_rows[0]["c"] if before_rows else 0
    menu = await fresh_menu(client)
    promo = (await click(client, menu, "🔮 Промокоды"))[0]
    del_btn = await click_pattern(client, promo, "🚫 Удалить")
    await client.send_message(BOT, code)
    await asyncio.sleep(2.5)
    after_rows = db_query("SELECT COUNT(*) AS c FROM promocodes WHERE code=?", code)
    after_n = after_rows[0]["c"] if after_rows else 0
    ok = (before_n >= 1) and (after_n == 0)
    results.append({
        "name": "promo_delete",
        "status": "OK" if ok else "FAIL",
        "detail": f"count {before_n} → {after_n}",
    })


async def scenario_spam_exclude(client, results):
    """Add user to spam_exclude → DB value contains their id."""
    TARGET = "yamagruh"  # internal id=1
    before = db_setting("spam_exclude") or ""
    menu = await fresh_menu(client)
    settings = (await click(client, menu, "⚙️ Настройки"))[0]
    admins = (await click(client, settings, "👑 Админы"))[0]
    spam = await click_pattern(client, admins, "Исключить из рассылки")
    await client.send_message(BOT, TARGET)
    await asyncio.sleep(2.5)
    after = db_setting("spam_exclude") or ""
    ok = "1" in after.split(",") and "1" not in before.split(",")
    if "1" in before.split(","):
        ok = "1" in after.split(",")  # already there; should still be there
    results.append({
        "name": "spam_exclude_add",
        "status": "OK" if ok else "FAIL",
        "detail": f"before={before!r} → after={after!r}",
    })


async def scenario_report_exclude(client, results):
    """Add user to report_exclude → DB value contains their id."""
    TARGET = "yamagruh"
    before = db_setting("report_exclude") or ""
    menu = await fresh_menu(client)
    settings = (await click(client, menu, "⚙️ Настройки"))[0]
    admins = (await click(client, settings, "👑 Админы"))[0]
    rep = await click_pattern(client, admins, "Исключить из отчетов")
    await client.send_message(BOT, TARGET)
    await asyncio.sleep(2.5)
    after = db_setting("report_exclude") or ""
    ok = "1" in after.split(",")
    results.append({
        "name": "report_exclude_add",
        "status": "OK" if ok else "FAIL",
        "detail": f"before={before!r} → after={after!r}",
    })


async def scenario_str_visual_edit(client, results):
    """Seed a str_ row, then edit it via visual editor → assert DB row updated.

    Also verifies the fix for str_edit_value index-mismatch: previously the
    handler indexed all_str (unfiltered) with an index drawn from the
    filtered captions_array → editing string A could write row B.
    """
    NEW = "TESTVAL_42"
    SEED = "str_test_seed"
    # Seed: ensure exactly one str_ row exists at index 0, plus a btn_ row that
    # would shift the unfiltered index and trigger the old bug.
    db_query("DELETE FROM strings WHERE parametr IN (?, ?)", SEED, "btn_test_pad")
    db_query("INSERT INTO strings(parametr, description, value) VALUES (?, '', 'old_value'), (?, '', 'pad')", SEED, "btn_test_pad")
    menu = await fresh_menu(client)
    settings = (await click(client, menu, "⚙️ Настройки"))[0]
    iface = (await click(client, settings, "⚙️ Интерфейс"))[0]
    editor = await click_pattern(client, iface, "Редактор строк")
    if not editor:
        results.append({"name": "str_visual_edit", "status": "BUTTON_NOT_FOUND", "detail": ""})
        return
    # Click ✏️ to edit the first str_ row
    edit_btn = await click_pattern(client, editor, "✏️")
    await client.send_message(BOT, NEW)
    await asyncio.sleep(2.5)
    after_rows = db_query("SELECT value FROM strings WHERE parametr = ?", SEED)
    pad_rows = db_query("SELECT value FROM strings WHERE parametr = ?", "btn_test_pad")
    after = after_rows[0]["value"] if after_rows else None
    pad_after = pad_rows[0]["value"] if pad_rows else None
    ok = after == NEW and pad_after == "pad"
    results.append({
        "name": "str_visual_edit",
        "status": "OK" if ok else "FAIL",
        "detail": f"seed str→{after!r} (expected {NEW!r}), btn_pad untouched? value={pad_after!r}",
    })
    # Cleanup
    db_query("DELETE FROM strings WHERE parametr IN (?, ?)", SEED, "btn_test_pad")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    client = get_client()
    await client.start()

    results = []
    await scenario_min_amount(client, results)
    await scenario_payment_toggle(client, results)
    await scenario_balance_change(client, results)
    await scenario_vip_set_unset(client, results)
    code = await scenario_promocode_create(client, results)
    await scenario_promo_delete(client, results, code)
    await scenario_spam_exclude(client, results)
    await scenario_report_exclude(client, results)
    await scenario_str_visual_edit(client, results)

    await client.disconnect()

    print("\n" + "=" * 80)
    print("FUNCTIONAL ADMIN AUDIT")
    print("=" * 80)
    ok_count = sum(1 for r in results if r["status"] == "OK")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    print(f"OK: {ok_count}  |  FAIL: {fail_count}  |  Other: {len(results) - ok_count - fail_count}")
    print()
    for r in results:
        mark = "✓" if r["status"] == "OK" else "✗"
        print(f"  {mark} [{r['status']:14}] {r['name']:25}")
        if r["detail"]:
            print(f"      {r['detail'][:200]}")


if __name__ == "__main__":
    asyncio.run(main())
