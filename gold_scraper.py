import json
import os
import requests
import time
import re
import random
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import AJIO_API_URL, SEARCH_PARAMS, REQUEST_DELAY
from price_calculator import GoldPriceCalculator

from payment_discounts import best_price_by_payment_mode
from config import PAYMENT_DISCOUNT_RULES, PAYMENT_MODES_TO_TRY, DEFAULT_PAYMENT_MODE


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
    return not bool(_EXCLUDE_RE.search(title or ""))


class GoldScraper:
    def __init__(self):
        self.price_calculator = GoldPriceCalculator()
        self.ajio_headers = {
            'authority': 'www.ajio.com',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'referer': 'https://www.ajio.com/',
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
        }

    def create_myntra_session(self):
        s = requests.Session()
        base_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Connection": "keep-alive",
        }
        s.get("https://www.myntra.com", headers=base_headers, timeout=15)
        time.sleep(random.uniform(1, 2))
        s.get("https://www.myntra.com/gold-coin", headers=base_headers, timeout=15)
        time.sleep(random.uniform(1, 2))
        s.cookies.set("mynt-ulc", "pincode:501503|addressId:", domain=".myntra.com")
        return s, base_headers

    def extract_purity_and_weight(self, title: str) -> Tuple[Optional[str], Optional[float]]:
        title = title or ""
        title_lower = title.lower()

        if not is_real_gold_product(title):
            return None, None

        purity = None
        purity_patterns = [
            (r'24\s*kt|24\s*karat|\b999\b|24k', '24K'),
            (r'22\s*kt|22\s*karat|\b916\b|22k', '22K'),
            (r'18\s*kt|18\s*karat|\b750\b|18k', '18K'),
            (r'14\s*kt|14\s*karat|\b585\b|14k', '14K'),
            (r'\b995\b', '995'),
        ]
        for pattern, purity_value in purity_patterns:
            if re.search(pattern, title_lower):
                purity = purity_value
                break

        PURITY_NUMBERS = {24, 22, 18, 14, 999, 916, 750, 585, 995}

        def is_valid_weight(n: float) -> bool:
            return n not in PURITY_NUMBERS and 0.001 <= n <= 10_000

        paren_total_pat = re.compile(r'(\d+(?:\.\d+)?)\s*(?:grams?|gms?|gm|gr)\b\s*\(([^)]+)\)', re.IGNORECASE)
        m = paren_total_pat.search(title_lower)
        if m:
            outside_total = float(m.group(1))
            inside_text = m.group(2)
            inside_weights = [float(x) for x in re.findall(r'(\d+(?:\.\d+)?)\s*(?:grams?|gms?|gm|gr)\b', inside_text, flags=re.IGNORECASE)]
            if inside_weights:
                inside_sum = sum(inside_weights)
                weight_in_grams = outside_total if abs(outside_total - inside_sum) <= 0.05 else inside_sum
            else:
                weight_in_grams = outside_total
            if is_valid_weight(weight_in_grams):
                return purity, round(weight_in_grams, 3)

        if '+' in title_lower:
            inside_parentheses = re.search(r'\(([^)]*\+[^)]*)\)', title_lower)
            if inside_parentheses:
                text = inside_parentheses.group(1)
                plus_weights = [float(x) for x in re.findall(r'(\d+(?:\.\d+)?)\s*(?:grams?|gms?|gm|gr)\b', text, flags=re.IGNORECASE)]
                plus_weights = [w for w in plus_weights if is_valid_weight(w)]
                if plus_weights:
                    return purity, round(sum(plus_weights), 3)

        hyphen_match = re.search(r'-\s*(\d+(?:\.\d+)?)\s*(?:grams?|gms?|gm|gr)\b', title_lower, flags=re.IGNORECASE)
        if hyphen_match:
            w = float(hyphen_match.group(1))
            if is_valid_weight(w):
                return purity, round(w, 3)

        mg_match = re.search(r'(\d+(?:\.\d+)?)\s*mg\b', title_lower, flags=re.IGNORECASE)
        if mg_match:
            w_mg = float(mg_match.group(1))
            grams = w_mg / 1000.0
            if is_valid_weight(grams):
                return purity, round(grams, 6)

        weight_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:grams?|gms?|gm|gr)\b',
            r'(\d+(?:\.\d+)?)\s*g(?!\w)',
        ]
        all_weights: List[float] = []
        seen_pos = set()

        for pat in weight_patterns:
            for mm in re.finditer(pat, title_lower, flags=re.IGNORECASE):
                if mm.start() in seen_pos:
                    continue
                try:
                    w = float(mm.group(1))
                    if is_valid_weight(w):
                        all_weights.append(w)
                        seen_pos.add(mm.start())
                except ValueError:
                    continue

        if all_weights:
            if all(w == all_weights[0] for w in all_weights):
                return purity, round(all_weights[0], 3)
            return purity, round(sum(all_weights), 3)

        return purity, None

    def determine_product_type(self, title: str, description: str = "") -> str:
        text = (title + " " + description).lower()
        coin_keywords = ['coin', 'sovereign', 'bar', 'biscuit', 'ingot', 'bullion', 'investment']
        jewellery_keywords = ['chain', 'pendant', 'ring', 'bangle', 'bracelet', 'earring',
                              'necklace', 'mangalsutra', 'jewellery', 'jewelry', 'ornament']
        coin_count = sum(1 for keyword in coin_keywords if keyword in text)
        jewellery_count = sum(1 for keyword in jewellery_keywords if keyword in text)
        return 'coin' if coin_count > jewellery_count else 'jewellery'

    def scrape_ajio(self) -> List[Dict]:
        print("🔄 Scraping AJIO...")
        products: List[Dict] = []

        def fetch_page(page: int):
            params = SEARCH_PARAMS['ajio'].copy()
            params['currentPage'] = page

            try:
                r = requests.get(AJIO_API_URL, params=params, headers=self.ajio_headers, timeout=10)
                if r.status_code != 200:
                    return []

                data = r.json()
                page_products = []

                for p in data.get("products", []):
                    parsed = self._parse_ajio_product(p)
                    if parsed:
                        page_products.append(parsed)

                time.sleep(REQUEST_DELAY)
                return page_products

            except Exception as e:
                print(f"AJIO page {page} error: {e}")
                return []

        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = [ex.submit(fetch_page, p) for p in range(1, 13)]
            for f in as_completed(futures):
                products.extend(f.result())

        print(f"✅ AJIO total: {len(products)}")
        return products

    def _parse_ajio_product(self, product: Dict) -> Optional[Dict]:
        try:
            title = product.get('name', '') or ''
            description = product.get('description', '') or ''

            if 'silver' in title.lower():
                return None

            purity, weight = self.extract_purity_and_weight(title)
            if not purity or weight is None:
                return None
            if weight < 0.3:
                return None

            product_type = self.determine_product_type(title, description)
            # IMPORTANT: price_calculator expects 'coin' or 'jewellery' string
            calc_type = 'coin' if product_type == 'coin' else 'jewellery'

            price_data = product.get('price', {}) or {}
            selling_price2 = (price_data.get('value', 0) or 0)

            offer_price = product.get('offerPrice', {}) or {}
            selling_price = (offer_price.get('value', 0) or 0)
            selling_price = selling_price if selling_price > 0 else selling_price2
            selling_price = float(selling_price)

            if selling_price < 1000:
                return None

            expected_price_info = self.price_calculator.calculate_expected_price(weight, purity, calc_type)
            expected_price = expected_price_info['total_expected']

            # Payment discount modeling
            _ = os.getenv("PAYMENT_MODE", DEFAULT_PAYMENT_MODE)
            best = best_price_by_payment_mode(
                site="AJIO",
                selling_price=selling_price,
                payment_modes=PAYMENT_MODES_TO_TRY,
                rules=PAYMENT_DISCOUNT_RULES,
                allow_stacking=True
            )

            pay_now_price = best["pay_now_price"]
            effective_price = best["effective_price"]
            payment_discount_value = best["discount_value"]
            payment_discount_rules = best["rules"]
            best_payment_mode = best["payment_mode"]

            discount_percent = self.price_calculator.calculate_discount_percentage(effective_price, expected_price)
            price_per_gram = effective_price / weight

            return {
                'source': 'AJIO',
                'title': title,
                'description': description[:200] if description else '',
                'weight_grams': weight,
                'purity': purity,
                'product_type': product_type,
                'is_jewellery': (product_type == 'jewellery'),

                'selling_price': selling_price,
                'pay_now_price': round(pay_now_price, 2),
                'effective_price': round(effective_price, 2),
                'payment_discount_value': round(payment_discount_value, 2),
                'payment_discount_rules': payment_discount_rules,
                'best_payment_mode': best_payment_mode,

                'expected_price': round(expected_price, 2),
                'discount_percent': discount_percent,
                'price_per_gram': round(price_per_gram, 2),

                'url': f"https://www.ajio.com{product.get('url', '')}",
                'image_url': product.get('images', [{}])[0].get('url', '') if product.get('images') else '',
                'brand': product.get('fnlColorVariantData', {}).get('brandName', 'Unknown'),
                'spot_price': expected_price_info.get('spot_price_per_gram', 0),
                'making_charges_percent': expected_price_info.get('making_charges_percent', 0),
                'gst_percent': expected_price_info.get('gst_percent', 0),
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            print(f"Error parsing AJIO product: {e}")
            return None

    def scrape_myntra(self) -> List[Dict]:
        print("🔄 Scraping Myntra...")
        products: List[Dict] = []

        def fetch_page(page: int):
            session, base_headers = self.create_myntra_session()

            params = {
                "rows": 50,
                "o": (49 * (page - 1)) + 1,
                "pincode": "384315"
            }

            api_headers = {
                "User-Agent": base_headers["User-Agent"],
                "referer": "https://www.myntra.com/gold-coin",
                "x-meta-app": "channel=web",
                "x-myntraweb": "Yes",
                "x-requested-with": "browser"
            }

            try:
                r = session.get(
                    "https://www.myntra.com/gateway/v4/search/gold-coin",
                    params=params,
                    headers=api_headers,
                    timeout=20
                )
                if r.status_code != 200:
                    return []

                data = r.json()
                page_products = []
                for p in data.get("products", []):
                    parsed = self._parse_myntra_product(p)
                    if parsed:
                        page_products.append(parsed)

                time.sleep(REQUEST_DELAY)
                return page_products

            except Exception as e:
                print(f"Myntra page {page} error: {e}")
                return []

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(fetch_page, p) for p in range(1, 13)]
            for f in as_completed(futures):
                products.extend(f.result())

        print(f"✅ Myntra total: {len(products)}")
        return products

    def _extract_myntra_price(self, price_data: Any) -> Tuple[float, float]:
        try:
            if isinstance(price_data, dict):
                selling_price = price_data.get('discountedPrice', 0)
                original_price = price_data.get('mrp', selling_price)
                return float(selling_price), float(original_price)

            if isinstance(price_data, (int, float)):
                return float(price_data), float(price_data)

            if isinstance(price_data, str):
                try:
                    price = float(price_data)
                    return price, price
                except Exception:
                    return 0.0, 0.0

            return 0.0, 0.0
        except Exception:
            return 0.0, 0.0

    def _parse_myntra_product(self, product: Dict) -> Optional[Dict]:
        try:
            title = product.get('productName', '') or ''
            if not title:
                return None
            if 'silver' in title.lower():
                return None

            purity, weight = self.extract_purity_and_weight(title)
            if not purity or weight is None:
                return None
            if weight < 0.3:
                return None

            product_type = self.determine_product_type(title)
            calc_type = 'coin' if product_type == 'coin' else 'jewellery'

            price_data = product.get('price')
            selling_price, original_price = self._extract_myntra_price(price_data)
            if selling_price < 1000:
                return None

            expected_price_info = self.price_calculator.calculate_expected_price(weight, purity, calc_type)
            expected_price = expected_price_info['total_expected']

            _ = os.getenv("PAYMENT_MODE", DEFAULT_PAYMENT_MODE)
            best = best_price_by_payment_mode(
                site="Myntra",
                selling_price=selling_price,
                payment_modes=PAYMENT_MODES_TO_TRY,
                rules=PAYMENT_DISCOUNT_RULES,
                allow_stacking=True
            )

            pay_now_price = best["pay_now_price"]
            effective_price = best["effective_price"]
            payment_discount_value = best["discount_value"]
            payment_discount_rules = best["rules"]
            best_payment_mode = best["payment_mode"]

            discount_percent = self.price_calculator.calculate_discount_percentage(effective_price, expected_price)
            price_per_gram = effective_price / weight

            landing_url = product.get('landingPageUrl', '') or ''
            if landing_url and not landing_url.startswith('http'):
                landing_url = f"https://www.myntra.com/{landing_url}"

            return {
                'source': 'Myntra',
                'title': title,
                'weight_grams': weight,
                'purity': purity,
                'product_type': product_type,
                'is_jewellery': (product_type == 'jewellery'),

                'selling_price': float(selling_price),
                'original_price': float(original_price),

                'pay_now_price': round(pay_now_price, 2),
                'effective_price': round(effective_price, 2),
                'payment_discount_value': round(payment_discount_value, 2),
                'payment_discount_rules': payment_discount_rules,
                'best_payment_mode': best_payment_mode,

                'expected_price': round(expected_price, 2),
                'discount_percent': discount_percent,
                'price_per_gram': round(price_per_gram, 2),

                'url': landing_url,
                'image_url': product.get('searchImage', ''),
                'brand': product.get('brandName', 'Unknown'),
                'spot_price': expected_price_info.get('spot_price_per_gram', 0),
                'making_charges_percent': expected_price_info.get('making_charges_percent', 0),
                'gst_percent': expected_price_info.get('gst_percent', 0),
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            print(f"Error parsing Myntra product: {e}")
            return None

    def scrape_all(self) -> List[Dict]:
        with ThreadPoolExecutor(max_workers=5) as ex:
            f1 = ex.submit(self.scrape_ajio)
            f2 = ex.submit(self.scrape_myntra)

            ajio_products = f1.result()
            myntra_products = f2.result()

        all_products = ajio_products + myntra_products
        print(f"\n📊 Total products: {len(all_products)}")
        return all_products

    def scrape_all_with_cache(self, force_refresh: bool = False):
        cache_file = "data/latest_scan.json"

        if not force_refresh and os.path.exists(cache_file):
            cache_age = time.time() - os.path.getmtime(cache_file)
            if cache_age < 300:
                with open(cache_file, 'r') as f:
                    return json.load(f)

        products = self.scrape_all()

        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump(products, f)

        return products
