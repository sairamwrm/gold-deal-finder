# =====================================================================
# Goodreturns Anchored "Real Deal" Check
# (Append-only block – safe to paste at end of price_calculator.py)
# =====================================================================
import os

def _purity_factor_from_string(purity: str) -> float:
    """
    Supports: '24K','22K','18K','14K','999','995','916','750','585'
    Falls back to 0.999 if unknown.
    """
    if purity is None:
        return 0.999
    p = str(purity).upper().strip()

    try:
        # PURITY_MAPPING is imported in your file from config
        if p in PURITY_MAPPING:
            return float(PURITY_MAPPING[p])
    except Exception:
        pass

    if p.isdigit():
        n = float(p)
        if n > 10:  # 999 / 995 / 916...
            return n / 1000.0

    if p.endswith("K"):
        try:
            k = float(p.replace("K", ""))
            return k / 24.0
        except Exception:
            pass

    return 0.999


def _pct_to_fraction(x, default=0.0) -> float:
    """
    Accepts 4 or 0.04. Returns fraction 0.04.
    """
    try:
        v = float(x)
    except Exception:
        return float(default)
    return v / 100.0 if v > 1.0 else v


def is_real_deal(
    total_price: float,
    weight_grams: float,
    purity: str,
    making_charges_percent: float = 0.0,
    gst_percent: float = None,
    goodreturns_24k_price: float = None,
    tolerance_pct: float = None
) -> dict:
    """
    Real deal check anchored to Goodreturns 24K price:

      effective ₹/g <= fair ₹/g

    fair ₹/g = (Goodreturns24K ₹/g × purity_factor) × (1 + making + gst) × (1 + tolerance)

    Returns dict with computed values.
    """
    if not weight_grams or float(weight_grams) <= 0:
        return {
            "is_deal": False,
            "effective_price_per_gram": None,
            "fair_price_per_gram": None,
            "goodreturns_24k_price": None
        }

    eff_pg = float(total_price) / float(weight_grams)

    # Get config values safely
    if goodreturns_24k_price is None:
        try:
            from config import GOODRETURNS_24K_PRICE
            goodreturns_24k_price = float(GOODRETURNS_24K_PRICE)
        except Exception:
            goodreturns_24k_price = float(os.getenv("GOODRETURNS_24K_PRICE", "0") or 0)

    if tolerance_pct is None:
        try:
            from config import GOODRETURNS_TOLERANCE_PCT
            tolerance_pct = float(GOODRETURNS_TOLERANCE_PCT)
        except Exception:
            tolerance_pct = 0.0

    if not goodreturns_24k_price or goodreturns_24k_price <= 0:
        # Do NOT claim a deal if reference price isn't configured
        return {
            "is_deal": False,
            "effective_price_per_gram": round(eff_pg, 2),
            "fair_price_per_gram": None,
            "goodreturns_24k_price": None
        }

    purity_factor = _purity_factor_from_string(purity)

    making_frac = _pct_to_fraction(making_charges_percent, 0.0)

    if gst_percent is None:
        try:
            gst_percent = float(GST_RATE)  # GST_RATE in your code is percent like 3.0
        except Exception:
            gst_percent = 3.0
    gst_frac = _pct_to_fraction(gst_percent, 0.03)

    base_pg = float(goodreturns_24k_price) * purity_factor
    fair_pg = base_pg * (1.0 + making_frac + gst_frac)
    fair_pg = fair_pg * (1.0 + float(tolerance_pct))

    return {
        "is_deal": eff_pg <= fair_pg,
        "effective_price_per_gram": round(eff_pg, 2),
        "fair_price_per_gram": round(fair_pg, 2),
        "goodreturns_24k_price": round(float(goodreturns_24k_price), 2),
        "purity_factor": round(float(purity_factor), 6),
        "making_frac": round(float(making_frac), 6),
        "gst_frac": round(float(gst_frac), 6),
        "tolerance_pct": round(float(tolerance_pct), 6),
    }
