import httplib2
import apiclient.discovery
from oauth2client.service_account import ServiceAccountCredentials
from utils.dates import format_display
from utils.sqlite3 import all_users, all_orders, get_user, all_refills, get_report_exclude, get_orders_batch
from data.config import services, GSHEETS_OWNER_EMAIL
from datetime import *
import gc
import logging
import os
import csv
import tempfile
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

CREDENTIALS_FILE = 'utils/dev-trees-414317-e16633571d94.json'

logger = logging.getLogger(__name__)

credentials = None
httpAuth = None
service = None


def _init():
    global credentials, httpAuth, service
    if service is not None:
        return
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        CREDENTIALS_FILE,
        ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'],
    )
    httpAuth = credentials.authorize(httplib2.Http())
    service = apiclient.discovery.build('sheets', 'v4', http=httpAuth)


def _transfer_ownership(drive_service, file_id):
    """Передаёт ownership созданного файла на GSHEETS_OWNER_EMAIL, чтобы файл
    не занимал квоту сервисного аккаунта.

    Для SA → consumer-gmail Google требует pending-ownership: новый владелец
    получает письмо/уведомление и однократно подтверждает приём в Drive UI.
    После подтверждения файл уезжает в его My Drive и SA-квота освобождается.

    Если GSHEETS_OWNER_EMAIL не задан — ничего не делает (старое поведение).
    Любая ошибка логируется и не валит экспорт: даже если transfer не прошёл,
    файл и публичная ссылка остаются рабочими, просто не освобождается квота.
    """
    if not GSHEETS_OWNER_EMAIL:
        return
    try:
        drive_service.permissions().create(
            fileId=file_id,
            body={
                'type': 'user',
                'role': 'writer',
                'emailAddress': GSHEETS_OWNER_EMAIL,
                'pendingOwner': True,
            },
            sendNotificationEmail=True,
            fields='id',
        ).execute()
        logger.info(
            "gsheets: pending ownership of %s set to %s — accept in Drive UI",
            file_id, GSHEETS_OWNER_EMAIL,
        )
    except HttpError as e:
        logger.warning(
            "gsheets: failed to set pending owner for %s on %s: %s",
            GSHEETS_OWNER_EMAIL, file_id, e,
        )

def get_user_str(user):
    if user['user_name']:
        return user['user_name']
    else:
        return str(user['id'])

def create_sheet():
    _init()
    csv_file = None
    try:
        d = datetime.now()
        DB_BATCH_SIZE = 1000  # Загружаем из БД пакетами
        
        print("🚀 Создание CSV-отчета...")
        
        # Создаем временный CSV файл
        csv_file = tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8', suffix='.csv', delete=False)
        csv_writer = csv.writer(csv_file)
        
        # Пишем заголовки
        csv_writer.writerow(['№', 'id', 'username', 'Ссылки', 'Контакты', 'Дней/ПФ', 'Итого', 'Статус', 'Дата'])
        
        # Получаем список исключений
        excludes = get_report_exclude()
        
        processed_rows = 0
        db_offset = 0
        
        print("📝 Обработка данных из БД...")
        
        # Загружаем и пишем в CSV пакетами
        while True:
            orders_batch = get_orders_batch(limit=DB_BATCH_SIZE, offset=db_offset)
            
            if not orders_batch:
                break
            
            print(f"📦 Обработка заказов {db_offset}-{db_offset + len(orders_batch)}")
            
            for order in orders_batch:
                if str(order['user_id']) not in excludes:
                    links_array = order['links'].split()
                    
                    for link in links_array:
                        # Пишем строку сразу в CSV (не накапливаем в памяти!)
                        csv_writer.writerow([
                            order['increment'],
                            order['user_id'],
                            order['user_name'],
                            link.replace("'", "").replace("[", "").replace("]", ""),
                            'Да' if order['contacts'] else 'Нет',
                            order['position_name'],
                            order['price'],
                            'Размещён' if order['status'] == 'Posted' else ('Выполнен' if order['status'] == 'Completed' else order['status']),
                            format_display(order['date'])
                        ])
                        processed_rows += 1
            
            # Очищаем память после каждого пакета
            del orders_batch
            gc.collect()
            db_offset += DB_BATCH_SIZE
        
        csv_file.close()
        csv_filename = csv_file.name
        
        print(f"✅ CSV создан: {processed_rows} строк, размер: {os.path.getsize(csv_filename) / 1024 / 1024:.1f} MB")
        print("📤 Загрузка в Google Drive...")
        
        # Загружаем CSV в Google Drive и конвертируем в Sheets
        driveService = apiclient.discovery.build('drive', 'v3', http=httpAuth)
        
        file_metadata = {
            'name': f"Заказы-{d.strftime('%d-%m-%Y-%H-%M-%S')}",
            'mimeType': 'application/vnd.google-apps.spreadsheet'  # Автоконвертация в Sheets
        }
        
        media = MediaFileUpload(
            csv_filename,
            mimetype='text/csv',
            resumable=True
        )
        
        spreadsheet = driveService.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        spreadsheet_id = spreadsheet['id']
        
        # Удаляем временный CSV
        os.unlink(csv_filename)
        
        print(f"📊 Таблица создана: {spreadsheet_id}")
        print("🎨 Применение форматирования...")
        
        # Получаем реальный sheetId (при загрузке CSV Google может создать не 0)
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_id = sheet_metadata['sheets'][0]['properties']['sheetId']
        
        print(f"📋 Sheet ID: {sheet_id}")
        
        # Применяем форматирование (ширина столбцов, заголовки, фильтры)
        format_requests = [
            # Ширина столбцов
            {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 40}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 3}, "properties": {"pixelSize": 100}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4}, "properties": {"pixelSize": 500}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 5, "endIndex": 6}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 6, "endIndex": 7}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 7, "endIndex": 8}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 8, "endIndex": 9}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
            # Форматирование заголовка (серый фон, жирный текст, центрирование)
            {'repeatCell': {
                'range': {'sheetId': sheet_id, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 9}, 
                'cell': {'userEnteredFormat': {
                    'horizontalAlignment': 'CENTER',
                    'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8, 'alpha': 1},
                    'textFormat': {'bold': True}
                }}, 
                'fields': 'userEnteredFormat'
            }},
            # Фильтр на заголовок
            {'setBasicFilter': {'filter': {'range': {'sheetId': sheet_id, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 9}}}}
        ]
        
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": format_requests}
        ).execute()
        
        print("✅ Форматирование применено")
        print("🔓 Настройка публичного доступа...")
        
        # Публичный доступ
        driveService.permissions().create(
            fileId=spreadsheet_id,
            body={'type': 'anyone', 'role': 'writer'},
            fields='id'
        ).execute()

        # Передача ownership на личный аккаунт (освобождает квоту SA после accept)
        _transfer_ownership(driveService, spreadsheet_id)

        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        print(f"🎉 Отчет готов: {spreadsheet_url}")
        print(f"📊 Всего строк: {processed_rows}")
        
        return spreadsheet_url
        
    except Exception as e:
        print(f'❌ Ошибка при создании отчета: {e}')
        import traceback
        traceback.print_exc()
        
        # Удаляем временный файл при ошибке
        if csv_file and hasattr(csv_file, 'name') and os.path.exists(csv_file.name):
            try:
                os.unlink(csv_file.name)
            except:
                pass
        
        raise

def _resolve_user_scope(user_id):
    """Returns (magic_user, [user_id, *referals]) — все id как int, дедуп с сохранением порядка."""
    magic_user = get_user(id=user_id)
    raw_ids = [user_id]
    if magic_user and magic_user.get('referals'):
        raw_ids += [x for x in magic_user['referals'].split(',') if x.strip()]
    seen = set()
    scope = []
    for rid in raw_ids:
        try:
            iid = int(rid)
        except (TypeError, ValueError):
            continue
        if iid in seen:
            continue
        seen.add(iid)
        scope.append(iid)
    return magic_user, scope


def create_orders_report(user_id):
    _init()
    orders = all_orders()
    d = datetime.now()
    sheet_name = f"Заказы-{d.strftime('%d-%m-%Y-%H-%M-%S')}"

    _, scope_ids = _resolve_user_scope(user_id)
    users_in_scope = {uid: get_user(id=uid) for uid in scope_ids}

    no = ['№']
    ids = ['id']
    logins = ['username']
    links = ['Ссылки']
    contacts = ['Контакты']
    position_name = ['Тариф']
    prices = ['Итого']
    status = ['Статус']
    reg_date = ['Дата']

    scope_set = set(scope_ids)
    for order in orders:
        try:
            oid = int(order['user_id'])
        except (TypeError, ValueError):
            continue
        if oid not in scope_set:
            continue
        usr = users_in_scope.get(oid)
        no.append(order['increment'])
        ids.append(order['user_id'])
        logins.append(get_user_str(usr) if usr else str(oid))
        links.append(order['links'].replace("'", "").replace(", ", "\n").replace("\n\n", "\n"))
        contacts.append('Да' if order['contacts'] else 'Нет')
        position_name.append(order['position_name'])
        prices.append(order['price'])
        status.append('Размещён' if order['status'] == 'Posted' else ('Выполнен' if order['status'] == 'Completed' else order['status']))
        reg_date.append(format_display(order['date']))

    row_cnt = len(no)
    sheet_title = 'Заказы'

    sheets_array = [{'properties': {
        'sheetType': 'GRID', 'sheetId': 0, 'title': sheet_title,
        'gridProperties': {'rowCount': max(row_cnt, 1), 'columnCount': 9}
    }}]

    formated_sheets_array = [
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 40}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 3}, "properties": {"pixelSize": 100}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4}, "properties": {"pixelSize": 500}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 5, "endIndex": 6}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 6, "endIndex": 7}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 7, "endIndex": 8}, "properties": {"pixelSize": 80}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 8, "endIndex": 9}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
        {'repeatCell': {'range': {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 9}, 'cell': {'userEnteredFormat': {'horizontalAlignment': 'CENTER', "backgroundColor": {"red": 0.8, "green": 0.8, "blue": 0.8, "alpha": 1}, 'textFormat': {'bold': True}}}, 'fields': 'userEnteredFormat'}},
        {'setBasicFilter': {'filter': {'range': {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 9}}}},
    ]

    data_array = [
        {"range": f"{sheet_title}!A1:A{row_cnt}", "majorDimension": "COLUMNS", "values": [no]},
        {"range": f"{sheet_title}!B1:B{row_cnt}", "majorDimension": "COLUMNS", "values": [ids]},
        {"range": f"{sheet_title}!C1:C{row_cnt}", "majorDimension": "COLUMNS", "values": [logins]},
        {"range": f"{sheet_title}!D1:D{row_cnt}", "majorDimension": "COLUMNS", "values": [links]},
        {"range": f"{sheet_title}!E1:E{row_cnt}", "majorDimension": "COLUMNS", "values": [contacts]},
        {"range": f"{sheet_title}!F1:F{row_cnt}", "majorDimension": "COLUMNS", "values": [position_name]},
        {"range": f"{sheet_title}!G1:G{row_cnt}", "majorDimension": "COLUMNS", "values": [prices]},
        {"range": f"{sheet_title}!H1:H{row_cnt}", "majorDimension": "COLUMNS", "values": [status]},
        {"range": f"{sheet_title}!I1:I{row_cnt}", "majorDimension": "COLUMNS", "values": [reg_date]},
    ]

    spreadsheet = service.spreadsheets().create(body={
        'properties': {'title': sheet_name, 'locale': 'ru_RU'},
        'sheets': sheets_array,
    }).execute()

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet['spreadsheetId'],
        body={"requests": formated_sheets_array},
    ).execute()

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet['spreadsheetId'],
        body={"valueInputOption": "USER_ENTERED", "data": data_array},
    ).execute()

    driveService = apiclient.discovery.build('drive', 'v3', http=httpAuth)
    driveService.permissions().create(
        fileId=spreadsheet['spreadsheetId'],
        body={'type': 'anyone', 'role': 'writer'},
        fields='id',
    ).execute()
    _transfer_ownership(driveService, spreadsheet['spreadsheetId'])

    return spreadsheet['spreadsheetUrl']

def create_refills_report(user_id):
    _init()
    refills = all_refills()
    d = datetime.now()
    sheet_name = f"Оплаты-{d.strftime('%d-%m-%Y-%H-%M-%S')}"

    _, scope_ids = _resolve_user_scope(user_id)
    users_in_scope = {uid: get_user(id=uid) for uid in scope_ids}

    no = ['№']
    ids = ['id']
    logins = ['username']
    amount = ['Оплата']
    amount_date = ['Дата']

    scope_set = set(scope_ids)
    for refill in refills:
        try:
            rid = int(refill['user_id'])
        except (TypeError, ValueError):
            continue
        if rid not in scope_set:
            continue
        usr = users_in_scope.get(rid)
        no.append(refill['increment'])
        ids.append(refill['user_id'])
        logins.append(get_user_str(usr) if usr else str(rid))
        amount.append(refill['amount'])
        amount_date.append(format_display(refill['date']))

    row_cnt = len(no)
    sheet_title = 'Оплаты'

    sheets_array = [{'properties': {
        'sheetType': 'GRID', 'sheetId': 0, 'title': sheet_title,
        'gridProperties': {'rowCount': max(row_cnt, 1), 'columnCount': 5}
    }}]

    formated_sheets_array = [
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 40}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 4}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
        {'repeatCell': {'range': {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 5}, 'cell': {'userEnteredFormat': {'horizontalAlignment': 'CENTER', "backgroundColor": {"red": 0.8, "green": 0.8, "blue": 0.8, "alpha": 1}, 'textFormat': {'bold': True}}}, 'fields': 'userEnteredFormat'}},
        {'setBasicFilter': {'filter': {'range': {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 5}}}},
    ]

    data_array = [
        {"range": f"{sheet_title}!A1:A{row_cnt}", "majorDimension": "COLUMNS", "values": [no]},
        {"range": f"{sheet_title}!B1:B{row_cnt}", "majorDimension": "COLUMNS", "values": [ids]},
        {"range": f"{sheet_title}!C1:C{row_cnt}", "majorDimension": "COLUMNS", "values": [logins]},
        {"range": f"{sheet_title}!D1:D{row_cnt}", "majorDimension": "COLUMNS", "values": [amount]},
        {"range": f"{sheet_title}!E1:E{row_cnt}", "majorDimension": "COLUMNS", "values": [amount_date]},
    ]

    spreadsheet = service.spreadsheets().create(body={
        'properties': {'title': sheet_name, 'locale': 'ru_RU'},
        'sheets': sheets_array,
    }).execute()

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet['spreadsheetId'],
        body={"requests": formated_sheets_array},
    ).execute()

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet['spreadsheetId'],
        body={"valueInputOption": "USER_ENTERED", "data": data_array},
    ).execute()

    driveService = apiclient.discovery.build('drive', 'v3', http=httpAuth)
    driveService.permissions().create(
        fileId=spreadsheet['spreadsheetId'],
        body={'type': 'anyone', 'role': 'writer'},
        fields='id',
    ).execute()
    _transfer_ownership(driveService, spreadsheet['spreadsheetId'])

    return spreadsheet['spreadsheetUrl']

def create_reviews_report(orders):
    _init()
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
            reg_date.append(format_display(order['date']))
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
    _transfer_ownership(driveService, spreadsheet['spreadsheetId'])

    return spreadsheet['spreadsheetUrl']

if __name__ == '__main__':
    print("Формируем отчет")
    print(create_sheet())
