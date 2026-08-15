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
from logging.handlers import RotatingFileHandler

_STORAGE = Path(__file__).resolve().parent / "storage"
_STORAGE.mkdir(exist_ok=True)
LOG_PATH = _STORAGE / "log.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        RotatingFileHandler(
            LOG_PATH,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)
# Use a private name so star-imports below cannot overwrite it.
_log = logging.getLogger("bot_runner")
_scheduler = None

# DB must exist before handler modules are imported — users_menu.py queries
# the settings table at module level (get_price calls on lines 10-15).
from utils.sqlite3 import create_db as _init_db
_init_db()

_log.info("Importing handlers...")
from handlers.main_start import *
from data.loader import dp
_log.info("Handlers imported successfully")

@dp.errors_handler()
async def _global_error_handler(update, exception):
    from utils.error_handler import report_handler_error

    source = update.message or update.callback_query
    context = {
        "handler": "global_error_handler",
        "update_id": update.update_id,
        "tg_user_id": source.from_user.id if source and source.from_user else None,
        "msg_text": (update.message.text or "")[:120] if update.message else None,
        "cb_data": update.callback_query.data if update.callback_query else None,
    }
    await report_handler_error(
        exception,
        logger=_log,
        context=context,
        reply_target=source,
    )
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
    from utils.sender import warn_missing_support_topics

    _log.info("Bot startup")
    await warn_missing_support_topics()
    # Reset allowed_updates so Telegram delivers all update types.
    # Without this, a stale webhook config (e.g. allowed_updates=["message"])
    # survives bot restarts and silently drops callback_query updates.
    await dp.bot.delete_webhook(drop_pending_updates=False)
    # Сбрасываем allowed_updates — стale webhook-фильтр выживает после рестарта
    # и может блокировать callback_query. Вызов get_updates с явным списком фиксит это.
    await dp.bot.get_updates(offset=-1, limit=1, allowed_updates=[
        "message", "callback_query", "inline_query", "chosen_inline_result",
        "shipping_query", "pre_checkout_query", "poll", "poll_answer",
        "my_chat_member", "chat_member",
    ])
    _log.info("Webhook cleared, polling with all update types")

    # ── Background schedulers (payment_probe + payment_reconciler) ────────────
    # Two independent jobs. Either can be enabled/disabled separately via env.
    # _scheduler is created on demand if at least one job is on.
    global _scheduler
    probe_interval = int(os.getenv("PAYMENT_PROBE_INTERVAL_MIN", "15"))
    reconciler_seconds = int(os.getenv("PAYMENT_RECONCILER_INTERVAL_SEC", "60"))

    if probe_interval > 0 or reconciler_seconds > 0:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        _scheduler = AsyncIOScheduler()

        if probe_interval > 0:
            from services.payment_probe import probe_and_alert
            _scheduler.add_job(probe_and_alert, "interval", minutes=probe_interval)
            _log.info("Payment probe scheduled (interval=%d min)", probe_interval)
        else:
            _log.info("Payment probe disabled (PAYMENT_PROBE_INTERVAL_MIN=0)")

        if reconciler_seconds > 0:
            from services.payment_reconciler import reconcile_pending
            _scheduler.add_job(
                reconcile_pending, "interval", seconds=reconciler_seconds,
                id="payment_reconciler",
                max_instances=1,
                misfire_grace_time=30,
            )
            _log.info("Payment reconciler scheduled (interval=%d sec)", reconciler_seconds)
        else:
            _log.info("Payment reconciler disabled (PAYMENT_RECONCILER_INTERVAL_SEC=0)")

        _scheduler.start()
    else:
        _log.info("Both probe and reconciler disabled — no scheduler started")

    if os.getenv("START_WEB", "1") != "0":
        asyncio.create_task(serve_web())
    print(Fore.MAGENTA + fig.renderText('launched') + Fore.RESET)


# Выполнение функции после выключения бота
async def on_shutdown(dp: Dispatcher):
    _log.info("Bot shutdown")
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
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
    from utils.sender import assert_errors_topic_configured
    assert_errors_topic_configured()

    from middlewares import *
    dp.setup_middleware(ExistsUserMiddleware())
    run_bot_forever()
