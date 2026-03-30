"""
trades/trade_log.py — Manual trade journal.

You log trades you actually take here. The system then monitors them
for exit signals, stop-loss breaches, and pyramid opportunities.

CLI usage:
  python main.py log-trade --ticker GLD --direction long \\
    --entry 215.40 --units 147 --stop 208.20 --system 2

The Streamlit form on the My Trades page calls log_trade() directly.
"""

import argparse
import logging
from datetime import date

from trades.database import log_trade, close_trade, get_open_trades, get_trade_by_id

logger = logging.getLogger(__name__)


def log_new_trade(
    ticker: str,
    direction: str,
    entry_price: float,
    units: int,
    stop_loss: float,
    system: int,
    entry_date: str | None = None,
    notes: str = "",
) -> int:
    """
    Record a trade that you have manually executed.

    Args:
        ticker:       Ticker symbol (e.g. 'GLD')
        direction:    'long' or 'short'
        entry_price:  Price at which you entered
        units:        Number of shares/units purchased
        stop_loss:    Your initial stop-loss price
        system:       1 or 2 (which Turtle system triggered this)
        entry_date:   ISO date string (defaults to today)
        notes:        Any free-form notes

    Returns:
        Database row id of the new trade.
    """
    direction = direction.lower().strip()
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got '{direction}'")
    if system not in (1, 2):
        raise ValueError(f"system must be 1 or 2, got {system}")
    if entry_price <= 0:
        raise ValueError(f"entry_price must be positive, got {entry_price}")
    if units <= 0:
        raise ValueError(f"units must be positive, got {units}")

    entry_date = entry_date or str(date.today())

    trade_id = log_trade(
        ticker=ticker.upper(),
        system=system,
        direction=direction,
        entry_date=entry_date,
        entry_price=entry_price,
        units=units,
        stop_loss=stop_loss,
        notes=notes,
    )

    print(f"\n\u2705 Trade logged successfully (ID: {trade_id})")
    print(f"   {direction.upper()} {units} {ticker.upper()} @ ${entry_price:.2f}")
    print(f"   System {system} | Stop: ${stop_loss:.2f}")
    print(f"   Monitor this trade with: python main.py monitor")

    return trade_id


def close_existing_trade(
    trade_id: int,
    exit_price: float,
    exit_reason: str = "manual",
    exit_date: str | None = None,
) -> None:
    """
    Mark a trade as closed with an exit price and reason.

    Args:
        trade_id:    The trade's database ID
        exit_price:  Price at which you exited
        exit_reason: 'exit_signal', 'stop_loss', 'time_exit', or 'manual'
        exit_date:   ISO date string (defaults to today)
    """
    exit_date = exit_date or str(date.today())
    trade = get_trade_by_id(trade_id)
    if trade is None:
        print(f"\u274c No trade found with ID {trade_id}")
        return

    close_trade(
        trade_id=trade_id,
        exit_date=exit_date,
        exit_price=exit_price,
        exit_reason=exit_reason,
    )

    direction = trade["direction"]
    entry_price = trade["entry_price"]
    units = trade["units"]
    ticker = trade["ticker"]

    if direction == "long":
        pnl = (exit_price - entry_price) * units
    else:
        pnl = (entry_price - exit_price) * units

    pnl_sign = "+" if pnl >= 0 else ""
    print(f"\n{'\u2705' if pnl >= 0 else '\U0001f534'} Trade {trade_id} closed")
    print(f"   {ticker} {direction.upper()} | Exit: ${exit_price:.2f}")
    print(f"   P&L: {pnl_sign}${pnl:,.2f}  ({exit_reason})")


def list_open_trades() -> None:
    """Print all open trades to the console."""
    trades = get_open_trades()
    if not trades:
        print("\nNo open trades logged.")
        return

    print("\n\U0001f4cb OPEN TRADES")
    print("=" * 80)
    print(f"{'ID':<4} {'Ticker':<8} {'Dir':<6} {'Sys':<4} {'Entry Date':<12} "
          f"{'Entry $':<10} {'Units':<6} {'Stop':<10} {'Notes'}")
    print("-" * 80)
    for t in trades:
        print(
            f"{t['id']:<4} {t['ticker']:<8} {t['direction'].upper():<6} "
            f"S{t['system']:<3} {t['entry_date']:<12} "
            f"${t['entry_price']:<9.2f} {t['units']:<6} "
            f"${t['stop_loss']:<9.2f} {t['notes'] or ''}"
        )


def cli_log_trade(args: argparse.Namespace) -> None:
    """Handle the 'log-trade' CLI sub-command."""
    log_new_trade(
        ticker=args.ticker,
        direction=args.direction,
        entry_price=args.entry,
        units=args.units,
        stop_loss=args.stop,
        system=args.system,
        notes=getattr(args, "notes", ""),
    )


def cli_close_trade(args: argparse.Namespace) -> None:
    """Handle the 'close-trade' CLI sub-command."""
    close_existing_trade(
        trade_id=args.id,
        exit_price=args.exit_price,
        exit_reason=getattr(args, "reason", "manual"),
    )
