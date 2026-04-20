import os
import re
import asyncio
from datetime import datetime

import requests

from gold_scraper import GoldScraper
from telegram_bot import TelegramAlertBot

from config import MIN_WEIGHT, MIN_DISCOUNT_PERCENTAGE, PAYMENT_MODES_ALLOWED, PURITY_MAPPING, GOODRETURNS_CITY


def _to_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _purity_factor(purity: str) -> float:
    if not purity:
        return 0.999
    p = str(purity).upper().strip()
    if p in PURITY_MAPPING:
        return float(PURITY_MAPPING[p])
    if p.isdigit():
        n = float(p)
        if n > 10:  # 999/995/916
            return n / 1000.0
    if p.endswith("K"):
        try:
            return float(p.replace("K", "")) / 24.0
        except Exception:
            return 0.999
    return 0.999


def fetch_goodreturns_24k_per_gram(city: str) -> float:
    """
    Scrapes Goodreturns city page and returns 24K Gold /g as float.
    Fallback: env GOODRETURNS_24K_PRICE if scraping fails.
    """
    fallback = _to_float(os.getenv("GOODRETURNS_24K_PRICE", "0"), 0.0)

    city = (city or "hyderabad").lower().strip()
    url = f"https://www.goodreturns.in/gold-rates/{city}.html"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml"
        }
        html = requests.get(url, headers=headers, timeout=20).text

        # Typical Goodreturns snippet includes: "24K Gold /g ₹15,246"
        # We capture the ₹ value
        m = re.search(r"24K\s+Gold\s*/g\s*₹\s*([0-9,]+)", html, re.IGNORECASE)
        if not m:
            # Some pages may have spacing variants
            m = re.search(r"24K\s*Gold\s*/g\s*₹\s*([0-9,]+)", html, re.IGNORECASE)

        if m:
            val = float(m.group(1).replace(",", ""))
            if val > 0:
                return val

        # If parsing fails, fallback
        return fallback

    except Exception:
        return fallback


async def main():
    test_run = str(os.getenv("TEST_RUN", "false")).lower() == "true"
    force_scan = str(os.getenv("FORCE_SCAN", "false")).lower() == "true"

    print("🔄 Starting Gold Deal Scanner...")
    print(f"Time: {datetime.utcnow().ctime()}")
    print(f"Test Run: {test_run}")
    print(f"Force Scan: {force_scan}")

    # ✅ Live Goodreturns reference (24K per gram)
    goodreturns_24k = fetch_goodreturns_24k_per_gram(GOODRETURNS_CITY)
    if goodreturns_24k <= 0:
        # Hard stop: if we cannot get reference, don't spam wrong alerts
        print("❌ Goodreturns reference not available. Set env GOODRETURNS_24K_PRICE.")
        return

    print(f"✅ Goodreturns 24K reference (₹/g): {goodreturns_24k}")

    scraper = GoldScraper()
    bot = TelegramAlertBot()

    products = scraper.scrape_all_with_cache(force_refresh=force_scan)

    deals = []
    for p in products:
        weight = _to_float(p.get("weight_grams"), 0.0)
        if weight < MIN_WEIGHT:
            continue

        # Payment mode filter (best mode computed by gold_scraper)
        best_mode = (p.get("best_payment_mode") or "").strip()
        if PAYMENT_MODES_ALLOWED and best_mode and best_mode not in PAYMENT_MODES_ALLOWED:
            continue

        selling_price = _to_float(p.get("selling_price"), 0.0)
        effective_price = _to_float(p.get("effective_price"), selling_price)
        if effective_price <= 0:
            continue

        purity = p.get("purity") or "999"
        pf = _purity_factor(purity)

        # ✅ Only reference: Goodreturns 24K adjusted to product purity
        ref_pg = goodreturns_24k * pf
        eff_pg = effective_price / weight

        # ✅ Deal rule: effective <= reference (no GST, no making)
        is_deal = eff_pg <= ref_pg

        if not is_deal:
            continue

        # ✅ Discount% ONLY vs Goodreturns reference (purity-adjusted)
        discount_pct = ((ref_pg - eff_pg) / ref_pg) * 100.0 if ref_pg > 0 else 0.0

        # Overwrite fields used by telegram formatting so nothing random can appear
        p["goodreturns_24k_price"] = round(goodreturns_24k, 2)
        p["goodreturns_fair_price_per_gram"] = round(ref_pg, 2)      # fair = reference only
        p["effective_price_per_gram"] = round(eff_pg, 2)

        # Make telegram show “Expected Value” as reference total (no GST/making)
        expected_total = ref_pg * weight
        p["expected_price"] = round(expected_total, 2)

        # IMPORTANT: overwrite discount_percent so old logic cannot leak in
        p["discount_percent"] = round(discount_pct, 2)

        # Optional filter: apply your threshold on THIS Goodreturns-based discount%
        if p["discount_percent"] >= MIN_DISCOUNT_PERCENTAGE:
            deals.append(p)

    # Best deals first: most below reference (more negative is better)
    def margin(item):
        return _to_float(item.get("effective_price_per_gram"), 1e12) - _to_float(item.get("goodreturns_fair_price_per_gram"), 1e12)

    deals.sort(key=margin)

    if test_run:
        print(f"TEST RUN: Found {len(deals)} deals")
        for d in deals[:5]:
            print(
                d.get("title"),
                d.get("effective_price_per_gram"),
                d.get("goodreturns_fair_price_per_gram"),
                d.get("discount_percent"),
            )
        return

    await bot.send_bulk_alerts(deals)


if __name__ == "__main__":
    asyncio.run(main())
