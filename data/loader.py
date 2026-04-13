from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

import data.config as config


bot = Bot(
    token=config.TOKEN,
    parse_mode=types.ParseMode.HTML,
)

storage = MemoryStorage()

dp = Dispatcher(
    bot=bot,
    storage=storage,
)


__all__ = (
    "bot",
    "storage",
    "dp",
)