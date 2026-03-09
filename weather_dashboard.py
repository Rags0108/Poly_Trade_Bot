"""
Weather Trading Dashboard — Streamlit visualization.

Run: streamlit run weather_dashboard.py
"""

import json
import pandas as pd
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Weather Trading Bot", layout="wide")
st.title("🌤️ Weather Prediction Trading Bot")

# Load trade log
try:
    with open("weather_trade_log.json", "r") as f:
        trades = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    trades = []

# Load bot status
try:
    with open("bot_status.json", "r") as f:
        status = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    status = {}

# Status
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Status", "Running" if status.get("bot_running") else "Stopped")
with col2:
    total_trades = len(trades)
    st.metric("Total Trades", total_trades)
with col3:
    if trades:
        closes = [t for t in trades if t.get("event") == "CLOSE"]
        total_pnl = sum(t.get("pnl", 0) for t in closes)
        st.metric("Total P&L", f"${total_pnl:.2f}")
    else:
        st.metric("Total P&L", "$0.00")
with col4:
    if trades:
        closes = [t for t in trades if t.get("event") == "CLOSE"]
        wins = sum(1 for t in closes if t.get("pnl", 0) > 0)
        wr = (wins / max(1, len(closes))) * 100
        st.metric("Win Rate", f"{wr:.1f}%")
    else:
        st.metric("Win Rate", "N/A")

st.divider()

# Trade History
if trades:
    st.subheader("📜 Trade History")

    df = pd.DataFrame(trades)

    # Format for display
    display_cols = []
    if "time" in df.columns:
        display_cols.append("time")
    if "market" in df.columns:
        display_cols.append("market")
    if "direction" in df.columns:
        display_cols.append("direction")
    if "price" in df.columns:
        display_cols.append("price")
    if "size" in df.columns:
        display_cols.append("size")
    if "edge_percent" in df.columns:
        display_cols.append("edge_percent")
    if "confidence" in df.columns:
        display_cols.append("confidence")
    if "strategy" in df.columns:
        display_cols.append("strategy")
    if "kelly_fraction" in df.columns:
        display_cols.append("kelly_fraction")
    if "pnl" in df.columns:
        display_cols.append("pnl")
    if "reason" in df.columns:
        display_cols.append("reason")

    if display_cols:
        st.dataframe(df[display_cols], use_container_width=True)

    # Strategy breakdown
    if "strategy" in df.columns:
        st.subheader("📊 Strategy Breakdown")
        strategy_counts = df["strategy"].value_counts()
        st.bar_chart(strategy_counts)

    # P&L over time
    closes_df = df[df.get("event", pd.Series(dtype=str)) == "CLOSE"] if "event" in df.columns else pd.DataFrame()
    if not closes_df.empty and "pnl" in closes_df.columns:
        st.subheader("📈 Cumulative P&L")
        closes_df = closes_df.copy()
        closes_df["cumulative_pnl"] = closes_df["pnl"].cumsum()
        st.line_chart(closes_df["cumulative_pnl"])

else:
    st.info("No trades yet. Start the weather bot: `python weather_bot.py`")

st.divider()
st.caption("Weather Trading Bot — Powered by Open-Meteo, OpenWeatherMap, WeatherAPI | Polymarket CLOB")
