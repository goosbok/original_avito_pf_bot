import sqlite3
from data import config
from data.config import path_database as path_db

# Устанавливаем соединение с базой данных
conn = sqlite3.connect(path_db)

# Создаем курсор для выполнения SQL-запросов
cursor = conn.cursor()

# Обновляем записи, изменяя строки с указанным шаблоном в столбце position_name
update_query = """
UPDATE orders
SET position_name =
    CASE
        WHEN position_name LIKE 'ПФ 1 день - %' THEN '1/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 2 дня - %' THEN '2/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 3 дня - %' THEN '3/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 4 дня - %' THEN '4/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 5 дней - %' THEN '5/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 6 дней - %' THEN '6/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 7 дней - %' THEN '7/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 8 дней - %' THEN '8/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 9 дней - %' THEN '9/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 10 дней - %' THEN '10/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 11 дней - %' THEN '11/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 12 дней - %' THEN '12/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 13 дней - %' THEN '13/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 14 дней - %' THEN '14/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 15 дней - %' THEN '15/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 16 дней - %' THEN '16/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 17 дней - %' THEN '17/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 18 дней - %' THEN '18/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 19 дней - %' THEN '19/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 20 дней - %' THEN '20/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 21 день - %' THEN '21/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 22 дня - %' THEN '22/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 23 дня - %' THEN '23/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 24 дня - %' THEN '24/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 25 дней - %' THEN '25/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 26 дней - %' THEN '26/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 27 дней - %' THEN '27/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 28 дней - %' THEN '28/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 29 дней- %' THEN '29/' || substr(position_name, instr(position_name, '-') + 2)
        WHEN position_name LIKE 'ПФ 30 дней - %' THEN '30/' || substr(position_name, instr(position_name, '-') + 2)
        ELSE position_name
    END
"""

# Выполняем обновление
cursor.execute(update_query)

# Сохраняем изменения
conn.commit()

# Проверяем обновленные данные
cursor.execute("SELECT * FROM orders;")
updated_rows = cursor.fetchall()
for row in updated_rows:
    print(row)

# Закрываем курсор и соединение
cursor.close()
conn.close()