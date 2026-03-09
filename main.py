import time
import threading
import json

from core.market_api import MarketAPI
from core.strategy_engine import StrategyEngine
from core.executor import Executor
from bot.telegram_bot import run_bot

# =========================
# MODE CONFIG
MODE = "DEMO"  # "DEMO" or "LIVE"

# =========================
# INIT CORE COMPONENTS
api = MarketAPI()
strategy = StrategyEngine()
executor = Executor(strategy=strategy, mode=MODE)

# =========================
# DASHBOARD STATUS
def update_status(bot_running=False, telegram_connected=False):
    status = {
        "bot_running": bot_running,
        "telegram_connected": telegram_connected
    }

    with open("bot_status.json", "w") as f:
        json.dump(status, f, indent=2)

# =========================
# MAIN LOOP
def trading_loop():
    print("Trading loop started...")
    update_status(bot_running=True)

    while True:
        print("Checking market...")

        market_data = api.get_market_data()
        if not market_data:
            time.sleep(10)
            continue

        analysis = strategy.analyze(market_data)

        executor.execute(analysis, market_data)

        time.sleep(30)

# =========================
# START SYSTEM
if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    trading_loop()









# import time
# import threading
# import json

# from core.market_api import MarketAPI
# from core.strategy_engine import StrategyEngine
# from core.executor import Executor
# from bot.telegram_bot import run_bot

# api = MarketAPI()
# strategy = StrategyEngine()
# executor = Executor()

# MODE = "DEMO"  # or "LIVE"

# # =========================
# # DASHBOARD STATUS FILE
# # =========================

# def update_status(bot_running=False, telegram_connected=False):
#     status = {
#         "bot_running": bot_running,
#         "telegram_connected": telegram_connected
#     }

#     with open("bot_status.json", "w") as f:
#         json.dump(status, f, indent=2)


# # =========================
# # TRADING LOOP
# # =========================

# def trading_loop():
#     print("Trading loop started...")
#     update_status(bot_running=True, telegram_connected=True)

#     while True:
#         try:
#             print("Checking market...")

#             market_data = api.get_market_data()
#             print("Market Data:", market_data)

#             signal = strategy.analyze(market_data)["direction"]
#             print("Signal:", signal)

#             executor.execute(signal, market_data)

#             time.sleep(20)  # check every 20 seconds

#         except Exception as e:
#             print("Error in trading loop:", e)
#             time.sleep(10)


# # =========================
# # START SYSTEM
# # =========================

# if __name__ == "__main__":
#     # Run trading loop in background thread
#     t = threading.Thread(target=trading_loop)
#     t.start()

#     # Run Telegram bot (blocking)
#     print("Telegram bot is running...")
#     run_bot()
