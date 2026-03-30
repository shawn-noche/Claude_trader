"""dashboard/app.py — Streamlit app entry point.

Launch with:
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import streamlit as st
from config import INITIAL_CAPITAL
from trades.database import init_db

init_db()

SETTINGS_FILE = Path(__file__).parent.parent / "user_settings.json"
if SETTINGS_FILE.exists():
    try:
        saved = json.loads(SETTINGS_FILE.read_text())
        for key, value in saved.items():
            if key not in st.session_state:
                st.session_state[key] = value
    except Exception:
        pass

st.set_page_config(
    page_title="Turtle Trader",
    page_icon="T",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    st.title("Turtle Trader")
    st.caption("Richard Dennis's Turtle Trading System")
    st.divider()
    account_equity = st.session_state.get("account_equity", INITIAL_CAPITAL)
    st.metric("Account Equity", f"${account_equity:,.2f}")
    st.divider()
    st.markdown("""
    **Navigation:**
    - [Today's Signals](./signals)
    - [My Trades](./my_trades)
    - [Watchlist](./watchlist)
    - [Backtest](./backtest)
    - [Settings](./settings)
    """)
    st.divider()
    st.caption("Data via Yahoo Finance (yfinance). For informational purposes only.")

st.title("Turtle Trader Signal System")
st.subheader("Richard Dennis's Original Turtle Trading System")

st.markdown("""
This system generates Turtle Trading signals. It tells you exactly what to do and why
- you execute manually.

---

### How to Use This System

| Step | Action |
|------|--------|
| 1. | Go to **Today's Signals** each morning to see new entry and exit alerts |
| 2. | Review each signal card - entry price, stop-loss, position size, pyramid levels |
| 3. | Execute trades manually through your broker |
| 4. | Log your trades in **My Trades** so the system can monitor them |
| 5. | Check **My Trades** daily for stop-loss breaches and exit signals |
| 6. | Use **Watchlist** to see tickers approaching breakout levels |
| 7. | Run **Backtest** to validate the strategy on historical data |

---

### The Turtle Rules (Summary)

**System 1** - Short-Term Trend
- Enter: Close breaks above/below the **20-day** high/low
- Exit: Close breaks opposite the **10-day** high/low
- Filter: Skip if the previous System 1 trade on this ticker was a winner

**System 2** - Long-Term Trend
- Enter: Close breaks above/below the **55-day** high/low
- Exit: Close breaks opposite the **20-day** high/low
- Filter: None - always take System 2 signals

**Stop-Loss**: Entry price +/- (2 x 20-day Wilder ATR)

**Position Size**: `floor(Account Equity x 1% / ATR)` shares

---
""")

col1, col2, col3 = st.columns(3)
with col1:
    st.info("**Today's Signals**\n\nSee new entry signals, exit alerts, and pyramid opportunities.")
with col2:
    st.info("**My Trades**\n\nLog your actual trades and monitor them in real time.")
with col3:
    st.info("**Settings**\n\nSet your account equity to get accurate position sizes.")
