#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      KIPiA
#
# Created:     24.12.2024
# Copyright:   (c) KIPiA 2024
# Licence:     <your licence>
#-------------------------------------------------------------------------------

#SELECT * FROM strings
#            WHERE parametr LIKE 'qna_avito:%'
#            ORDER BY CAST(SUBSTR(parametr, INSTR(parametr, ':') + 1) AS INTEGER)

import ast
import sqlite3
from data.config import path_database as path_db
from utils.sqlite3 import *
from datetime import date, datetime
from data.loader import bot
from design import *
from data.config import *
import asyncio
import re


def fix_positions():
    orders = all_orders()
    pos_arr = []
    for order in orders:
        if '-' in order['position_name']:
            data = order['position_name'].split('-')
            days = data[0].split()[0]
            pf = data[1].split()[0]
            increment = order['increment']
            with sqlite3.connect(path_db) as con:
                sql = "UPDATE orders SET position_name = ? WHERE increment = ?"
                con.execute(sql, (f"{days}/{pf}", increment))
                con.commit()

def print_positions():
    orders = all_orders()
    pos_arr = []
    for order in orders:
        if order['position_name'] not in pos_arr:
            pos_arr.append(order['position_name'])
    print(pos_arr)

def print_status():
    orders = all_orders()
    pos_arr = []
    for order in orders:
        if order['status'] not in pos_arr:
            pos_arr.append(order['status'])
    print(pos_arr)

def fix_status():
    orders = all_orders()
    for order in orders:
        if order['status'] == 'Размещён':
            status = 'Posted'
        elif order['status'] == 'Выполнено':
            status = 'Completed'
        else:
            status = order['status']

        with sqlite3.connect(path_db) as con:
            sql = "UPDATE orders SET status = ? WHERE increment = ?"
            con.execute(sql, (status, order['increment']))
            con.commit()

def print_delta():
    orders = all_orders()
    d0 = datetime.now()
    for order in orders:
        d1 = datetime.strptime(order['date'], '%d.%m.%Y %H:%M:%S')
        delta = d0 - d1
        print(delta.days)

async def order_executor():
    orders = all_orders()
    d0 = datetime.now()
    for order in orders:
        days_in_order = int(order['position_name'].split('/')[0])
        d1 = datetime.strptime(order['date'], '%d.%m.%Y %H:%M:%S')
        delta = d0 - d1
        if order['status'] == 'Posted':
            if delta.days >= days_in_order:
                status = 'Completed'
                with sqlite3.connect(path_db) as con:
                    sql = "UPDATE orders SET status = ? WHERE increment = ?"
                    con.execute(sql, (status, order['increment']))
                    con.commit()
                msg = f"✅ Ваш заказ №{order['increment']} выполнен."
                try:
                    await bot.send_message(chat_id=int(order['user_id']), text=msg, disable_web_page_preview=True)
                    print(f"Заказ № {order['increment']}. Сообщение юзеру {order['user_id']} отправлено!")
                except Exception as e:
                    print(f"Заказ № {order['increment']}. Сообщение юзеру {order['user_id']} не отправлено!\n{e}")

def sql_link_cleaner(link):
    """
    cleaned_link = re.sub(r"^[\"'\\]+|[\"'\\]+$|[<>{}|\\^~\[\]`]+", "", link)
    cleaned_link = re.sub(r";\s*$", "", cleaned_link)
    cleaned_link = cleaned_link.replace(";", "")
    cleaned_link = cleaned_link.replace("\s", "\n")
    cleaned_link = re.sub(r"\?$", "", cleaned_link)  # Удаляем знак вопроса в конце
    cleaned_link = cleaned_link.replace(" ,", " ")
    """
    cleaned_link = link.replace("''", "").replace("[", "").replace("[", "")
    return cleaned_link


def fix_links():
    # Получаем все строки из таблицы
    with sqlite3.connect(path_db) as con:
        rows = con.execute("SELECT increment, links FROM orders").fetchall()
        # Обновляем строки с очищенными ссылками
        for row in rows:
            increment, link = row
            cleaned_link = sql_link_cleaner(link)

            # Обновляем только если ссылка изменилась
            if cleaned_link != link:
                con.execute("UPDATE orders SET links = ? WHERE increment = ?", (cleaned_link, increment))

def add_user_name():
    orders = all_orders()
    users = all_users()
    for order in orders:
        for user in users:
            if order['user_id'] == user['id']:
                with sqlite3.connect(path_db) as con:
                    con.row_factory = dict_factory
                    con.execute("UPDATE orders SET user_name = ? WHERE user_id = ?", (user['user_name'], user['id']))
                    con.commit()

def check_globals():
    all_var = dir()
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        all_strings = con.execute("SELECT parametr FROM settings WHERE parametr like 'str_%'").fetchall()
        all_buttons = con.execute("SELECT parametr FROM settings WHERE parametr like 'btn_%'").fetchall()
        con.commit()

    for name in all_var:
        # Print the item if it doesn't start with '__'
        #if not name.startswith('__'):
        myvalue = eval(name)
        print(f"{name}, is, {type(myvalue)}, and is equal to {myvalue}")

def del_bots(in_date):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        all_bots = con.execute(f"SELECT id FROM users WHERE reg_date LIKE '{in_date}%' AND user_name='' and balance=0").fetchall()
    
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        con.execute(f"DELETE FROM users WHERE reg_date LIKE '{in_date}%' AND user_name='' and balance=0").fetchall()
    
    all_bots_arr = []
    for bot in all_bots:
        all_bots_arr.append(bot['id'])
        
    #print(all_bots_arr)
    botCnt = 0
    for bot in all_bots_arr:
        botCnt += 1

    print(f"За {in_date} удалено {botCnt}")

if __name__ == '__main__':
    #asyncio.run(order_executor())
    attack_dates=['02.04.2025', '08.04.2025', '09.04.2025']
    for d in attack_dates:
        del_bots(d)