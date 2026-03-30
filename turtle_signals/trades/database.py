"""
trades/database.py — SQLite database setup and connection management.

Schema:
  signals         — every computed signal with full details
  my_trades       — trades I manually logged
  equity_snapshots — daily equity curve tracking
"""

import sqlite3
import logging
from pathlib import Path

from config import DB_PATH

logger = logging.getLogger(__name__)

CREATE_SIGNALS_TABLE = """
CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT    NOT NULL,
    ticker        TEXT    NOT NULL,
    system        INTEGER NOT NULL,
    signal_type   TEXT    NOT NULL,
    price         REAL,
    atr           REAL,
    breakout_level REAL,
    stop_loss     REAL,
    unit_size     INTEGER,
    risk_amount   REAL,
    reason        TEXT
);
"""

CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS my_trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT    NOT NULL,
    system        INTEGER NOT NULL,
    direction     TEXT    NOT NULL,
    entry_date    TEXT    NOT NULL,
    entry_price   REAL    NOT NULL,
    units         INTEGER NOT NULL,
    stop_loss     REAL    NOT NULL,
    current_units INTEGER DEFAULT 1,
    status        TEXT    DEFAULT 'open',
    exit_date     TEXT,
    exit_price    REAL,
    exit_reason   TEXT,
    pnl           REAL,
    notes         TEXT
);
"""

CREATE_EQUITY_TABLE = """
CREATE TABLE IF NOT EXISTS equity_snapshots (
    date          TEXT PRIMARY KEY,
    cash_equity   REAL,
    open_pnl      REAL,
    total_equity  REAL
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_signals_date   ON signals(date);",
    "CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);",
    "CREATE INDEX IF NOT EXISTS idx_trades_ticker  ON my_trades(ticker);",
    "CREATE INDEX IF NOT EXISTS idx_trades_status  ON my_trades(status);",
]


def get_db() -> sqlite3.Connection:
    """
    Open and return a SQLite connection.
    Rows are returned as sqlite3.Row (dict-like access by column name).
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrency
    return conn


def init_db() -> None:
    """Create all tables and indexes if they don't exist yet."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        conn.execute(CREATE_SIGNALS_TABLE)
        conn.execute(CREATE_TRADES_TABLE)
        conn.execute(CREATE_EQUITY_TABLE)
        for idx_sql in CREATE_INDEXES:
            conn.execute(idx_sql)
        conn.commit()
        logger.info("Database initialized at %s", DB_PATH)
    finally:
        conn.close()


# ─── Signal persistence ─────────────────────────────────────────────

def save_signal(
    date: str,
    ticker: str,
    system: int,
    signal_type: str,
    price: float,
    atr: float,
    breakout_level: float,
    stop_loss: float,
    unit_size: int,
    risk_amount: float,
    reason: str,
) -> int:
    """Insert a signal into the database. Returns the new row id."""
    conn = get_db()
    try:
        cur = conn.execute(
            """
            INSERT INTO signals
              (date, ticker, system, signal_type, price, atr,
               breakout_level, stop_loss, unit_size, risk_amount, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (date, ticker, system, signal_type, price, atr,
             breakout_level, stop_loss, unit_size, risk_amount, reason),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_signals_for_date(date: str) -> list[sqlite3.Row]:
    """Retrieve all signals for a specific date."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM signals WHERE date = ? ORDER BY system, signal_type",
            (date,),
        ).fetchall()
    finally:
        conn.close()


def signals_already_saved(date: str) -> bool:
    """Check if signals have already been computed for today (avoids duplicates)."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM signals WHERE date = ?", (date,)
        ).fetchone()
        return row["cnt"] > 0
    finally:
        conn.close()


# ─── Trade persistence ──────────────────────────────────────────────

def log_trade(
    ticker: str,
    system: int,
    direction: str,
    entry_date: str,
    entry_price: float,
    units: int,
    stop_loss: float,
    notes: str = "",
) -> int:
    """Insert a new trade into my_trades. Returns the new row id."""
    conn = get_db()
    try:
        cur = conn.execute(
            """
            INSERT INTO my_trades
              (ticker, system, direction, entry_date, entry_price,
               units, stop_loss, current_units, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, system, direction, entry_date, entry_price,
             units, stop_loss, units, notes),
        )
        conn.commit()
        logger.info("Logged trade: %s %s %d units @ %.2f", direction.upper(), ticker, units, entry_price)
        return cur.lastrowid
    finally:
        conn.close()


def close_trade(
    trade_id: int,
    exit_date: str,
    exit_price: float,
    exit_reason: str,
) -> None:
    """Mark a trade as closed and calculate P&L."""
    conn = get_db()
    try:
        trade = conn.execute(
            "SELECT * FROM my_trades WHERE id = ?", (trade_id,)
        ).fetchone()
        if trade is None:
            logger.warning("Trade id %d not found", trade_id)
            return

        direction = trade["direction"]
        entry_price = trade["entry_price"]
        units = trade["units"]

        if direction == "long":
            pnl = (exit_price - entry_price) * units
        else:
            pnl = (entry_price - exit_price) * units

        conn.execute(
            """
            UPDATE my_trades
            SET status = 'closed',
                exit_date = ?,
                exit_price = ?,
                exit_reason = ?,
                pnl = ?
            WHERE id = ?
            """,
            (exit_date, exit_price, exit_reason, round(pnl, 2), trade_id),
        )
        conn.commit()
        logger.info(
            "Closed trade %d: %s @ %.2f \u2192 P&L $%.2f", trade_id, exit_reason, exit_price, pnl
        )
    finally:
        conn.close()


def update_trade_stop(trade_id: int, new_stop: float) -> None:
    """Update the stop-loss on an open trade (after pyramid add)."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE my_trades SET stop_loss = ? WHERE id = ?",
            (new_stop, trade_id),
        )
        conn.commit()
    finally:
        conn.close()


def add_pyramid_unit(trade_id: int) -> None:
    """Increment current_units by 1 to track a pyramid add."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE my_trades SET current_units = current_units + 1 WHERE id = ?",
            (trade_id,),
        )
        conn.commit()
    finally:
        conn.close()


def get_open_trades() -> list[sqlite3.Row]:
    """Return all open trades."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM my_trades WHERE status = 'open' ORDER BY entry_date",
        ).fetchall()
    finally:
        conn.close()


def get_all_trades() -> list[sqlite3.Row]:
    """Return all trades (open and closed)."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM my_trades ORDER BY entry_date DESC",
        ).fetchall()
    finally:
        conn.close()


def get_trade_by_id(trade_id: int) -> sqlite3.Row | None:
    """Fetch a single trade by its ID."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM my_trades WHERE id = ?", (trade_id,)
        ).fetchone()
    finally:
        conn.close()


# ─── Equity snapshots ───────────────────────────────────────────────

def save_equity_snapshot(date: str, cash_equity: float, open_pnl: float) -> None:
    """Save or update today's equity snapshot."""
    total = cash_equity + open_pnl
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO equity_snapshots (date, cash_equity, open_pnl, total_equity)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
              cash_equity = excluded.cash_equity,
              open_pnl    = excluded.open_pnl,
              total_equity = excluded.total_equity
            """,
            (date, cash_equity, open_pnl, total),
        )
        conn.commit()
    finally:
        conn.close()


def get_equity_history() -> list[sqlite3.Row]:
    """Return the full equity snapshot history, ordered by date."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM equity_snapshots ORDER BY date"
        ).fetchall()
    finally:
        conn.close()
