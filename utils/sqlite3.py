# - *- coding: utf- 8 - *-
import json
import sqlite3
import ast
from colorama import Fore
from data.config import path_database as path_db
from data.config import *
from utils.other import get_date, str2dict

# Преобразование полученного списка в словарь
def dict_factory(cursor, row):
    save_dict = {}

    for idx, col in enumerate(cursor.description):
        save_dict[col[0]] = row[idx]

    return save_dict


# Форматирование запроса без аргументов
def query(sql, parameters: dict):
    if "XXX" not in sql: sql += " XXX "
    values = ", ".join([
        f"{item} = ?" for item in parameters
    ])
    sql = sql.replace("XXX", values)

    return sql, list(parameters.values())


# Форматирование запроса с аргументами
def str2dict(str_value):
    result_dict = ast.literal_eval(str_value)

    return result_dict
################################################################################################
##################################         Настройки          ##################################
################################################################################################

def add_string_to_base(parametr, description, str_value):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        try:
            con.execute(
                "INSERT INTO strings (parametr, description, value) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(parametr) DO UPDATE SET "
                "description = excluded.description, value = excluded.value",
                [parametr, description, str_value]
            )
            con.commit()
        except Exception as e:
            print(f"{Fore.RED}Error. The parameter has not been added:{Fore.RESET}\n{e}")


_STRING_DEFAULTS: dict[str, str] = {
    # ── buttons ──────────────────────────────────────────────────────────────
    "btn_how_to_start": "🕐 Как начать работу",
    "btn_avito": "🚀 Накрутка ПФ Авито",
    "btn_profile": "🪪 Личный кабинет",
    "btn_channel": "TG канал⛓️‍💥",
    "btn_site": "🌐 Наш сайт",
    "btn_main_menu": "🧊 Главное меню",
    "btn_yes": "✅ Да",
    "btn_no": "❎ Нет",
    "btn_all_completed": "✅ Выполненные",
    "btn_all_posted": "✍️ Размещённые",
    "btn_avito_cases": "🔗 Кейсы Авито",
    "btn_support": "🧑‍💻 Тех поддержка",
    "btn_qna": "📲 FAQ / Кейсы",
    "btn_promocodes": "🔮 Промокоды",
    "btn_refill_balance": "💳 Пополнить баланс",
    "btn_video_guide": "🎬 Видео-инструкция",
    # ── user-facing messages ─────────────────────────────────────────────────
    "str_select_action": "📋 Выберите действие:",
    "srt_select_variant_pf": "📋 Выберите действие:",
    "str_user_profile": (
        "🪪 <b>Личный кабинет</b>\n\n"
        "💰 Баланс: <b>{}</b> ₽\n"
        "🔗 Реферальная ссылка: {}\n"
        "👥 Рефералов: <b>{}</b>"
    ),
    "str_error": (
        "⚠️ К сожалению, во время операции произошла ошибка.\n\n"
        "Мы уже ведём работы по её устранению. "
        "Если с вас были списаны деньги, а услуга недоступна — "
        "напишите нам в поддержку."
    ),
    "str_cmd_cancel": "❌ Отменено.",
    "str_your_id": "🆔 Ваш ID: <code>{}</code>",
    "str_delete_user": "🗑 Пользователь {} удалён.",
    "str_bad_command": "❓ Неизвестная команда.",
    "str_input_promo": "🔮 Введите промокод:",
    "str_promo_activated": "✅ Промокод активирован! Начислено: <b>{}</b> ₽. Баланс: <b>{}</b> ₽.",
    "str_promo_inactive": "❌ Промокод уже использован.",
    "str_promo_reactiv": "❌ Вы уже активировали промокод <b>{}</b>.",
    "str_promo_bad": "❌ Промокод не найден.",
    "str_msg_admin_promo": "🔮 Промокод <b>{}</b> активирован пользователем {}. Баланс: <b>{}</b> ₽.",
    "str_refill_balance_text": "💳 Введите сумму пополнения (целое число):",
    "str_payment_not_work": "⚠️ Оплата временно недоступна. Обратитесь к менеджеру: {}",
    "str_input_order_number": "🔢 Введите номер заказа:",
    "str_order_status_txt": "📦 Заказ #{}: статус <b>{}</b>",
    "str_not_your_order": "❌ Это не ваш заказ.",
    "no_such_order": "❌ Заказ не найден.",
    "str_error_get_orders": "❌ Не удалось получить заказы.",
    "str_no_posted_orders": "📭 Нет заказов с таким статусом.",
    "str_not_enough_money": (
        "💰 Недостаточно средств.\n"
        "Баланс: <b>{}</b> ₽ | Сумма: <b>{}</b> ₽ | Не хватает: <b>{}</b> ₽"
    ),
    "str_more_money": "⚠️ Минимальная сумма пополнения: <b>{}</b> ₽.",
    "str_select_payment_method": "💳 Выберите способ оплаты для пополнения на <b>{}</b> ₽:",
    "str_manual_payment": (
        "📋 Для пополнения на <b>{}</b> ₽ напишите менеджеру:\n\n"
        "<code>{}</code>"
    ),
    "str_debet_money": "К оплате: <b>{}</b> ₽",
    "str_pay_error": "❌ Ошибка оплаты. Обратитесь в поддержку: {}",
    "str_payment_error": "❌ Не удалось создать счёт. Обратитесь в поддержку: {}",
    "str_usr_pay_success": "✅ Оплата <b>{}</b> ₽ прошла. Баланс: <b>{}</b> ₽.",
    "str_adm_pay_success": "💰 Пополнение <b>{}</b> ₽ от {}. Баланс: <b>{}</b> ₽.",
    "str_ref_balance_refil": "🎁 Ваш реферал пополнил баланс! Вам начислено <b>{}</b> ₽. Баланс: <b>{}</b> ₽.",
    "str_tasks_text": "📋 Стоимость накрутки ПФ: <b>{}</b> ₽/шт. в день.",
    "str_how_to_start_text": (
        "1️⃣ Кликаем на «Заказать ПФ Авито»\n"
        "2️⃣ Выбираем какое количество дней накручивать просмотры подряд\n"
        "3️⃣ Дальше кол-во просмотров на объяву в день сколько хотим крутить\n"
        "4️⃣ Вставляем ссылку на объявление авито "
        "(можно сразу много объявлений/ссылок)\n"
        "5️⃣ Надо ли крутить «запрос контактов», это посмотреть номер телефона "
        "«не звонить». Подсказка: для товарки — да, для услуг — нет.\n"
        "6️⃣ Подтверждаем списание денег "
        "(если их на балансе нет, то предложит — окно оплаты)"
    ),
    "str_qna_text": "📲 <b>FAQ / Кейсы</b>\n\nВопросы и ответы не заданы.",
    "str_support_text": "🧑‍💻 Техническая поддержка: {}",
    "str_pf_text": (
        "📅 Период: <b>{} {}</b>\n"
        "💰 Стоимость: <b>{}</b> ₽/шт. в день\n\n"
        "Выберите количество объявлений:"
    ),
    "str_enter_days": "📅 Введите количество дней (целое число ≥ 1):",
    "str_enter_pf": "🔢 Введите количество объявлений (≥ 5):",
    "str_bad_number": "❌ Неверное число. Попробуйте ещё раз.",
    "str_pf_links": (
        "🔗 <b>Вставьте ссылки на объявления Авито</b>\n\n"
        "По одной ссылке на строку. Принимаются только ссылки avito.ru"
    ),
    "str_bad_link": "❌ Ссылки {} не найдены. Проверьте и попробуйте снова.",
    "str_pf_contacts": (
        "Накручиваем запросы контактов?\n"
        "Совет: товарка — ✅ ; услуги — ❌"
    ),
    "str_debet_pf": "💰 К списанию: <b>{}</b> ₽. Подтвердить заказ?",
    "str_new_order_text": (
        "📦 <b>Новый заказ #{}</b>\n"
        "💰 Сумма: <b>{}</b> ₽\n"
        "👤 Пользователь: {}\n"
        "📋 Тариф: {}\n"
        "📊 Статус: {}\n"
        "📞 Контакт: {}\n"
        "📅 Дата: {}\n"
        "🔗 Ссылок: {}\n{}"
    ),
    "str_order_text": (
        "📦 <b>Заказ #{}</b>\n"
        "💰 Сумма: <b>{}</b> ₽\n"
        "👤 Пользователь: {}\n"
        "📋 Тариф: {}\n"
        "📊 Статус: {}\n"
        "📞 Контакт: {}\n"
        "📅 Дата: {}\n"
        "🔗 Ссылок: {}\n{}"
    ),
    "str_order_confirm": "✅ Заказ #{} размещён! Менеджер свяжется с вами.",
}

# Defaults for the `settings` table — used when row is missing or value is empty.
_SETTING_DEFAULTS: dict[str, str] = {
    "payment_work": "true",
    "min_amount": "100",
    "manager_nick": "support",
    "channel_link": "https://t.me/pf_avito_top",
    "egg_sticker": "",
    "ref_percent": "10",
}

# Defaults for the `settings` table when used as prices (numeric or dict-as-string).
_PRICE_DEFAULTS: dict[str, str] = {
    "price_avito_pf": "6",
    "price_seo": "1500",
    "price_avito_del_review": "7000",
    "seo_price": "1500",
}

#Получаем строку из базы или из конфига
def get_string(param):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        str_value = con.execute("SELECT * FROM strings WHERE parametr = ?", (param,)).fetchone()
        # Fall back to defaults when row missing OR value is empty/null —
        # otherwise a placeholder row in the DB silently breaks .format() calls.
        if str_value and str_value['value']:
            return str_value['value']
        return _STRING_DEFAULTS.get(param) or globals().get(param)


#Получаем настройку из базы или из конфига
def get_setting(param):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        setting = con.execute("SELECT * FROM settings WHERE parametr = ?", (param,)).fetchone()
        if setting and setting['value']:
            return setting['value']
        return _SETTING_DEFAULTS.get(param) or globals().get(param)

def get_setting_from_base(param):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        setting = con.execute("SELECT * FROM settings WHERE parametr = ?", (param,)).fetchone()
        return setting

#Получаем все настройки
def get_all_settings():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM settings").fetchall()

#Добавить настройку в базу
def add_setting_to_base(parametr, description, str_value):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        try:
            con.execute(
                "INSERT INTO settings (parametr, description, value) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(parametr) DO UPDATE SET "
                "description = excluded.description, value = excluded.value",
                [parametr, description, str_value]
            )
            con.commit()
        except Exception as e:
            print(f"{Fore.RED}Error. The parameter has not been added:{Fore.RESET}\n{e}")

#Редактируем строку из базы
def edit_string(param, value):
    # UPSERT — defaults live in _STRING_DEFAULTS (not the DB), so a plain UPDATE
    # silently no-ops when the row hasn't been materialized yet.
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute(
            "INSERT INTO strings (parametr, description, value) "
            "VALUES (?, '', ?) "
            "ON CONFLICT(parametr) DO UPDATE SET value = excluded.value",
            [param, value]
        )
        con.commit()

#Редактируем настройку из базы
def edit_setting(param, value):
    # UPSERT — same reasoning as edit_string above (defaults in _SETTING_DEFAULTS).
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute(
            "INSERT INTO settings (parametr, description, value) "
            "VALUES (?, '', ?) "
            "ON CONFLICT(parametr) DO UPDATE SET value = excluded.value",
            [param, value]
        )
        con.commit()

def get_string_from_base(env_string):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM strings WHERE parametr = ?", (env_string,)).fetchone()

def get_all_strings():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM strings").fetchall()

def get_all_qna_avito():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        #req = "SELECT * FROM strings WHERE parametr LIKE 'qna_avito%'"
        req = """SELECT * FROM strings
        WHERE parametr LIKE 'qna_avito:%'
        ORDER BY CAST(SUBSTR(parametr, INSTR(parametr, ':') + 1) AS INTEGER)"""
        return con.execute(req).fetchall()

#Прайс. Получить
def get_price(param):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        setting = con.execute("SELECT * FROM settings WHERE parametr = ?", (param,)).fetchone()
    raw = setting['value'] if (setting and setting['value']) else (
        _PRICE_DEFAULTS.get(param) or globals().get(param)
    )
    if raw is None:
        return None
    # Numeric price (e.g. "6") → int; dict-as-string (e.g. "{'5': 600}") → dict.
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, int):
        return raw
    raw_str = str(raw).strip()
    if raw_str.isdigit():
        return int(raw_str)
    try:
        return str2dict(raw_str)
    except (ValueError, SyntaxError):
        return None

def edit_price(param, prices):
    req = "UPDATE settings SET value = ? WHERE parametr = ?"
    prices_str = json.dumps(prices)
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute(req, [prices_str, param])

#Админы
def get_admins():
    admins = []
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        adm = con.execute("SELECT * FROM settings WHERE parametr = 'admins'").fetchone()

        if adm and 'value' in adm:
            # Получаем строку и разделяем её на массив
            administrators = adm['value'].strip()
            if administrators:  # Проверяем, что строка не пустая
                admins = administrators.split(',')  # Делаем список
                admins = [admin.strip() for admin in admins if admin.strip()]  # Убираем лишние пробелы и пустые элементы

    return admins

def add_admin(user_id):
    user_id_str = str(user_id)
    admins = get_admins()

    # Убедимся, что user_id уникален
    if user_id_str not in admins:
        admins.append(user_id_str)  # Добавляем нового администратора
        with sqlite3.connect(path_db) as con:
            con.execute(
                "INSERT INTO settings (parametr, description, value) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(parametr) DO UPDATE SET "
                "description = excluded.description, value = excluded.value",
                ('admins', 'Админы', ','.join(admins))  # Сохраняем строку, разделенную запятыми
            )
        con.commit()
    else:
        print(f"Admin with user_id {user_id_str} already exists.")

def del_admin(user_id):
    user_id_str = str(user_id)
    admins = get_admins()
    new_admins = [admin for admin in admins if admin != user_id_str]

    if len(admins) != len(new_admins):
        with sqlite3.connect(path_db) as con:
            con.execute(
                "UPDATE settings SET value = ? WHERE parametr = 'admins'",
                (','.join(new_admins),)  # Устанавливаем обновленный список администраторов
            )
        con.commit()
    else:
        print(f"Admin with user_id {user_id_str} not found.")

def get_tg_id_for_user(internal_user_id: int) -> "int | None":
    """Return the Telegram chat_id for an internal user PK, or None if not found."""
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        row = con.execute(
            "SELECT identifier FROM auth_providers WHERE user_id = ? AND provider = 'telegram'",
            (internal_user_id,)
        ).fetchone()
    return int(row["identifier"]) if row else None

def get_all_telegram_ids() -> "list[int]":
    """Return all Telegram IDs registered in auth_providers."""
    with sqlite3.connect(path_db) as con:
        rows = con.execute(
            "SELECT identifier FROM auth_providers WHERE provider = 'telegram'"
        ).fetchall()
    return [int(row[0]) for row in rows]

#Исключения
def get_spam_exclude():
    usrs = []
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        excludes = con.execute("SELECT * FROM settings WHERE parametr = 'spam_exclude'").fetchone()

        if excludes and 'value' in excludes:
            # Получаем строку и разделяем её на массив
            users = excludes['value'].strip()
            if users:  # Проверяем, что строка не пустая
                usrs = users.split(',')  # Делаем список
                usrs = [user.strip() for user in usrs if user.strip()]  # Убираем лишние пробелы и пустые элементы

    return usrs

def add_spam_exclude(user_id):
    user_id_str = str(user_id)
    admins = get_spam_exclude()

    # Убедимся, что user_id уникален
    if user_id_str not in admins:
        admins.append(user_id_str)  # Добавляем нового администратора
        with sqlite3.connect(path_db) as con:
            con.execute(
                "INSERT INTO settings (parametr, description, value) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(parametr) DO UPDATE SET "
                "description = excluded.description, value = excluded.value",
                ('spam_exclude', 'Исключены из рассылки', ','.join(admins))  # Сохраняем строку, разделенную запятыми
            )
        con.commit()
    else:
        print(f"User with user_id {user_id_str} already in exclude list.")

def get_report_exclude():
    usrs = []
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        excludes = con.execute("SELECT * FROM settings WHERE parametr = 'report_exclude'").fetchone()

        if excludes and 'value' in excludes:
            # Получаем строку и разделяем её на массив
            users = excludes['value'].strip()
            if users:  # Проверяем, что строка не пустая
                usrs = users.split(',')  # Делаем список
                usrs = [user.strip() for user in usrs if user.strip()]  # Убираем лишние пробелы и пустые элементы

    return usrs

def add_report_exclude(user_id):
    user_id_str = str(user_id)
    admins = get_report_exclude()

    # Убедимся, что user_id уникален
    if user_id_str not in admins:
        admins.append(user_id_str)  # Добавляем нового администратора
        with sqlite3.connect(path_db) as con:
            con.execute(
                "INSERT INTO settings (parametr, description, value) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(parametr) DO UPDATE SET "
                "description = excluded.description, value = excluded.value",
                ('report_exclude', 'Исключены из рассылки', ','.join(admins))  # Сохраняем строку, разделенную запятыми
            )
        con.commit()
    else:
        print(f"User with user_id {user_id_str} already in exclude list.")

################################################################################################
##################################           Юзеры            ##################################
################################################################################################

# Регистрация пользователя в БД
# Получение пользователя из БД
def get_user(**kwargs):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        where = " AND ".join(f"{k} = ?" for k in kwargs)
        return con.execute(f"SELECT * FROM users WHERE {where}", list(kwargs.values())).fetchone()


def get_user_by_tg_id(tg_id):
    """Look up a user by Telegram ID via auth_providers."""
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT u.* FROM users u "
            "JOIN auth_providers ap ON ap.user_id = u.id "
            "WHERE ap.provider = 'telegram' AND ap.identifier = ?",
            (str(tg_id),),
        ).fetchone()


# Редактирование пользователя
def update_user(id, **kwargs):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        queryy = f"UPDATE users SET"
        queryy, params = query(queryy, kwargs)
        params.append(id)
        con.execute(queryy + "WHERE id = ?", params)
        con.commit()


# Удаление пользователя из БД
def delete_user(id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("DELETE FROM users WHERE id = ?", (id,))
        con.commit()


# Получение всех пользователей из БД
def all_users():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM users").fetchall()

def get_all_vip():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM users WHERE is_vip IS NOT NULL").fetchall()


#############################################################################################
###############################            Заказы             ###############################
#############################################################################################

# Добавление покупки
def add_order(user_id, price, position_name, status, links, contacts, user_name):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("INSERT INTO orders "
                    "(user_id, price, position_name, status, links, date, contacts, user_name) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [user_id, price, position_name, status, links, get_date(), contacts, user_name])
        con.commit()

# Получение покупки
def get_order(id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM orders WHERE increment = ?", (id,)).fetchone()

# Удаление заказа
def delete_order(id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("DELETE FROM orders WHERE increment = ?", (id,))
        con.commit()

# Получение последнего заказа данного пользователя
def get_users_last_order(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY increment DESC LIMIT 1", (user_id,)).fetchone()

# Получение всех заказов
def edit_order(status, order):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = "UPDATE orders SET status = ? WHERE increment = ?"
        con.execute(sql, (status,order))
        con.commit()

# Получение всех заказов
def all_orders():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = "SELECT * FROM orders"
        return con.execute(sql).fetchall()

# Получение заказов пакетами для экономии памяти
def get_orders_batch(limit=1000, offset=0):
    """Получает заказы порциями из БД"""
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = "SELECT * FROM orders LIMIT ? OFFSET ?"
        return con.execute(sql, (limit, offset)).fetchall()


def get_orders_with_links_batch(limit=1000, offset=0):
    """JOIN orders + order_links, по строке на ссылку. Спек §7.1.

    user_name берётся из users (live), а не из snapshot в orders — последний
    в новом unpaid→paid flow (services.orders.create_unpaid) пишется NULL.
    COALESCE с o.user_name — фоллбэк для случая, когда users-строки нет
    (удалённый юзер), сохраняет исторический snapshot.
    """
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = (
            "SELECT "
            "  o.increment AS order_id, o.user_id, o.position_name, "
            "  o.status AS order_status, o.date AS order_date, "
            "  o.contacts, o.phone, o.start_date, "
            "  COALESCE(u.user_name, o.user_name) AS user_name, "
            "  ol.url, ol.status AS link_status, "
            "  ol.delivery_mode, ol.deadline_at "
            "FROM orders o "
            "JOIN order_links ol ON ol.order_id = o.increment "
            "LEFT JOIN users u ON u.id = o.user_id "
            "ORDER BY o.increment DESC, ol.id "
            "LIMIT ? OFFSET ?"
        )
        return con.execute(sql, (limit, offset)).fetchall()


def get_pending_manual_links_due_today():
    """Все pending+manual ссылки заказов готовых к старту (Спек §7.2).

    Cutoff 04:00 МСК — та же бизнес-сутка биза, что использует
    services.pf_executor_api._effective_start_msk при выставлении
    `start_date` на создании заказа. Ссылка появляется в выгрузке как
    только её бизнес-сутка началась (после 04:00 МСК соответствующей
    календарной даты), и остаётся видна до её закрытия.

    user_name — live из users с фоллбэком на snapshot, см. комментарий в
    get_orders_with_links_batch.
    """
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = (
            "SELECT "
            "  o.increment AS order_id, o.user_id, o.position_name, "
            "  o.date AS order_date, o.contacts, o.phone, o.start_date, "
            "  COALESCE(u.user_name, o.user_name) AS user_name, "
            "  ol.url, ol.status AS link_status, "
            "  ol.delivery_mode, ol.deadline_at "
            "FROM order_links ol "
            "JOIN orders o ON o.increment = ol.order_id "
            "LEFT JOIN users u ON u.id = o.user_id "
            "WHERE ol.status='pending' AND ol.delivery_mode='manual' "
            # Business day cutoff 04:00 МСК:
            #   `+3 hours` — UTC → MSK
            #   `-4 hours` — отступаем к началу бизнес-суток (04:00 МСК)
            #   `-1 seconds` — граница 04:00:00 МСК принадлежит ПРЕДЫДУЩЕЙ
            #     сутке (правило «до 04:00 включительно → today batch» в
            #     services.pf_executor_api._effective_start_msk).
            "AND (o.start_date IS NULL OR date(o.start_date) <= "
            "     date('now', '+3 hours', '-4 hours', '-1 seconds')) "
            "ORDER BY COALESCE(o.start_date, '9999-12-31') ASC, o.date ASC"
        )
        return con.execute(sql).fetchall()

# Получение всех заказов в зависимости от статуса
def all_orders_by_status(status):
    array = []
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        data = con.execute("SELECT * FROM orders WHERE status = ?", (status,)).fetchall()
        for order in data:
            array.append(order)
        return array


# Все заказы пользователя
def user_orders_all(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM orders WHERE user_id = ?", (user_id,)).fetchall()


#############################################################################################
###############################          SEO BOOST            ###############################
#############################################################################################

# Добавление покупки
def add_order_seo(user_id, price, months, status, link):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("INSERT INTO seo "
                    "(user_id, price, months, status, link, date) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [user_id, price, months, status, link, get_date()])
        con.commit()

# Получение последнего заказа данного пользователя
def get_user_last_order_seo(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM seo WHERE user_id = ? ORDER BY increment DESC LIMIT 1", (user_id,)).fetchone()

###############################################################################################
#############################            Пополнения            ################################
###############################################################################################

# Добавление пополнения
def get_user_all_refills(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT * FROM refills WHERE user_id = ? AND status = 'succeeded'",
            (user_id,),
        ).fetchall()


def all_refills():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT * FROM refills WHERE status = 'succeeded'"
        ).fetchall()

###############################################################################################
#############################            Промокоды             ################################
###############################################################################################

# Добавление промокода
def add_promocode(code, price):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("INSERT INTO promocodes("
                    "code, price)"
                    "VALUES (?, ?)",
                    [code, price])
        con.commit()
    return True


# Получение всех промокодов
def all_promocodes():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = "SELECT * FROM promocodes"
        return con.execute(sql).fetchall()

def get_promocode(**kwargs):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        where = " AND ".join(f"{k} = ?" for k in kwargs)
        return con.execute(f"SELECT * FROM promocodes WHERE {where}", list(kwargs.values())).fetchone()

def update_promocode(increment, **kwargs):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        queryy = f"UPDATE promocodes SET"
        queryy, params = query(queryy, kwargs)
        params.append(increment)
        con.execute(queryy + "WHERE increment = ?", params)
        con.commit()

def search(code):
    with sqlite3.connect(path_db) as con:
        cursor = con.cursor()
        cursor.execute("SELECT increment, isactivated, price FROM promocodes WHERE code = ?", (code,))
        result = cursor.fetchone()
        return result

def del_promo(code):
    with sqlite3.connect(path_db) as con:
        cursor = con.cursor()
        cursor.execute("DELETE FROM promocodes WHERE code = ?", (code,))
        con.commit()

def activate_promocode(code, **kwargs):
    with sqlite3.connect(path_db) as con:
        con.execute("UPDATE promocodes SET isactivated = 1 WHERE code = ?", (code,))
        con.commit()

def get_balancik(id):
    with sqlite3.connect(path_db) as con:
        cursor = con.cursor()
        cursor.execute("SELECT balance FROM users WHERE id = ?", (id,))
        result = cursor.fetchone()
        if result:
            return result[0]  # Возвращаем баланс пользователя
        else:
            return None  # Если пользователя с таким ID не существует

def add_balance(new_balance, id):
    with sqlite3.connect(path_db) as con:
        cursor = con.cursor()
        cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, id))
        con.commit()
#######################################################################################
############################            Создание            ###########################
############################           Базы Данных          ###########################
#######################################################################################

def get_schema_statements() -> list[tuple[str, str, int]]:
    """Возвращает список (table_name, create_sql, expected_column_count).

    Используется create_db() для бутстрапа продовой БД и tests.conftest для tmp-БД.
    """
    return [
        (
            "users",
            "CREATE TABLE users("
            "id INTEGER PRIMARY KEY,"
            "user_name TEXT,"
            "first_name TEXT,"
            "balance INTEGER DEFAULT 0,"
            "reg_date TIMESTAMP,"
            "ref_user_name TEXT,"
            "ref_id INTEGER,"
            "is_vip BOOLEN,"
            "magic TEXT,"
            "referals TEXT,"
            "ref_link_id INTEGER)",
            11,
        ),
        (
            "refills",
            "CREATE TABLE refills("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "amount INTEGER,"
            "date TIMESTAMP,"
            "payment_id TEXT,"
            "source_type TEXT NOT NULL DEFAULT 'telegram',"
            "source_app_id INTEGER,"
            "status TEXT NOT NULL DEFAULT 'succeeded',"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            8,
        ),
        (
            "orders",
            "CREATE TABLE orders("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "price INTEGER,"
            "position_name TEXT,"
            "status TEXT,"
            "links TEXT,"
            "date TIMESTAMP,"
            "contacts BOOLEN DEFAULT False,"
            "user_name TEXT,"
            "payment_method TEXT,"
            "payment_expires_at TIMESTAMP,"
            "payment_id TEXT,"
            "phone TEXT,"
            "start_date TEXT,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            9,
        ),
        (
            "promocodes",
            "CREATE TABLE promocodes("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            "code TEXT NOT NULL,"
            "price INTEGER,"
            "isactivated BOOL DEFAULT FALSE,"
            "prom_users TEXT)",
            5,
        ),
        (
            "settings",
            "CREATE TABLE IF NOT EXISTS settings("
            "parametr TEXT PRIMARY KEY,"
            "description TEXT,"
            "value TEXT)",
            3,
        ),
        (
            "strings",
            "CREATE TABLE IF NOT EXISTS strings("
            "parametr TEXT PRIMARY KEY,"
            "description TEXT,"
            "value TEXT)",
            3,
        ),
        (
            "auth_providers",
            "CREATE TABLE IF NOT EXISTS auth_providers("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "provider TEXT NOT NULL,"
            "identifier TEXT NOT NULL,"
            "credential_hash TEXT,"
            "created_at TIMESTAMP NOT NULL,"
            "last_used_at TIMESTAMP,"
            "verified INTEGER NOT NULL DEFAULT 1,"
            "UNIQUE(provider, identifier),"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            8,
        ),
        (
            "applications",
            "CREATE TABLE IF NOT EXISTS applications("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "owner_user_id INTEGER NOT NULL,"
            "name TEXT NOT NULL,"
            "api_key_hash TEXT NOT NULL UNIQUE,"
            "api_key_prefix TEXT NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "revoked_at TIMESTAMP,"
            "FOREIGN KEY (owner_user_id) REFERENCES users(id))",
            7,
        ),
        (
            "otp_codes",
            "CREATE TABLE IF NOT EXISTS otp_codes("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "purpose TEXT NOT NULL,"
            "destination TEXT NOT NULL,"
            "channel TEXT NOT NULL DEFAULT 'telegram',"
            "code_hash TEXT NOT NULL,"
            "user_id_to_link INTEGER,"
            "created_at TIMESTAMP NOT NULL,"
            "expires_at TIMESTAMP NOT NULL,"
            "attempts INTEGER NOT NULL DEFAULT 0,"
            "consumed_at TIMESTAMP,"
            "FOREIGN KEY (user_id_to_link) REFERENCES users(id))",
            9,
        ),
        (
            "support_messages",
            "CREATE TABLE support_messages("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "direction TEXT NOT NULL,"
            "text TEXT NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "tg_message_id INTEGER,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            6,
        ),
        (
            "pending_email_registrations",
            "CREATE TABLE IF NOT EXISTS pending_email_registrations("
            "email TEXT PRIMARY KEY,"
            "password_hash TEXT NOT NULL,"
            "first_name TEXT,"
            "code TEXT NOT NULL,"
            "expires_at TIMESTAMP NOT NULL,"
            "created_at TIMESTAMP NOT NULL)",
            6,
        ),
        (
            "pending_email_links",
            "CREATE TABLE IF NOT EXISTS pending_email_links("
            "email TEXT PRIMARY KEY,"
            "user_id INTEGER NOT NULL,"
            "password_hash TEXT NOT NULL,"
            "code TEXT NOT NULL,"
            "expires_at TIMESTAMP NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            6,
        ),
        (
            "funnel_events",
            "CREATE TABLE IF NOT EXISTS funnel_events("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "service TEXT NOT NULL,"
            "step TEXT NOT NULL,"
            "ts TIMESTAMP NOT NULL,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            5,
        ),
        # guest_orders таблица намеренно удалена из схемы — миграция в apply_phase2_migrations
        # дропает её для legacy-БД, новые БД её не создают (логика объединена с orders).
        (
            "notifications",
            "CREATE TABLE IF NOT EXISTS notifications("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "kind TEXT NOT NULL,"
            "order_id INTEGER,"
            "new_status TEXT,"
            "text TEXT NOT NULL,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "read_at TIMESTAMP)",
            8,
        ),
        (
            "order_links",
            "CREATE TABLE IF NOT EXISTS order_links("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "order_id INTEGER NOT NULL,"
            "url TEXT NOT NULL,"
            "status TEXT NOT NULL DEFAULT 'pending',"
            "delivery_mode TEXT,"
            "deadline_at TIMESTAMP,"
            "started_at TIMESTAMP,"
            "done_at TIMESTAMP,"
            "failed_at TIMESTAMP,"
            "failure_reason TEXT,"
            "external_id TEXT,"
            "created_at TIMESTAMP NOT NULL,"
            "dispatch_attempts INTEGER NOT NULL DEFAULT 0,"
            "FOREIGN KEY (order_id) REFERENCES orders(increment))",
            13,
        ),
        (
            "avito_ad_phrase_cache",
            "CREATE TABLE IF NOT EXISTS avito_ad_phrase_cache("
            "ad_id TEXT PRIMARY KEY,"
            "search_link TEXT NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "cached_at TIMESTAMP NOT NULL)",
            4,  # column count
        ),
        (
            "referral_links",
            "CREATE TABLE IF NOT EXISTS referral_links("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "slug TEXT NOT NULL COLLATE NOCASE,"
            "clicks INTEGER NOT NULL DEFAULT 0,"
            "custom_percent INTEGER,"
            "created_at TIMESTAMP NOT NULL,"
            "archived_at TIMESTAMP,"
            "UNIQUE (user_id, slug),"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            7,
        ),
        (
            "referral_bonuses",
            "CREATE TABLE IF NOT EXISTS referral_bonuses("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "referrer_id INTEGER NOT NULL,"
            "referred_user_id INTEGER NOT NULL,"
            "refill_id INTEGER,"
            "link_id INTEGER,"
            "amount INTEGER NOT NULL,"
            "percent INTEGER NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "FOREIGN KEY (referrer_id) REFERENCES users(id),"
            "FOREIGN KEY (referred_user_id) REFERENCES users(id),"
            "FOREIGN KEY (refill_id) REFERENCES refills(increment),"
            "FOREIGN KEY (link_id) REFERENCES referral_links(id))",
            8,
        ),
    ]


def get_index_statements() -> list[str]:
    """Index DDL applied after tables. Idempotent."""
    return [
        "CREATE INDEX IF NOT EXISTS idx_funnel_service_ts "
        "ON funnel_events(service, ts)",
        "CREATE INDEX IF NOT EXISTS idx_funnel_service_step_user "
        "ON funnel_events(service, step, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_unread "
        "ON notifications(user_id, read_at)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_created "
        "ON notifications(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_order_links_order "
        "ON order_links(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_order_links_deadline "
        "ON order_links(status, deadline_at) WHERE status = 'in_work'",
        "CREATE INDEX IF NOT EXISTS idx_apc_cached_at "
        "ON avito_ad_phrase_cache(cached_at)",
        # refills.status/payment_id indexes intentionally NOT here — they reference
        # a column added by apply_phase2_migrations() which runs AFTER create_db(),
        # so a fresh-deploy on an existing DB would fail with "no such column: status".
        # The indexes are created inside apply_phase2_migrations() after ALTER ADD COLUMN.
    ]


def apply_phase2_migrations():
    """Идемпотентно добавляет колонки — запускается при каждом старте."""
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        existing_refills = {row['name'] for row in con.execute("PRAGMA table_info(refills)").fetchall()}
        if 'source_type' not in existing_refills:
            con.execute("ALTER TABLE refills ADD COLUMN source_type TEXT NOT NULL DEFAULT 'telegram'")
            print("refills.source_type added")
        if 'source_app_id' not in existing_refills:
            con.execute("ALTER TABLE refills ADD COLUMN source_app_id INTEGER")
            print("refills.source_app_id added")
        if 'payment_id' not in existing_refills:
            con.execute("ALTER TABLE refills ADD COLUMN payment_id TEXT")
            print("refills.payment_id added")
        # === refills.status (state machine: pending|succeeded|canceled|expired) ===
        if 'status' not in existing_refills:
            con.execute(
                "ALTER TABLE refills ADD COLUMN status TEXT NOT NULL DEFAULT 'succeeded'"
            )
            print("refills.status added (existing rows defaulted to status='succeeded')")
        # Индексы создаём отдельно от ALTER — IF NOT EXISTS делает идемпотентным.
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_refills_status_date "
            "ON refills (status, date)"
        )
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_refills_payment_id "
            "ON refills (payment_id) WHERE payment_id IS NOT NULL"
        )
        existing_orders = {row['name'] for row in con.execute("PRAGMA table_info(orders)").fetchall()}
        if 'user_name' not in existing_orders:
            con.execute("ALTER TABLE orders ADD COLUMN user_name TEXT")
            print("orders.user_name added")

        # === unpaid order flow ===
        if 'payment_method' not in existing_orders:
            con.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT")
            print("orders.payment_method added")
        if 'payment_expires_at' not in existing_orders:
            con.execute("ALTER TABLE orders ADD COLUMN payment_expires_at TIMESTAMP")
            print("orders.payment_expires_at added")
        if 'payment_id' not in existing_orders:
            con.execute("ALTER TABLE orders ADD COLUMN payment_id TEXT")
            print("orders.payment_id added")
        if 'phone' not in existing_orders:
            con.execute("ALTER TABLE orders ADD COLUMN phone TEXT")
            print("orders.phone added")
        if 'start_date' not in existing_orders:
            con.execute("ALTER TABLE orders ADD COLUMN start_date TEXT")
            print("orders.start_date added")

        # === order_links.dispatch_attempts (per-link auto retry counter) ===
        ol_exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='order_links'"
        ).fetchone()
        if ol_exists:
            existing_ol = {row['name'] for row in con.execute("PRAGMA table_info(order_links)").fetchall()}
            if 'dispatch_attempts' not in existing_ol:
                con.execute("ALTER TABLE order_links ADD COLUMN dispatch_attempts INTEGER NOT NULL DEFAULT 0")
                print("order_links.dispatch_attempts added (existing rows defaulted to 0)")

        # === auth_providers.verified ===
        existing_ap = {row['name'] for row in con.execute("PRAGMA table_info(auth_providers)").fetchall()}
        if 'verified' not in existing_ap:
            con.execute("ALTER TABLE auth_providers ADD COLUMN verified INTEGER NOT NULL DEFAULT 1")
            print("auth_providers.verified added (existing rows defaulted to verified=1)")

        # === otp_codes generalization ===
        existing_otp = {row['name'] for row in con.execute("PRAGMA table_info(otp_codes)").fetchall()}
        if 'destination' not in existing_otp:
            if 'telegram_id' in existing_otp:
                con.execute("ALTER TABLE otp_codes RENAME COLUMN telegram_id TO destination")
                print("otp_codes.telegram_id -> destination renamed")
        if 'channel' not in existing_otp:
            con.execute("ALTER TABLE otp_codes ADD COLUMN channel TEXT NOT NULL DEFAULT 'telegram'")
            print("otp_codes.channel added (default='telegram')")

        # === order status renaming (Posted/Completed/Cancelled/Pending -> new) ===
        status_map = {
            "Posted": "paid",
            "Completed": "done",
            "Cancelled": "cancelled",
            "Pending": "payment_failed",
        }
        for old, new in status_map.items():
            cur = con.execute("UPDATE orders SET status = ? WHERE status = ?", (new, old))
            if cur.rowcount:
                print(f"orders.status: {old} -> {new} ({cur.rowcount} rows)")

        # === migrate guest_orders -> orders, then drop ===
        tables = {row['name'] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if 'guest_orders' in tables:
            guest_rows = con.execute("SELECT * FROM guest_orders").fetchall()
            for row in guest_rows:
                phone = row["phone"]
                ap = con.execute(
                    "SELECT user_id FROM auth_providers "
                    "WHERE provider='phone' AND identifier=?",
                    (phone,),
                ).fetchone()
                if ap:
                    user_id = ap["user_id"]
                else:
                    cur = con.execute(
                        "INSERT INTO users(balance, user_name, first_name) "
                        "VALUES (0, NULL, NULL)"
                    )
                    user_id = cur.lastrowid
                    verified = 1 if row["status"] == "paid" else 0
                    con.execute(
                        "INSERT INTO auth_providers(user_id, provider, identifier, "
                        "created_at, verified) VALUES (?, 'phone', ?, ?, ?)",
                        (user_id, phone, row["created_at"], verified),
                    )
                new_status = {
                    "paid": "paid",
                    "pending_payment": "payment_failed",
                    "failed": "payment_failed",
                }.get(row["status"], "payment_failed")
                con.execute(
                    "INSERT INTO orders(user_id, price, position_name, status, "
                    "links, contacts, user_name, payment_method, payment_id, phone) "
                    "VALUES (?, ?, ?, ?, ?, ?, NULL, 'yookassa', ?, ?)",
                    (
                        user_id, row["price"],
                        f"{row['days']}/{row['fix_count']}",
                        new_status, row["links"], row["contacts"],
                        row["payment_id"], phone,
                    ),
                )
            con.execute("DROP TABLE guest_orders")
            print(f"guest_orders migrated ({len(guest_rows)} rows) and dropped")

        # === referral program (multi-link) ===
        existing_users = {row['name'] for row in con.execute("PRAGMA table_info(users)").fetchall()}
        if 'ref_link_id' not in existing_users:
            con.execute("ALTER TABLE users ADD COLUMN ref_link_id INTEGER")
            print("users.ref_link_id added")
        con.execute(
            "CREATE TABLE IF NOT EXISTS referral_links("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "slug TEXT NOT NULL COLLATE NOCASE,"
            "clicks INTEGER NOT NULL DEFAULT 0,"
            "custom_percent INTEGER,"
            "created_at TIMESTAMP NOT NULL,"
            "archived_at TIMESTAMP,"
            "UNIQUE (user_id, slug),"
            "FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS referral_bonuses("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "referrer_id INTEGER NOT NULL,"
            "referred_user_id INTEGER NOT NULL,"
            "refill_id INTEGER,"
            "link_id INTEGER,"
            "amount INTEGER NOT NULL,"
            "percent INTEGER NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "FOREIGN KEY (referrer_id) REFERENCES users(id),"
            "FOREIGN KEY (referred_user_id) REFERENCES users(id),"
            "FOREIGN KEY (refill_id) REFERENCES refills(increment),"
            "FOREIGN KEY (link_id) REFERENCES referral_links(id))"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_referral_links_user "
            "ON referral_links(user_id)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_referral_bonuses_referrer "
            "ON referral_bonuses(referrer_id, id DESC)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_referral_bonuses_link "
            "ON referral_bonuses(link_id)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_ref_link_id "
            "ON users(ref_link_id)"
        )
        # Сидим строку настройки: экран настроек в боте листает ТОЛЬКО строки
        # из БД (get_all_settings), дефолт в _SETTING_DEFAULTS там не виден.
        # ON CONFLICT DO NOTHING — правки админа не затираются при рестартах.
        # settings таблица есть во всех реальных БД; guard нужен только для
        # тестовых фикстур с минимальной легаси-схемой (tests/unit/test_refills_migration.py).
        settings_exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'"
        ).fetchone()
        if settings_exists:
            con.execute(
                "INSERT INTO settings(parametr, description, value) "
                "VALUES ('ref_percent', "
                "'Партнерка: % с каждого пополнения реферала', '10') "
                "ON CONFLICT(parametr) DO NOTHING"
            )

        con.commit()


def create_db():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        for idx, (table, ddl, cols) in enumerate(get_schema_statements(), start=1):
            existing = con.execute(f"PRAGMA table_info({table})").fetchall()
            if len(existing) == 0:
                con.execute(ddl)
                print(f"database was not found ({table} | {idx}/{len(get_schema_statements())}), creating...")
            else:
                print(f"database was found ({table} | {idx}/{len(get_schema_statements())})")
        for ddl in get_index_statements():
            con.execute(ddl)
        con.commit()
    apply_phase2_migrations()

def get_nick(param):
    value = get_setting(param)
    if value:
        if not value.startswith('@'):
            value = '@' + value
        return value
    else:
        return None


def user_orders_paginated(user_id, limit=20, offset=0):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY increment DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()


def user_orders_count(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        result = con.execute(
            "SELECT COUNT(*) as cnt FROM orders WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return (result["cnt"] if result else 0)


def support_add_message(user_id, direction, text, tg_message_id=None):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        cur = con.execute(
            "INSERT INTO support_messages(user_id, direction, text, created_at, tg_message_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, direction, text, get_date(), tg_message_id),
        )
        con.commit()
        return cur.lastrowid


def support_get_messages(user_id, limit=100, since_id=0):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT * FROM support_messages WHERE user_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
            (user_id, since_id, limit),
        ).fetchall()


def support_find_by_tg_message_id(tg_message_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT * FROM support_messages WHERE tg_message_id = ?",
            (tg_message_id,),
        ).fetchone()
