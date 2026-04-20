import json
import os
import requests
import time
import re
import random
from typing import Dict, List, Optional, Tuple, Any
from config import AJIO_API_URL, SEARCH_PARAMS, REQUEST_DELAY
from price_calculator import GoldPriceCalculator
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


_EXCLUDE_PATTERNS = [
    r'gold[- ]plated',
    r'gold plated',
    r'american diamond',
    r'multi[- ]piece set',
    r'\d+[- ]piece\s+(?:suit|spread|collar|set)',
    r'embellished\s+\d+[- ]piece',
    r'mangalsutra',
    r'necklace',
    r'lobster closure',
    r'stone[- ]studded',
    r'beaded multi',
]
_EXCLUDE_RE = re.compile('|'.join(_EXCLUDE_PATTERNS), re.IGNORECASE)


def is_real_gold_product(title: str) -> bool:
    """Return False for gold-plated / fashion / non-coin products."""
