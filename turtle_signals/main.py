"""
main.py — Daily scan orchestrator and CLI entry point.

Usage:
  python main.py                         # Run daily scan + print briefing
  python main.py scan                    # Run today's signal scan
  python main.py briefing                # Generate and send morning briefing
  python main.py monitor                 # Check open trades for alerts
  python main.py schedule                # Start APScheduler (9:30 AM ET daily)

  python main.py log-trade --ticker GLD --direction long \\
    --entry 215.40 --units 147 --stop 208.20 --system 2

  python main.py close-trade --id 3 --exit-price 220.50 --reason exit_signal
  python main.py trades                  # List all open trades
"""

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Ensure the project root is in the path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Core scan logic ───────────────────────────────────────────────────────────

def run_daily_scan(account_equity: float | None = None) -> dict:
    """
    Run the full daily signal scan across all configured tickers.

    Returns a dict with:
      entry_signals, exit_alerts, add_alerts, time_alerts, watchlist, open_trades
    """
    from config import TICKERS, INITIAL_CAPITAL
    from data.cache import load_all
    from signals.turtle_signals import compute_signals, compute_watchlist_proximity
    from signals.filters import apply_s1_filter
    from trades.database import init_db, save_signal, signals_already_saved
    from trades.monitor import monitor_all_trades, get_open_trade_summary
    from risk.portfolio_limits import get_portfolio_status

    init_db()
    equity = account_equity or INITIAL_CAPITAL
    today_str = str(date.today())

    logger.info("Starting daily scan for %s...", today_str)
    price_data = load_all(TICKERS, days=200)
    logger.info("Loaded price data for %d tickers.", len(price_data))

    all_entry_signals = []
    watchlist = []

    for ticker, df in price_data.items():
        # Check System 1 winner filter for this ticker
        filtered = apply_s1_filter(ticker, "entry_long")

        # Compute all signals
        sigs = compute_signals(ticker, df, account_equity=equity, prev_s1_was_winner=filtered)
        all_entry_signals.extend(sigs)

        # Save to DB (avoid duplicates)
        if not signals_already_saved(today_str):
            for sig in sigs:
                save_signal(
                    date=sig.date,
                    ticker=sig.ticker,
                    system=sig.system,
                    signal_type=sig.signal_type,
                    price=sig.price,
                    atr=sig.atr,
                    breakout_level=sig.breakout_level,
                    stop_loss=sig.stop_loss,
                    unit_size=sig.unit_size,
                    risk_amount=sig.risk_amount,
                    reason=sig.reason,
                )

        # Watchlist proximity
        prox = compute_watchlist_proximity(ticker, df)
        if prox:
            watchlist.append(prox)

    # Sort watchlist by closest proximity
    watchlist.sort(
        key=lambda w: max(w.get("s1_long_proximity") or 0, w.get("s2_long_proximity") or 0),
        reverse=True,
    )

    # Monitor open trades for alerts
    monitor_alerts = monitor_all_trades(price_data)
    exit_alerts = [a for a in monitor_alerts if a.alert_type == "exit_signal"]
    add_alerts = [a for a in monitor_alerts if a.alert_type == "pyramid"]
    time_alerts = [a for a in monitor_alerts if a.alert_type == "time_exit"]
    stop_alerts = [a for a in monitor_alerts if a.alert_type == "stop_loss"]

    # Get enriched open trade data
    open_trades = get_open_trade_summary(price_data)

    entry_count = len([s for s in all_entry_signals if "entry" in s.signal_type and not s.filtered])
    logger.info(
        "Scan complete: %d entry signals, %d exit alerts, %d add alerts, "
        "%d time warnings, %d stop alerts",
        entry_count, len(exit_alerts), len(add_alerts), len(time_alerts), len(stop_alerts),
    )

    # Urgent stop-loss alerts via Telegram immediately
    if stop_alerts:
        from alerts.telegram_alert import send_urgent_alert
        for alert in stop_alerts:
            send_urgent_alert(alert.ticker, "stop_loss", alert.message)
            logger.warning("URGENT: Stop-loss breach on %s!", alert.ticker)

    return {
        "entry_signals": all_entry_signals,
        "exit_alerts": exit_alerts,
        "add_alerts": add_alerts,
        "time_alerts": time_alerts,
        "stop_alerts": stop_alerts,
        "watchlist": watchlist,
        "open_trades": open_trades,
    }


def send_morning_briefing(scan_results: dict, account_equity: float | None = None):
    """Generate and send the full morning briefing."""
    from config import INITIAL_CAPITAL
    from alerts.briefing import generate_briefing
    from alerts.telegram_alert import send_morning_briefing as tg_send
    from alerts.email_alert import send_morning_briefing as email_send

    equity = account_equity or INITIAL_CAPITAL

    plain_text, markdown = generate_briefing(
        entry_signals=scan_results["entry_signals"],
        exit_alerts=scan_results["exit_alerts"],
        add_alerts=scan_results["add_alerts"],
        time_alerts=scan_results["time_alerts"],
        watchlist=scan_results["watchlist"],
        open_trades=scan_results["open_trades"],
        account_equity=equity,
    )

    print("\n" + plain_text + "\n")

    # Send via Telegram
    tg_ok = tg_send(markdown)
    if tg_ok:
        logger.info("Morning briefing sent via Telegram.")
    else:
        logger.info("Telegram not configured or unavailable — briefing printed to console only.")

    # Send via email
    email_ok = email_send(plain_text)
    if email_ok:
        logger.info("Morning briefing sent via email.")

    return plain_text, markdown


# ── CLI commands ──────────────────────────────────────────────────────────────

def cmd_scan(args):
    """Run today's scan and print a summary."""
    results = run_daily_scan()
    entry_sigs = [s for s in results["entry_signals"] if "entry" in s.signal_type and not s.filtered]

    print(f"\n{'='*50}")
    print(f"TURTLE SCAN — {date.today()}")
    print(f"{'='*50}")

    if entry_sigs:
        print(f"\n🟢 {len(entry_sigs)} Entry Signal(s):")
        for sig in entry_sigs:
            direction = "LONG" if sig.signal_type == "entry_long" else "SHORT"
            print(f"  {sig.ticker} — {direction} (S{sig.system}) @ ${sig.price:.2f} | Stop: ${sig.stop_loss:.2f} | {sig.unit_size} shares")
    else:
        print("\nNo new entry signals today.")

    if results["exit_alerts"]:
        print(f"\n🔴 {len(results['exit_alerts'])} Exit Alert(s):")
        for a in results["exit_alerts"]:
            print(f"  {a.ticker} — EXIT @ ${a.current_price:.2f}")

    if results["stop_alerts"]:
        print(f"\n🚨 {len(results['stop_alerts'])} STOP-LOSS BREACH(ES)!")
        for a in results["stop_alerts"]:
            print(f"  {a.ticker} — STOP HIT @ ${a.current_price:.2f}")

    print(f"\nRun 'python main.py briefing' for the full formatted report.")


def cmd_briefing(args):
    """Run scan and send full morning briefing."""
    from config import INITIAL_CAPITAL
    results = run_daily_scan()
    send_morning_briefing(results)


def cmd_monitor(args):
    """Check open trades for alerts (no new signal scan)."""
    from trades.monitor import monitor_all_trades
    alerts = monitor_all_trades()
    if not alerts:
        print("All open trades look healthy.")
    else:
        for a in alerts:
            print(f"\n{a.urgency.upper()}: {a.message}")


def cmd_trades(args):
    """List all open trades."""
    from trades.trade_log import list_open_trades
    list_open_trades()


def cmd_log_trade(args):
    """Log a new trade."""
    from trades.trade_log import cli_log_trade
    cli_log_trade(args)


def cmd_close_trade(args):
    """Close an existing trade."""
    from trades.trade_log import cli_close_trade
    cli_close_trade(args)


def cmd_schedule(args):
    """Start the APScheduler to run the daily briefing at 9:30 AM ET."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from config import BRIEFING_HOUR, BRIEFING_MINUTE, BRIEFING_TIMEZONE

    scheduler = BlockingScheduler()

    def daily_job():
        logger.info("Running scheduled daily briefing...")
        try:
            results = run_daily_scan()
            send_morning_briefing(results)
        except Exception as exc:
            logger.error("Scheduled job failed: %s", exc, exc_info=True)

    scheduler.add_job(
        daily_job,
        trigger=CronTrigger(
            hour=BRIEFING_HOUR,
            minute=BRIEFING_MINUTE,
            timezone=BRIEFING_TIMEZONE,
        ),
        id="morning_briefing",
        name="Daily Turtle Briefing",
        replace_existing=True,
    )

    print(f"\n🐢 Turtle Trader scheduler started.")
    print(f"   Daily briefing: {BRIEFING_HOUR:02d}:{BRIEFING_MINUTE:02d} {BRIEFING_TIMEZONE}")
    print(f"   Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nScheduler stopped.")


# ── Main entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🐢 Turtle Trader — Signal-Generation & Trade Advisory System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                   # Run scan + print briefing
  python main.py scan              # Quick scan summary
  python main.py briefing          # Full briefing + send alerts
  python main.py monitor           # Check open trades
  python main.py trades            # List open trades
  python main.py schedule          # Start daily scheduler (9:30 AM ET)
  python main.py log-trade --ticker GLD --direction long --entry 215.40 --units 147 --stop 208.20 --system 2
  python main.py close-trade --id 3 --exit-price 220.50 --reason exit_signal
        """,
    )

    subparsers = parser.add_subparsers(dest="command")

    # scan
    subparsers.add_parser("scan", help="Run today's signal scan")

    # briefing
    subparsers.add_parser("briefing", help="Generate and send morning briefing")

    # monitor
    subparsers.add_parser("monitor", help="Check open trades for alerts")

    # trades
    subparsers.add_parser("trades", help="List all open trades")

    # schedule
    subparsers.add_parser("schedule", help="Start the daily scheduler")

    # log-trade
    log_p = subparsers.add_parser("log-trade", help="Log a trade you've manually taken")
    log_p.add_argument("--ticker", required=True, help="Ticker symbol (e.g. GLD)")
    log_p.add_argument("--direction", required=True, choices=["long", "short"])
    log_p.add_argument("--entry", type=float, required=True, dest="entry", help="Entry price")
    log_p.add_argument("--units", type=int, required=True, help="Number of shares/units")
    log_p.add_argument("--stop", type=float, required=True, help="Stop-loss price")
    log_p.add_argument("--system", type=int, required=True, choices=[1, 2])
    log_p.add_argument("--notes", default="", help="Optional notes")

    # close-trade
    close_p = subparsers.add_parser("close-trade", help="Close an open trade")
    close_p.add_argument("--id", type=int, required=True, help="Trade ID from 'python main.py trades'")
    close_p.add_argument("--exit-price", type=float, required=True, dest="exit_price")
    close_p.add_argument(
        "--reason",
        default="manual",
        choices=["exit_signal", "stop_loss", "time_exit", "manual"],
    )

    args = parser.parse_args()

    dispatch = {
        "scan": cmd_scan,
        "briefing": cmd_briefing,
        "monitor": cmd_monitor,
        "trades": cmd_trades,
        "log-trade": cmd_log_trade,
        "close-trade": cmd_close_trade,
        "schedule": cmd_schedule,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        # Default: run scan and briefing
        logger.info("Running default scan + briefing...")
        results = run_daily_scan()
        send_morning_briefing(results)


if __name__ == "__main__":
    main()
