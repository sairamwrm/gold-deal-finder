from price_calculator import (
    calculate_effective_price_per_gram,
    is_real_deal
)
from config import PAYMENT_MODES_ALLOWED
from notifier import send_telegram_alert


def process_product(product):
    """
    product = {
        name, price, weight, purity, making_pct, payment_mode, url
    }
    """

    if product["payment_mode"] not in PAYMENT_MODES_ALLOWED:
        return

    eff_pg = calculate_effective_price_per_gram(
        product["price"],
        product["weight"]
    )

    is_deal, fair_pg = is_real_deal(
        eff_pg,
        product["purity"],
        product["making_pct"]
    )

    if not is_deal:
        return

    send_telegram_alert(
        product=product,
        eff_pg=eff_pg,
        fair_pg=fair_pg
    )
