import requests

class PolymarketAPI:

    BASE_URL = "https://gamma-api.polymarket.com"

    def get_markets(self, limit=10):
        url = f"{self.BASE_URL}/markets?limit={limit}"
        r = requests.get(url)
        r.raise_for_status()
        return r.json()
    
    def get_market_by_slug(self, slug):
        url = f"{self.BASE_URL}/markets?slug={slug}"
        r = requests.get(url)
        r.raise_for_status()
        markets = r.json()
        return markets[0] if markets else None