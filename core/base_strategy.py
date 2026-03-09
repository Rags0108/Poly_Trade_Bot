class BaseStrategy:
    def analyze(self, market_data: dict) -> dict:
        """
        Must return:
        {
            "direction": "BUY_YES" / "BUY_NO" / "HOLD",
            "confidence": 0-100,
            "fair_value": float,
            "edge": float,
            "strategy": "strategy_name"
        }
        """
        raise NotImplementedError("Strategy must implement analyze()")
