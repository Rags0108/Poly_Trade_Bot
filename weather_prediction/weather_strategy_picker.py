"""
Weather Strategy Picker — Dynamic multi-strategy orchestrator.

Runs ALL weather strategies on EVERY market, ranks signals by
risk-adjusted edge, and returns the single best trade.

Features:
  - Strategy priority system (boost high-value strategies)
  - Win/loss learning per strategy
  - Confidence adjustments based on track record
  - Automatic strategy disabling after too many losses
  - Strategy restoration after idle period (prevents permanent blacklisting)
"""

from typing import Dict, List, Optional, Tuple

from weather_prediction.weather_api import WeatherAPIClient
from weather_prediction.weather_strategy import (
    WeatherForecastEdgeStrategy,
    ExtremeWeatherHunterStrategy,
    ConsensusDivergenceStrategy,
    SeasonalPatternStrategy,
    RapidChangeMomentumStrategy,
)


# Strategy priority boosts (added to confidence before ranking)
STRATEGY_PRIORITY = {
    "WEATHER_FORECAST_EDGE": 0.10,       # Primary strategy — decent track record
    "EXTREME_WEATHER_HUNTER": 0.15,      # High-conviction extreme events
    "CONSENSUS_DIVERGENCE": 0.05,        # Medium — needs divergence to fire
    "SEASONAL_PATTERN": 0.08,            # Seasonal patterns are reliable
    "RAPID_CHANGE_MOMENTUM": 0.12,       # Fast-moving — higher priority
}


class WeatherStrategyPicker:
    """
    All-in-one strategy dispatcher.
    
    Runs every strategy on every market, applies priority + learning boosts,
    returns the single best signal.
    """

    def __init__(self, weather_client: WeatherAPIClient):
        self.strategies = [
            WeatherForecastEdgeStrategy(weather_client, min_edge=0.03),
            ExtremeWeatherHunterStrategy(weather_client),
            ConsensusDivergenceStrategy(weather_client, divergence_threshold=2.5),
            SeasonalPatternStrategy(weather_client),
            RapidChangeMomentumStrategy(weather_client),
        ]

    def pick_best_signal(
        self,
        market_data: dict,
        disabled_strategies: List[str] = None,
        min_confidence: float = 0.3,
        confidence_adjustments: Dict[str, float] = None,
    ) -> Optional[Dict]:
        """
        Run all strategies and return the best signal.
        
        Args:
            market_data: Normalized market data dict
            disabled_strategies: List of strategy names to skip
            min_confidence: Minimum confidence threshold
            confidence_adjustments: {strategy_name: adjustment} from tracker
        
        Returns:
            Best trade signal dict, or None if no good signals
        """
        if disabled_strategies is None:
            disabled_strategies = []
        if confidence_adjustments is None:
            confidence_adjustments = {}

        signals = []

        for strategy in self.strategies:
            if strategy.name in disabled_strategies:
                continue

            try:
                result = strategy.analyze(market_data)

                if result.get("direction") not in ("BUY_YES", "BUY_NO"):
                    continue

                confidence = result.get("confidence_percent", 0) / 100
                edge = result.get("edge_percent", 0)

                if abs(edge) < 1:  # Minimum 1% edge
                    continue

                # Apply learning adjustment
                adj = confidence_adjustments.get(strategy.name, 0)
                adjusted_confidence = confidence + adj

                # Apply priority boost
                priority_boost = STRATEGY_PRIORITY.get(strategy.name, 0)
                rank_score = adjusted_confidence + priority_boost

                # Filter by min confidence
                if adjusted_confidence < min_confidence:
                    continue

                # Composite score for ranking: edge × adjusted_confidence
                composite = abs(edge) * rank_score

                result["adjusted_confidence"] = round(adjusted_confidence, 3)
                result["rank_score"] = round(rank_score, 3)
                result["composite_score"] = round(composite, 3)
                result["tracker_adjustment"] = round(adj, 3)
                result["priority_boost"] = round(priority_boost, 3)

                signals.append(result)

            except Exception as e:
                print(f"⚠️ Strategy {strategy.name} error: {e}")

        if not signals:
            return None

        # Rank by composite score (edge × confidence × priority)
        signals.sort(key=lambda s: s.get("composite_score", 0), reverse=True)

        return signals[0]

    def get_all_signals(
        self,
        market_data: dict,
        disabled_strategies: List[str] = None,
    ) -> List[Dict]:
        """Run all strategies and return ALL signals (for debugging)."""
        if disabled_strategies is None:
            disabled_strategies = []

        all_signals = []
        for strategy in self.strategies:
            if strategy.name in disabled_strategies:
                continue
            try:
                result = strategy.analyze(market_data)
                all_signals.append(result)
            except Exception as e:
                all_signals.append({
                    "strategy": strategy.name,
                    "direction": "ERROR",
                    "error": str(e),
                })

        return all_signals
