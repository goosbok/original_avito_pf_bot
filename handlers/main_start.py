import colorama
from aiogram.dispatcher import FSMContext
from aiogram.types import Message

from data.loader import bot, storage, dp
from utils.sqlite3 import get_user, update_user, all_users
from design import (
    yes_refer, refer_not_in_base, invite_yourself,
    start_text, start_text_ref,
)
from keyboards.inline_keyboards import get_menu_kb

async def get_user_name(user):
    if user.first_name:
        name = user.first_name
    elif user.username:
        name = f"@{user.username:}"
    else:
        name = user.id
    return name

async def get_refer_name(user_id):
    user = get_user(id=user_id)
    if user:
        if user['user_name'] and user['first_name']:
            name = f"{user['first_name']} (@{user['user_name']})"
            return name
        elif user['user_name']:
            name = f"@{user['user_name']}"
            return name
        elif user['first_name']:
            name = user['first_name']
            return name
        elif user['id']:
            name = user['id']
            return name
        else:
            return None
    else:
        return None

@dp.message_handler(commands=['start'], state="*")
async def main_start(message: Message, state: FSMContext, user_id: int):
    await state.finish()
    user = get_user(id=user_id)
    usr = message.from_user
    args = message.get_args()
    name = await get_user_name(usr)
    if args == 'connect':
        # Deep-link from web SPA: /start connect → trigger phone-sharing flow
        from handlers.connect import prompt_for_contact
        await prompt_for_contact(message)
        return
    if args:
        if user['ref_user_name'] is not None:
            ref_name = await get_refer_name(user['ref_id'])
            await message.answer(f"{yes_refer.format(name, ref_name)}")
        else:
            if args.isdigit():  # Проверка на цифры (id пользователя)
                refer_id = args
                ref_name = await get_refer_name(refer_id)
                refer = get_user(id=refer_id)
                if refer:
                    if refer['id'] == user_id:
                        await message.answer(invite_yourself)
                    else:
                        update_user(id=user_id, ref_user_name=refer['user_name'])
                        update_user(id=user_id, ref_id=refer['id'])
                        if refer['referals']:
                            referals_array = refer['referals'].split(',')
                            if str(user_id) not in referals_array:
                                referals_array.append(user_id)
                            referals_str = ""
                            for ref_id in referals_array:
                                if referals_str == "":
                                    referals_str = ref_id
                                else:
                                    referals_str += f",{ref_id}"
                            update_user(id=refer['id'], referals=referals_str)
                        else:
                            update_user(id=refer['id'], referals=user_id)
                        await message.answer(start_text_ref(ref_first_name=ref_name), reply_markup=get_menu_kb())
                else:
                    await message.answer(f"{refer_not_in_base.format(name, refer_id)}")
            else:
                users = all_users()
                if user['magic'] != args:
                    for usr in users:
                        if args == usr['magic']:
                            ref_first_name = f"{usr['first_name']} (@{usr['user_name']})"
                            update_user(id=user_id, ref_id=usr['id'])
                            update_user(id=user_id, ref_user_name=usr['user_name'])
                            if usr['referals']:
                                referals_array = usr['referals'].split(',')
                                if str(user_id) not in referals_array:
                                    referals_array.append(user_id)

                                referals_str = ""
                                for ref_id in referals_array:
                                    if referals_str == "":
                                        referals_str = ref_id
                                    else:
                                        referals_str += f",{ref_id}"
                                update_user(id=usr['id'], referals=referals_str)
                            else:
                                update_user(id=usr['id'], referals=user_id)
                            await message.answer(start_text_ref(ref_first_name), reply_markup=get_menu_kb())
                else:
                    await message.answer(invite_yourself)
                        #await message.reply(f"Привет {user['first_name']}! Ты пришел по реферальной ссылке {usr['first_name']} (@{usr['user_name']}).")
    else:
        await message.answer(f"{start_text.format(name)}", reply_markup=get_menu_kb())