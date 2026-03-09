from datetime import datetime
import json

from core.pre_trade_validator import PreTradeValidator
from core.risk_manager import RiskManager
from bot.telegram_bot import send_trade_alert, send_trade_open
from core.position_manager import PositionManager

class Executor:

    def __init__(self, strategy, mode="DEMO"):
        # Initialize correctly
        self.strategy = strategy
        self.mode = mode

        self.validator = PreTradeValidator()
        self.risk_manager = RiskManager()
        self.position_manager = PositionManager()

    # ====================================
    # MAIN EXECUTION FUNCTION
    # ====================================
    def execute(self, analysis: dict, market_data: dict):
        # Check existing positions first
        self.position_manager.check_positions(
            self.risk_manager,
            market_data
        )
        
        # 1️⃣ Validate market conditions
        valid, reason = self.validator.validate(market_data, analysis)

        if not valid:
            print("❌ Trade rejected:", reason)
            return

        # 2️⃣ Calculate dynamic position size
        trade_size = self.risk_manager.calculate_position_size()

        # 3️⃣ Risk check
        if not self.risk_manager.can_trade(trade_size):
            print("❌ RiskManager blocked trade")
            return

        direction = analysis["direction"]

        entry_price = (
            market_data["price_yes"]
            if direction == "BUY_YES"
            else market_data["price_no"]
        )

        trade_info = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "market": market_data["market"],
            "direction": direction,
            "price": entry_price,
            "size": trade_size,
            "mode": self.mode,
            "confidence": analysis.get("confidence_percent"),
            "edge": analysis.get("edge_percent")
        }

        # 4️⃣ Register position in RiskManager
        self.risk_manager.open_position(trade_info)

        # 5️⃣ Demo vs Live execution
        if self.mode == "DEMO":
            print("🧪 DEMO TRADE EXECUTED")
        else:
            print("🚀 LIVE TRADE EXECUTION REQUIRED (MetaMask integration)")
            # TODO: Implement real order execution here

        # 6️⃣ Log trade
        self.log_trade(trade_info)

        # 7️⃣ Telegram notifications
        send_trade_alert(market_data, analysis)
        send_trade_open(trade_info)

    # ====================================
    # TRADE LOGGER
    # ====================================
    def log_trade(self, trade_info):

        try:
            with open("trade_log.json", "r") as f:
                data = json.load(f)
        except:
            data = []

        data.append(trade_info)

        with open("trade_log.json", "w") as f:
            json.dump(data, f, indent=2)







# from core.strategy_engine import StrategyEngine
# from bot.telegram_bot import send_trade_alert, send_trade_open
# import json
# from datetime import datetime

# from core.pre_trade_validator import PreTradeValidator

# validator = PreTradeValidator()

# strategy = StrategyEngine()

# class Executor:

#     def __init__(self):
#         self.trade_size = 50  # fixed size for now

#     def execute(self, signal, market_data):
#         analysis = strategy.analyze(market_data)
#         valid, reason = validator.validate(market_data, analysis)
        
#         if not valid:
#             print("Trade rejected:", reason)
#             return

#         # 🧠 Get AI analysis
#         analysis = strategy.analyze(market_data)

#         trade_info = {
#             "time": datetime.now().strftime("%H:%M:%S"),
#             "market": market_data["market"],
#             "direction": analysis["direction"],
#             "price": market_data["price_yes"],
#             "fair_value": analysis["fair_value"],
#             "confidence_label": analysis["confidence_label"],
#             "confidence_percent": analysis["confidence_percent"],
#             "edge_percent": analysis["edge_percent"],
#             "size": self.trade_size
#         }

#         print("Trade Info:", trade_info)

#         # 📜 Save to trade log
#         self.save_trade(trade_info)

#         # 📩 Send Telegram alerts
#         send_trade_alert(trade_info)
#         send_trade_open(trade_info)

#     # =========================
#     # TRADE LOGGER
#     # =========================

#     def save_trade(self, trade_info):
#         try:
#             with open("trade_log.json", "r") as f:
#                 trades = json.load(f)
#         except:
#             trades = []

#         trades.append(trade_info)

#         with open("trade_log.json", "w") as f:
#             json.dump(trades, f, indent=2)
