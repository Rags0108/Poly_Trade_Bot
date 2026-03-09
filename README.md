# Poly Trade Bot

**Weather prediction trading bot for Polymarket** — Uses real-time weather data from multiple free APIs to find and trade weather prediction markets with Kelly criterion sizing, risk management, and auto-redemption.

## Features

- **5 Trading Strategies**: Forecast Edge, Extreme Weather Hunter, Consensus Divergence, Seasonal Pattern, Rapid Change Momentum
- **Multi-Source Weather Data**: Open-Meteo (primary, free), OpenWeatherMap, WeatherAPI.com — automatic fallback chain
- **Kelly Criterion Sizing**: Fractional Kelly with adaptive streak adjustments
- **5 Risk Modes**: SEED → GROWTH → FOCUSED → MEDIUM → AGGRESSIVE with auto-graduation
- **Position Management**: Stop-loss, take-profit, trailing stops, time-based exits
- **Auto-Redeem**: On-chain redemption of resolved positions on Polygon
- **Telegram Bot**: `/weather`, `/positions`, `/pnl`, `/strategies`, `/mode`, `/status`
- **Streamlit Dashboard**: Real-time trade visualization
- **Railway Deploy**: One-click deployment with health check endpoint

## Quick Start

```bash
# Clone
git clone https://github.com/Rags0108/Poly_Trade_Bot.git
cd Poly_Trade_Bot

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run (paper trading)
python weather_bot.py

# Run (live trading)
python weather_bot.py --live

# Dashboard
streamlit run weather_dashboard.py
```

## CLI Options

```
python weather_bot.py [OPTIONS]

  --live                 Enable live trading (requires POLY_PRIVATE_KEY)
  --balance FLOAT        Starting paper balance (default: $100)
  --risk MODE            Risk mode: seed/growth/focused/medium/aggressive
  --interval SECONDS     Market scan interval (default: 30)
  --no-telegram          Disable Telegram bot
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | No | OpenAI key for LLM strategy |
| `GEMINI_API_KEY` | No | Google Gemini key |
| `TELEGRAM_TOKEN` | No | Telegram bot alerts |
| `TELEGRAM_CHAT_ID` | No | Telegram chat for alerts |
| `POLY_PRIVATE_KEY` | Live only | Polymarket wallet private key |
| `POLY_PROXY_WALLET` | No | Proxy wallet address |
| `OPENWEATHERMAP_KEY` | No | OpenWeatherMap free key |
| `WEATHERAPI_KEY` | No | WeatherAPI.com free key |
| `POLYGON_RPC_URL` | No | Custom Polygon RPC |

> Open-Meteo (primary weather source) requires **no API key**.

## Architecture

```
weather_bot.py                  ← CLI entry point + health server
├── weather_prediction/
│   ├── weather_api.py          ← Multi-source weather data (3 APIs)
│   ├── weather_model.py        ← Ensemble prediction (4 sub-models)
│   ├── weather_strategy.py     ← 5 trading strategies
│   ├── weather_balance_manager.py ← Kelly sizing + risk modes
│   ├── weather_position_manager.py ← Stop-loss / trailing stops
│   ├── weather_live_trader.py  ← Paper + Live CLOB execution
│   ├── auto_redeem.py          ← On-chain position redemption
│   ├── weather_market_scanner.py ← Polymarket market discovery
│   ├── weather_strategy_picker.py ← Multi-strategy orchestrator
│   └── weather_trading_engine.py ← Main async engine
├── core/                       ← Base strategies & market API
├── bot/telegram_bot.py         ← Telegram commands
├── weather_dashboard.py        ← Streamlit dashboard
└── trade_dashboard.py          ← Legacy trade dashboard
```

## Railway Deployment

1. Connect this repo to [Railway](https://railway.app)
2. Set environment variables in Railway dashboard
3. Deploy — the bot starts automatically with health check on `/health`

Railway config is in `railway.toml` and `Procfile`.

## Risk Modes

| Mode | Balance Range | Kelly Fraction | Max Position |
|------|--------------|----------------|--------------|
| SEED | $0 – $5 | 15% | $1.00 |
| GROWTH | $5 – $20 | 20% | $3.00 |
| FOCUSED | $20 – $50 | 25% | $8.00 |
| MEDIUM | $50 – $200 | 30% | $20.00 |
| AGGRESSIVE | $200+ | 35% | $50.00 |

## License

MIT
