from aiogram import Dispatcher
from aiogram.utils import executor
#from aiogram import executor
from pyfiglet import Figlet
from colorama import Fore
import logging
import time
from pathlib import Path

fig = Figlet(font='slant', width=200)
print(f"{Fore.RED}{fig.renderText('ABUTO by OEvg85')}{Fore.RESET}")

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from handlers.admin_functions import *
from handlers.main_start import *
from data.loader import dp
from utils.msql import sql_start


LOG_PATH = Path(__file__).resolve().parent / "log.txt"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("bot_runner")

# Выполнение функции после запуска бота
async def on_startup(dp: Dispatcher):
#    sql_start()
    logger.info("Bot startup")
    print(Fore.MAGENTA + fig.renderText('launched') + Fore.RESET)


# Выполнение функции после выключения бота
async def on_shutdown(dp: Dispatcher):
    logger.info("Bot shutdown")
    await dp.storage.close()
    await dp.storage.wait_closed()
    await (await dp.bot.get_session()).close()


def run_bot_forever(restart_delay_seconds: int = 5):
    while True:
        try:
            logger.info("Starting polling")
            executor.start_polling(
                dp,
                on_startup=on_startup,
                on_shutdown=on_shutdown,
                skip_updates=True,
            )
            logger.warning("Polling stopped without exception. Restart in %s sec", restart_delay_seconds)
        except KeyboardInterrupt:
            logger.info("Bot stopped by KeyboardInterrupt")
            break
        except Exception:
            logger.exception("Unhandled exception in polling loop. Restart in %s sec", restart_delay_seconds)

        time.sleep(restart_delay_seconds)

if __name__ == '__main__':
    from middlewares import *
    from utils.sqlite3 import create_db
    create_db()
    dp.setup_middleware(ExistsUserMiddleware())
    run_bot_forever()
