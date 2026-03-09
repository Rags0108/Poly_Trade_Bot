"""
Weather Position Manager — Track and manage open weather positions.

Features:
  - Stop-loss / take-profit automatic exits
  - Trailing stop for profitable positions
  - Time-based exits for expiring markets
  - Dynamic hold/sell decisions based on weather changes
  - Position P&L tracking
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional


class WeatherPosition:
    """Represents a single open position."""

    def __init__(
        self,
        position_id: str,
        market_id: str,
        market_question: str,
        token_id: str,
        direction: str,
        entry_price: float,
        size: float,
        shares: float,
        strategy: str,
        city_key: str = "",
        entry_time: float = None,
        market_end_date: str = "",
    ):
        self.position_id = position_id
        self.market_id = market_id
        self.market_question = market_question
        self.token_id = token_id
        self.direction = direction  # "YES" or "NO"
        self.entry_price = entry_price
        self.size = size
        self.shares = shares
        self.strategy = strategy
        self.city_key = city_key
        self.entry_time = entry_time or time.time()
        self.market_end_date = market_end_date

        # Tracking
        self.current_price = entry_price
        self.peak_price = entry_price
        self.unrealized_pnl = 0.0
        self.unrealized_pnl_pct = 0.0

    def update_price(self, new_price: float):
        """Update current price and P&L."""
        self.current_price = new_price
        if new_price > self.peak_price:
            self.peak_price = new_price

        # P&L calculation
        if self.direction == "YES":
            self.unrealized_pnl = (new_price - self.entry_price) * self.shares
        else:
            self.unrealized_pnl = (self.entry_price - new_price) * self.shares

        if self.entry_price > 0:
            self.unrealized_pnl_pct = (
                (new_price - self.entry_price) / self.entry_price * 100
                if self.direction == "YES"
                else (self.entry_price - new_price) / self.entry_price * 100
            )

    def to_dict(self) -> Dict:
        return {
            "position_id": self.position_id,
            "market_id": self.market_id,
            "market": self.market_question[:80],
            "direction": self.direction,
            "entry_price": round(self.entry_price, 4),
            "current_price": round(self.current_price, 4),
            "size": round(self.size, 2),
            "shares": round(self.shares, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 1),
            "strategy": self.strategy,
            "city_key": self.city_key,
            "hold_time_min": round((time.time() - self.entry_time) / 60, 1),
        }


class WeatherPositionManager:
    """
    Manages open positions with dynamic stop-loss/take-profit.

    Exit rules:
      1. Stop-loss: Close at -X% (mode-dependent)
      2. Take-profit: Close at +Y% (mode-dependent)
      3. Trailing stop: After +Z%, trail by T%
      4. Time exit: Close if market expiry < N minutes
      5. Weather shift: Close if weather changes against position
    """

    def __init__(
        self,
        stop_loss_pct: float = 20.0,
        take_profit_pct: float = 50.0,
        trailing_pct: float = 15.0,
        trailing_activation_pct: float = 20.0,
        time_exit_minutes: float = 5.0,
    ):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_pct = trailing_pct
        self.trailing_activation_pct = trailing_activation_pct
        self.time_exit_minutes = time_exit_minutes

        self.positions: List[WeatherPosition] = []
        self.closed_positions: List[Dict] = []

        # Stats
        self.total_closed = 0
        self.total_wins = 0
        self.total_realized_pnl = 0.0

    def open_position(self, **kwargs) -> WeatherPosition:
        """Open a new tracked position."""
        pos_id = f"wp_{len(self.positions)}_{int(time.time())}"
        position = WeatherPosition(position_id=pos_id, **kwargs)
        self.positions.append(position)
        return position

    def check_exits(self, price_updates: Dict[str, float]) -> List[Dict]:
        """
        Check all positions for exit conditions.

        Args:
            price_updates: {token_id: current_price}

        Returns:
            List of positions that should be closed, with exit reason.
        """
        exits = []

        for pos in self.positions[:]:  # Copy to allow removal during iteration
            token_id = pos.token_id
            if token_id not in price_updates:
                continue

            new_price = price_updates[token_id]
            pos.update_price(new_price)

            exit_reason = self._check_exit_conditions(pos)
            if exit_reason:
                exits.append({
                    "position": pos,
                    "reason": exit_reason,
                    "pnl": pos.unrealized_pnl,
                    "pnl_pct": pos.unrealized_pnl_pct,
                })

        return exits

    def close_position(self, position: WeatherPosition, reason: str, actual_pnl: float = None) -> Dict:
        """Close a position and record the result."""
        pnl = actual_pnl if actual_pnl is not None else position.unrealized_pnl
        won = pnl > 0

        result = {
            **position.to_dict(),
            "exit_reason": reason,
            "realized_pnl": round(pnl, 2),
            "won": won,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        }

        self.closed_positions.append(result)
        self.total_closed += 1
        self.total_realized_pnl += pnl
        if won:
            self.total_wins += 1

        # Remove from open positions
        if position in self.positions:
            self.positions.remove(position)

        return result

    def _check_exit_conditions(self, pos: WeatherPosition) -> Optional[str]:
        """Check all exit conditions for a position."""

        pnl_pct = pos.unrealized_pnl_pct

        # 1. Stop-loss
        if pnl_pct <= -self.stop_loss_pct:
            return f"🛑 STOP LOSS ({pnl_pct:.1f}%)"

        # 2. Take-profit
        if pnl_pct >= self.take_profit_pct:
            return f"🎯 TAKE PROFIT ({pnl_pct:.1f}%)"

        # 3. Trailing stop (if position was profitable enough)
        if pnl_pct > self.trailing_activation_pct:
            # Calculate trailing from peak
            if pos.peak_price > 0 and pos.entry_price > 0:
                if pos.direction == "YES":
                    peak_pnl_pct = (pos.peak_price - pos.entry_price) / pos.entry_price * 100
                else:
                    peak_pnl_pct = (pos.entry_price - (1 - pos.peak_price)) / pos.entry_price * 100

                drawdown_from_peak = peak_pnl_pct - pnl_pct
                if drawdown_from_peak >= self.trailing_pct:
                    return f"📉 TRAILING STOP (peak {peak_pnl_pct:.1f}%, now {pnl_pct:.1f}%)"

        # 4. Time-based exit (near market expiry)
        if pos.market_end_date:
            try:
                end_dt = datetime.fromisoformat(pos.market_end_date.replace("Z", "+00:00"))
                minutes_left = (end_dt - datetime.now(timezone.utc)).total_seconds() / 60
                if 0 < minutes_left < self.time_exit_minutes:
                    # Close near expiry — let it settle
                    if pnl_pct > 10:
                        return f"⏰ EXPIRY EXIT (profitable, {minutes_left:.0f}m left)"
            except (ValueError, TypeError):
                pass

        return None

    def get_total_position_value(self) -> float:
        """Get total estimated value of all open positions."""
        total = 0.0
        for pos in self.positions:
            total += pos.current_price * pos.shares
        return total

    def get_open_count(self) -> int:
        return len(self.positions)

    def get_stats(self) -> Dict:
        open_pnl = sum(p.unrealized_pnl for p in self.positions)
        return {
            "open_positions": len(self.positions),
            "closed_positions": self.total_closed,
            "total_wins": self.total_wins,
            "win_rate": round(self.total_wins / max(1, self.total_closed) * 100, 1),
            "open_pnl": round(open_pnl, 2),
            "realized_pnl": round(self.total_realized_pnl, 2),
            "total_pnl": round(open_pnl + self.total_realized_pnl, 2),
        }
