import requests, uuid, time
from fake_useragent import UserAgent

ua = UserAgent()
session = requests.Session()
headers={"User-Agent": ua.random}
# 1. Warm up session with homepage (sets cookies)
session.get(
    "https://www.myntra.com",
    headers={"User-Agent": ua.random},
    timeout=10
)
time.sleep(2)  # Human-like delay

# 2. Add dynamic headers
headers["x-request-id"] = str(uuid.uuid4())
headers["Cookie"] = "; ".join([f"{c.name}={c.value}" for c in session.cookies])

# 3. Make API request
response = session.get(
    "https://www.myntra.com/gateway/v4/search/gold-coin?rows=50&o=49&plaEnabled=true&xdEnabled=false&isFacet=true&p=2&pincode=384345",
    headers=headers,
    timeout=15
)
print(response.status_code)
print(response.json())