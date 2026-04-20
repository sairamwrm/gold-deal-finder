# ---------------- PAYMENT DISCOUNT RULES ----------------
# These rules model payment-time discounts that are applied at checkout.
# AJIO examples are published in AJIO T&C pages with min order value and cap. [1](https://www.linkedin.com/pulse/web-scraping-ajio-data-fashion-trends-pricing-product-analysis-nokle)[2](https://regexr.com/)

PAYMENT_DISCOUNT_RULES = [
    # AJIO prepaid/UPI example: 5% instant prepaid discount, min ₹40,000, max ₹2,000. [1](https://www.linkedin.com/pulse/web-scraping-ajio-data-fashion-trends-pricing-product-analysis-nokle)
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

    # AJIO ICICI offer snapshot example (choose one of the offer tiers). [2](https://regexr.com/)
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

    # Myntra: add your own rules if you want to model bank/card/coupon effects.
    # Example placeholder:
    # {
    #     "name": "MYNTRA_BANK_X",
    #     "site": "Myntra",
    #     "type": "cashback_percent",
    #     "percent": 5.0,
    #     "max_discount": 1000.0,
    #     "min_order_value": 3500.0,
    #     "payment_modes": ["BANK_CC"],
    #     "stackable": False
    # },
]

# Default modes to compare (you can change)
PAYMENT_MODES_TO_TRY = ["UPI", "PREPAID", "ICICI_CC"]
DEFAULT_PAYMENT_MODE = "UPI"
``
