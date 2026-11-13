import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="NSE Trend-Shift Scanner", page_icon="⚡", layout="wide")

st.title("⚡ NSE Trend-Shift Scanner & Automated Signal Validator")
st.write("Strategy: SuperTrend (10,3) Green Flip + RSI > 55 (1-Hour Chart) | Target: +2.5% | Stop-Loss: -1.5%")

NIFTY_50 = [
    "ADANIENT.NS", "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "BAJAJ-AUTO.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "BEL.NS", "BHARTIARTL.NS",
    "BPCL.NS", "BRITANNIA.NS", "CIPLA.NS", "COALINDIA.NS", "DRREDDY.NS",
    "EICHERMOT.NS", "GRASIM.NS", "HCLTECH.NS", "HDFCBANK.NS", "HDFCLIFE.NS",
    "HEROMOTOCO.NS", "HINDALCO.NS", "HINDUNILVR.NS", "ICICIBANK.NS", "INDUSINDBK.NS",
    "INFY.NS", "ITC.NS", "JSWSTEEL.NS", "KOTAKBANK.NS", "LT.NS",
    "M&M.NS", "MARUTI.NS", "NESTLEIND.NS", "NTPC.NS", "ONGC.NS",
    "POWERGRID.NS", "RELIANCE.NS", "SBILIFE.NS", "SBIN.NS", "SHRIRAMFIN.NS",
    "SUNPHARMA.NS", "TATACONSUM.NS", "TATAMOTORS.NS", "TATASTEEL.NS", "TCS.NS",
    "TECHM.NS", "TITAN.NS", "TRENT.NS", "ULTRACEMCO.NS", "WIPRO.NS"
]

st.sidebar.header("⚙️ Strategy Settings")
target_pct = st.sidebar.number_input("Profit Target (%)", 0.5, 15.0, 2.5, 0.5) / 100
stoploss_pct = st.sidebar.number_input("Stop Loss (%)", 0.5, 10.0, 1.5, 0.5) / 100
rsi_threshold = st.sidebar.slider("Minimum RSI for Entry", 45, 70, 55)
fee_pct = st.sidebar.number_input("Round-Trip Taxes & Fees (%)", 0.0, 1.0, 0.15, 0.05) / 100

user_tickers = st.text_input("NSE Watchlist (Full Nifty 50 loaded by default):", value=", ".join(NIFTY_50))
tickers = [t.strip().upper() for t in user_tickers.split(",") if t.strip()]

def calc_indicators(df):
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + (gain / loss)))

    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(10).mean()
    hl2 = (high + low) / 2
    upper = hl2 + (3.0 * atr)
    lower = hl2 - (3.0 * atr)

    trend = [True] * len(df)
    for i in range(1, len(df)):
        if close.iloc[i] > upper.iloc[i - 1]:
            trend[i] = True
        elif close.iloc[i] < lower.iloc[i - 1]:
            trend[i] = False
        else:
            trend[i] = trend[i - 1]
            if trend[i] and lower.iloc[i] < lower.iloc[i - 1]:
                lower.iloc[i] = lower.iloc[i - 1]
            if not trend[i] and upper.iloc[i] > upper.iloc[i - 1]:
                upper.iloc[i] = upper.iloc[i - 1]
    df["In_Uptrend"] = trend
    return df.dropna()

@st.cache_data(ttl=900)
def get_stock_data(ticker, period="1y"):
    try:
        df = yf.download(ticker, period=period, interval="1h", progress=False)
        if df.empty or len(df) < 40:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return calc_indicators(df)
    except Exception:
        return None

def simulate_trades(ticker_list, period="1y"):
    closed_trades, open_trades = [], []
    for ticker in ticker_list:
        df = get_stock_data(ticker, period=period)
        if df is None:
            continue
        in_trade, entry_price, entry_time, target_p, stop_p = False, 0.0, None, 0.0, 0.0
        for i in range(1, len(df) - 1):
            curr, prev, nxt = df.iloc[i], df.iloc[i - 1], df.iloc[i + 1]
            if not in_trade:
                if (not prev["In_Uptrend"]) and curr["In_Uptrend"] and (curr["RSI"] > rsi_threshold):
                    in_trade = True
                    entry_price = float(nxt["Open"])
                    entry_time = df.index[i + 1]
                    target_p = entry_price * (1 + target_pct)
                    stop_p = entry_price * (1 - stoploss_pct)
            else:
                if float(curr["Low"]) <= stop_p:
                    net = (-stoploss_pct - fee_pct) * 100
                    closed_trades.append({
                        "Stock": ticker.replace(".NS", ""), "Entry Time": str(entry_time)[:16],
                        "Exit Time": str(df.index[i])[:16], "Entry (₹)": round(entry_price, 2),
                        "Exit (₹)": round(stop_p, 2), "Status": "❌ FALSE (Stop-Loss)", "Net Return (%)": round(net, 2)
                    })
                    in_trade = False
                elif float(curr["High"]) >= target_p:
                    net = (target_pct - fee_pct) * 100
                    closed_trades.append({
                        "Stock": ticker.replace(".NS", ""), "Entry Time": str(entry_time)[:16],
                        "Exit Time": str(df.index[i])[:16], "Entry (₹)": round(entry_price, 2),
                        "Exit (₹)": round(target_p, 2), "Status": "✅ TRUE (Target Hit)", "Net Return (%)": round(net, 2)
                    })
                    in_trade = False
                elif not curr["In_Uptrend"]:
                    net = (((float(curr["Close"]) - entry_price) / entry_price) - fee_pct) * 100
                    status = "✅ TRUE (Trend Profit)" if net > 0 else "❌ FALSE (Trend Reversal)"
                    closed_trades.append({
                        "Stock": ticker.replace(".NS", ""), "Entry Time": str(entry_time)[:16],
                        "Exit Time": str(df.index[i])[:16], "Entry (₹)": round(entry_price, 2),
                        "Exit (₹)": round(float(curr["Close"]), 2), "Status": status, "Net Return (%)": round(net, 2)
                    })
                    in_trade = False
        if in_trade:
            curr_p = float(df["Close"].iloc[-1])
            unreal = (((curr_p - entry_price) / entry_price) - fee_pct) * 100
            open_trades.append({
                "Stock": ticker.replace(".NS", ""), "Entry Time": str(entry_time)[:16],
                "Entry (₹)": round(entry_price, 2), "Current (₹)": round(curr_p, 2),
                "Target (₹)": round(target_p, 2), "Stop Loss (₹)": round(stop_p, 2), "Unrealized (%)": round(unreal, 2)
            })
    return pd.DataFrame(closed_trades), pd.DataFrame(open_trades)

tab1, tab2, tab3 = st.tabs(["📡 Live Market Scanner", "🧪 1-Year Signal Tester", "📝 14-Day Forward Grader"])

with tab1:
    st.subheader("Live 1-Hour Market Signals")
    if st.button("Click Here to Scan Live Market"):
        with st.spinner("Scanning Nifty 50 1-hour charts..."):
            rows = []
            for ticker in tickers:
                df = get_stock_data(ticker, period="1mo")
                if df is None:
                    continue
                c_close, c_rsi = float(df["Close"].iloc[-1]), float(df["RSI"].iloc[-1])
                c_trend, p_trend = bool(df["In_Uptrend"].iloc[-1]), bool(df["In_Uptrend"].iloc[-2])
                if not p_trend and c_trend and c_rsi > rsi_threshold:
                    sig, prio = "🟢 CONFIRMED BUY (Fresh Flip)", 1
                elif c_trend and c_rsi >= 70:
                    sig, prio = "💰 TAKE PROFIT (RSI Overbought)", 2
                elif p_trend and not c_trend:
                    sig, prio = "🔴 EXIT / SELL (Trend Flipped Red)", 3
                elif c_trend:
                    sig, prio = "🟡 ACTIVE UPTREND", 4
                else:
                    sig, prio = "⚪ WAIT (No Setup)", 5
                rows.append({
                    "Priority": prio, "Stock": ticker.replace(".NS", ""), "Price (₹)": round(c_close, 2),
                    "RSI (14)": round(c_rsi, 1), "Signal": sig,
                    "Target (₹)": round(c_close * (1 + target_pct), 2), "Stop Loss (₹)": round(c_close * (1 - stoploss_pct), 2)
                })
            if rows:
                out_df = pd.DataFrame(rows).sort_values("Priority").drop(columns=["Priority"])
                st.dataframe(out_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Automated 1-Year Signal Validation")
    if st.button("Click Here to Run 1-Year Validation Test"):
        with st.spinner("Testing 1 year of historical signals across Nifty 50 (takes ~25 seconds)..."):
            trades_df, _ = simulate_trades(tickers, period="1y")
            if trades_df.empty:
                st.warning("No completed signals found.")
            else:
                total = len(trades_df)
                wins = len(trades_df[trades_df["Net Return (%)"] > 0])
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total Signals", total)
                c2.metric("True Signals (Wins)", wins)
                c3.metric("False Signals (Losses)", total - wins)
                c4.metric("Accuracy (%)", f"{(wins / total) * 100:.1f}%")

                summary = trades_df.groupby("Stock").agg(
                    Signals=("Net Return (%)", "count"),
                    Wins=("Net Return (%)", lambda x: (x > 0).sum()),
                    Losses=("Net Return (%)", lambda x: (x <= 0).sum()),
                    Accuracy_Pct=("Net Return (%)", lambda x: round((x > 0).mean() * 100, 1)),
                    Total_Net_Return_Pct=("Net Return (%)", lambda x: round(x.sum(), 2))
                ).sort_values("Accuracy_Pct", ascending=False).reset_index()
                st.dataframe(summary, use_container_width=True, hide_index=True)
                st.dataframe(trades_df, use_container_width=True, hide_index=True)
                st.download_button("Download Audit CSV", trades_df.to_csv(index=False).encode("utf-8"), "audit_1y.csv", "text/csv")

with tab3:
    st.subheader("Recent 14-Day Forward Signal Grader")
    if st.button("Click Here to Grade Last 14 Days"):
        with st.spinner("Checking last 14 days of signals..."):
            closed_14, open_14 = simulate_trades(tickers, period="1mo")
            cutoff = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
if not closed_14.empty:
                closed_14 = closed_14[closed_14["Entry Time"] >= cutoff]
            if not open_14.empty:
                open_14 = open_14[open_14["Entry Time"] >= cutoff]
            st.write("**Active Signals (In Progress):**")
            st.dataframe(open_14, use_container_width=True, hide_index=True)
            st.write("**Completed Signals (Last 14 Days):**")
            st.dataframe(closed_14, use_container_width=True, hide_index=True)
