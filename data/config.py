import os

# Telegram Bot
TOKEN: str = os.getenv("BOT_TOKEN", "")
path_database: str = os.getenv("DATABASE_PATH", "data/database.db")
bot_version: str = os.getenv("BOT_VERSION", "1.0.1")

# Yookassa payments
YOOKASSA_TEST: str = os.getenv("YOOKASSA_TEST", "")
SHOP_ID: int = int(os.getenv("SHOP_ID", "0"))
SECRET_KEY: str = os.getenv("YOOKASSA_SECRET_KEY", "")

# Bot operation
support_tag: str = os.getenv("SUPPORT_TAG", "avito_pf_otzizi")
ADMINS: list = [int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip()]
SUPPORT_CHAT_ID: int = int(os.getenv("SUPPORT_CHAT_ID", "0"))
SUPPORT_THREAD_QUESTIONS: int = int(os.getenv("SUPPORT_THREAD_QUESTIONS", "0"))
SUPPORT_THREAD_ORDERS:    int = int(os.getenv("SUPPORT_THREAD_ORDERS", "0"))
SUPPORT_THREAD_ERRORS:    int = int(os.getenv("SUPPORT_THREAD_ERRORS", "0"))
SUPPORT_THREAD_NEW_USERS: int = int(os.getenv("SUPPORT_THREAD_NEW_USERS", "0"))
CODER: int = int(os.getenv("CODER", "0"))
botlink: str = os.getenv("BOT_LINK", "https://t.me/AVITOPF_bot")
SITE_URL: str = os.getenv("SITE_URL", "")
channel_link: str = os.getenv("CHANNEL_LINK", "https://t.me/pf_avito_top")

# --- Static pricing config (rarely changes, not secret) ---
fix_price: int = 6
prices = {
    'day-5': fix_price, 'day-10': fix_price, 'day-20': fix_price,
    'day-30': fix_price, 'day-50': fix_price, 'day-100': fix_price,
    'day-150': fix_price, 'day-500': fix_price, 'day-1000': fix_price,
    'week-5': fix_price, 'week-10': fix_price, 'week-15': fix_price,
    'week-20': fix_price, 'week-30': fix_price, 'week-50': fix_price,
    'week-100': fix_price, 'week-150': fix_price, 'week-500': fix_price,
    'week-1000': fix_price,
    'month-5': fix_price, 'month-10': fix_price, 'month-15': fix_price,
    'month-20': fix_price, 'month-30': fix_price, 'month-50': fix_price,
    'month-100': fix_price, 'month-150': fix_price, 'month-500': fix_price,
    'month-1000': fix_price,
}
services = {
    'vk': 'ВКонтакте', 'yandex': 'Яндекс', '2gis': '2ГИС',
    'flamp': 'Фламп', 'google': 'Google', 'avito': 'Авито',
}
price_google = {'100': 120, '50': 150, '20': 180, '10': 200, '5': 300}
price_yandex = {'100': 300, '50': 350, '20': 400, '10': 450, '5': 500}
price_vk     = {'100': 400, '50': 450, '20': 500, '10': 550, '5': 600}
price_flamp  = {'100': 120, '50': 150, '20': 180, '10': 200, '5': 300}
price_2gis   = {'100': 120, '50': 150, '20': 180, '10': 200, '5': 300}
price_avito  = {'100': 650, '50': 650, '20': 650, '10': 650, '5': 650}

# Google Sheets exports
# ID существующей таблицы, в которую бот пишет все 4 отчёта (по вкладкам).
# Service account из utils/dev-trees-*.json должен быть добавлен в шаринг этой
# таблицы с правом Editor. Никаких новых файлов SA не создаёт (у него Drive-квота 0).
GSHEETS_TARGET_SHEET_ID: str = os.getenv("GSHEETS_TARGET_SHEET_ID", "")

# Web / JWT
JWT_SECRET: str = os.getenv("JWT_SECRET", "")
WEB_HOST: str = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT: int = int(os.getenv("WEB_PORT", "8000"))

# OTP
OTP_TTL_SECONDS: int = int(os.getenv("OTP_TTL_SECONDS", "300"))
OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
OTP_RESEND_COOLDOWN: int = int(os.getenv("OTP_RESEND_COOLDOWN", "60"))
BOT_HTTP_API_BASE: str = os.getenv("BOT_HTTP_API_BASE", "https://api.telegram.org")

# Avito link-preview proxy on the RU-VPS (139.28.222.146).
# Bypass: Avito blocks Hetzner egress (403) but the RU-VPS sits in Moscow and gets 200.
# The proxy is a single nginx location with a shared-secret header check.
AVITO_PROXY_URL: str = os.getenv("AVITO_PROXY_URL", "https://lk.pf-bot.com")
AVITO_PROXY_SECRET: str = os.getenv("AVITO_PROXY_SECRET", "")
