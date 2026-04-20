from typing import Dict, List, Tuple

# These imports may be used by other parts of your repo or for future logic
# Keep them to avoid import errors if your file expects them.
from config import GST_RATE, PURITY_MAPPING, GOODRETURNS_CITY  # noqa: F401


def apply_payment_discounts(
    site: str,
    selling_price: float,
    payment_mode: str,
    rules: List[Dict],
    allow_stacking: bool = True
) -> Tuple[float, float, float, str]:
    """
    Apply configured payment discount rules.

    Returns:
      pay_now_price: price after instant discounts
      effective_price: price after instant discounts and cashback-type discounts (if modeled)
      total_discount_value: total discount value applied
      applied_rules: comma-separated rule names or 'NONE'
    """
    pay_now = float(selling_price)
    effective = float(selling_price)
    discount_total = 0.0
    applied = []

    for r in rules:
        if r.get("site") != site:
            continue

        if payment_mode not in (r.get("payment_modes") or []):
            continue

        if selling_price < float(r.get("min_order_value", 0) or 0):
            continue

        # If stacking isn't allowed globally or this rule says not stackable, block after first apply
        if applied and (not allow_stacking or not r.get("stackable", True)):
            continue

        rtype = r.get("type")

        if rtype == "instant_percent":
            percent = float(r.get("percent", 0) or 0)
            cap = float(r.get("max_discount", 10**18) or 10**18)
            disc = min(pay_now * percent / 100.0, cap)

            pay_now = max(0.0, pay_now - disc)
            effective = pay_now

            discount_total += disc
            applied.append(r.get("name", "RULE"))

        elif rtype == "instant_flat":
            flat = float(r.get("flat", 0) or 0)
            cap = float(r.get("max_discount", 10**18) or 10**18)
            disc = min(flat, cap)

            pay_now = max(0.0, pay_now - disc)
            effective = pay_now

            discount_total += disc
            applied.append(r.get("name", "RULE"))

        elif rtype == "cashback_percent":
            # Modeled as "effective benefit" (not always instant at checkout)
            percent = float(r.get("percent", 0) or 0)
            cap = float(r.get("max_discount", 10**18) or 10**18)
            disc = min(effective * percent / 100.0, cap)

            effective = max(0.0, effective - disc)

            discount_total += disc
            applied.append(r.get("name", "RULE"))

    return pay_now, effective, discount_total, ",".join(applied) if applied else "NONE"


def best_price_by_payment_mode(
    site: str,
    selling_price: float,
    payment_modes: List[str],
    rules: List[Dict],
    allow_stacking: bool = True
) -> Dict:
    """
    Evaluate multiple payment modes and return the best (lowest effective_price).
    This is the function your gold_scraper.py imports.
    """
    best = {
        "payment_mode": None,
        "pay_now_price": float(selling_price),
        "effective_price": float(selling_price),
        "discount_value": 0.0,
        "rules": "NONE"
    }

    for mode in payment_modes or []:
        pay_now, effective, disc, label = apply_payment_discounts(
            site=site,
            selling_price=selling_price,
            payment_mode=mode,
            rules=rules,
            allow_stacking=allow_stacking
        )

        if effective < best["effective_price"]:
            best = {
                "payment_mode": mode,
                "pay_now_price": float(pay_now),
                "effective_price": float(effective),
                "discount_value": float(disc),
                "rules": label
            }

    if best["payment_mode"] is None:
        best["payment_mode"] = payment_modes[0] if payment_modes else "NONE"

    return best
