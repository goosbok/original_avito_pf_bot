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
    create_auto_tasks_sheet()   → "Авто запуски"

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
TAB_MANUAL_TASKS = 'Manual задачи'
TAB_AUTO_TASKS = 'Авто запуски'


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


def _fmt_date_only(s):
    """`YYYY-MM-DD` → `dd.mm.yyyy`. Пусто/битый/None → ''."""
    if not s:
        return ''
    try:
        from datetime import date as _date
        d = _date.fromisoformat(str(s).strip())
        return d.strftime('%d.%m.%Y')
    except (ValueError, TypeError):
        return str(s)


def _views_per_day(position_name):
    """`дни/ПФ` → строка с количеством ПФ в день. Битое значение → ''."""
    parts = str(position_name or '').split('/')
    if len(parts) < 2:
        return ''
    value = parts[1].strip()
    return value if value.isdigit() else ''


def _fmt_msk_date(value):
    """Любой известный формат даты → 'dd.mm.yyyy' в московском времени.

    `started_at`/`deadline_at` хранятся в UTC (utils.dates.now_iso), а
    заказчик сверяется с дашбордом биза по московским суткам — срезать
    первые 10 символов ISO-строки нельзя, будет сдвиг на день у вечерних
    запусков. `format_display` уже делает конверсию в МСК и возвращает ''
    на пустом/битом вводе.
    """
    return format_display(value)[:10]


def _start_or_order_date(start_date, order_date):
    """Колонка «Старт» в выгрузках.

    Если у заказа явно проставлен `start_date` — используем его.
    Если NULL (юзер не выбрал и сработал дефолт «сегодня») — fallback'аем
    на дату создания заказа: для ISO-timestamp'ов берём первые 10 символов,
    для legacy `dd.mm.YYYY HH:MM` — формат и так подходит.
    """
    if start_date:
        return _fmt_date_only(start_date)
    if not order_date:
        return ''
    s = str(order_date).strip()
    return _fmt_date_only(s[:10])


def _write_tab(tab_title, sheet_id, columns, column_widths):
    """Очищает вкладку и записывает данные + форматирование.

    columns: список колонок, каждая — список вида [header, *values].
    column_widths: список троек (start_col_idx, end_col_idx_excl, pixel_width).

    Возвращает URL с #gid= указанной вкладки.
    """
    num_cols = len(columns)
    row_cnt = len(columns[0]) if columns else 1

    # 0) расширить сетку под текущее количество колонок/строк, если таб
    # существовал со старой схемой (например, до 47a9595 «Все заказы»
    # был 9-колоночным, а после стало 12 → запись в J падала с
    # «Range … exceeds grid limits. Max columns: 9»). Google sheets API
    # не растягивает grid автоматически — нужен явный updateSheetProperties.
    service.spreadsheets().batchUpdate(
        spreadsheetId=GSHEETS_TARGET_SHEET_ID,
        body={'requests': [{
            'updateSheetProperties': {
                'properties': {
                    'sheetId': sheet_id,
                    'gridProperties': {
                        'columnCount': max(num_cols, 1),
                        'rowCount': max(row_cnt, 1),
                    },
                },
                'fields': 'gridProperties.columnCount,gridProperties.rowCount',
            }
        }]},
    ).execute()

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
    """Полный отчёт по всем заказам, лист 'Все заказы'.

    Новая схема: одна строка на ссылку (JOIN orders+order_links).
    Колонки: №, id, username, Ссылка, Статус ссылки, Mode, Дедлайн,
    Контакты, Дней/ПФ, Цена, Статус заказа, Дата.
    """
    _init()
    _require_target()
    sheet_id = _get_or_create_tab(TAB_ALL_ORDERS)

    excludes = get_report_exclude()

    no = ['№']
    ids = ['id']
    logins = ['username']
    links = ['Ссылки']
    link_status = ['Статус ссылки']
    delivery_mode = ['Mode']
    deadline = ['Дедлайн']
    start = ['Старт']
    contacts = ['Контакты']
    position = ['Дней/ПФ']
    prices = ['Итого']
    status = ['Статус заказа']
    dates = ['Дата']

    from utils.sqlite3 import get_orders_with_links_batch
    DB_BATCH_SIZE = 1000
    db_offset = 0
    while True:
        batch = get_orders_with_links_batch(limit=DB_BATCH_SIZE, offset=db_offset)
        if not batch:
            break
        for row in batch:
            if str(row['user_id']) in excludes:
                continue
            no.append(row['order_id'])
            ids.append(row['user_id'])
            logins.append(row['user_name'])
            links.append(row['url'])
            link_status.append(row['link_status'] or '')
            delivery_mode.append(row['delivery_mode'] or '')
            deadline.append(format_display(row['deadline_at'])
                            if row['deadline_at'] else '')
            start.append(_start_or_order_date(row['start_date'],
                                              row['order_date']))
            contacts.append('Да' if row['contacts'] else 'Нет')
            position.append(row['position_name'])
            prices.append('')  # цена показывается только в первой строке заказа? Пока пусто
            status.append(_order_status_ru(row['order_status']))
            dates.append(format_display(row['order_date']))
        db_offset += DB_BATCH_SIZE

    column_widths = [
        (0, 1, 40),
        (1, 3, 100),
        (3, 4, 500),
        (4, 7, 120),
        (7, 8, 80),    # Дедлайн
        (8, 9, 80),    # Старт
        (9, 10, 100),  # Контакты
        (10, 11, 80),  # Дней/ПФ
        (11, 12, 140), # Итого
        (12, 13, 140), # Статус заказа + Дата
    ]
    url = _write_tab(
        TAB_ALL_ORDERS, sheet_id,
        [no, ids, logins, links, link_status, delivery_mode, deadline,
         start, contacts, position, prices, status, dates],
        column_widths,
    )
    logger.info("gsheets: 'Все заказы' updated, %d rows, url=%s",
                len(no) - 1, url)
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
    start = ['Старт']
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
            from services.order_links import list_links as _list_order_links
            order_links_rows = _list_order_links(int(order['increment']))
            cell_parts = []
            for ln in order_links_rows:
                label = ln['status']
                if ln['delivery_mode']:
                    label += f" · {ln['delivery_mode']}"
                if ln.get('deadline_at') and ln['status'] == 'in_work':
                    label += f" · до {ln['deadline_at'][:10]}"
                cell_parts.append(f"{ln['url']}  [{label}]")
            links.append("\n".join(cell_parts))
            contacts.append('Да' if order['contacts'] else 'Нет')
            position_name.append(order['position_name'])
            prices.append(order['price'])
            status.append(_order_status_ru(order['status']))
            start.append(_start_or_order_date(order.get('start_date'),
                                              order.get('date')))
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
        (8, 9, 80),    # Старт
        (9, 10, 140),  # Дата
    ]
    url = _write_tab(
        TAB_USER_ORDERS, sheet_id,
        [no, ids, logins, links, contacts, position_name, prices, status, start, reg_date],
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


def create_manual_tasks_sheet():
    """Выгрузить pending+manual ссылки с due-start в шит для админа."""
    _init()
    _require_target()
    sheet_id = _get_or_create_tab(TAB_MANUAL_TASKS)

    from utils.sqlite3 import get_pending_manual_links_due_today
    rows = get_pending_manual_links_due_today()

    no = ['№']
    ids = ['id']
    logins = ['username']
    links = ['Ссылка']
    link_status = ['Статус']
    delivery_mode = ['Mode']
    deadline = ['Дедлайн']
    contacts = ['Контакты']
    position = ['Дней/ПФ']
    start = ['Старт']
    dates = ['Дата заказа']

    for row in rows:
        no.append(row['order_id'])
        ids.append(row['user_id'])
        logins.append(row['user_name'])
        links.append(row['url'])
        link_status.append(row['link_status'] or '')
        delivery_mode.append(row['delivery_mode'] or '')
        deadline.append(row['deadline_at'] or '')
        contacts.append('Да' if row['contacts'] else 'Нет')
        position.append(row['position_name'])
        start.append(_start_or_order_date(row['start_date'], row['order_date']))
        dates.append(format_display(row['order_date']))

    column_widths = [
        (0, 1, 40),
        (1, 3, 100),
        (3, 4, 500),
        (4, 7, 120),
        (7, 8, 80),
        (8, 9, 100),
        (9, 10, 100),
        (10, 11, 140),
    ]
    url = _write_tab(
        TAB_MANUAL_TASKS, sheet_id,
        [no, ids, logins, links, link_status, delivery_mode, deadline,
         contacts, position, start, dates],
        column_widths,
    )
    logger.info("gsheets: '%s' updated, %d rows, url=%s",
                TAB_MANUAL_TASKS, len(no) - 1, url)
    return url


def create_auto_tasks_sheet(days=30):
    """Ссылки, отправленные в биза автоматом за последние `days` дней.

    Вкладка «Авто запуски» — рабочий инструмент заказчика для сверки с
    дашбордом исполнителя: видно, что улетело, с какой фразой и до какой
    даты крутим. Колонки 'Номер заказа' и 'Задача в биза' обе нужны —
    первое наш инкремент, второе id задачи на стороне исполнителя.
    """
    _init()
    _require_target()
    sheet_id = _get_or_create_tab(TAB_AUTO_TASKS)

    from utils.sqlite3 import get_auto_launched_links
    rows = get_auto_launched_links(days=days)

    search_links = ['Ссылка с поисковым запросом']
    ad_links = ['Ссылка на объявление']
    contacts = ['Контакты']
    views = ['ПФ в день']
    start = ['Старт']
    deadline = ['Крутим до']
    order_no = ['Номер заказа']
    biza_no = ['Задача в биза']
    client = ['ID клиента']
    link_status = ['Статус ссылки']

    for row in rows:
        search_links.append(row['search_link'] or '')
        ad_links.append(row['url'])
        contacts.append('Да' if row['contacts'] else 'Нет')
        views.append(_views_per_day(row['position_name']))
        start.append(_fmt_msk_date(row['started_at']))
        deadline.append(_fmt_msk_date(row['deadline_at']))
        order_no.append(row['order_id'])
        biza_no.append(row['external_id'] or '')
        client.append(row['user_id'])
        link_status.append(row['link_status'] or '')

    column_widths = [
        (0, 2, 500),    # обе ссылки
        (2, 4, 90),     # Контакты, ПФ в день
        (4, 6, 100),    # Старт, Крутим до
        (6, 8, 110),    # Номер заказа, Задача в биза
        (8, 9, 130),    # ID клиента
        (9, 10, 110),   # Статус ссылки
    ]
    url = _write_tab(
        TAB_AUTO_TASKS, sheet_id,
        [search_links, ad_links, contacts, views, start, deadline,
         order_no, biza_no, client, link_status],
        column_widths,
    )
    logger.info("gsheets: '%s' updated, %d rows, url=%s",
                TAB_AUTO_TASKS, len(search_links) - 1, url)
    return url


if __name__ == '__main__':
    print("Формируем отчет")
    print(create_sheet())
