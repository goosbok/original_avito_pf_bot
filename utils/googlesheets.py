import httplib2
import apiclient.discovery
from oauth2client.service_account import ServiceAccountCredentials
from utils.sqlite3 import all_users, all_orders, get_user, all_refills, get_report_exclude, get_orders_batch, get_orders_count
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
        d = datetime.now()
        
        # Размер пакета для обработки - КРИТИЧНО для памяти!
        DB_BATCH_SIZE = 1000  # Загружаем из БД пакетами по 1000 заказов
        SHEET_BATCH_SIZE = 500  # Отправляем в Google Sheets пакетами по 500 строк
        
        print("🚀 Создание таблицы...")
        
        # Создаем таблицу сразу
        spreadsheet = service.spreadsheets().create(body = {
            'properties': {'title': f"Заказы-{d.strftime('%d-%m-%Y-%H-%M-%S')}", 'locale': 'ru_RU'},
            'sheets': [{'properties': {'sheetType': 'GRID', 'sheetId': 0, 'title': 'Заказы', 'gridProperties': {'rowCount': 200000, 'columnCount': 9}}}]
        }).execute()

        spreadsheet_id = spreadsheet['spreadsheetId']
        del spreadsheet
        
        print(f"📊 Таблица создана: {spreadsheet_id}")
        
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
        
        # Форматирование
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": format_requests}).execute()
        del format_requests
        
        print("✅ Форматирование завершено")
        
        # Сначала добавляем заголовки
        headers = [['№'], ['id'], ['username'], ['Ссылки'], ['Контакты'], ['Дней/ПФ'], ['Итого'], ['Статус'], ['Дата']]
        service.spreadsheets().values().batchUpdate(spreadsheetId=spreadsheet_id, body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": "Заказы!A1", "values": [headers[0]]},
                {"range": "Заказы!B1", "values": [headers[1]]},
                {"range": "Заказы!C1", "values": [headers[2]]},
                {"range": "Заказы!D1", "values": [headers[3]]},
                {"range": "Заказы!E1", "values": [headers[4]]},
                {"range": "Заказы!F1", "values": [headers[5]]},
                {"range": "Заказы!G1", "values": [headers[6]]},
                {"range": "Заказы!H1", "values": [headers[7]]},
                {"range": "Заказы!I1", "values": [headers[8]]}
            ]
        }).execute()
        del headers
        
        print("📝 Заголовки добавлены, начинаем обработку данных...")
        
        # Получаем список исключений один раз
        excludes = get_report_exclude()
        
        # Пакет для накопления данных перед отправкой в Sheets
        batch_data = {
            'no': [], 'ids': [], 'logins': [], 'links': [],
            'contacts': [], 'position_name': [], 'prices': [],
            'reg_date': [], 'status': []
        }
        
        current_row = 2  # Начинаем со второй строки (первая - заголовки)
        processed_rows = 0
        db_offset = 0
        
        # Загружаем и обрабатываем заказы пакетами из БД
        while True:
            # Загружаем пакет заказов из БД
            orders_batch = get_orders_batch(limit=DB_BATCH_SIZE, offset=db_offset)
            
            if not orders_batch:
                break  # Больше заказов нет
            
            print(f"📦 Загружен пакет заказов {db_offset}-{db_offset + len(orders_batch)} из БД")
            
            # Обрабатываем каждый заказ в пакете
            for order in orders_batch:
                if str(order['user_id']) not in excludes:
                    links_array = order['links'].split()
                    for link in links_array:
                        batch_data['logins'].append(order['user_name'])
                        batch_data['links'].append(link.replace("'", "").replace("[", "").replace("]", ""))
                        batch_data['no'].append(order['increment'])
                        batch_data['ids'].append(order['user_id'])
                        batch_data['contacts'].append('Да' if order['contacts'] else 'Нет')
                        batch_data['position_name'].append(order['position_name'])
                        batch_data['prices'].append(order['price'])
                        batch_data['reg_date'].append(order['date'])
                        
                        if order['status'] == 'Posted':
                            batch_data['status'].append('Размещён')
                        elif order['status'] == 'Completed':
                            batch_data['status'].append('Выполнен')
                        else:
                            batch_data['status'].append(order['status'])
                        
                        processed_rows += 1
                        
                        # Когда накопили SHEET_BATCH_SIZE строк - отправляем в Sheets
                        if len(batch_data['no']) >= SHEET_BATCH_SIZE:
                            end_row = current_row + len(batch_data['no']) - 1
                            service.spreadsheets().values().batchUpdate(spreadsheetId=spreadsheet_id, body={
                                "valueInputOption": "USER_ENTERED",
                                "data": [
                                    {"range": f"Заказы!A{current_row}:A{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['no']]},
                                    {"range": f"Заказы!B{current_row}:B{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['ids']]},
                                    {"range": f"Заказы!C{current_row}:C{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['logins']]},
                                    {"range": f"Заказы!D{current_row}:D{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['links']]},
                                    {"range": f"Заказы!E{current_row}:E{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['contacts']]},
                                    {"range": f"Заказы!F{current_row}:F{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['position_name']]},
                                    {"range": f"Заказы!G{current_row}:G{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['prices']]},
                                    {"range": f"Заказы!H{current_row}:H{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['status']]},
                                    {"range": f"Заказы!I{current_row}:I{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['reg_date']]}
                                ]
                            }).execute()
                            
                            print(f"✅ Отправлено {processed_rows} строк в таблицу")
                            current_row = end_row + 1
                            
                            # Очищаем пакет
                            batch_data = {
                                'no': [], 'ids': [], 'logins': [], 'links': [],
                                'contacts': [], 'position_name': [], 'prices': [],
                                'reg_date': [], 'status': []
                            }
                    
                    del links_array
            
            # Очищаем пакет заказов из памяти
            del orders_batch
            db_offset += DB_BATCH_SIZE
        
        # Отправляем остаток данных
        if batch_data['no']:
            end_row = current_row + len(batch_data['no']) - 1
            service.spreadsheets().values().batchUpdate(spreadsheetId=spreadsheet_id, body={
                "valueInputOption": "USER_ENTERED",
                "data": [
                    {"range": f"Заказы!A{current_row}:A{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['no']]},
                    {"range": f"Заказы!B{current_row}:B{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['ids']]},
                    {"range": f"Заказы!C{current_row}:C{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['logins']]},
                    {"range": f"Заказы!D{current_row}:D{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['links']]},
                    {"range": f"Заказы!E{current_row}:E{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['contacts']]},
                    {"range": f"Заказы!F{current_row}:F{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['position_name']]},
                    {"range": f"Заказы!G{current_row}:G{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['prices']]},
                    {"range": f"Заказы!H{current_row}:H{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['status']]},
                    {"range": f"Заказы!I{current_row}:I{end_row}", "majorDimension": "COLUMNS", "values": [batch_data['reg_date']]}
                ]
            }).execute()
            print(f"✅ Отправлен финальный пакет: {processed_rows} строк (всего)")
        
        # Очищаем все данные
        del batch_data, excludes
        
        print("🔓 Настройка публичного доступа...")
        
        # Публичный доступ
        driveService = apiclient.discovery.build('drive', 'v3', http = httpAuth)
        driveService.permissions().create(
            fileId=spreadsheet_id,
            body={'type': 'anyone', 'role': 'writer'},
            fields='id'
        ).execute()
        
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        print(f"🎉 Отчет готов: {spreadsheet_url}")
        print(f"📊 Обработано строк: {processed_rows}")
        
        return spreadsheet_url
        
    except Exception as e:
        print(f'❌ Error in create_sheet: {e}')
        import traceback
        traceback.print_exc()
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
