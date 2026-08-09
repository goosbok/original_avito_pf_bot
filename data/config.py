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
SUPPORT_THREAD_QUESTIONS:  int = int(os.getenv("SUPPORT_THREAD_QUESTIONS", "0"))
SUPPORT_THREAD_ORDERS:     int = int(os.getenv("SUPPORT_THREAD_ORDERS", "0"))
SUPPORT_THREAD_ORDERS_WEB: int = int(os.getenv("SUPPORT_THREAD_ORDERS_WEB", "0"))
SUPPORT_THREAD_ERRORS:     int = int(os.getenv("SUPPORT_THREAD_ERRORS", "0"))
SUPPORT_THREAD_NEW_USERS:  int = int(os.getenv("SUPPORT_THREAD_NEW_USERS", "0"))
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

# Public landing URL — shown in TG bot main menu as "🌐 Наш сайт" next to the
# channel link. Override via env if landing moves to another host.
LANDING_URL: str = os.getenv("LANDING_URL", "https://pf-bot.com")

# === Biznesklondaik PF executor (auto-mode) ===
BIZA_API_KEY: str = os.getenv("BIZA_API_KEY", "")
BIZA_LOGIN: str = os.getenv("BIZA_LOGIN", "")
BIZA_PASSWORD: str = os.getenv("BIZA_PASSWORD", "")
BIZA_API_BASE_URL: str = os.getenv(
    "BIZA_API_BASE_URL",
    "https://biznesklondaik.ru/fwdrjjkigor_new/api",
).rstrip("/")
BIZA_DASHBOARD_BASE_URL: str = os.getenv(
    "BIZA_DASHBOARD_BASE_URL",
    "https://biznesklondaik.ru/fwdrjjkigor_new/pf-avito",
).rstrip("/")

PF_PHRASE_CACHE_REFRESH_ENABLED: bool = (
    os.getenv("PF_PHRASE_CACHE_REFRESH_ENABLED", "false").lower() in ("1", "true", "yes")
)
PF_AUTO_DISPATCH_ENABLED: bool = (
    os.getenv("PF_AUTO_DISPATCH_ENABLED", "false").lower() in ("1", "true", "yes")
)

# Ежедневная выгрузка авто-запусков в Google Sheets. Флаг гейтит ТОЛЬКО
# фоновый луп — админская кнопка «Авто запуски в шит» работает всегда,
# чтобы выгрузку можно было дёрнуть руками до включения расписания.
PF_AUTO_EXPORT_ENABLED: bool = (
    os.getenv("PF_AUTO_EXPORT_ENABLED", "false").lower() in ("1", "true", "yes")
)
PF_AUTO_EXPORT_HOUR_MSK: int = max(
    0, min(23, int(os.getenv("PF_AUTO_EXPORT_HOUR_MSK", "6")))
)

PF_PHRASE_CACHE_CHUNK_DAYS: int = int(
    os.getenv("PF_PHRASE_CACHE_CHUNK_DAYS", "4")
)
PF_PHRASE_CACHE_REFRESH_INTERVAL_H: int = int(
    os.getenv("PF_PHRASE_CACHE_REFRESH_INTERVAL_H", "24")
)
PF_DASHBOARD_REQUEST_DELAY_SEC: int = int(
    os.getenv("PF_DASHBOARD_REQUEST_DELAY_SEC", "3")
)
PF_AUTO_RATE_METRIC_INTERVAL_H: int = int(
    os.getenv("PF_AUTO_RATE_METRIC_INTERVAL_H", "1")
)
# Час старта накрутки на стороне исполнителя (МСК). Маппится в start_hour
# поля API биза (0..23). Применяется ко всем задачам которые мы отправляем
# в add-tasks.php. Глобальная настройка; если когда-то понадобится per-order
# — отдельная задача.
PF_DEFAULT_START_HOUR: int = max(
    0, min(23, int(os.getenv("PF_DEFAULT_START_HOUR", "0")))
)

# === biza API resilience (rate limit / circuit breaker / attempt cap) ===
# biza режет при >60 req/min (HTTP 429). Token-bucket ёмкости C в худшем
# случае (полный бакет + дозаправка) выдаёт до 2·C за скользящее окно 60с,
# поэтому дефолт 30 → ≤60/мин в любом окне. Реальный объём много ниже.
BIZA_MAX_PER_MIN: int = max(1, int(os.getenv("BIZA_MAX_PER_MIN", "30")))
# Стоп-кран: сколько ошибок подряд (429/500/сеть) до открытия.
BIZA_BREAKER_ERRORS: int = max(1, int(os.getenv("BIZA_BREAKER_ERRORS", "3")))
# Сколько минут не трогать biza после открытия стоп-крана.
BIZA_COOLDOWN_MIN: int = max(1, int(os.getenv("BIZA_COOLDOWN_MIN", "30")))
# Потолок попыток авто-отправки на ссылку; дальше → manual.
BIZA_MAX_ATTEMPTS: int = max(1, int(os.getenv("BIZA_MAX_ATTEMPTS", "2")))

# ── Welcome bonus ────────────────────────────────────────────────────────────
# Приветственный бонус новым пользователям, в рублях. 0 = выключено.
WELCOME_BONUS_RUB: int = int(os.getenv("WELCOME_BONUS_RUB", "0"))
