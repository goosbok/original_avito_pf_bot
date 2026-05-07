from aiogram import Dispatcher
from aiogram.utils import executor
from pyfiglet import Figlet
from colorama import Fore
import logging
import time
from pathlib import Path
import asyncio
import os

fig = Figlet(font='slant', width=200)
print(f"{Fore.RED}{fig.renderText('ABUTO by OEvg85')}{Fore.RESET}")

# Logging must be configured before any module imports so that import-time
# errors (missing DB rows, bad env vars, etc.) appear in the log file.
LOG_PATH = Path(__file__).resolve().parent / "log.txt"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
# Use a private name so star-imports below cannot overwrite it.
_log = logging.getLogger("bot_runner")

# DB must exist before handler modules are imported — users_menu.py queries
# the settings table at module level (get_price calls on lines 10-15).
from utils.sqlite3 import create_db as _init_db
_init_db()

_log.info("Importing handlers...")
from handlers.admin_functions import *
from handlers.main_start import *
from data.loader import dp
_log.info("Handlers imported successfully")

@dp.errors_handler()
async def _global_error_handler(update, exception):
    _log.exception("Unhandled exception for update %s", update, exc_info=exception)
    return True


async def serve_web():
    import uvicorn
    from web.main import app
    from web.config import WEB_HOST, WEB_PORT, assert_configured

    assert_configured()
    config = uvicorn.Config(
        app,
        host=WEB_HOST,
        port=WEB_PORT,
        log_level="info",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    await server.serve()


# Выполнение функции после запуска бота
async def on_startup(dp: Dispatcher):
    _log.info("Bot startup")
    # Reset allowed_updates so Telegram delivers all update types.
    # Without this, a stale webhook config (e.g. allowed_updates=["message"])
    # survives bot restarts and silently drops callback_query updates.
    await dp.bot.delete_webhook(drop_pending_updates=False)
    _log.info("Webhook cleared, polling with all update types")
    if os.getenv("START_WEB", "1") != "0":
        asyncio.create_task(serve_web())
    print(Fore.MAGENTA + fig.renderText('launched') + Fore.RESET)


# Выполнение функции после выключения бота
async def on_shutdown(dp: Dispatcher):
    _log.info("Bot shutdown")
    await dp.storage.close()
    await dp.storage.wait_closed()
    await (await dp.bot.get_session()).close()


def run_bot_forever(restart_delay_seconds: int = 5):
    while True:
        try:
            _log.info("Starting polling")
            executor.start_polling(
                dp,
                on_startup=on_startup,
                on_shutdown=on_shutdown,
                skip_updates=True,
            )
            _log.warning("Polling stopped without exception. Restart in %s sec", restart_delay_seconds)
        except KeyboardInterrupt:
            _log.info("Bot stopped by KeyboardInterrupt")
            break
        except Exception:
            _log.exception("Unhandled exception in polling loop. Restart in %s sec", restart_delay_seconds)

        time.sleep(restart_delay_seconds)

if __name__ == '__main__':
    from middlewares import *
    dp.setup_middleware(ExistsUserMiddleware())
    run_bot_forever()
