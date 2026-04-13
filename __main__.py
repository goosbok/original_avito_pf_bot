from aiogram import Dispatcher
from aiogram.utils import executor
#from aiogram import executor
from pyfiglet import Figlet
from colorama import Fore

fig = Figlet(font='slant', width=200)
print(f"{Fore.RED}{fig.renderText('ABUTO by OEvg85')}{Fore.RESET}")

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from handlers.admin_functions import *
from handlers.main_start import *
from data.loader import dp
from utils.msql import sql_start

# Выполнение функции после запуска бота
async def on_startup(dp: Dispatcher):
#    sql_start()
    print(Fore.MAGENTA + fig.renderText('launched') + Fore.RESET)


# Выполнение функции после выключения бота
async def on_shutdown(dp: Dispatcher):
    await dp.storage.close()
    await dp.storage.wait_closed()
    await (await dp.bot.get_session()).close()

if __name__ == '__main__':
    from middlewares import *
    from utils.sqlite3 import create_db
    create_db()
    dp.setup_middleware(ExistsUserMiddleware())
    executor.start_polling(
        dp,
        on_startup=on_startup,  # Вызывается при запуске бота
        on_shutdown=on_shutdown,  # Вызывается при остановке бота
        skip_updates=True
    )
