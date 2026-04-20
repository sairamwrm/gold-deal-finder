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
        if n > 10:
            return n / 1000.0
    if p.endswith("K"):
        try:
            return float(p.replace("K", "")) / 24.0
        except Exception:
            return 0.999
    return 0.999


def fetch_goodreturns_24k_per_gram(city: str) -> float:
    fallback = _to_float(os.getenv("GOODRETURNS_24K_PRICE", "0"), 0.0)
    city = (city or "hyderabad").lower().strip()
    url = f"https://www.goodreturns.in/gold-rates/{city}.html"

    try:
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html"}
        html = requests.get(url, headers=headers, timeout=20).text

        m = re.search(r"24K\s+Gold\s*/g\s*₹\s*([0-9,]+)", html, re.IGNORECASE)
        if not m:
            m = re.search(r"24K\s*Gold\s*/g\s*₹\s*([0-9,]+)", html, re.IGNORECASE)

        if m:
            val = float(m.group(1).replace(",", ""))
            if val > 0:
                return val

        return fallback
    except Exception:
        return fallback


async def _safe_send(bot: TelegramAlertBot, text: str):
    """
    Try common send methods without breaking if your class uses a different name.
    """
    for method_name in ["send_message", "send_text", "send_text_message", "send_telegram_message"]:
        if hasattr(bot, method_name):
            try:
                await getattr(bot, method_name)(text)
                return
            except Exception:
                pass
    # Fallback: if only bulk exists, do nothing
    print(text)


async def main():
    test_run = str(os.getenv("TEST_RUN", "false")).lower() == "true"
    force_scan = str(os.getenv("FORCE_SCAN", "false")).lower() == "true"

    print("🔄 Starting Gold Deal Scanner...")
    print(f"Time: {datetime.utcnow().ctime()}")
    print(f"Test Run: {test_run}")
    print(f"Force Scan: {force_scan}")

    goodreturns_24k = fetch_goodreturns_24k_per_gram(GOODRETURNS_CITY)
    if goodreturns_24k <= 0:
        print("❌ Goodreturns 24K reference not available. Set env GOODRETURNS_24K_PRICE.")
        return

    print(f"✅ Goodreturns 24K (₹/g) = {goodreturns_24k}")

    scraper = GoldScraper()
    bot = TelegramAlertBot()

    products = scraper.scrape_all_with_cache(force_refresh=force_scan)

    # Debug counters
    total = len(products)
    skipped_weight = 0
    skipped_mode = 0
    skipped_price = 0
    checked = 0
    deals = []
    near = []  # keep closest items even if not deals

    # Normalize allowed modes: if empty string -> allow all
    allowed_modes = [m.strip() for m in PAYMENT_MODES_ALLOWED if str(m).strip()]
    allow_all_modes = len(allowed_modes) == 0

    for p in products:
        weight = _to_float(p.get("weight_grams"), 0.0)
        if weight < MIN_WEIGHT:
            skipped_weight += 1
            continue

        best_mode = (p.get("best_payment_mode") or "").strip()
        if not allow_all_modes and best_mode and best_mode not in allowed_modes:
            skipped_mode += 1
            continue

        selling_price = _to_float(p.get("selling_price"), 0.0)
        effective_price = _to_float(p.get("effective_price"), selling_price)
        if effective_price <= 0:
            skipped_price += 1
            continue

        purity = p.get("purity") or "999"
        pf = _purity_factor(purity)

        # Reference price per gram = Goodreturns 24K * purity factor (NO GST / making)
        ref_pg = goodreturns_24k * pf
        eff_pg = effective_price / weight
        checked += 1

        # % below Goodreturns (negative means above)
        below_pct = ((ref_pg - eff_pg) / ref_pg) * 100.0 if ref_pg > 0 else 0.0

        # Overwrite fields so telegram never uses old random values
        p["goodreturns_24k_price"] = round(goodreturns_24k, 2)
        p["goodreturns_fair_price_per_gram"] = round(ref_pg, 2)
        p["effective_price_per_gram"] = round(eff_pg, 2)
        p["expected_price"] = round(ref_pg * weight, 2)     # reference total
        p["discount_percent"] = round(below_pct, 2)         # BELOW Goodreturns (%)

        # Deal rule
        if eff_pg <= ref_pg and p["discount_percent"] >= MIN_DISCOUNT_PERCENTAGE:
            deals.append(p)
        else:
            # Keep near misses (closest 10 above/below)
            near.append(p)

    # Sort deals: best first (most below)
    deals.sort(key=lambda x: _to_float(x.get("effective_price_per_gram"), 1e12) - _to_float(x.get("goodreturns_fair_price_per_gram"), 1e12))
    # Sort near: closest to reference (absolute gap)
    near.sort(key=lambda x: abs(_to_float(x.get("effective_price_per_gram"), 1e12) - _to_float(x.get("goodreturns_fair_price_per_gram"), 1e12)))

    print("---- DEBUG SUMMARY ----")
    print(f"Total scraped: {total}")
    print(f"Skipped (weight<{MIN_WEIGHT}): {skipped_weight}")
    print(f"Skipped (payment mode filter): {skipped_mode} | Allowed modes={allowed_modes if not allow_all_modes else 'ALL'}")
    print(f"Skipped (bad price): {skipped_price}")
    print(f"Checked: {checked}")
    print(f"Deals found: {len(deals)}")
    print("-----------------------")

    if test_run:
        print("TEST RUN: top 5 closest items to Goodreturns reference")
        for d in near[:5]:
            print(d.get("title"), d.get("effective_price_per_gram"), d.get("goodreturns_fair_price_per_gram"), d.get("discount_percent"))
        return

    if len(deals) == 0:
        # Send "no deals" message with closest 5
        lines = []
        for d in near[:5]:
            lines.append(
                f"- {d.get('title','(no title)')}\n"
                f"  Eff ₹/g: {d.get('effective_price_per_gram')} | Ref ₹/g: {d.get('goodreturns_fair_price_per_gram')} | Below: {d.get('discount_percent')}%\n"
            )
        msg = (
            f"⚠️ No deals found vs Goodreturns ({GOODRETURNS_CITY})\n"
            f"Goodreturns 24K: ₹{goodreturns_24k}/g\n\n"
            f"Closest items:\n" + "\n".join(lines)
        )
        await _safe_send(bot, msg)
        return

    await bot.send_bulk_alerts(deals)


if __name__ == "__main__":
    asyncio.run(main())
