# - *- coding: utf- 8 - *-
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
def query_args(sql, parameters: dict):
    sql = f"{sql} WHERE "

    sql += " AND ".join([
        f"{item} = ?" for item in parameters
    ])

    return sql, list(parameters.values())


def str2dict(str_value):
    result_dict = ast.literal_eval(str_value)

    return result_dict

def dict2str(input_dict):
    # Преобразуем словарь в строку JSON
    json_string = json.dumps(input_dict)
    return json_string
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
    "btn_channel": "🔗 Наш телеграм канал",
    "btn_main_menu": "🧊 Главное меню",
    "btn_yes": "✅ Да",
    "btn_no": "❎ Нет",
    "btn_all_completed": "✅ Выполненные",
    "btn_all_posted": "✍️ Размещённые",
    "btn_avito_cases": "🔗 Кейсы Авито",
    "btn_seo_howto": "❓ Как работает",
    "btn_seo_why": "💡 Зачем нужно",
    "btn_seo_result": "📊 Результат",
    "btn_seo_order": "🚀 Заказать",
    "btn_rules": "🔰 Правила пользования ботом",
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
    "str_error": "⚠️ Произошла ошибка. Попробуйте позже.",
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
    "str_debet_money": "⏳ Ожидаем оплату <b>{}</b> ₽...",
    "str_pay_error": "❌ Ошибка оплаты. Обратитесь в поддержку: {}",
    "str_payment_error": "❌ Не удалось создать счёт. Обратитесь в поддержку: {}",
    "str_usr_pay_success": "✅ Оплата <b>{}</b> ₽ прошла. Баланс: <b>{}</b> ₽.",
    "str_adm_pay_success": "💰 Пополнение <b>{}</b> ₽ от {}. Баланс: <b>{}</b> ₽.",
    "str_ref_balance_refil": "🎁 Ваш реферал пополнил баланс! Вам начислено <b>{}</b> ₽. Баланс: <b>{}</b> ₽.",
    "str_tasks_text": "📋 Стоимость накрутки ПФ: <b>{}</b> ₽/шт. в день.",
    "str_how_to_start_text": (
        "📖 <b>Как начать работу</b>\n\n"
        "1. Пополните баланс\n"
        "2. Выберите «Накрутка ПФ Авито»\n"
        "3. Укажите период и количество\n"
        "4. Вставьте ссылки на объявления\n"
        "5. Подтвердите заказ"
    ),
    "str_rules_text": "📜 <b>Правила пользования ботом</b>\n\nПравила не заданы. Обратитесь к администратору.",
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
    "str_pf_contacts": "📞 Нужна обратная связь по заказу?",
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
    "str_order_confirm": "✅ Заказ #{} размещён! Менеджер свяжется с вами.",
    "str_review_start": "⭐ Выберите площадку для отзывов:",
    "str_reviews_vk": "📝 Отзывы ВКонтакте:",
    "str_reviews_yandex": "📝 Отзывы Яндекс:",
    "str_reviews_avito": "📝 Отзывы Авито:",
    "str_reviews_2gis": "📝 Отзывы 2ГИС:",
    "str_reviews_flamp": "📝 Отзывы Фламп:",
    "str_reviews_add_link": "🔗 Вставьте ссылку на вашу страницу:",
    "str_review_bad_link": "❌ Ссылка не соответствует выбранной площадке.",
    "str_review_order_confirm": "✅ {} отзывов для {} по {} ₽/шт. Итого: {} ₽. Подтвердить?",
    "str_review_confirm": "✅ Заказ #{} принят! Свяжитесь с менеджером: {}",
    "str_new_review_admin_report": "⭐ Новый заказ отзывов #{}\n💰 {} ₽\n👤 {}\n📍 {}\n📊 {}\n📅 {}\n🔗 {}",
    "str_delete_review": "🗑 Удаление негативного отзыва Авито.\nСтоимость: <b>{}</b> ₽.\nВставьте ссылку на отзыв:",
    "str_seo_main": "🔍 <b>SEO-буст</b>\n\nПовышение позиций в поиске Авито.",
    "str_seo_howto": "❓ SEO-буст — это продвижение объявлений в топ поиска Авито.",
    "str_seo_why": "💡 SEO-буст увеличивает видимость объявлений и приток клиентов.",
    "str_seo_result": "📊 Результат заметен в течение 7-14 дней.",
    "str_seo_order_start": "🚀 SEO-буст: <b>{}</b> ₽/мес. Выберите срок:",
    "str_seo_enter_link": "🔗 Введите ссылку на объявление (срок: {} {}):",
    "str_seo_order": "📋 SEO-буст {} {} для:\n{}\nСумма: <b>{}</b> ₽. Подтвердить?",
    "str_seo_order_confirm": "✅ SEO-заказ #{} принят! Менеджер: {}",
    "str_seo_admin_msg": "🔍 SEO-заказ #{}\n📅 {} мес.\n💰 {} ₽\n👤 {}\n📊 {}\n📅 {}\n🔗 {}",
}

# Defaults for the `settings` table — used when row is missing or value is empty.
_SETTING_DEFAULTS: dict[str, str] = {
    "payment_work": "true",
    "min_amount": "100",
    "manager_nick": "support",
    "nick_manager_reviews": "support",
    "channel_link": "https://t.me/pf_avito_top",
    "egg_sticker": "",
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
    req = "UPDATE strings SET value = ? WHERE parametr = ?"
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute(req, [value, param])

#Редактируем настройку из базы
def edit_setting(param, value):
    req = "UPDATE settings SET value = ? WHERE parametr = ?"
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute(req, [value, param])

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
    prices_str = dict2str(prices)
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute(req, [value, prices_str])

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
def register_user(id, user_name, first_name):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        """
        con.execute("INSERT OR IGNORE INTO users("
                    "id, user_name, first_name, balance, reg_date, ref_user_name, ref_id, is_vip, magic, referals) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)", [id, user_name, first_name, 0, get_date(), None, None, None, None, None])
        """
        if not user_name:
            user_name = None
        first_name = first_name.replace("'", '`').replace("<", '«').replace(">", '»')
        try:
            con.execute("INSERT INTO users("
                    "id, user_name, first_name, balance, reg_date, ref_user_name, ref_id, is_vip, magic, referals) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)", [id, user_name, first_name, 0, get_date(), None, None, None, None, None])
            con.commit()
            print(f"User {Fore.GREEN}@{user_name} ({id}){Fore.RESET} has been successfully registered!")
        except Exception as e:
            print(f"{Fore.RED}Error registration user:{Fore.RESET}\n{e}")

# Получение пользователя из БД
def get_user(**kwargs):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        queryy = "SELECT * FROM users"
        queryy, params = query_args(queryy, kwargs)
        return con.execute(queryy, params).fetchone()


def get_user_by_tg_id(tg_id):
    """Look up a user by Telegram ID.

    Supports both legacy users (users.id == tg_id) and users created via the
    identity service (users.id is auto-increment; linked via auth_providers).
    """
    u = get_user(id=tg_id)
    if u:
        return u
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

# Получение общего количества заказов
def get_orders_count():
    """Возвращает общее количество заказов"""
    with sqlite3.connect(path_db) as con:
        sql = "SELECT COUNT(*) as count FROM orders"
        result = con.execute(sql).fetchone()
        return result[0] if result else 0

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
###############################            Отзывы             ###############################
#############################################################################################

# Добавление покупки
def add_order_reviews(user_id, price, service, link, status):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("INSERT INTO reviews "
                    "(user_id, price, service, link, status, date) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [user_id, price, service, link, status, get_date()])
        con.commit()

# Получение последнего заказа данного пользователя
def get_users_last_order_reviews(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM reviews WHERE user_id = ? ORDER BY increment DESC LIMIT 1", (user_id,)).fetchone()

# Получение заказа на отзывы
def get_order_reviews(id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM reviews WHERE increment = ?", (id,)).fetchone()

# Удаление заказа
def delete_order_reviews(id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("DELETE FROM reviews WHERE increment = ?", (id,))
        con.commit()

# Редактирование заказа
def edit_order_reviews(status, order):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = "UPDATE reviews SET status = ? WHERE increment = ?"
        con.execute(sql, (status,order))
        con.commit()

# Получение всех заказов
def all_orders_reviews():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = "SELECT * FROM reviews"
        return con.execute(sql).fetchall()


# Все заказы пользователя
def user_orders_all_reviews(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM reviews WHERE user_id = ?", (user_id,)).fetchall()

###############################################################################################
###############################    Удаление негативного отзыва   ##############################
###############################################################################################

# Добавление покупки
def add_order_delreview(user_id, price, service, link, status):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("INSERT INTO delreviews "
                    "(user_id, price, service, link, status, date) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [user_id, price, service, link, status, get_date()])
        con.commit()

# Получение последнего заказа данного пользователя
def get_users_last_order_delreviews(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM delreviews WHERE user_id = ? ORDER BY increment DESC LIMIT 1", (user_id,)).fetchone()

# Получение заказа на отзывы
def get_order_delreviews(id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM delreviews WHERE increment = ?", (id,)).fetchone()

# Удаление заказа
def delete_order_delreviews(id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("DELETE FROM delreviews WHERE increment = ?", (id,))
        con.commit()

# Редактирование заказа
def edit_order_delreviews(status, order):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = "UPDATE delreviews SET status = ? WHERE increment = ?"
        con.execute(sql, (status,order))
        con.commit()

# Получение всех заказов
def all_orders_delreviews():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = "SELECT * FROM delreviews"
        return con.execute(sql).fetchall()


# Все заказы пользователя
def user_orders_all_delreviews(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM delreviews WHERE user_id = ?", (user_id,)).fetchall()

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
def add_refill(amount, user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("INSERT INTO refills("
                    "amount, date, user_id) "
                    "VALUES (?,?,?)",
                    [amount, get_date(), user_id])
        con.commit()


# Получение пополнения
def get_refill(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM refills WHERE user_id = ?", (user_id,)).fetchone()

def get_user_all_refills(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute("SELECT * FROM refills WHERE user_id = ?", (user_id,)).fetchall()

# Получение всех пополнений
def all_refills():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = "SELECT * FROM refills"
        return con.execute(sql).fetchall()

# Получение общей суммы пополнений
def all_refills_sum():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = "SELECT * FROM refills"
        refills = con.execute(sql).fetchall()
        summ = 0
        for refill in refills:
            summ += refill['amount']
        return summ


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
        queryy = "SELECT * FROM promocodes"
        queryy, params = query_args(queryy, kwargs)
        return con.execute(queryy, params).fetchone()

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
            "referals TEXT)",
            10,
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
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            7,
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
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            8,
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
            "reviews",
            "CREATE TABLE reviews ("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "price INTEGER, "
            "service TEXT, "
            "link TEXT, "
            "status TEXT, "
            "date TIMESTAMP, "
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            7,
        ),
        (
            "delreviews",
            "CREATE TABLE delreviews ("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "price INTEGER, "
            "service TEXT, "
            "link TEXT, "
            "status TEXT, "
            "date TIMESTAMP, "
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            7,
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
            "telegram_id INTEGER NOT NULL,"
            "code_hash TEXT NOT NULL,"
            "user_id_to_link INTEGER,"
            "created_at TIMESTAMP NOT NULL,"
            "expires_at TIMESTAMP NOT NULL,"
            "attempts INTEGER NOT NULL DEFAULT 0,"
            "consumed_at TIMESTAMP,"
            "FOREIGN KEY (user_id_to_link) REFERENCES users(id))",
            9,
        ),
    ]


def apply_phase2_migrations():
    """Идемпотентно добавляет колонки source-tracking в refills и link в reviews."""
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
        existing_reviews = {row['name'] for row in con.execute("PRAGMA table_info(reviews)").fetchall()}
        if 'link' not in existing_reviews:
            con.execute("ALTER TABLE reviews ADD COLUMN link TEXT")
            print("reviews.link added")
        con.commit()


def create_db():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        for idx, (table, ddl, cols) in enumerate(get_schema_statements(), start=1):
            existing = con.execute(f"PRAGMA table_info({table})").fetchall()
            if len(existing) == cols:
                print(f"database was found ({table} | {idx}/{len(get_schema_statements())})")
            else:
                con.execute(ddl)
                print(f"database was not found ({table} | {idx}/{len(get_schema_statements())}), creating...")
        con.commit()
    apply_phase2_migrations()

