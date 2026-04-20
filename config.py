import os

# ---------------- TELEGRAM ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------- TAX & PURITY (REQUIRED by price_calculator.py) ----------------
# GST for gold products in India is typically 3%
GST_RATE = float(os.getenv("GST_RATE", "0.03"))

# Purity mapping used to convert karat/labels to purity fraction
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

# ---------------- SCRAPER SETTINGS ----------------
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.6"))

# AJIO API URL (keep same as what worked earlier if you had a different one)
AJIO_API_URL = os.getenv("AJIO_API_URL", "https://www.ajio.com/api/search")

# SEARCH PARAMS (keep same as earlier working values if yours were different)
SEARCH_PARAMS = {
    "ajio": {
        "query": "gold",
        "currentPage": 1,
        "pageSize": 48,
        "sortBy": "relevance",
    },
    "myntra": {
        "rows": 50
    }
}

# ---------------- PAYMENT DISCOUNT RULES ----------------
PAYMENT_DISCOUNT_RULES = [
    # Example: AJIO prepaid/UPI discount model
    {
        "name": "AJIO_PREPAID_UPI_5P",
        "site": "AJIO",
        "type": "instant_percent",
        "percent": 5.0,
        "max_discount": 2000.0,
        "min_order_value": 40000.0,
        "payment_modes": ["UPI", "PREPAID"],
        "stackable": True
    },

    # Example: ICICI card instant discount model
    {
        "name": "AJIO_ICICI_CC_10P",
        "site": "AJIO",
        "type": "instant_percent",
        "percent": 10.0,
        "max_discount": 1000.0,
        "min_order_value": 3000.0,
        "payment_modes": ["ICICI_CC"],
        "stackable": False
    },
]

PAYMENT_MODES_TO_TRY = ["UPI", "PREPAID", "ICICI_CC"]
DEFAULT_PAYMENT_MODE = "UPI"
