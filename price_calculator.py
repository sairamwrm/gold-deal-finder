import json
import time
import requests
import os
import fcntl
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional
from config import GST_RATE, PURITY_MAPPING, GOODRETURNS_CITY, GOODRETURNS_24K_OVERRIDE
import logging
import threading
from functools import lru_cache

logger = logging.getLogger(__name__)

class GoldPriceCalculator:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self.API_ENDPOINTS = [
            {
                'name': 'myb-be',
                'url': 'https://myb-be.onrender.com/api/rates',
                'parser': self._parse_myb_response
            },
            {
                'name': 'goldprice.org',
                'url': 'https://data-asg.goldprice.org/dbXRates/INR',
                'parser': self._parse_goldprice_response
            }
        ]

        self.CACHE_FILE = Path("bullion_cache.json")
        self.CACHE_TTL = 300
        self._last_api_call = 0
        self._cache_lock = threading.Lock()
        self._min_api_interval = 2

        self.OZ_TO_GRAM = 31.1035
        self.LANDED_MULTIPLIER = 1.11
        self.RETAIL_SPREAD = 700
        self.RTGS_DISCOUNT = 600
        self.JEWELLERY_PREMIUM_22K = 1200

        self.MAKING_CHARGES = {
            'coin_24K': 0.00,
            'coin_22K': 0.00,
            'jewellery_24K': 0.00,
            'jewellery_22K': 0.00,
            'jewellery_18K': 0.00,
            'jewellery_14K': 0.00,
        }

        self._initialized = True

    # ------------------- GOODRETURNS REFERENCE (NEW) -------------------

    def get_goodreturns_24k_per_gram(self) -> Optional[float]:
        """
        Returns Goodreturns 24K per-gram reference for the configured city if possible.
        If GOODRETURNS_24K_OVERRIDE is set, uses it directly (most reliable).
        Otherwise attempts to parse Goodreturns India page and pick configured city.
        """
        # 1) manual override (best stability)
        if GOODRETURNS_24K_OVERRIDE:
            try:
                return float(str(GOODRETURNS_24K_OVERRIDE).replace(",", "").strip())
            except Exception:
                pass

        # 2) parse Goodreturns India page (contains major cities table)
        try:
            url = "https://www.goodreturns.in/gold-rates/"
            html = requests.get(url, timeout=15).text

            # Example text contains "Hyderabad ₹15,578" or similar
            city = (GOODRETURNS_CITY or "Hyderabad").strip()
            pattern = re.compile(rf"{re.escape(city)}\\s+₹\\s*([0-9,]+)", re.IGNORECASE)
            m = pattern.search(html)
            if m:
                return float(m.group(1).replace(",", ""))
        except Exception as e:
            logger.warning(f"Goodreturns parse failed: {e}")

        return None

    def compute_goodreturns_fair_value(self, weight: float, purity: str, product_type: str) -> Dict:
        """
        Computes expected fair total using Goodreturns 24K/g as base,
        purity factor, making charges, and GST (same GST_RATE used elsewhere).
        """
        ref_24k = self.get_goodreturns_24k_per_gram()
        purity_factor = PURITY_MAPPING.get(purity, 0.9167)

        # If no Goodreturns ref, mark unavailable
        if not ref_24k or ref_24k <= 0:
            return {
                "goodreturns_24k_per_gram": None,
                "goodreturns_expected_per_gram": None,
                "goodreturns_expected_total": None
            }

        # making charges key
        charges_key = f'coin_{purity}' if product_type == 'coin' else f'jewellery_{purity}'
        making_charges_percent = self.MAKING_CHARGES.get(
            charges_key,
            0.12 if product_type == 'jewellery' else 0.04
        )

        base_per_gram = ref_24k * purity_factor
        gold_value = base_per_gram * weight
        making = gold_value * making_charges_percent
        gst = (gold_value + making) * (GST_RATE / 100.0)
        total = gold_value + making + gst
        per_gram_total = total / weight if weight > 0 else 0

        return {
            "goodreturns_24k_per_gram": round(ref_24k, 2),
            "goodreturns_expected_per_gram": round(per_gram_total, 2),
            "goodreturns_expected_total": round(total, 2),
            "goodreturns_making_pct": round(making_charges_percent * 100, 2)
        }

    # ------------------- EXISTING PARSERS (UNCHANGED) -------------------

    def _parse_myb_response(self, response_data: Dict) -> Dict:
        spot = response_data['spot']
        gold_products = response_data['goldProducts']
        gold_by_karat = response_data['goldByKarat']
        gold_per_gram = float(gold_products['retail999']) / 10

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "source": "live_api",
            "spot_price_per_gram": round(gold_per_gram, 2),
            "gold": {
                "spot_10g": round(float(spot['gldInr']), 2),
                "retail_999_10g": round(float(gold_products['retail999']), 2),
                "rtgs_999_10g": round(float(gold_products['rtgs999']), 2),
                "999_with_gst_10g": round(float(gold_products['withGst999']), 2),
                "retail_22k_10g": round(float(gold_by_karat['22K']), 2),
                "retail_22k_with_gst_10g": round(float(gold_by_karat['22K']) * (1 + GST_RATE/100), 2),
                "per_gram": {
                    "999_spot": round(float(spot['gldInr']) / 10, 2),
                    "999_landed": round(float(gold_products['withGst999']) / 10, 2),
                    "22k_spot": round(float(gold_by_karat['22K']) / 10, 2),
                    "22k_landed": round(float(gold_by_karat['22K']) / 10, 2),
                }
            },
            "raw_api_response": response_data
        }

    def _parse_goldprice_response(self, response_data: Dict) -> Dict:
        item = response_data["items"][0]
        xau = float(item["xauPrice"])
        gold_per_gram = xau / self.OZ_TO_GRAM

        spot_10g = gold_per_gram * 10
        landed_10g = spot_10g * self.LANDED_MULTIPLIER

        retail_999 = landed_10g + self.RETAIL_SPREAD
        rtgs_999 = landed_10g - self.RTGS_DISCOUNT
        gst_999 = rtgs_999

        base_22k = landed_10g * 0.9167
        retail_22k = base_22k + self.JEWELLERY_PREMIUM_22K
        retail_22k_gst = retail_22k * (1 + GST_RATE/100)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "source": "live_api",
            "spot_price_per_gram": round(gold_per_gram, 2),
            "gold": {
                "spot_10g": round(spot_10g, 2),
                "retail_999_10g": round(retail_999, 2),
                "rtgs_999_10g": round(rtgs_999, 2),
                "999_with_gst_10g": round(gst_999, 2),
                "retail_22k_10g": round(retail_22k, 2),
                "retail_22k_with_gst_10g": round(retail_22k_gst, 2),
                "per_gram": {
                    "999_spot": round(gold_per_gram, 2),
                    "999_landed": round(gold_per_gram * self.LANDED_MULTIPLIER, 2),
                    "22k_spot": round(gold_per_gram * 0.9167, 2),
                    "22k_landed": round((gold_per_gram * 0.9167) * self.LANDED_MULTIPLIER, 2),
                }
            }
        }

    # ------------------- CACHE HELPERS (UNCHANGED) -------------------

    def _read_cache_safe(self) -> Optional[Dict]:
        if not self.CACHE_FILE.exists():
            return None
        try:
            with open(self.CACHE_FILE, 'r') as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    return json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception:
            return None

    def _write_cache_safe(self, data: Dict) -> bool:
        try:
            temp_file = self.CACHE_FILE.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            temp_file.replace(self.CACHE_FILE)
            return True
        except Exception:
            return False

    def _is_cache_valid(self, cached_data: Dict) -> bool:
        try:
            cache_timestamp = datetime.fromisoformat(cached_data.get('timestamp', '2000-01-01'))
            return datetime.now() - cache_timestamp < timedelta(seconds=self.CACHE_TTL)
        except Exception:
            return False

    def _fetch_from_api(self, endpoint_config: Dict) -> Optional[Dict]:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
            }
            response = requests.get(endpoint_config['url'], headers=headers, params=endpoint_config.get('params', {}), timeout=15)
            if response.status_code != 200:
                return None
            data = response.json()
            return endpoint_config['parser'](data)
        except Exception:
            return None

    def get_live_gold_price(self, force_refresh: bool = False) -> Dict:
        with self._cache_lock:
            if not force_refresh:
                cached_data = self._read_cache_safe()
                if cached_data and self._is_cache_valid(cached_data):
                    return cached_data

            current_time = time.time()
            if current_time - self._last_api_call < self._min_api_interval:
                cached_data = self._read_cache_safe()
                if cached_data:
                    cached_data['source'] = 'cached_rate_limited'
                    return cached_data
                time.sleep(self._min_api_interval)

            output = None
            for endpoint in self.API_ENDPOINTS:
                result = self._fetch_from_api(endpoint)
                if result:
                    output = result
                    self._last_api_call = time.time()
                    break

            if output is None:
                output = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "fallback",
                    "spot_price_per_gram": 0,
                    "gold": {"per_gram": {"999_landed": 0, "999_spot": 0, "22k_landed": 0, "22k_spot": 0}}
                }

            self._write_cache_safe(output)
            return output

    # ------------------- EXPECTED PRICE (UPDATED) -------------------

    def calculate_expected_price(self, weight: float, purity: str, product_type: str = 'jewellery') -> Dict:
        gold_data = self.get_live_gold_price()
        purity_factor = PURITY_MAPPING.get(purity, 0.9167)

        # base price from existing logic (kept)
        if purity == '24K':
            base_price_per_gram = gold_data['gold']['per_gram']['999_landed']
        else:
            base_price_per_gram = gold_data['gold']['per_gram']['999_landed'] * purity_factor

        gold_value = base_price_per_gram * weight

        charges_key = f'coin_{purity}' if product_type == 'coin' else f'jewellery_{purity}'
        making_charges_percent = self.MAKING_CHARGES.get(
            charges_key,
            0.12 if product_type == 'jewellery' else 0.04
        )

        making_charges = gold_value * making_charges_percent
        gst_amount = (gold_value + making_charges) * (GST_RATE/100)
        total_expected = gold_value + making_charges + gst_amount
        price_per_gram = total_expected / weight if weight > 0 else 0

        # NEW: Goodreturns fair reference
        gr = self.compute_goodreturns_fair_value(weight, purity, product_type)

        return {
            'source': gold_data.get('source', 'unknown'),
            'spot_price_per_gram': gold_data.get('spot_price_per_gram', 0),
            'landed_price_per_gram': base_price_per_gram,
            'gold_value': round(gold_value, 2),
            'making_charges': round(making_charges, 2),
            'making_charges_percent': round(making_charges_percent * 100, 2),
            'gst': round(gst_amount, 2),
            'gst_percent': GST_RATE,
            'total_expected': round(total_expected, 2),
            'price_per_gram': round(price_per_gram, 2),
            'purity_factor': purity_factor,
            'product_type': product_type,
            'timestamp': gold_data.get('timestamp', datetime.utcnow().isoformat()),
            'data_source': gold_data.get('source', 'live_api'),

            # Goodreturns fields (used by gold_scraper & scanner)
            'goodreturns_24k_per_gram': gr.get("goodreturns_24k_per_gram"),
            'goodreturns_expected_per_gram': gr.get("goodreturns_expected_per_gram"),
            'goodreturns_expected_total': gr.get("goodreturns_expected_total"),
            'goodreturns_making_pct': gr.get("goodreturns_making_pct"),
        }

    def calculate_discount_percentage(self, selling_price: float, expected_price: float) -> float:
        if expected_price <= 0:
            return 0
        discount = ((expected_price - selling_price) / expected_price) * 100
        return round(max(discount, -100), 2)

    @lru_cache(maxsize=1)
    def get_cached_price_summary(self) -> str:
        return self.get_price_summary()

    def get_price_summary(self) -> str:
        gold_data = self.get_live_gold_price()
        gold = gold_data.get('gold', {}).get('per_gram', {})
        ref = self.get_goodreturns_24k_per_gram()
        ref_txt = f"Goodreturns 24K ref: ₹{ref:,.0f}/g" if ref else "Goodreturns ref: N/A"
        return f"📌 {ref_txt}\nAPI 999 landed: ₹{gold.get('999_landed', 0):,.0f}/g"

# ---------------- REAL DEAL CHECK (Goodreturns anchored) ----------------
import os

def _purity_factor_from_string(purity: str) -> float:
    """
    Supports: '24K','22K','18K','14K','999','995','916','750','585'
    Falls back to 0.999 if unknown.
    """
    if purity is None:
        return 0.999
    p = str(purity).upper().strip()

    # If PURITY_MAPPING exists in this module (it does in your file via config import)
    try:
        if p in PURITY_MAPPING:
            return float(PURITY_MAPPING[p])
    except Exception:
        pass

    # Numeric purity like 999 / 995 / 916
    if p.isdigit():
        n = float(p)
        if n > 10:  # 999/995/916 etc
            return n / 1000.0

    # Karat strings
    if p.endswith("K"):
        try:
            k = float(p.replace("K", ""))
            return k / 24.0
        except Exception:
            pass

    return 0.999


def _normalize_pct(x, default=0.0) -> float:
    """
    Accepts 4 or 0.04. Returns fraction: 0.04
    """
    try:
        v = float(x)
    except Exception:
        return float(default)
    if v > 1.0:
        return v / 100.0
    return v


def is_real_deal(
    total_price: float,
    weight_grams: float,
    purity: str,
    making_charges_percent: float = 0.0,
    gst_percent: float = None,
    goodreturns_24k_price: float = None,
) -> dict:
    """
    Returns a dict:
      {
        'is_deal': bool,
        'effective_price_per_gram': float,
        'fair_price_per_gram': float,
        'goodreturns_24k_price': float,
        'purity_factor': float,
        'making_pct': float,
        'gst_pct': float
      }

    Logic:
      effective ₹/g <= (Goodreturns24K ₹/g * purity_factor) * (1 + making + gst)
    """

    # Validate
    if not weight_grams or float(weight_grams) <= 0:
        return {
            "is_deal": False,
            "effective_price_per_gram": None,
            "fair_price_per_gram": None,
            "goodreturns_24k_price": None,
            "purity_factor": None,
            "making_pct": None,
            "gst_pct": None
        }

    eff_pg = float(total_price) / float(weight_grams)

    # Get Goodreturns reference (priority: arg -> config -> env -> fallback)
    if goodreturns_24k_price is None:
        try:
            from config import GOODRETURNS_24K_PRICE
            goodreturns_24k_price = float(GOODRETURNS_24K_PRICE)
        except Exception:
            goodreturns_24k_price = float(os.getenv("GOODRETURNS_24K_PRICE", "0") or 0)

    if not goodreturns_24k_price or goodreturns_24k_price <= 0:
        # If Goodreturns not set, do NOT label as deal (prevents fake alerts)
        return {
            "is_deal": False,
            "effective_price_per_gram": round(eff_pg, 2),
            "fair_price_per_gram": None,
            "goodreturns_24k_price": None,
            "purity_factor": _purity_factor_from_string(purity),
            "making_pct": _normalize_pct(making_charges_percent, 0.0),
            "gst_pct": None
        }

    purity_factor = _purity_factor_from_string(purity)

    making_pct = _normalize_pct(making_charges_percent, 0.0)

    # gst_percent: if not provided, use GST_RATE from config import in this file.
    if gst_percent is None:
        try:
            gst_percent = float(GST_RATE)  # in your code GST_RATE is like 3 (percent)
        except Exception:
            gst_percent = 3.0

    gst_pct = _normalize_pct(gst_percent, 0.03)  # 3 => 0.03

    # Fair price per gram based on Goodreturns
    base_pg = float(goodreturns_24k_price) * float(purity_factor)
    fair_pg = base_pg * (1.0 + making_pct + gst_pct)

    return {
        "is_deal": eff_pg <= fair_pg,
        "effective_price_per_gram": round(eff_pg, 2),
        "fair_price_per_gram": round(fair_pg, 2),
        "goodreturns_24k_price": round(float(goodreturns_24k_price), 2),
        "purity_factor": round(float(purity_factor), 6),
        "making_pct": round(float(making_pct), 6),
        "gst_pct": round(float(gst_pct), 6),
    }
