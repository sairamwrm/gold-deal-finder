import os
import asyncio
from datetime import datetime

from gold_scraper import GoldScraper
from telegram_bot import TelegramAlertBot

from config import MIN_WEIGHT, MIN_DISCOUNT_PERCENTAGE, PAYMENT_MODES_ALLOWED
from price_calculator import is_real_deal


def _to_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


async def main():
    test_run = str(os.getenv("TEST_RUN", "false")).lower() == "true"
    force_scan = str(os.getenv("FORCE_SCAN", "false")).lower() == "true"

    print("🔄 Starting Gold Deal Scanner...")
    print(f"Time: {datetime.utcnow().ctime()}")
    print(f"Test Run: {test_run}")
    print(f"Force Scan: {force_scan}")

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

        purity = p.get("purity") or "999"

        # making/gst from your expected price info (if present)
        making_pct = _to_float(p.get("making_charges_percent"), 0.0)
        gst_pct = _to_float(p.get("gst_percent"), 3.0)

        # Goodreturns anchored real-deal test
        deal = is_real_deal(
            total_price=effective_price,
            weight_grams=weight,
            purity=purity,
            making_charges_percent=making_pct,
            gst_percent=gst_pct,
        )

        # If using discount threshold too (optional), keep it as a secondary filter
        discount_percent = _to_float(p.get("discount_percent"), 0.0)

        if deal.get("is_deal"):
            # Attach computed values for telegram formatting
            p["goodreturns_fair_price_per_gram"] = deal.get("fair_price_per_gram")
            p["effective_price_per_gram"] = deal.get("effective_price_per_gram")
            p["goodreturns_24k_price"] = deal.get("goodreturns_24k_price")

            # Optional secondary threshold (leave MIN_DISCOUNT_PERCENTAGE=0 for Goodreturns-only)
            if discount_percent >= MIN_DISCOUNT_PERCENTAGE:
                deals.append(p)

    # Best deals first: biggest margin below fair value
    def margin_below_fair(item):
        eff = _to_float(item.get("effective_price_per_gram"), 10**12)
        fair = _to_float(item.get("goodreturns_fair_price_per_gram"), 10**12)
        return eff - fair  # more negative is better

    deals.sort(key=margin_below_fair)

    if test_run:
        print(f"TEST RUN: Found {len(deals)} deals")
        for d in deals[:5]:
            print(d.get("title"), d.get("effective_price_per_gram"), d.get("goodreturns_fair_price_per_gram"))
        return

    await bot.send_bulk_alerts(deals)


if __name__ == "__main__":
    asyncio.run(main())
