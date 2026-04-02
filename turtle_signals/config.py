"""
config.py — Central configuration for the Turtle Trading Signal System.
All parameters are adjustable here or via the Streamlit Settings page.
"""

import os
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "cache"
DB_PATH = BASE_DIR / "trades" / "turtle.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ─── System 1 (Short-Term Trend) ─────────────────────────────────────────────
SYSTEM1_ENTRY = 20        # 20-day breakout for entry
SYSTEM1_EXIT = 10         # 10-day breakout for exit
SYSTEM1_MAX_DAYS = 10     # Time-based exit after 10 days with no movement
SYSTEM1_ENABLED = True

# ─── System 2 (Long-Term Trend) ──────────────────────────────────────────────
SYSTEM2_ENTRY = 55        # 55-day breakout for entry
SYSTEM2_EXIT = 20         # 20-day breakout for exit
SYSTEM2_MAX_DAYS = 14     # Time-based exit after 14 days with no movement
SYSTEM2_ENABLED = True

# ─── ATR (Average True Range) ────────────────────────────────────────────────
ATR_PERIOD = 20           # Wilder's smoothing, 20-day ATR

# ─── Position Sizing ───────────────────────────────────────────────────────────────────
INITIAL_CAPITAL = 100_000.0   # Default account equity (update in Settings)
RISK_PER_TRADE = 0.01         # 1% risk per unit (default)
MAX_RISK_PER_TRADE = 0.02     # 2% risk per unit (aggressive variant)

# ─── Portfolio Limits ───────────────────────────────────────────────────────────────────
MAX_UNITS_PER_INSTRUMENT = 4   # Max units in a single ticker
MAX_UNITS_TOTAL = 12           # Max total units across all positions
MAX_UNITS_SAME_DIRECTION = 6   # Max units all long or all short

# ─── Pyramiding ──────────────────────────────────────────────────────────────────────────
PYRAMID_STEP_ATR = 0.5        # Add 1 unit every 0.5 × ATR in profit
MAX_PYRAMID_UNITS = 4         # Maximum pyramid adds per trade

# ─── Time-Based Exit ───────────────────────────────────────────────────────────────────
TIME_EXIT_THRESHOLD = 0.005   # Less than 0.5% movement triggers time-exit warning

# ─── Stop-Loss ──────────────────────────────────────────────────────────────────────────
STOP_ATR_MULTIPLIER = 2.0     # Stop = Entry ± (2 × ATR)

# ─── Universe / Ticker Selection ─────────────────────────────────────────────
# Options:
#   "russell2000"  — scan all ~2,000 Russell 2000 small-cap stocks (downloaded
#                    automatically from iShares IWM and cached for 7 days)
#   "custom"       — use the TICKERS list below
UNIVERSE = "russell2000"

# Used when UNIVERSE = "custom"
TICKERS = [
    "SPY", "QQQ", "IWM",
    "GLD", "SLV", "USO", "DBA",
    "TLT", "IEF",
    "FXE", "FXY", "UUP",
    "VNQ", "IAU",
]

# ─── Breakout Proximity Alert ─────────────────────────────────────────────────────────
BREAKOUT_PROXIMITY_THRESHOLD = 0.95   # Alert when 95% of the way to breakout

# ─── Cache TTL ──────────────────────────────────────────────────────────────────────────
CACHE_TTL_HOURS = 24   # Re-fetch data after 24 hours

# ─── Scheduler ──────────────────────────────────────────────────────────────────────────
BRIEFING_HOUR = 9       # 9:30 AM ET
BRIEFING_MINUTE = 30
BRIEFING_TIMEZONE = "America/New_York"

# ─── Telegram (loaded from .env) ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Email (loaded from .env) ───────────────────────────────────────────────────────────────────
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")

# ─── Minimum price data history required ───────────────────────────────────────────────
MIN_HISTORY_DAYS = 120   # Need at least 120 days for System 2 signals
