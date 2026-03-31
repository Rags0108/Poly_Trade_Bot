"""
Weather Market Scanner — Discover weather prediction markets on Polymarket.

Scans Polymarket's Gamma API for active weather-related markets,
matches them to cities, and returns structured market data.
"""

import time
import re
import json
import requests
from typing import Dict, List, Optional

from weather_prediction.weather_api import WEATHER_CITIES

GAMMA_API_URL = "https://gamma-api.polymarket.com"

# Keywords that identify weather markets
WEATHER_KEYWORDS = [
    "temperature", "weather", "rain", "snow", "hurricane", "tornado",
    "heat", "cold", "freeze", "frost", "wind", "storm", "precipitation",
    "drought", "flood", "celsius", "fahrenheit", "degrees", "hot", "warm",
    "climate", "heatwave", "blizzard", "cyclone", "typhoon", "monsoon",
    "sunny", "cloudy", "fog", "humidity", "barometric", "pressure",
    "rainfall", "snowfall", "record high", "record low", "degrees in",
    "temp in", "high temp", "low temp",
]

# Cache
_market_cache: Dict[str, tuple] = {}
MARKET_CACHE_TTL = 60  # 1 minute


class WeatherMarketScanner:
    """Discover and monitor weather prediction markets on Polymarket."""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "WeatherTradingBot/1.0",
            "Accept": "application/json",
        })
        self._known_markets: Dict[str, dict] = {}

    def scan_markets(self, limit: int = 200) -> List[Dict]:
        """
        Scan Polymarket for active weather markets.
        
        Returns list of normalized market data dicts.
        """
        cache_key = f"scan_{limit}"
        if cache_key in _market_cache:
            ts, data = _market_cache[cache_key]
            if time.time() - ts < MARKET_CACHE_TTL:
                return data

        weather_markets = []
        seen_ids = set()

        try:
            # First pass: active markets feed
            markets = self._fetch_gamma_markets(limit)

            # Second pass: keyword-targeted queries to avoid missing weather markets
            for term in ("weather", "temperature", "rain", "snow"):
                markets.extend(self._fetch_gamma_markets_by_query(term, 80))

            for m in markets:
                question = m.get("question", "")
                if not self._is_weather_market(question):
                    continue

                # Parse market data
                parsed = self._parse_market(m)
                if parsed and parsed["market_id"] not in seen_ids:
                    seen_ids.add(parsed["market_id"])
                    weather_markets.append(parsed)
                    self._known_markets[parsed["market_id"]] = parsed

            print(
                f"🔎 Scanner: checked={len(markets)} weather={len(weather_markets)}"
            )

        except Exception as e:
            print(f"⚠️ Market scan error: {e}")

        _market_cache[cache_key] = (time.time(), weather_markets)
        return weather_markets

    def get_market_by_id(self, market_id: str) -> Optional[Dict]:
        """Get a specific market by condition ID."""
        if market_id in self._known_markets:
            return self._known_markets[market_id]

        try:
            resp = self._session.get(
                f"{GAMMA_API_URL}/markets/{market_id}",
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                parsed = self._parse_market(data)
                if parsed:
                    self._known_markets[market_id] = parsed
                    return parsed
        except Exception as e:
            print(f"⚠️ Market fetch error: {e}")

        return None

    def get_market_prices(self, market_id: str) -> Optional[Dict]:
        """Get current live prices for a market from CLOB."""
        try:
            url = "https://clob.polymarket.com/markets"
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            markets = data.get("data", []) if isinstance(data, dict) else data

            for m in markets:
                if m.get("condition_id") == market_id:
                    tokens = m.get("tokens", [])
                    yes_price = None
                    no_price = None
                    for t in tokens:
                        if t.get("outcome") == "Yes":
                            yes_price = float(t.get("price", 0))
                        elif t.get("outcome") == "No":
                            no_price = float(t.get("price", 0))
                    return {
                        "price_yes": yes_price,
                        "price_no": no_price,
                        "volume": float(m.get("volume", 0)),
                        "liquidity": float(m.get("liquidity", 0)),
                    }
        except Exception as e:
            print(f"⚠️ Price fetch error: {e}")

        return None

    def _fetch_gamma_markets(self, limit: int) -> List[dict]:
        """Fetch markets from Gamma API."""
        all_markets = []
        offset = 0
        page_size = min(100, limit)

        while len(all_markets) < limit:
            try:
                resp = self._session.get(
                    f"{GAMMA_API_URL}/markets",
                    params={
                        "limit": page_size,
                        "offset": offset,
                        "active": True,
                        "closed": False,
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                if not data:
                    break

                if isinstance(data, list):
                    all_markets.extend(data)
                elif isinstance(data, dict) and "data" in data:
                    all_markets.extend(data["data"])
                else:
                    break

                if len(data if isinstance(data, list) else data.get("data", [])) < page_size:
                    break
                offset += page_size
            except Exception:
                break

        return all_markets

    def _fetch_gamma_markets_by_query(self, query: str, limit: int) -> List[dict]:
        """Fetch markets with a query term using Gamma's search-compatible params."""
        try:
            for query_key in ("query", "search"):
                resp = self._session.get(
                    f"{GAMMA_API_URL}/markets",
                    params={
                        "limit": min(100, limit),
                        "active": True,
                        "closed": False,
                        query_key: query,
                    },
                    timeout=12,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "data" in data:
                    return data.get("data", [])
        except Exception:
            pass
        return []

    def _is_weather_market(self, question: str) -> bool:
        """Check if a market question is weather-related."""
        q = question.lower()
        return any(keyword in q for keyword in WEATHER_KEYWORDS)

    def _parse_market(self, raw_market: dict) -> Optional[Dict]:
        """Parse raw market data into normalized format."""
        question = raw_market.get("question", "")
        if not question:
            return None

        market_id = (
            raw_market.get("condition_id")
            or raw_market.get("conditionId")
            or raw_market.get("id", "")
        )
        if not market_id:
            return None

        # Try to identify city
        city_key = self._identify_city(question)

        # Get token prices
        tokens = raw_market.get("tokens", [])
        yes_price = None
        no_price = None
        yes_token_id = ""
        no_token_id = ""

        for t in tokens:
            outcome = t.get("outcome", "").lower()
            if outcome == "yes":
                yes_price = float(t.get("price", 0)) if t.get("price") else None
                yes_token_id = t.get("token_id") or t.get("tokenId") or t.get("id", "")
            elif outcome == "no":
                no_price = float(t.get("price", 0)) if t.get("price") else None
                no_token_id = t.get("token_id") or t.get("tokenId") or t.get("id", "")

        # Fallback price fields seen in Gamma payloads.
        if yes_price is None or no_price is None:
            outcome_prices = raw_market.get("outcomePrices") or raw_market.get("outcome_prices")
            if isinstance(outcome_prices, str):
                # Some Gamma payloads provide JSON-string arrays.
                try:
                    outcome_prices = json.loads(outcome_prices)
                except Exception:
                    outcome_prices = []
            if isinstance(outcome_prices, list) and len(outcome_prices) >= 2:
                try:
                    if yes_price is None:
                        yes_price = float(outcome_prices[0])
                    if no_price is None:
                        no_price = float(outcome_prices[1])
                except Exception:
                    pass

        # Fallback token id fields seen in some payloads.
        if not yes_token_id or not no_token_id:
            clob_token_ids = raw_market.get("clobTokenIds") or raw_market.get("clob_token_ids")
            if isinstance(clob_token_ids, str):
                try:
                    clob_token_ids = json.loads(clob_token_ids)
                except Exception:
                    clob_token_ids = []
            if isinstance(clob_token_ids, list) and len(clob_token_ids) >= 2:
                yes_token_id = yes_token_id or str(clob_token_ids[0])
                no_token_id = no_token_id or str(clob_token_ids[1])

        return {
            "market_id": market_id,
            "market": question,
            "slug": raw_market.get("slug", ""),
            "city_key": city_key,
            "city_name": WEATHER_CITIES.get(city_key, {}).get("name", "Unknown") if city_key else "Unknown",
            "price_yes": yes_price,
            "price_no": no_price,
            "yes_token_id": yes_token_id,
            "no_token_id": no_token_id,
            "volume": float(raw_market.get("volume", 0)),
            "liquidity": float(raw_market.get("liquidity", 0)),
            "active": raw_market.get("active", True),
            "closed": raw_market.get("closed", False),
            "end_date": raw_market.get("end_date_iso", raw_market.get("end_date", "")),
            "neg_risk": raw_market.get("neg_risk", raw_market.get("negRisk", False)),
            "source": "polymarket_gamma",
        }

    def _identify_city(self, question: str) -> Optional[str]:
        """Match question to a tracked city."""
        q = question.lower()
        for key, city in WEATHER_CITIES.items():
            if city["name"].lower() in q:
                return key

        # Common abbreviations
        abbreviations = {
            "nyc": "new_york", "ny": "new_york",
            "la": "los_angeles", "sf": "san_francisco",
            "dc": "washington_dc", "d.c.": "washington_dc",
        }
        for abbr, city_key in abbreviations.items():
            if abbr in q:
                return city_key

        return None
