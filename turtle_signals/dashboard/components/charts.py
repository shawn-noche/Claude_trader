"""dashboard/components/charts.py — Plotly chart builders for the Streamlit dashboard."""

from typing import Optional
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def price_chart(
    df: pd.DataFrame,
    ticker: str,
    signals: Optional[list] = None,
    s1_high: Optional[float] = None,
    s1_low: Optional[float] = None,
    s2_high: Optional[float] = None,
    s2_low: Optional[float] = None,
) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.05, row_heights=[0.75, 0.25],
    )
    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            name=ticker, increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        ),
        row=1, col=1,
    )
    if s1_high is not None:
        fig.add_hline(y=s1_high, line_dash="dash", line_color="rgba(255,200,0,0.7)",
                      annotation_text=f"S1 High ${s1_high:.2f}", row=1, col=1)
    if s1_low is not None:
        fig.add_hline(y=s1_low, line_dash="dash", line_color="rgba(255,200,0,0.7)",
                      annotation_text=f"S1 Low ${s1_low:.2f}", row=1, col=1)
    if s2_high is not None:
        fig.add_hline(y=s2_high, line_dash="dot", line_color="rgba(100,200,255,0.7)",
                      annotation_text=f"S2 High ${s2_high:.2f}", row=1, col=1)
    if s2_low is not None:
        fig.add_hline(y=s2_low, line_dash="dot", line_color="rgba(100,200,255,0.7)",
                      annotation_text=f"S2 Low ${s2_low:.2f}", row=1, col=1)
    if signals:
        long_dates, long_prices, short_dates, short_prices = [], [], [], []
        for sig in signals:
            try:
                sig_date = pd.to_datetime(sig.date)
            except Exception:
                continue
            if sig.signal_type == "entry_long":
                long_dates.append(sig_date)
                long_prices.append(sig.price)
            elif sig.signal_type == "entry_short":
                short_dates.append(sig_date)
                short_prices.append(sig.price)
        if long_dates:
            fig.add_trace(go.Scatter(x=long_dates, y=long_prices, mode="markers",
                                     marker=dict(symbol="triangle-up", size=14, color="lime"),
                                     name="Entry Long"), row=1, col=1)
        if short_dates:
            fig.add_trace(go.Scatter(x=short_dates, y=short_prices, mode="markers",
                                     marker=dict(symbol="triangle-down", size=14, color="red"),
                                     name="Entry Short"), row=1, col=1)
    if "Volume" in df.columns:
        colors = ["#26a69a" if df["Close"].iloc[i] >= df["Open"].iloc[i] else "#ef5350"
                  for i in range(len(df))]
        fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume",
                             marker_color=colors, opacity=0.6), row=2, col=1)
    fig.update_layout(
        title=f"{ticker} - Price Chart", xaxis_rangeslider_visible=False,
        template="plotly_dark", height=550, margin=dict(l=40, r=40, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    return fig


def equity_curve_chart(equity_df: pd.DataFrame, initial_capital: float) -> go.Figure:
    fig = go.Figure()
    if not equity_df.empty:
        fig.add_trace(go.Scatter(
            x=equity_df["date"], y=equity_df["equity"], mode="lines",
            name="Portfolio Equity", line=dict(color="#00bcd4", width=2),
            fill="tozeroy", fillcolor="rgba(0,188,212,0.1)",
        ))
        fig.add_hline(y=initial_capital, line_dash="dash", line_color="rgba(255,255,255,0.4)",
                      annotation_text=f"Initial ${initial_capital:,.0f}")
    fig.update_layout(
        title="Equity Curve", template="plotly_dark", height=350,
        margin=dict(l=40, r=40, t=50, b=30),
        yaxis_title="Portfolio Value ($)", xaxis_title="Date",
    )
    return fig


def drawdown_chart(equity_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not equity_df.empty and "equity" in equity_df.columns:
        equity = equity_df["equity"]
        rolling_max = equity.cummax()
        drawdown = (equity - rolling_max) / rolling_max * 100
        fig.add_trace(go.Scatter(
            x=equity_df["date"], y=drawdown, mode="lines", name="Drawdown",
            line=dict(color="#ef5350", width=1.5),
            fill="tozeroy", fillcolor="rgba(239,83,80,0.15)",
        ))
    fig.update_layout(
        title="Drawdown (%)", template="plotly_dark", height=250,
        margin=dict(l=40, r=40, t=50, b=30),
        yaxis_title="Drawdown (%)", xaxis_title="Date",
    )
    return fig


def pnl_distribution_chart(trades_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not trades_df.empty and "P&L ($)" in trades_df.columns:
        pnl = trades_df["P&L ($)"]
        fig.add_trace(go.Histogram(
            x=pnl, nbinsx=30, name="P&L Distribution",
            marker_color=["#26a69a" if v >= 0 else "#ef5350" for v in pnl],
        ))
        fig.add_vline(x=0, line_dash="dash", line_color="white")
    fig.update_layout(
        title="Trade P&L Distribution", template="plotly_dark", height=300,
        xaxis_title="P&L ($)", yaxis_title="Count",
        margin=dict(l=40, r=40, t=50, b=30),
    )
    return fig


def portfolio_gauge(current_units: int, max_units: int, long_units: int, short_units: int) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=current_units,
        title={"text": f"Units Used ({current_units}/{max_units})"},
        gauge={
            "axis": {"range": [0, max_units]},
            "bar": {"color": "#00bcd4"},
            "steps": [
                {"range": [0, max_units * 0.5], "color": "rgba(0,188,212,0.1)"},
                {"range": [max_units * 0.5, max_units * 0.75], "color": "rgba(255,200,0,0.2)"},
                {"range": [max_units * 0.75, max_units], "color": "rgba(239,83,80,0.2)"},
            ],
            "threshold": {"line": {"color": "red", "width": 3}, "thickness": 0.75, "value": max_units},
        },
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=20, r=20, t=40, b=20))
    return fig
