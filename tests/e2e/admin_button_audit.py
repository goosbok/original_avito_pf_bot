"""E2E audit: click through every admin button and capture bot responses + crashes.

Run from repo root:
    .venv-test/bin/python tests/e2e/admin_button_audit.py
"""
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from client import get_client, button_texts, BOT


LOG_SINCE = None  # will be set at start


def docker_logs_since(start_iso: str) -> str:
    """Capture container logs since a given timestamp."""
    out = subprocess.run(
        ["docker", "logs", "original_avito_pf_bot-bot-1", "--since", start_iso],
        capture_output=True, text=True, timeout=10,
    )
    return out.stdout + out.stderr


async def click_and_capture(client, msg, label, timeout=2.5):
    """Click a button by label and return the bot's reply (latest message)."""
    try:
        await msg.click(text=label)
    except Exception as e:
        return None, f"CLICK_FAILED: {e}"
    await asyncio.sleep(timeout)
    msgs = await client.get_messages(BOT, limit=1)
    return (msgs[0] if msgs else None), None


async def click_and_back(client, parent_msg, label, results: list, scenario: str):
    """Click a button, record result, then go back to admin menu via /admin."""
    reply, err = await click_and_capture(client, parent_msg, label)
    status = "OK"
    text = ""
    if err:
        status = "ERR"
        text = err
    elif reply is None:
        status = "NO_REPLY"
    else:
        text = (reply.text or getattr(reply, "message", "") or "")[:200]
        if "⚠️" in text and "Ошибка" in text:
            status = "BOT_ERROR_MSG"
    results.append({"scenario": scenario, "button": label, "status": status, "text": text})
    return reply


async def main():
    global LOG_SINCE
    LOG_SINCE = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    client = get_client()
    await client.start()

    results: list[dict] = []

    # ----- Admin entry -----
    await client.send_message(BOT, "/admin")
    await asyncio.sleep(2)
    admin_menu = (await client.get_messages(BOT, limit=1))[0]
    btns_root = button_texts(admin_menu)
    results.append({"scenario": "entry", "button": "/admin", "status": "OK", "text": str(btns_root)[:200]})

    # Each subscenario re-sends /admin to get a fresh menu (handlers delete prior msg)
    async def fresh_menu():
        await client.send_message(BOT, "/admin")
        await asyncio.sleep(1.5)
        return (await client.get_messages(BOT, limit=1))[0]

    # ----- 1. Search order (asks for input) -----
    menu = await fresh_menu()
    reply = await click_and_back(client, menu, "🔎 Заказ", results, "search_order")
    if reply:
        await client.send_message(BOT, "999999")  # nonexistent order id
        await asyncio.sleep(2)
        latest = (await client.get_messages(BOT, limit=1))[0]
        results.append({"scenario": "search_order_invalid_id", "button": "999999",
                       "status": "OK" if latest else "NO_REPLY",
                       "text": (latest.text or "")[:200] if latest else ""})

    # ----- 2. User balance (asks for input) -----
    menu = await fresh_menu()
    reply = await click_and_back(client, menu, "💳 Баланс", results, "user_balance")
    if reply:
        await client.send_message(BOT, "nonexistent_user_xyz")
        await asyncio.sleep(2)
        latest = (await client.get_messages(BOT, limit=1))[0]
        results.append({"scenario": "user_balance_invalid", "button": "nonexistent_user_xyz",
                       "status": "OK" if latest else "NO_REPLY",
                       "text": (latest.text or "")[:200] if latest else ""})

    # ----- 3. Reviews -----
    menu = await fresh_menu()
    rev_menu = await click_and_back(client, menu, "⭐️ Отзывы", results, "reviews_man")
    if rev_menu:
        sub_btns = button_texts(rev_menu)
        for label in sub_btns:
            if label in ("⬅️ Назад", "🧊 Главное меню") or "Назад" in label:
                continue
            menu2 = await fresh_menu()
            rev_menu2 = await click_and_capture(client, menu2, "⭐️ Отзывы")
            if rev_menu2[0]:
                await click_and_back(client, rev_menu2[0], label, results, f"reviews:{label}")
                # If input requested, send junk to test None-guard
                if "Введите" in (rev_menu2[0].text or "") or "номер" in label.lower():
                    await client.send_message(BOT, "999999")
                    await asyncio.sleep(2)
                    latest = (await client.get_messages(BOT, limit=1))[0]
                    results.append({"scenario": f"reviews:{label}:invalid_input",
                                   "button": "999999",
                                   "status": "OK" if latest else "NO_REPLY",
                                   "text": (latest.text or "")[:200] if latest else ""})

    # ----- 4. Orders -----
    menu = await fresh_menu()
    ord_menu = await click_and_back(client, menu, "📖 Заказы", results, "orders_man")
    if ord_menu:
        for label in ["🔎 Найти", "🐹 По юзеру", "👌🏻 Выполненные", "✍🏻 Размещенные",
                      "✅ Выполнить", "❎ Удалить"]:
            menu2 = await fresh_menu()
            ord_menu2 = (await click_and_capture(client, menu2, "📖 Заказы"))[0]
            if ord_menu2:
                await click_and_back(client, ord_menu2, label, results, f"orders:{label}")
                if label in ("🔎 Найти", "🐹 По юзеру", "✅ Выполнить", "❎ Удалить"):
                    await client.send_message(BOT, "999999")
                    await asyncio.sleep(2)
                    latest = (await client.get_messages(BOT, limit=1))[0]
                    results.append({"scenario": f"orders:{label}:invalid",
                                   "button": "999999",
                                   "status": "OK" if latest else "NO_REPLY",
                                   "text": (latest.text or "")[:200] if latest else ""})

    # ----- 5. Settings → Admins → spam/report exclude -----
    menu = await fresh_menu()
    set_menu = await click_and_back(client, menu, "⚙️ Настройки", results, "settings")
    if set_menu:
        adm_menu = await click_and_back(client, set_menu, "👑 Админы", results, "settings:admins")
        if adm_menu:
            adm_btns = button_texts(adm_menu)
            # spam_exclude test
            for label in ["📧 Исключить из рассылки", "📝 Исключить из отчетов"]:
                if label in adm_btns:
                    menu3 = await fresh_menu()
                    s = (await click_and_capture(client, menu3, "⚙️ Настройки"))[0]
                    a = (await click_and_capture(client, s, "👑 Админы"))[0]
                    await click_and_back(client, a, label, results, f"admins:{label}")
                    await client.send_message(BOT, "definitely_nonexistent")
                    await asyncio.sleep(2)
                    latest = (await client.get_messages(BOT, limit=1))[0]
                    results.append({"scenario": f"admins:{label}:bad_user",
                                   "button": "definitely_nonexistent",
                                   "status": "OK" if latest else "NO_REPLY",
                                   "text": (latest.text or "")[:200] if latest else ""})

    # ----- 6. Promo codes -----
    menu = await fresh_menu()
    promo_menu = await click_and_back(client, menu, "🔮 Промокоды", results, "promo_codes")
    if promo_menu:
        for label in ["🔮 Создать", "🔮Показать промокоды", "🚫 Удалить",
                      "🔥Свой промокод🔥", "🚫Удалить активированные"]:
            menu2 = await fresh_menu()
            p = (await click_and_capture(client, menu2, "🔮 Промокоды"))[0]
            if p:
                await click_and_back(client, p, label, results, f"promo:{label}")

    # ----- 7. Users → various -----
    menu = await fresh_menu()
    u = await click_and_back(client, menu, "🐹 Юзеры", results, "users_man")
    if u:
        for label in ["🐹 Количество", "🐹 IDы", "❌ Удалить", "💎 показать VIPов",
                      "💎 уст. VIP", "💎 снять VIP", "💰 Финансы пользователя",
                      "💳 Управление балансом"]:
            menu2 = await fresh_menu()
            u2 = (await click_and_capture(client, menu2, "🐹 Юзеры"))[0]
            if u2:
                await click_and_back(client, u2, label, results, f"users:{label}")
                if label in ("❌ Удалить", "💎 уст. VIP", "💎 снять VIP",
                            "💰 Финансы пользователя", "💳 Управление балансом"):
                    await client.send_message(BOT, "nonexistent_xyz")
                    await asyncio.sleep(2)
                    latest = (await client.get_messages(BOT, limit=1))[0]
                    results.append({"scenario": f"users:{label}:invalid",
                                   "button": "nonexistent_xyz",
                                   "status": "OK" if latest else "NO_REPLY",
                                   "text": (latest.text or "")[:200] if latest else ""})

    # ----- 8. Messages menu -----
    menu = await fresh_menu()
    mm = await click_and_back(client, menu, "📝 Сообщения", results, "messages_menu")

    # ----- 9. Magic (referrals) -----
    menu = await fresh_menu()
    m = await click_and_back(client, menu, "🔗 Рефералки", results, "magic")
    if m:
        for label in ["🔗 Сгенерировать", "📖 Отчет по пользователю",
                      "📖 Таблица по заказам", "📖 Таблица по финансам"]:
            menu2 = await fresh_menu()
            m2 = (await click_and_capture(client, menu2, "🔗 Рефералки"))[0]
            if m2:
                await click_and_back(client, m2, label, results, f"magic:{label}")
                await client.send_message(BOT, "nonexistent_xyz")
                await asyncio.sleep(2)

    # ----- 10. gsheets - critical (was crashing) -----
    menu = await fresh_menu()
    await click_and_back(client, menu, "📖 Таблица по заказам", results, "gsheets_top")

    # ----- 11. Money by year -----
    menu = await fresh_menu()
    await click_and_back(client, menu, "💰 Финансовый отчет", results, "money_by_year")

    # ----- Capture logs -----
    await asyncio.sleep(2)
    logs = docker_logs_since(LOG_SINCE)
    errors = [line for line in logs.splitlines() if "ERROR" in line or "Traceback" in line or "Unhandled" in line]

    # ----- Report -----
    print("\n" + "=" * 80)
    print("ADMIN BUTTON AUDIT REPORT")
    print("=" * 80)
    bad = [r for r in results if r["status"] not in ("OK",)]
    print(f"\nTotal scenarios: {len(results)}")
    print(f"OK: {len([r for r in results if r['status'] == 'OK'])}")
    print(f"Non-OK: {len(bad)}\n")

    for r in results:
        marker = "✓" if r["status"] == "OK" else "✗"
        print(f"  {marker} [{r['status']:14}] {r['scenario']:50} → {r['button'][:40]}")
        if r["status"] != "OK" and r["text"]:
            print(f"      text: {r['text'][:100]}")

    print(f"\n--- Bot container errors since {LOG_SINCE} ---")
    if errors:
        for line in errors[:30]:
            print(f"  {line}")
    else:
        print("  (no unhandled exceptions captured)")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
