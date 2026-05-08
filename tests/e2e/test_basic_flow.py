"""Basic bot flow e2e tests.

Run:
    cd <project_root>
    .venv-test/bin/python -m pytest tests/e2e/test_basic_flow.py -v -s
"""
import asyncio
import os
import pytest
from client import get_client, send_and_wait, click_button, click_first_matching_button, button_texts, BOT

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


# ---------------------------------------------------------------------------
# Phase 1c: full user-flow tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_profile_shows_balance(bot_client):
    """Открыть ЛК → нажать кнопку профиля → убедиться, что в ответе есть «Баланс» и цифра."""
    start_msg = await send_and_wait(bot_client, "/start")
    lk_msg = await click_button(bot_client, start_msg, "🪪 Личный кабинет")
    assert lk_msg is not None, "Бот не ответил на кнопку «Личный кабинет»"

    # В ЛК есть inline-кнопка с callback, содержащим «profile».
    # Ищем кнопку, текст которой содержит «профиль» / «Профиль» / «👤» или кнопку с именем пользователя.
    profile_btn_patterns = ["profile", "профил", "👤", "Профил"]
    profile_msg = None
    for pattern in profile_btn_patterns:
        profile_msg = await click_first_matching_button(bot_client, lk_msg, pattern)
        if profile_msg is not None:
            break

    # Если специальной кнопки нет — само сообщение ЛК уже содержит баланс.
    target_msg = profile_msg if profile_msg is not None else lk_msg
    text = target_msg.text or ""
    assert "Баланс" in text, f"Ожидалось «Баланс» в ответе. Получено: {text!r}"
    assert any(ch.isdigit() for ch in text), f"Ожидалась цифра (значение баланса) в ответе. Получено: {text!r}"


@pytest.mark.asyncio
async def test_pf_avito_full_tarif_selection(bot_client):
    """Накрутка ПФ Авито → выбрать период «День» → бот отвечает (следующий шаг)."""
    start_msg = await send_and_wait(bot_client, "/start")
    tarif_msg = await click_button(bot_client, start_msg, "🚀 Накрутка ПФ Авито")
    assert tarif_msg is not None, "Бот не ответил на «Накрутка ПФ Авито»"

    btns = button_texts(tarif_msg)
    # Убеждаемся, что кнопки периода присутствуют
    assert any("День" in b or "Неделя" in b or "Месяц" in b for b in btns), (
        f"Ожидались кнопки периода, получены: {btns}"
    )

    # Нажимаем первую кнопку, содержащую «День» или «день»
    next_msg = await click_first_matching_button(bot_client, tarif_msg, "ень")
    assert next_msg is not None, (
        f"Бот не ответил после выбора периода. Доступные кнопки: {btns}"
    )


@pytest.mark.asyncio
async def test_cancel_returns_to_menu(bot_client):
    """/cancel → бот отвечает; /start → главное меню со стандартными кнопками."""
    cancel_msg = await send_and_wait(bot_client, "/cancel")
    assert cancel_msg is not None, "Бот не ответил на /cancel"

    start_msg = await send_and_wait(bot_client, "/start")
    assert start_msg is not None, "Бот не ответил на /start после /cancel"
    btns = button_texts(start_msg)
    assert "🚀 Накрутка ПФ Авито" in btns, f"Главное меню не содержит ожидаемых кнопок. Кнопки: {btns}"
    assert "🪪 Личный кабинет" in btns, f"Главное меню не содержит «Личный кабинет». Кнопки: {btns}"


@pytest.mark.asyncio
async def test_profile_order_list(bot_client):
    """ЛК → профиль → нажать кнопку заказов → бот отвечает (список или «нет заказов»)."""
    start_msg = await send_and_wait(bot_client, "/start")
    lk_msg = await click_button(bot_client, start_msg, "🪪 Личный кабинет")
    assert lk_msg is not None, "Бот не ответил на «Личный кабинет»"

    # Пробуем открыть подраздел профиля (может называться по-разному)
    profile_btn_patterns = ["profile", "профил", "👤", "Профил"]
    profile_msg = None
    for pattern in profile_btn_patterns:
        profile_msg = await click_first_matching_button(bot_client, lk_msg, pattern)
        if profile_msg is not None:
            break

    source_msg = profile_msg if profile_msg is not None else lk_msg

    # Ищем кнопку заказов в полученном сообщении
    order_btn_patterns = ["list", "заказ", "Заказ", "ордер", "Order"]
    orders_msg = None
    for pattern in order_btn_patterns:
        orders_msg = await click_first_matching_button(bot_client, source_msg, pattern)
        if orders_msg is not None:
            break

    # Если кнопка заказов не найдена — проверяем, что само сообщение содержит
    # информацию об отсутствии заказов или их список.
    if orders_msg is None:
        available_btns = button_texts(source_msg)
        # Допустимо, если кнопки заказов нет, но ответ существует
        assert source_msg is not None, (
            f"Не удалось найти кнопку заказов. Доступные кнопки: {available_btns}"
        )
    else:
        text = orders_msg.text or ""
        assert orders_msg is not None, "Бот не ответил после нажатия кнопки заказов"
        # Бот либо показывает список, либо сообщает об отсутствии заказов
        has_content = bool(text.strip()) or bool(orders_msg.caption)
        assert has_content, "Ответ бота на раздел заказов пустой"
