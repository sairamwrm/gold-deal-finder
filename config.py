import os

# ---------- Deal filters (scanner.py expects these) ----------
MIN_DISCOUNT_PERCENTAGE = float(os.getenv("MIN_DISCOUNT_PERCENTAGE", "0"))  # keep 0 when using Goodreturns rule
MIN_WEIGHT = float(os.getenv("MIN_WEIGHT", "0.3"))

# ---------- Telegram ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------- Tax & purity (price_calculator.py expects these) ----------
# IMPORTANT: your price_calculator uses GST_RATE/100 => GST_RATE must be percent (3), not 0.03
GST_RATE = float(os.getenv("GST_RATE", "3.0"))

PURITY_MAPPING = {
    "24K": 0.999,
    "999": 0.999,
    "995": 0.995,
    "22K": 0.916,
    "916": 0.916,
    "18K": 0.750,
    "750": 0.750,
    "14K": 0.585,
    "585": 0.585,
}

# ---------- Scraper settings ----------
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.6"))
AJIO_API_URL = os.getenv("AJIO_API_URL", "https://www.ajio.com/api/search")

SEARCH_PARAMS = {
    "ajio": {"query": "gold", "currentPage": 1, "pageSize": 48, "sortBy": "relevance"},
    "myntra": {"rows": 50},
}

# ---------- Payment discounts ----------
# IMPORTANT: keep ONLY the modes you actually want to consider.
# If you don’t want ICICI offers, remove ICICI_CC here.
PAYMENT_MODES_TO_TRY = os.getenv("PAYMENT_MODES_TO_TRY", "UPI,PREPAID").split(",")
DEFAULT_PAYMENT_MODE = os.getenv("DEFAULT_PAYMENT_MODE", "UPI")

PAYMENT_DISCOUNT_RULES = [
    {
        "name": "AJIO_PREPAID_UPI_5P",
        "site": "AJIO",
        "type": "instant_percent",
        "percent": 5.0,
        "max_discount": 2000.0,
        "min_order_value": 40000.0,
        "payment_modes": ["UPI", "PREPAID"],
        "stackable": True,
    },
    {
        "name": "AJIO_ICICI_CC_10P",
        "site": "AJIO",
        "type": "instant_percent",
        "percent": 10.0,
        "max_discount": 1000.0,
        "min_order_value": 3000.0,
        "payment_modes": ["ICICI_CC"],
        "stackable": False,
    },
]

# ---------- Goodreturns reference (NEW) ----------
# If you set GOODRETURNS_24K_OVERRIDE, we will use it and skip parsing.
GOODRETURNS_CITY = os.getenv("GOODRETURNS_CITY", "Hyderabad")
GOODRETURNS_24K_OVERRIDE = os.getenv("GOODRETURNS_24K_OVERRIDE", "")  # e.g. "15529"
GOODRETURNS_TOLERANCE_PCT = float(os.getenv("GOODRETURNS_TOLERANCE_PCT", "0.0"))  # 0 => strictly at/below
