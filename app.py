import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Page Configuration
st.set_page_config(
    page_title="NSE Trend-Shift Scanner & Automated Signal Validator",
    page_icon="⚡",
    layout="wide"
)

# Header & Strategy Summary
st.title("⚡ NSE Trend-Shift Scanner & Automated Signal Validator")
st.markdown(
    "**Single Strategy:** Enter on **SuperTrend (10,3) Green Flip + RSI Confirmation** (1-Hour Chart) | "
    "**Quick Exit:** Take fixed profit target or exit immediately on stop-loss/trend flip."
)

# Default Liquid Nifty Watchlist
DEFAULT_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "AXISBANK.NS",
    "M&M.NS", "SUNPHARMA.NS", "MARUTI.NS", "TITAN.NS", "BAJFINANCE.NS",
    "NTPC.NS", "POWERGRID.NS", "HCLTECH.NS", "WIPRO.NS", "TATASTEEL.NS"
]

# Sidebar Controls
st.sidebar.header("⚙️ Strategy Settings")
target_pct = st.sidebar.number_input("Profit Target (%)", min_value=0.5, max_value=15.0, value=2.5, step=0.5) / 100
stoploss_pct = st.sidebar.number_input("Stop Loss (%)", min_value=0.5, max_value=10.0, value=1.5, step=0.5) / 100
rsi_threshold = st.sidebar.slider("Minimum RSI for Entry", min_value=45, max_value=70, value=55)
fee_pct = st.sidebar.number_input("Round-Trip Taxes & Fees (%)", min_value=0.0, max_value=1.0, value=0.15, step=0.05) / 100

st.sidebar.markdown("---")
st.sidebar.info(
    "**Risk Reminder:** No strategy is 100% foolproof. Always diversify across 5–10 stocks, "
    "respect stop-losses, and paper trade before deploying real capital."
)

# Watchlist Input
user_tickers = st.text_input(
    "NSE Watchlist (comma-separated, ending with .NS):",
    value=", ".join(DEFAULT_TICKERS)
)
tickers = [t.strip().upper() for t in user_tickers.split(",") if t.strip()]

# --- TECHNICAL INDICATORS ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_supertrend(df, period=10, multiplier=3.0):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    
    hl2 = (high + low) / 2
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)
    
    in_uptrend = [True] * len(df)
    for i in range(1, len(df)):
        if close.iloc[i] > upperband.iloc[i - 1]:
            in_uptrend[i] = True
        elif close.iloc[i] < lowerband.iloc[i - 1]:
            in_uptrend[i] = False
        else:
            in_uptrend[i] = in_uptrend[i - 1]
            if in_uptrend[i] and lowerband.iloc[i] < lowerband.iloc[i - 1]:
                lowerband.iloc[i] = lowerband.iloc[i - 1]
            if not in_uptrend[i] and upperband.iloc[i] > upperband.iloc[i - 1]:
                upperband.iloc[i] = upperband.iloc[i - 1]
                
    df["In_Uptrend"] = in_uptrend
    return df

@st.cache_data(ttl=900)
def fetch_data(ticker, period="1y"):
    try:
        df = yf.download(ticker, period=period, interval="1h", progress=False)
        if df.empty or len(df) < 40:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df["RSI"] = calculate_rsi(df["Close"])
        df = calculate_supertrend(df)
        df.dropna(inplace=True)
        return df
    except Exception:
        return None

# --- SIMULATION ENGINE ---
def simulate_signals(ticker_list, period="1y"):
    all_trades = []
    open_trades = []
    
    for ticker in ticker_list:
        df = fetch_data(ticker, period=period)
        if df is None:
            continue
            
        in_trade = False
        entry_price = 0.0
        entry_time = None
        target_price = 0.0
        stop_price = 0.0
        
        for i in range(1, len(df) - 1):
            curr_row = df.iloc[i]
            prev_row = df.iloc[i - 1]
            next_row = df.iloc[i + 1]
            
            if not in_trade:
                if (not prev_row["In_Uptrend"]) and curr_row["In_Uptrend"] and (curr_row["RSI"] > rsi_threshold):
                    in_trade = True
                    entry_price = float(next_row["Open"])
                    entry_time = df.index[i + 1]
                    target_price = entry_price * (1 + target_pct)
                    stop_price = entry_price * (1 - stoploss_pct)
            else:
                candle_high = float(curr_row["High"])
                candle_low = float(curr_row["Low"])
                candle_close = float(curr_row["Close"])
                
                if candle_low <= stop_price:
                    net_ret = (-stoploss_pct - fee_pct) * 100
                    all_trades.append({
                        "Stock": ticker.replace(".NS", ""),
                        "Entry Time": str(entry_time)[:16],
                        "Exit Time": str(df.index[i])[:16],
                        "Entry (₹)": round(entry_price, 2),
                        "Exit (₹)": round(stop_price, 2),
                        "Status": "❌ FALSE SIGNAL (Stop-Loss)",
                        "Net Return (%)": round(net_ret, 2)
                    })
                    in_trade = False
                elif candle_high >= target_price:
                    net_ret = (target_pct - fee_pct) * 100
                    all_trades.append({
                        "Stock": ticker.replace(".NS", ""),
                        "Entry Time": str(entry_time)[:16],
                        "Exit Time": str(df.index[i])[:16],
                        "Entry (₹)": round(entry_price, 2),
                        "Exit (₹)": round(target_price, 2),
                        "Status": "✅ TRUE SIGNAL (Target Hit)",
                        "Net Return (%)": round(net_ret, 2)
                    })
                    in_trade = False
                elif not curr_row["In_Uptrend"]:
                    raw_ret = (candle_close - entry_price) / entry_price
                    net_ret = (raw_ret - fee_pct) * 100
                    label = "✅ TRUE SIGNAL (Trend Exit Profit)" if net_ret > 0 else "❌ FALSE SIGNAL (Trend Reversal)"
                    all_trades.append({
                        "Stock": ticker.replace(".NS", ""),
                        "Entry Time": str(entry_time)[:16],
                        "Exit Time": str(df.index[i])[:16],
                        "Entry (₹)": round(entry_price, 2),
                        "Exit (₹)": round(candle_close, 2),
                        "Status": label,
                        "Net Return (%)": round(net_ret, 2)
                    })
                    in_trade = False
                    
        # Record still-open trades for the live forward tracker
        if in_trade:
            curr_price = float(df["Close"].iloc[-1])
            unrealized = ((curr_price - entry_price) / entry_price - fee_pct) * 100
            open_trades.append({
                "Stock": ticker.replace(".NS", ""),
                "Entry Time": str(entry_time)[:16],
                "Entry (₹)": round(entry_price, 2),
                "Current (₹)": round(curr_price, 2),
                "Target (₹)": round(target_price, 2),
                "Stop Loss (₹)": round(stop_price, 2),
                "Unrealized (%)": round(unrealized, 2)
            })
            
    return pd.DataFrame(all_trades), pd.DataFrame(open_trades)

# --- TABS ---
tab1, tab2, tab3 = st.tabs([
    "📡 Live Market Scanner",
    "🧪 Automated Signal Tester (1-Year)",
    "📝 Recent 14-Day Forward Grader"
])

# TAB 1: LIVE SCANNER
with tab1:
    st.subheader("Current 1-Hour Market Signals")
    if st.button("Scan Live Market Now", type="primary"):
        with st.spinner("Scanning latest NSE 1-hour candles..."):
            rows = []
            for ticker in tickers:
                df = fetch_data(ticker, period="1mo")
                if df is None:
                    continue
                curr_close = float(df["Close"].iloc[-1])
                curr_rsi = float(df["RSI"].iloc[-1])
                curr_trend = bool(df["In_Uptrend"].iloc[-1])
                prev_trend = bool(df["In_Uptrend"].iloc[-2])

                if not prev_trend and curr_trend and curr_rsi > rsi_threshold:
                    signal = "🟢 CONFIRMED BUY (Fresh Flip)"
                    priority = 1
                elif curr_trend and curr_rsi >= 70:
                    signal = "💰 TAKE PROFIT (RSI Overbought)"
                    priority = 2
                elif prev_trend and not curr_trend:
                    signal = "🔴 EXIT / SELL (Trend Flipped Red)"
                    priority = 3
                elif curr_trend:
                    signal = "🟡 ACTIVE UPTREND"
                    priority = 4
                else:
                    signal = "⚪ WAIT (No Setup)"
                    priority = 5

                rows.append({
                    "Priority": priority,
                    "Stock": ticker.replace(".NS", ""),
                    "Last Price (₹)": round(curr_close, 2),
                    "RSI (14)": round(curr_rsi, 1),
                    "Action Signal": signal,
                    f"Target (+{target_pct*100:.1f}%)": round(curr_close * (1 + target_pct), 2),
                    f"Stop Loss (-{stoploss_pct*100:.1f}%)": round(curr_close * (1 - stoploss_pct), 2)
                })
                
            if rows:
                scan_df = pd.DataFrame(rows).sort_values("Priority").drop(columns=["Priority"])
                st.dataframe(scan_df, use_container_width=True, hide_index=True)
