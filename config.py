import os
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gold_deal_finder.log'),
        # logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

load_dotenv()

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID')

# If you have API keys for premium services
METALPRICE_API_KEY = os.getenv('METALPRICE_API_KEY', '')
GOLDAPI_TOKEN = os.getenv('GOLDAPI_TOKEN', '')

# API Endpoints
AJIO_API_URL = "https://www.ajio.com/api/search"
MYNTRA_API_URL = "https://www.myntra.com/gateway/v4/search"

# GST Rate (for India)
GST_RATE = 0  # 3% GST on gold

# Purity to karat mapping
PURITY_MAPPING = {
    '24K': 0.999,
    '22K': 0.9167,
    '18K': 0.750,
    '14K': 0.585,
    '916': 0.9167,
    '999': 0.999,
    '750': 0.750,
    '585': 0.585
}

# Search Parameters
SEARCH_PARAMS = {
    'ajio': {
        'query': 'gold coin:relevance',
        'text': 'gold coin',
        'pageSize': 45,
        'format': 'json',
        'fields': 'SITE',
        'pincode': '384315',
        'state': 'GUJARAT',
        'city': 'MAHESANA'
    },
    'myntra': {
        'rows': 50,
        'pincode': '384345',
        'plaEnabled': 'true'
    }
}

# Alert Thresholds
MIN_DISCOUNT_PERCENTAGE = -1
MIN_WEIGHT = 0.5
MAX_PRICE_PER_GRAM = {
    '24K': 18000,
    '22K': 17000,
    '18K': 16000,
    '14K': 15000,
    'default': 14000
}

# Price calculation constants
OZ_TO_GRAM = 31.1035
LANDED_MULTIPLIER = 1.11
RETAIL_SPREAD = 700
RTGS_DISCOUNT = 600
JEWELLERY_PREMIUM_22K = 1200

# Cache settings
CACHE_TTL = 300  # 5 minutes
CACHE_FILE = "bullion_cache.json"

# Local app runtime
APP_HOST = os.getenv('APP_HOST', '0.0.0.0')
APP_PORT = int(os.getenv('APP_PORT', '8000'))
APP_RELOAD = os.getenv('APP_RELOAD', 'true').lower() == 'true'
AUTO_OPEN_BROWSER = os.getenv('AUTO_OPEN_BROWSER', 'false').lower() == 'true'

# Scan behavior
SCAN_COOLDOWN_MINUTES = int(os.getenv('SCAN_COOLDOWN_MINUTES', '0'))
HISTORICAL_SCAN_LIMIT_DEFAULT = int(os.getenv('HISTORICAL_SCAN_LIMIT_DEFAULT', '5'))
MAX_HISTORICAL_SCAN_LIMIT = int(os.getenv('MAX_HISTORICAL_SCAN_LIMIT', '25'))

# Scraping settings
REQUEST_DELAY = 2  # seconds between requests
MAX_PAGES = 3
REQUEST_TIMEOUT = 30

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 5
