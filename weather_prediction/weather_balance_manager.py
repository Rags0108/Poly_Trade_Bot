"""
Weather Balance Manager — Risk Modes + Kelly Sizing + Auto-Graduation

Adapted from 5min_trade reference implementation for weather trading.

MODES:
  🌱 SEED ($0-5): Ultra-conservative. Only high-confidence forecasts.
  🌿 GROWTH ($5-20): Moderate risk. Kelly-sized bets, quality signals.
  🎯 FOCUSED ($20-50): Balanced. More strategies enabled.
  ⚖️ MEDIUM ($50-200): All strategies, moderate sizing.
  🔥 AGGRESSIVE ($200+): Full compound, max growth.

FEATURES:
  - Fractional Kelly criterion for edge-aware sizing
  - Consecutive loss/win streak multipliers
  - Drawdown tracking with circuit breaker
  - Auto-graduation/demotion based on balance
  - Session loss protection for small accounts
"""

import time
from typing import Dict, Optional


# ═══════════════════════════════════════════════════════════════════
# RISK MODE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════

class RiskMode:
    """Defines parameters for a trading risk mode."""
    def __init__(self, name: str, emoji: str, max_bet_pct: float,
                 reserve_pct: float, reserve_min: float,
                 max_positions: int, min_confidence: float,
                 kelly_fraction: float, description: str):
        self.name = name
        self.emoji = emoji
        self.max_bet_pct = max_bet_pct
        self.reserve_pct = reserve_pct
        self.reserve_min = reserve_min
        self.max_positions = max_positions
        self.min_confidence = min_confidence
        self.kelly_fraction = kelly_fraction
        self.description = description


RISK_MODES = {
    "seed": RiskMode(
        name="SEED", emoji="🌱",
        max_bet_pct=15.0, reserve_pct=20.0, reserve_min=0.50,
        max_positions=2, min_confidence=0.85,
        kelly_fraction=0.15,
        description="$0-5 | 2 positions | High confidence only",
    ),
    "growth": RiskMode(
        name="GROWTH", emoji="🌿",
        max_bet_pct=20.0, reserve_pct=18.0, reserve_min=1.50,
        max_positions=3, min_confidence=0.75,
        kelly_fraction=0.25,
        description="$5-20 | 3 positions | Kelly-sized growth",
    ),
    "focused": RiskMode(
        name="FOCUSED", emoji="🎯",
        max_bet_pct=22.0, reserve_pct=30.0, reserve_min=3.00,
        max_positions=5, min_confidence=0.60,
        kelly_fraction=0.25,
        description="$20-50 | 5 positions | Balanced approach",
    ),
    "medium": RiskMode(
        name="MEDIUM", emoji="⚖️",
        max_bet_pct=28.0, reserve_pct=20.0, reserve_min=5.00,
        max_positions=8, min_confidence=0.45,
        kelly_fraction=0.30,
        description="$50-200 | 8 positions | All strategies enabled",
    ),
    "aggressive": RiskMode(
        name="AGGRESSIVE", emoji="🔥",
        max_bet_pct=40.0, reserve_pct=10.0, reserve_min=5.00,
        max_positions=12, min_confidence=0.30,
        kelly_fraction=0.35,
        description="$200+ | 12 positions | Max compound growth",
    ),
}

# Auto-graduation thresholds
GRADUATION_THRESHOLDS = {
    "seed": ("growth", 5.0),
    "growth": ("focused", 20.0),
    "focused": ("medium", 50.0),
    "medium": ("aggressive", 200.0),
}

# Demotion thresholds
DEMOTION_THRESHOLDS = {
    "aggressive": ("medium", 200.0),
    "medium": ("focused", 50.0),
    "focused": ("growth", 20.0),
    "growth": ("seed", 5.0),
}


class WeatherBalanceManager:
    """
    Dynamic balance management with Kelly criterion sizing.
    
    Core features adapted from 5min_trade:
    - Fractional Kelly sizing based on edge and confidence
    - Risk mode auto-graduation/demotion
    - Consecutive streak adjustments (±5% per result)
    - Drawdown alerts + session circuit breaker
    - Strategy filtering by mode
    """

    # Consecutive loss/win sizing
    LOSS_SHRINK = 0.95       # -5% per consecutive loss
    WIN_GROW = 1.05          # +5% per consecutive win
    MAX_MULTIPLIER = 1.30    # Max growth from streaks
    MIN_MULTIPLIER = 0.60    # Min shrink from streaks

    def __init__(self, starting_balance: float = 100.0, mode: str = "growth"):
        self.balance = starting_balance
        self.starting_balance = starting_balance
        self.mode_name = mode.lower()
        self.mode = RISK_MODES.get(self.mode_name, RISK_MODES["growth"])

        self.open_positions: int = 0
        self.open_position_list: list = []

        # Peak/drawdown tracking
        self.peak_balance = starting_balance
        self.daily_start_balance = starting_balance
        self._daily_reset_ts = time.time()
        self._drawdown_alerted = False

        # Streak tracking
        self._consecutive_losses = 0
        self._consecutive_wins = 0
        self._size_multiplier = 1.0

        # Session circuit breaker
        self._session_start_balance = starting_balance
        self._session_paused_until = 0.0
        self._estimated_position_value = 0.0

        # Auto-migrate
        self.auto_migrate = True

        # Stats
        self.total_trades = 0
        self.total_wins = 0
        self.total_pnl = 0.0

    # ═══════════════════════════════════════════════════════════════
    # BALANCE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    def update_balance(self, new_balance: float):
        """Update balance and track peaks/daily reset."""
        self.balance = new_balance
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance
        # Reset daily tracking every 24h
        now = time.time()
        if now - self._daily_reset_ts > 86400:
            self.daily_start_balance = new_balance
            self._daily_reset_ts = now

    def record_result(self, won: bool, pnl: float = 0.0):
        """Track trade results for streak sizing."""
        self.total_trades += 1
        self.total_pnl += pnl

        if won:
            self.total_wins += 1
            self._consecutive_wins += 1
            self._consecutive_losses = 0
            self._size_multiplier = min(
                self.MAX_MULTIPLIER,
                self._size_multiplier * self.WIN_GROW,
            )
        else:
            self._consecutive_losses += 1
            self._consecutive_wins = 0
            self._size_multiplier = max(
                self.MIN_MULTIPLIER,
                self._size_multiplier * self.LOSS_SHRINK,
            )

    # ═══════════════════════════════════════════════════════════════
    # POSITION SIZING (KELLY CRITERION)
    # ═══════════════════════════════════════════════════════════════

    def get_position_size(
        self,
        confidence: float,
        edge_percent: float = 0.0,
        market_price: float = 0.5,
        kelly_override: float = 0.0,
    ) -> float:
        """
        Calculate position size using fractional Kelly criterion.
        
        Kelly formula:
            f* = (p × b - q) / b
        where:
            p = our estimated probability of winning
            q = 1 - p
            b = net odds (payout ratio)
            
        We use a fraction of full Kelly to reduce variance.
        
        Args:
            confidence: Strategy confidence (0-1)
            edge_percent: Our edge vs market (%)
            market_price: Market price of the outcome we're buying
            kelly_override: If provided by strategy, use this Kelly fraction
        
        Returns:
            Position size in dollars (>= $1 minimum or 0 if can't afford)
        """
        min_size = 1.0  # Polymarket minimum

        tradeable = self.tradeable_balance
        if tradeable < min_size:
            return 0

        # Estimate win probability from edge + confidence
        if market_price > 0 and market_price < 1:
            our_prob = market_price + edge_percent / 100
            our_prob = max(0.01, min(0.99, our_prob))
        else:
            our_prob = 0.5 + edge_percent / 200
            our_prob = max(0.01, min(0.99, our_prob))

        # Kelly calculation
        if kelly_override > 0:
            kelly_frac = kelly_override
        else:
            b = (1 / market_price) - 1 if market_price > 0 and market_price < 1 else 1
            q = 1 - our_prob
            if b > 0:
                full_kelly = (b * our_prob - q) / b
            else:
                full_kelly = 0
            # Apply mode-specific fractional Kelly
            kelly_frac = max(0, full_kelly * self.mode.kelly_fraction)

        # Kelly-based size
        kelly_size = tradeable * kelly_frac

        # Percentage-based fallback
        pct = self.mode.max_bet_pct * (0.5 + confidence * 0.5) / 100
        pct_size = tradeable * pct

        # Use the SMALLER of Kelly and percentage (conservative)
        if kelly_frac > 0:
            size = min(kelly_size, pct_size)
        else:
            size = pct_size

        # Apply streak multiplier
        size *= self._size_multiplier

        # Hard cap: percentage of total balance
        hard_cap = self.balance * (self.mode.max_bet_pct / 100)
        size = max(min_size, min(size, hard_cap))

        # Can't afford?
        if size > tradeable:
            if tradeable >= min_size:
                size = tradeable
            else:
                return 0

        return round(size, 2)

    # ═══════════════════════════════════════════════════════════════
    # CAN TRADE CHECK
    # ═══════════════════════════════════════════════════════════════

    def can_trade(self, confidence: float = 0.0) -> tuple:
        """
        Check if a new trade is allowed.
        
        Returns:
            (bool, reason_string)
        """
        # Session circuit breaker (SEED/GROWTH only)
        if self.mode_name in ("seed", "growth"):
            if self._session_start_balance > 0:
                effective = self.balance + self._estimated_position_value
                session_loss_pct = (1 - effective / self._session_start_balance) * 100
                if session_loss_pct >= 25:
                    now = time.time()
                    if self._session_paused_until == 0:
                        self._session_paused_until = now + 600  # 10 minutes
                        print(f"🚨 SESSION BREAKER: -{session_loss_pct:.0f}% loss in {self.mode.name}")
                    if now < self._session_paused_until:
                        remaining = (self._session_paused_until - now) / 60
                        return False, f"🚨 Session breaker ({remaining:.0f}m left)"
                    else:
                        self._session_start_balance = self.balance
                        self._session_paused_until = 0

        # Drawdown alerts (alert only, never blocks)
        dd = self.drawdown_pct
        if dd >= 25 and not self._drawdown_alerted:
            self._drawdown_alerted = True
            print(f"⚠️ DRAWDOWN ALERT: {dd:.1f}% from peak "
                  f"${self.peak_balance:.2f} → ${self.balance:.2f}")
        elif dd < 15:
            self._drawdown_alerted = False

        # Balance check
        if self.balance < 1.0:
            return False, "💀 Balance below $1 minimum"
        if self.tradeable_balance < 1.0:
            return False, f"🛡️ Only reserve left (${self.reserve:.2f})"

        # Position limit
        if self.open_positions >= self.mode.max_positions:
            return False, f"📊 {self.open_positions}/{self.mode.max_positions} positions open"

        # Confidence filter
        if confidence > 0 and confidence < self.mode.min_confidence:
            return False, f"📉 Confidence {confidence:.2f} < {self.mode.min_confidence}"

        return True, f"{self.mode.emoji} {self.mode.name}"

    # ═══════════════════════════════════════════════════════════════
    # PROPERTIES
    # ═══════════════════════════════════════════════════════════════

    @property
    def reserve(self) -> float:
        return max(self.mode.reserve_min, self.balance * self.mode.reserve_pct / 100)

    @property
    def tradeable_balance(self) -> float:
        return max(0, self.balance - self.reserve)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.balance) / self.peak_balance * 100

    @property
    def daily_pnl_pct(self) -> float:
        if self.daily_start_balance <= 0:
            return 0.0
        return (self.balance - self.daily_start_balance) / self.daily_start_balance * 100

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.total_wins / self.total_trades

    # ═══════════════════════════════════════════════════════════════
    # MODE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    def set_mode(self, mode: str) -> bool:
        mode = mode.lower()
        if mode in RISK_MODES:
            old = self.mode.name
            self.mode_name = mode
            self.mode = RISK_MODES[mode]
            print(f"📊 RISK MODE: {old} → {self.mode.emoji} {self.mode.name}")
            return True
        return False

    def check_auto_graduate(self) -> str:
        """Auto-graduate to next tier if balance exceeds threshold."""
        if not self.auto_migrate:
            return ""
        grad = GRADUATION_THRESHOLDS.get(self.mode_name)
        if grad:
            next_mode, threshold = grad
            if self.balance >= threshold:
                self.set_mode(next_mode)
                return (
                    f"🎉 GRADUATED! ${self.balance:.2f} ≥ ${threshold:.2f}\n"
                    f"Switched to {self.mode.emoji} {self.mode.name}: {self.mode.description}"
                )
        return ""

    def check_auto_demote(self) -> str:
        """Auto-demote to lower tier if balance drops below threshold."""
        if not self.auto_migrate:
            return ""
        demote = DEMOTION_THRESHOLDS.get(self.mode_name)
        if demote:
            lower_mode, threshold = demote
            effective = self.balance + self._estimated_position_value
            if effective < threshold:
                old_name = self.mode.name
                self.set_mode(lower_mode)
                further = self.check_auto_demote()  # Recursive for multi-level drops
                msg = (
                    f"📉 DEMOTED: {old_name} → {self.mode.emoji} {self.mode.name}\n"
                    f"Balance ${self.balance:.2f} < ${threshold:.2f}"
                )
                if further:
                    msg += f"\n{further}"
                return msg
        return ""

    def reset_tracking(self) -> str:
        """Reset all tracking data."""
        self.peak_balance = self.balance
        self.daily_start_balance = self.balance
        self._daily_reset_ts = time.time()
        self._drawdown_alerted = False
        self._size_multiplier = 1.0
        self._consecutive_losses = 0
        self._consecutive_wins = 0
        self._session_start_balance = self.balance
        self._session_paused_until = 0
        self._estimated_position_value = 0.0
        return f"✅ Tracking reset. Peak=${self.balance:.2f}, sizing=1.00×"

    def get_strategy_filter(self) -> Dict:
        """Which strategies are enabled for current mode."""
        disabled = []
        if self.mode_name == "seed":
            # Only high-confidence forecast edge
            disabled = ["EXTREME_WEATHER_HUNTER", "RAPID_CHANGE_MOMENTUM", "CONSENSUS_DIVERGENCE"]
        elif self.mode_name == "growth":
            disabled = ["RAPID_CHANGE_MOMENTUM"]

        return {
            "enabled": "all",
            "disabled": disabled,
            "min_confidence": self.mode.min_confidence,
        }

    # ═══════════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════════

    def get_status(self) -> Dict:
        return {
            "balance": round(self.balance, 2),
            "mode": self.mode.name,
            "mode_emoji": self.mode.emoji,
            "mode_desc": self.mode.description,
            "tradeable": round(self.tradeable_balance, 2),
            "reserve": round(self.reserve, 2),
            "max_positions": self.mode.max_positions,
            "open_positions": self.open_positions,
            "min_confidence": self.mode.min_confidence,
            "kelly_fraction": self.mode.kelly_fraction,
            "peak_balance": round(self.peak_balance, 2),
            "drawdown_pct": round(self.drawdown_pct, 2),
            "daily_pnl_pct": round(self.daily_pnl_pct, 2),
            "consecutive_losses": self._consecutive_losses,
            "consecutive_wins": self._consecutive_wins,
            "size_multiplier": round(self._size_multiplier, 3),
            "total_trades": self.total_trades,
            "total_wins": self.total_wins,
            "win_rate": round(self.win_rate * 100, 1),
            "total_pnl": round(self.total_pnl, 2),
        }
