"""
tests/test_monitor.py — Tests for trade monitoring logic.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from trades.monitor import (
    _check_exit_signal,
    _check_pyramid,
    monitor_all_trades,
)
from trades.database import init_db, log_trade, close_trade, get_db
from config import DB_PATH


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Use a temporary DB for each test to avoid cross-test pollution."""
    test_db = tmp_path / "test_turtle.db"
    monkeypatch.setattr("config.DB_PATH", test_db)
    monkeypatch.setattr("trades.database.DB_PATH", test_db)
    init_db()
    yield test_db


def make_price_df(n: int = 50, close_prices=None) -> pd.DataFrame:
    """Create a simple price DataFrame."""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    if close_prices is None:
        closes = [100.0] * n
    else:
        closes = list(close_prices)
        # Pad with flat prices if needed
        while len(closes) < n:
            closes.insert(0, closes[0])
    return pd.DataFrame(
        {
            "Open":  [c - 0.2 for c in closes],
            "High":  [c + 0.5 for c in closes],
            "Low":   [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [1_000_000] * n,
        },
        index=dates,
    )


# ── Exit Signal Tests ─────────────────────────────────────────────────────────

class TestCheckExitSignal:
    def test_long_no_exit_above_low(self):
        """Long position above the 10-day low should NOT trigger exit."""
        closes = [100.0] * 20 + [105.0] * 5   # price went up, no exit
        df = make_price_df(25, closes)
        result = _check_exit_signal("TEST", "long", 1, 105.0, {"TEST": df})
        assert result is None

    def test_long_exit_below_10day_low(self):
        """Long position breaking below the 10-day low should trigger System 1 exit."""
        # Create data where current price is below the 10-day low
        closes = [100.0] * 40 + [98.0]   # Last close is 98, 10-day low is ~100
        df = make_price_df(41, closes)
        # Override lows to make 10-day low = 99.5, current = 98
        df.iloc[-10:, df.columns.get_loc("Low")] = 99.5
        df.iloc[-1, df.columns.get_loc("Close")] = 97.0
        result = _check_exit_signal("TEST", "long", 1, 97.0, {"TEST": df})
        assert result is not None
        assert "low" in result.lower()

    def test_short_no_exit_below_high(self):
        """Short position below the 10-day high should NOT trigger exit."""
        closes = [100.0] * 25
        df = make_price_df(25, closes)
        result = _check_exit_signal("TEST", "short", 1, 95.0, {"TEST": df})
        assert result is None

    def test_short_exit_above_10day_high(self):
        """Short position breaking above the 10-day high should trigger exit."""
        closes = [100.0] * 40
        df = make_price_df(40, closes)
        df.iloc[-10:, df.columns.get_loc("High")] = 99.0
        result = _check_exit_signal("TEST", "short", 1, 102.0, {"TEST": df})
        assert result is not None

    def test_no_price_data_returns_none(self):
        """Missing price data should return None gracefully."""
        result = _check_exit_signal("MISSING", "long", 1, 100.0, {})
        assert result is None

    def test_system2_uses_20day_period(self):
        """System 2 exit uses 20-day period, not 10-day."""
        closes = [100.0] * 50
        df = make_price_df(50, closes)
        # With all prices flat at 100, current at 97 should trigger exit
        # (20-day low = 99.5 with our df construction)
        df.iloc[-20:, df.columns.get_loc("Low")] = 99.5
        result = _check_exit_signal("TEST", "long", 2, 97.0, {"TEST": df})
        assert result is not None


# ── Pyramid Check Tests ───────────────────────────────────────────────────────

class TestCheckPyramid:
    def test_no_pyramid_at_max_units(self):
        """When already at max units, no pyramid alert."""
        from config import MAX_PYRAMID_UNITS
        df = make_price_df(50)
        result = _check_pyramid(
            "TEST", "long", 100.0, 105.0,
            current_units=MAX_PYRAMID_UNITS,
            price_data={"TEST": df},
        )
        assert result is None

    def test_pyramid_triggered_long(self):
        """Long pyramid should trigger when price moves up by 0.5 ATR."""
        from config import PYRAMID_STEP_ATR
        closes = [100.0] * 50
        df = make_price_df(50, closes)
        # ATR ≈ 1.0 (High-Low spread is 1.0), step = 0.5 * 1.0 = 0.5
        # With current_units=1, trigger = entry + 1*0.5*ATR = entry + 0.5*ATR
        # Current price must be >= trigger
        entry_price = 100.0
        current_price = 101.5  # Well above trigger
        result = _check_pyramid(
            "TEST", "long", entry_price, current_price,
            current_units=1,
            price_data={"TEST": df},
        )
        assert result is not None
        assert "trigger_price" in result
        assert "new_stop" in result

    def test_pyramid_not_triggered_below_level(self):
        """No pyramid alert when price hasn't reached the add level."""
        closes = [100.0] * 50
        df = make_price_df(50, closes)
        entry_price = 100.0
        current_price = 100.1  # Barely above entry, nowhere near trigger
        result = _check_pyramid(
            "TEST", "long", entry_price, current_price,
            current_units=1,
            price_data={"TEST": df},
        )
        assert result is None

    def test_pyramid_stop_above_entry_for_long(self):
        """After pyramid add, new stop should be below latest entry."""
        closes = [100.0] * 50
        df = make_price_df(50, closes)
        result = _check_pyramid(
            "TEST", "long", 100.0, 102.0,
            current_units=1,
            price_data={"TEST": df},
        )
        if result:
            assert result["new_stop"] < 102.0


# ── Monitor All Trades Tests ──────────────────────────────────────────────────

class TestMonitorAllTrades:
    def test_no_open_trades_returns_empty(self):
        """No open trades → no alerts."""
        alerts = monitor_all_trades(price_data={})
        assert alerts == []

    def test_stop_loss_breach_detected(self):
        """When current price <= stop loss for long, urgent stop alert fires."""
        # Log a long trade
        entry_date = str((date.today() - timedelta(days=3)))
        trade_id = log_trade(
            ticker="TST",
            system=1,
            direction="long",
            entry_date=entry_date,
            entry_price=100.0,
            units=100,
            stop_loss=95.0,
        )

        # Price data: current close at 93.0 — below the 95.0 stop
        closes = [100.0] * 30 + [93.0]
        df = make_price_df(31, closes)

        alerts = monitor_all_trades(price_data={"TST": df})
        stop_alerts = [a for a in alerts if a.alert_type == "stop_loss"]

        assert len(stop_alerts) >= 1
        assert stop_alerts[0].urgency == "urgent"
        assert stop_alerts[0].ticker == "TST"

    def test_time_exit_warning(self):
        """Trade open for too many days with minimal movement should warn."""
        from config import SYSTEM1_MAX_DAYS
        # Open trade 12 days ago (exceeds System 1's 10-day limit)
        old_date = str(date.today() - timedelta(days=SYSTEM1_MAX_DAYS + 2))
        trade_id = log_trade(
            ticker="TST",
            system=1,
            direction="long",
            entry_date=old_date,
            entry_price=100.0,
            units=100,
            stop_loss=94.0,
        )

        # Current price barely moved (0.1% — below 0.5% threshold)
        closes = [100.0] * 30 + [100.1]
        df = make_price_df(31, closes)

        alerts = monitor_all_trades(price_data={"TST": df})
        time_alerts = [a for a in alerts if a.alert_type == "time_exit"]

        assert len(time_alerts) >= 1
        assert time_alerts[0].ticker == "TST"

    def test_stop_sorted_before_time_exit(self):
        """Stop-loss alerts should appear before time-exit alerts (sorted by urgency)."""
        old_date = str(date.today() - timedelta(days=15))
        log_trade("TST", 1, "long", old_date, 100.0, 100, 94.0)

        closes_stop = [100.0] * 20 + [90.0]   # Stop hit
        df = make_price_df(21, closes_stop)

        alerts = monitor_all_trades(price_data={"TST": df})
        if len(alerts) >= 2:
            # First alert should be urgent
            assert alerts[0].urgency == "urgent"
