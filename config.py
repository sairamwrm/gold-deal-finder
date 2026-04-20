import os

# ---------------- TELEGRAM ----------------
# Keep these in GitHub Secrets:
# TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------- SCRAPER SETTINGS ----------------
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.6"))  # seconds between requests

# AJIO search API endpoint (this is what your project already uses)
AJIO_API_URL = os.getenv("AJIO_API_URL", "https://www.ajio.com/api/search")

# Search params for AJIO + Myntra
# NOTE: If your old config had specific params that worked, keep them.
SEARCH_PARAMS = {
    "ajio": {
        # AJIO often uses query/searchText + page fields
        # Keep this structure because your scraper updates currentPage dynamically.
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
# Payment-time discounts applied at checkout (modeled rules)
PAYMENT_DISCOUNT_RULES = [
    # AJIO prepaid/UPI example: 5% instant prepaid discount, min ₹40,000, max ₹2,000
    {
        "name": "AJIO_PREPAID_UPI_5P",
        "site": "AJIO",
        "type": "instant_percent",      # instant_percent | cashback_percent | instant_flat
        "percent": 5.0,
        "max_discount": 2000.0,
        "min_order_value": 40000.0,
        "payment_modes": ["UPI", "PREPAID"],
        "stackable": True
    },

    # AJIO ICICI offer example: 10% off up to ₹1000, min ₹3000
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

    # Myntra rules optional (add later if needed)
    # {
    #     "name": "MYNTRA_BANK_CC_5P",
    #     "site": "Myntra",
    #     "type": "cashback_percent",
    #     "percent": 5.0,
    #     "max_discount": 1000.0,
    #     "min_order_value": 3500.0,
    #     "payment_modes": ["BANK_CC"],
    #     "stackable": False
    # },
]

PAYMENT_MODES_TO_TRY = ["UPI", "PREPAID", "ICICI_CC"]
DEFAULT_PAYMENT_MODE = "UPI"
