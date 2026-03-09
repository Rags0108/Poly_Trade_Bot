from core.base_strategy import BaseStrategy


class DipArbitrageStrategy(BaseStrategy):
    def __init__(self, dip_threshold=0.05):
        """
        dip_threshold = 5% price move considered abnormal
        """
        self.dip_threshold = dip_threshold
        self.name = "DIP_ARBITRAGE"

        # store last price for comparison
        self.last_price_yes = None

    # =====================================================
    # MAIN ANALYSIS
    def analyze(self, market_data: dict) -> dict:

        price_yes = market_data.get("price_yes", 0.5)
        price_no = market_data.get("price_no", 0.5)

        direction = "HOLD"
        confidence = 0
        edge = 0
        fair_value = price_yes

        # First run → no previous price
        if self.last_price_yes is None:
            self.last_price_yes = price_yes
            return {
                "direction": "HOLD",
                "confidence": 0,
                "fair_value": price_yes,
                "edge": 0,
                "strategy": self.name
            }

        # -------------------------------------------------
        # Calculate price change %
        change = price_yes - self.last_price_yes
        change_percent = change / self.last_price_yes

        # -------------------------------------------------
        # Detect DIP
        if change_percent <= -self.dip_threshold:
            direction = "BUY_YES"
            confidence = round(abs(change_percent) * 100 * 2, 2)
            edge = round(abs(change_percent) * 100, 2)
            fair_value = round(self.last_price_yes, 3)

        # -------------------------------------------------
        # Detect SPIKE
        elif change_percent >= self.dip_threshold:
            direction = "BUY_NO"
            confidence = round(abs(change_percent) * 100 * 2, 2)
            edge = round(abs(change_percent) * 100, 2)
            fair_value = round(self.last_price_yes, 3)

        # Update last price
        self.last_price_yes = price_yes

        return {
            "direction": direction,
            "confidence": confidence,
            "fair_value": fair_value,
            "edge": edge,
            "strategy": self.name
        }