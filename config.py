import os

# ============================================================
# 1) CORE SCRAPER CONFIG (gold_scraper.py imports these)
# ============================================================
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.6"))

AJIO_API_URL = os.getenv("AJIO_API_URL", "https://www.ajio.com/api/search")

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

# ============================================================
# 2) THRESHOLDS (scanner.py / filtering)
# ============================================================
MIN_WEIGHT = float(os.getenv("MIN_WEIGHT", "0.3"))

# Keep this as 0 if you want ONLY Goodreturns-based deal logic
MIN_DISCOUNT_PERCENTAGE = float(os.getenv("MIN_DISCOUNT_PERCENTAGE", "0"))

# ============================================================
# 3) GOODRETURNS ANCHOR (real-deal comparison)
# ============================================================
# Example: Hyderabad 24K ~ ₹15,529 per gram on 20 Apr 2026. [1](https://www.livemint.com/gold-prices/hyderabad)
GOODRETURNS_24K_PRICE = float(os.getenv("GOODRETURNS_24K_PRICE", "15529"))

# Optional tolerance: 0.0 = strict, 0.003 = allow 0.3% above fair
GOODRETURNS_TOLERANCE_PCT = float(os.getenv("GOODRETURNS_TOLERANCE_PCT", "0.0"))

# ============================================================
# 4) TAX & PURITY (price_calculator.py imports these)
# ============================================================
# IMPORTANT: your GoldPriceCalculator uses GST_RATE/100,
# so GST_RATE must be 3.0 (not 0.03)
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

# ============================================================
# 5) TELEGRAM (telegram_bot.py imports these)
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ============================================================
# 6) PAYMENT MODES (scanner.py imports this exact name)
# ============================================================
# Configure in GitHub Actions env: PAYMENT_MODES_ALLOWED="UPI,PREPAID"
PAYMENT_MODES_ALLOWED = os.getenv("PAYMENT_MODES_ALLOWED", "UPI,PREPAID").split(",")
PAYMENT_MODES_ALLOWED = [m.strip() for m in PAYMENT_MODES_ALLOWED if m.strip()]

# ============================================================
# 7) PAYMENT DISCOUNT MODEL (gold_scraper.py may use these)
# ============================================================
PAYMENT_DISCOUNT_RULES = [
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

# For backward compatibility if your code expects these names:
PAYMENT_MODES_TO_TRY = PAYMENT_MODES_ALLOWED[:] if PAYMENT_MODES_ALLOWED else ["UPI"]
DEFAULT_PAYMENT_MODE = PAYMENT_MODES_TO_TRY[0] if PAYMENT_MODES_TO_TRY else "UPI"
