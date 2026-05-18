import data.config as config
from data.loader import bot


async def send_admins(msg: str):
    await bot.send_message(
        chat_id=config.SUPPORT_CHAT_ID,
        text=msg,
        disable_web_page_preview=True,
    )
