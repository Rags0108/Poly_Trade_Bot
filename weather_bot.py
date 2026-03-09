"""
Weather Trading Bot — Main Entry Point

Starts the weather prediction trading engine with:
  - Multi-source weather data (Open-Meteo, OpenWeatherMap, WeatherAPI)
  - 5 trading strategies (forecast edge, extreme weather, consensus, seasonal, momentum)
  - Kelly criterion position sizing
  - Risk mode auto-graduation (SEED → GROWTH → FOCUSED → MEDIUM → AGGRESSIVE)
  - Stop-loss / take-profit / trailing stop position management
  - Auto-redeem for resolved positions
  - Telegram bot integration for alerts

Usage:
  python weather_bot.py                    # Paper trading, $100 balance
  python weather_bot.py --live             # Live trading
  python weather_bot.py --balance 50       # Custom starting balance
  python weather_bot.py --risk seed        # Start in SEED mode

Environment Variables (set in .env):
  OPENWEATHERMAP_KEY    — OpenWeatherMap API key (free fallback)
  WEATHERAPI_KEY        — WeatherAPI.com key (free fallback)
  POLY_PRIVATE_KEY      — For live trading on Polymarket
  POLY_PROXY_WALLET     — Proxy wallet (if using proxy)
  POLY_SIGNATURE_TYPE   — 0=EOA, 1=Magic, 2=Proxy
  TELEGRAM_TOKEN        — Telegram bot token for alerts
"""

import argparse
import os
import sys
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from weather_prediction.weather_trading_engine import WeatherTradingEngine
from bot.telegram_bot import run_bot, set_weather_engine

# ─── Lightweight health-check server for Railway ───────────────
_engine_ref = None


class _HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler: GET / returns JSON status."""

    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            body = json.dumps({
                "status": "ok",
                "engine": _engine_ref.get_full_status() if _engine_ref else {}
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # silence request logs


def _start_health_server():
    """Start health-check HTTP server on $PORT (Railway) or 8080."""
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    print(f"🌐 Health server listening on :{port}")
    server.serve_forever()


def parse_args():
    parser = argparse.ArgumentParser(description="Weather Prediction Trading Bot")
    parser.add_argument(
        "--live", action="store_true",
        help="Enable live trading (requires POLY_PRIVATE_KEY)"
    )
    parser.add_argument(
        "--balance", type=float, default=100.0,
        help="Starting paper balance (default: $100)"
    )
    parser.add_argument(
        "--risk", type=str, default="growth",
        choices=["seed", "growth", "focused", "medium", "aggressive"],
        help="Risk mode (default: growth)"
    )
    parser.add_argument(
        "--interval", type=int, default=30,
        help="Scan interval in seconds (default: 30)"
    )
    parser.add_argument(
        "--no-telegram", action="store_true",
        help="Disable Telegram bot"
    )
    return parser.parse_args()


def main():
    global _engine_ref
    args = parse_args()

    mode = "LIVE" if args.live else "PAPER"

    # Validate live mode requirements
    if mode == "LIVE":
        pk = os.getenv("POLY_PRIVATE_KEY", "").strip()
        if not pk or pk == "your_private_key":
            print("❌ Live mode requires POLY_PRIVATE_KEY in .env")
            print("   Set your Polymarket wallet private key and try again.")
            sys.exit(1)

    # Create engine
    engine = WeatherTradingEngine(
        mode=mode,
        starting_balance=args.balance,
        risk_mode=args.risk,
        scan_interval=args.interval,
    )
    _engine_ref = engine

    # Wire engine to Telegram commands
    set_weather_engine(engine)

    # Start Telegram bot in background (optional)
    if not args.no_telegram:
        telegram_token = os.getenv("TELEGRAM_TOKEN", "").strip()
        if telegram_token:
            print("🤖 Starting Telegram bot...")
            threading.Thread(target=run_bot, daemon=True).start()
        else:
            print("ℹ️ No TELEGRAM_TOKEN — Telegram alerts disabled")

    # Start health-check server for Railway (non-blocking)
    threading.Thread(target=_start_health_server, daemon=True).start()

    # Start trading engine (blocking)
    engine.start()


if __name__ == "__main__":
    main()
