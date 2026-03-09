from datetime import datetime


class RiskManager:

    def __init__(
        self,
        starting_balance=1000,
        risk_per_trade_percent=2,
        max_daily_loss_percent=10,
        max_open_positions=5
    ):
        self.starting_balance = starting_balance
        self.current_balance = starting_balance

        self.risk_per_trade_percent = risk_per_trade_percent
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_open_positions = max_open_positions

        self.open_positions = []
        self.daily_loss = 0
        self.last_reset_date = datetime.utcnow().date()

    # =========================
    # RESET DAILY LOSS
    # =========================
    def reset_daily_if_needed(self):
        today = datetime.utcnow().date()

        if today != self.last_reset_date:
            self.daily_loss = 0
            self.last_reset_date = today

    # =========================
    # CHECK IF TRADE ALLOWED
    # =========================
    def can_trade(self, trade_size):

        self.reset_daily_if_needed()

        # 1️⃣ Max open positions
        if len(self.open_positions) >= self.max_open_positions:
            print("❌ Max open positions reached")
            return False

        # 2️⃣ Max risk per trade
        max_allowed = self.current_balance * (self.risk_per_trade_percent / 100)

        if trade_size > max_allowed:
            print("❌ Trade size exceeds risk per trade limit")
            return False

        # 3️⃣ Daily loss protection
        max_daily_loss = self.starting_balance * (self.max_daily_loss_percent / 100)

        if self.daily_loss >= max_daily_loss:
            print("❌ Max daily loss reached")
            return False

        return True

    # =========================
    # REGISTER NEW POSITION
    # =========================
    def open_position(self, trade_info):

        self.open_positions.append(trade_info)

    # =========================
    # CLOSE POSITION
    # =========================
    def close_position(self, position_index, profit_or_loss):

        if position_index >= len(self.open_positions):
            return

        position = self.open_positions.pop(position_index)

        self.current_balance += profit_or_loss

        if profit_or_loss < 0:
            self.daily_loss += abs(profit_or_loss)

    # =========================
    # POSITION SIZE CALCULATOR
    # =========================
    def calculate_position_size(self):

        return round(
            self.current_balance * (self.risk_per_trade_percent / 100),
            2
        )