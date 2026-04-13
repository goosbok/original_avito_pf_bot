import httplib2
import apiclient.discovery
from oauth2client.service_account import ServiceAccountCredentials
from utils.sqlite3 import all_users, all_orders, get_user, all_refills, get_report_exclude
from utils.msql import sql_get_all_reviews, sql_get_all_reviews_by_user
from data.config import services
from utils.other import link_cleaner, get_days_suffix
from datetime import *
import asyncio

CREDENTIALS_FILE = 'utils/dev-trees-414317-e16633571d94.json'  # имя файла с закрытым ключом

credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, ['https://www.googleapis.com/auth/spreadsheets',
                                                                                  'https://www.googleapis.com/auth/drive'])
httpAuth = credentials.authorize(httplib2.Http())
service = apiclient.discovery.build('sheets', 'v4', http = httpAuth)

def get_user_str(user):
    if user['user_name']:
        return user['user_name']
    else:
        return str(user['id'])

def create_sheet():
    try:
        orders = all_orders()
        excludes = get_report_exclude()
        d = datetime.now()

        # Размер чанка для обработки
        CHUNK_SIZE = 1000
        
        #Получаю № заказа
        no = ['№']
        ids = ['id']
        logins = ['username']
        links = ['Ссылки']
        contacts = ['Контакты']
        position_name = ['Дней/ПФ']
        prices = ['Итого']
        reg_date = ['Дата']
        status = ['Статус']
        
        # Обрабатываем заказы чанками
        for order in orders:
            if str(order['user_id']) not in excludes:
                links_array = order['links'].split()
                for link in links_array:
                    logins.append(order['user_name'])
                    # Очищаем ссылку один раз
                    clean_link = link.replace("'", "").replace("[", "").replace("]", "")
                    links.append(clean_link)
                    
                    #Получаю № заказа
                    no.append(order['increment'])
                    ids.append(order['user_id'])
                    contacts.append('Да' if order['contacts'] else 'Нет')
                    position_name.append(order['position_name'])
                    prices.append(order['price'])
                    reg_date.append(order['date'])
                    
                    if order['status'] == 'Posted':
                        status.append('Размещён')
                    elif order['status'] == 'Completed':
                        status.append('Выполнен')
                    else:
                        status.append(order['status'])
                
                # Очищаем временный массив
                del links_array
        
        # Очищаем orders из памяти
        del orders

        # Компактные запросы форматирования
        format_requests = [
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 40}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 3}, "properties": {"pixelSize": 100}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4}, "properties": {"pixelSize": 500}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 5, "endIndex": 6}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 6, "endIndex": 7}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 7, "endIndex": 8}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 8, "endIndex": 9}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
            {'repeatCell': {'range': {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 9}, 
                           'cell': {'userEnteredFormat': {'horizontalAlignment': 'CENTER', "backgroundColor": {"red": 0.8, "green": 0.8, "blue": 0.8, "alpha": 1}, 'textFormat': {'bold': True}}}, 
                           'fields': 'userEnteredFormat'}},
            {'setBasicFilter': {'filter': {'range': {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 9}}}}
        ]

        spreadsheet = service.spreadsheets().create(body = {
            'properties': {'title': f"Заказы-{d.strftime('%d-%m-%Y-%H-%M-%S')}", 'locale': 'ru_RU'},
            'sheets': [{'properties': {'sheetType': 'GRID', 'sheetId': 0, 'title': 'Заказы', 'gridProperties': {'rowCount': len(no), 'columnCount': 9}}}]
        }).execute()

        spreadsheet_id = spreadsheet['spreadsheetId']
        
        # Форматирование
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": format_requests}).execute()
        
        # Очищаем format_requests
        del format_requests

        # Заполнение данными чанками для экономии памяти
        total_rows = len(no)
        
        # Отправляем данные по колонкам чанками
        all_columns = [
            ('A', no),
            ('B', ids),
            ('C', logins),
            ('D', links),
            ('E', contacts),
            ('F', position_name),
            ('G', prices),
            ('H', status),
            ('I', reg_date)
        ]
        
        for col_letter, col_data in all_columns:
            # Разбиваем каждую колонку на чанки и отправляем
            for chunk_start in range(0, total_rows, CHUNK_SIZE):
                chunk_end = min(chunk_start + CHUNK_SIZE, total_rows)
                chunk = col_data[chunk_start:chunk_end]
                
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"Заказы!{col_letter}{chunk_start + 1}:{col_letter}{chunk_end}",
                    valueInputOption="USER_ENTERED",
                    body={"majorDimension": "COLUMNS", "values": [chunk]}
                ).execute()
                
                # Очищаем чанк
                del chunk
        
        # Очищаем большие массивы данных
        del no, ids, logins, links, contacts, position_name, prices, reg_date, status
        del all_columns, excludes

        driveService = apiclient.discovery.build('drive', 'v3', http = httpAuth)
        driveService.permissions().create(
            fileId=spreadsheet_id,
            body={'type': 'anyone', 'role': 'writer'},
            fields='id'
        ).execute()

        spreadsheet_url = spreadsheet['spreadsheetUrl']
        del spreadsheet
        
        return spreadsheet_url
        
    except Exception as e:
        print(f'Error in create_sheet: {e}')
        raise

def create_orders_report(user_id):
    orders = all_orders()
    users = all_users()
    d=datetime.now()
    sheet_name = f"Заказы-{d.strftime('%d-%m-%Y-%H-%M-%S')}"

    sheets_array = []
    formated_sheets_array = []
    data_array = []
    magic_user = get_user(id=user_id)
    ids_array = []
    if magic_user['referals']:
        ids_array = [str(user_id)] + magic_user['referals'].split(',')
    else:
        ids_array = [str(user_id)]

    for i in range(len(ids_array)):
        usr = get_user(id=ids_array[i])
        row_cnt = 1

        no = ['№']
        ids = ['id']
        logins = ['username']
        links = ['Ссылки']
        contacts = ['Контакты']
        position_name = ['Тариф']
        prices = ['Итого']
        reg_date = ['Дата']
        status = ['Статус']

        for order in orders:
            if int(usr['id']) == int(order['user_id']):
                no.append(order['increment'])
                ids.append(order['user_id'])
                links.append(order['links'].replace("'", "").replace(", ", "\n").replace("\n\n", "\n"))
                contacts.append(order['contacts'])
                position_name.append(order['position_name'])
                prices.append(order['price'])
                reg_date.append(order['date'])
                status.append(order['status'])
                #logins.append(usr['user_name'])
                logins.append(get_user_str(usr))
                row_cnt += 1

        #Массив для создания таблицы
        #sheet_title = usr['user_name']
        sheet_title = get_user_str(usr)
        sheets_array.append({'properties':
            {'sheetType': 'GRID', 'sheetId': i, 'title': sheet_title, 'gridProperties': {'rowCount': row_cnt, 'columnCount': 10}}}
        )

        #Массив для форматирования
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 40},"fields": "pixelSize"}})
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 3}, "properties": {"pixelSize": 100}, "fields": "pixelSize"}})
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4}, "properties": {"pixelSize": 500}, "fields": "pixelSize"}})
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}})
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 5, "endIndex": 6}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}})
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 6, "endIndex": 7}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}})
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 7, "endIndex": 8}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}})
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 8, "endIndex": 9}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}})
        formated_sheets_array.append({'repeatCell': {'range': {'sheetId': i, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 9}, 'cell': {'userEnteredFormat': {'horizontalAlignment': 'CENTER', "backgroundColor": {"red": 0.8, "green": 0.8, "blue": 0.8, "alpha": 1}, 'textFormat': {'bold': True}}}, 'fields': 'userEnteredFormat'}})
        formated_sheets_array.append({'setBasicFilter': {'filter': {'range': {'sheetId': i, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 9}}}})

        #Самое важное - массив данных!
        data_array.append({"range": f"{sheet_title}!A1:A{row_cnt}", "majorDimension": "COLUMNS", "values": [no]})
        data_array.append({"range": f"{sheet_title}!B1:B{row_cnt}", "majorDimension": "COLUMNS", "values": [ids]})
        data_array.append({"range": f"{sheet_title}!C1:C{row_cnt}", "majorDimension": "COLUMNS", "values": [logins]})
        data_array.append({"range": f"{sheet_title}!D1:D{row_cnt}", "majorDimension": "COLUMNS", "values": [links]})
        data_array.append({"range": f"{sheet_title}!E1:E{row_cnt}", "majorDimension": "COLUMNS", "values": [contacts]})
        data_array.append({"range": f"{sheet_title}!F1:F{row_cnt}", "majorDimension": "COLUMNS", "values": [position_name]})
        data_array.append({"range": f"{sheet_title}!G1:G{row_cnt}", "majorDimension": "COLUMNS", "values": [prices]})
        data_array.append({"range": f"{sheet_title}!H1:H{row_cnt}", "majorDimension": "COLUMNS", "values": [status]})
        data_array.append({"range": f"{sheet_title}!I1:I{row_cnt}", "majorDimension": "COLUMNS", "values": [reg_date]})

    """
    Создаем таблицу
    """
    spreadsheet = service.spreadsheets().create(body = {
        'properties': {'title': sheet_name, 'locale': 'ru_RU'},
        'sheets': sheets_array
    }).execute()

    """
    Форматируем
    """
    results = service.spreadsheets().batchUpdate(spreadsheetId = spreadsheet['spreadsheetId'], body = {"requests": formated_sheets_array}).execute()

    """
    Заполняем данными
    """
    results = service.spreadsheets().values().batchUpdate(spreadsheetId = spreadsheet['spreadsheetId'], body = {
        "valueInputOption": "USER_ENTERED",
        "data": data_array
    }).execute()

    driveService = apiclient.discovery.build('drive', 'v3', http = httpAuth)
    shareRes = driveService.permissions().create(
        fileId = spreadsheet['spreadsheetId'],
        body = {'type': 'anyone', 'role': 'writer'},  # доступ на чтение кому угодно
        fields = 'id'
    ).execute()

    return spreadsheet['spreadsheetUrl']

def create_refills_report(user_id):
    refills = all_refills()
    users = all_users()
    d=datetime.now()
    sheet_name = f"Оплаты-{d.strftime('%d-%m-%Y-%H-%M-%S')}"

    sheets_array = []
    formated_sheets_array = []
    data_array = []
    magic_user = get_user(id=user_id)
    ids_array = []
    if magic_user['referals']:
        ids_array = [str(user_id)] + magic_user['referals'].split(',')
    else:
        ids_array = [str(user_id)]

    for i in range(len(ids_array)):
        usr = get_user(id=ids_array[i])
        row_cnt = 1

        no = ['№']
        ids = ['id']
        logins = ['username']
        amount = ['Оплата']
        amount_date = ['Дата']

        for refill in refills:
            if int(usr['id']) == int(refill['user_id']):
                no.append(refill['increment'])
                ids.append(refill['user_id'])
                amount_date.append(refill['date'])
                amount.append(refill['amount'])
                logins.append(usr['user_name'])
                row_cnt += 1

        #Массив для создания таблицы
        sheet_title = get_user_str(usr)
        sheets_array.append({'properties':
            {'sheetType': 'GRID', 'sheetId': i, 'title': sheet_title, 'gridProperties': {'rowCount': row_cnt, 'columnCount': 5}}}
        )

        #Массив для форматирования
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 40},"fields": "pixelSize"}})
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 4}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}})
        formated_sheets_array.append({"updateDimensionProperties": {"range": {"sheetId": i, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}})
        formated_sheets_array.append({'repeatCell': {'range': {'sheetId': i, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 5}, 'cell': {'userEnteredFormat': {'horizontalAlignment': 'CENTER', "backgroundColor": {"red": 0.8, "green": 0.8, "blue": 0.8, "alpha": 1}, 'textFormat': {'bold': True}}}, 'fields': 'userEnteredFormat'}})
        formated_sheets_array.append({'setBasicFilter': {'filter': {'range': {'sheetId': i, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 5}}}})

        #Самое важное - массив данных!
        data_array.append({"range": f"{sheet_title}!A1:A{row_cnt}", "majorDimension": "COLUMNS", "values": [no]})
        data_array.append({"range": f"{sheet_title}!B1:B{row_cnt}", "majorDimension": "COLUMNS", "values": [ids]})
        data_array.append({"range": f"{sheet_title}!C1:C{row_cnt}", "majorDimension": "COLUMNS", "values": [logins]})
        data_array.append({"range": f"{sheet_title}!D1:D{row_cnt}", "majorDimension": "COLUMNS", "values": [amount]})
        data_array.append({"range": f"{sheet_title}!E1:E{row_cnt}", "majorDimension": "COLUMNS", "values": [amount_date]})

    """
    Создаем таблицу
    """
    spreadsheet = service.spreadsheets().create(body = {
        'properties': {'title': sheet_name, 'locale': 'ru_RU'},
        'sheets': sheets_array
    }).execute()

    """
    Форматируем
    """
    results = service.spreadsheets().batchUpdate(spreadsheetId = spreadsheet['spreadsheetId'], body = {"requests": formated_sheets_array}).execute()

    """
    Заполняем данными
    """
    results = service.spreadsheets().values().batchUpdate(spreadsheetId = spreadsheet['spreadsheetId'], body = {
        "valueInputOption": "USER_ENTERED",
        "data": data_array
    }).execute()

    driveService = apiclient.discovery.build('drive', 'v3', http = httpAuth)
    shareRes = driveService.permissions().create(
        fileId = spreadsheet['spreadsheetId'],
        body = {'type': 'anyone', 'role': 'writer'},  # доступ на чтение кому угодно
        fields = 'id'
    ).execute()

    return spreadsheet['spreadsheetUrl']

def create_reviews_report(orders):
    users = all_users()
    excludes = get_report_exclude()
    d=datetime.now()

    #Получаю № заказа
    no = ['№']
    ids = ['id']
    logins = ['username']
    ru_services = ['Сервис']
    links = ['Ссылка']
    prices = ['Итого']
    reg_date = ['Дата']
    status = ['Статус']
    for order in orders:
        if str(order['user_id']) not in excludes:
            #Получаю № заказа
            no.append(order['id'])
            ids.append(order['user_id'])
            prices.append(str(order['price']))
            ru_services.append(services[order['service']])
            reg_date.append(str(order['date']))
            if order['status'] == 'Posted':
                status.append('Размещён')
            elif order['status'] == 'Completed':
                status.append('Выполнен')
            else:
                status.append(order['status'])
            links.append(order['link'].replace("'", "").replace(", ", "").replace("\n", "").replace("\\", "").replace("\"", ""))
            for user in users:
                if int(order['user_id']) == int(user['id']):
                    logins.append(get_user_str(user))

    spreadsheet = service.spreadsheets().create(body = {
        'properties': {'title': f"Отзывы-{d.strftime('%d-%m-%Y-%H-%M-%S')}", 'locale': 'ru_RU'},
        'sheets': [{'properties': {'sheetType': 'GRID',
                                    'sheetId': 0,
                                    'title': 'Отзывы',
                                    'gridProperties': {'rowCount': len(no), 'columnCount': 8}}}]
    }).execute()

    results = service.spreadsheets().batchUpdate(spreadsheetId = spreadsheet['spreadsheetId'], body = {
        "requests": [
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 40}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 3}, "properties": {"pixelSize": 100}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5}, "properties": {"pixelSize": 500}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 5, "endIndex": 6}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 6, "endIndex": 7}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 7, "endIndex": 8}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
            {'repeatCell': {'range': {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 8}, 'cell': {'userEnteredFormat': {'horizontalAlignment': 'CENTER', "backgroundColor": {"red": 0.8, "green": 0.8, "blue": 0.8, "alpha": 1}, 'textFormat': {'bold': True}}}, 'fields': 'userEnteredFormat'}},
            {'setBasicFilter': {'filter': {'range': {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 8}}}}
            ]}).execute()

    results = service.spreadsheets().values().batchUpdate(spreadsheetId = spreadsheet['spreadsheetId'], body = {
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": f"Отзывы!A1:A{len(no)}", "majorDimension": "COLUMNS", "values": [no]},
                 {"range": f"Отзывы!B1:B{len(no)}", "majorDimension": "COLUMNS", "values": [ids]},
                 {"range": f"Отзывы!C1:C{len(no)}", "majorDimension": "COLUMNS", "values": [logins]},
                 {"range": f"Отзывы!D1:D{len(no)}", "majorDimension": "COLUMNS", "values": [ru_services]},
                 {"range": f"Отзывы!E1:E{len(no)}", "majorDimension": "COLUMNS", "values": [links]},
                 {"range": f"Отзывы!F1:F{len(no)}", "majorDimension": "COLUMNS", "values": [prices]},
                 {"range": f"Отзывы!G1:G{len(no)}", "majorDimension": "COLUMNS", "values": [status]},
                 {"range": f"Отзывы!H1:H{len(no)}", "majorDimension": "COLUMNS", "values": [reg_date]}]
    }).execute()

    driveService = apiclient.discovery.build('drive', 'v3', http = httpAuth)
    shareRes = driveService.permissions().create(
        fileId = spreadsheet['spreadsheetId'],
        body = {'type': 'anyone', 'role': 'writer'},  # доступ на чтение кому угодно
        fields = 'id'
    ).execute()

    return spreadsheet['spreadsheetUrl']

if __name__ == '__main__':
    print("Формируем отчет")
    print(create_sheet())
