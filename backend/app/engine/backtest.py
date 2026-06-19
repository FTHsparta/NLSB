"""Phase 1 backtest runner: hard-coded RSI strategy and B&H benchmark via vectorbt.

buy when RSI(rsi_period) < rsi_lower; sell when RSI(rsi_period) > rsi_upper.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
import vectorbt as vbt

from app.engine.indicators import wilder_rsi
from app.engine.signals import rsi_threshold_signals, shift_for_next_bar_execution

# Daily bars from yfinance have no fixed pandas freq (weekends/holidays), so
# vectorbt's own annualized_return()/sharpe_ratio() can't infer a year_freq.
# Annualize using the standard 252-trading-days-per-year convention instead.
TRADING_DAYS_PER_YEAR = 252


@dataclass
class BacktestResult:
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    num_trades: int
    start: str
    end: str

    def as_dict(self) -> dict:
        return asdict(self)


def run_rsi_backtest(
    close: pd.Series,
    rsi_period: int = 14,
    rsi_lower: float = 30,
    rsi_upper: float = 70,
    fees: float = 0.0,
    slippage: float = 0.0,
    init_cash: float = 10_000,
) -> BacktestResult:
    """Run the hard-coded RSI strategy and return summary metrics.

    The first ``rsi_period`` bars have no RSI value, and the no-lookahead
    shift consumes one more bar before a signal can act — those
    ``rsi_period + 1`` warmup bars are dropped from the *effective* window
    that vectorbt actually trades over (requirement: warmup / indicator
    lookback must not silently shrink the reported test window without the
    user knowing).
    """
    rsi = wilder_rsi(close, period=rsi_period)
    raw_entries, raw_exits = rsi_threshold_signals(rsi, rsi_lower, rsi_upper)

    entries = shift_for_next_bar_execution(raw_entries)
    exits = shift_for_next_bar_execution(raw_exits)

    warmup = rsi_period + 1
    eff_close = close.iloc[warmup:]
    eff_entries = entries.iloc[warmup:]
    eff_exits = exits.iloc[warmup:]

    pf = vbt.Portfolio.from_signals(
        eff_close,
        eff_entries,
        eff_exits,
        fees=fees,
        slippage=slippage,
        init_cash=init_cash,
    )

    num_trades = int(pf.trades.count())
    num_bars = len(eff_close)
    total_return = float(pf.total_return())

    annualized_return = (1 + total_return) ** (TRADING_DAYS_PER_YEAR / num_bars) - 1

    daily_returns = pf.returns()
    returns_std = daily_returns.std()
    sharpe_ratio = (
        float(daily_returns.mean() / returns_std * np.sqrt(TRADING_DAYS_PER_YEAR))
        if returns_std > 0
        else float("nan")
    )

    return BacktestResult(
        total_return=total_return,
        annualized_return=float(annualized_return),
        sharpe_ratio=sharpe_ratio,
        max_drawdown=float(pf.max_drawdown()),
        win_rate=float(pf.trades.win_rate()) if num_trades > 0 else float("nan"),
        num_trades=num_trades,
        start=str(eff_close.index[0].date()),
        end=str(eff_close.index[-1].date()),
    )


def run_ir_backtest(
    ir: dict,
    price_data: pd.DataFrame,
    fees: float = 0.0,
    slippage: float = 0.0,
    init_cash: float = 10_000,
) -> BacktestResult:
    """Run a strategy described by a validated IR dict and return summary metrics.

    This is the generic counterpart to ``run_rsi_backtest``: it calls the safe
    interpreter to produce entry/exit signals, then runs vectorbt with the same
    cost model and effective-window logic.

    Parameters
    ----------
    ir:
        Strategy IR dict (validated against the JSON schema).
    price_data:
        DataFrame with columns Open, High, Low, Close (yfinance convention).
    """
    from app.translation.interpreter import compute_ir_warmup, interpret_ir

    entries, exits = interpret_ir(ir, price_data)
    warmup = compute_ir_warmup(ir)

    close = price_data["Close"]
    eff_close = close.iloc[warmup:]
    eff_entries = entries.iloc[warmup:]
    eff_exits = exits.iloc[warmup:]

    pf = vbt.Portfolio.from_signals(
        eff_close,
        eff_entries,
        eff_exits,
        fees=fees,
        slippage=slippage,
        init_cash=init_cash,
    )

    num_trades = int(pf.trades.count())
    num_bars = len(eff_close)
    total_return = float(pf.total_return())
    annualized_return = (1 + total_return) ** (TRADING_DAYS_PER_YEAR / num_bars) - 1

    daily_returns = pf.returns()
    returns_std = daily_returns.std()
    sharpe_ratio = (
        float(daily_returns.mean() / returns_std * np.sqrt(TRADING_DAYS_PER_YEAR))
        if returns_std > 0
        else float("nan")
    )

    return BacktestResult(
        total_return=total_return,
        annualized_return=float(annualized_return),
        sharpe_ratio=sharpe_ratio,
        max_drawdown=float(pf.max_drawdown()),
        win_rate=float(pf.trades.win_rate()) if num_trades > 0 else float("nan"),
        num_trades=num_trades,
        start=str(eff_close.index[0].date()),
        end=str(eff_close.index[-1].date()),
    )


def compute_buy_and_hold_metrics(
    close: pd.Series,
    warmup: int,
    fees: float = 0.0,
    slippage: float = 0.0,
    init_cash: float = 10_000,
) -> BacktestResult:
    """Buy-and-hold benchmark over the same effective window as the strategy.

    Buys on the first bar after ``warmup`` bars are dropped and holds to the
    end.  Applies the same cost model as the strategy so comparisons are
    apples-to-apples; win_rate and num_trades are not meaningful for a single
    held position and are set to nan/0 respectively.
    """
    eff_close = close.iloc[warmup:]

    entries = pd.Series(False, index=eff_close.index)
    entries.iloc[0] = True
    exits = pd.Series(False, index=eff_close.index)

    pf = vbt.Portfolio.from_signals(
        eff_close,
        entries,
        exits,
        fees=fees,
        slippage=slippage,
        init_cash=init_cash,
    )

    num_bars = len(eff_close)
    total_return = float(pf.total_return())
    annualized_return = (1 + total_return) ** (TRADING_DAYS_PER_YEAR / num_bars) - 1

    daily_returns = pf.returns()
    returns_std = daily_returns.std()
    sharpe_ratio = (
        float(daily_returns.mean() / returns_std * np.sqrt(TRADING_DAYS_PER_YEAR))
        if returns_std > 0
        else float("nan")
    )

    return BacktestResult(
        total_return=total_return,
        annualized_return=float(annualized_return),
        sharpe_ratio=sharpe_ratio,
        max_drawdown=float(pf.max_drawdown()),
        win_rate=float("nan"),
        num_trades=0,
        start=str(eff_close.index[0].date()),
        end=str(eff_close.index[-1].date()),
    )
