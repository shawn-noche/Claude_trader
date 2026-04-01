"""
dashboard/pages/2_my_trades.py — My Open Trades page.

Shows all manually logged trades with real-time P&L, exit alerts,
and controls to log new trades and close existing ones.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date

import pandas as pd
import streamlit as st

from config import TICKERS, INITIAL_CAPITAL
from data.cache import load_all
from trades.database import init_db, get_all_trades, get_open_trades
from trades.monitor import get_open_trade_summary
from trades.trade_log import log_new_trade, close_existing_trade
from trades.database import save_equity_snapshot, get_equity_history
from dashboard.components.charts import equity_curve_chart

st.set_page_config(
    page_title="Turtle Signals — My Trades",
    page_icon="🐢",
    layout="wide",
)

init_db()

account_equity = st.session_state.get("account_equity", INITIAL_CAPITAL)

st.title("📋 My Open Trades")
st.caption("Log your trades and monitor them in real time.")

# ── Log New Trade Form ─────────────────────────────────────────────────────────
with st.expander("➕ Log a New Trade", expanded=bool(st.session_state.get("show_log_form", False))):
    # Check if pre-filled from signals page
    prefill_key = None
    for key in st.session_state:
        if key.startswith("prefill_"):
            prefill_key = key
            break

    prefill = st.session_state.get(prefill_key, {}) if prefill_key else {}

    with st.form("log_trade_form", clear_on_submit=True):
        st.subheader("New Trade Entry")
        col1, col2, col3 = st.columns(3)

        with col1:
            ticker_input = st.selectbox(
                "Ticker",
                options=TICKERS,
                index=TICKERS.index(prefill.get("ticker", TICKERS[0]))
                      if prefill.get("ticker") in TICKERS else 0,
            )
            direction_input = st.radio(
                "Direction",
                options=["long", "short"],
                index=0 if prefill.get("direction", "long") == "long" else 1,
                horizontal=True,
            )

        with col2:
            entry_price_input = st.number_input(
                "Entry Price ($)",
                min_value=0.01,
                value=float(prefill.get("entry_price", 100.0)),
                step=0.01,
                format="%.2f",
            )
            units_input = st.number_input(
                "Units (Shares)",
                min_value=1,
                value=int(prefill.get("units", 100)),
                step=1,
            )

        with col3:
            stop_input = st.number_input(
                "Stop-Loss ($)",
                min_value=0.01,
                value=float(prefill.get("stop_loss", 95.0)),
                step=0.01,
                format="%.2f",
            )
            system_input = st.selectbox(
                "System",
                options=[1, 2],
                index=int(prefill.get("system", 1)) - 1,
                format_func=lambda x: f"System {x}",
            )

        entry_date_input = st.date_input("Entry Date", value=date.today())
        notes_input = st.text_area("Notes (optional)", height=60)

        submitted = st.form_submit_button("✅ Log Trade", type="primary", use_container_width=True)

        if submitted:
            try:
                trade_id = log_new_trade(
                    ticker=ticker_input,
                    direction=direction_input,
                    entry_price=entry_price_input,
                    units=units_input,
                    stop_loss=stop_input,
                    system=system_input,
                    entry_date=str(entry_date_input),
                    notes=notes_input,
                )
                st.success(
                    f"✅ Trade logged! ID: {trade_id} | "
                    f"{direction_input.upper()} {units_input} {ticker_input} @ ${entry_price_input:.2f}"
                )
                # Clear prefill
                if prefill_key:
                    del st.session_state[prefill_key]
                st.rerun()
            except ValueError as e:
                st.error(f"❌ Invalid trade data: {e}")

st.divider()

# ── Open Trades Table ─────────────────────────────────────────────────────────
st.subheader("Open Positions")

with st.spinner("Loading current prices..."):
    tickers = st.session_state.get("tickers", TICKERS)
    price_data = load_all(tickers, days=200)
    open_summaries = get_open_trade_summary(price_data)

if not open_summaries:
    st.info("No open trades logged. Use the form above to log a trade you've taken.")
else:
    # Summary metrics
    total_pnl = sum(t["unrealized_pnl"] for t in open_summaries)
    total_exposure = sum(t["current_price"] * t["units"] for t in open_summaries)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Open Trades", len(open_summaries))
    col2.metric("Total Unrealized P&L", f"${total_pnl:+,.2f}",
                delta_color="normal" if total_pnl >= 0 else "inverse")
    col3.metric("Total Exposure", f"${total_exposure:,.2f}")
    col4.metric("% of Account", f"{total_exposure / account_equity * 100:.1f}%")

    st.divider()

    # Render each trade as a row with close button
    for trade in open_summaries:
        pnl = trade["unrealized_pnl"]
        is_profitable = pnl >= 0

        # Color the row background
        row_color = "rgba(0,200,83,0.08)" if is_profitable else "rgba(244,67,54,0.08)"
        pnl_icon = "🟢" if is_profitable else "🔴"

        with st.container(border=True):
            col_head, col_close = st.columns([5, 1])

            with col_head:
                st.markdown(
                    f"**{pnl_icon} {trade['ticker']}** — "
                    f"{trade['direction'].upper()} | System {trade['system']} | "
                    f"Opened {trade['entry_date']} ({trade['days_open']} days ago)"
                )

            with col_close:
                close_clicked = st.button(
                    "Close",
                    key=f"close_btn_{trade['id']}",
                    type="secondary",
                )

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Entry Price", f"${trade['entry_price']:.2f}")
            c2.metric("Current Price", f"${trade['current_price']:.2f}")
            c3.metric("Units", str(trade['units']))
            c4.metric("Stop-Loss", f"${trade['stop_loss']:.2f}")
            c5.metric(
                "Unrealized P&L",
                f"${pnl:+,.2f}",
                delta=f"{pnl / (trade['entry_price'] * trade['units']) * 100:+.2f}%"
                if trade['entry_price'] * trade['units'] > 0 else None,
                delta_color="normal" if is_profitable else "inverse",
            )
            c6.metric("Pyramid Units", f"{trade['current_units']} / 4")

            if trade.get("notes"):
                st.caption(f"📝 {trade['notes']}")

            # Stop breached warning
            if trade["direction"] == "long" and trade["current_price"] <= trade["stop_loss"]:
                st.error("🚨 STOP-LOSS BREACHED — EXIT IMMEDIATELY")
            elif trade["direction"] == "short" and trade["current_price"] >= trade["stop_loss"]:
                st.error("🚨 STOP-LOSS BREACHED — EXIT IMMEDIATELY")

            # Close trade dialog
            if close_clicked or st.session_state.get(f"close_trade_{trade['id']}"):
                st.session_state[f"show_close_{trade['id']}"] = True

            if st.session_state.get(f"show_close_{trade['id']}"):
                with st.form(key=f"close_form_{trade['id']}"):
                    st.markdown(f"**Close {trade['ticker']} trade (ID: {trade['id']})**")
                    exit_price = st.number_input(
                        "Exit Price ($)",
                        min_value=0.01,
                        value=float(trade["current_price"]),
                        step=0.01,
                        format="%.2f",
                        key=f"exit_price_{trade['id']}",
                    )
                    exit_reason = st.selectbox(
                        "Exit Reason",
                        options=["exit_signal", "stop_loss", "time_exit", "manual"],
                        key=f"exit_reason_{trade['id']}",
                    )
                    confirm = st.form_submit_button("✅ Confirm Close", use_container_width=True)
                    if confirm:
                        close_existing_trade(trade["id"], exit_price, exit_reason)
                        st.session_state.pop(f"show_close_{trade['id']}", None)
                        st.session_state.pop(f"close_trade_{trade['id']}", None)
                        st.success(f"Trade {trade['id']} closed.")
                        st.rerun()

st.divider()

# ── Closed Trades History ─────────────────────────────────────────────────────
st.subheader("Trade History (Closed Trades)")

all_trades = get_all_trades()
closed = [dict(t) for t in all_trades if t["status"] == "closed"]

if not closed:
    st.info("No closed trades yet.")
else:
    closed_df = pd.DataFrame(closed)
    display_cols = [
        "ticker", "direction", "system", "entry_date", "entry_price",
        "units", "exit_date", "exit_price", "exit_reason", "pnl"
    ]
    available_cols = [c for c in display_cols if c in closed_df.columns]
    closed_df = closed_df[available_cols].copy()
    closed_df.columns = [c.replace("_", " ").title() for c in closed_df.columns]

    # Color P&L column
    st.dataframe(
        closed_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Pnl": st.column_config.NumberColumn("P&L ($)", format="$%.2f"),
            "Entry Price": st.column_config.NumberColumn(format="$%.2f"),
            "Exit Price": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    total_realized = sum(t.get("pnl") or 0 for t in closed)
    st.metric("Total Realized P&L", f"${total_realized:+,.2f}")

# ── Equity Curve ──────────────────────────────────────────────────────────────
st.subheader("Account Equity Curve")

# Save today's snapshot
total_open_pnl = sum(t["unrealized_pnl"] for t in open_summaries) if open_summaries else 0
total_closed_pnl = sum(t.get("pnl") or 0 for t in closed) if closed else 0
current_equity = account_equity + total_closed_pnl
save_equity_snapshot(str(date.today()), current_equity, total_open_pnl)

equity_history = get_equity_history()
if equity_history:
    eq_df = pd.DataFrame([dict(r) for r in equity_history])
    st.plotly_chart(
        equity_curve_chart(eq_df, account_equity),
        use_container_width=True,
    )
else:
    st.info("Equity curve will appear after you log and close some trades.")
