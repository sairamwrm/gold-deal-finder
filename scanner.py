import os
import re
import json
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime, timezone

import requests

from gold_scraper import GoldScraper
from telegram_bot import TelegramAlertBot
from config import MIN_WEIGHT, MIN_DISCOUNT_PERCENTAGE, PAYMENT_MODES_ALLOWED, GOODRETURNS_CITY, PURITY_MAPPING

STATE_PATH = Path(".scanner_state.json")

for i in range(5):
    run_scan_once()
    if i < 4:
        time.sleep(60)
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


def _state_read() -> dict:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _state_write(st: dict):
    try:
        STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
    except Exception:
        pass


def _set_last_ref(val: float, source: str):
    st = _state_read()
    st["last_reference_24k_per_gram"] = round(float(val), 2)
    st["last_reference_source"] = source
    st["last_reference_updated_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _state_write(st)


def _get_last_ref() -> float:
    st = _state_read()
    return _to_float(st.get("last_reference_24k_per_gram"), 0.0)


def fetch_reference_24k_per_gram(city: str, force_refresh: bool = False):
    """
    Auto reference:
      1) Goodreturns scrape (if works)
      2) Fallback: spot-with-GST from GoldPriceCalculator
      3) Backup: last_known from .scanner_state.json
    """
    last_val = _get_last_ref()

    # 1) Try Goodreturns
    try:
        city = (city or "hyderabad").lower().strip()
        url = f"https://www.goodreturns.in/gold-rates/{city}.html"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }
        r = requests.get(url, headers=headers, timeout=25, allow_redirects=True)
        if r.status_code == 200:
            html = r.text
            m = re.search(r"24K\s*Gold\s*/g\s*₹\s*([0-9,]+)", html, re.IGNORECASE)
            if m:
                val = float(m.group(1).replace(",", ""))
                if val > 0:
                    _set_last_ref(val, "goodreturns")
                    return val, "goodreturns"
    except Exception:
        pass

    # 2) Fallback: Spot with GST
    try:
        from price_calculator import GoldPriceCalculator
        calc = GoldPriceCalculator()
        data = calc.get_live_gold_price(force_refresh=force_refresh)
        gold = data.get("gold", {})
        gst_10g = gold.get("999_with_gst_10g")
        if gst_10g and float(gst_10g) > 0:
            val = float(gst_10g) / 10.0
            _set_last_ref(val, "spot_with_gst")
            return val, "spot_with_gst"
    except Exception:
        pass

    # 3) Backup last-known
    if last_val > 0:
        return last_val, "last_known"

    return 0.0, "unavailable"


def _hash_payload(payload: dict) -> str:
    s = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _should_send(tag: str, new_hash: str) -> bool:
    st = _state_read()
    return st.get(f"last_{tag}_hash") != new_hash


def _mark_sent(tag: str, new_hash: str):
    st = _state_read()
    st[f"last_{tag}_hash"] = new_hash
    st[f"last_{tag}_sent_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _state_write(st)


async def _safe_send(bot: TelegramAlertBot, text: str):
    for method_name in ["send_message", "send_text", "send_text_message", "send_telegram_message"]:
        if hasattr(bot, method_name):
            try:
                await getattr(bot, method_name)(text)
                return True
            except Exception:
                pass
    return False


def _normalize_allowed_modes():
    allowed = [m.strip() for m in PAYMENT_MODES_ALLOWED if str(m).strip()]
    return allowed, (len(allowed) == 0)


def run_one_scan(products, ref_24k, ref_source):
    allowed_modes, allow_all_modes = _normalize_allowed_modes()

    deals = []
    near = []

    total = len(products)
    skipped_weight = skipped_mode = skipped_price = checked = 0

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

        ref_pg = ref_24k * pf
        eff_pg = effective_price / weight
        checked += 1

        below_pct = ((ref_pg - eff_pg) / ref_pg) * 100.0 if ref_pg > 0 else 0.0

        # overwrite fields for consistent telegram formatting
        p["reference_source"] = ref_source
        p["reference_24k_price"] = round(ref_24k, 2)
        p["goodreturns_fair_price_per_gram"] = round(ref_pg, 2)
        p["effective_price_per_gram"] = round(eff_pg, 2)
        p["expected_price"] = round(ref_pg * weight, 2)
        p["discount_percent"] = round(below_pct, 2)

        if eff_pg <= ref_pg and p["discount_percent"] >= MIN_DISCOUNT_PERCENTAGE:
            deals.append(p)
        else:
            near.append(p)

    deals.sort(key=lambda x: _to_float(x.get("effective_price_per_gram"), 1e12) - _to_float(x.get("goodreturns_fair_price_per_gram"), 1e12))
    near.sort(key=lambda x: abs(_to_float(x.get("effective_price_per_gram"), 1e12) - _to_float(x.get("goodreturns_fair_price_per_gram"), 1e12)))

    stats = {
        "total_products": total,
        "checked": checked,
        "deals_found": len(deals),
        "skipped_weight": skipped_weight,
        "skipped_mode": skipped_mode,
        "skipped_price": skipped_price,
    }
    return deals, near, stats


async def main():
    test_run = str(os.getenv("TEST_RUN", "false")).lower() == "true"
    force_scan = str(os.getenv("FORCE_SCAN", "false")).lower() == "true"

    print("🔄 Starting Gold Deal Scanner...")
    print(f"Time: {datetime.utcnow().ctime()}")
    print(f"Test Run: {test_run}")
    print(f"Force Scan: {force_scan}")

    ref_24k, ref_source = fetch_reference_24k_per_gram(GOODRETURNS_CITY, force_refresh=force_scan)
    if ref_24k <= 0:
        print("❌ Reference 24K unavailable.")
        return

    scraper = GoldScraper()
    bot = TelegramAlertBot()

    products = scraper.scrape_all_with_cache(force_refresh=force_scan)

    # ⚡ Burst scanning: 5 scans 60 seconds apart
    burst_scans = 5
    best_deals = []
    best_near = []
    last_stats = {}

    for i in range(burst_scans):
        print(f"⚡ Burst scan {i+1}/{burst_scans}")
        deals, near, stats = run_one_scan(products, ref_24k, ref_source)
        last_stats = stats
        if deals:
            best_deals = deals
        if near:
            best_near = near
        if i < burst_scans - 1:
            await asyncio.sleep(60)

    # ✅ Always write summary artifact
    Path("scan_summary.json").write_text(
        json.dumps({
            "time_utc": datetime.utcnow().isoformat(),
            "reference_city": GOODRETURNS_CITY,
            "reference_source": ref_source,
            "reference_24k_per_gram": round(ref_24k, 2),
            "burst_scans": burst_scans,
            "stats": last_stats,
            "closest_items": [
                {
                    "title": (x.get("title") or "")[:120],
                    "eff_pg": x.get("effective_price_per_gram"),
                    "ref_pg": x.get("goodreturns_fair_price_per_gram"),
                    "discount_percent": x.get("discount_percent"),
                    "url": x.get("url") or ""
                }
                for x in (best_near[:5] if best_near else [])
            ]
        }, indent=2),
        encoding="utf-8"
    )

    if test_run:
        return

    # Dedup messaging
    if not best_deals:
        closest = []
        for d in (best_near[:5] if best_near else []):
            closest.append({
                "title": (d.get("title") or "")[:120],
                "eff_pg": _to_float(d.get("effective_price_per_gram"), 0.0),
                "ref_pg": _to_float(d.get("goodreturns_fair_price_per_gram"), 0.0),
                "url": d.get("url") or ""
            })

        payload = {
            "type": "no_deals",
            "city": GOODRETURNS_CITY,
            "reference_source": ref_source,
            "reference_24k": round(ref_24k, 2),
            "closest": closest
        }
        h = _hash_payload(payload)

        if _should_send("no_deals", h):
            msg = f"⚠️ No deals found (burst {burst_scans} scans)\nRef: {ref_source} ₹{round(ref_24k,2)}/g"
            await _safe_send(bot, msg)
            _mark_sent("no_deals", h)
        return

    top_deals = []
    for d in best_deals[:10]:
        top_deals.append({
            "title": (d.get("title") or "")[:120],
            "eff_pg": _to_float(d.get("effective_price_per_gram"), 0.0),
            "ref_pg": _to_float(d.get("goodreturns_fair_price_per_gram"), 0.0),
            "url": d.get("url") or ""
        })

    payload = {"type": "deals", "city": GOODRETURNS_CITY, "reference_source": ref_source, "items": top_deals}
    h = _hash_payload(payload)

    if not _should_send("deals", h):
        return

    await bot.send_bulk_alerts(best_deals)
    _mark_sent("deals", h)


if __name__ == "__main__":
    asyncio.run(main())
