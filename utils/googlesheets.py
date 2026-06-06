"""Экспорты в Google Sheets.

Все 4 функции пишут в ОДНУ заранее созданную таблицу, ID которой задан
переменной окружения GSHEETS_TARGET_SHEET_ID. Никаких files.create() —
у сервисного аккаунта Drive-квота 0 байт, поэтому создавать новые файлы
он не может. Юзер создаёт таблицу руками один раз, шарит её service-account
email'у с правом Editor, и бот переписывает содержимое нужных вкладок.

Вкладки, в которые пишет каждая функция:
    create_sheet()              → "Все заказы"
    create_orders_report()      → "Заказы по юзеру"
    create_refills_report()     → "Пополнения по юзеру"

Если какая-то вкладка отсутствует — она создаётся (addSheet).
"""

import httplib2
import logging
import apiclient.discovery
from oauth2client.service_account import ServiceAccountCredentials
from utils.dates import format_display
from utils.sqlite3 import all_users, get_user, all_refills, get_report_exclude, get_orders_batch
from data.config import services, GSHEETS_TARGET_SHEET_ID
from datetime import datetime

CREDENTIALS_FILE = 'utils/google-creds.json'

logger = logging.getLogger(__name__)

credentials = None
httpAuth = None
service = None

TAB_ALL_ORDERS = 'Все заказы'
TAB_USER_ORDERS = 'Заказы по юзеру'
TAB_USER_REFILLS = 'Пополнения по юзеру'
TAB_REVIEWS = 'Отзывы'


def _init():
    global credentials, httpAuth, service
    if service is not None:
        return
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        CREDENTIALS_FILE,
        ['https://www.googleapis.com/auth/spreadsheets'],
    )
    httpAuth = credentials.authorize(httplib2.Http())
    service = apiclient.discovery.build('sheets', 'v4', http=httpAuth)


def _require_target():
    if not GSHEETS_TARGET_SHEET_ID:
        raise RuntimeError(
            "GSHEETS_TARGET_SHEET_ID is not set. Create a Google spreadsheet, "
            "share it as Editor with the service-account email from "
            f"{CREDENTIALS_FILE}, and put the spreadsheet ID into .env."
        )


def _get_or_create_tab(tab_title):
    """Returns sheetId of the tab; creates it if missing."""
    meta = service.spreadsheets().get(spreadsheetId=GSHEETS_TARGET_SHEET_ID).execute()
    for s in meta['sheets']:
        if s['properties']['title'] == tab_title:
            return s['properties']['sheetId']
    resp = service.spreadsheets().batchUpdate(
        spreadsheetId=GSHEETS_TARGET_SHEET_ID,
        body={'requests': [{'addSheet': {'properties': {'title': tab_title}}}]},
    ).execute()
    return resp['replies'][0]['addSheet']['properties']['sheetId']


def _column_letter(idx):
    """0 → A, 25 → Z, 26 → AA …"""
    result = ''
    n = idx
    while True:
        result = chr(ord('A') + n % 26) + result
        n = n // 26 - 1
        if n < 0:
            break
    return result


def _write_tab(tab_title, sheet_id, columns, column_widths):
    """Очищает вкладку и записывает данные + форматирование.

    columns: список колонок, каждая — список вида [header, *values].
    column_widths: список троек (start_col_idx, end_col_idx_excl, pixel_width).

    Возвращает URL с #gid= указанной вкладки.
    """
    num_cols = len(columns)
    row_cnt = len(columns[0]) if columns else 1

    # 1) очистить старое содержимое
    service.spreadsheets().values().clear(
        spreadsheetId=GSHEETS_TARGET_SHEET_ID,
        range=f"'{tab_title}'",
        body={},
    ).execute()

    # 2) записать данные построчно (majorDimension=COLUMNS, чтобы передать колонками)
    data = []
    for col_idx, col_values in enumerate(columns):
        letter = _column_letter(col_idx)
        data.append({
            'range': f"'{tab_title}'!{letter}1:{letter}{row_cnt}",
            'majorDimension': 'COLUMNS',
            'values': [col_values],
        })
    if data:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=GSHEETS_TARGET_SHEET_ID,
            body={'valueInputOption': 'USER_ENTERED', 'data': data},
        ).execute()

    # 3) форматирование (ширина колонок, заголовок, фильтр)
    fmt_requests = []
    for (start, end, width) in column_widths:
        fmt_requests.append({
            'updateDimensionProperties': {
                'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS',
                          'startIndex': start, 'endIndex': end},
                'properties': {'pixelSize': width},
                'fields': 'pixelSize',
            }
        })
    fmt_requests.append({
        'repeatCell': {
            'range': {'sheetId': sheet_id, 'startRowIndex': 0, 'endRowIndex': 1,
                      'startColumnIndex': 0, 'endColumnIndex': num_cols},
            'cell': {'userEnteredFormat': {
                'horizontalAlignment': 'CENTER',
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8, 'alpha': 1},
                'textFormat': {'bold': True},
            }},
            'fields': 'userEnteredFormat',
        }
    })
    # Старый фильтр сбросить (иначе setBasicFilter упадёт)
    fmt_requests.append({'clearBasicFilter': {'sheetId': sheet_id}})
    fmt_requests.append({
        'setBasicFilter': {'filter': {
            'range': {'sheetId': sheet_id, 'startRowIndex': 0, 'endRowIndex': 1,
                      'startColumnIndex': 0, 'endColumnIndex': num_cols},
        }}
    })
    service.spreadsheets().batchUpdate(
        spreadsheetId=GSHEETS_TARGET_SHEET_ID,
        body={'requests': fmt_requests},
    ).execute()

    return f"https://docs.google.com/spreadsheets/d/{GSHEETS_TARGET_SHEET_ID}/edit#gid={sheet_id}"


_ORDER_STATUS_RU = {
    'unpaid': 'Ожидает оплаты',
    'paid': 'В работе',
    'done': 'Выполнен',
    'failed': 'Ошибка накрутки',
    'payment_failed': 'Не оплачен',
    'cancelled': 'Отменён',
}


def _order_status_ru(status):
    return _ORDER_STATUS_RU.get(status, status)


def get_user_str(user):
    if user and user['user_name']:
        return user['user_name']
    if user:
        return str(user['id'])
    return ''


def _resolve_user_scope(user_id):
    """(magic_user, [user_id, *referals]) — int с дедупом."""
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


def create_sheet():
    """Полный отчёт по всем заказам, лист 'Все заказы'."""
    _init()
    _require_target()
    sheet_id = _get_or_create_tab(TAB_ALL_ORDERS)

    excludes = get_report_exclude()

    no = ['№']
    ids = ['id']
    logins = ['username']
    links = ['Ссылки']
    contacts = ['Контакты']
    position = ['Дней/ПФ']
    prices = ['Итого']
    status = ['Статус']
    dates = ['Дата']

    DB_BATCH_SIZE = 1000
    db_offset = 0
    while True:
        batch = get_orders_batch(limit=DB_BATCH_SIZE, offset=db_offset)
        if not batch:
            break
        logger.info("gsheets: processing orders %d-%d", db_offset, db_offset + len(batch))
        for order in batch:
            if str(order['user_id']) in excludes:
                continue
            for link in order['links'].split():
                no.append(order['increment'])
                ids.append(order['user_id'])
                logins.append(order['user_name'])
                links.append(link.replace("'", "").replace("[", "").replace("]", ""))
                contacts.append('Да' if order['contacts'] else 'Нет')
                position.append(order['position_name'])
                prices.append(order['price'])
                status.append(_order_status_ru(order['status']))
                dates.append(format_display(order['date']))
        db_offset += DB_BATCH_SIZE

    column_widths = [
        (0, 1, 40),
        (1, 3, 100),
        (3, 4, 500),
        (4, 5, 80),
        (5, 6, 140),
        (6, 7, 80),
        (7, 8, 80),
        (8, 9, 140),
    ]
    url = _write_tab(
        TAB_ALL_ORDERS, sheet_id,
        [no, ids, logins, links, contacts, position, prices, status, dates],
        column_widths,
    )
    logger.info("gsheets: 'Все заказы' updated, %d rows, url=%s", len(no) - 1, url)
    return url


def create_orders_report(user_id):
    """Заказы юзера + его рефералов, лист 'Заказы по юзеру'."""
    _init()
    _require_target()
    sheet_id = _get_or_create_tab(TAB_USER_ORDERS)

    _, scope_ids = _resolve_user_scope(user_id)
    users_in_scope = {uid: get_user(id=uid) for uid in scope_ids}
    scope_set = set(scope_ids)

    no = ['№']
    ids = ['id']
    logins = ['username']
    links = ['Ссылки']
    contacts = ['Контакты']
    position_name = ['Тариф']
    prices = ['Итого']
    status = ['Статус']
    reg_date = ['Дата']

    DB_BATCH_SIZE = 1000
    db_offset = 0
    while True:
        batch = get_orders_batch(limit=DB_BATCH_SIZE, offset=db_offset)
        if not batch:
            break
        for order in batch:
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
            status.append(_order_status_ru(order['status']))
            reg_date.append(format_display(order['date']))
        db_offset += DB_BATCH_SIZE

    column_widths = [
        (0, 1, 40),
        (1, 3, 100),
        (3, 4, 500),
        (4, 5, 80),
        (5, 6, 140),
        (6, 7, 80),
        (7, 8, 80),
        (8, 9, 140),
    ]
    url = _write_tab(
        TAB_USER_ORDERS, sheet_id,
        [no, ids, logins, links, contacts, position_name, prices, status, reg_date],
        column_widths,
    )
    logger.info("gsheets: '%s' updated, %d rows, scope=%s", TAB_USER_ORDERS, len(no) - 1, scope_ids)
    return url


def create_refills_report(user_id):
    """Пополнения юзера + его рефералов, лист 'Пополнения по юзеру'."""
    _init()
    _require_target()
    sheet_id = _get_or_create_tab(TAB_USER_REFILLS)

    _, scope_ids = _resolve_user_scope(user_id)
    users_in_scope = {uid: get_user(id=uid) for uid in scope_ids}
    scope_set = set(scope_ids)

    no = ['№']
    ids = ['id']
    logins = ['username']
    amount = ['Оплата']
    amount_date = ['Дата']

    for refill in all_refills():
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

    column_widths = [
        (0, 1, 40),
        (1, 4, 140),
        (4, 5, 140),
    ]
    url = _write_tab(
        TAB_USER_REFILLS, sheet_id,
        [no, ids, logins, amount, amount_date],
        column_widths,
    )
    logger.info("gsheets: '%s' updated, %d rows, scope=%s", TAB_USER_REFILLS, len(no) - 1, scope_ids)
    return url


if __name__ == '__main__':
    print("Формируем отчет")
    print(create_sheet())
