from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from utils.sqlite3 import get_user, get_string_from_base, get_setting, get_all_qna_avito, get_admins
from design import *
from data.config import price_google, price_yandex, price_vk, price_flamp, price_2gis, price_avito
from utils.other_functions import str2bool

months_names = {'1': 'Январь', '2': 'Февраль', '3': 'Март', '4': 'Апрель',
                '5': 'Май', '6': 'Июнь', '7': 'Июль', '8': 'Август',
                '9': 'Сентябрь', '10': 'Октябрь', '11': 'Ноябрь', '12': 'Декабрь'}

def get_string(param):
    str_value = get_string_from_base(param)
    if str_value:
        return str_value['value']
    else:
        return globals().get(param)

def get_username(user_id):
    user = get_user(id=user_id)
    if user['user_name']:
        return user['user_name']
    else:
        return user['id']

###############################################################################################
#############################       Меню пользователя          ################################
###############################################################################################
def get_menu_kb():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_how_to_start'),
            callback_data='info:start'
        )
    ),
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_avito'),
            callback_data='tarifs:pf'
        )
    ),
    """keyboard.add(
        InlineKeyboardButton(
            text=f"🚀 Заказать ПФ Яндекс",
            callback_data='yandex_pf'
        )
    ),"""
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_reviews'),
            callback_data="reviews"
        )
    ),
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_seo_boost'),
            callback_data="seo_boost"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_profile'),
            callback_data='user:profile'
        )
    ),
    """keyboard.add(
        InlineKeyboardButton(
            text=f"❗️Получи 1.000₽ баланса за отзыв❗️",
            callback_data='review_bonus'
        )
    ),"""
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_channel'),
            url=get_setting('channel_link')
        )
    )
    keyboard.row(
        InlineKeyboardButton(
            text=rules,
            callback_data='info:rules'
        ),
        InlineKeyboardButton(
            text=support,
            callback_data='info:support'
        )
    ),
    keyboard.add(

        InlineKeyboardButton(
            text=qna,
            callback_data='info:qna'
        ),
        InlineKeyboardButton(
            text=promocodes,
            callback_data='user:promo'
        )
    )

    return keyboard

###############################################################################################
#############################           SEO BOOST              ################################
###############################################################################################
def seo_boost_kb():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_seo_howto'),
            callback_data='seo_howto'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_seo_why'),
            callback_data='seo_why'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_seo_result'),
            callback_data='seo_result'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_seo_order'),
            callback_data='seo_order'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_main_menu'),
            callback_data='menu'
        )
    )
    return keyboard

#Клавиатура с месяцами для SEO
def seo_months(buttons_per_row=6):
    keyboard = InlineKeyboardMarkup()
    buttons = []
    for i in range(1,13):
        button = InlineKeyboardButton(
            text=str(i),
            callback_data=f"seo:{str(i)}"
        )
        buttons.append(button)

        # Если количество кнопок достигло buttons_per_row, добавляем ряд в клавиатуру
        if len(buttons) == buttons_per_row:
            keyboard.row(*buttons)
            buttons = []

    # Добавляем оставшиеся кнопки, если их число не делится на buttons_per_row
    if buttons:
        keyboard.row(*buttons)

    keyboard.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data='seo_boost'
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='menu'
        )
    )

    return keyboard

#Подтверждение заказа SEO
def seo_order_confirm(param):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton(
            text=get_string('btn_yes'),
            callback_data=f'seo_yes:{param}'
        ),
        InlineKeyboardButton(
            text=get_string('btn_no'),
            callback_data='seo_boost'
        ),
        InlineKeyboardButton(
            text=get_string('btn_main_menu'),
            callback_data='menu'
        )
    )
    return keyboard

###############################################################################################
#############################           QnA AVITO              ################################
###############################################################################################
def qna_avito_kb():
    keyboard = InlineKeyboardMarkup()
    all_qna = get_all_qna_avito()
    buttons = []
    for qna in all_qna:
        button = InlineKeyboardButton(
            text=qna['description'],
            callback_data=qna['parametr']
        )
        keyboard.add(button)

    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_avito_cases'),
            url=config.channel_link
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_main_menu'),
            callback_data='menu'
        )
    )
    return keyboard

def tarifs_kb():
    keyboard = InlineKeyboardMarkup()


    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_main_menu'),
            callback_data='menu'
        )
    )
    return keyboard

def pf_kb():
    keyboard = InlineKeyboardMarkup()

    keyboard.row(
        InlineKeyboardButton(
            text=f"День",
            callback_data='pf:1'
        ),
        InlineKeyboardButton(
            text="Неделя",
            callback_data='pf:7'
        ),
        InlineKeyboardButton(
            text="Месяц",
            callback_data='pf:30'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="✍️ Ввести нужное количество",
            callback_data='pf:enter-period'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="Главное меню",
            callback_data='menu'
        )
    )
    return keyboard

def pf_period_kb(param):
    keyboard = InlineKeyboardMarkup()

    keyboard.row(
        InlineKeyboardButton(
            text="5",
            callback_data=f"pf:{param}-5"
        ),
        InlineKeyboardButton(
            text="10",
            callback_data=f"pf:{param}-10"
        ),
        InlineKeyboardButton(
            text="20",
            callback_data=f"pf:{param}-20"
        ),
        InlineKeyboardButton(
            text="30",
            callback_data=f"pf:{param}-30"
        ),
        InlineKeyboardButton(
            text="50",
            callback_data=f"pf:{param}-50"
        )
    )
    keyboard.row(
        InlineKeyboardButton(
            text="100",
            callback_data=f"pf:{param}-100"
        ),
        InlineKeyboardButton(
            text="150",
            callback_data=f"pf:{param}-150"
        ),
        InlineKeyboardButton(
            text="500",
            callback_data=f"pf:{param}-500"
        ),
        InlineKeyboardButton(
            text="1000",
            callback_data=f"pf:{param}-1000"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="✍️ Ввести нужное количество ПФ",
            callback_data='pf:enter-pf'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="🧊 Главное меню",
            callback_data='menu'
        )
    )
    return keyboard

def profile_kb():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(
            text=refill_balance,
            callback_data='profile:ref_bal'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=list_orders,
            callback_data='profile:listord'
        )
    )
    keyboard.row(
        InlineKeyboardButton(
            text=get_string('btn_all_completed'),
            callback_data='user_show_all:completed'
        ),
        InlineKeyboardButton(
            text=get_string('btn_all_posted'),
            callback_data='user_show_all:posted'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_channel'),
            url=get_setting('channel_link')
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=main_menu,
            callback_data='menu'
        )
    )
    return keyboard

def menu_btn_kb():
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            text=main_menu,
            callback_data='menu'
        )
    )
    return keyboard


def yes_no_kb():
    keyboard = InlineKeyboardMarkup()
    STR_YES = get_string('btn_yes')
    STR_NO = get_string('btn_no')
    keyboard.row(
        InlineKeyboardButton(
            text=STR_YES,
            callback_data='refil:confirm'
        ),
        InlineKeyboardButton(
            text=STR_NO,
            callback_data='menu'
        )
    )
    return keyboard

def yes_no_contact_kb():
    keyboard = InlineKeyboardMarkup()
    STR_YES = get_string('btn_yes')
    STR_NO = get_string('btn_no')
    keyboard.row(
        InlineKeyboardButton(
            text=STR_YES,
            callback_data='contact:True'
        ),
        InlineKeyboardButton(
            text=STR_NO,
            callback_data='contact:False'
        )
    )
    return keyboard

def yes_no_order_kb():
    keyboard = InlineKeyboardMarkup()
    STR_YES = get_string('btn_yes')
    STR_NO = get_string('btn_no')
    keyboard.row(
        InlineKeyboardButton(
            text=STR_YES,
            callback_data='order_confirm'
        ),
        InlineKeyboardButton(
            text=STR_NO,
            callback_data='menu'
        )
    )
    return keyboard

def pay_kb(price):
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            text=f"Оплатить {price} RUB",
            callback_data='refill_balance'
            #pay=True
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="Главное меню",
            callback_data='menu'
        )
    )
    return keyboard

def yookassa_kb(price, pay_url):
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            text=f"Оплатить {price} RUB",
            url=pay_url
        )
    )
    return keyboard

def admin():
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton(
                text="🔎 Заказ",
                callback_data='search_order'
            ),
            InlineKeyboardButton(
                text="💳 Баланс",
                callback_data="user_balance"
            )
        )
        keyboard.row(
            InlineKeyboardButton(
                text="⭐️ Отзывы",
                callback_data='reviews_man'
            ),
            InlineKeyboardButton(
                text="📖 Заказы",
                callback_data='orders_man'
            )
        )
        keyboard.row(
            InlineKeyboardButton(
                text="⚙️ Настройки",
                callback_data='settings'
            ),
            InlineKeyboardButton(
                text="🔮 Промокоды",
                callback_data='promo_codes'
            )
        )
        keyboard.row(
            InlineKeyboardButton(
                text="🐹 Юзеры",
                callback_data='users_man'
            ),
            InlineKeyboardButton(
                text="📝 Сообщения",
                callback_data='messages_menu'
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="🔗 Рефералки",
                callback_data='magic'
            )
        )

        keyboard.add(
            InlineKeyboardButton(
                text="📖 Таблица по заказам",
                callback_data='gsheets'
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="💰 Финансовый отчет",
                callback_data='money_by_year'
            )
        )
        return keyboard
def setup_kb():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton(
            text="⚙️ Интерфейс",
            callback_data='interface_setup'
        ),
        InlineKeyboardButton(
            text="⚙️ Переменные",
            callback_data='variables_setup'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="💰 Касса/цены",
            callback_data='price_setup'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="👑 Админы",
            callback_data='admins_setup'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )
    return keyboard

def setup_variables_kb():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton(
            text="🆕 Строка",
            callback_data='str_variable_add'
        ),
        InlineKeyboardButton(
            text="👁‍🗨 Строку",
            callback_data='str_variable_view'
        )
    )
    keyboard.row(
        InlineKeyboardButton(
            text="🆕 Переменная",
            callback_data='variable_add'
        ),
        InlineKeyboardButton(
            text="👁‍🗨 Переменную",
            callback_data='variable_view'
        )
    )
    keyboard.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="settings"
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )
    return keyboard

def setup_strings_kb():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(
            text="✏️ Редактор строк",
            callback_data='str_visual_edit'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="✏️ Редактор кнопок",
            callback_data='btn_visual_edit'
        )
    )
    """
    keyboard.row(
        InlineKeyboardButton(
            text="✏️ Создать кнопку",
            callback_data='btn_add'
        ),
        InlineKeyboardButton(
            text="✏️ Посмотреть кнопку",
            callback_data='btn_view'
        )
    )
    """
    keyboard.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="settings"
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )
    return keyboard

def str_visual_edit_kb(index, str_cnt, page='interface_setup'):
    keyboard = InlineKeyboardMarkup()
    if index == 0:
        keyboard.row(
            InlineKeyboardButton(
                text="✏️",
                callback_data=f"edit:{index}"
            ),
            InlineKeyboardButton(
                text=f"{index+2}/{str_cnt} ▶️",
                callback_data=f"caption:{index+1}"
            )
        )
    elif index != 0 and index < str_cnt - 1:
        keyboard.row(
            InlineKeyboardButton(
                text=f"◀️ {index}/{str_cnt}",
                callback_data=f"caption:{index-1}"
            ),
            InlineKeyboardButton(
                text="✏️",
                callback_data=f"edit:{index}"
            ),
            InlineKeyboardButton(
                text=f"{index+2}/{str_cnt} ▶️",
                callback_data=f"caption:{index+1}"
            ),
        )
    else:
        keyboard.row(
            InlineKeyboardButton(
                text=f"◀️ {index}/{str_cnt}",
                callback_data=f"caption:{index-1}"
            ),
            InlineKeyboardButton(
                text="✏️",
                callback_data=f"edit:{index}"
            )
        )

    keyboard.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=page
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )
    return keyboard

def btn_visual_edit_kb(index, str_cnt, page='interface_setup'):
    keyboard = InlineKeyboardMarkup()
    if index == 0:
        keyboard.row(
            InlineKeyboardButton(
                text="✏️",
                callback_data=f"btn_edit:{index}"
            ),
            InlineKeyboardButton(
                text=f"{index+2}/{str_cnt} ▶️",
                callback_data=f"btn:{index+1}"
            )
        )
    elif index != 0 and index < str_cnt - 1:
        keyboard.row(
            InlineKeyboardButton(
                text=f"◀️ {index}/{str_cnt}",
                callback_data=f"btn:{index-1}"
            ),
            InlineKeyboardButton(
                text="✏️",
                callback_data=f"btn_edit:{index}"
            ),
            InlineKeyboardButton(
                text=f"{index+2}/{str_cnt} ▶️",
                callback_data=f"btn:{index+1}"
            ),
        )
    else:
        keyboard.row(
            InlineKeyboardButton(
                text=f"◀️ {index}/{str_cnt}",
                callback_data=f"btn:{index-1}"
            ),
            InlineKeyboardButton(
                text="✏️",
                callback_data=f"btn_edit:{index}"
            )
        )

    keyboard.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=page
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )
    return keyboard

def payment_setup_kb(param):
    keyboard = InlineKeyboardMarkup()
    pay_work = not str2bool(param)
    if pay_work:
       button = InlineKeyboardButton(
           text="❎Отключить",
           callback_data=f"payment_toggle:{param}"
       )
       keyboard.add(button)
    else:
       button = InlineKeyboardButton(
           text="✅Включить",
           callback_data=f"payment_toggle:{param}"
       )
       keyboard.add(button)

    keyboard.add(
        InlineKeyboardButton(
            text="💰 Минимальный платеж",
            callback_data='min_amount'
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            text="💰 Прайс \"ПФ Авито\"",
            callback_data='price_edit:avito_pf'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="💰 Прайс \"Накрутка отзывов Авито\"",
            callback_data='price_edit:avito'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="💰 Прайс \"Накрутка отзывов Google\"",
            callback_data='price_edit:google'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="💰 Прайс \"Накрутка отзывов Яндекс\"",
            callback_data='price_edit:yandex'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="💰 Прайс \"Накрутка отзывов ВКонтакте\"",
            callback_data='price_edit:vk'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="💰 Прайс \"Накрутка отзывов Flamp\"",
            callback_data='price_edit:flamp'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="💰 Прайс \"Накрутка отзывов 2ГИС\"",
            callback_data='price_edit:2gis'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="💰 Прайс \"SEO Boost\"",
            callback_data='price_edit:seo'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="💰 Прайс \"Удаление отзыва Авито\"",
            callback_data='price_edit:avito_del_review'
        )
    )
    keyboard.row(
       InlineKeyboardButton(
           text="⬅️ Назад",
           callback_data="settings"
       ),
       InlineKeyboardButton(
           text=main_menu,
           callback_data='to_admin_menu'
       )
    )
    return keyboard

def edit_price_kb(service, price, buttons_per_row=3):
    keyboard = InlineKeyboardMarkup()

    # Сортируем словарь по числовым ключам
    sorted_price = {key: price[key] for key in sorted(price.keys(), key=int)}

    buttons = []
    for k,v in sorted_price.items():
        button = InlineKeyboardButton(
            text=f"{k} отз.:{v} ₽",
            callback_data=f"edit_price-{service}-{k}:{v}"
        )
        buttons.append(button)

        # Если количество кнопок достигло buttons_per_row, добавляем ряд в клавиатуру
        if len(buttons) == buttons_per_row:
            keyboard.row(*buttons)
            buttons = []

    # Добавляем оставшиеся кнопки, если их число не делится на buttons_per_row
    if buttons:
        keyboard.row(*buttons)

    keyboard.row(
       InlineKeyboardButton(
           text="⬅️ Назад",
           callback_data="price_setup"
       ),
       InlineKeyboardButton(
           text=main_menu,
           callback_data='to_admin_menu'
       )
    )

    return keyboard

def setup_admins():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton(
            text="➕ Добавить",
            callback_data='admin:add'
        ),
        InlineKeyboardButton(
            text="➖ Удалить",
            callback_data='admin:del'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="📧 Исключить из рассылки",
            callback_data='spam_exclude'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="📝 Исключить из отчетов",
            callback_data='report_exclude'
        )
    )
    keyboard.row(
       InlineKeyboardButton(
           text="⬅️ Назад",
           callback_data="settings"
       ),
       InlineKeyboardButton(
           text=main_menu,
           callback_data='to_admin_menu'
       )
    )
    return keyboard

def del_admin_kb(buttons_per_row=2, show_nick=True, show_id=False):
    keyboard = InlineKeyboardMarkup()
    admins = get_admins()
    buttons = []
    for admin in admins:
        user = get_user(id=admin)
        if user['user_name']:
            user_name = user['user_name']
        else:
            user_name = 'Нет имени'
        button = InlineKeyboardButton(
            text=f"❎{user_name}",
            callback_data=f"del_admin:{admin}"
        )
        buttons.append(button)

        # Если количество кнопок достигло buttons_per_row, добавляем ряд в клавиатуру
        if len(buttons) == buttons_per_row:
            keyboard.row(*buttons)
            buttons = []

    # Добавляем оставшиеся кнопки, если их число не делится на buttons_per_row
    if buttons:
        keyboard.row(*buttons)

    keyboard.row(
       InlineKeyboardButton(
           text="⬅️ Назад",
           callback_data="admins_setup"
       ),
       InlineKeyboardButton(
           text=main_menu,
           callback_data='to_admin_menu'
       )
    )
    return keyboard

def magic_kb():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(
            text="🔗 Сгенерировать",
            callback_data='magic:generate'
        )
    ),
    keyboard.add(
        InlineKeyboardButton(
            text="📖 Отчет по пользователю",
            callback_data='magic:report'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="📖 Таблица по заказам",
            callback_data='magic:orders'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="📖 Таблица по финансам",
            callback_data='magic:refills'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="⬅️ Обратно в меню",
            callback_data='to_admin_menu'
        )
    )
    return keyboard
def gsheets_url(URL):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton(
            text="Перейти",
            url=URL
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )

    return keyboard

def messages_kb():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(
            text="🐹 Рассылка",
            callback_data='send_spam'
        )
    )
    keyboard.add(
        InlineKeyboardButton(
                text="🤖 Написать адину",
                callback_data='admin_send'
            )
        )
    keyboard.add(
        InlineKeyboardButton(
            text="🤖 сообщение кодеру",
            callback_data="coder_send"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )
    return keyboard

def users_man_kb():
        keyboard = InlineKeyboardMarkup()

        keyboard.row(
            InlineKeyboardButton(
                text="🐹 Количество",
                callback_data='users_len'
            ),
            InlineKeyboardButton(
                text="🔎 Поиск",
                callback_data='magic:report'
            )
        )
        keyboard.row(
            InlineKeyboardButton(
                text="🐹 IDы",
                callback_data='users_ids'
            ),
            InlineKeyboardButton(
                text="❌ Удалить",
                callback_data="del_user"
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="💎 показать VIPов",
                callback_data="get_vip"
            )
        )
        keyboard.row(
            InlineKeyboardButton(
                text="💎 уст. VIP",
                callback_data="set_vip"
            ),
            InlineKeyboardButton(
                text="💎 снять VIP",
                callback_data="delete_vip"
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="💰 Финансы пользователя",
                callback_data="refills:user"
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="💳 Управление балансом",
                callback_data="user_balance"
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text=main_menu,
                callback_data='to_admin_menu'
            )
        )
        return keyboard

def promo_codes_kb():
        keyboard = InlineKeyboardMarkup()

        keyboard.row(
            InlineKeyboardButton(
                text="🔮 Создать",
                callback_data='add_promo'
            ),
            InlineKeyboardButton(
                text="🚫 Удалить",
                callback_data='deactiv_promo'
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="🔮Показать промокоды",
                callback_data='show_promo'
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="🔥Свой промокод🔥",
                callback_data='add_custom_promo'
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="🚫Удалить активированные",
                callback_data='del_activated_promo'
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text=main_menu,
                callback_data='to_admin_menu'
            )
        )
        return keyboard

def orders_kb():
        keyboard = InlineKeyboardMarkup()

        keyboard.row(
            InlineKeyboardButton(
                text="🔎 Найти",
                callback_data='search_order'
            ),
            InlineKeyboardButton(
                text="🐹 По юзеру",
                callback_data='user_all_orders'
            )
        )
        keyboard.row(
            InlineKeyboardButton(
                text="👌🏻 Выполненные",
                callback_data="orders_completed"
            ),
            InlineKeyboardButton(
                text="✍🏻 Размещенные",
                callback_data="orders_posted"
            )
        )
        keyboard.row(
            InlineKeyboardButton(
                text="✅ Выполнить",
                callback_data="gotovoebat"
            ),
            InlineKeyboardButton(
                text="❎ Удалить",
                callback_data="del_order"
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text=main_menu,
                callback_data='to_admin_menu'
            )
        )
        return keyboard

def admin_back_kb(param:None):
    keyboard = InlineKeyboardMarkup()

    if param:
        keyboard.row(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=param
            ),
            InlineKeyboardButton(
                text=main_menu,
                callback_data='to_admin_menu'
            )
        )
    else:
        keyboard.add(
            InlineKeyboardButton(
                text=main_menu,
                callback_data='to_admin_menu'
            )
        )

    return keyboard

def show_admin_order_by_index(index, orders_cnt, page='orders_man', all_orders=True):
    if orders_cnt > 100:
        all_orders = False
    keyboard = InlineKeyboardMarkup()
    if orders_cnt:
        if all_orders==True:
            keyboard.add(
                InlineKeyboardButton(
                    text="📖Все заказы",
                    callback_data="admin_show_all_orders"
                )
            )
        if orders_cnt !=1:
            keyboard.add(
                InlineKeyboardButton(
                    text=f"Заказ #1",
                    callback_data=f"order:0"
                )
            )
            if index == 0:
                keyboard.add(
                    InlineKeyboardButton(
                        text=f"Следующий ({index+2}/{orders_cnt}) ▶️",
                        callback_data=f"order:{index+1}"
                    )
                )
            elif index != 0 and index < orders_cnt - 1:
                keyboard.row(
                    InlineKeyboardButton(
                        text=f"◀️ ({index}/{orders_cnt})",
                        callback_data=f"order:{index-1}"
                    ),
                    InlineKeyboardButton(
                        text=f"({index+2}/{orders_cnt}) ▶️",
                        callback_data=f"order:{index+1}"
                    ),
                )
            else:
                keyboard.add(
                    InlineKeyboardButton(
                        text=f"◀️ Предыдущий ({index}/{orders_cnt})",
                        callback_data=f"order:{index-1}"
                    )
                )
            keyboard.add(
                InlineKeyboardButton(
                    text=f"Заказ #{orders_cnt}",
                    callback_data=f"order:{orders_cnt-1}"
                )
            )
    else:
        pass

    keyboard.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=page
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )
    return keyboard

def show_user_order_by_index(index, orders_cnt):
    keyboard = InlineKeyboardMarkup()
    if orders_cnt:
        keyboard.add(
            InlineKeyboardButton(
                text="🔁 Повторить заказ",
                callback_data=f"repeat:{index}"
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="📖Все заказы",
                callback_data="user_show_all:orders"
            )
        )
        if orders_cnt !=1:
            keyboard.add(
                InlineKeyboardButton(
                    text=f"Заказ #1",
                    callback_data=f"ordr:0"
                )
            )
            if index == 0:
                keyboard.add(
                    InlineKeyboardButton(
                        text=f"Следующий ({index+2}/{orders_cnt}) ▶️",
                        callback_data=f"ordr:{index+1}"
                    )
                )
            elif index != 0 and index < orders_cnt - 1:
                keyboard.row(
                    InlineKeyboardButton(
                        text=f"◀️ Предыдущий ({index}/{orders_cnt})",
                        callback_data=f"ordr:{index-1}"
                    ),
                    InlineKeyboardButton(
                        text=f"Следующий ({index+2}/{orders_cnt}) ▶️",
                        callback_data=f"ordr:{index+1}"
                    ),
                )
            else:
                keyboard.add(
                    InlineKeyboardButton(
                        text=f"◀️ Предыдущий ({index}/{orders_cnt})",
                        callback_data=f"ordr:{index-1}"
                    )
                )

            keyboard.add(
                InlineKeyboardButton(
                    text=f"Заказ #{orders_cnt}",
                    callback_data=f"ordr:{orders_cnt-1}"
                )
            )
    else:
        pass

    keyboard.row(
        InlineKeyboardButton(
            text=profile,
            callback_data='user:profile'
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='menu'
        )
    )
    return keyboard

def user_back_kb(param):
    keyboard = InlineKeyboardMarkup()

    keyboard.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=param
        ),
        InlineKeyboardButton(
            text=get_string('btn_main_menu'),
            callback_data='menu'
        )
    )
    return keyboard

def magic_general_kb(page='users_man', show_referals=False, show_orders=False, show_refills=False):
    keyboard = InlineKeyboardMarkup()

    if show_referals:
        keyboard.add(
            InlineKeyboardButton(
                text="🐹 Рефералы",
                callback_data = "magic:referals"
            )
        )

    if show_orders:
        keyboard.add(
            InlineKeyboardButton(
                text="📖 Заказы пользователя",
                callback_data='user_all_orders'
            )
        )

        keyboard.add(
            InlineKeyboardButton(
                text="📖 Таблица по заказам",
                callback_data='magic:orders'
            )
        )

    if show_refills:
        keyboard.add(
            InlineKeyboardButton(
                text="💰 Финансы пользователя",
                callback_data="refills:user"
                #callback_data="maic:all_refills"
            )
        )

        keyboard.add(
            InlineKeyboardButton(
                text="📖 Таблица по финансам",
                callback_data='magic:refills'
            )
        )

    keyboard.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=page
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )

    return keyboard

def magic_referals_kb(page='users_man', show_orders=False, show_refills=False):
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            text="🐹 Отчет",
            callback_data = "magic:report"
        )
    )

    if show_orders:
        keyboard.add(
            InlineKeyboardButton(
                text="📖 Заказы пользователя",
                callback_data='user_all_orders'
            )
        )

        keyboard.add(
            InlineKeyboardButton(
                text="📖 Таблица по заказам",
                callback_data='magic:orders'
            )
        )

    if show_refills:
        keyboard.add(
            InlineKeyboardButton(
                text="📖 Таблица по финансам",
                callback_data='magic:refills'
            )
        )

    keyboard.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=page
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )

    return keyboard

def refill_ref_kb(user_id, kb_page_dict={}, page=0, buttons_per_row=2, back='users_man'):
    keyboard = InlineKeyboardMarkup()
    buttons = []
    if int(page) > len(kb_page_dict):
        page = len(page_dict)
    if kb_page_dict:
        for usr_id in kb_page_dict[str(page)]:
            user_str = get_username(usr_id)
            button = InlineKeyboardButton(
                text=f"🐹 {user_str}",
                callback_data=f"refills:{usr_id}:{page}"
            )
            buttons.append(button)

            # Если количество кнопок достигло buttons_per_row, добавляем ряд в клавиатуру
            if len(buttons) == buttons_per_row:
                keyboard.row(*buttons)
                buttons = []

    # Добавляем оставшиеся кнопки, если их число не делится на buttons_per_row
    if buttons:
        keyboard.row(*buttons)

    if int(page) == 0:
        keyboard.add(
            InlineKeyboardButton(
                text="Страница 2▶️",
                callback_data=f"refills:{user_id}:{int(page) + 1}"
            )
        )
    elif int(page) > 0 and int(page) < len(kb_page_dict) - 1:
        keyboard.row(
            InlineKeyboardButton(
                text=f"◀️Страница {page}",
                callback_data=f"refills:{user_id}:{int(page) - 1}"
            ),
            InlineKeyboardButton(
                text=f"Страница {int(page) + 2}▶️",
                callback_data=f"refills:{user_id}:{int(page) + 1}"
            )
        )
    elif int(page) == len(kb_page_dict) - 1:
        keyboard.add(
            InlineKeyboardButton(
                text=f"◀️Страница {int(page)}",
                callback_data=f"refills:{user_id}:{int(page) - 1}"
            )
        )

    keyboard.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=back
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )

    return keyboard

def spam_send_kb():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton(
            text='✅Да',
            callback_data='send:yes'
        ),
        InlineKeyboardButton(
            text='❎Нет',
            callback_data='send:no'
        )
    )

    return keyboard

def money_by_years(years_array, buttons_per_row=4):
    keyboard = InlineKeyboardMarkup()
    buttons = []
    for year in years_array:
        button = InlineKeyboardButton(
            text=str(year),
            callback_data=f"year:{year}"
        )
        buttons.append(button)

        # Если количество кнопок достигло buttons_per_row, добавляем ряд в клавиатуру
        if len(buttons) == buttons_per_row:
            keyboard.row(*buttons)
            buttons = []

    # Добавляем оставшиеся кнопки, если их число не делится на buttons_per_row
    if buttons:
        keyboard.row(*buttons)

    keyboard.add(
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )

    return keyboard

def money_by_month(months_array, buttons_per_row=3):
    keyboard = InlineKeyboardMarkup()
    buttons = []
    for month in months_array:
        button = InlineKeyboardButton(
            text=months_names[str(month)],
            callback_data=f"month:{month}"
        )
        buttons.append(button)

        # Если количество кнопок достигло buttons_per_row, добавляем ряд в клавиатуру
        if len(buttons) == buttons_per_row:
            keyboard.row(*buttons)
            buttons = []

    # Добавляем оставшиеся кнопки, если их число не делится на buttons_per_row
    if buttons:
        keyboard.row(*buttons)

    keyboard.add(
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )

    return keyboard

def reviews_kb():
    """
    ВКонтакте, Яндекс , Авито , 2гис, фламп, Гугл
    """
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton(
            text="🚀 ВКонтакте",
            callback_data="reviews:vk"
        ),
        InlineKeyboardButton(
            text="🚀 Яндекс",
            callback_data="reviews:yandex"
        ),
        #InlineKeyboardButton(
        #    text="🚀 Авито",
        #    callback_data="reviews:avito"
        #),
    ),
    keyboard.row(
        InlineKeyboardButton(
            text="🚀 2ГИС",
            callback_data="reviews:2gis"
        ),
        InlineKeyboardButton(
            text="🚀 Фламп",
            callback_data="reviews:flamp"
        ),
        InlineKeyboardButton(
            text="🚀 Google",
            callback_data="reviews:google"
        )
    ),
    keyboard.add(
        InlineKeyboardButton(
            text=main_menu,
            callback_data="menu"
        )
    )

    return keyboard

def reviews_count(service, buttons_per_row=5):
    if service == "vk":
        price = price_vk
    elif service == "yandex":
        price = price_yandex
    elif service == "avito":
        price = price_avito
    elif service == "2gis":
        price = price_2gis
    elif service == "flamp":
        price = price_flamp
    elif service == "google":
        price = price_google

    keyboard = InlineKeyboardMarkup()
    buttons = []

    # Преобразование ключей к int и сортировка
    sorted_keys = sorted(price.keys(), key=int)

    for key in sorted_keys:
        button = InlineKeyboardButton(
            text=str(key),
            callback_data=f"rev_price:{str(key)}"
        )
        buttons.append(button)

        if len(buttons) == buttons_per_row:
            keyboard.row(*buttons)
            buttons = []

    # Добавляем оставшиеся кнопки, если их число не делится на buttons_per_row
    if buttons:
        keyboard.row(*buttons)

    if service == "avito":
        keyboard.add(
            InlineKeyboardButton(
                text="Удаление негативного отзыва",
                callback_data="avito_del_review"
            )
        )

    keyboard.add(
        InlineKeyboardButton(
            text=main_menu,
            callback_data='menu'
        )
    )

    return keyboard

def yes_no_reviews():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton(
            text="✅ Да",
            callback_data="rev_confirm"
        ),
        InlineKeyboardButton(
            text="❎ Нет",
            callback_data="menu"
        ),
    )
    return keyboard

def reviews_man_kb():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton(
            text="🔎 по юзеру",
            callback_data="rev_user_search"
        ),
        InlineKeyboardButton(
            text="✅ Выполнить",
            callback_data="reviw_close"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="📖 Таблица по отзывам",
            callback_data="reviews_sheet"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="🐹 Заказы на удаление отзыва",
            callback_data="del_rev_user_search"
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            text="✅ Выполнить заказ",
            callback_data="del_review_close"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )
    return keyboard

def show_admin_review_by_index(index, orders_cnt, page='reviews_man'):
    keyboard = InlineKeyboardMarkup()
    if orders_cnt:
        keyboard.add(
            InlineKeyboardButton(
                text="📖Все заказы",
                callback_data="admin_show_all_reviews"
            )
        )
        if orders_cnt != 1:
            keyboard.add(
                InlineKeyboardButton(
                    text=f"Заказ #1",
                    callback_data=f"review:0"
                )
            )
            if index == 0:
                keyboard.add(
                    InlineKeyboardButton(
                        text=f"Следующий ({index+2}/{orders_cnt}) ▶️",
                        callback_data=f"review:{index+1}"
                    )
                )
            elif index != 0 and index < orders_cnt - 1:
                keyboard.row(
                    InlineKeyboardButton(
                        text=f"◀️ Предыдущий ({index}/{orders_cnt})",
                        callback_data=f"review:{index-1}"
                    ),
                    InlineKeyboardButton(
                        text=f"Следующий ({index+2}/{orders_cnt}) ▶️",
                        callback_data=f"review:{index+1}"
                    ),
                )
            else:
                keyboard.add(
                    InlineKeyboardButton(
                        text=f"◀️ Предыдущий ({index}/{orders_cnt})",
                        callback_data=f"review:{index-1}"
                    )
                )
            keyboard.add(
                InlineKeyboardButton(
                    text=f"Заказ #{orders_cnt}",
                    callback_data=f"review:{orders_cnt-1}"
                )
            )
    else:
        pass

    keyboard.add(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=page
        ),
        InlineKeyboardButton(
            text=main_menu,
            callback_data='to_admin_menu'
        )
    )
    return keyboard
