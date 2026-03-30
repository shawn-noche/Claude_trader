"""backtest/report.py — Format backtest performance results for display."""

import pandas as pd


def format_report(result: dict) -> str:
    lines = [
        "=" * 52,
        f"  TURTLE TRADING BACKTEST REPORT - {result['ticker']}",
        "=" * 52,
        f"  Period         : {result['start_date']}  to  {result['end_date']}",
        f"  Initial Capital: ${result['initial_capital']:>12,.2f}",
        f"  Final Value    : ${result['final_value']:>12,.2f}",
        "",
        "  RETURNS",
        "  " + "-" * 40,
        f"  Total Return   : {result['total_return_pct']:>+8.2f}%",
        f"  CAGR           : {result['cagr_pct']:>+8.2f}%  (annualized)",
        f"  Sharpe Ratio   : {result['sharpe_ratio']:>8.3f}",
        f"  Max Drawdown   : {result['max_drawdown_pct']:>8.2f}%",
        "",
        "  TRADE STATISTICS",
        "  " + "-" * 40,
        f"  Total Trades   : {result['total_trades']:>8}",
        f"  Won            : {result['won_trades']:>8}",
        f"  Lost           : {result['lost_trades']:>8}",
        f"  Win Rate       : {result['win_rate_pct']:>8.1f}%",
        f"  Avg Win        : ${result['avg_win']:>10,.2f}",
        f"  Avg Loss       : ${result['avg_loss']:>10,.2f}",
        f"  Profit Factor  : {result['profit_factor']:>8.2f}",
        "=" * 52,
    ]
    return "\n".join(lines)


def trades_to_dataframe(result: dict) -> pd.DataFrame:
    trades = result.get("completed_trades", [])
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    if df.empty:
        return df
    rename = {
        "open_date": "Entry Date", "close_date": "Exit Date",
        "direction": "Direction", "system": "System",
        "entry_price": "Entry $", "exit_price": "Exit $",
        "pnl": "P&L ($)", "pnl_pct": "P&L (%)",
    }
    cols = [c for c in rename if c in df.columns]
    df = df[cols].rename(columns=rename)
    for col in ["P&L ($)", "P&L (%)", "Entry $", "Exit $"]:
        if col in df.columns:
            df[col] = df[col].round(2)
    return df
