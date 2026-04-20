import json
from pathlib import Path
import requests
import re
from price_calculator import GoldPriceCalculator
import datetime

STATE_PATH = Path(".scanner_state.json")

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

def _get_last_ref() -> float:
    st = _state_read()
    try:
        return float(st.get("last_reference_24k_per_gram", 0) or 0)
    except Exception:
        return 0.0

def _set_last_ref(val: float, source: str):
    st = _state_read()
    st["last_reference_24k_per_gram"] = round(float(val), 2)
    st["last_reference_source"] = source
    _state_write(st)

def fetch_reference_24k_per_gram(city: str, force_refresh: bool = False):
    """
    Fully automatic reference rate (no manual env):
      1) Goodreturns city scrape (24K Gold /g)  (typically excludes GST) [1](https://arcadiso365.sharepoint.com/teams/ch-103134961/_layouts/15/Doc.aspx?sourcedoc=%7B03D4A538-C175-4F7A-A9EC-18FAD0F84C67%7D&file=Bid%20Model%20Spreadsheet_ARTC%20Sandy%20Creek.xlsm&action=default&mobileredirect=true&DefaultItemOpen=1)
      2) Fallback: Spot price WITH GST from GoldPriceCalculator (999_with_gst_10g / 10)
      3) Backup: last_reference_24k_per_gram stored in .scanner_state.json

    Returns: (value_float, source_string)
    """
    last_val = _get_last_ref()

    # ---- 1) Goodreturns scrape ----
    try:
        city = (city or "hyderabad").lower().strip()
        url = f"https://www.goodreturns.in/gold-rates/{city}.html"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        }
        r = requests.get(url, headers=headers, timeout=25, allow_redirects=True)
        if r.status_code == 200:
            html = r.text
            # Example Goodreturns pattern: "24K Gold /g ₹15,246" [1](https://arcadiso365.sharepoint.com/teams/ch-103134961/_layouts/15/Doc.aspx?sourcedoc=%7B03D4A538-C175-4F7A-A9EC-18FAD0F84C67%7D&file=Bid%20Model%20Spreadsheet_ARTC%20Sandy%20Creek.xlsm&action=default&mobileredirect=true&DefaultItemOpen=1)
            m = re.search(r"24K\s*Gold\s*/g\s*₹\s*([0-9,]+)", html, re.IGNORECASE)
            if m:
                val = float(m.group(1).replace(",", ""))
                if val > 0:
                    _set_last_ref(val, "goodreturns")
                    return val, "goodreturns"
    except Exception:
        pass

    # ---- 2) Fallback: Spot WITH GST (auto) ----
    try:
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

    # ---- 3) Backup: last known ----
    if last_val and last_val > 0:
        return float(last_val), "last_known"

    return 0.0, "unavailable"
    from pathlib import Path
import json

Path("scan_summary.json").write_text(json.dumps({
    "time_utc": datetime.datetime.utcnow().isoformat(),
    "total_products": len(products),
    "deals_found": len(deals)
}, indent=2), encoding="utf-8")
