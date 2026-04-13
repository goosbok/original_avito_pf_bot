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

def get_price(param:'price_test'):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        setting = con.execute("SELECT * FROM settings WHERE parametr = ?", (param,)).fetchone()

        price_dict = str2dict(setting['value'])
        print(price_dict)
        for k,v in price_dict.items():
            print(f"{k}:{v}")

if __name__ == '__main__':
    get_price('price_test')