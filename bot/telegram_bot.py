from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

app_instance = None
_telegram_loop = None


# =========================
# COMMAND HANDLERS
# =========================

# Reference to the weather engine (set by weather_bot.py)
_weather_engine = None


def set_weather_engine(engine):
    """Called by weather_bot.py to wire up the engine for commands."""
    global _weather_engine
    _weather_engine = engine


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌤️ Weather Trading Bot\n\n"
        "Commands:\n"
        "/status — Bot & balance status\n"
        "/weather <city> — Current weather\n"
        "/positions — Open positions\n"
        "/pnl — P&L summary\n"
        "/strategies — Strategy stats\n"
        "/mode — Current risk mode\n"
        "/help — Show commands"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _weather_engine:
        s = _weather_engine.get_full_status()
        bal = s.get("balance", {})
        eng = s.get("engine", {})
        msg = (
            f"{'🟢' if eng.get('running') else '🔴'} Weather Bot | {eng.get('mode', '?')}\n"
            f"Balance: ${bal.get('balance', 0):.2f}\n"
            f"Mode: {bal.get('mode_emoji', '')} {bal.get('mode', '?')}\n"
            f"Drawdown: {bal.get('drawdown_pct', 0):.1f}%\n"
            f"Scans: {eng.get('scan_count', 0)}"
        )
    else:
        msg = "✅ Bot Active — engine not attached yet"
    await update.message.reply_text(msg)


async def weather_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current weather for a city."""
    if not _weather_engine:
        await update.message.reply_text("⚠️ Engine not running")
        return
    city = " ".join(context.args).lower() if context.args else "new_york"
    city_key = city.replace(" ", "_")
    try:
        data = _weather_engine.weather_client.get_current_weather(city_key)
        if data:
            msg = (
                f"\U0001f321\ufe0f {city_key.replace('_', ' ').title()}\n"
                f"Temp: {data.get('temperature_c', '?')}\u00b0C\n"
                f"Humidity: {data.get('humidity_pct', '?')}%\n"
                f"Wind: {data.get('wind_speed_kmh', '?')} km/h\n"
                f"Source: {data.get('source', '?')}"
            )
        else:
            msg = f"❌ No data for {city_key}"
    except Exception as e:
        msg = f"⚠️ Error: {e}"
    await update.message.reply_text(msg)


async def positions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show open positions."""
    if not _weather_engine:
        await update.message.reply_text("⚠️ Engine not running")
        return
    stats = _weather_engine.position_manager.get_stats()
    positions = _weather_engine.position_manager.positions
    if not positions:
        msg = "📭 No open positions"
    else:
        lines = [f"📊 {stats['open_positions']} Open Positions\n"]
        for p in positions[:10]:
            lines.append(
                f"• {p.market_question[:40]}\n"
                f"  {p.direction} @ ${p.entry_price:.3f} → ${p.current_price:.3f} "
                f"({p.unrealized_pnl_pct:+.1f}%)"
            )
        msg = "\n".join(lines)
    await update.message.reply_text(msg)


async def pnl_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """P&L summary."""
    if not _weather_engine:
        await update.message.reply_text("⚠️ Engine not running")
        return
    stats = _weather_engine.position_manager.get_stats()
    bal = _weather_engine.balance_manager.get_status()
    msg = (
        f"📈 P&L Report\n\n"
        f"Balance: ${bal.get('balance', 0):.2f}\n"
        f"Peak: ${bal.get('peak_balance', 0):.2f}\n"
        f"Open P&L: ${stats.get('open_pnl', 0):.2f}\n"
        f"Realized: ${stats.get('realized_pnl', 0):.2f}\n"
        f"Win Rate: {stats.get('win_rate', 0):.1f}%\n"
        f"Wins: {bal.get('consecutive_wins', 0)} streak | "
        f"Losses: {bal.get('consecutive_losses', 0)} streak"
    )
    await update.message.reply_text(msg)


async def strategies_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Strategy performance."""
    if not _weather_engine:
        await update.message.reply_text("⚠️ Engine not running")
        return
    strats = _weather_engine.strategy_tracker.get_all_stats()
    if not strats:
        msg = "📊 No strategy data yet"
    else:
        lines = ["📊 Strategy Stats\n"]
        for name, s in strats.items():
            lines.append(
                f"• {name}: {s['wins']}W/{s['losses']}L "
                f"({s['win_rate']:.0f}%) adj={s['adjustment']:+.3f}"
            )
        msg = "\n".join(lines)
    await update.message.reply_text(msg)


async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current risk mode."""
    if not _weather_engine:
        await update.message.reply_text("⚠️ Engine not running")
        return
    bal = _weather_engine.balance_manager.get_status()
    msg = (
        f"⚙️ Risk Mode: {bal.get('mode_emoji', '')} {bal.get('mode', '?')}\n"
        f"Tradeable: ${bal.get('tradeable', 0):.2f}\n"
        f"Reserve: ${bal.get('reserve', 0):.2f}\n"
        f"Size Multiplier: {bal.get('size_multiplier', 1.0):.2f}×"
    )
    await update.message.reply_text(msg)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


# =========================
# MESSAGE SENDER (SAFE)
# =========================

async def send_telegram_message(text: str):
    global app_instance
    if app_instance and CHAT_ID:
        await app_instance.bot.send_message(chat_id=CHAT_ID, text=text)


def send_message_sync(text: str):
    """
    Allows other threads (trading loop) to send messages safely.
    Uses run_coroutine_threadsafe for cross-thread async calls.
    """
    if app_instance and app_instance.running and _telegram_loop and CHAT_ID:
        try:
            asyncio.run_coroutine_threadsafe(send_telegram_message(text), _telegram_loop)
        except Exception:
            pass


async def _on_post_init(app):
    """Capture Telegram event loop for cross-thread sends."""
    global _telegram_loop
    _telegram_loop = asyncio.get_running_loop()


# =========================
# TRADE ALERTS
def send_trade_alert(market_data, analysis):
    message = f"""
🚀 TRADE SIGNAL

Market: {market_data.get("market")}
Direction: {analysis.get("direction")}
Edge: {analysis.get("edge")}%
Confidence: {analysis.get("confidence_percent")}%
"""
    # send_message(chat_id=CHAT_ID, text=message)
    send_message_sync(message)

def send_trade_open(trade):
    message = f"""
🟢 TRADE OPENED

Market: {trade['market']}
Size: ${trade['size']}
Price: ${trade['price']}
Direction: {trade['direction']}
Confidence: {trade['confidence_percent']}%
Edge: {trade['edge_percent']}%
"""
    send_message_sync(message)


def send_trade_close(trade):
    message = f"""
🔴 TRADE CLOSED

Market: {trade['market']}
Direction: {trade['direction']}
Exit Price: ${trade['price']}
PnL: {trade.get('pnl', 'N/A')}
"""
    send_message_sync(message)


# =========================
# RUN BOT
# =========================

def run_bot():
    global app_instance, _telegram_loop

    if not BOT_TOKEN:
        print("⚠️ TELEGRAM_TOKEN not set — Telegram bot disabled")
        return

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(_on_post_init)
        .build()
    )
    app_instance = app

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("weather", weather_cmd))
    app.add_handler(CommandHandler("positions", positions_cmd))
    app.add_handler(CommandHandler("pnl", pnl_cmd))
    app.add_handler(CommandHandler("strategies", strategies_cmd))
    app.add_handler(CommandHandler("mode", mode_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    print("Telegram bot is running...")
    # stop_signals=None avoids signal handling issues when run outside main thread.
    app.run_polling(stop_signals=None, drop_pending_updates=True)
