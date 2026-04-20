from price_calculator import is_real_deal
from config import PAYMENT_MODES_ALLOWED
from telegram_bot import send_telegram_message


def process_product(product):
    """
    product dict MUST contain:
    {
        "name": str,
        "price": float,      # final payable price
        "weight": float,     # grams
        "purity": str,       # "999", "995", "916"
        "making_pct": float, # 0.04 for 4%
        "payment_mode": str,
        "url": str
    }
    """

    # 1️⃣ Ignore unwanted payment modes
    if product["payment_mode"] not in PAYMENT_MODES_ALLOWED:
        return

    # 2️⃣ Check real deal vs Goodreturns
    is_deal, eff_pg, fair_pg = is_real_deal(
        total_price=product["price"],
        weight=product["weight"],
        purity=product["purity"],
        making_pct=product["making_pct"],
    )

    if not is_deal:
        return

    # 3️⃣ Send alert (ONLY REAL DEALS)
    send_telegram_message(
        f"""
💰 *REAL GOLD DEAL FOUND*

🪙 {product['name']}
⚖️ {product['weight']} g | Purity: {product['purity']}
💳 Payment: {product['payment_mode']}

💰 Total Price: ₹{product['price']}

📉 Effective: ₹{eff_pg}/g
📊 Fair (Goodreturns): ₹{fair_pg}/g

✅ *BELOW FAIR VALUE*

🔗 {product['url']}
""".strip()
    )
