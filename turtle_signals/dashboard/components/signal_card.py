"""
dashboard/components/signal_card.py — Reusable Streamlit signal display component.

Renders a full trade advisory card for each signal with all details
the user needs to manually execute the trade.
"""

import streamlit as st
from signals.turtle_signals import Signal


def render_entry_signal_card(sig: Signal, account_equity: float, key_prefix: str = "") -> bool:
    """
    Render a complete entry signal card with all Turtle trade details.
    Returns True if the user clicked "Mark as Taken".
    """
    is_long = sig.signal_type == "entry_long"
    direction_label = "BUY LONG" if is_long else "SELL SHORT"
    direction_color = "#00c853" if is_long else "#f44336"
    direction_icon = "🟢" if is_long else "🔴"

    # Card container with border
    with st.container(border=True):
        col_title, col_badge = st.columns([3, 1])
        with col_title:
            st.markdown(
                f"### {direction_icon} **{sig.ticker}** — {direction_label}  "
                f"<span style='background:#1e3a5f;padding:4px 10px;border-radius:12px;"
                f"font-size:13px;color:#64b5f6'>System {sig.system}</span>",
                unsafe_allow_html=True,
            )
        with col_badge:
            if sig.filtered:
                st.warning("⚠️ FILTERED\n(prev S1 winner)")

        # Main trade details in two columns
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**📍 Entry Details**")
            st.markdown(f"- **Current Price:** `${sig.price:.2f}`")
            st.markdown(f"- **Breakout Level:** `${sig.breakout_level:.2f}`")
            st.markdown(f"- **Stop-Loss:** `${sig.stop_loss:.2f}`")
            st.markdown(
                f"  _(2 × ATR of `${sig.atr:.2f}` "
                f"{'below' if is_long else 'above'} entry)_"
            )
            st.markdown(f"- **Risk per Share:** `${sig.risk_amount:.2f}`")
            st.markdown(f"- **ATR (20-day):** `${sig.atr:.2f}`")

        with col2:
            st.markdown("**💰 Position Sizing**")
            st.markdown(f"- **Unit Size (1% risk):** `{sig.unit_size} shares`")
            st.markdown(f"- **Unit Size (2% risk):** `{sig.unit_size_2pct} shares`")
            st.markdown(f"- **Total Cost:** `~${sig.total_cost:,.2f}`")
            st.markdown(f"- **Max Risk:** `${sig.max_risk_dollars:,.2f}`  (1.0% of account)")
            pct_exposed = sig.total_cost / account_equity * 100
            st.markdown(f"- **% of Account:** `{pct_exposed:.1f}%`")

        # Sizing breakdown expander
        with st.expander("📐 Position Sizing Calculation (Step-by-Step)"):
            st.code(
                f"Account Equity       = ${account_equity:,.2f}\n"
                f"Risk per Trade       = 1.0%\n"
                f"Dollar Risk Budget   = ${account_equity:,.2f} × 1% = ${sig.max_risk_dollars:,.2f}\n"
                f"\n"
                f"ATR (20-day Wilder)  = ${sig.atr:.2f}\n"
                f"Stop Multiplier      = 2×\n"
                f"Stop Distance        = 2 × ${sig.atr:.2f} = ${sig.risk_amount:.2f}\n"
                f"\n"
                f"Unit Size = floor(${sig.max_risk_dollars:,.2f} ÷ ${sig.atr:.2f}) = {sig.unit_size} shares\n"
                f"Total Cost = {sig.unit_size} × ${sig.price:.2f} = ${sig.total_cost:,.2f}\n"
                f"Stop Loss  = ${sig.price:.2f} {'−' if is_long else '+'} ${sig.risk_amount:.2f} = ${sig.stop_loss:.2f}",
                language="text",
            )

        # Reason
        st.info(f"📌 **Reason:** {sig.reason}")

        # Pyramid levels
        if sig.pyramid_levels:
            st.markdown("**📈 Pyramid Add Levels** (add units as price moves in your favor):")
            pyramid_cols = st.columns(len(sig.pyramid_levels))
            for i, (col, lvl) in enumerate(zip(pyramid_cols, sig.pyramid_levels), 1):
                with col:
                    st.metric(
                        label=f"Unit {i + 1}",
                        value=f"${lvl:.2f}",
                        delta=f"+{(lvl - sig.price) / sig.price * 100:.1f}%" if is_long
                              else f"{(lvl - sig.price) / sig.price * 100:.1f}%",
                    )

        # Action button
        taken = st.button(
            f"✅ Mark as Taken — Log {sig.ticker} {direction_label}",
            key=f"{key_prefix}_{sig.ticker}_{sig.signal_type}_{sig.system}",
            type="primary",
            use_container_width=True,
        )
        return taken


def render_exit_signal_card(alert, key_prefix: str = "") -> bool:
    """
    Render an exit alert card for an open trade.
    Returns True if user clicks "Close Trade".
    """
    pnl_color = "normal" if alert.pnl_estimate >= 0 else "inverse"
    pnl_icon = "🟢" if alert.pnl_estimate >= 0 else "🔴"

    with st.container(border=True):
        st.markdown(
            f"### 🔴 **{alert.ticker}** — EXIT {alert.direction.upper()}"
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Your Entry", f"${alert.entry_price:.2f}")
            st.markdown(f"_Opened {alert.days_open} days ago_")
        with col2:
            st.metric("Current Price", f"${alert.current_price:.2f}")
        with col3:
            st.metric(
                "Est. P&L",
                f"${alert.pnl_estimate:+,.2f}",
                delta=f"{alert.pnl_estimate / (alert.entry_price * alert.units) * 100:+.2f}%"
                if alert.entry_price * alert.units > 0 else None,
                delta_color=pnl_color,
            )

        st.error(f"**{alert.message.split(chr(10))[0]}**")

        return st.button(
            f"🔴 Close This Trade — {alert.ticker}",
            key=f"{key_prefix}_close_{alert.trade_id}",
            use_container_width=True,
        )


def render_pyramid_card(alert, key_prefix: str = "") -> bool:
    """Render an add-to-position (pyramid) alert card."""
    with st.container(border=True):
        st.markdown(f"### ⚠️  **{alert.ticker}** — ADD UNIT {alert.units + 1}")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Entry Price", f"${alert.entry_price:.2f}")
        with col2:
            st.metric("Current Price", f"${alert.current_price:.2f}")
        with col3:
            if alert.new_stop:
                st.metric("New Stop", f"${alert.new_stop:.2f}")

        st.warning(alert.message)

        return st.button(
            f"⚠️  Add Unit — {alert.ticker}",
            key=f"{key_prefix}_add_{alert.trade_id}",
        )


def render_time_exit_card(alert) -> None:
    """Render a time-based exit warning card."""
    change_pct = abs(alert.current_price - alert.entry_price) / alert.entry_price * 100
    with st.container(border=True):
        st.markdown(f"### ⏰ **{alert.ticker}** — Consider Exiting ({alert.days_open} days open)")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Your Entry", f"${alert.entry_price:.2f}")
        with col2:
            st.metric("Current Price", f"${alert.current_price:.2f}", delta=f"+{change_pct:.2f}%")
        with col3:
            st.metric("Days Open", str(alert.days_open))

        st.warning(
            f"No trend has developed after {alert.days_open} days "
            f"(only {change_pct:.1f}% price movement). "
            f"Consider closing this position."
        )
