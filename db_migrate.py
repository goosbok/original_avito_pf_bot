#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      KIPiA
#
# Created:     29.12.2024
# Copyright:   (c) KIPiA 2024
# Licence:     <your licence>
#-------------------------------------------------------------------------------

def main():
    pass

if __name__ == '__main__':
    main()
import sqlite3
import mysql.connector

def copy_table(sqlite_db_path, mysql_config, table_name):
    # Подключение к SQLite
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_cursor = sqlite_conn.cursor()

    # Подключение к MySQL
    mysql_conn = mysql.connector.connect(**mysql_config)
    mysql_cursor = mysql_conn.cursor()

    try:
        # Извлечение данных из таблицы SQLite
        sqlite_cursor.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cursor.fetchall()

        # Получение названий столбцов
        column_names = [description[0] for description in sqlite_cursor.description]

        # Создание таблицы в MySQL, если она не существует
        create_table_query = f"CREATE TABLE IF NOT EXISTS {table_name} (" + ", ".join([f"{col} TEXT" for col in column_names]) + ")"
        mysql_cursor.execute(create_table_query)

        # Вставка данных в таблицу MySQL
        insert_query = f"INSERT INTO {table_name} ({', '.join(column_names)}) VALUES ({', '.join(['%s'] * len(column_names))})"
        mysql_cursor.executemany(insert_query, rows)

        # Подтверждение изменений
        mysql_conn.commit()
        print(f"Таблица '{table_name}' успешно скопирована из SQLite в MySQL.")

    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        # Закрытие соединений
        sqlite_cursor.close()
        sqlite_conn.close()
        mysql_cursor.close()
        mysql_conn.close()

# Пример использования
sqlite_db_path = "data/database.db"
mysql_config = {
    'host': '31.129.101.122',
    'user': 'admin_otziviigor',
    'password': 'AlDW6AOn7b',
    'database': 'admin_otziviigor'
}
table_name = 'reviews'

copy_table(sqlite_db_path, mysql_config, table_name)
