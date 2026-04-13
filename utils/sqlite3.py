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


#Получаем строку из базы или из конфига
def get_string(param):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        str_value = con.execute("SELECT * FROM strings WHERE parametr = ?", (param,)).fetchone()
        if str_value:
            return str_value['value']
        else:
            return globals().get(param)


#Получаем настройку из базы или из конфига
def get_setting(param):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        setting = con.execute("SELECT * FROM settings WHERE parametr = ?", (param,)).fetchone()
        if setting:
            return setting['value']
        else:
            return globals().get(param)

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
        if setting['value'].isdigit():
            return int(setting['value'])
        else:
            price_dict = str2dict(setting['value'])
            return price_dict

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
def add_order_reviews(user_id, price, service, status):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute("INSERT INTO reviews "
                    "(user_id, price, service, status, date) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [user_id, price, service, status, get_date()])
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

# Создание Базы Данных
def create_db():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory

        # Пользователи
        if len(con.execute("PRAGMA table_info(users)").fetchall()) == 10:
            print("database was found (users | 1/6)")
        else:
            con.execute("CREATE TABLE users("
                        "id INTEGER PRIMARY KEY,"
                        "user_name TEXT,"
                        "first_name TEXT,"
                        "balance INTEGER DEFAULT 0,"
                        "reg_date TIMESTAMP,"
                        "ref_user_name TEXT,"
                        "ref_id INTEGER,"
                        "is_vip BOOLEN,"
                        "magic TEXT,"
                        "referals TEXT)")

            print("database was not found (users | 1/6), creating...")
        # Пополнения
        if len(con.execute("PRAGMA table_info(refills)").fetchall()) == 4:
            print("database was found (refills | 2/6)")
        else:
            con.execute("CREATE TABLE refills("
                        "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
                        "user_id INTEGER NOT NULL,"
                        "amount INTEGER,"
                        "date TIMESTAMP,"
                        "FOREIGN KEY (user_id) REFERENCES users(id))")
            print("database was not found (refills | 2/6), creating...")

        # Покупки
        if len(con.execute("PRAGMA table_info(orders)").fetchall()) == 9:
            print("database was found (orders | 3/6)")
        else:
            con.execute("CREATE TABLE orders("
                        "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
                        "user_id INTEGER NOT NULL,"
                        "price INTEGER,"
                        "position_name TEXT,"
                        "status TEXT,"
                        "links TEXT,"
                        "date TIMESTAMP,"
                        "contacts BOOLEN DEFAULT False,"
                        "FOREIGN KEY (user_id) REFERENCES users(id))")
            print("database was not found (orders | 3/6), creating...")
            con.commit()

        # Покупки
        if len(con.execute("PRAGMA table_info(promocodes)").fetchall()) == 5:
            print("database was found (promocodes | 4/6)")
        else:
            con.execute("CREATE TABLE promocodes("
                        "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
                        "code TEXT NOT NULL,"
                        "price INTEGER,"
                        "isactivated BOOL DEFAULT FALSE,"
                        "prom_users TEXT,)")
            print("database was not found (promocodes | 4/6), creating...")
            con.commit()
        #Отзывы
        if len(con.execute("PRAGMA table_info(reviews)").fetchall()) == 6:
            print("database was found (reviews | 5/6)")
        else:
            # Создание таблицы reviews
            con.execute("CREATE TABLE reviews ("
                        "increment INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "user_id INTEGER NOT NULL, "
                        "price INTEGER, "
                        "service TEXT, "
                        "status TEXT, "
                        "date TIMESTAMP, "
                        "FOREIGN KEY (user_id) REFERENCES users(id))")
            print("database was not found (reviews | 5/6), creating...")

        if len(con.execute("PRAGMA table_info(delreviews)").fetchall()) == 7:
            print("database was found (delreviews | 6/6)")
        else:
            # Создание таблицы reviews
            con.execute("CREATE TABLE delreviews ("
                        "increment INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "user_id INTEGER NOT NULL, "
                        "price INTEGER, "
                        "service TEXT, "
                        "link TEXT, "
                        "status TEXT, "
                        "date TIMESTAMP, "
                        "FOREIGN KEY (user_id) REFERENCES users(id))")
            print("database was not found (delreviews | 6/6), creating...")
            con.commit()

