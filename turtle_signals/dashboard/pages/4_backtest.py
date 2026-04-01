"""
dashboard/pages/4_backtest.py — Backtest Results page.

Run the full Turtle Trading strategy on historical data and view
comprehensive performance metrics, equity curve, and trade list.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config import TICKERS, INITIAL_CAPITAL, RISK_PER_TRADE
from data.fetcher import fetch_ohlcv
from backtest.backtest_engine import run_backtest
from backtest.report import format_report, trades_to_dataframe
from dashboard.components.charts import equity_curve_chart, drawdown_chart, pnl_distribution_chart

st.set_page_config(
    page_title="Turtle Signals — Backtest",
    page_icon="🐢",
    layout="wide",
)

st.title("📊 Backtest — Turtle Trading Strategy")
st.caption(
    "Run a historical backtest of the Turtle Trading strategy on any ticker. "
    "Uses exact Turtle rules: Donchian channels, Wilder ATR stops, and 1% unit sizing."
)

# ── Backtest Configuration ────────────────────────────────────────────────────
with st.form("backtest_form"):
    st.subheader("Backtest Parameters")

    col1, col2, col3 = st.columns(3)

    with col1:
        bt_ticker = st.selectbox("Ticker", options=TICKERS, index=0)
        bt_capital = st.number_input(
            "Initial Capital ($)",
            min_value=1000.0,
            value=float(INITIAL_CAPITAL),
            step=1000.0,
        )

    with col2:
        bt_start = st.date_input(
            "Start Date",
            value=date.today() - timedelta(days=5 * 365),
        )
        bt_end = st.date_input("End Date", value=date.today())

    with col3:
        bt_risk = st.slider("Risk per Trade (%)", 0.5, 2.0, float(RISK_PER_TRADE * 100), 0.1) / 100
        bt_systems = st.multiselect(
            "Systems to Test",
            options=["System 1", "System 2"],
            default=["System 1", "System 2"],
        )

    col4, col5 = st.columns(2)
    with col4:
        apply_filter = st.checkbox("Apply System 1 Winner Filter", value=True)
    with col5:
        verbose = st.checkbox("Verbose Trade Output", value=False)

    run_btn = st.form_submit_button("▶️  Run Backtest", type="primary", use_container_width=True)

# ── Run Backtest ──────────────────────────────────────────────────────────────
if run_btn:
    with st.spinner(f"Running Turtle backtest on {bt_ticker}..."):
        # Fetch historical data
        days_needed = (bt_end - bt_start).days + 120
        df = fetch_ohlcv(bt_ticker, days=days_needed, end_date=bt_end)

        if df is None or df.empty:
            st.error(f"Could not fetch data for {bt_ticker}. Try a different ticker.")
        else:
            use_s1 = "System 1" in bt_systems
            use_s2 = "System 2" in bt_systems

            result = run_backtest(
                df=df,
                ticker=bt_ticker,
                start_date=str(bt_start),
                end_date=str(bt_end),
                initial_capital=bt_capital,
                risk_pct=bt_risk,
                use_system1=use_s1,
                use_system2=use_s2,
                apply_s1_filter=apply_filter,
                verbose=verbose,
            )

            st.session_state["last_backtest"] = result

# ── Display Results ───────────────────────────────────────────────────────────
result = st.session_state.get("last_backtest")

if result:
    st.divider()
    st.subheader(f"Results — {result['ticker']}  |  {result['start_date']} → {result['end_date']}")

    # Top-line metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Total Return",
        f"{result['total_return_pct']:+.2f}%",
        delta=f"${result['final_value'] - result['initial_capital']:+,.0f}",
    )
    col2.metric("CAGR", f"{result['cagr_pct']:+.2f}%")
    col3.metric("Sharpe Ratio", f"{result['sharpe_ratio']:.3f}")
    col4.metric("Max Drawdown", f"-{result['max_drawdown_pct']:.2f}%")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Total Trades", str(result["total_trades"]))
    col6.metric("Win Rate", f"{result['win_rate_pct']:.1f}%")
    col7.metric("Avg Win", f"${result['avg_win']:,.2f}")
    col8.metric("Profit Factor", f"{result['profit_factor']:.2f}")

    # Full text report
    with st.expander("📋 Full Performance Report"):
        st.code(format_report(result), language="text")

    st.divider()

    # Equity curve
    col_eq, col_dd = st.columns(2)
    with col_eq:
        if not result["equity_curve"].empty:
            st.plotly_chart(
                equity_curve_chart(result["equity_curve"], result["initial_capital"]),
                use_container_width=True,
            )
        else:
            st.info("Equity curve unavailable for this run.")

    with col_dd:
        if not result["equity_curve"].empty:
            st.plotly_chart(
                drawdown_chart(result["equity_curve"]),
                use_container_width=True,
            )

    # Trade list
    st.divider()
    st.subheader("Individual Trades")

    trades_df = trades_to_dataframe(result)
    if not trades_df.empty:
        # P&L distribution chart
        st.plotly_chart(pnl_distribution_chart(trades_df), use_container_width=True)

        # Color-code winning vs losing trades
        def row_style(row):
            if "P&L ($)" in row and row["P&L ($)"] >= 0:
                return ["background-color: rgba(0,200,83,0.1)"] * len(row)
            return ["background-color: rgba(244,67,54,0.1)"] * len(row)

        styled = trades_df.style.apply(row_style, axis=1)
        st.dataframe(
            trades_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "P&L ($)": st.column_config.NumberColumn(format="$%.2f"),
                "P&L (%)": st.column_config.NumberColumn(format="%.2f%%"),
                "Entry $": st.column_config.NumberColumn(format="$%.2f"),
                "Exit $": st.column_config.NumberColumn(format="$%.2f"),
            },
        )
    else:
        st.info("No completed trades in this backtest period.")
else:
    # Instructions before first run
    st.info(
        "Configure the backtest parameters above and click **Run Backtest** to see results.\n\n"
        "The backtest uses the exact Turtle Trading rules:\n"
        "- **System 1**: 20-day breakout entry, 10-day exit, System 1 winner filter\n"
        "- **System 2**: 55-day breakout entry, 20-day exit, no filter\n"
        "- **Stop-Loss**: 2× ATR (Wilder's smoothing)\n"
        "- **Position Sizing**: 1% of equity ÷ ATR\n"
        "- **Commission**: 0.1% per trade\n"
    )
