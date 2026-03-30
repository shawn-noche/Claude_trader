"""backtest/backtest_engine.py — Run the Turtle Trading backtest using Backtrader."""

import logging
from typing import Optional

import backtrader as bt
import pandas as pd

from backtest.turtle_strategy import TurtleStrategy
from config import INITIAL_CAPITAL, RISK_PER_TRADE

logger = logging.getLogger(__name__)


def run_backtest(
    df: pd.DataFrame,
    ticker: str = "Asset",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = INITIAL_CAPITAL,
    risk_pct: float = RISK_PER_TRADE,
    use_system1: bool = True,
    use_system2: bool = True,
    apply_s1_filter: bool = True,
    verbose: bool = False,
) -> dict:
    if start_date:
        df = df[df.index >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df.index <= pd.to_datetime(end_date)]

    if len(df) < 60:
        logger.warning("Insufficient data for backtest (%d rows)", len(df))
        return _empty_result(ticker, initial_capital)

    cerebro = bt.Cerebro(stdstats=False)
    data_feed = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data_feed, name=ticker)
    cerebro.addstrategy(
        TurtleStrategy,
        s1_entry=20, s1_exit=10,
        s2_entry=55, s2_exit=20,
        atr_period=20,
        risk_pct=risk_pct,
        stop_multiplier=2.0,
        use_system1=use_system1,
        use_system2=use_system2,
        apply_s1_filter=apply_s1_filter,
        verbose=verbose,
    )
    cerebro.broker.setcash(initial_capital)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        riskfreerate=0.04, annualize=True, timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns", timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade_stats")
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_returns")

    try:
        results = cerebro.run()
    except Exception as exc:
        logger.error("Backtest failed: %s", exc)
        return _empty_result(ticker, initial_capital)

    strat = results[0]
    final_value = cerebro.broker.getvalue()

    sharpe_raw = strat.analyzers.sharpe.get_analysis()
    sharpe = sharpe_raw.get("sharperatio") or 0.0

    dd_analysis = strat.analyzers.drawdown.get_analysis()
    max_drawdown_pct = dd_analysis.get("max", {}).get("drawdown", 0.0)

    trade_stats = strat.analyzers.trade_stats.get_analysis()
    total_trades = trade_stats.get("total", {}).get("closed", 0)
    won_trades = trade_stats.get("won", {}).get("total", 0)
    lost_trades = trade_stats.get("lost", {}).get("total", 0)
    avg_win = trade_stats.get("won", {}).get("pnl", {}).get("average", 0.0)
    avg_loss = trade_stats.get("lost", {}).get("pnl", {}).get("average", 0.0)
    total_won_pnl = trade_stats.get("won", {}).get("pnl", {}).get("total", 0.0)
    total_lost_pnl = trade_stats.get("lost", {}).get("pnl", {}).get("total", 0.0)

    win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0.0
    profit_factor = abs(total_won_pnl / total_lost_pnl) if total_lost_pnl != 0 else float("inf")
    total_return_pct = ((final_value - initial_capital) / initial_capital) * 100

    years = len(df) / 252.0
    cagr = ((final_value / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0.0

    time_returns = strat.analyzers.time_returns.get_analysis()
    equity_curve = _build_equity_curve(time_returns, initial_capital)

    return {
        "ticker": ticker,
        "start_date": str(df.index[0].date()) if len(df) > 0 else "",
        "end_date": str(df.index[-1].date()) if len(df) > 0 else "",
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "total_trades": total_trades,
        "won_trades": won_trades,
        "lost_trades": lost_trades,
        "win_rate_pct": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "completed_trades": strat.completed_trades,
        "equity_curve": equity_curve,
    }


def _build_equity_curve(time_returns: dict, initial_capital: float) -> pd.DataFrame:
    if not time_returns:
        return pd.DataFrame(columns=["date", "equity"])
    dates = sorted(time_returns.keys())
    equity = initial_capital
    rows = []
    for dt in dates:
        equity *= (1 + time_returns[dt])
        rows.append({"date": dt, "equity": round(equity, 2)})
    return pd.DataFrame(rows)


def _empty_result(ticker: str, initial_capital: float) -> dict:
    return {
        "ticker": ticker, "start_date": "", "end_date": "",
        "initial_capital": initial_capital, "final_value": initial_capital,
        "total_return_pct": 0.0, "cagr_pct": 0.0, "sharpe_ratio": 0.0,
        "max_drawdown_pct": 0.0, "total_trades": 0, "won_trades": 0,
        "lost_trades": 0, "win_rate_pct": 0.0, "avg_win": 0.0,
        "avg_loss": 0.0, "profit_factor": 0.0, "completed_trades": [],
        "equity_curve": pd.DataFrame(columns=["date", "equity"]),
    }
