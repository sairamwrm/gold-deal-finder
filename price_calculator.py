from config import GOODRETURNS_24K_PRICE, PURITY_MAP, GST_RATE, DEFAULT_MAKING

def calculate_fair_price_per_gram(purity: str, making_pct: float = DEFAULT_MAKING):
    """
    Fair price per gram based on Goodreturns 24K rate
    """
    purity_factor = PURITY_MAP.get(purity, 0.999)

    base_price = GOODRETURNS_24K_PRICE * purity_factor
    gst_amount = base_price * GST_RATE
    making_amount = base_price * making_pct

    fair_price = base_price + gst_amount + making_amount
    return round(fair_price, 2)


def calculate_effective_price_per_gram(total_price: float, weight: float):
    return round(total_price / weight, 2)


def is_real_deal(effective_price_pg: float, purity: str, making_pct: float):
    fair_pg = calculate_fair_price_per_gram(purity, making_pct)
    return effective_price_pg <= fair_pg, fair_pg
