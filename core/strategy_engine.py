from core.llm_strategy import LLMStrategy
from core.dip_arbitrage import DipArbitrageStrategy


class StrategyEngine:
    def __init__(self):

        # Initialize strategies
        self.strategies = [
            LLMStrategy(use_api=True),          # Demo LLM
            DipArbitrageStrategy(dip_threshold=0.05)
        ]

    # =====================================================
    # RUN ALL STRATEGIES
    def analyze(self, market_data: dict) -> dict:

        results = []

        # Run each strategy
        for strategy in self.strategies:
            result = strategy.analyze(market_data)
            results.append(result)

        # -------------------------------------------------
        # Filter only BUY signals
        trade_signals = [
            r for r in results
            # if r["direction"] in ["BUY_YES", "BUY_NO"]
            if r.get("direction") in ["BUY_YES", "BUY_NO"]
        ]

        # If no strategy wants to trade
        if not trade_signals:
            return {
                "direction": "HOLD",
                "confidence": 0,
                "fair_value": market_data.get("price_yes"),
                "edge": 0,
                "strategy": "NONE"
            }

        # -------------------------------------------------
        # Pick strategy with highest EDGE
        best_signal = max(trade_signals, key=lambda x: x["edge"])
        return best_signal









# import math
# import random

# class StrategyEngine:

#     def calculate_fair_value(self, market_price):
#         bias = random.uniform(-0.15, 0.15)
#         fair_value = 1 / (1 + math.exp(-(market_price - 0.5 + bias) * 5))

#         return round(fair_value, 3)

#     def analyze(self, market_data):

#         market_price = market_data["price_yes"]

#         # 🧠 Model Estimated Probability
#         fair_value = self.calculate_fair_value(market_price)

#         # 📊 EDGE calculation
#         edge = fair_value - market_price
#         edge_percent = round(edge * 100, 2)

#         # 🎯 Direction
#         if edge > 0.02:
#             direction = "BUY YES"
#         elif edge < -0.02:
#             direction = "BUY NO"
#         else:
#             direction = "HOLD"

#         # 📈 Confidence score (based on distance from 0.5)
#         confidence_score = abs(fair_value - 0.5) * 2
#         confidence_percent = round(confidence_score * 100, 1)

#         if confidence_percent > 70:
#             confidence_level = "High"
#         elif confidence_percent > 45:
#             confidence_level = "Medium"
#         else:
#             confidence_level = "Low"

#         return {
#             "direction": direction,
#             "confidence_label": confidence_level,
#             "confidence_percent": confidence_percent,
#             "edge_percent": edge_percent,
#             "fair_value": fair_value
#         }
