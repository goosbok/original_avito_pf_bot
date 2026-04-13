import mysql.connector
from mysql.connector import Error
from colorama import Fore
import zipfile
import random
import json
from decimal import Decimal
from datetime import datetime as dt
import re
import sys
from data.config import host, user, bd_name, password
#from loader import host, user, bd_name, password, port, db_connect, REF_AMOUNT

db = ''
cur = ''
masked_password = "*" * len(password)

def create_connection():
    global db, cur
    try:
        # MySQL
        db = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=bd_name,
        )
        db.autocommit = True
        cur = db.cursor(dictionary=True)

        fDate = dt.now().strftime("%d.%m.%Y %H:%M")
        print(f"\n{fDate}: DB successfully connected")
        return True
    except Exception as ex:
        fDate = dt.now().strftime("%d.%m.%Y %H:%M")
        print(f'{fDate}: BD error: {ex}')
        sys.exit()
        return False

def execute_query(query, params=None):
    global db, cur
    try:
        cur.execute(query, params)
        return cur.fetchall()  # Возвращаем результаты запроса
    except mysql.connector.errors.OperationalError as e:
        print(f"Error:\n{e}")
        # Если соединение потеряно, повторное подключение
        db.close()  # Закрываем текущее соединение
        create_connection()  # Повторное подключение
        return execute_query(query, params)  # Повторный вызов функции

def sql_start():
    print(f"==========={Fore.GREEN}DB OPTIONS{Fore.RESET}===========")
    print(f"{Fore.YELLOW}HOST{Fore.RESET} : {host}")
    print(f"{Fore.YELLOW}USER{Fore.RESET} : {user}")
    print(f"{Fore.YELLOW}BD{Fore.RESET} : {bd_name}")
    print(f"{Fore.YELLOW}PASSWORD{Fore.RESET} : {masked_password}")

    if create_connection():
        # Создание таблиц
        execute_query("""CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            username VARCHAR(255) DEFAULT NULL,
            date_write DATE NOT NULL,
            first_name VARCHAR(255) DEFAULT NULL,
            last_name VARCHAR(255) DEFAULT NULL,
            lang VARCHAR(10) DEFAULT NULL,
            refer VARCHAR(255) DEFAULT NULL,
            referals VARCHAR(255) DEFAULT NULL,
            balance DECIMAL(10, 2) DEFAULT 0)
        """)

        execute_query("""CREATE TABLE IF NOT EXISTS reviews (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            price DECIMAL(10, 2) DEFAULT 0,
            service VARCHAR(255) DEFAULT NULL,
            link VARCHAR(255) DEFAULT NULL,
            status VARCHAR(255) DEFAULT NULL,
            date DATE NOT NULL)
        """)

################################################################################################
##################################           Юзеры            ##################################
################################################################################################

async def sql_user_add(user_info, refer=''):
    user = {}

    # Проверка существования пользователя
    data = execute_query("SELECT * FROM users WHERE user_id = %s LIMIT 1", (str(user_info.id),))  # Исправлено: передача параметров
    for row in data:  # Исправлено: добавлены скобки для вызова метода
        user = dict(row)

    if user:  # если старый юзер
        user_new = {
            'last_name': '',
            'first_name': '',
            'username': '',
            'language_code': '',
            'date_write': dt.now()  # Исправлено: вызов метода today()
        }
        user_info = user_new | dict(user_info)  # добавит пустые параметры, если их не было в user_info
        user_info['last_name'] = user_info['last_name'].replace("'", '`').replace("<", '«').replace(">", '»')
        user_info['first_name'] = user_info['first_name'].replace("'", '`').replace("<", '«').replace(">", '»')

        # Обновление информации о пользователе
        execute_query("UPDATE users SET username = %s, first_name = %s, last_name = %s, lang = %s WHERE user_id = %s AND (date_write IS NULL OR lang IS NULL)",
                    (user_info['username'], user_info['first_name'], user_info['last_name'], user_info['language_code'], str(user_info['id'])))

        user['new'] = 0

    else:  # если новый юзер
        user_new = {
            'last_name': '',
            'first_name': '',
            'username': '',
            'language_code': '',
            'date_write': dt.now()  # Исправлено: вызов метода today()
        }
        user_info = user_new | dict(user_info)  # добавит пустые параметры, если их не было в user_info
        user_info['last_name'] = user_info['last_name'].replace("'", '`').replace("<", '«').replace(">", '»')
        user_info['first_name'] = user_info['first_name'].replace("'", '`').replace("<", '«').replace(">", '»')

        # Вставка нового пользователя
        execute_query("INSERT INTO users (user_id, username, first_name, last_name, lang, date_write, refer, referals, balance) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (str(user_info['id']), user_info['username'], user_info['first_name'], user_info['last_name'], user_info['language_code'], dt.now(), refer, None, 0))

        # Проверка добавленного пользователя
        data1 = execute_query("SELECT * FROM users WHERE user_id = %s LIMIT 1", (user_info['id'],))  # Исправлено: передача параметров
        for row in data1:  # Исправлено: добавлены скобки для вызова метода
            user = dict(row)
            user['new'] = 1

    return user

async def sql_get_user(user_id):
    execute_query("SELECT * FROM users WHERE user_id = %s", (str(user_id),))
    user = cur.fetchone()  # Исправлено: добавлены скобки для вызова метода
    return user

async def get_user_by_username(username):
    if username.startswith("@"):
        username = username[1:]
    try:
        execute_query("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()  # Исправлено: добавлены скобки для вызова метода
        return user
    except Exception as e:
        print(f"Error:\n{e}")  # Добавлено: вывод ошибки
        return False

# referal - выгружаем таблицу referal в массив
async def sql_referal_load(action=False, param=False):
    if action:
        if action == 'add' and param:
            execute_query("INSERT INTO referal_links (title, link, user_id) VALUES (%s, %s, %s)",
                        (param['title'], param['link'], param['user_id']))
            execute_query("SELECT MAX(id) AS max FROM referal_links WHERE title = %s AND link = %s",
                        (param['title'], param['link']))
            maximum = cur.fetchone()['max']
            if not param['link']:
                param['link'] = f'link_{maximum}'
            if not param['title']:
                param['title'] = param['link']
            execute_query("UPDATE referal_links SET title = %s, link = %s WHERE id = %s",
                        (param['title'], param['link'], maximum))
        elif action == 'delete' and param:
            execute_query("DELETE FROM referal_links WHERE id = %s", (param,))
    ref = []
    execute_query("SELECT * FROM referal_links WHERE link != '' AND link IS NOT NULL")
    for row in cur.fetchall():
        ref.append(row['link'])
    return ref

async def sql_delete_user(user_id):
    try:
        execute_query("DELETE FROM users WHERE user_id = %s", (user_id,))
        return True
    except Exception as ex:
        fDate = dt.now().strftime("%d.%m.%Y %H:%M")
        print(f"{Fore.RED}{fDate}{Fore.RESET}: ERROR Deleting user with id {Fore.RED}{user_id}{Fore.RESET}\n{ex}")
        return False


################################################################################################
##################################           Отзывы           ##################################
################################################################################################
#Добавить отзыв.
async def sql_add_review(user_id, price, service_name, link, status:'Posted'):
    execute_query("INSERT INTO reviews (user_id, price, service, link, status, date) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, price, service_name, link, status, dt.now()))

#Получить последний заказ пользователя
async def sql_get_last_review(user_id):
    data = execute_query("SELECT * FROM reviews WHERE user_id = %s ORDER BY id DESC LIMIT 1", (user_id,))  # Исправлено: синтаксис MySQL
    return data[len(data) - 1]  # Возвращаем одну строку

#Получить все.
async def sql_get_all_reviews():
    data = execute_query("SELECT * FROM reviews")
    return data

#Получить все заказы по сервису.
async def sql_get_reviews_by_service(service_name):
    reviews_array = []
    reviews = execute_query("SELECT * FROM reviews WHERE service = %s", (service_name,))
    for review in reviews:
        reviews_array.append(review)

    return reviews_array

async def sql_get_all_reviews_by_user(user_id):
    reviews_array = []
    reviews = execute_query("SELECT * FROM reviews WHERE user_id = %s", (str(user_id),))
    for review in reviews:
        reviews_array.append(review)

    return reviews_array