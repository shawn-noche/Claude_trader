"""
tests/test_position_sizer.py — Tests for position sizing calculations.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from risk.position_sizer import (
    calculate_position_size,
    recalculate_stop_after_pyramid,
    SizingBreakdown,
)
from config import STOP_ATR_MULTIPLIER, MAX_PYRAMID_UNITS


class TestCalculatePositionSize:
    def test_basic_long_sizing(self):
        """Standard 1% risk long position at $100 with $2 ATR."""
        result = calculate_position_size(
            ticker="TEST",
            direction="long",
            entry_price=100.0,
            atr=2.0,
            account_equity=100_000,
            risk_pct=0.01,
        )
        assert isinstance(result, SizingBreakdown)
        # Unit size = floor(100000 * 0.01 / 2.0) = 500
        assert result.unit_size == 500
        # Stop = 100 - 2*2 = 96
        assert result.stop_loss == pytest.approx(96.0)
        # Total cost = 500 * 100 = 50000
        assert result.total_cost == pytest.approx(50_000.0)

    def test_basic_short_sizing(self):
        """Short position stop should be ABOVE entry."""
        result = calculate_position_size(
            ticker="TEST",
            direction="short",
            entry_price=100.0,
            atr=2.0,
            account_equity=100_000,
            risk_pct=0.01,
        )
        # Stop = 100 + 2*2 = 104
        assert result.stop_loss == pytest.approx(104.0)
        assert result.stop_loss > result.entry_price

    def test_dollar_risk_budget(self):
        """Dollar risk budget = equity × risk_pct."""
        result = calculate_position_size(
            ticker="TEST",
            direction="long",
            entry_price=50.0,
            atr=1.0,
            account_equity=50_000,
            risk_pct=0.01,
        )
        assert result.dollar_risk_budget == pytest.approx(500.0)

    def test_max_risk_is_one_percent(self):
        """At default risk, max loss should be 1% of equity."""
        equity = 100_000
        result = calculate_position_size(
            ticker="TEST",
            direction="long",
            entry_price=100.0,
            atr=2.0,
            account_equity=equity,
            risk_pct=0.01,
        )
        assert result.max_risk_dollars == pytest.approx(equity * 0.01)

    def test_aggressive_2pct_larger_than_1pct(self):
        """2% risk should give a larger unit than 1% risk."""
        r1 = calculate_position_size("T", "long", 100.0, 2.0, 100_000, 0.01)
        r2 = calculate_position_size("T", "long", 100.0, 2.0, 100_000, 0.02)
        assert r2.unit_size == r1.unit_size * 2

    def test_larger_atr_gives_smaller_unit(self):
        """Higher volatility (ATR) should reduce position size."""
        r_small = calculate_position_size("T", "long", 100.0, 1.0, 100_000, 0.01)
        r_large = calculate_position_size("T", "long", 100.0, 4.0, 100_000, 0.01)
        assert r_small.unit_size > r_large.unit_size

    def test_pyramid_levels_count(self):
        """Should have exactly MAX_PYRAMID_UNITS pyramid levels."""
        result = calculate_position_size("T", "long", 100.0, 2.0, 100_000, 0.01)
        assert len(result.pyramid_levels) == MAX_PYRAMID_UNITS

    def test_long_pyramid_ascending(self):
        """Long pyramid levels should increase."""
        result = calculate_position_size("T", "long", 100.0, 2.0, 100_000, 0.01)
        levels = result.pyramid_levels
        assert levels == sorted(levels), f"Expected ascending: {levels}"

    def test_short_pyramid_descending(self):
        """Short pyramid levels should decrease."""
        result = calculate_position_size("T", "short", 100.0, 2.0, 100_000, 0.01)
        levels = result.pyramid_levels
        assert levels == sorted(levels, reverse=True), f"Expected descending: {levels}"

    def test_explanation_contains_key_values(self):
        """The explanation string should mention key values."""
        result = calculate_position_size("GLD", "long", 215.0, 3.6, 100_000, 0.01)
        assert "100,000" in result.explanation or "100000" in result.explanation
        assert "1.0%" in result.explanation
        assert "GLD" in result.explanation

    def test_account_pct_exposed(self):
        """% of account exposed = total_cost / equity."""
        result = calculate_position_size("T", "long", 100.0, 2.0, 100_000, 0.01)
        expected_pct = result.total_cost / 100_000 * 100
        assert result.account_pct_exposed == pytest.approx(expected_pct, rel=0.01)

    def test_zero_atr_gives_zero_units(self):
        """Zero ATR is undefined — should return 0 units."""
        result = calculate_position_size("T", "long", 100.0, 0.0, 100_000, 0.01)
        assert result.unit_size == 0

    def test_stop_distance_is_two_atr(self):
        """Stop distance should always be exactly STOP_ATR_MULTIPLIER × ATR."""
        atr = 3.5
        result = calculate_position_size("T", "long", 100.0, atr, 100_000, 0.01)
        assert result.stop_distance == pytest.approx(STOP_ATR_MULTIPLIER * atr)


class TestRecalculateStopAfterPyramid:
    def test_long_stop_below_latest_entry(self):
        """After pyramid add, new stop should be below the latest entry price."""
        units = [(100.0, 2.0), (101.0, 2.0), (102.0, 2.0)]
        new_stop = recalculate_stop_after_pyramid(units, "long")
        # Stop = latest_entry - 2 * latest_atr = 102 - 4 = 98
        assert new_stop == pytest.approx(98.0)
        assert new_stop < units[-1][0]

    def test_short_stop_above_latest_entry(self):
        """After pyramid add short, stop should be above latest entry."""
        units = [(100.0, 2.0), (99.0, 2.0)]
        new_stop = recalculate_stop_after_pyramid(units, "short")
        # Stop = latest_entry + 2 * atr = 99 + 4 = 103
        assert new_stop == pytest.approx(103.0)
        assert new_stop > units[-1][0]

    def test_empty_units_returns_zero(self):
        result = recalculate_stop_after_pyramid([], "long")
        assert result == 0.0
