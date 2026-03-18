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
        """Create and prepare a session for Myntra with proper cookies"""
        s = requests.Session()
        
        base_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Connection": "keep-alive",
        }
        
        # First visit to generate cookies
        s.get("https://www.myntra.com", headers=base_headers, timeout=15)
        time.sleep(random.uniform(1, 2))
        
        # Visit gold coins page
        s.get("https://www.myntra.com/gold-coin", headers=base_headers, timeout=15)
        time.sleep(random.uniform(1, 2))
        
        # Set pincode cookie
        s.cookies.set(
            "mynt-ulc",
            "pincode:384345|addressId:",
            domain=".myntra.com"
        )
        
        return s, base_headers
    
    def extract_purity_and_weight(self, title: str) -> Tuple[Optional[str], Optional[float]]:
        """
        Extract purity and weight from product title
        Returns: (purity, weight_in_grams)
        """
        title_lower = title.lower()
        
        # Extract purity
        purity = None
        purity_patterns = [
            (r'24\s*kt|24\s*karat|999|24k', '24K'),
            (r'22\s*kt|22\s*karat|916|22k', '22K'),
            (r'18\s*kt|18\s*karat|750|18k', '18K'),
            (r'14\s*kt|14\s*karat|585|14k', '14K'),
        ]
        
        for pattern, purity_value in purity_patterns:
            if re.search(pattern, title_lower):
                purity = purity_value
                break
        
        # SPECIAL CASE 1: Handle parentheses with plus signs (like "4.5 Gm (0.5 Gm + 2 Gm + 2 Gm)")
        # First, check if there's a weight outside parentheses and a sum inside parentheses
        parentheses_pattern = r'(\d+\.?\d*)\s*gm?\s*\(([^)]+)\)'
        parentheses_match = re.search(parentheses_pattern, title_lower)
        
        if parentheses_match:
            # We have a pattern like "4.5 Gm (0.5 Gm + 2 Gm + 2 Gm)"
            outside_weight = float(parentheses_match.group(1))
            inside_content = parentheses_match.group(2)
            
            # Extract all weights from inside parentheses
            inside_weights = re.findall(r'(\d+\.?\d*)\s*gm?', inside_content)
            if inside_weights:
                # Sum the inside weights
                inside_sum = sum(float(w) for w in inside_weights)
                
                # If outside weight matches the sum, return the outside weight
                if abs(outside_weight - inside_sum) < 0.01:
                    return purity, outside_weight
        
        # SPECIAL CASE 2: Handle plus signs (these should ALWAYS be summed)
        if '+' in title_lower:
            parts = re.split(r'\s*\+\s*', title_lower)
            plus_weights = []
            
            for part in parts:
                weight_match = re.search(r'(\d+\.?\d*)\s*gm?', part)
                if weight_match:
                    try:
                        weight = float(weight_match.group(1))
                        if 0.001 <= weight <= 1000:
                            plus_weights.append(weight)
                    except:
                        continue
            
            if plus_weights:
                # Return the SUM of all weights found with plus signs
                total_weight = sum(plus_weights)
                return purity, total_weight
        
        # SPECIAL CASE 3: Handle hyphen pattern
        hyphen_pattern = r'-\s*(\d+\.?\d*)\s*gm?'
        hyphen_match = re.search(hyphen_pattern, title_lower)
        if hyphen_match:
            try:
                weight = float(hyphen_match.group(1))
                return purity, weight
            except:
                pass
        
        # SPECIAL CASE 4: Handle patterns where weight is explicitly stated first
        # (like "4.5 Gm" at the beginning)
        first_weight_pattern = r'^.*?(\d+\.?\d*)\s*gm?'
        first_match = re.search(first_weight_pattern, title_lower)
        
        # Find all weights
        weight_patterns = [
            r'(\d+\.?\d*)\s*gm\b',
            r'(\d+\.?\d*)\s*gram\b',
            r'(\d+\.?\d*)\s*g\b(?!\w)',
            r'(\d+\.?\d*)\s*grams\b',
            r'(\d+\.?\d*)\s*gr\b',
        ]
        
        all_weights = []
        for pattern in weight_patterns:
            matches = re.finditer(pattern, title_lower)
            for match in matches:
                try:
                    num_float = float(match.group(1))
                    # Filter out purity numbers
                    if num_float not in [24, 22, 18, 14, 999, 916, 750, 585]:
                        if 0.001 <= num_float <= 1000:
                            all_weights.append(num_float)
                except:
                    continue
        
        if all_weights:
            # Check if all weights are the same
            if all(w == all_weights[0] for w in all_weights):
                # All weights are identical, return that weight
                return purity, all_weights[0]
            else:
                # Different weights, sum them
                return purity, sum(all_weights)
        
        return purity, None
    
    
    def determine_product_type(self, title: str, description: str = "") -> str:
        """
        Determine if product is jewellery or coin/bar
        """
        text = (title + " " + description).lower()
        
        coin_keywords = ['coin', 'sovereign', 'bar', 'biscuit', 'ingot', 'bullion', 'investment']
        jewellery_keywords = ['chain', 'pendant', 'ring', 'bangle', 'bracelet', 'earring', 
                             'necklace', 'mangalsutra', 'jewellery', 'jewelry', 'ornament']
        
        coin_count = sum(1 for keyword in coin_keywords if keyword in text)
        jewellery_count = sum(1 for keyword in jewellery_keywords if keyword in text)
        
        if coin_count > jewellery_count:
            return 'coin'
        else:
            return 'jewellery'
    
    def scrape_ajio(self) -> List[Dict]:
        print("🔄 Scraping AJIO...")
        products = []

        def fetch_page(page: int):
            params = SEARCH_PARAMS['ajio'].copy()
            params['currentPage'] = page

            try:
                r = requests.get(
                    AJIO_API_URL,
                    params=params,
                    headers=self.ajio_headers,
                    timeout=10
                )

                if r.status_code != 200:
                    print(f"Page {page} failed")
                    return []

                data = r.json()
                page_products = []

                for p in data.get("products", []):
                    parsed = self._parse_ajio_product(p)
                    if parsed:
                        page_products.append(parsed)

                print(f"Page {page}: {len(page_products)} valid")
                return page_products

            except Exception as e:
                print(f"Page {page} error: {e}")
                return []

        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = [ex.submit(fetch_page, p) for p in range(1, 13)]

            for f in as_completed(futures):
                products.extend(f.result())

        print(f"✅ AJIO total: {len(products)}")
        return products
    
    def _parse_ajio_product(self, product: Dict) -> Optional[Dict]:
        """Parse AJIO product data"""
        try:
            title = product.get('name', '')
            description = product.get('description', '')
            
            # Skip non-gold products
            # if 'gold' not in title.lower() and 'gold' not in description.lower():
            #     print('Skipping non-gold product    :', title)
            #     return None

            if 'silver' in title.lower():
                # print('Skipping silver product    :', title)
                return None
            
            # Extract purity and weight
            purity, weight = self.extract_purity_and_weight(title)
            
            if not purity or not weight:
                print(product)
                print('AJIO>Skipping invalid purity/weight product :', title)
                return None
            
            # Skip very small items
            if weight < 0.3:
                print('Skipping <0.3 product    :', title)
                return None
            
            # Determine product type
            product_type = self.determine_product_type(title, description)
            is_jewellery = (product_type == 'jewellery')
            
            # Extract price
            price_data = product.get('price', {})
            selling_price2 = price_data.get('value', 0)

            price_data = product.get('offerPrice', {})
            selling_price = price_data.get('value', 0)
            selling_price = selling_price if selling_price > 0 else selling_price2
            
            # Skip if price is too low
            if selling_price < 1000:
                print('Skipping <1000 price product    :', title)
                return None
            
            # Calculate expected price
            expected_price_info = self.price_calculator.calculate_expected_price(
                weight, purity, is_jewellery
            )
            # print(weight, purity, is_jewellery)
            # print(expected_price_info);
            expected_price = expected_price_info['total_expected']
            
            # Calculate discount
            discount_percent = self.price_calculator.calculate_discount_percentage(
                selling_price, expected_price
            )
            
            # Calculate price per gram
            price_per_gram = selling_price / weight
            # print({
            #     'source': 'AJIO',
            #     'title': title,
            #     'description': description[:200] if description else '',
            #     'weight_grams': weight,
            #     'purity': purity,
            #     'product_type': product_type,
            #     'is_jewellery': is_jewellery,
            #     'selling_price': selling_price,
            #     'expected_price': round(expected_price, 2),
            #     'discount_percent': discount_percent,
            #     'price_per_gram': round(price_per_gram, 2),
            #     'url': f"https://www.ajio.com{product.get('url', '')}",
            #     'image_url': product.get('images', [{}])[0].get('url', '') if product.get('images') else '',
            #     'brand': product.get('fnlColorVariantData', {}).get('brandName', 'Unknown'),
            #     'spot_price': expected_price_info['spot_price_per_gram'],
            #     'making_charges_percent': expected_price_info['making_charges_percent'],
            #     'gst_percent': expected_price_info['gst_percent'],
            #     'timestamp': datetime.now().isoformat()
            # })
            return {
                'source': 'AJIO',
                'title': title,
                'description': description[:200] if description else '',
                'weight_grams': weight,
                'purity': purity,
                'product_type': product_type,
                'is_jewellery': is_jewellery,
                'selling_price': selling_price,
                'expected_price': round(expected_price, 2),
                'discount_percent': discount_percent,
                'price_per_gram': round(price_per_gram, 2),
                'url': f"https://www.ajio.com{product.get('url', '')}",
                'image_url': product.get('images', [{}])[0].get('url', '') if product.get('images') else '',
                'brand': product.get('fnlColorVariantData', {}).get('brandName', 'Unknown'),
                'spot_price': expected_price_info['spot_price_per_gram'],
                'making_charges_percent': expected_price_info['making_charges_percent'],
                'gst_percent': expected_price_info['gst_percent'],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error parsing AJIO product: {e}")
            return None
    
    def scrape_myntra(self) -> List[Dict]:
        print("🔄 Scraping Myntra...")
        products = []

        def fetch_page(page: int):
            session, base_headers = self.create_myntra_session()

            params = {
                "rows": 50,
                "o": (49 * (page - 1)) + 1,
                "pincode": "384315"
            }

            api_headers = {
                "User-Agent": base_headers["User-Agent"],
                # "Accept": "application/json",
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
                # print(f"Page {page} response:")
                # print(r.status_code)
                # print(r.text)  # Print first 200 characters of response text
                data = r.json()
                page_products = []

                for p in data.get("products", []):
                    parsed = self._parse_myntra_product(p)
                    if parsed:
                        page_products.append(parsed)

                print(f"Page {page}: {len(page_products)} valid")
                return page_products

            except Exception as e:
                print(f"Page {page} error: {e}")
                return []

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(fetch_page, p) for p in range(1, 13)]

            for f in as_completed(futures):
                products.extend(f.result())

        print(f"✅ Myntra total: {len(products)}")
        return products
    
    def _extract_myntra_price(self, price_data: Any) -> Tuple[float, float]:
        """
        Extract prices from Myntra product data
        Returns: (selling_price, original_price)
        """
        try:
            # If price_data is a dictionary
            if isinstance(price_data, dict):
                selling_price = price_data.get('discountedPrice', 0)
                original_price = price_data.get('mrp', selling_price)
                return float(selling_price), float(original_price)
            
            # If price_data is a single integer/float
            elif isinstance(price_data, (int, float)):
                return float(price_data), float(price_data)
            
            # If price_data is a string
            elif isinstance(price_data, str):
                try:
                    price = float(price_data)
                    return price, price
                except:
                    return 0, 0
            
            else:
                return 0, 0
                
        except Exception as e:
            print(f"Error extracting Myntra price: {e}")
            return 0, 0
    
    def _parse_myntra_product(self, product: Dict) -> Optional[Dict]:
        """Parse Myntra product data with improved price handling"""
        try:
            title = product.get('productName', '')
            
            # Skip if no title
            if not title:
                print('Skipping Myntra price product    :', title)
                return None
            
            # Skip non-gold products
            # if 'gold' not in title.lower():
            #     print('Skipping not gold product    :', title)
            #     return None
        
            if 'silver' in title.lower():
                # print('Skipping silver  product    :', title)
                return None
            
            # Extract purity and weight
            purity, weight = self.extract_purity_and_weight(title)
            
            if not purity or not weight:
                # print(product);
                print('Myntra>Skipping invalid purity/weight product    :', title)
                return None
            
            # Skip very small items
            if weight < 0.3:
                print('Skipping very small weight < 0.3 product    :', title)
                return None
            
            # Determine product type from title
            product_type = self.determine_product_type(title)
            is_jewellery = (product_type == 'jewellery')
            
            # Extract price - handle different formats
            price_data = product.get('price')
            selling_price, original_price = self._extract_myntra_price(price_data)
            
            # Skip if price is too low
            if selling_price < 1000:
                print('Skipping very small price <1000 product    :', title)
                return None
            
            # Calculate expected price
            expected_price_info = self.price_calculator.calculate_expected_price(
                weight, purity, is_jewellery
            )
            expected_price = expected_price_info['total_expected']
            # print(expected_price,weight, purity, is_jewellery)
            # print(expected_price_info)
            # return {}
            # Calculate discount
            discount_percent = self.price_calculator.calculate_discount_percentage(
                selling_price, expected_price
            )
            
            # Calculate price per gram
            price_per_gram = selling_price / weight
            
            # Get other product details
            landing_url = product.get('landingPageUrl', '')
            if landing_url and not landing_url.startswith('http'):
                landing_url = f"https://www.myntra.com/{landing_url}"
            
            # print({
            #     'source': 'Myntra',
            #     'title': title,
            #     'weight_grams': weight,
            #     'purity': purity,
            #     'product_type': product_type,
            #     'is_jewellery': is_jewellery,
            #     'selling_price': selling_price,
            #     'original_price': original_price,
            #     'expected_price': round(expected_price, 2),
            #     'discount_percent': discount_percent,
            #     'price_per_gram': round(price_per_gram, 2),
            #     'url': landing_url,
            #     'image_url': product.get('searchImage', ''),
            #     'brand': product.get('brandName', 'Unknown'),
            #     'spot_price': expected_price_info['spot_price_per_gram'],
            #     'making_charges_percent': expected_price_info['making_charges_percent'],
            #     'gst_percent': expected_price_info['gst_percent'],
            #     'timestamp': datetime.now().isoformat()
            # })

            return {
                'source': 'Myntra',
                'title': title,
                'weight_grams': weight,
                'purity': purity,
                'product_type': product_type,
                'is_jewellery': is_jewellery,
                'selling_price': selling_price,
                'original_price': original_price,
                'expected_price': round(expected_price, 2),
                'discount_percent': discount_percent,
                'price_per_gram': round(price_per_gram, 2),
                'url': landing_url,
                'image_url': product.get('searchImage', ''),
                'brand': product.get('brandName', 'Unknown'),
                'spot_price': expected_price_info['spot_price_per_gram'],
                'making_charges_percent': expected_price_info['making_charges_percent'],
                'gst_percent': expected_price_info['gst_percent'],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error parsing Myntra product '{product.get('productName', 'Unknown')}': {e}")
            import traceback
            traceback.print_exc()
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

    def scrape_all_with_cache(self, force_refresh=False):
        """Scrape all sources with caching"""
        cache_file = "data/latest_scan.json"
        
        # Check cache if not forcing refresh
        if not force_refresh and os.path.exists(cache_file):
            cache_age = time.time() - os.path.getmtime(cache_file)
            if cache_age < 300:  # 5 minutes cache
                with open(cache_file, 'r') as f:
                    return json.load(f)
        
        # Perform fresh scrape
        products = self.scrape_all()
        
        # Save to cache
        with open(cache_file, 'w') as f:
            json.dump(products, f)
        
        return products