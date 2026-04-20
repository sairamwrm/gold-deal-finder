import os

# ===================== Deal thresholds =====================
# We will primarily use Goodreturns comparison. These are fallback thresholds.
MIN_DISCOUNT_PERCENTAGE = float(os.getenv("MIN_DISCOUNT_PERCENTAGE", "0"))  # fallback only
MIN_WEIGHT = float(os.getenv("MIN_WEIGHT", "0.3"))

# ===================== Goodreturns comparison =====================
# Goodreturns pages note rates are indicative and do not include GST/TCS/other levies. [1](https://www.goodreturns.in/gold-rates/hyderabad.html)[2](https://www.goodreturns.in/gold-rates/)
GOODRETURNS_CITY = os.getenv("GOODRETURNS_CITY", "hyderabad")  # hyderabad | india
GOODRETURNS_COMPARE = os.getenv("GOODRETURNS_COMPARE", "EX_GST")  # EX_GST or INCL_GST
GOODRETURNS_TOLERANCE_PCT = float(os.getenv("GOODRETURNS_TOLERANCE_PCT", "0.0"))  # allow small slack e.g. 0.2

# ===================== Telegram =====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ===================== Tax & purity =====================
# Your price_calculator uses GST_RATE/100, so GST_RATE must be 3.0 (not 0.03)
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

# ===================== Scraper =====================
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.6"))
AJIO_API_URL = os.getenv("AJIO_API_URL", "https://www.ajio.com/api/search")

SEARCH_PARAMS = {
    "ajio": {"query": "gold", "currentPage": 1, "pageSize": 48, "sortBy": "relevance"},
    "myntra": {"rows": 50},
}

# ===================== Payment discount modeling =====================
# You control what modes are allowed by changing PAYMENT_MODES_TO_TRY.
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

# Example: ["UPI"] if you do NOT want ICICI offers.
PAYMENT_MODES_TO_TRY = os.getenv("PAYMENT_MODES_TO_TRY", "UPI,PREPAID,ICICI_CC").split(",")
DEFAULT_PAYMENT_MODE = os.getenv("DEFAULT_PAYMENT_MODE", "UPI")
