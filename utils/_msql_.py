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

################################################################################################
##################################         При старте         ##################################
################################################################################################
def sql_connect():
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
        print(f"\n{Fore.GREEN}{fDate}{Fore.RESET}: DB successfully connected")
        return True
    except Exception as ex:
        fDate = dt.now().strftime("%d.%m.%Y %H:%M")
        print(f'{Fore.RED}{fDate}{Fore.RESET}: BD error: {ex}')
        sys.exit()
        return False

def sql_start():
    #global db, cur

    print(f"""==========={Fore.GREEN}DB OPTIONS{Fore.RESET}===========
    {Fore.YELLOW}HOST{Fore.RESET} : {host}
    {Fore.YELLOW}USER{Fore.RESET} : {user}
    {Fore.YELLOW}BD{Fore.RESET} : {bd_name}
    {Fore.YELLOW}PASSWORD{Fore.RESET} : {masked_password}""")

    sql_connect()


    cur.execute("""CREATE TABLE IF NOT EXISTS users (
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

    cur.execute("""CREATE TABLE IF NOT EXISTS reviews (
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
    cur.execute("SELECT * FROM users WHERE user_id = %s LIMIT 1", (str(user_info.id),))  # Исправлено: передача параметров
    for row in cur.fetchall():  # Исправлено: добавлены скобки для вызова метода
        user = dict(row)

    if user:  # если старый юзер
        user_new = {
            'last_name': '',
            'first_name': '',
            'username': '',
            'language_code': '',
            'date_write': dt.today()  # Исправлено: вызов метода today()
        }
        user_info = user_new | dict(user_info)  # добавит пустые параметры, если их не было в user_info
        user_info['last_name'] = user_info['last_name'].replace("'", '`').replace("<", '«').replace(">", '»')
        user_info['first_name'] = user_info['first_name'].replace("'", '`').replace("<", '«').replace(">", '»')

        # Обновление информации о пользователе
        cur.execute("UPDATE users SET username = %s, first_name = %s, last_name = %s, lang = %s WHERE user_id = %s AND (date_write IS NULL OR lang IS NULL)",
                    (user_info['username'], user_info['first_name'], user_info['last_name'], user_info['language_code'], str(user_info['id'])))

        user['new'] = 0

    else:  # если новый юзер
        user_new = {
            'last_name': '',
            'first_name': '',
            'username': '',
            'language_code': '',
            'date_write': dt.today()  # Исправлено: вызов метода today()
        }
        user_info = user_new | dict(user_info)  # добавит пустые параметры, если их не было в user_info
        user_info['last_name'] = user_info['last_name'].replace("'", '`').replace("<", '«').replace(">", '»')
        user_info['first_name'] = user_info['first_name'].replace("'", '`').replace("<", '«').replace(">", '»')

        # Вставка нового пользователя
        cur.execute("INSERT INTO users (user_id, username, first_name, last_name, lang, date_write, refer, referals, balance) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (str(user_info['id']), user_info['username'], user_info['first_name'], user_info['last_name'], user_info['language_code'], dt.now(), refer, None, 0))

        # Проверка добавленного пользователя
        cur.execute("SELECT * FROM users WHERE user_id = %s LIMIT 1", (user_info['id'],))  # Исправлено: передача параметров
        for row in cur.fetchall():  # Исправлено: добавлены скобки для вызова метода
            user = dict(row)
            user['new'] = 1

    return user

async def sql_get_user(user_id):
    cur.execute("SELECT * FROM users WHERE user_id = %s", (str(user_id),))
    user = cur.fetchone()  # Исправлено: добавлены скобки для вызова метода
    return user

async def get_user_by_username(username):
    if username.startswith("@"):
        username = username[1:]
    try:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()  # Исправлено: добавлены скобки для вызова метода
        return user
    except Exception as e:
        print(f"Error: {e}")  # Добавлено: вывод ошибки
        return False

# referal - выгружаем таблицу referal в массив
async def sql_referal_load(action=False, param=False):
    if action:
        if action == 'add' and param:
            cur.execute("INSERT INTO referal_links (title, link, user_id) VALUES (%s, %s, %s)",
                        (param['title'], param['link'], param['user_id']))
            cur.execute("SELECT MAX(id) AS max FROM referal_links WHERE title = %s AND link = %s",
                        (param['title'], param['link']))
            maximum = cur.fetchone()['max']
            if not param['link']:
                param['link'] = f'link_{maximum}'
            if not param['title']:
                param['title'] = param['link']
            cur.execute("UPDATE referal_links SET title = %s, link = %s WHERE id = %s",
                        (param['title'], param['link'], maximum))
        elif action == 'delete' and param:
            cur.execute("DELETE FROM referal_links WHERE id = %s", (param,))
    ref = []
    cur.execute("SELECT * FROM referal_links WHERE link != '' AND link IS NOT NULL")
    for row in cur.fetchall():
        ref.append(row['link'])
    return ref

async def sql_delete_user(user_id):
    try:
        cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
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
    try:
        cur.execute("INSERT INTO reviews (user_id, price, service, link, status, date) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, price, service_name, link, status, dt.now()))
    except Exception as Ex:
        print(f'{Fore.RED}Error:{Fore.RESET}\n{Ex}')
        sql_connect()
        cur.execute("INSERT INTO reviews (user_id, price, service, link, status, date) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, price, service_name, link, status, dt.now().strftime('%d.%m.%Y %H:%M')))

#Получить последний заказ пользователя
async def sql_get_last_review(user_id):
    try:
        # Запрос для получения последнего заказа пользователя
        cur.execute("SELECT * FROM reviews WHERE user_id = %s ORDER BY id DESC LIMIT 1", (user_id,))  # Исправлено: синтаксис MySQL
        return cur.fetchone()  # Возвращаем одну строку

    except Exception as e:
        print(f"Ошибка: {e}")
        return None

#Получить все.
async def sql_get_all_reviews():
    try:
        cur.execute("SELECT * FROM reviews")
        return cur.fetchall()
    except Exception as e:
        print(f'{Fore.RED}Error:{Fore.RESET}\n{e}')
        sql_connect()
        cur.execute("SELECT * FROM reviews")
        return cur.fetchall()

#Получить все заказы по сервису.
async def sql_get_reviews_by_service(service_name):
    reviews_array = []
    try:
        cur.execute("SELECT * FROM reviews WHERE service = %s", (service_name,))
        reviews = cur.fetchall()
        # Преобразование списка отзывов в словарь
        #reviews_dict = {review['increment']: review for review in reviews}
        for review in reviews:
            reviews_array.append(review)
        return reviews_array
    except Exception as e:
        print(f"Ошибка: {e}")
        return {}

async def sql_get_all_reviews_by_user(user_id):
    reviews_array = []
    try:
        cur.execute("SELECT * FROM reviews WHERE user_id = %s", (str(user_id),))
        rev = cur.fetchall()
    except:
        sql_connect()
        cur.execute("SELECT * FROM reviews WHERE user_id = %s", (str(user_id),))
        rev = cur.fetchall()

    for r in rev:
        reviews_array.append(r)

    return reviews_array