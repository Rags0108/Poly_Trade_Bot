"""
Weather Prediction Model — Statistical + Ensemble Forecasting

Multi-model ensemble approach for weather prediction:
  1. Climatological Model — Historical averages + seasonal patterns
  2. Persistence Model — Recent conditions projected forward
  3. Trend Model — Extrapolate recent trends (regression-based)
  4. Ensemble Model — Weighted combination of all models
  5. LLM-Enhanced Model — Use LLM for qualitative weather analysis

Outputs:
  - Temperature probability distributions
  - Rain/snow probability estimates
  - Confidence scores for each prediction
  - Edge calculations vs market prices
"""

import math
import statistics
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from weather_prediction.weather_api import WeatherAPIClient


class WeatherPredictionModel:
    """Ensemble weather prediction model for trading."""

    # Weights for ensemble combination (tuned for accuracy)
    MODEL_WEIGHTS = {
        "climatological": 0.25,
        "persistence": 0.20,
        "trend": 0.30,
        "forecast_api": 0.25,
    }

    def __init__(self, weather_client: WeatherAPIClient):
        self.client = weather_client
        self._prediction_cache: Dict[str, Tuple[float, dict]] = {}
        self._historical_accuracy: Dict[str, List[float]] = {}

    # ═══════════════════════════════════════════════════════════════
    # MAIN PREDICTION API
    # ═══════════════════════════════════════════════════════════════

    def predict_temperature(self, city_key: str, hours_ahead: int = 24) -> Optional[Dict]:
        """
        Predict temperature N hours from now.

        Returns:
            {
                "predicted_temp_c": float,
                "confidence": float (0-1),
                "temp_range_low": float,
                "temp_range_high": float,
                "probability_above_threshold": dict,
                "model_outputs": dict,
                "city": str,
            }
        """
        current = self.client.get_current_weather(city_key)
        forecast = self.client.get_forecast(city_key, hours=max(48, hours_ahead + 12))
        historical = self.client.get_historical(city_key, days_back=30)

        if not current:
            return None

        # Run individual models
        models = {}

        # 1. Climatological model
        if historical:
            models["climatological"] = self._climatological_prediction(
                historical, hours_ahead
            )

        # 2. Persistence model (current temp + diurnal cycle)
        models["persistence"] = self._persistence_prediction(
            current, hours_ahead
        )

        # 3. Trend model (extrapolate recent changes)
        if forecast:
            models["trend"] = self._trend_prediction(
                current, forecast, hours_ahead
            )

        # 4. API forecast model (use raw forecast as a model input)
        if forecast and hours_ahead < len(forecast):
            models["forecast_api"] = self._api_forecast_prediction(
                forecast, hours_ahead
            )

        if not models:
            return None

        # Ensemble combination
        ensemble = self._ensemble_predict(models)

        # Calculate confidence based on model agreement
        all_temps = [m["predicted_temp"] for m in models.values()]
        spread = max(all_temps) - min(all_temps) if len(all_temps) > 1 else 5.0
        # More agreement = higher confidence
        # 0°C spread = 0.95 confidence, 10°C spread = 0.50 confidence
        confidence = max(0.30, min(0.95, 1.0 - (spread / 20.0)))

        # Uncertainty range (±σ)
        std_dev = statistics.stdev(all_temps) if len(all_temps) > 1 else 3.0
        temp_range = max(1.5, std_dev * 1.5)

        return {
            "predicted_temp_c": round(ensemble, 2),
            "confidence": round(confidence, 3),
            "temp_range_low": round(ensemble - temp_range, 1),
            "temp_range_high": round(ensemble + temp_range, 1),
            "std_dev": round(std_dev, 2),
            "model_outputs": {k: round(v["predicted_temp"], 2) for k, v in models.items()},
            "city": current.get("city", city_key),
            "hours_ahead": hours_ahead,
        }

    def predict_precipitation(self, city_key: str, hours_ahead: int = 24) -> Optional[Dict]:
        """
        Predict probability of precipitation in the next N hours.

        Returns:
            {
                "rain_probability": float (0-1),
                "total_precip_mm": float,
                "confidence": float (0-1),
                "model_outputs": dict,
            }
        """
        current = self.client.get_current_weather(city_key)
        forecast = self.client.get_forecast(city_key, hours=max(48, hours_ahead + 12))
        historical = self.client.get_historical(city_key, days_back=30)

        if not current:
            return None

        probs = []

        # From API forecast
        if forecast:
            relevant_hours = forecast[:hours_ahead]
            if relevant_hours:
                api_rain_probs = [
                    h.get("precip_probability_pct", 0) / 100
                    for h in relevant_hours
                ]
                # Probability of ANY rain in window
                prob_no_rain = 1.0
                for p in api_rain_probs:
                    prob_no_rain *= (1 - p)
                api_prob = 1 - prob_no_rain
                probs.append(("forecast_api", api_prob, 0.40))

                total_precip = sum(h.get("precipitation_mm", 0) for h in relevant_hours)
            else:
                total_precip = 0
        else:
            total_precip = 0

        # From current conditions
        current_humidity = current.get("humidity_pct", 0)
        current_pressure = current.get("pressure_hpa", 1013)
        current_precip = current.get("precipitation_mm", 0)

        # Humidity-based probability
        humidity_prob = max(0, min(1, (current_humidity - 50) / 50))
        probs.append(("humidity", humidity_prob, 0.15))

        # Pressure-based probability (low pressure = more rain)
        pressure_prob = max(0, min(1, (1020 - current_pressure) / 30))
        probs.append(("pressure", pressure_prob, 0.15))

        # Current rain persistence
        if current_precip > 0:
            persistence_prob = 0.7  # If raining now, likely continues
        else:
            persistence_prob = 0.2
        probs.append(("persistence", persistence_prob, 0.15))

        # Historical base rate
        if historical:
            rainy_days = sum(1 for d in historical if d.get("precipitation_mm", 0) > 0.5)
            hist_prob = rainy_days / max(1, len(historical))
            probs.append(("historical", hist_prob, 0.15))

        # Weighted ensemble
        total_weight = sum(w for _, _, w in probs)
        rain_probability = sum(p * w for _, p, w in probs) / total_weight if total_weight > 0 else 0.5

        # Confidence based on source agreement
        all_probs_vals = [p for _, p, _ in probs]
        if len(all_probs_vals) > 1:
            spread = max(all_probs_vals) - min(all_probs_vals)
            confidence = max(0.35, min(0.90, 1.0 - spread))
        else:
            confidence = 0.40

        return {
            "rain_probability": round(rain_probability, 3),
            "total_precip_mm": round(total_precip, 1),
            "confidence": round(confidence, 3),
            "model_outputs": {name: round(p, 3) for name, p, _ in probs},
            "city": current.get("city", city_key),
            "hours_ahead": hours_ahead,
        }

    def predict_extreme_event(self, city_key: str, event_type: str, threshold: float) -> Optional[Dict]:
        """
        Predict probability of an extreme weather event.

        event_type:
            "temp_above" — temperature above threshold (°C)
            "temp_below" — temperature below threshold (°C)
            "rain_above" — precipitation above threshold (mm)
            "wind_above" — wind speed above threshold (km/h)

        Returns:
            {
                "probability": float (0-1),
                "confidence": float (0-1),
                "current_value": float,
                "threshold": float,
                "distance_to_threshold": float,
            }
        """
        current = self.client.get_current_weather(city_key)
        forecast = self.client.get_forecast(city_key, hours=48)
        historical = self.client.get_historical(city_key, days_back=90)

        if not current:
            return None

        # Determine which metric we're tracking
        metric_map = {
            "temp_above": ("temperature_c", "temp_max_c"),
            "temp_below": ("temperature_c", "temp_min_c"),
            "rain_above": ("precipitation_mm", "precipitation_mm"),
            "wind_above": ("wind_speed_kmh", "wind_max_kmh"),
        }

        if event_type not in metric_map:
            return None

        current_key, hist_key = metric_map[event_type]
        current_value = current.get(current_key, 0)

        prob_sources = []

        # From forecast
        if forecast:
            exceed_count = 0
            for h in forecast[:48]:
                val = h.get(current_key.replace("precipitation_mm", "precipitation_mm")
                           .replace("wind_speed_kmh", "wind_speed_kmh"), 0)
                if val is None:
                    val = 0
                if event_type.endswith("above") and val > threshold:
                    exceed_count += 1
                elif event_type.endswith("below") and val < threshold:
                    exceed_count += 1
            forecast_prob = exceed_count / max(1, len(forecast[:48]))
            prob_sources.append(("forecast", forecast_prob, 0.45))

        # From historical
        if historical:
            hist_exceed = 0
            for d in historical:
                val = d.get(hist_key, 0)
                if val is None:
                    val = 0
                if event_type.endswith("above") and val > threshold:
                    hist_exceed += 1
                elif event_type.endswith("below") and val < threshold:
                    hist_exceed += 1
            hist_prob = hist_exceed / max(1, len(historical))
            prob_sources.append(("historical", hist_prob, 0.25))

        # From current trajectory
        distance = abs(current_value - threshold)
        if event_type.endswith("above"):
            trajectory_prob = max(0, min(1, 1 - distance / max(threshold * 0.3, 5)))
            if current_value > threshold:
                trajectory_prob = min(1.0, 0.7 + trajectory_prob * 0.3)
        else:
            trajectory_prob = max(0, min(1, 1 - distance / max(abs(threshold) * 0.3 + 5, 5)))
            if current_value < threshold:
                trajectory_prob = min(1.0, 0.7 + trajectory_prob * 0.3)
        prob_sources.append(("trajectory", trajectory_prob, 0.30))

        # Ensemble
        total_w = sum(w for _, _, w in prob_sources)
        probability = sum(p * w for _, p, w in prob_sources) / total_w if total_w > 0 else 0.5

        # Confidence
        all_vals = [p for _, p, _ in prob_sources]
        spread = max(all_vals) - min(all_vals) if len(all_vals) > 1 else 0.3
        confidence = max(0.30, min(0.90, 1.0 - spread * 0.8))

        return {
            "probability": round(probability, 3),
            "confidence": round(confidence, 3),
            "current_value": round(current_value, 2),
            "threshold": threshold,
            "distance_to_threshold": round(current_value - threshold, 2),
            "event_type": event_type,
            "model_outputs": {name: round(p, 3) for name, p, _ in prob_sources},
            "city": current.get("city", city_key),
        }

    # ═══════════════════════════════════════════════════════════════
    # INDIVIDUAL MODELS
    # ═══════════════════════════════════════════════════════════════

    def _climatological_prediction(self, historical: List[Dict], hours_ahead: int) -> Dict:
        """Predict based on historical averages for this time of year."""
        if not historical:
            return {"predicted_temp": 20.0, "confidence": 0.3}

        temps = [
            d.get("temp_mean_c", 0) for d in historical
            if d.get("temp_mean_c") is not None
        ]

        if not temps:
            return {"predicted_temp": 20.0, "confidence": 0.3}

        mean_temp = statistics.mean(temps)
        std_temp = statistics.stdev(temps) if len(temps) > 1 else 5.0

        # Simple seasonal adjustment based on time of day
        hour = (datetime.now(timezone.utc).hour + hours_ahead) % 24
        # Diurnal cycle: coolest at 5am, warmest at 3pm
        diurnal_offset = -3 * math.cos(2 * math.pi * (hour - 15) / 24)

        predicted = mean_temp + diurnal_offset

        return {
            "predicted_temp": predicted,
            "std_dev": std_temp,
            "confidence": max(0.3, 0.7 - std_temp / 20),
        }

    def _persistence_prediction(self, current: Dict, hours_ahead: int) -> Dict:
        """Predict based on current conditions + diurnal cycle."""
        current_temp = current.get("temperature_c", 20)

        hour_now = datetime.now(timezone.utc).hour
        hour_target = (hour_now + hours_ahead) % 24

        # Diurnal amplitude (typically 5-10°C depending on location/season)
        amplitude = 5.0

        # Current position in diurnal cycle
        current_diurnal = amplitude * math.cos(2 * math.pi * (hour_now - 15) / 24)
        target_diurnal = amplitude * math.cos(2 * math.pi * (hour_target - 15) / 24)

        # Predicted = current - current_offset + target_offset
        predicted = current_temp - current_diurnal + target_diurnal

        # Confidence decreases with hours_ahead
        confidence = max(0.3, 0.85 - hours_ahead * 0.02)

        return {
            "predicted_temp": predicted,
            "confidence": confidence,
        }

    def _trend_prediction(self, current: Dict, forecast: List[Dict], hours_ahead: int) -> Dict:
        """Predict by extrapolating recent temperature trend."""
        temps = [h.get("temperature_c", 0) for h in forecast[:12] if h.get("temperature_c") is not None]

        if len(temps) < 3:
            return self._persistence_prediction(current, hours_ahead)

        # Simple linear regression on recent temps
        n = len(temps)
        x = list(range(n))
        mean_x = sum(x) / n
        mean_y = sum(temps) / n

        numerator = sum((x[i] - mean_x) * (temps[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

        if denominator == 0:
            return self._persistence_prediction(current, hours_ahead)

        slope = numerator / denominator
        intercept = mean_y - slope * mean_x

        # Extrapolate
        predicted = intercept + slope * (n - 1 + hours_ahead)

        # Dampen extreme predictions
        current_temp = current.get("temperature_c", 20)
        max_change = 15  # Max 15°C change
        predicted = max(current_temp - max_change, min(current_temp + max_change, predicted))

        # Confidence decreases with extrapolation distance
        confidence = max(0.25, 0.80 - hours_ahead * 0.03)

        return {
            "predicted_temp": predicted,
            "confidence": confidence,
        }

    def _api_forecast_prediction(self, forecast: List[Dict], hours_ahead: int) -> Dict:
        """Use the API forecast directly as a model output."""
        if hours_ahead < len(forecast):
            temp = forecast[hours_ahead].get("temperature_c", 20)
        else:
            temp = forecast[-1].get("temperature_c", 20)

        # API forecasts are generally accurate short-term, less so long-term
        confidence = max(0.40, 0.92 - hours_ahead * 0.015)

        return {
            "predicted_temp": temp,
            "confidence": confidence,
        }

    def _ensemble_predict(self, models: Dict[str, Dict]) -> float:
        """Weighted ensemble of all model predictions."""
        total_weight = 0
        weighted_sum = 0

        for name, output in models.items():
            base_weight = self.MODEL_WEIGHTS.get(name, 0.15)
            model_confidence = output.get("confidence", 0.5)

            # Weight = base_weight × model_confidence
            weight = base_weight * model_confidence
            weighted_sum += output["predicted_temp"] * weight
            total_weight += weight

        if total_weight == 0:
            return 20.0

        return weighted_sum / total_weight

    # ═══════════════════════════════════════════════════════════════
    # MARKET EDGE CALCULATION
    # ═══════════════════════════════════════════════════════════════

    def calculate_edge(
        self,
        city_key: str,
        market_question: str,
        market_price_yes: float,
        threshold: float = None,
        event_type: str = None,
    ) -> Optional[Dict]:
        """
        Calculate trading edge for a weather market.

        Parses the market question to determine what's being predicted,
        then computes our probability vs market probability (price).

        Returns:
            {
                "our_probability": float (0-1),
                "market_probability": float (market_price_yes),
                "edge": float (our_prob - market_prob),
                "edge_percent": float,
                "confidence": float,
                "direction": "BUY_YES" / "BUY_NO" / "HOLD",
                "kelly_fraction": float,
            }
        """
        # Determine prediction type from market question or explicit params
        if not event_type:
            event_type, threshold = self._parse_market_question(market_question)

        if not event_type or threshold is None:
            return None

        # Get our prediction
        if event_type.startswith("temp_"):
            prediction = self.predict_extreme_event(city_key, event_type, threshold)
        elif event_type.startswith("rain_"):
            prediction = self.predict_precipitation(city_key, hours_ahead=24)
        elif event_type.startswith("wind_"):
            prediction = self.predict_extreme_event(city_key, event_type, threshold)
        else:
            prediction = self.predict_extreme_event(city_key, event_type, threshold)

        if not prediction:
            return None

        our_prob = prediction.get("probability", prediction.get("rain_probability", 0.5))
        confidence = prediction.get("confidence", 0.5)

        # Edge calculation
        edge = our_prob - market_price_yes
        edge_pct = round(edge * 100, 2)

        # Direction
        if abs(edge) < 0.02:  # Less than 2% edge — not worth trading
            direction = "HOLD"
        elif edge > 0:
            direction = "BUY_YES"
        else:
            direction = "BUY_NO"

        # Kelly criterion
        if direction == "BUY_YES":
            p = our_prob
            q = 1 - p
            b = (1 / market_price_yes) - 1  # Odds offered
            kelly = (b * p - q) / b if b > 0 else 0
        elif direction == "BUY_NO":
            p = 1 - our_prob
            q = 1 - p
            b = (1 / (1 - market_price_yes)) - 1
            kelly = (b * p - q) / b if b > 0 else 0
        else:
            kelly = 0

        kelly = max(0, min(0.25, kelly))  # Cap at 25% Kelly

        return {
            "our_probability": round(our_prob, 4),
            "market_probability": market_price_yes,
            "edge": round(edge, 4),
            "edge_percent": edge_pct,
            "confidence": round(confidence, 3),
            "direction": direction,
            "kelly_fraction": round(kelly, 4),
            "prediction": prediction,
        }

    def _parse_market_question(self, question: str) -> Tuple[Optional[str], Optional[float]]:
        """
        Parse a Polymarket weather question to extract event type and threshold.

        Examples:
            "Will NYC temperature exceed 100°F on July 4?" → ("temp_above", 37.8)
            "Will it rain in London tomorrow?" → ("rain_above", 0.1)
            "Will wind speeds in Miami exceed 75 mph?" → ("wind_above", 120.7)
        """
        q = question.lower()

        # Temperature questions
        if any(w in q for w in ["temperature", "temp", "hot", "cold", "heat", "warm", "degrees"]):
            # Extract threshold
            threshold = self._extract_number(q)
            if threshold is not None:
                # Convert F to C if seems like Fahrenheit
                if "°f" in q or "fahrenheit" in q or threshold > 60:
                    threshold = (threshold - 32) * 5 / 9

                if any(w in q for w in ["above", "exceed", "over", "higher", "hot", "heat"]):
                    return ("temp_above", threshold)
                elif any(w in q for w in ["below", "under", "lower", "cold", "freeze"]):
                    return ("temp_below", threshold)
                else:
                    return ("temp_above", threshold)

        # Rain questions
        if any(w in q for w in ["rain", "precipitation", "snow", "rainfall"]):
            threshold = self._extract_number(q)
            if threshold is None:
                threshold = 0.1  # Any rain
            return ("rain_above", threshold)

        # Wind questions
        if any(w in q for w in ["wind", "hurricane", "storm", "gust"]):
            threshold = self._extract_number(q)
            if threshold is not None:
                # Convert mph to km/h if needed
                if "mph" in q:
                    threshold *= 1.60934
                return ("wind_above", threshold)

        return (None, None)

    def _extract_number(self, text: str) -> Optional[float]:
        """Extract first number from text."""
        import re
        match = re.search(r'[-+]?\d*\.?\d+', text)
        if match:
            return float(match.group())
        return None
