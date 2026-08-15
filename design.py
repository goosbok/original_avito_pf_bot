from data import config
from data.config import *
from utils.sqlite3 import get_user
from utils.dates import format_display
from utils.order_status import order_status_label
from utils.other_functions import get_user_string_without_first_name, get_days_suffix, format_decimal
start_text = "👋 Приветствую, <b>{}</b> ! Выберите что хотите сделать."
welcome_bonus_line = "\n\n🎁 Вам начислен приветственный бонус {} ₽"

profile = "🪪 Личный кабинет"
tarifs = "💰 Тарифы"
promocodes = "🔮 Промокоды"
qna = "📲 FAQ / Кейсы"
btn_how_to_start = "🕐 Как начать работу"
support = "🧑‍💻 Тех поддержка"
in_devel = "⚠️ Данная функция в разработке!"
btn_channel = "TG канал⛓️‍💥"

manager_nick = "avito_pf_otzivi"

yes_refer = "<b>❗ {}, у вас уже есть рефер - {}!</b>"
refer_not_in_base = "❗ {}, пользователь с <b>ID {}</b> не зарегистрирован!"
user_not_in_base = "❗ Пользователь <b>{}</b> не зарегистрирован!"
magic_ref = "⚙️ Введите ID или логин пользователя, для которого хотите сгенерировать реф-ссылку:"
magic_report = "⚙️ Введите ID или логин пользователя, для которого хотите получить отчет:"
magic_gen_str = "⚙️Для пользователя <b>{}</b> сгенерирована волшебная ссылка\n🔗{}"
sheet_complete = "⚙️ Cформирована электронная таблица в GoogleSheets:"
invite_yourself = "<b>❗ Вы не можете пригласить себя</b>"
new_refferal = "<b>💎 У вас новый реферал! @{user_name} </b>"


def start_text_ref(ref_first_name):
    msg = (f" 🎉Добро пожаловать!\n"
           f"🙋‍♂️Вас пригласил: {ref_first_name}")
    return msg


tasks_text = """Прайс сделан для примера с расчетом на одно объявление, ниже вы выбираете количество пф.

Чтобы запустить на разное количество, запускайте объявления ПО ОТДЕЛЬНОСТИ.

{} рублей за 1 ПФ

Выберите количество ПФ в день:
"""

qna_text = "📲 Вопросы и ответы."

how_to_start_text = '''1. Перейти в личный кабинет и нажать кнопку Пополнить баланс
2. Ввести сумму и выберете способ оплаты
3. После пополнения баланса перейти в меню Накрутка ПФ
4. Выбрать срок работы накрутки ПФ
5. Выбрать количество ПФ в день
6. Указать ссылку/ссылки на объявления, если их несколько, то каждую ссылку на объявление с новой строки
7. Подтвердить списание с баланса бота.
'''

main_menu = "🧊 Главное меню"

# Button label fallbacks for get_string().
# get_string() in keyboards/inline_keyboards.py falls back to globals() of that
# module (which has `from design import *`). Any btn_* key used in a keyboard
# MUST have a constant here so keyboards never produce text=None.
btn_avito = "🚀 Накрутка ПФ Авито"
btn_profile = "🪪 Личный кабинет"
btn_main_menu = "🧊 Главное меню"
btn_yes = "✅ Да"
btn_no = "❎ Нет"
btn_all_completed = "✅ Выполненные"
btn_all_posted = "🚀 В работе"
btn_avito_cases = "🔗 Кейсы Авито"
btn_support = "🧑‍💻 Поддержка"
btn_qna = "📲 FAQ / Кейсы"
btn_promocodes = "🔮 Промокоды"

show_balance = "💳 Показать баланс"
refill_balance = "💰 Пополнить баланс"
list_orders = "📖 Показать список заказов"
order_status = "📖️ Проверить статус заказа"
get_ref = "🐼 Показать реферальную ссылку"

def get_ref_text(user_id):
    return f"🔗 Ваша реферальная ссылка: {config.botlink}?start={user_id}"

def show_bal_text(balance):
    return f"💰 Ваш баланс составляет {balance} руб."

enter_days = "✍️ Введите требуемое количество дней. Минимум 1:"

enter_pf = "✍️ Введите требуемое количество ПФ. Минимум 5:"

refill_balance_text = '''💳 Даём + 50% к балансу при пополнении от 15.000₽ «от 7.500₽ сверху закинем»

🧊 Пожалуйста, введите сумму пополнения баланса (минимум - 100₽)'''

'''💳 При пополнении баланса более чем на 15 000 руб. действует скидка 50% на все услуги (кроме отзывов)

🧊 Пожалуйста, введите сумму пополнения баланса (минимум - 100)'''


def _render_order_links_block(order: dict) -> str:
    """Возвращает HTML-блок ссылок для TG-сообщения о заказе.

    Читает order_links таблицу — orders.links колонка deprecated."""
    from services.order_links import list_links
    try:
        rows = list_links(int(order['increment']))
    except Exception:
        rows = []
    urls = [r['url'] for r in rows if r.get('url')]
    if not urls:
        return "🔗 Ссылок нет"
    out = f"🔗 Ссылки на объявления({len(urls)}):"
    for url in urls:
        out += f"\n<code>{url}</code>"
    return out


def _render_order_deadline_line(order: dict) -> str:
    """Строка со сроком накрутки — только для заказов в работе.

    Срок берём как самый поздний deadline_at среди ссылок: заказ считается
    выполненным, когда закрылась последняя. Пока диспетчер не разослал ссылки
    (все pending, старт по PF_DEFAULT_START_HOUR), deadline_at ещё нет — это
    штатное состояние, а не ошибка, поэтому так и пишем.

    Для остальных статусов строки нет — возвращаем ''."""
    if order.get('status') != 'paid':
        return ""
    from services.order_links import list_links
    try:
        rows = list_links(int(order['increment']))
    except Exception:
        return ""
    # deadline_at пишет только services.order_links.compute_deadline, и всегда
    # в одном виде ('YYYY-MM-DDT00:00:00+00:00'), поэтому max по строке здесь
    # совпадает с максимумом по времени. Сменится формат — max станет врать.
    deadlines = [r['deadline_at'] for r in rows if r.get('deadline_at')]
    if not deadlines:
        return "⏳ Ожидает запуска\n"
    latest = format_display(max(deadlines))[:10]
    if not latest:
        return "⏳ Ожидает запуска\n"
    return f"⏳ Работает до: {latest}\n"


def listord_array(orders: list[dict]):
    orders_array = []
    for order in orders:
        if order['contacts']:
            contacts_str = '✅ Да'
        else:
            contacts_str = '❎ Нет'
        info = get_user(id=order['user_id'])
        if info:
            if info['user_name'] is not None:
                usr_str = f"@{info['user_name']} (<a href='tg://user?id={info['id']}'>{info['id']}</a>)"
            else:
                usr_str = f"<a href='tg://user?id={info['id']}'>{info['id']}</a>"
        else:
            usr_str = 'неизвестно'
        status = order_status_label(order['status'])
        pos = order['position_name'].split('/')
        dec_days = get_days_suffix(int(pos[0]))
        position_name = f"{pos[0]} {dec_days} - {pos[1]} ПФ"
        f_price = format_decimal(order['price'])
        msg = (f"🐼 ID заказа: <code>{order['increment']}</code>\n"
               f"💳 Цена: {f_price}\n"
               f"👤 Пользователь: {usr_str}\n"
               f"⚙️ Имя позиции: {position_name}\n"
               f"🔰 Статус: {status}\n"
               + _render_order_deadline_line(order)
               + f"👥 Контакты: {contacts_str}\n"
               f"🗓 Дата: {format_display(order['date'])}\n"
               + _render_order_links_block(order))
        orders_array.append(msg)
    return orders_array

tarifs_text = '''При пополнении баланса более чем на 15 000 руб. действует скидка 50% на все услуги кроме отзывов.
Наша группа: *вставить ссылку*

Для заказа услуги выберите раздел:'''

def order_status_txt(id, status):
    return f"Заказ номер {id}\nСтатус заказа: {status}"


pf_text = """Вы выбрали {} {}.

Выберите / Введите необходимое количество поведенческого фактора !

Наши рекомендации:
•Товары (с контактами)
•Услуга (лучше без контактов)

🚀 50пф - частый выбор наших клиентов!

Цена {}₽ за 1 ПФ

Выберите количество ПФ на день:
"""

pf_links = """Больше 1 ссылки запустить сразу - можно!

- КАЖДАЯ ССЫЛКА С НОВОЙ СТРОКИ 'CTRL+ENTER'."""


def order_text(order: dict):
    info = get_user(id=order['user_id'])
    if order['contacts']:
        contacts_str = 'Да'
    else:
        contacts_str = 'Нет'
    try:
        info = get_user(id=order['user_id'])
        msg = (f"🐼 ID заказа: {order['increment']}\n"
               f"💳 Цена: {order['price']}\n"
               f"👤 Пользователь: @{info['user_name']} | <a href='tg://user?id={info['id']}'>{info['id']}</a>\n"
               f"⚙️ Имя позиции: {order['position_name']}\n"
               f"🔰 Статус: {order_status_label(order['status'])}\n"
               + _render_order_deadline_line(order)
               + f"👥 Контакты: {contacts_str}\n"
               f"🗓 Дата: {format_display(order['date'])}\n"
               + _render_order_links_block(order))
        return msg
    except Exception as e:
        print(e)
        return "заказ не найден"

str_select_payment_method = "💳 Пополнение на <b>{}</b>₽\n\nВыберите способ оплаты:"

str_manual_payment = (
    "💳 Ручная оплата на <b>{}</b>₽\n\n"
    "Напишите менеджеру следующее сообщение\n"
    "(нажмите, чтобы скопировать):\n\n"
    "<code>{}</code>"
)