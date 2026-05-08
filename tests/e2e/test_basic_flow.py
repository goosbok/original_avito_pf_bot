"""Basic bot flow e2e tests.

Run:
    cd <project_root>
    .venv-test/bin/python -m pytest tests/e2e/test_basic_flow.py -v -s
"""
import asyncio
import os
import pytest
from client import get_client, send_and_wait, click_button, button_texts, BOT

AVITO_URL = os.environ.get("TEST_AVITO_URL", "")


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def bot_client():
    client = get_client()
    await client.start()
    yield client
    await client.disconnect()


@pytest.mark.asyncio
async def test_start_shows_main_menu(bot_client):
    msg = await send_and_wait(bot_client, "/start")
    assert msg is not None, "Бот не ответил на /start"
    btns = button_texts(msg)
    assert "🚀 Накрутка ПФ Авито" in btns, f"Кнопки: {btns}"
    assert "🪪 Личный кабинет" in btns


@pytest.mark.asyncio
async def test_profile_opens(bot_client):
    start_msg = await send_and_wait(bot_client, "/start")
    msg = await click_button(bot_client, start_msg, "🪪 Личный кабинет")
    assert msg is not None
    assert "Личный кабинет" in (msg.text or ""), f"Ответ: {msg.text}"
    assert "Баланс" in (msg.text or "")


@pytest.mark.asyncio
async def test_pf_avito_flow(bot_client):
    start_msg = await send_and_wait(bot_client, "/start")
    tarif_msg = await click_button(bot_client, start_msg, "🚀 Накрутка ПФ Авито")
    assert tarif_msg is not None
    btns = button_texts(tarif_msg)
    # Должны быть кнопки выбора периода
    assert any("День" in b or "Неделя" in b or "Месяц" in b for b in btns), f"Кнопки: {btns}"


@pytest.mark.asyncio
async def test_info_start(bot_client):
    start_msg = await send_and_wait(bot_client, "/start")
    msg = await click_button(bot_client, start_msg, "🕐 Как начать работу")
    assert msg is not None
    assert msg.text or msg.caption
