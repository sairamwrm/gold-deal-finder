import os
import json
import asyncio
from pathlib import Path
from datetime import datetime

from gold_scraper import GoldScraper
from telegram_bot import TelegramAlertBot
from config import (
    MIN_WEIGHT,
    MIN_DISCOUNT_PERCENTAGE,
    PAYMENT_MODES_ALLOWED,
    GOODRETURNS_CITY,
)

STATE_FILE = Path(".scanner_state.json")


def read_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def write_state(data):
    try:
        STATE_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def fetch_reference_price():
    """
    Reference = Goodreturns city 24K price per gram
    Fallback = last stored reference
    """
    try:
        from price_calculator import GoldPriceCalculator

        calc = GoldPriceCalculator()
        data = calc.get_live_gold_price()
        val = float(data["gold"]["999_with_gst_10g"]) / 10
        state = read_state()
        state["last_reference"] = val
        write_state(state)
        return val, "spot_with_gst"
    except Exception:
        state = read_state()
        return state.get("last_reference", 0), "last_known"


async def main():
    print("🔄 Starting Gold Deal Scanner...")
    print(f"Time: {datetime.utcnow().ctime()}")

    test_run = os.getenv("TEST_RUN", "false") == "true"
    force_scan = os.getenv("FORCE_SCAN", "false") == "true"

    ref_price, ref_source = fetch_reference_price()
    if ref_price <= 0:
        print("❌ Reference price unavailable")
        return

    print(f"✅ Reference price ₹{ref_price}/g ({ref_source})")

    scraper = GoldScraper()
    bot = TelegramAlertBot()

    products = scraper.scrape_all_with_cache(force_refresh=force_scan)
    deals = []

    for p in products:
        weight = float(p.get("weight_grams", 0))
        if weight < MIN_WEIGHT:
            continue

        eff_price = float(p.get("effective_price", 0))
        if eff_price <= 0:
            continue

        eff_pg = eff_price / weight
        discount_pct = ((ref_price - eff_pg) / ref_price) * 100

        p["effective_price_per_gram"] = round(eff_pg, 2)
        p["reference_price_per_gram"] = round(ref_price, 2)
        p["discount_percent"] = round(discount_pct, 2)

        if eff_pg <= ref_price and discount_pct >= MIN_DISCOUNT_PERCENTAGE:
            deals.append(p)

    # ✅ ALWAYS WRITE SUMMARY FILE (this fixed your crash)
    Path("scan_summary.json").write_text(
        json.dumps({
            "time_utc": datetime.utcnow().isoformat(),
            "reference_price": ref_price,
            "reference_source": ref_source,
            "products_scanned": len(products),
            "deals_found": len(deals)
        }, indent=2)
    )

    if test_run:
        print("TEST RUN ONLY")
        return

    if deals:
        await bot.send_bulk_alerts(deals)
        print("✅ Deals sent")
    else:
        print("ℹ️ No deals found")


if __name__ == "__main__":
    asyncio.run(main())
