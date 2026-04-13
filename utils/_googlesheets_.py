import httplib2
import apiclient.discovery
from oauth2client.service_account import ServiceAccountCredentials
from utils.sqlite3 import all_users, all_orders, get_user, all_refills
from datetime import *

CREDENTIALS_FILE = 'utils/dev-trees-414317-e16633571d94.json'  # имя файла с закрытым ключом

credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, ['https://www.googleapis.com/auth/spreadsheets',
                                                                                  'https://www.googleapis.com/auth/drive'])
httpAuth = credentials.authorize(httplib2.Http())
service = apiclient.discovery.build('sheets', 'v4', http = httpAuth)

def create_sheet():
    orders = all_orders()
    users = all_users()

    d=datetime.now()

    #Получаю № заказа
    no = ['№']
    ids = ['id']
    logins = ['username']
    links = ['Ссылки']
    contacts = ['Контакты']
    position_name = ['Тариф']
    prices = ['Итого']
    reg_date = ['Дата']
    status = ['Статус']
    for i in range(len(orders)):
        #Получаю № заказа
        no.append(orders[i]['increment'])
        ids.append(orders[i]['user_id'])
        links.append(orders[i]['links'])
        if orders[i]['contacts']:
            contacts.append('Да')
        else:
            contacts.append('Нет')
        position_name.append(orders[i]['position_name'])
        prices.append(orders[i]['price'])
        reg_date.append(orders[i]['date'])
        status.append(orders[i]['status'])
        for a in range(len(users)):
            if orders[i]['user_id'] == users[a]['id']:
               logins.append(users[a]['user_name'])

    spreadsheet = service.spreadsheets().create(body = {
        'properties': {'title': f"Заказы-{d.strftime('%d-%m-%Y-%H-%M-%S')}", 'locale': 'ru_RU'},
        'sheets': [{'properties': {'sheetType': 'GRID',
                                    'sheetId': 0,
                                    'title': 'Заказы',
                                    'gridProperties': {'rowCount': len(no), 'columnCount': 10}}}]
    }).execute()

    results = service.spreadsheets().batchUpdate(spreadsheetId = spreadsheet['spreadsheetId'], body = {
        "requests": [
            # Задать ширину столбца A: 40 пикселей
            {
                "updateDimensionProperties": {
                    "range": {
                    "sheetId": 0,
                    "dimension": "COLUMNS",  # COLUMNS - потому что столбец
                    "startIndex": 0,         # Столбцы нумеруются с нуля
                    "endIndex": 1            # startIndex берётся включительно, endIndex - НЕ включительно,
                                             # т.е. размер будет применён к столбцам в диапазоне [0,1), т.е. только к столбцу A
                    },
                    "properties": {
                    "pixelSize": 40     # размер в пикселях
                    },
                    "fields": "pixelSize"  # нужно задать только pixelSize и не трогать другие параметры столбца
                }
            },

            # Задать ширину столбцов B и C: 100 пикселей
            {
                "updateDimensionProperties": {
                    "range": {
                    "sheetId": 0,
                    "dimension": "COLUMNS",
                    "startIndex": 1,
                    "endIndex": 3
                    },
                    "properties": {
                    "pixelSize": 100
                    },
                    "fields": "pixelSize"
                }
            },

            # Задать ширину столбца D: 500 пикселей
            {
                "updateDimensionProperties": {
                    "range": {
                    "sheetId": 0,
                    "dimension": "COLUMNS",
                    "startIndex": 3,
                    "endIndex": 4
                    },
                    "properties": {
                    "pixelSize": 500
                    },
                    "fields": "pixelSize"
                }
            },

            # Задать ширину столбца E: 140 пикселей
            {
                "updateDimensionProperties": {
                    "range": {
                    "sheetId": 0,
                    "dimension": "COLUMNS",
                    "startIndex": 4,
                    "endIndex": 5
                    },
                    "properties": {
                    "pixelSize": 80
                    },
                    "fields": "pixelSize"
                }
            },

            # Задать ширину столбца F: 140 пикселей
            {
                "updateDimensionProperties": {
                    "range": {
                    "sheetId": 0,
                    "dimension": "COLUMNS",
                    "startIndex": 5,
                    "endIndex": 6
                    },
                    "properties": {
                    "pixelSize": 140
                    },
                    "fields": "pixelSize"
                }
            },

            # Задать ширину столбца G: 80 пикселей
            {
                "updateDimensionProperties": {
                    "range": {
                    "sheetId": 0,
                    "dimension": "COLUMNS",
                    "startIndex": 6,
                    "endIndex": 7
                    },
                    "properties": {
                    "pixelSize": 80
                    },
                    "fields": "pixelSize"
                }
            },

            # Задать ширину столбца H: 80 пикселей
            {
                "updateDimensionProperties": {
                    "range": {
                    "sheetId": 0,
                    "dimension": "COLUMNS",
                    "startIndex": 7,
                    "endIndex": 8
                    },
                    "properties": {
                    "pixelSize": 80
                    },
                    "fields": "pixelSize"
                }
            },

            # Задать ширину столбца I: 140 пикселей
            {
                "updateDimensionProperties": {
                    "range": {
                    "sheetId": 0,
                    "dimension": "COLUMNS",
                    "startIndex": 8,
                    "endIndex": 9
                    },
                    "properties": {
                    "pixelSize": 140
                    },
                    "fields": "pixelSize"
                }
            },

            #Шапка таблицы
            {
                'repeatCell': {
                    'range': {
                        'sheetId': 0,
                        'startRowIndex': 0,
                        'endRowIndex': 1,
                        'startColumnIndex': 0,
                        'endColumnIndex': 9
                    },
                    'cell': {
                        'userEnteredFormat': {
                        'horizontalAlignment': 'CENTER',
                        "backgroundColor": {
                            "red": 0.8,
                            "green": 0.8,
                            "blue": 0.8,
                            "alpha": 1
                        },
                        'textFormat': {'bold': True}
                        }
                    },
                    'fields': 'userEnteredFormat'
                    }
            },
            {
            'setBasicFilter': {
                'filter': {
                    'range': {
                        'sheetId': 0,
                        'startRowIndex': 0,
                        'endRowIndex': 1,
                        'startColumnIndex': 0,
                        'endColumnIndex': 9
                    }
                }
            }}
            ]}).execute()

    results = service.spreadsheets().values().batchUpdate(spreadsheetId = spreadsheet['spreadsheetId'], body = {
        "valueInputOption": "USER_ENTERED",
        "data": [
            {"range": f"Заказы!A1:A{len(no)}",
            "majorDimension": "COLUMNS",
            "values": [no]},
            {"range": f"Заказы!B1:B{len(no)}",
            "majorDimension": "COLUMNS",
            "values": [ids]},
            {"range": f"Заказы!C1:C{len(no)}",
            "majorDimension": "COLUMNS",
            "values": [logins]},
            {"range": f"Заказы!D1:D{len(no)}",
            "majorDimension": "COLUMNS",
            "values": [links]},
            {"range": f"Заказы!E1:E{len(no)}",
            "majorDimension": "COLUMNS",
            "values": [contacts]},
            {"range": f"Заказы!F1:F{len(no)}",
            "majorDimension": "COLUMNS",
            "values": [position_name]},
            {"range": f"Заказы!G1:G{len(no)}",
            "majorDimension": "COLUMNS",
            "values": [prices]},
            {"range": f"Заказы!H1:H{len(no)}",
            "majorDimension": "COLUMNS",
            "values": [status]},
            {"range": f"Заказы!I1:I{len(no)}",
            "majorDimension": "COLUMNS",
            "values": [reg_date]}
        ]
    }).execute()

    driveService = apiclient.discovery.build('drive', 'v3', http = httpAuth)
    shareRes = driveService.permissions().create(
        fileId = spreadsheet['spreadsheetId'],
        body = {'type': 'anyone', 'role': 'writer'},  # доступ на чтение кому угодно
        fields = 'id'
    ).execute()

    return spreadsheet['spreadsheetUrl']

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
                links.append(order['links'])
                contacts.append(order['contacts'])
                position_name.append(order['position_name'])
                prices.append(order['price'])
                reg_date.append(order['date'])
                status.append(order['status'])
                logins.append(usr['user_name'])
                row_cnt += 1

        #Массив для создания таблицы
        sheet_title = usr['user_name']
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
        sheet_title = usr['user_name']
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

if __name__ == '__main__':
    print("Формируем отчет")
    print(create_sheet())
