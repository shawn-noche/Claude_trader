"""
dashboard/pages/3_watchlist.py — Watchlist / Approaching Breakout page.

Shows all tickers sorted by how close they are to triggering a signal.
Useful for planning ahead and monitoring near-breakout candidates.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

from config import TICKERS, INITIAL_CAPITAL, BREAKOUT_PROXIMITY_THRESHOLD
from data.cache import load_all
from signals.turtle_signals import compute_watchlist_proximity
from signals.atr import latest_atr
from dashboard.components.charts import price_chart

st.set_page_config(
    page_title="Turtle Signals — Watchlist",
    page_icon="🐢",
    layout="wide",
)

st.title("👀 Watchlist — Approaching Breakouts")
st.caption(
    "Tickers sorted by how close they are to triggering a Turtle entry signal. "
    "Refresh to update with latest prices."
)

# Refresh control
col_btn, col_thresh = st.columns([1, 3])
with col_btn:
    if st.button("🔄 Refresh Watchlist", type="primary"):
        st.cache_data.clear()
        st.rerun()
with col_thresh:
    threshold = st.slider(
        "Show tickers ≥ X% proximity to breakout",
        min_value=50, max_value=99, value=70, step=5, format="%d%%",
    ) / 100

# Load all price data
tickers = st.session_state.get("tickers", TICKERS)

with st.spinner("Loading price data and computing proximity levels..."):
    price_data = load_all(tickers, days=200)

# Compute proximity for all tickers
all_watchlist = []
for ticker, df in price_data.items():
    prox = compute_watchlist_proximity(ticker, df)
    if prox:
        all_watchlist.append(prox)

# Sort by best proximity
all_watchlist.sort(
    key=lambda w: max(w.get("s1_long_proximity") or 0, w.get("s2_long_proximity") or 0),
    reverse=True,
)

# Filter by threshold
filtered = [
    w for w in all_watchlist
    if max(w.get("s1_long_proximity") or 0, w.get("s2_long_proximity") or 0) >= threshold
]

st.info(f"Showing {len(filtered)} tickers within {threshold * 100:.0f}% of a breakout level.")

# ── Main Table ────────────────────────────────────────────────────────────────
if not filtered:
    st.warning("No tickers are near breakout levels at the current threshold. Lower the slider to see more.")
else:
    rows = []
    for w in filtered:
        s1_prox = w.get("s1_long_proximity") or 0
        s2_prox = w.get("s2_long_proximity") or 0

        rows.append({
            "Ticker": w["ticker"],
            "Current $": w["current_price"],
            "S1 Long Breakout": w.get("s1_long_level"),
            "S1 % Away": w.get("s1_long_pct_away"),
            "S2 Long Breakout": w.get("s2_long_level"),
            "S2 % Away": w.get("s2_long_pct_away"),
            "ATR": w.get("atr"),
            "S1 Proximity %": round(s1_prox * 100, 1),
            "S2 Proximity %": round(s2_prox * 100, 1),
            "Potential Stop (Long)": w.get("potential_stop_long"),
        })

    df_table = pd.DataFrame(rows)

    st.dataframe(
        df_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Current $": st.column_config.NumberColumn(format="$%.2f"),
            "S1 Long Breakout": st.column_config.NumberColumn("S1 Breakout", format="$%.2f"),
            "S1 % Away": st.column_config.NumberColumn("S1 % Away", format="+%.2f%%"),
            "S2 Long Breakout": st.column_config.NumberColumn("S2 Breakout", format="$%.2f"),
            "S2 % Away": st.column_config.NumberColumn("S2 % Away", format="+%.2f%%"),
            "ATR": st.column_config.NumberColumn("ATR ($)", format="$%.2f"),
            "S1 Proximity %": st.column_config.ProgressColumn(
                "S1 Proximity", min_value=0, max_value=100, format="%.0f%%"
            ),
            "S2 Proximity %": st.column_config.ProgressColumn(
                "S2 Proximity", min_value=0, max_value=100, format="%.0f%%"
            ),
            "Potential Stop (Long)": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

# ── Detailed Ticker Charts ────────────────────────────────────────────────────
st.divider()
st.subheader("Price Chart — Deep Dive")

if filtered:
    selected_ticker = st.selectbox(
        "Select ticker for detailed chart:",
        options=[w["ticker"] for w in filtered],
    )

    if selected_ticker and selected_ticker in price_data:
        df = price_data[selected_ticker]
        prox_data = next((w for w in all_watchlist if w["ticker"] == selected_ticker), {})

        fig = price_chart(
            df.tail(120),
            selected_ticker,
            s1_high=prox_data.get("s1_long_level"),
            s1_low=prox_data.get("s1_short_level"),
            s2_high=prox_data.get("s2_long_level"),
            s2_low=prox_data.get("s2_short_level"),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Key stats
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Current Price", f"${prox_data.get('current_price', 0):.2f}")
        col2.metric("ATR (20d)", f"${prox_data.get('atr', 0):.2f}")

        s1_away = prox_data.get("s1_long_pct_away")
        if s1_away is not None:
            col3.metric(
                f"S1 Breakout (${prox_data.get('s1_long_level', 0):.2f})",
                f"+{abs(s1_away):.1f}% away",
            )

        s2_away = prox_data.get("s2_long_pct_away")
        if s2_away is not None:
            col4.metric(
                f"S2 Breakout (${prox_data.get('s2_long_level', 0):.2f})",
                f"+{abs(s2_away):.1f}% away",
            )
else:
    st.info("No tickers meet the current proximity threshold.")

# ── Full Watchlist Table ──────────────────────────────────────────────────────
st.divider()
with st.expander("📊 Full Watchlist (All Tickers)"):
    all_rows = []
    for w in all_watchlist:
        s1_prox = w.get("s1_long_proximity") or 0
        s2_prox = w.get("s2_long_proximity") or 0
        all_rows.append({
            "Ticker": w["ticker"],
            "Price": w["current_price"],
            "S1 Long": w.get("s1_long_level"),
            "S1 % Away": w.get("s1_long_pct_away"),
            "S2 Long": w.get("s2_long_level"),
            "S2 % Away": w.get("s2_long_pct_away"),
            "ATR": w.get("atr"),
            "S1 Prox %": round(s1_prox * 100, 1),
            "S2 Prox %": round(s2_prox * 100, 1),
        })
    full_df = pd.DataFrame(all_rows)
    st.dataframe(
        full_df, use_container_width=True, hide_index=True,
        column_config={
            "Price": st.column_config.NumberColumn(format="$%.2f"),
            "S1 Long": st.column_config.NumberColumn(format="$%.2f"),
            "S2 Long": st.column_config.NumberColumn(format="$%.2f"),
            "ATR": st.column_config.NumberColumn(format="$%.2f"),
            "S1 % Away": st.column_config.NumberColumn(format="+%.2f%%"),
            "S2 % Away": st.column_config.NumberColumn(format="+%.2f%%"),
            "S1 Prox %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
            "S2 Prox %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
        },
    )
