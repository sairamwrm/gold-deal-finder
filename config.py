import os

# ---------------- BASIC THRESHOLDS ----------------
# Keep these (your older scanner versions may still rely on them)
MIN_DISCOUNT_PERCENTAGE = float(os.getenv("MIN_DISCOUNT_PERCENTAGE", "0"))  # keep 0 for Goodreturns-only logic
MIN_WEIGHT = float(os.getenv("MIN_WEIGHT", "0.3"))

# ---------------- GOODRETURNS ANCHOR ----------------
# Put today's 24K per gram here (Hyderabad). Ex: 15529 on Apr 20, 2026. [1](https://www.goodreturns.in/news/huge-drop-gold-price-akshaya-tritiya-chennai-hyderabad-24k-22k-18k-gold-rate-today-april-20-mcx-1503279.html)[2](https://www.goldsrate.com/india/telangana/gold-rate-in-hyderabad.html)
GOODRETURNS_24K_PRICE = float(os.getenv("GOODRETURNS_24K_PRICE", "15529"))

# Optional tolerance: 0 means strictly <= fair value, 0.003 means allow 0.3% wiggle
GOODRETURNS_TOLERANCE_PCT = float(os.getenv("GOODRETURNS_TOLERANCE_PCT", "0.0"))

# ---------------- TAX & PURITY (required by your GoldPriceCalculator) ----------------
# IMPORTANT: your price_calculator uses GST_RATE/100, so GST_RATE must be 3 not 0.03
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

# ---------------- TELEGRAM ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------- PAYMENT MODES ----------------
# This name MUST exist because scanner.py imports it.
