from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from utils.sqlite3 import get_user, get_string, get_setting, get_all_qna_avito, get_admins, get_price
from design import *
from utils.other_functions import str2bool

months_names = {'1': 'Январь', '2': 'Февраль', '3': 'Март', '4': 'Апрель',
                '5': 'Май', '6': 'Июнь', '7': 'Июль', '8': 'Август',
                '9': 'Сентябрь', '10': 'Октябрь', '11': 'Ноябрь', '12': 'Декабрь'}

price_google = get_price('price_google')
price_yandex = get_price('price_yandex')
price_vk = get_price('price_vk')
price_flamp = get_price('price_flamp')
price_2gis = get_price('price_2gis')
price_avito = get_price('price_avito')

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
    )
    # keyboard.add(
    #     InlineKeyboardButton(
    #         text=get_string('btn_reviews'),
    #         callback_data="reviews"
    #     )
    # ),
    # keyboard.add(
    #     InlineKeyboardButton(
    #         text=get_string('btn_seo_boost'),
    #         callback_data="seo_boost"
    #     )
    # )
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_profile'),
            callback_data='user:profile'
        )
    ),
    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_channel'),
            url=get_setting('channel_link')
        )
    )
    keyboard.row(
        InlineKeyboardButton(
            text=get_string('btn_rules'),
            callback_data='info:rules'
        ),
        InlineKeyboardButton(
            text=get_string('btn_support'),
            callback_data='info:support'
        )
    ),
    keyboard.add(

        InlineKeyboardButton(
            text=get_string('btn_qna'),
            callback_data='info:qna'
        ),
        InlineKeyboardButton(
            text=get_string('btn_promocodes'),
            callback_data='user:promo'
        )
    )
    return keyboard

###############################################################################################
#############################             ПФ АВИТО             ################################
###############################################################################################

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
            text=get_string('btn_main_menu'),
            callback_data='menu'
        )
    )
    return keyboard

###############################################################################################
#############################              ПРОФИЛЬ             ################################
###############################################################################################

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
            text=get_string('btn_main_menu'),
            callback_data='menu'
        )
    )
    return keyboard

###############################################################################################
#############################               НАЗАД              ################################
###############################################################################################

def menu_btn_kb():
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_main_menu'),
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

###############################################################################################
#############################              ДА/НЕТ              ################################
###############################################################################################

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

    keyboard.row(
        InlineKeyboardButton(
            text=f"Оплатить {price} ₽",
            callback_data='refill_balance'
        ),
        InlineKeyboardButton(
            text=get_string('btn_main_menu'),
            callback_data='menu'
        )
    )
    return keyboard

def yookassa_kb(price, pay_url):
    keyboard = InlineKeyboardMarkup()

    keyboard.row(
        InlineKeyboardButton(
            text=f"Оплатить {price} ₽",
            url=pay_url
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
#############################        Заказы по индексу         ################################
###############################################################################################

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

###############################################################################################
#############################           ОТЗЫВЫ              ################################
###############################################################################################

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


def payment_error_kb():
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_support'),
            callback_data='info:support'
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            text=get_string('btn_main_menu'),
            callback_data='menu'
        )
    )
    return keyboard
