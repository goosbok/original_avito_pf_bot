"""Кнопка фильтра заказов называется так же, как статус в карточке.

`user_show_all:posted` отбирает заказы в статусе paid, т.е. «в работе»,
а подписана была «Размещённые» — клиент видел два разных слова про одно и то же.
"""


def _button_texts(keyboard):
    return [btn.text for row in keyboard.inline_keyboard for btn in row]


def test_paid_filter_button_default_label(tmp_db):
    from utils.sqlite3 import get_string
    assert get_string('btn_all_posted') == "🚀 В работе"


def test_done_filter_button_label_unchanged(tmp_db):
    from utils.sqlite3 import get_string
    assert get_string('btn_all_completed') == "✅ Выполненные"


def test_profile_keyboard_shows_in_progress_button(tmp_db):
    from keyboards.users_menu import profile_kb
    texts = _button_texts(profile_kb())
    assert "🚀 В работе" in texts
    assert not any("Размещ" in t for t in texts)
