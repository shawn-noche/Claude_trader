"""
dashboard/pages/5_settings.py — Settings page.

Adjust all Turtle Trading parameters without restarting the app.
Settings are stored in Streamlit session_state and applied immediately.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json

import streamlit as st

import config
from config import TICKERS, INITIAL_CAPITAL

SETTINGS_FILE = Path(__file__).parent.parent.parent / "user_settings.json"

st.set_page_config(
    page_title="Turtle Signals — Settings",
    page_icon="🐢",
    layout="wide",
)

st.title("⚙️  Settings")
st.caption("Adjust Turtle Trading parameters. Changes take effect immediately in this session.")


def load_saved_settings() -> dict:
    """Load previously saved settings from disk."""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {}


def save_settings(settings: dict) -> None:
    """Persist settings to disk so they survive restarts."""
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


# Load saved settings and inject into session state if not already set
saved = load_saved_settings()
for key, value in saved.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ── Account Settings ──────────────────────────────────────────────────────────
st.subheader("💰 Account Settings")

col1, col2 = st.columns(2)
with col1:
    new_equity = st.number_input(
        "Account Equity ($)",
        min_value=1000.0,
        value=float(st.session_state.get("account_equity", INITIAL_CAPITAL)),
        step=1000.0,
        help="Your total account value. Used for all position sizing calculations.",
    )
with col2:
    st.info(
        f"Current equity: **${new_equity:,.2f}**\n\n"
        f"1% risk = ${new_equity * 0.01:,.2f} per unit\n"
        f"2% risk = ${new_equity * 0.02:,.2f} per unit"
    )

st.divider()

# ── Risk Settings ─────────────────────────────────────────────────────────────
st.subheader("📊 Risk Management")

col1, col2 = st.columns(2)
with col1:
    new_risk = st.slider(
        "Risk per Trade (%)",
        min_value=0.5, max_value=2.0,
        value=float(st.session_state.get("risk_pct", config.RISK_PER_TRADE) * 100),
        step=0.1,
        format="%.1f%%",
        help="Percentage of account equity at risk per unit. Turtle default = 1%.",
    ) / 100

with col2:
    st.metric("Dollar Risk per Unit", f"${new_equity * new_risk:,.2f}")
    st.caption(f"At a typical ATR of $3.00, this gives ~{int(new_equity * new_risk / 3)} shares per unit")

st.divider()

# ── System Parameters ─────────────────────────────────────────────────────────
st.subheader("🐢 Turtle System Parameters")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**System 1 (Short-Term)**")
    s1_entry = st.slider(
        "System 1 Entry Period",
        min_value=10, max_value=40,
        value=int(st.session_state.get("s1_entry", config.SYSTEM1_ENTRY)),
        step=1,
        help="Days for System 1 breakout entry (original Turtle = 20)",
    )
    s1_exit = st.slider(
        "System 1 Exit Period",
        min_value=5, max_value=20,
        value=int(st.session_state.get("s1_exit", config.SYSTEM1_EXIT)),
        step=1,
        help="Days for System 1 exit (original Turtle = 10)",
    )
    s1_enabled = st.toggle(
        "Enable System 1 Signals",
        value=bool(st.session_state.get("s1_enabled", config.SYSTEM1_ENABLED)),
    )

with col2:
    st.markdown("**System 2 (Long-Term)**")
    s2_entry = st.slider(
        "System 2 Entry Period",
        min_value=30, max_value=100,
        value=int(st.session_state.get("s2_entry", config.SYSTEM2_ENTRY)),
        step=1,
        help="Days for System 2 breakout entry (original Turtle = 55)",
    )
    s2_exit = st.slider(
        "System 2 Exit Period",
        min_value=10, max_value=40,
        value=int(st.session_state.get("s2_exit", config.SYSTEM2_EXIT)),
        step=1,
        help="Days for System 2 exit (original Turtle = 20)",
    )
    s2_enabled = st.toggle(
        "Enable System 2 Signals",
        value=bool(st.session_state.get("s2_enabled", config.SYSTEM2_ENABLED)),
    )

st.divider()

# ── Ticker Watchlist ──────────────────────────────────────────────────────────
st.subheader("📋 Ticker Watchlist")

current_tickers = st.session_state.get("tickers", TICKERS)

new_tickers = st.multiselect(
    "Tickers to Track",
    options=TICKERS + ["SPX", "GDX", "XLE", "XLF", "EEM", "AGG", "BND"],
    default=current_tickers,
    help="Select which tickers to scan for signals.",
)

custom_ticker = st.text_input(
    "Add Custom Ticker (e.g. AAPL, TSLA):",
    placeholder="Enter Yahoo Finance ticker symbol",
)

if custom_ticker:
    custom_ticker = custom_ticker.upper().strip()
    if custom_ticker not in new_tickers:
        new_tickers = new_tickers + [custom_ticker]
        st.info(f"Added {custom_ticker} to watchlist (click Save to apply).")

st.divider()

# ── ATR Settings ──────────────────────────────────────────────────────────────
st.subheader("📈 ATR Settings")
atr_period = st.slider(
    "ATR Period (Wilder's Smoothing)",
    min_value=10, max_value=30,
    value=int(st.session_state.get("atr_period", config.ATR_PERIOD)),
    step=1,
    help="Wilder's ATR period for stop calculation. Original Turtle = 20.",
)

st.divider()

# ── Save Button ───────────────────────────────────────────────────────────────
col_save, col_reset = st.columns(2)

with col_save:
    if st.button("💾 Save Settings", type="primary", use_container_width=True):
        new_settings = {
            "account_equity": new_equity,
            "risk_pct": new_risk,
            "s1_entry": s1_entry,
            "s1_exit": s1_exit,
            "s1_enabled": s1_enabled,
            "s2_entry": s2_entry,
            "s2_exit": s2_exit,
            "s2_enabled": s2_enabled,
            "tickers": new_tickers,
            "atr_period": atr_period,
        }
        # Update session state
        for key, value in new_settings.items():
            st.session_state[key] = value

        # Persist to disk
        save_settings(new_settings)

        # Clear cached signals so they regenerate with new settings
        st.cache_data.clear()

        st.success("✅ Settings saved! Signal cache cleared — next scan will use new parameters.")
        st.balloons()

with col_reset:
    if st.button("🔄 Reset to Defaults", use_container_width=True):
        defaults = {
            "account_equity": INITIAL_CAPITAL,
            "risk_pct": config.RISK_PER_TRADE,
            "s1_entry": config.SYSTEM1_ENTRY,
            "s1_exit": config.SYSTEM1_EXIT,
            "s1_enabled": True,
            "s2_entry": config.SYSTEM2_ENTRY,
            "s2_exit": config.SYSTEM2_EXIT,
            "s2_enabled": True,
            "tickers": TICKERS,
            "atr_period": config.ATR_PERIOD,
        }
        for key, value in defaults.items():
            st.session_state[key] = value
        if SETTINGS_FILE.exists():
            SETTINGS_FILE.unlink()
        st.cache_data.clear()
        st.success("✅ Settings reset to defaults.")
        st.rerun()

# ── Current Settings Preview ──────────────────────────────────────────────────
st.divider()
with st.expander("👁️  Current Active Settings"):
    st.json({
        "account_equity": new_equity,
        "risk_pct": f"{new_risk * 100:.1f}%",
        "system_1": {
            "entry_period": s1_entry,
            "exit_period": s1_exit,
            "enabled": s1_enabled,
        },
        "system_2": {
            "entry_period": s2_entry,
            "exit_period": s2_exit,
            "enabled": s2_enabled,
        },
        "atr_period": atr_period,
        "tickers": new_tickers,
    })

# ── Alert Setup Guide ─────────────────────────────────────────────────────────
st.divider()
st.subheader("🔔 Alert Setup (Telegram & Email)")

with st.expander("How to set up Telegram alerts"):
    st.markdown("""
    **Step 1** — Create a Telegram Bot:
    1. Open Telegram and message `@BotFather`
    2. Send `/newbot` and follow the prompts
    3. Copy the **bot token** you receive

    **Step 2** — Get your Chat ID:
    1. Message `@userinfobot` on Telegram
    2. Copy your **chat ID** from the response

    **Step 3** — Configure `.env`:
    ```
    TELEGRAM_BOT_TOKEN=your_bot_token_here
    TELEGRAM_CHAT_ID=your_chat_id_here
    ```

    **Step 4** — Restart the app. Briefings will now send at 9:30 AM ET.
    """)

with st.expander("How to set up Email alerts (Gmail)"):
    st.markdown("""
    **Step 1** — Enable Gmail App Password:
    1. Go to **Google Account** → **Security** → **2-Step Verification** (enable it)
    2. Then go to **App Passwords** and create a new one for "Mail"

    **Step 2** — Configure `.env`:
    ```
    EMAIL_SMTP_HOST=smtp.gmail.com
    EMAIL_SMTP_PORT=587
    EMAIL_USERNAME=your_email@gmail.com
    EMAIL_PASSWORD=your_16_char_app_password
    EMAIL_RECIPIENT=your_email@gmail.com
    ```

    **Note:** Use the App Password, NOT your regular Gmail password.
    """)
