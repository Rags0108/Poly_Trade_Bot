from datetime import datetime


class PositionManager:

    def __init__(
        self,
        stop_loss_percent=20,     # 20% loss
        take_profit_percent=40    # 40% gain
    ):
        self.stop_loss_percent = stop_loss_percent
        self.take_profit_percent = take_profit_percent

    # ====================================
    # CHECK POSITIONS FOR EXIT
    # ====================================
    def check_positions(self, risk_manager, market_data):

        for index, position in enumerate(risk_manager.open_positions[:]):

            current_price = (
                market_data["price_yes"]
                if position["direction"] == "BUY_YES"
                else market_data["price_no"]
            )

            entry_price = position["price"]

            pnl_percent = self.calculate_pnl_percent(
                entry_price,
                current_price,
                position["direction"]
            )

            # Stop loss
            if pnl_percent <= -self.stop_loss_percent:
                print("🛑 STOP LOSS TRIGGERED")
                self.close_position(index, risk_manager, pnl_percent, position)

            # Take profit
            elif pnl_percent >= self.take_profit_percent:
                print("🎯 TAKE PROFIT TRIGGERED")
                self.close_position(index, risk_manager, pnl_percent, position)

    # ====================================
    # CALCULATE PNL %
    # ====================================
    def calculate_pnl_percent(self, entry, current, direction):

        if direction == "BUY_YES":
            change = current - entry
        else:
            change = entry - current

        return round((change / entry) * 100, 2)

    # ====================================
    # CLOSE POSITION
    # ====================================
    def close_position(self, index, risk_manager, pnl_percent, position):

        profit_or_loss = position["size"] * (pnl_percent / 100)

        risk_manager.close_position(index, profit_or_loss)

        print(
            f"Position closed | "
            f"Market: {position['market']} | "
            f"PnL: {round(profit_or_loss,2)}"
        )