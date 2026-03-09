"""
Weather API Client — Multi-Source Weather Data with Fallback Chain

Sources (all FREE tier):
  1. Open-Meteo (PRIMARY) — No API key required, 10,000 req/day
  2. OpenWeatherMap (FALLBACK) — Free tier 1,000 req/day
  3. WeatherAPI.com (FALLBACK 2) — Free tier 1,000,000 req/month

Returns normalized weather data for trading decisions:
  - Current conditions (temp, humidity, wind, pressure, precipitation)
  - Hourly forecasts (next 48h)
  - Historical data for model training
  - Extreme weather alerts
"""

import time
import requests
import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

# Major cities with active weather markets (Polymarket typically has these)
WEATHER_CITIES = {
    "new_york": {"lat": 40.7128, "lon": -74.0060, "name": "New York"},
    "london": {"lat": 51.5074, "lon": -0.1278, "name": "London"},
    "tokyo": {"lat": 35.6762, "lon": 139.6503, "name": "Tokyo"},
    "los_angeles": {"lat": 34.0522, "lon": -118.2437, "name": "Los Angeles"},
    "chicago": {"lat": 41.8781, "lon": -87.6298, "name": "Chicago"},
    "miami": {"lat": 25.7617, "lon": -80.1918, "name": "Miami"},
    "dallas": {"lat": 32.7767, "lon": -96.7970, "name": "Dallas"},
    "seattle": {"lat": 47.6062, "lon": -122.3321, "name": "Seattle"},
    "phoenix": {"lat": 33.4484, "lon": -112.0740, "name": "Phoenix"},
    "denver": {"lat": 39.7392, "lon": -104.9903, "name": "Denver"},
    "atlanta": {"lat": 33.7490, "lon": -84.3880, "name": "Atlanta"},
    "boston": {"lat": 42.3601, "lon": -71.0589, "name": "Boston"},
    "san_francisco": {"lat": 37.7749, "lon": -122.4194, "name": "San Francisco"},
    "washington_dc": {"lat": 38.9072, "lon": -77.0369, "name": "Washington DC"},
    "houston": {"lat": 29.7604, "lon": -95.3698, "name": "Houston"},
    "paris": {"lat": 48.8566, "lon": 2.3522, "name": "Paris"},
    "sydney": {"lat": -33.8688, "lon": 151.2093, "name": "Sydney"},
    "mumbai": {"lat": 19.0760, "lon": 72.8777, "name": "Mumbai"},
    "dubai": {"lat": 25.2048, "lon": 55.2708, "name": "Dubai"},
    "singapore": {"lat": 1.3521, "lon": 103.8198, "name": "Singapore"},
}

# Cache for API responses
_cache: Dict[str, Tuple[float, dict]] = {}
CACHE_TTL = 300  # 5 minutes


class WeatherAPIClient:
    """Multi-source weather data client with automatic fallback."""

    def __init__(self, openweathermap_key: str = "", weatherapi_key: str = ""):
        self.owm_key = openweathermap_key
        self.wapi_key = weatherapi_key
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "WeatherTradingBot/1.0",
            "Accept": "application/json",
        })
        self._request_count = 0
        self._last_reset = time.time()

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════════

    def get_current_weather(self, city_key: str) -> Optional[Dict]:
        """Get current weather for a city. Uses cache + fallback chain."""
        cache_key = f"current_{city_key}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        city = WEATHER_CITIES.get(city_key)
        if not city:
            return None

        # Fallback chain: Open-Meteo → OpenWeatherMap → WeatherAPI
        result = (
            self._fetch_open_meteo_current(city)
            or self._fetch_owm_current(city)
            or self._fetch_weatherapi_current(city)
        )

        if result:
            result["city"] = city["name"]
            result["city_key"] = city_key
            result["fetched_at"] = datetime.now(timezone.utc).isoformat()
            self._set_cached(cache_key, result)

        return result

    def get_forecast(self, city_key: str, hours: int = 48) -> Optional[List[Dict]]:
        """Get hourly forecast for a city. Returns list of hourly data."""
        cache_key = f"forecast_{city_key}_{hours}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        city = WEATHER_CITIES.get(city_key)
        if not city:
            return None

        result = (
            self._fetch_open_meteo_forecast(city, hours)
            or self._fetch_owm_forecast(city, hours)
            or self._fetch_weatherapi_forecast(city, hours)
        )

        if result:
            self._set_cached(cache_key, result)

        return result

    def get_historical(self, city_key: str, days_back: int = 7) -> Optional[List[Dict]]:
        """Get historical daily weather data. Open-Meteo archive is free."""
        cache_key = f"hist_{city_key}_{days_back}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        city = WEATHER_CITIES.get(city_key)
        if not city:
            return None

        result = self._fetch_open_meteo_historical(city, days_back)
        if result:
            self._set_cached(cache_key, result)

        return result

    def get_all_cities_current(self) -> Dict[str, Dict]:
        """Get current weather for all tracked cities."""
        results = {}
        for city_key in WEATHER_CITIES:
            data = self.get_current_weather(city_key)
            if data:
                results[city_key] = data
        return results

    def detect_extreme_weather(self, city_key: str) -> List[Dict]:
        """Detect extreme weather conditions that create trading opportunities."""
        current = self.get_current_weather(city_key)
        forecast = self.get_forecast(city_key, hours=24)

        if not current:
            return []

        alerts = []
        temp = current.get("temperature_c", 0)
        wind = current.get("wind_speed_kmh", 0)
        precip = current.get("precipitation_mm", 0)
        humidity = current.get("humidity_pct", 0)

        # Extreme heat
        if temp >= 40:
            alerts.append({
                "type": "EXTREME_HEAT",
                "severity": "HIGH",
                "value": temp,
                "message": f"Extreme heat: {temp}°C",
                "trading_signal": "BUY_YES on high temp markets"
            })
        elif temp >= 35:
            alerts.append({
                "type": "HEAT_WAVE",
                "severity": "MEDIUM",
                "value": temp,
                "message": f"Heat wave: {temp}°C",
                "trading_signal": "BUY_YES on above-average temp"
            })

        # Extreme cold
        if temp <= -20:
            alerts.append({
                "type": "EXTREME_COLD",
                "severity": "HIGH",
                "value": temp,
                "message": f"Extreme cold: {temp}°C",
                "trading_signal": "BUY_YES on record cold markets"
            })

        # High wind
        if wind >= 80:
            alerts.append({
                "type": "HURRICANE_FORCE",
                "severity": "CRITICAL",
                "value": wind,
                "message": f"Hurricane-force winds: {wind} km/h",
                "trading_signal": "BUY_YES on extreme weather events"
            })
        elif wind >= 50:
            alerts.append({
                "type": "HIGH_WIND",
                "severity": "HIGH",
                "value": wind,
                "message": f"High wind: {wind} km/h",
                "trading_signal": "Increased weather volatility"
            })

        # Heavy precipitation
        if precip >= 50:
            alerts.append({
                "type": "HEAVY_RAIN",
                "severity": "HIGH",
                "value": precip,
                "message": f"Heavy precipitation: {precip}mm",
                "trading_signal": "BUY_YES on rainfall threshold markets"
            })

        # Forecast-based alerts
        if forecast:
            max_forecast_temp = max(h.get("temperature_c", 0) for h in forecast[:24])
            min_forecast_temp = min(h.get("temperature_c", 0) for h in forecast[:24])
            total_precip_24h = sum(h.get("precipitation_mm", 0) for h in forecast[:24])

            if max_forecast_temp - temp > 10:
                alerts.append({
                    "type": "RAPID_WARMING",
                    "severity": "MEDIUM",
                    "value": max_forecast_temp - temp,
                    "message": f"Rapid warming expected: +{max_forecast_temp - temp:.1f}°C in 24h",
                    "trading_signal": "Temperature overshoot opportunity"
                })

            if total_precip_24h > 25:
                alerts.append({
                    "type": "RAIN_FORECAST",
                    "severity": "MEDIUM",
                    "value": total_precip_24h,
                    "message": f"Heavy rain forecast: {total_precip_24h:.1f}mm in 24h",
                    "trading_signal": "BUY_YES on rain probability markets"
                })

        return alerts

    # ═══════════════════════════════════════════════════════════════
    # OPEN-METEO (PRIMARY — FREE, NO KEY NEEDED)
    # ═══════════════════════════════════════════════════════════════

    def _fetch_open_meteo_current(self, city: dict) -> Optional[Dict]:
        """Open-Meteo current weather. Free, no API key."""
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": city["lat"],
                "longitude": city["lon"],
                "current": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "precipitation,rain,snowfall,weather_code,cloud_cover,"
                    "pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,"
                    "wind_gusts_10m"
                ),
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                "timezone": "auto",
            }
            r = self._session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            current = data.get("current", {})

            return {
                "source": "open_meteo",
                "temperature_c": current.get("temperature_2m", 0),
                "feels_like_c": current.get("apparent_temperature", 0),
                "humidity_pct": current.get("relative_humidity_2m", 0),
                "precipitation_mm": current.get("precipitation", 0),
                "rain_mm": current.get("rain", 0),
                "snowfall_mm": current.get("snowfall", 0),
                "cloud_cover_pct": current.get("cloud_cover", 0),
                "pressure_hpa": current.get("pressure_msl", 0),
                "wind_speed_kmh": current.get("wind_speed_10m", 0),
                "wind_direction_deg": current.get("wind_direction_10m", 0),
                "wind_gusts_kmh": current.get("wind_gusts_10m", 0),
                "weather_code": current.get("weather_code", 0),
            }
        except Exception as e:
            print(f"⚠️ Open-Meteo current failed: {e}")
            return None

    def _fetch_open_meteo_forecast(self, city: dict, hours: int) -> Optional[List[Dict]]:
        """Open-Meteo hourly forecast."""
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": city["lat"],
                "longitude": city["lon"],
                "hourly": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "precipitation_probability,precipitation,rain,snowfall,"
                    "weather_code,cloud_cover,pressure_msl,wind_speed_10m,"
                    "wind_direction_10m,wind_gusts_10m"
                ),
                "forecast_hours": min(hours, 168),
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "timezone": "auto",
            }
            r = self._session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])

            result = []
            for i, t in enumerate(times[:hours]):
                result.append({
                    "time": t,
                    "temperature_c": hourly.get("temperature_2m", [0])[i] if i < len(hourly.get("temperature_2m", [])) else 0,
                    "feels_like_c": hourly.get("apparent_temperature", [0])[i] if i < len(hourly.get("apparent_temperature", [])) else 0,
                    "humidity_pct": hourly.get("relative_humidity_2m", [0])[i] if i < len(hourly.get("relative_humidity_2m", [])) else 0,
                    "precip_probability_pct": hourly.get("precipitation_probability", [0])[i] if i < len(hourly.get("precipitation_probability", [])) else 0,
                    "precipitation_mm": hourly.get("precipitation", [0])[i] if i < len(hourly.get("precipitation", [])) else 0,
                    "rain_mm": hourly.get("rain", [0])[i] if i < len(hourly.get("rain", [])) else 0,
                    "snowfall_mm": hourly.get("snowfall", [0])[i] if i < len(hourly.get("snowfall", [])) else 0,
                    "cloud_cover_pct": hourly.get("cloud_cover", [0])[i] if i < len(hourly.get("cloud_cover", [])) else 0,
                    "pressure_hpa": hourly.get("pressure_msl", [0])[i] if i < len(hourly.get("pressure_msl", [])) else 0,
                    "wind_speed_kmh": hourly.get("wind_speed_10m", [0])[i] if i < len(hourly.get("wind_speed_10m", [])) else 0,
                    "wind_gusts_kmh": hourly.get("wind_gusts_10m", [0])[i] if i < len(hourly.get("wind_gusts_10m", [])) else 0,
                    "weather_code": hourly.get("weather_code", [0])[i] if i < len(hourly.get("weather_code", [])) else 0,
                })
            return result
        except Exception as e:
            print(f"⚠️ Open-Meteo forecast failed: {e}")
            return None

    def _fetch_open_meteo_historical(self, city: dict, days_back: int) -> Optional[List[Dict]]:
        """Open-Meteo historical archive. Free & unlimited."""
        try:
            end_date = datetime.now(timezone.utc).date()
            start_date = end_date - timedelta(days=days_back)

            url = "https://archive-api.open-meteo.com/v1/archive"
            params = {
                "latitude": city["lat"],
                "longitude": city["lon"],
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "daily": (
                    "temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
                    "precipitation_sum,rain_sum,snowfall_sum,wind_speed_10m_max,"
                    "wind_gusts_10m_max,precipitation_hours"
                ),
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "timezone": "auto",
            }
            r = self._session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            daily = data.get("daily", {})
            times = daily.get("time", [])

            result = []
            for i, t in enumerate(times):
                result.append({
                    "date": t,
                    "temp_max_c": daily.get("temperature_2m_max", [0])[i] if i < len(daily.get("temperature_2m_max", [])) else 0,
                    "temp_min_c": daily.get("temperature_2m_min", [0])[i] if i < len(daily.get("temperature_2m_min", [])) else 0,
                    "temp_mean_c": daily.get("temperature_2m_mean", [0])[i] if i < len(daily.get("temperature_2m_mean", [])) else 0,
                    "precipitation_mm": daily.get("precipitation_sum", [0])[i] if i < len(daily.get("precipitation_sum", [])) else 0,
                    "rain_mm": daily.get("rain_sum", [0])[i] if i < len(daily.get("rain_sum", [])) else 0,
                    "snowfall_mm": daily.get("snowfall_sum", [0])[i] if i < len(daily.get("snowfall_sum", [])) else 0,
                    "wind_max_kmh": daily.get("wind_speed_10m_max", [0])[i] if i < len(daily.get("wind_speed_10m_max", [])) else 0,
                    "wind_gust_max_kmh": daily.get("wind_gusts_10m_max", [0])[i] if i < len(daily.get("wind_gusts_10m_max", [])) else 0,
                    "precip_hours": daily.get("precipitation_hours", [0])[i] if i < len(daily.get("precipitation_hours", [])) else 0,
                })
            return result
        except Exception as e:
            print(f"⚠️ Open-Meteo historical failed: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # OPENWEATHERMAP (FALLBACK 1)
    # ═══════════════════════════════════════════════════════════════

    def _fetch_owm_current(self, city: dict) -> Optional[Dict]:
        """OpenWeatherMap current weather. Requires API key."""
        if not self.owm_key:
            return None
        try:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {
                "lat": city["lat"],
                "lon": city["lon"],
                "appid": self.owm_key,
                "units": "metric",
            }
            r = self._session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            main = data.get("main", {})
            wind = data.get("wind", {})
            rain = data.get("rain", {})
            snow = data.get("snow", {})

            return {
                "source": "openweathermap",
                "temperature_c": main.get("temp", 0),
                "feels_like_c": main.get("feels_like", 0),
                "humidity_pct": main.get("humidity", 0),
                "precipitation_mm": rain.get("1h", 0) + snow.get("1h", 0),
                "rain_mm": rain.get("1h", 0),
                "snowfall_mm": snow.get("1h", 0),
                "cloud_cover_pct": data.get("clouds", {}).get("all", 0),
                "pressure_hpa": main.get("pressure", 0),
                "wind_speed_kmh": wind.get("speed", 0) * 3.6,
                "wind_direction_deg": wind.get("deg", 0),
                "wind_gusts_kmh": wind.get("gust", 0) * 3.6,
                "weather_code": data.get("weather", [{}])[0].get("id", 0),
            }
        except Exception as e:
            print(f"⚠️ OpenWeatherMap current failed: {e}")
            return None

    def _fetch_owm_forecast(self, city: dict, hours: int) -> Optional[List[Dict]]:
        """OpenWeatherMap 5-day/3-hour forecast."""
        if not self.owm_key:
            return None
        try:
            url = "https://api.openweathermap.org/data/2.5/forecast"
            params = {
                "lat": city["lat"],
                "lon": city["lon"],
                "appid": self.owm_key,
                "units": "metric",
            }
            r = self._session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()

            result = []
            for item in data.get("list", []):
                main = item.get("main", {})
                wind = item.get("wind", {})
                rain = item.get("rain", {})
                snow = item.get("snow", {})
                result.append({
                    "time": item.get("dt_txt", ""),
                    "temperature_c": main.get("temp", 0),
                    "feels_like_c": main.get("feels_like", 0),
                    "humidity_pct": main.get("humidity", 0),
                    "precip_probability_pct": item.get("pop", 0) * 100,
                    "precipitation_mm": rain.get("3h", 0) + snow.get("3h", 0),
                    "rain_mm": rain.get("3h", 0),
                    "snowfall_mm": snow.get("3h", 0),
                    "cloud_cover_pct": item.get("clouds", {}).get("all", 0),
                    "pressure_hpa": main.get("pressure", 0),
                    "wind_speed_kmh": wind.get("speed", 0) * 3.6,
                    "wind_gusts_kmh": wind.get("gust", 0) * 3.6,
                    "weather_code": item.get("weather", [{}])[0].get("id", 0),
                })
            return result[:hours]
        except Exception as e:
            print(f"⚠️ OpenWeatherMap forecast failed: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # WEATHERAPI.COM (FALLBACK 2)
    # ═══════════════════════════════════════════════════════════════

    def _fetch_weatherapi_current(self, city: dict) -> Optional[Dict]:
        """WeatherAPI.com current weather. Requires API key."""
        if not self.wapi_key:
            return None
        try:
            url = "https://api.weatherapi.com/v1/current.json"
            params = {
                "key": self.wapi_key,
                "q": f"{city['lat']},{city['lon']}",
            }
            r = self._session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            current = data.get("current", {})

            return {
                "source": "weatherapi",
                "temperature_c": current.get("temp_c", 0),
                "feels_like_c": current.get("feelslike_c", 0),
                "humidity_pct": current.get("humidity", 0),
                "precipitation_mm": current.get("precip_mm", 0),
                "rain_mm": current.get("precip_mm", 0),
                "snowfall_mm": 0,
                "cloud_cover_pct": current.get("cloud", 0),
                "pressure_hpa": current.get("pressure_mb", 0),
                "wind_speed_kmh": current.get("wind_kph", 0),
                "wind_direction_deg": current.get("wind_degree", 0),
                "wind_gusts_kmh": current.get("gust_kph", 0),
                "weather_code": current.get("condition", {}).get("code", 0),
            }
        except Exception as e:
            print(f"⚠️ WeatherAPI current failed: {e}")
            return None

    def _fetch_weatherapi_forecast(self, city: dict, hours: int) -> Optional[List[Dict]]:
        """WeatherAPI.com forecast."""
        if not self.wapi_key:
            return None
        try:
            days = max(1, min(3, hours // 24 + 1))
            url = "https://api.weatherapi.com/v1/forecast.json"
            params = {
                "key": self.wapi_key,
                "q": f"{city['lat']},{city['lon']}",
                "days": days,
            }
            r = self._session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()

            result = []
            for day in data.get("forecast", {}).get("forecastday", []):
                for h in day.get("hour", []):
                    result.append({
                        "time": h.get("time", ""),
                        "temperature_c": h.get("temp_c", 0),
                        "feels_like_c": h.get("feelslike_c", 0),
                        "humidity_pct": h.get("humidity", 0),
                        "precip_probability_pct": h.get("chance_of_rain", 0),
                        "precipitation_mm": h.get("precip_mm", 0),
                        "rain_mm": h.get("precip_mm", 0),
                        "snowfall_mm": h.get("chance_of_snow", 0),
                        "cloud_cover_pct": h.get("cloud", 0),
                        "pressure_hpa": h.get("pressure_mb", 0),
                        "wind_speed_kmh": h.get("wind_kph", 0),
                        "wind_gusts_kmh": h.get("gust_kph", 0),
                        "weather_code": h.get("condition", {}).get("code", 0),
                    })
            return result[:hours]
        except Exception as e:
            print(f"⚠️ WeatherAPI forecast failed: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # CACHE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    def _get_cached(self, key: str) -> Optional[dict]:
        if key in _cache:
            ts, data = _cache[key]
            if time.time() - ts < CACHE_TTL:
                return data
            del _cache[key]
        return None

    def _set_cached(self, key: str, data):
        _cache[key] = (time.time(), data)

    def clear_cache(self):
        _cache.clear()
