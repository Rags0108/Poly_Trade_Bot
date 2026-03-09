import pandas as pd
import streamlit as st
import json

st.title("Polymarket AI Trading Bot")

try:
    with open("trade_log.json", "r") as f:
        trades = json.load(f)
except:
    trades = []

if trades:
    df = pd.DataFrame(trades)

    # Format columns
    df["Confidence"] = df["confidence_percent"].astype(str) + "%"
    df["Edge"] = df["edge_percent"].astype(str) + "%"
    df["Fair Value"] = df["fair_value"]
    df["Price"] = df["price"]
    df["Direction"] = df["direction"]
    df["Market"] = df["market"]
    df["Size"] = df["size"]

    st.subheader("📜 Trade History")
    st.dataframe(df[[
        "time",
        "Market",
        "Direction",
        "Price",
        "Fair Value",
        "Edge",
        "Confidence",
        "Size"
    ]])
else:
    st.write("No trades yet.")
