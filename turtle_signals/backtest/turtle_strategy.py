"""backtest/turtle_strategy.py — Backtrader Strategy implementing Turtle Trading."""

import backtrader as bt
import backtrader.indicators as btind


class TurtleStrategy(bt.Strategy):
    params = dict(
        s1_entry=20, s1_exit=10,
        s2_entry=55, s2_exit=20,
        atr_period=20,
        risk_pct=0.01,
        stop_multiplier=2.0,
        use_system1=True,
        use_system2=True,
        apply_s1_filter=True,
        verbose=False,
    )

    def __init__(self):
        self.s1_high = btind.Highest(self.data.high, period=self.p.s1_entry)
        self.s1_low  = btind.Lowest(self.data.low,   period=self.p.s1_entry)
        self.s1_exit_low  = btind.Lowest(self.data.low,   period=self.p.s1_exit)
        self.s1_exit_high = btind.Highest(self.data.high, period=self.p.s1_exit)

        self.s2_high = btind.Highest(self.data.high, period=self.p.s2_entry)
        self.s2_low  = btind.Lowest(self.data.low,   period=self.p.s2_entry)
        self.s2_exit_low  = btind.Lowest(self.data.low,   period=self.p.s2_exit)
        self.s2_exit_high = btind.Highest(self.data.high, period=self.p.s2_exit)

        self.atr = btind.ATR(self.data, period=self.p.atr_period)

        self.current_position = 0
        self.entry_price = None
        self.stop_price = None
        self.active_system = None
        self.last_s1_winner = False
        self.last_s1_pnl = 0.0
        self.completed_trades = []
        self._trade_open_bar = None
        self._trade_open_price = None
        self._trade_direction = None
        self._trade_system = None
        self._order = None

    def log(self, msg: str):
        if self.p.verbose:
            dt = self.data.datetime.date(0)
            print(f"{dt} | {msg}")

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f"BUY  @ {order.executed.price:.2f}  size={order.executed.size:.0f}")
            else:
                self.log(f"SELL @ {order.executed.price:.2f}  size={order.executed.size:.0f}")
            self._order = None
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self._order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        pnl = trade.pnl
        if self.active_system == 1:
            self.last_s1_winner = pnl > 0
            self.last_s1_pnl = pnl
        self.completed_trades.append({
            "open_bar": self._trade_open_bar,
            "close_bar": len(self),
            "open_date": self.data.datetime.date(-trade.barlen) if trade.barlen else None,
            "close_date": self.data.datetime.date(0),
            "direction": self._trade_direction,
            "system": self._trade_system,
            "entry_price": self._trade_open_price,
            "exit_price": trade.price,
            "pnl": pnl,
            "pnl_pct": pnl / (self._trade_open_price * abs(trade.size)) * 100
                       if self._trade_open_price else 0,
        })
        self.current_position = 0
        self.entry_price = None
        self.stop_price = None
        self.active_system = None

    def _calc_size(self) -> int:
        equity = self.broker.getvalue()
        atr = self.atr[0]
        if atr <= 0:
            return 0
        return max(1, int((equity * self.p.risk_pct) / atr))

    def next(self):
        if self._order:
            return

        close = self.data.close[0]
        atr = self.atr[0]
        if atr <= 0:
            return

        if self.position:
            pos_size = self.position.size
            if pos_size > 0:
                if close <= self.stop_price:
                    self._order = self.close()
                    return
                if self.active_system == 1 and close < self.s1_exit_low[-1]:
                    self._order = self.close()
                    return
                if self.active_system == 2 and close < self.s2_exit_low[-1]:
                    self._order = self.close()
                    return
            elif pos_size < 0:
                if close >= self.stop_price:
                    self._order = self.close()
                    return
                if self.active_system == 1 and close > self.s1_exit_high[-1]:
                    self._order = self.close()
                    return
                if self.active_system == 2 and close > self.s2_exit_high[-1]:
                    self._order = self.close()
                    return
            return

        if self.p.use_system2:
            if close > self.s2_high[-1]:
                size = self._calc_size()
                if size > 0:
                    self._order = self.buy(size=size)
                    self.entry_price = close
                    self.stop_price = close - self.p.stop_multiplier * atr
                    self.current_position = 1
                    self.active_system = 2
                    self._trade_open_bar = len(self)
                    self._trade_open_price = close
                    self._trade_direction = "long"
                    self._trade_system = 2
                    return
            if close < self.s2_low[-1]:
                size = self._calc_size()
                if size > 0:
                    self._order = self.sell(size=size)
                    self.entry_price = close
                    self.stop_price = close + self.p.stop_multiplier * atr
                    self.current_position = -1
                    self.active_system = 2
                    self._trade_open_bar = len(self)
                    self._trade_open_price = close
                    self._trade_direction = "short"
                    self._trade_system = 2
                    return

        if self.p.use_system1:
            s1_allowed = not (self.p.apply_s1_filter and self.last_s1_winner)
            if s1_allowed:
                if close > self.s1_high[-1]:
                    size = self._calc_size()
                    if size > 0:
                        self._order = self.buy(size=size)
                        self.entry_price = close
                        self.stop_price = close - self.p.stop_multiplier * atr
                        self.current_position = 1
                        self.active_system = 1
                        self.last_s1_winner = False
                        self._trade_open_bar = len(self)
                        self._trade_open_price = close
                        self._trade_direction = "long"
                        self._trade_system = 1
                        return
                if close < self.s1_low[-1]:
                    size = self._calc_size()
                    if size > 0:
                        self._order = self.sell(size=size)
                        self.entry_price = close
                        self.stop_price = close + self.p.stop_multiplier * atr
                        self.current_position = -1
                        self.active_system = 1
                        self.last_s1_winner = False
                        self._trade_open_bar = len(self)
                        self._trade_open_price = close
                        self._trade_direction = "short"
                        self._trade_system = 1
                        return
