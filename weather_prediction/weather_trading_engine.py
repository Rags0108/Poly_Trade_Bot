"""
Weather Trading Engine — Main orchestrator for weather prediction trading.

This is the central brain that ties ALL components together:
  - Weather API (multi-source data with fallback)
  - Weather Model (ensemble predictions)
  - 5 Trading Strategies (forecast edge, extreme weather, consensus divergence,
    seasonal pattern, rapid change momentum)
  - Balance Manager (Kelly sizing + risk modes + auto-graduation)
  - Position Manager (stop-loss, take-profit, trailing stops)
  - Live Trader (paper/live CLOB execution)
  - Auto-Redeemer (claim resolved positions)
  - Market Scanner (discover weather markets)
  - Strategy Tracker (win/loss learning per strategy)

Adapted from 5min_trade TradingEngine architecture.
"""

import asyncio
import json
import os
import time
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from weather_prediction.weather_api import WeatherAPIClient
from weather_prediction.weather_model import WeatherPredictionModel
from weather_prediction.weather_strategy import (
    WeatherForecastEdgeStrategy,
    ExtremeWeatherHunterStrategy,
    ConsensusDivergenceStrategy,
    SeasonalPatternStrategy,
    RapidChangeMomentumStrategy,
)
from weather_prediction.weather_balance_manager import WeatherBalanceManager
from weather_prediction.weather_position_manager import WeatherPositionManager
from weather_prediction.weather_live_trader import WeatherLiveTrader
from weather_prediction.auto_redeem import WeatherAutoRedeemer
from weather_prediction.weather_market_scanner import WeatherMarketScanner


class StrategyTracker:
    """Track win/loss per strategy for adaptive confidence adjustments."""

    def __init__(self):
        self._stats: Dict[str, Dict] = {}

    def record(self, strategy_name: str, won: bool):
        if strategy_name not in self._stats:
            self._stats[strategy_name] = {
                "wins": 0, "losses": 0, "streak": 0, "idle_scans": 0
            }
        s = self._stats[strategy_name]
        if won:
            s["wins"] += 1
            s["streak"] = max(1, s["streak"] + 1) if s["streak"] >= 0 else 1
        else:
            s["losses"] += 1
            s["streak"] = min(-1, s["streak"] - 1) if s["streak"] <= 0 else -1
        s["idle_scans"] = 0

    def get_confidence_adjustment(self, strategy_name: str) -> float:
        """Get confidence adjustment (-0.12 to +0.15) based on track record."""
        if strategy_name not in self._stats:
            return 0.0
        s = self._stats[strategy_name]
        total = s["wins"] + s["losses"]
        if total < 3:
            return 0.0

        win_rate = s["wins"] / total
        streak = s["streak"]

        # Base adjustment from win rate
        adjustment = (win_rate - 0.5) * 0.30  # ±0.15 range

        # Streak bonus/penalty
        if streak > 0:
            adjustment += min(streak * 0.03, 0.09)
        elif streak < 0:
            adjustment -= min(abs(streak) * 0.02, 0.06)

        return max(-0.12, min(0.15, adjustment))

    def tick_idle(self, strategy_name: str):
        """Record an idle scan (no signal) for decay."""
        if strategy_name in self._stats:
            self._stats[strategy_name]["idle_scans"] += 1
            # After 50 idle scans, start decaying penalties
            if self._stats[strategy_name]["idle_scans"] > 50:
                s = self._stats[strategy_name]
                if s["streak"] < 0:
                    s["streak"] = min(0, s["streak"] + 1)

    def get_all_stats(self) -> Dict:
        result = {}
        for name, s in self._stats.items():
            total = s["wins"] + s["losses"]
            result[name] = {
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": round(s["wins"] / max(1, total) * 100, 1),
                "streak": s["streak"],
                "adjustment": round(self.get_confidence_adjustment(name), 3),
            }
        return result


class WeatherTradingEngine:
    """
    Main weather trading engine.
    
    Usage:
        engine = WeatherTradingEngine(mode="PAPER", starting_balance=100)
        engine.start()
    """

    def __init__(
        self,
        mode: str = "PAPER",
        starting_balance: float = 100.0,
        risk_mode: str = "growth",
        scan_interval: int = 30,
        openweathermap_key: str = "",
        weatherapi_key: str = "",
    ):
        self.mode = mode.upper()
        self.scan_interval = scan_interval
        self._running = False
        self._scan_count = 0
        self._last_scan_total_markets = 0
        self._last_scan_weather_markets = 0
        self._last_no_trade_reasons: Dict[str, int] = {}

        # Tunable trading thresholds (can be overridden in Railway env vars).
        self.min_edge_pct = float(os.getenv("WEATHER_MIN_EDGE", "2.0"))
        self.min_confidence_override = os.getenv("WEATHER_MIN_CONFIDENCE", "").strip()
        self.max_scan_markets = int(os.getenv("WEATHER_MAX_SCAN_MARKETS", "200"))

        # Core components
        self.weather_client = WeatherAPIClient(
            openweathermap_key=openweathermap_key or os.getenv("OPENWEATHERMAP_KEY", ""),
            weatherapi_key=weatherapi_key or os.getenv("WEATHERAPI_KEY", ""),
        )
        self.model = WeatherPredictionModel(self.weather_client)
        self.scanner = WeatherMarketScanner()
        self.balance_manager = WeatherBalanceManager(
            starting_balance=starting_balance,
            mode=risk_mode,
        )
        self.position_manager = WeatherPositionManager(
            stop_loss_pct=20.0,
            take_profit_pct=50.0,
            trailing_pct=15.0,
        )
        self.trader = WeatherLiveTrader(mode=self.mode)
        self.auto_redeemer = WeatherAutoRedeemer(
            private_key=os.getenv("POLY_PRIVATE_KEY", ""),
            proxy_wallet=os.getenv("POLY_PROXY_WALLET", ""),
        )
        self.strategy_tracker = StrategyTracker()

        # Strategies
        self.strategies = [
            WeatherForecastEdgeStrategy(self.weather_client, min_edge=0.05),
            ExtremeWeatherHunterStrategy(self.weather_client),
            ConsensusDivergenceStrategy(self.weather_client, divergence_threshold=3.0),
            SeasonalPatternStrategy(self.weather_client),
            RapidChangeMomentumStrategy(self.weather_client),
        ]

        # Trade log
        self.trade_log_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "weather_trade_log.json"
        )

    def start(self):
        """Start the trading engine."""
        print("=" * 60)
        print("🌤️  WEATHER TRADING ENGINE")
        print(f"   Mode: {self.mode}")
        print(f"   Balance: ${self.balance_manager.balance:.2f}")
        print(f"   Risk: {self.balance_manager.mode.emoji} {self.balance_manager.mode.name}")
        print(f"   Strategies: {len(self.strategies)}")
        print(f"   Scan interval: {self.scan_interval}s")
        print("=" * 60)

        # Init auto-redeemer
        if self.mode == "LIVE":
            self.auto_redeemer.init()

        self._running = True

        # Run async event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main_loop())
        except KeyboardInterrupt:
            print("\n🛑 Shutting down weather trading engine...")
        finally:
            self._running = False
            loop.close()

    def stop(self):
        """Stop the trading engine."""
        self._running = False
        print("🛑 Weather trading engine stopped")

    async def _main_loop(self):
        """Main trading loop."""
        last_redeem_check = 0
        last_report = 0

        while self._running:
            try:
                self._scan_count += 1

                # 1. Auto-graduate/demote based on balance
                grad_msg = self.balance_manager.check_auto_graduate()
                if grad_msg:
                    print(f"\n{grad_msg}\n")
                demote_msg = self.balance_manager.check_auto_demote()
                if demote_msg:
                    print(f"\n{demote_msg}\n")

                # 2. Check existing positions for exits
                await self._check_positions()

                # 3. Scan for weather markets
                markets = self.scanner.scan_markets(limit=self.max_scan_markets)
                weather_markets = [m for m in markets if m.get("price_yes") is not None]
                self._last_scan_total_markets = len(markets)
                self._last_scan_weather_markets = len(weather_markets)
                scan_reason_counter: Counter = Counter()

                if weather_markets:
                    print(f"\n🔍 Scan #{self._scan_count}: Found {len(weather_markets)} weather markets")

                    # 4. Run strategies on each market
                    for market_data in weather_markets:
                        eval_result = await self._evaluate_market(market_data)
                        for reason in eval_result.get("reasons", []):
                            scan_reason_counter[reason] += 1

                    self._last_no_trade_reasons = dict(scan_reason_counter)
                    if scan_reason_counter and self._scan_count % 5 == 0:
                        top_reasons = ", ".join(
                            f"{reason}:{count}" for reason, count in scan_reason_counter.most_common(3)
                        )
                        print(f"ℹ️ No-trade summary: {top_reasons}")
                else:
                    self._last_no_trade_reasons = {"NO_WEATHER_MARKETS": 1}
                    if self._scan_count % 10 == 0:
                        print(f"📭 Scan #{self._scan_count}: No weather markets found")

                # 5. Auto-redeem (every 2 minutes)
                now = time.time()
                if now - last_redeem_check > 120:
                    result = await self.auto_redeemer.check_and_redeem()
                    if result.get("redeemed", 0) > 0:
                        print(f"💰 Auto-redeemed: {result['redeemed']} positions "
                              f"(+${result['total_redeemed_usd']:.2f})")
                    last_redeem_check = now

                # 6. Periodic P&L report (every 5 minutes)
                if now - last_report > 300:
                    self._print_report()
                    last_report = now

                # 7. Update position values for balance manager
                self.balance_manager._estimated_position_value = (
                    self.position_manager.get_total_position_value()
                )

            except Exception as e:
                print(f"⚠️ Scan error: {e}")

            await asyncio.sleep(self.scan_interval)

    async def _evaluate_market(self, market_data: dict):
        """Run all strategies on a single market and execute the best signal."""
        strategy_filter = self.balance_manager.get_strategy_filter()
        disabled = strategy_filter.get("disabled", [])
        min_confidence = strategy_filter.get("min_confidence", 0.5)
        if self.min_confidence_override:
            try:
                min_confidence = float(self.min_confidence_override)
            except ValueError:
                pass

        signals = []
        reasons = []

        for strategy in self.strategies:
            if strategy.name in disabled:
                self.strategy_tracker.tick_idle(strategy.name)
                reasons.append("STRATEGY_DISABLED")
                continue

            try:
                result = strategy.analyze(market_data)

                if result.get("direction") in ("BUY_YES", "BUY_NO"):
                    confidence = result.get("confidence_percent", 0) / 100
                    edge = result.get("edge_percent", 0)

                    # Apply strategy tracker adjustment
                    adj = self.strategy_tracker.get_confidence_adjustment(strategy.name)
                    adjusted_confidence = confidence + adj

                    # Filter by minimum confidence
                    if adjusted_confidence >= min_confidence and abs(edge) >= self.min_edge_pct:
                        result["adjusted_confidence"] = round(adjusted_confidence, 3)
                        result["tracker_adjustment"] = round(adj, 3)
                        signals.append(result)
                    else:
                        if adjusted_confidence < min_confidence:
                            reasons.append("LOW_CONFIDENCE")
                        if abs(edge) < self.min_edge_pct:
                            reasons.append("LOW_EDGE")
                else:
                    self.strategy_tracker.tick_idle(strategy.name)
                    reasons.append("NO_DIRECTION")
            except Exception as e:
                print(f"⚠️ Strategy {strategy.name} error: {e}")
                reasons.append("STRATEGY_ERROR")

        if not signals:
            return {"traded": False, "reasons": reasons}

        # Pick best signal by effective edge (edge × confidence)
        best = max(signals, key=lambda s: abs(s.get("edge_percent", 0)) * s.get("adjusted_confidence", 0.5))

        # Execute trade
        executed = await self._execute_trade(best, market_data)
        if not executed:
            reasons.append("EXECUTION_SKIPPED")
        return {"traded": bool(executed), "reasons": reasons}

    async def _execute_trade(self, signal: dict, market_data: dict):
        """Execute a trade based on the best strategy signal."""
        direction = signal["direction"]
        confidence = signal.get("adjusted_confidence", signal.get("confidence_percent", 0) / 100)
        edge_pct = signal.get("edge_percent", 0)
        strategy_name = signal.get("strategy", "UNKNOWN")
        kelly = signal.get("kelly_fraction", 0)

        # Check if we can trade
        can_trade, reason = self.balance_manager.can_trade(confidence)
        if not can_trade:
            return False

        # Get market details
        price_yes = market_data.get("price_yes", 0.5)
        price_no = market_data.get("price_no", 0.5)
        market_question = market_data.get("market", "")

        if direction == "BUY_YES":
            price = price_yes
            token_id = market_data.get("yes_token_id", "")
        else:
            price = price_no
            token_id = market_data.get("no_token_id", "")

        if not token_id or price is None or price <= 0:
            return False

        # Calculate position size
        size = self.balance_manager.get_position_size(
            confidence=confidence,
            edge_percent=edge_pct,
            market_price=price,
            kelly_override=kelly,
        )

        if size <= 0:
            return False

        # Execute order
        order = self.trader.execute_order(
            token_id=token_id,
            side="BUY",
            size=size,
            price=price,
            market_question=market_question,
        )

        if not order:
            return False

        # Open position tracking
        shares = order.get("shares", size / price)
        position = self.position_manager.open_position(
            market_id=market_data.get("market_id", ""),
            market_question=market_question,
            token_id=token_id,
            direction="YES" if direction == "BUY_YES" else "NO",
            entry_price=price,
            size=size,
            shares=shares,
            strategy=strategy_name,
            city_key=market_data.get("city_key", ""),
            market_end_date=market_data.get("end_date", ""),
        )

        # Update balance manager
        self.balance_manager.open_positions += 1
        self.balance_manager.update_balance(self.balance_manager.balance - size)

        # Log trade
        trade_info = {
            "time": datetime.now(timezone.utc).isoformat(),
            "market": market_question[:80],
            "direction": direction,
            "price": round(price, 4),
            "size": round(size, 2),
            "shares": round(shares, 2),
            "edge_percent": round(edge_pct, 2),
            "confidence": round(confidence, 3),
            "strategy": strategy_name,
            "kelly_fraction": round(kelly, 4),
            "mode": self.mode,
            "position_id": position.position_id,
        }
        self._log_trade(trade_info)

        print(f"\n{'='*50}")
        print(f"📊 TRADE EXECUTED | {strategy_name}")
        print(f"   Market: {market_question[:60]}")
        print(f"   Direction: {direction}")
        print(f"   Price: ${price:.4f} | Size: ${size:.2f}")
        print(f"   Edge: {edge_pct:.1f}% | Confidence: {confidence:.1%}")
        print(f"   Kelly: {kelly:.2%} | Balance: ${self.balance_manager.balance:.2f}")
        print(f"{'='*50}\n")
        return True

    async def _check_positions(self):
        """Check all open positions for exit conditions."""
        if not self.position_manager.positions:
            return

        # Get current prices for all open positions
        price_updates = {}
        for pos in self.position_manager.positions:
            prices = self.scanner.get_market_prices(pos.market_id)
            if prices:
                if pos.direction == "YES":
                    price_updates[pos.token_id] = prices.get("price_yes", pos.current_price)
                else:
                    price_updates[pos.token_id] = prices.get("price_no", pos.current_price)

        # Check for exits
        exits = self.position_manager.check_exits(price_updates)

        for exit_info in exits:
            pos = exit_info["position"]
            reason = exit_info["reason"]
            pnl = exit_info["pnl"]

            # Execute sell
            sell_order = self.trader.execute_order(
                token_id=pos.token_id,
                side="SELL",
                size=pos.shares * pos.current_price,
                price=pos.current_price,
                market_question=pos.market_question,
            )

            if sell_order:
                # Close position
                result = self.position_manager.close_position(pos, reason, pnl)

                # Update balance
                exit_value = pos.current_price * pos.shares
                self.balance_manager.update_balance(self.balance_manager.balance + exit_value)
                self.balance_manager.open_positions = max(0, self.balance_manager.open_positions - 1)

                # Record result for strategy tracker and balance manager
                won = pnl > 0
                self.strategy_tracker.record(pos.strategy, won)
                self.balance_manager.record_result(won, pnl)

                # Set cooldown after stop-loss
                if "STOP LOSS" in reason:
                    self.trader.set_cooldown(pos.token_id, "BUY", 60)

                print(f"\n{'='*50}")
                print(f"{'🟢' if won else '🔴'} POSITION CLOSED | {reason}")
                print(f"   Market: {pos.market_question[:60]}")
                print(f"   P&L: {'+'if pnl>=0 else ''}{pnl:.2f} ({pos.unrealized_pnl_pct:+.1f}%)")
                print(f"   Balance: ${self.balance_manager.balance:.2f}")
                print(f"{'='*50}\n")

                # Log trade close
                self._log_trade({
                    "time": datetime.now(timezone.utc).isoformat(),
                    "event": "CLOSE",
                    "market": pos.market_question[:80],
                    "direction": pos.direction,
                    "entry_price": round(pos.entry_price, 4),
                    "exit_price": round(pos.current_price, 4),
                    "pnl": round(pnl, 2),
                    "reason": reason,
                    "strategy": pos.strategy,
                })

    def _print_report(self):
        """Print periodic P&L report."""
        bal = self.balance_manager.get_status()
        pos = self.position_manager.get_stats()
        strat = self.strategy_tracker.get_all_stats()

        print(f"\n{'='*60}")
        print(f"📈 WEATHER TRADING REPORT | {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        print(f"{'='*60}")
        print(f"   Balance: ${bal['balance']:.2f} | "
              f"Peak: ${bal['peak_balance']:.2f} | "
              f"Drawdown: {bal['drawdown_pct']:.1f}%")
        print(f"   Mode: {bal['mode_emoji']} {bal['mode']} | "
              f"Tradeable: ${bal['tradeable']:.2f} | "
              f"Reserve: ${bal['reserve']:.2f}")
        print(f"   Positions: {pos['open_positions']} open | "
              f"{pos['closed_positions']} closed | "
              f"Win rate: {pos['win_rate']:.1f}%")
        print(f"   P&L: Open ${pos['open_pnl']:.2f} | "
              f"Realized ${pos['realized_pnl']:.2f} | "
              f"Total ${pos['total_pnl']:.2f}")
        print(f"   Sizing: {bal['size_multiplier']:.2f}× | "
              f"Wins: {bal['consecutive_wins']} | "
              f"Losses: {bal['consecutive_losses']}")

        if strat:
            print(f"\n   Strategy Performance:")
            for name, stats in strat.items():
                print(f"     {name}: {stats['wins']}W/{stats['losses']}L "
                      f"({stats['win_rate']:.0f}%) adj={stats['adjustment']:+.3f}")

        print(f"{'='*60}\n")

    def _log_trade(self, trade_info: dict):
        """Append trade to JSON log file."""
        try:
            try:
                with open(self.trade_log_path, "r") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = []

            data.append(trade_info)

            with open(self.trade_log_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Trade log error: {e}")

    def get_full_status(self) -> Dict:
        """Get complete engine status."""
        return {
            "engine": {
                "mode": self.mode,
                "running": self._running,
                "scan_count": self._scan_count,
                "strategies": len(self.strategies),
                "last_scan_total_markets": self._last_scan_total_markets,
                "last_scan_weather_markets": self._last_scan_weather_markets,
                "last_no_trade_reasons": self._last_no_trade_reasons,
                "min_edge_pct": self.min_edge_pct,
                "min_confidence": self.min_confidence_override or "mode_default",
            },
            "balance": self.balance_manager.get_status(),
            "positions": self.position_manager.get_stats(),
            "trader": self.trader.get_stats(),
            "auto_redeem": self.auto_redeemer.get_stats(),
            "strategy_stats": self.strategy_tracker.get_all_stats(),
        }
