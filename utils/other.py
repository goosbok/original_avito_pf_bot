import time
import ast
import re
from decimal import Decimal
from datetime import datetime, timedelta

# Получение текущей даты
def get_date():
    this_date = datetime.today().replace(microsecond=0)
    this_date = this_date.strftime("%d.%m.%Y %H:%M:%S")

    return this_date

def format_decimal(value):
    decimal_value = Decimal(value)
    formatted_value = f"{decimal_value:,.2f}".replace(',', ' ')
    return formatted_value

def str2dict(str_value):
    result_dict = ast.literal_eval(str_value)

    return result_dict

"""
def get_admins():
    return config.ADMINS
"""

def link_cleaner(link):
    cleaned_link = re.sub(r"^[\"'\\]+|[\"'\\]+$|[<>{}|\\^~\[\]`]+", "", link)
    cleaned_link = re.sub(r";\s*$", "", cleaned_link)
    cleaned_link = cleaned_link.replace(";", "")
    cleaned_link = cleaned_link.replace("\s", "\n")
    cleaned_link = re.sub(r"\?$", "", cleaned_link)  # Удаляем знак вопроса в конце
    cleaned_link = cleaned_link.replace(']','').replace('[','')
    return cleaned_link

def str2bool(value):
  return value.lower() in ("yes", "true", "1")

def str2dict(str_value):
    result_dict = ast.literal_eval(str_value)

    return result_dict

#Падежи для слова день
def get_days_suffix(count):
    if 11 <= int(count) % 100 <= 14:
        return "дней"
    elif int(count) % 10 == 1:
        return "день"
    elif int(count) % 10 in [2, 3, 4]:
        return "дня"
    else:
        return "дней"

def declension_months(count):
    if count % 10 == 1 and count % 100 != 11:
        return f"месяц"
    elif 2 <= count % 10 <= 4 and not (12 <= count % 100 <= 14):
        return f"месяца"
    else:
        return f"месяцев"

def declension_review(count):
    # Определяем склонение слова "отзыв"
    if count % 10 == 1 and count % 100 != 11:
        return f"отзыв"
    elif 2 <= count % 10 <= 4 and not (12 <= count % 100 <= 14):
        return f"отзыва"
    else:
        return f"отзывов"

def decline_order(count):
    if count % 10 == 1 and count % 100 != 11:
        return f"заказ"
    elif 2 <= count % 10 <= 4 and not (12 <= count % 100 <= 14):
        return f"заказа"
    else:
        return f"заказов"

#Преобразование времени
async def conv_delta(dlt: timedelta) -> str:
    minutes, seconds = divmod(int(dlt.total_seconds()), 60)
    return f"{minutes}:{seconds:02}"

#Делим сообщение на части
def split_messages(msg_array, symbol):
    result = []
    current_message = ""

    for msg in msg_array:
        if len(current_message) + len(msg) + 1 <= 4096:  # +1 для пробела или разделителя
            if current_message:
                current_message += symbol  # добавляем пробел перед новым сообщением
            current_message += msg
        else:
            result.append(current_message)
            current_message = msg  # начинаем новое сообщение

    if current_message:  # добавляем последнее сообщение, если оно не пустое
        result.append(current_message)

    return result

#Получаем имя пользователя из базы. С именем
async def get_user_string_with_first_name(user):
    if user['user_name'] is not None and user['first_name'] is not None:
        return f"<a href='tg://user?id={user['id']}'>{user['id']}</a>: {user['first_name']}(@{user['user_name']})"
    elif user['user_name'] is not None:
        return f"@{user['user_name']} (<a href='tg://user?id={user['id']}'>{user['id']}</a>)"
    elif user['first_name'] is not None:
        return f"<a href='tg://user?id={user['id']}'>{user['id']}</a>: {user['first_name']}"
    else:
        return f"<a href='tg://user?id={user['id']}'>{user['id']}</a>"

#Без имени.
async def get_user_string_without_first_name(user):
    if user['user_name'] is not None:
        return f"@{user['user_name']} (<a href='tg://user?id={user['id']}'>{user['id']}</a>)"
    else:
        return f"<a href='tg://user?id={user['id']}'>{user['id']}</a>"

#Получаем количество рефералов.
def get_referals_count(user):
    if user['referals']:
        referals_array = user['referals'].split(',')
        referals_count = len(referals_array)
        return referals_count
    else:
        return 0