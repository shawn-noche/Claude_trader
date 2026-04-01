"""
dashboard/pages/1_signals.py — Today's Signals page.

Shows all entry signals, exit alerts, pyramid opportunities, and
approaching breakouts computed by today's scan.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date

import streamlit as st
import pandas as pd

from config import TICKERS, INITIAL_CAPITAL
from data.cache import load_all
from signals.turtle_signals import compute_signals, compute_watchlist_proximity
from signals.filters import apply_s1_filter
from trades.database import init_db, get_signals_for_date, save_signal
from trades.monitor import monitor_all_trades
from trades.trade_log import log_new_trade
from risk.portfolio_limits import get_portfolio_status
from dashboard.components.signal_card import (
    render_entry_signal_card, render_exit_signal_card,
    render_pyramid_card, render_time_exit_card,
)
from dashboard.components.charts import portfolio_gauge

st.set_page_config(
    page_title="Turtle Signals — Today's Signals",
    page_icon="🐢",
    layout="wide",
)

init_db()


@st.cache_data(ttl=300)   # Cache for 5 minutes
def load_signals(account_equity: float):
    """Fetch prices and compute all signals for today."""
    tickers = st.session_state.get("tickers", TICKERS)
    price_data = load_all(tickers, days=200)

    entry_signals = []
    watchlist = []

    for ticker, df in price_data.items():
        filtered = apply_s1_filter(ticker, "entry_long")
        sigs = compute_signals(
            ticker, df,
            account_equity=account_equity,
            prev_s1_was_winner=filtered,
        )
        entry_signals.extend(sigs)

        # Watchlist proximity
        prox = compute_watchlist_proximity(ticker, df)
        if prox:
            watchlist.append(prox)

    # Sort watchlist by closest proximity
    watchlist.sort(
        key=lambda w: max(w.get("s1_long_proximity") or 0, w.get("s2_long_proximity") or 0),
        reverse=True,
    )

    monitor_alerts = monitor_all_trades(price_data)
    return entry_signals, monitor_alerts, watchlist, price_data


# ── Page header ───────────────────────────────────────────────────────────────
st.title("🐢 Turtle Trader — Today's Signals")
st.caption(f"📅 {date.today().strftime('%A, %B %d, %Y')} | Daily morning scan")

account_equity = st.session_state.get("account_equity", INITIAL_CAPITAL)

# Refresh button
col_refresh, col_equity = st.columns([1, 3])
with col_refresh:
    if st.button("🔄 Refresh Signals", type="primary"):
        st.cache_data.clear()
        st.rerun()
with col_equity:
    st.info(f"Account Equity: **${account_equity:,.2f}** | Adjust in Settings ⚙️")

# Portfolio summary bar
portfolio = get_portfolio_status()
col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Total Units", f"{portfolio.total_units} / {portfolio.max_total}")
col_b.metric("Long Units", str(portfolio.long_units))
col_c.metric("Short Units", str(portfolio.short_units))
col_d.metric("Available", str(portfolio.available_units))

st.divider()

# Load signals
with st.spinner("Computing Turtle signals..."):
    all_signals, monitor_alerts, watchlist, price_data = load_signals(account_equity)

# Separate signal types
entry_signals = [s for s in all_signals if "entry" in s.signal_type]
exit_signals_gen = [s for s in all_signals if "exit" in s.signal_type]

# Separate monitor alert types
exit_alerts = [a for a in monitor_alerts if a.alert_type == "exit_signal"]
add_alerts = [a for a in monitor_alerts if a.alert_type == "pyramid"]
time_alerts = [a for a in monitor_alerts if a.alert_type == "time_exit"]
stop_alerts = [a for a in monitor_alerts if a.alert_type == "stop_loss"]

# URGENT: Stop-loss alerts shown prominently
if stop_alerts:
    st.error("## 🚨 URGENT — STOP-LOSS BREACHED")
    for alert in stop_alerts:
        st.error(alert.message)
    st.divider()

# ── Section 1: New Entry Signals ──────────────────────────────────────────────
unfiltered = [s for s in entry_signals if not s.filtered]
filtered = [s for s in entry_signals if s.filtered]

st.header(f"🟢 New Entry Signals ({len(unfiltered)} signals — act today)")

if not unfiltered:
    st.info("No new entry signals today. Check back tomorrow morning.")
else:
    for i, sig in enumerate(unfiltered):
        taken = render_entry_signal_card(sig, account_equity, key_prefix=f"s{i}")
        if taken:
            st.session_state[f"prefill_{sig.ticker}"] = {
                "ticker": sig.ticker,
                "direction": "long" if sig.signal_type == "entry_long" else "short",
                "entry_price": sig.price,
                "units": sig.unit_size,
                "stop_loss": sig.stop_loss,
                "system": sig.system,
            }
            st.success(f"✅ Pre-filled trade form for {sig.ticker}. Go to My Trades page to confirm.")

if filtered:
    with st.expander(f"⚠️  {len(filtered)} signal(s) filtered by System 1 winner rule"):
        for sig in filtered:
            direction = "LONG" if sig.signal_type == "entry_long" else "SHORT"
            st.warning(
                f"**{sig.ticker}** — {direction} (System {sig.system}) — "
                f"SKIPPED: previous System 1 trade on this ticker was profitable. "
                f"Turtle rule: don't chase a trend that was already captured."
            )

st.divider()

# ── Section 2: Exit Alerts ────────────────────────────────────────────────────
st.header(f"🔴 Exit Alerts ({len(exit_alerts)} trades to close)")

if not exit_alerts:
    st.success("All open trades look healthy — no exit signals triggered.")
else:
    for i, alert in enumerate(exit_alerts):
        closed = render_exit_signal_card(alert, key_prefix=f"e{i}")
        if closed:
            st.session_state[f"close_trade_{alert.trade_id}"] = True
            st.warning(f"Go to My Trades page to confirm closing {alert.ticker}.")

st.divider()

# ── Section 3: Add-to-Position Alerts ─────────────────────────────────────────
st.header(f"⚠️  Add-to-Position Alerts ({len(add_alerts)})")

if not add_alerts:
    st.info("No pyramid add opportunities today.")
else:
    for i, alert in enumerate(add_alerts):
        render_pyramid_card(alert, key_prefix=f"a{i}")

st.divider()

# ── Section 4: Time-Based Exit Warnings ──────────────────────────────────────
st.header(f"⏰ Time-Based Exit Warnings ({len(time_alerts)})")

if not time_alerts:
    st.info("No stagnant trades to flag.")
else:
    for alert in time_alerts:
        render_time_exit_card(alert)

st.divider()

# ── Section 5: Approaching Breakouts ─────────────────────────────────────────
threshold = 0.85
close_ones = [
    w for w in watchlist
    if max(w.get("s1_long_proximity") or 0, w.get("s2_long_proximity") or 0) >= threshold
]

st.header(f"👀 Approaching Breakout — Watch These ({len(close_ones)})")

if not close_ones:
    st.info("No tickers within 85% of a breakout level right now.")
else:
    rows = []
    for w in close_ones[:15]:
        s1_prox = w.get("s1_long_proximity") or 0
        s2_prox = w.get("s2_long_proximity") or 0
        best_prox = max(s1_prox, s2_prox)
        best_system = "System 2" if s2_prox >= s1_prox else "System 1"
        best_level = (
            w.get("s2_long_level") if s2_prox >= s1_prox else w.get("s1_long_level")
        ) or 0
        pct_away = (
            w.get("s2_long_pct_away") if s2_prox >= s1_prox else w.get("s1_long_pct_away")
        ) or 0

        rows.append({
            "Ticker": w["ticker"],
            "Current $": f"${w['current_price']:.2f}",
            "System": best_system,
            "Breakout Level": f"${best_level:.2f}",
            "% Away": f"+{abs(pct_away):.1f}%",
            "Proximity": f"{best_prox * 100:.0f}%",
            "ATR": f"${w['atr']:.2f}",
            "Potential Stop": f"${w.get('potential_stop_long', 0):.2f}"
            if w.get("potential_stop_long") else "—",
        })

    wl_df = pd.DataFrame(rows)
    st.dataframe(wl_df, use_container_width=True, hide_index=True)
