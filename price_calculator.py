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
