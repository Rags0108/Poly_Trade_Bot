from datetime import datetime
from typing import Tuple


class PreTradeValidator:

    def __init__(
        self,
        min_volume=1000,
        min_liquidity=2000,
        min_confidence=0,
        min_edge=0,
        min_days_to_expiry=7,
        max_spread=0.05
    ):
        self.min_volume = min_volume
        self.min_liquidity = min_liquidity
        self.min_confidence = min_confidence
        self.min_edge = min_edge
        self.min_days_to_expiry = min_days_to_expiry
        self.max_spread = max_spread

    # =========================
    # MAIN VALIDATION FUNCTION
    # =========================
    def validate(self, market_data: dict, analysis: dict) -> Tuple[bool, str]:

        # 1️⃣ Market active
        if not market_data.get("active", True):
            return False, "Market not active"

        if market_data.get("closed", False):
            return False, "Market closed"

        # 2️⃣ Volume check
        if market_data.get("volume", 0) < self.min_volume:
            return False, "Low volume"

        # 3️⃣ Liquidity check
        if market_data.get("liquidity", 0) < self.min_liquidity:
            return False, "Low liquidity"

        # 4️⃣ Expiry check
        end_date_str = market_data.get("end_date")
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str)
            days_left = (end_date - datetime.utcnow()).days
            if days_left < self.min_days_to_expiry:
                return False, "Too close to expiry"

        # 5️⃣ Extreme probability check
        price_yes = market_data.get("price_yes", 0.5)
        if price_yes < 0.05 or price_yes > 0.95:
            return False, "Extreme probability market"

        # 6️⃣ Confidence check
        # if analysis.get("confidence_percent", 0) < self.min_confidence:
        #     return False, "Low confidence"

        # 7️⃣ Edge check
        if abs(analysis.get("edge_percent", 0)) < self.min_edge:
            return False, "Edge too small"

        # 8️⃣ Spread check (if available)
        spread = market_data.get("spread")
        if spread is not None and spread > self.max_spread:
            return False, "Spread too high"

        return True, "Trade valid"
