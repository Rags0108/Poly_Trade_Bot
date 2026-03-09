"""
Weather Trading Strategy — Multi-Strategy Weather Market Trading

Strategies:
  1. Forecast Edge — Use ensemble model vs market price
  2. Extreme Weather Hunter — High-confidence extreme event bets
  3. Consensus Divergence — Multi-source disagreement exploitation
  4. Seasonal Pattern — Historical seasonal patterns vs market mispricing
  5. Rapid Change Momentum — Trade sudden weather shifts

Integrates with:
  - WeatherPredictionModel for probability estimates
  - WeatherAPIClient for real-time data
  - Kelly criterion for position sizing
  - Risk management for capital protection
"""

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from core.base_strategy import BaseStrategy
from weather_prediction.weather_api import WeatherAPIClient, WEATHER_CITIES
from weather_prediction.weather_model import WeatherPredictionModel


class WeatherForecastEdgeStrategy(BaseStrategy):
    """
    Primary strategy: Use ensemble weather model to find mispricings.
    
    Compares our multi-model probability estimate against the market price.
    Trades when edge > min_edge threshold with sufficient confidence.
    """

    def __init__(self, weather_client: WeatherAPIClient, min_edge: float = 0.05):
        self.name = "WEATHER_FORECAST_EDGE"
        self.client = weather_client
        self.model = WeatherPredictionModel(weather_client)
        self.min_edge = min_edge
        self._last_signals: Dict[str, dict] = {}

    def analyze(self, market_data: dict) -> dict:
        """Analyze a weather market for trading opportunities."""
        question = market_data.get("market", "")
        price_yes = market_data.get("price_yes", 0.5)
        price_no = market_data.get("price_no", 0.5)

        if price_yes is None or price_no is None:
            return self._hold("Invalid price data")

        # Try to identify city and event from the market question
        city_key = self._identify_city(question)
        if not city_key:
            return self._hold("Cannot identify city from market question")

        # Calculate edge using our model
        edge_result = self.model.calculate_edge(
            city_key=city_key,
            market_question=question,
            market_price_yes=price_yes,
        )

        if not edge_result:
            return self._hold("Cannot calculate edge for this market")

        direction = edge_result["direction"]
        edge = edge_result["edge_percent"]
        confidence = edge_result["confidence"]
        our_prob = edge_result["our_probability"]
        kelly = edge_result["kelly_fraction"]

        # Apply minimum edge filter
        if abs(edge) < self.min_edge * 100:
            return self._hold(f"Edge too small: {edge:.1f}%")

        # Confidence-weighted edge
        effective_edge = abs(edge) * confidence

        return {
            "direction": direction,
            "confidence_percent": round(confidence * 100, 2),
            "fair_value": round(our_prob, 4),
            "edge": round(edge, 2),
            "edge_percent": round(edge, 2),
            "strategy": self.name,
            "kelly_fraction": kelly,
            "effective_edge": round(effective_edge, 2),
            "prediction": edge_result.get("prediction", {}),
        }

    def _identify_city(self, question: str) -> Optional[str]:
        """Match market question to a tracked city."""
        q = question.lower()
        for key, city in WEATHER_CITIES.items():
            name_lower = city["name"].lower()
            # Match by city name or common abbreviations
            if name_lower in q:
                return key
            # Handle abbreviations
            abbreviations = {
                "nyc": "new_york", "ny": "new_york",
                "la": "los_angeles", "sf": "san_francisco",
                "dc": "washington_dc", "d.c.": "washington_dc",
            }
            for abbr, city_k in abbreviations.items():
                if abbr in q:
                    return city_k
        return None

    def _hold(self, reason: str) -> dict:
        return {
            "direction": "HOLD",
            "confidence_percent": 0,
            "fair_value": 0.5,
            "edge": 0,
            "edge_percent": 0,
            "strategy": self.name,
            "reason": reason,
        }


class ExtremeWeatherHunterStrategy(BaseStrategy):
    """
    Hunt for extreme weather events that markets underestimate.
    
    Markets tend to underprice extreme events because:
    1. People anchor to recent "normal" weather
    2. Extreme events have fat-tail distributions
    3. Climate change increases tail-risk
    """

    def __init__(self, weather_client: WeatherAPIClient):
        self.name = "EXTREME_WEATHER_HUNTER"
        self.client = weather_client
        self.model = WeatherPredictionModel(weather_client)

    def analyze(self, market_data: dict) -> dict:
        question = market_data.get("market", "")
        price_yes = market_data.get("price_yes", 0.5)

        city_key = self._identify_city(question)
        if not city_key:
            return self._hold("Cannot identify city")

        # Check for extreme weather alerts
        alerts = self.client.detect_extreme_weather(city_key)

        if not alerts:
            return self._hold("No extreme weather detected")

        # Find the most severe alert
        severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        best_alert = max(alerts, key=lambda a: severity_rank.get(a.get("severity", "LOW"), 0))

        severity = severity_rank.get(best_alert.get("severity", "LOW"), 0)

        # Higher severity = higher confidence
        confidence = min(0.95, 0.50 + severity * 0.12)

        # If extreme weather is happening/imminent and market hasn't priced it in
        our_prob = min(0.95, 0.60 + severity * 0.10)
        edge = (our_prob - price_yes) * 100

        if abs(edge) < 3:
            return self._hold("Market already pricing extreme event")

        direction = "BUY_YES" if edge > 0 else "BUY_NO"

        # Kelly for extreme events (more conservative)
        if direction == "BUY_YES":
            p = our_prob
            b = (1 / price_yes) - 1 if price_yes > 0 else 0
        else:
            p = 1 - our_prob
            b = (1 / (1 - price_yes)) - 1 if price_yes < 1 else 0
        kelly = max(0, (b * p - (1 - p)) / b) if b > 0 else 0
        kelly = min(0.15, kelly)  # More conservative for extreme events

        return {
            "direction": direction,
            "confidence_percent": round(confidence * 100, 2),
            "fair_value": round(our_prob, 4),
            "edge": round(edge, 2),
            "edge_percent": round(edge, 2),
            "strategy": self.name,
            "kelly_fraction": round(kelly, 4),
            "alert": best_alert,
        }

    def _identify_city(self, question: str) -> Optional[str]:
        q = question.lower()
        for key, city in WEATHER_CITIES.items():
            if city["name"].lower() in q:
                return key
            abbreviations = {
                "nyc": "new_york", "ny": "new_york",
                "la": "los_angeles", "sf": "san_francisco",
                "dc": "washington_dc",
            }
            for abbr, city_k in abbreviations.items():
                if abbr in q:
                    return city_k
        return None

    def _hold(self, reason: str) -> dict:
        return {
            "direction": "HOLD",
            "confidence_percent": 0,
            "fair_value": 0.5,
            "edge": 0,
            "edge_percent": 0,
            "strategy": self.name,
            "reason": reason,
        }


class ConsensusDivergenceStrategy(BaseStrategy):
    """
    Exploit disagreements between weather sources.
    
    When Open-Meteo, OpenWeatherMap, and WeatherAPI disagree significantly,
    the market often follows the "popular" source. We trade toward the
    consensus of the more accurate sources.
    """

    def __init__(self, weather_client: WeatherAPIClient, divergence_threshold: float = 3.0):
        self.name = "CONSENSUS_DIVERGENCE"
        self.client = weather_client
        self.model = WeatherPredictionModel(weather_client)
        self.divergence_threshold = divergence_threshold

    def analyze(self, market_data: dict) -> dict:
        question = market_data.get("market", "")
        price_yes = market_data.get("price_yes", 0.5)

        city_key = self._identify_city(question)
        if not city_key:
            return self._hold("Cannot identify city")

        # Get temperature prediction with all model outputs
        prediction = self.model.predict_temperature(city_key, hours_ahead=24)
        if not prediction:
            return self._hold("Cannot get prediction")

        model_outputs = prediction.get("model_outputs", {})
        if len(model_outputs) < 3:
            return self._hold("Not enough models for divergence")

        temps = list(model_outputs.values())
        spread = max(temps) - min(temps)

        if spread < self.divergence_threshold:
            return self._hold(f"Model agreement too tight: {spread:.1f}°C")

        # Our ensemble prediction should be more accurate than any single model
        ensemble_temp = prediction["predicted_temp_c"]
        confidence = prediction["confidence"]

        # Parse threshold from market question
        event_type, threshold = self.model._parse_market_question(question)
        if not event_type or threshold is None:
            return self._hold("Cannot parse market question")

        # Calculate our probability
        edge_result = self.model.calculate_edge(
            city_key=city_key,
            market_question=question,
            market_price_yes=price_yes,
        )

        if not edge_result:
            return self._hold("Cannot calculate edge")

        # Boost confidence when sources disagree (more opportunity)
        boosted_confidence = min(0.95, confidence + 0.10)
        edge = edge_result["edge_percent"]

        if abs(edge) < 2:
            return self._hold("Edge too small despite divergence")

        direction = edge_result["direction"]
        kelly = min(0.20, edge_result.get("kelly_fraction", 0))

        return {
            "direction": direction,
            "confidence_percent": round(boosted_confidence * 100, 2),
            "fair_value": edge_result["our_probability"],
            "edge": round(edge, 2),
            "edge_percent": round(edge, 2),
            "strategy": self.name,
            "kelly_fraction": round(kelly, 4),
            "model_spread": round(spread, 1),
        }

    def _identify_city(self, question: str) -> Optional[str]:
        q = question.lower()
        for key, city in WEATHER_CITIES.items():
            if city["name"].lower() in q:
                return key
        return None

    def _hold(self, reason: str) -> dict:
        return {
            "direction": "HOLD",
            "confidence_percent": 0,
            "fair_value": 0.5,
            "edge": 0,
            "edge_percent": 0,
            "strategy": self.name,
            "reason": reason,
        }


class SeasonalPatternStrategy(BaseStrategy):
    """
    Exploit seasonal weather patterns that markets misprice.
    
    Uses 30-day historical data to identify current seasonal trends
    and predict if the market is over/underpricing based on season.
    """

    def __init__(self, weather_client: WeatherAPIClient):
        self.name = "SEASONAL_PATTERN"
        self.client = weather_client
        self.model = WeatherPredictionModel(weather_client)

    def analyze(self, market_data: dict) -> dict:
        question = market_data.get("market", "")
        price_yes = market_data.get("price_yes", 0.5)

        city_key = self._identify_city(question)
        if not city_key:
            return self._hold("Cannot identify city")

        # Get historical data
        historical = self.client.get_historical(city_key, days_back=30)
        if not historical or len(historical) < 14:
            return self._hold("Insufficient historical data")

        # Detect seasonal trends
        recent_temps = [d.get("temp_mean_c", 0) for d in historical[-7:] if d.get("temp_mean_c") is not None]
        older_temps = [d.get("temp_mean_c", 0) for d in historical[:14] if d.get("temp_mean_c") is not None]

        if not recent_temps or not older_temps:
            return self._hold("No temperature data")

        import statistics
        recent_mean = statistics.mean(recent_temps)
        older_mean = statistics.mean(older_temps)
        trend = recent_mean - older_mean  # Positive = warming, negative = cooling

        # Parse market question
        event_type, threshold = self.model._parse_market_question(question)
        if not event_type or threshold is None:
            return self._hold("Cannot parse market question")

        # Seasonal adjustment to our probability
        edge_result = self.model.calculate_edge(
            city_key=city_key,
            market_question=question,
            market_price_yes=price_yes,
        )

        if not edge_result:
            return self._hold("Cannot calculate edge")

        # Adjust probability based on seasonal trend
        our_prob = edge_result["our_probability"]

        if event_type == "temp_above" and trend > 1.5:
            # Warming trend + above-threshold market = boost YES
            our_prob = min(0.95, our_prob + 0.05)
        elif event_type == "temp_below" and trend < -1.5:
            # Cooling trend + below-threshold market = boost YES
            our_prob = min(0.95, our_prob + 0.05)

        edge = (our_prob - price_yes) * 100
        confidence = edge_result["confidence"]

        if abs(edge) < 3:
            return self._hold("Seasonal edge too small")

        direction = "BUY_YES" if edge > 0 else "BUY_NO"
        kelly = min(0.15, edge_result.get("kelly_fraction", 0))

        return {
            "direction": direction,
            "confidence_percent": round(confidence * 100, 2),
            "fair_value": round(our_prob, 4),
            "edge": round(edge, 2),
            "edge_percent": round(edge, 2),
            "strategy": self.name,
            "kelly_fraction": round(kelly, 4),
            "seasonal_trend": round(trend, 1),
        }

    def _identify_city(self, question: str) -> Optional[str]:
        q = question.lower()
        for key, city in WEATHER_CITIES.items():
            if city["name"].lower() in q:
                return key
        return None

    def _hold(self, reason: str) -> dict:
        return {
            "direction": "HOLD",
            "confidence_percent": 0,
            "fair_value": 0.5,
            "edge": 0,
            "edge_percent": 0,
            "strategy": self.name,
            "reason": reason,
        }


class RapidChangeMomentumStrategy(BaseStrategy):
    """
    Trade sudden weather shifts that haven't been priced in yet.
    
    Detects rapid temperature/pressure changes and trades the momentum
    before the market adjusts. Similar to oracle delay exploit but for weather.
    """

    def __init__(self, weather_client: WeatherAPIClient):
        self.name = "RAPID_CHANGE_MOMENTUM"
        self.client = weather_client
        self.model = WeatherPredictionModel(weather_client)
        self._last_readings: Dict[str, Dict] = {}

    def analyze(self, market_data: dict) -> dict:
        question = market_data.get("market", "")
        price_yes = market_data.get("price_yes", 0.5)

        city_key = self._identify_city(question)
        if not city_key:
            return self._hold("Cannot identify city")

        current = self.client.get_current_weather(city_key)
        if not current:
            return self._hold("Cannot get current weather")

        # Compare with last reading
        last = self._last_readings.get(city_key)
        self._last_readings[city_key] = {
            "temp": current.get("temperature_c", 0),
            "pressure": current.get("pressure_hpa", 1013),
            "wind": current.get("wind_speed_kmh", 0),
            "timestamp": time.time(),
        }

        if not last:
            return self._hold("First reading — need baseline")

        time_diff = time.time() - last.get("timestamp", 0)
        if time_diff < 60:  # Too soon
            return self._hold("Reading too recent")

        # Calculate changes
        temp_change = current.get("temperature_c", 0) - last.get("temp", 0)
        pressure_change = current.get("pressure_hpa", 1013) - last.get("pressure", 1013)
        wind_change = current.get("wind_speed_kmh", 0) - last.get("wind", 0)

        # Detect rapid changes (per hour rate)
        hours_elapsed = max(time_diff / 3600, 0.1)
        temp_rate = temp_change / hours_elapsed
        pressure_rate = pressure_change / hours_elapsed

        # Significant changes: >2°C/hour or >3hPa/hour
        is_rapid = abs(temp_rate) > 2 or abs(pressure_rate) > 3

        if not is_rapid:
            return self._hold("No rapid change detected")

        # Calculate edge based on momentum
        edge_result = self.model.calculate_edge(
            city_key=city_key,
            market_question=question,
            market_price_yes=price_yes,
        )

        if not edge_result:
            return self._hold("Cannot calculate edge")

        # Boost our probability in the direction of momentum
        our_prob = edge_result["our_probability"]
        event_type, threshold = self.model._parse_market_question(question)

        if event_type == "temp_above" and temp_rate > 2:
            our_prob = min(0.95, our_prob + 0.08)
        elif event_type == "temp_below" and temp_rate < -2:
            our_prob = min(0.95, our_prob + 0.08)

        edge = (our_prob - price_yes) * 100
        confidence = min(0.85, edge_result["confidence"] + 0.05)

        if abs(edge) < 3:
            return self._hold("Momentum edge too small")

        direction = "BUY_YES" if edge > 0 else "BUY_NO"
        kelly = min(0.20, edge_result.get("kelly_fraction", 0))

        return {
            "direction": direction,
            "confidence_percent": round(confidence * 100, 2),
            "fair_value": round(our_prob, 4),
            "edge": round(edge, 2),
            "edge_percent": round(edge, 2),
            "strategy": self.name,
            "kelly_fraction": round(kelly, 4),
            "temp_rate_per_hour": round(temp_rate, 2),
            "pressure_rate_per_hour": round(pressure_rate, 2),
        }

    def _identify_city(self, question: str) -> Optional[str]:
        q = question.lower()
        for key, city in WEATHER_CITIES.items():
            if city["name"].lower() in q:
                return key
        return None

    def _hold(self, reason: str) -> dict:
        return {
            "direction": "HOLD",
            "confidence_percent": 0,
            "fair_value": 0.5,
            "edge": 0,
            "edge_percent": 0,
            "strategy": self.name,
            "reason": reason,
        }
