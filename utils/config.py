from dotenv import load_dotenv
import os

load_dotenv()

# ======= API KEYS & PROVIDERS =======
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")          # Google Gemini (Generative AI) key
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()  # "openai" or "gemini"

# ======= Bot & Wallet =======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY", "YOUR_PRIVATE_KEY")

# ======= Polymarket Live Trading =======
POLY_PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY", "")
POLY_PROXY_WALLET = os.getenv("POLY_PROXY_WALLET", "")
POLY_SIGNATURE_TYPE = int(os.getenv("POLY_SIGNATURE_TYPE", "0"))
CLOB_RELAY_URL = os.getenv("CLOB_RELAY_URL", "")
POLYMARKET_MIN_ORDER_SIZE = 1.0  # $1 minimum order

# ======= Weather API Keys =======
OPENWEATHERMAP_KEY = os.getenv("OPENWEATHERMAP_KEY", "")
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY", "")

# ======= Risk & Trading =======
MAX_DAILY_LOSS = 50      # dollars
MAX_POSITION_SIZE = 20   # per trade
TRADE_INTERVAL = 30      # seconds
STARTING_BALANCE = float(os.getenv("STARTING_BALANCE", "100"))

# ======= Weather Trading Defaults =======
WEATHER_SCAN_INTERVAL = 30     # seconds between market scans
WEATHER_MIN_EDGE = 3.0         # minimum edge % to trade
WEATHER_MIN_CONFIDENCE = 0.50  # minimum confidence to trade
WEATHER_DEFAULT_RISK_MODE = os.getenv("WEATHER_RISK_MODE", "growth")
