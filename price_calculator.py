import json
import time
import requests
import os
import fcntl
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging
import threading
from functools import lru_cache

from config import GST_RATE, PURITY_MAPPING, GOODRETURNS_24K_PRICE, GOODRETURNS_TOLERANCE_PCT

logger = logging.getLogger(__name__)


class GoldPriceCalculator:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        # Singleton pattern to ensure only one instance exists
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        # Multiple API endpoints for redundancy
        self.API_ENDPOINTS = [
            {
                "name": "myb-be",
                "url": "https://myb-be.onrender.com/api/rates",
                "parser": self._parse_myb_response,
            },
            {
                "name": "goldprice.org",
                "url": "https://data-asg.goldprice.org/dbXRates/INR",
                "parser": self._parse_goldprice_response,
            },
        ]

        self.CACHE_FILE = Path("bullion_cache.json")
        self.CACHE_TTL = 300  # 5 minutes
        self._last_api_call = 0
        self._cache_lock = threading.Lock()
        self._min_api_interval = 2

        # Constants
        self.OZ_TO_GRAM = 31.1035
        self.LANDED_MULTIPLIER = 1.11
        self.RETAIL_SPREAD = 700     # for 10g
        self.RTGS_DISCOUNT = 600     # for 10g
        self.JEWELLERY_PREMIUM_22K = 1200  # for 10g

        # Making charges (fractions)
        self.MAKING_CHARGES = {
            "coin_24K": 0.00,
            "coin_22K": 0.00,
            "coin_995": 0.00,
            "coin_999": 0.00,

            "jewellery_24K": 0.00,
            "jewellery_22K": 0.00,
            "jewellery_18K": 0.00,
            "jewellery_14K": 0.00,
        }

        self._initialized = True

    # ---------------- API Parsers ----------------

    def _parse_myb_response(self, response_data: Dict) -> Dict:
        """
        Parse response from myb-be API and return normalized data.
        NOTE: myb-be seems to provide GST-inclusive values already in some fields.
        """
        spot = response_data["spot"]
        gold_products = response_data["goldProducts"]
        silver_products = response_data["silverProducts"]
        gold_by_karat = response_data["goldByKarat"]

        gold_per_gram = float(gold_products["retail999"]) / 10.0

        output = {
            "timestamp": datetime.utcnow().isoformat(),
            "source": "live_api",
            "spot_price_per_gram": round(gold_per_gram, 2),
            "gold": {
                "spot_10g": round(float(spot["gldInr"]), 2),
                "retail_999_10g": round(float(gold_products["retail999"]), 2),
                "rtgs_999_10g": round(float(gold_products["rtgs999"]), 2),
                "999_with_gst_10g": round(float(gold_products["withGst999"]), 2),
                "retail_22k_10g": round(float(gold_by_karat["22K"]), 2),
                "retail_22k_with_gst_10g": round(float(gold_by_karat["22K"]) * (1 + GST_RATE / 100), 2),
                "per_gram": {
                    "999_spot": round(float(spot["gldInr"]) / 10, 2),
                    "999_landed": round(float(gold_products["withGst999"]) / 10, 2),
                    "22k_spot": round(float(gold_by_karat["22K"]) / 10, 2),
                    "22k_landed": round(float(gold_by_karat["22K"]) / 10, 2),
                },
            },
            "silver": {
                "per_gram": round(float(silver_products["retail999"]) / 1000, 2),
                "per_kg": round(float(silver_products["retail999"]), 2),
            },
            "raw_api_response": response_data,
        }

        logger.info("Successfully parsed myb-be response")
        return output

    def _parse_goldprice_response(self, response_data: Dict) -> Dict:
        """
        Parse response from goldprice.org and calculate all derived prices.
        """
        item = response_data["items"][0]
        xau = float(item["xauPrice"])  # INR per troy ounce
        xag = float(item["xagPrice"])

        gold_per_gram = xau / self.OZ_TO_GRAM
        silver_per_gram = xag / self.OZ_TO_GRAM

        spot_10g = gold_per_gram * 10
        landed_10g = spot_10g * self.LANDED_MULTIPLIER

        retail_999 = landed_10g + self.RETAIL_SPREAD
        rtgs_999 = landed_10g - self.RTGS_DISCOUNT
        gst_999 = rtgs_999

        base_22k = landed_10g * 0.9167
        retail_22k = base_22k + self.JEWELLERY_PREMIUM_22K
        retail_22k_gst = retail_22k * (1 + GST_RATE / 100)

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
                },
            },
            "silver": {
                "per_gram": round(silver_per_gram, 2),
                "per_kg": round(silver_per_gram * 1000, 2),
            },
        }

    # ---------------- Cache helpers ----------------

    def _read_cache_safe(self) -> Optional[Dict]:
        if not self.CACHE_FILE.exists():
            return None
        try:
            with open(self.CACHE_FILE, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    return json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e:
            logger.warning(f"Error reading cache: {e}")
            return None

    def _write_cache_safe(self, data: Dict) -> bool:
        try:
            temp_file = self.CACHE_FILE.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            temp_file.replace(self.CACHE_FILE)
            return True
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
            return False

    def _is_cache_valid(self, cached_data: Dict) -> bool:
        try:
            cache_timestamp = datetime.fromisoformat(cached_data.get("timestamp", "2000-01-01"))
            return datetime.now() - cache_timestamp < timedelta(seconds=self.CACHE_TTL)
        except Exception:
            return False

    def _fetch_from_api(self, endpoint_config: Dict) -> Optional[Dict]:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            }
            params = endpoint_config.get("params", {})
            logger.info(f"Trying {endpoint_config['name']} API...")
            response = requests.get(endpoint_config["url"], headers=headers, params=params, timeout=15)

            if response.status_code != 200:
                logger.warning(f"{endpoint_config['name']} returned status {response.status_code}")
                return None

            data = response.json()
            output = endpoint_config["parser"](data)
            logger.info(f"Successfully fetched from {endpoint_config['name']}")
            return output

        except Exception as e:
            logger.warning(f"Error with {endpoint_config['name']}: {e}")
            return None

    # ---------------- Public methods ----------------

    def get_live_gold_price(self, force_refresh: bool = False) -> Dict:
        with self._cache_lock:
            if not force_refresh:
                cached = self._read_cache_safe()
                if cached and self._is_cache_valid(cached):
                    return cached

            current_time = time.time()
            if current_time - self._last_api_call < self._min_api_interval:
                cached = self._read_cache_safe()
                if cached:
                    cached["source"] = "cached_rate_limited"
                    return cached
                time.sleep(self._min_api_interval)

            output = None
            for endpoint in self.API_ENDPOINTS:
                result = self._fetch_from_api(endpoint)
                if result:
                    output = result
                    self._last_api_call = time.time()
                    break

            if output is None:
                return self._calculate_fallback_prices()

            self._write_cache_safe(output)
            return output

    def _calculate_fallback_prices(self) -> Dict:
        cached = self._read_cache_safe()
        if cached:
            cached["source"] = "cached_fallback"
            cached["timestamp"] = datetime.utcnow().isoformat()
            return cached

        gold_per_gram = 7010.4176
        spot_10g = gold_per_gram * 10
        landed_10g = spot_10g * self.LANDED_MULTIPLIER

        retail_999 = landed_10g + self.RETAIL_SPREAD
        rtgs_999 = landed_10g - self.RTGS_DISCOUNT
        gst_999 = rtgs_999 * (1 + GST_RATE / 100)

        base_22k = landed_10g * 0.9167
        retail_22k = base_22k + self.JEWELLERY_PREMIUM_22K
        retail_22k_gst = retail_22k * (1 + GST_RATE / 100)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "source": "hardcoded_fallback",
            "spot_price_per_gram": gold_per_gram,
            "gold": {
                "spot_10g": round(spot_10g, 2),
                "retail_999_10g": round(retail_999, 2),
                "rtgs_999_10g": round(rtgs_999, 2),
                "999_with_gst_10g": round(gst_999, 2),
                "retail_22k_10g": round(retail_22k, 2),
                "retail_22k_with_gst_10g": round(retail_22k_gst, 2),
                "per_gram": {
                    "999_spot": gold_per_gram,
                    "999_landed": round(gold_per_gram * self.LANDED_MULTIPLIER, 2),
                    "22k_spot": round(gold_per_gram * 0.9167, 2),
                    "22k_landed": round((gold_per_gram * 0.9167) * self.LANDED_MULTIPLIER, 2),
                },
            },
            "silver": {
                "per_gram": round(gold_per_gram / 80, 2),
                "per_kg": round(gold_per_gram / 80 * 1000, 2),
            },
        }

    def calculate_expected_price(self, weight: float, purity: str, product_type: str = "jewellery") -> Dict:
        gold_data = self.get_live_gold_price()
        purity_factor = PURITY_MAPPING.get(purity, 0.9167)

        if purity == "24K":
            base_price_per_gram = gold_data["gold"]["per_gram"]["999_landed"]
        else:
            if "raw_api_response" in gold_data and "goldByKarat" in gold_data["raw_api_response"]:
                karat_price_10g = float(gold_data["raw_api_response"]["goldByKarat"].get(purity, 0))
                if karat_price_10g > 0:
                    base_price_per_gram = karat_price_10g / 10
                else:
                    base_price_per_gram = gold_data["gold"]["per_gram"]["999_landed"] * purity_factor
            else:
                base_price_per_gram = gold_data["gold"]["per_gram"]["999_landed"] * purity_factor

        gold_value = base_price_per_gram * weight

        if product_type == "coin":
            charges_key = f"coin_{purity}"
        else:
            charges_key = f"jewellery_{purity}"

        making_charges_percent = self.MAKING_CHARGES.get(
            charges_key,
            0.12 if product_type == "jewellery" else 0.04
        )

        making_charges = gold_value * making_charges_percent
        gst_amount = (gold_value + making_charges) * (GST_RATE / 100)
        total_expected = gold_value + making_charges + gst_amount
        price_per_gram = total_expected / weight if weight > 0 else 0

        return {
            "source": gold_data.get("source", "unknown"),
            "spot_price_per_gram": gold_data["spot_price_per_gram"],
            "landed_price_per_gram": base_price_per_gram,
            "gold_value": round(gold_value, 2),
            "making_charges": round(making_charges, 2),
            "making_charges_percent": round(making_charges_percent * 100, 2),
            "gst": round(gst_amount, 2),
            "gst_percent": GST_RATE,
            "total_expected": round(total_expected, 2),
            "price_per_gram": round(price_per_gram, 2),
            "purity_factor": purity_factor,
            "product_type": product_type,
            "timestamp": gold_data["timestamp"],
            "data_source": gold_data.get("source", "live_api"),
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
        gold = gold_data["gold"]
        source = gold_data.get("source", "live_api")

        source_emoji = "🟢" if source == "live_api" else "🟡" if "cached" in source else "🔴"

        summary = f"""
{source_emoji} <b>Current Gold Prices</b> {source_emoji}

<b>24K (999) Gold:</b>
├ Spot (10g): ₹{gold['spot_10g']:,.0f}
├ Landed (10g): ₹{gold['retail_999_10g']:,.0f}
├ With GST (10g): ₹{gold['999_with_gst_10g']:,.0f}
└ Per gram: ₹{gold['per_gram']['999_landed']:,.0f}

<b>22K Gold (Jewellery):</b>
├ Retail (10g): ₹{gold['retail_22k_10g']:,.0f}
├ With GST (10g): ₹{gold['retail_22k_with_gst_10g']:,.0f}
└ Per gram: ₹{gold['per_gram']['22k_landed']:,.0f}

<i>Source: {source.replace('_', ' ').title()}
Last updated: {datetime.fromisoformat(gold_data['timestamp']).strftime('%d %b %Y, %I:%M %p')}</i>
"""
        return summary


# =====================================================================
# Goodreturns anchored "Real Deal" function (scanner imports this)
# =====================================================================

def _purity_factor_from_string(purity: str) -> float:
    if purity is None:
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


def _pct_to_fraction(v, default=0.0) -> float:
    try:
        x = float(v)
    except Exception:
        return float(default)
    return x / 100.0 if x > 1.0 else x


def is_real_deal(total_price: float,
                 weight_grams: float,
                 purity: str,
                 making_charges_percent: float = 0.0,
                 gst_percent: float = None,
                 goodreturns_24k_price: float = None,
                 tolerance_pct: float = None) -> dict:
    """
    effective ₹/g <= (Goodreturns24K ₹/g * purity_factor) * (1 + making + gst) * (1 + tolerance)
    """
    if not weight_grams or float(weight_grams) <= 0:
        return {"is_deal": False, "effective_price_per_gram": None, "fair_price_per_gram": None}

    eff_pg = float(total_price) / float(weight_grams)

    if goodreturns_24k_price is None:
        goodreturns_24k_price = float(GOODRETURNS_24K_PRICE)

    if tolerance_pct is None:
        tolerance_pct = float(GOODRETURNS_TOLERANCE_PCT)

    if gst_percent is None:
        gst_percent = float(GST_RATE)

    purity_factor = _purity_factor_from_string(purity)
    making_frac = _pct_to_fraction(making_charges_percent, 0.0)
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
