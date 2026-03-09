import requests
import random


class MarketAPI:

    def __init__(self):
        self.url = "https://clob.polymarket.com/markets"

    # =========================
    # CALCULATE SPREAD
    # =========================
    def calculate_spread(self, market):
        try:
            best_bid = float(market.get("best_bid", 0))
            best_ask = float(market.get("best_ask", 0))

            if best_bid and best_ask:
                return round(best_ask - best_bid, 4)

            return 0.01
        except:
            return 0.01

    # =========================
    # GET MARKET DATA
    def get_market_data(self):
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Connection": "keep-alive"
            }

            session = requests.Session()
            r = session.get(self.url, headers=headers, timeout=30)
            # r = requests.get(self.url, timeout=30)
            r.raise_for_status()

            response = r.json()
            markets = response.get("data", [])

            if not markets:
                raise Exception("No active markets")
            
            m = next(
                (
                    mk for mk in markets
                    if mk.get("active") == True
                    and mk.get("closed") == False
                    and mk.get("accepting_orders") == True
                    and mk.get("tokens")
                    and any(t.get("price") is not None for t in mk.get("tokens", []))
                ),
                None
            )

            if not m:
                raise Exception("No active live markets found")

            tokens = m.get("tokens", [])

            yes_price = None
            no_price = None

            for t in tokens:
                if t.get("outcome") == "Yes":
                    yes_price = float(t.get("price", 0))
                elif t.get("outcome") == "No":
                    no_price = float(t.get("price", 0))
            
            return {
                "market": m.get("question"),
                "price_yes": yes_price,
                "price_no": no_price,
                "volume": float(m.get("volume", 0)),
                "liquidity": float(m.get("liquidity", 0)),
                "active": m.get("active", True),
                "closed": m.get("closed", False),
                "end_date": m.get("end_date_iso"),
                "spread": self.calculate_spread(m),
                "source": "live"
            }

        except Exception as e:
            print("⚠ API ERROR — Using simulated data:", e)

            yes = round(random.uniform(0.4, 0.6), 3)

            return {
                "market": "Simulated Market",
                "price_yes": yes,
                "price_no": round(1 - yes, 3),
                "volume": 5000,
                "liquidity": 8000,
                "active": True,
                "closed": False,
                "end_date": None,
                "spread": 0.01,
                "source": "simulated"
            }









# import requests

# class MarketAPI:
#     def __init__(self):
#         self.url = "https://clob.polymarket.com/markets"

#     def get_market_data(self):
#         try:
#             r = requests.get(self.url, timeout=10)
#             r.raise_for_status()
#             data = r.json()

#             markets = data.get("data", [])

#             # Filter ACTIVE markets that are tradable
#             active = [
#                 m for m in markets
#                 if m.get("active") and not m.get("closed") and m.get("enable_order_book")
#             ]

#             if not active:
#                 raise Exception("No active markets available")

#             m = active[0]  # pick first live market

#             tokens = m.get("tokens", [])
#             yes_price = None
#             no_price = None

#             for t in tokens:
#                 if t.get("outcome") == "Yes":
#                     yes_price = t.get("price")
#                 if t.get("outcome") == "No":
#                     no_price = t.get("price")

#             return {
#                 "market": m.get("question"),
#                 "price_yes": float(yes_price),
#                 "price_no": float(no_price),
#                 "volume": m.get("volume", 0),
#                 "liquidity": m.get("liquidity", 0),
#                 "active": m.get("active", True),
#                 "closed": m.get("closed", False),
#                 "end_date": m.get("end_date_iso"),
#                 "spread": calculate_spread(m),
#                 "source": "live"
#             }

#         except Exception as e:
#             print("⚠ API ERROR — Using simulated data:", e)

#             # fallback ONLY if API fails
#             import random
#             yes = round(random.uniform(0.4, 0.6), 3)

#             return {
#                 "market": "Simulated Market",
#                 "price_yes": yes,
#                 "price_no": round(1 - yes, 3),
#                 "source": "simulated"
#             }
