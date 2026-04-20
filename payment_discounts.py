import json
import time
import requests
import os
import fcntl
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from config import GST_RATE, PURITY_MAPPING, GOODRETURNS_CITY
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
        if hasattr(self, "_initialized"):
            return

        self.API_ENDPOINTS = [
            {"name": "myb-be", "url": "https://myb-be.onrender.com/api/rates", "parser": self._parse_myb_response},
            {"name": "goldprice.org", "url": "https://data-asg.goldprice.org/dbXRates/INR", "parser": self._parse_goldprice_response},
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

        # Your code defaults to 0.04 for coins and 0.12 for jewellery if not found.
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

        self._goodreturns_cache: Optional[Dict] = None
        self._goodreturns_cache_ts: float = 0.0
        self._goodreturns_ttl = 600  # 10 minutes

        self._initialized = True

    # -------------------- Goodreturns helpers --------------------

    def get_goodreturns_rates(self, city: str = None) -> Optional[Dict]:
        """
        Fetch Goodreturns 24K/22K/18K per-gram rates.
        Note: Goodreturns pages state rates are indicative and do not include GST/TCS/levies. [1](https://www.goodreturns.in/gold-rates/hyderabad.html)[2](https://www.goodreturns.in/gold-rates/)
        We treat these as EX-GST reference rates.
        """
        city = (city or GOODRETURNS_CITY or "hyderabad").strip().lower()

        now = time.time()
        if self._goodreturns_cache and (now - self._goodreturns_cache_ts) < self._goodreturns_ttl:
            return self._goodreturns_cache

        url = "https://www.goodreturns.in/gold-rates/hyderabad.html" if city == "hyderabad" else "https://www.goodreturns.in/gold-rates/"

        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return None
            text = r.text

            # Patterns like: "24K Gold /g ₹15,246" or "24K Gold /g ₹15,578"
            def extract(pattern: str) -> Optional[float]:
                m = re.search(pattern, text, flags=re.IGNORECASE)
                if not m:
                    return None
                val = m.group(1).replace(",", "").strip()
                try:
                    return float(val)
                except Exception:
                    return None

            g24 = extract(r"24K\s*Gold\s*/g\s*₹\s*([\d,]+)")
            g22 = extract(r"22K\s*Gold\s*/g\s*₹\s*([\d,]+)")
            g18 = extract(r"18K\s*Gold\s*/g\s*₹\s*([\d,]+)")

            if not g24:
                return None

            out = {"city": city, "24K": g24, "22K": g22, "18K": g18, "fetched_at": datetime.utcnow().isoformat(), "url": url}
            self._goodreturns_cache = out
            self._goodreturns_cache_ts = now
            return out
        except Exception:
            return None

    def goodreturns_ref_per_gram(self, purity: str, city: str = None) -> Optional[float]:
        rates = self.get_goodreturns_rates(city=city)
        if not rates:
            return None

        purity = (purity or "").strip()
        if purity in ("24K", "999"):
            return float(rates["24K"])
        if purity == "995":
            return float(rates["24K"]) * 0.995
        if purity in ("22K", "916") and rates.get("22K"):
            return float(rates["22K"])
        if purity in ("18K", "750") and rates.get("18K"):
            return float(rates["18K"])
        # fallback: scale from 24K
        factor = PURITY_MAPPING.get(purity, 0.9167)
        return float(rates["24K"]) * factor

    # -------------------- API parsers --------------------

    def _parse_myb_response(self, response_data: Dict) -> Dict:
        spot = response_data["spot"]
        gold_products = response_data["goldProducts"]
        silver_products = response_data["silverProducts"]
        gold_by_karat = response_data["goldByKarat"]

        gold_per_gram = float(gold_products["retail999"]) / 10

        return {
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
            "silver": {"per_gram": round(float(silver_products["retail999"]) / 1000, 2), "per_kg": round(float(silver_products["retail999"]), 2)},
            "raw_api_response": response_data,
        }

    def _parse_goldprice_response(self, response_data: Dict) -> Dict:
        item = response_data["items"][0]
        xau = float(item["xauPrice"])
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
            "silver": {"per_gram": round(silver_per_gram, 2), "per_kg": round(silver_per_gram * 1000, 2)},
        }

    # -------------------- Cache helpers --------------------

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
        except Exception:
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
        except Exception:
            return False

    def _is_cache_valid(self, cached_data: Dict) -> bool:
        try:
            cache_timestamp = datetime.fromisoformat(cached_data.get("timestamp", "2000-01-01"))
            return datetime.now() - cache_timestamp < timedelta(seconds=self.CACHE_TTL)
        except Exception:
            return False

    def _fetch_from_api(self, endpoint_config: Dict) -> Optional[Dict]:
        try:
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            response = requests.get(endpoint_config["url"], headers=headers, params=endpoint_config.get("params", {}), timeout=15)
            if response.status_code != 200:
                return None
            data = response.json()
            return endpoint_config["parser"](data)
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
                    cached_data["source"] = "cached_rate_limited"
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
                return self._calculate_fallback_prices()

            self._write_cache_safe(output)
            return output

    def _calculate_fallback_prices(self) -> Dict:
        cached_data = self._read_cache_safe()
        if cached_data:
            cached_data["source"] = "cached_fallback"
            cached_data["timestamp"] = datetime.utcnow().isoformat()
            return cached_data

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
            "silver": {"per_gram": round(gold_per_gram / 80, 2), "per_kg": round(gold_per_gram / 80 * 1000, 2)},
        }

    # -------------------- Expected price --------------------

    def calculate_expected_price(self, weight: float, purity: str, product_type: str = "jewellery") -> Dict:
        gold_data = self.get_live_gold_price()

        purity_factor = PURITY_MAPPING.get(purity, 0.9167)

        if purity in ("24K", "999"):
            base_price_per_gram = gold_data["gold"]["per_gram"]["999_landed"]
        else:
            if "raw_api_response" in gold_data and "goldByKarat" in gold_data["raw_api_response"]:
                karat_price_10g = float(gold_data["raw_api_response"]["goldByKarat"].get(purity, 0))
                base_price_per_gram = (karat_price_10g / 10) if karat_price_10g > 0 else gold_data["gold"]["per_gram"]["999_landed"] * purity_factor
            else:
                base_price_per_gram = gold_data["gold"]["per_gram"]["999_landed"] * purity_factor

        gold_value = base_price_per_gram * weight

        charges_key = f"coin_{purity}" if product_type == "coin" else f"jewellery_{purity}"
        making_charges_percent = self.MAKING_CHARGES.get(charges_key, 0.12 if product_type == "jewellery" else 0.04)

        making_charges = gold_value * making_charges_percent
        gst_amount = (gold_value + making_charges) * (GST_RATE / 100)
        total_expected = gold_value + making_charges + gst_amount
        price_per_gram = total_expected / weight if weight > 0 else 0

        # Add Goodreturns reference (EX-GST baseline)
        gr_ref = self.goodreturns_ref_per_gram(purity)

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
            "goodreturns_ref_per_gram_ex_gst": round(gr_ref, 2) if gr_ref else None,
        }

    def calculate_discount_percentage(self, selling_price: float, expected_price: float) -> float:
        if expected_price <= 0:
            return 0.0
        discount = ((expected_price - selling_price) / expected_price) * 100
        return round(max(discount, -100), 2)

    def get_price_summary(self) -> str:
        gold_data = self.get_live_gold_price()
        gold = gold_data["gold"]
        source = gold_data.get("source", "live_api")
        return (
            f"🟢 <b>Current Gold Prices</b>\n\n"
            f"<b>24K (999) Gold:</b>\n"
            f"• Spot (10g): ₹{gold['spot_10g']:,.0f}\n"
            f"• Landed (10g): ₹{gold['retail_999_10g']:,.0f}\n"
            f"• With GST (10g): ₹{gold['999_with_gst_10g']:,.0f}\n"
            f"• Per gram: ₹{gold['per_gram']['999_landed']:,.0f}\n\n"
            f"<i>Source: {source}</i>"
        )

    @lru_cache(maxsize=1)
    def get_cached_price_summary(self) -> str:
        return self.get_price_summary()
