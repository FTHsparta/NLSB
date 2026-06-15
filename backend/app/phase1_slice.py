"""Phase 1: dumbest end-to-end slice. No LLM, no IR, no frontend.

Hard-coded strategy: buy SPY when RSI(14) < 30, sell when RSI(14) > 70.
Proves the core pipeline: yfinance -> Wilder's RSI -> next-bar signals ->
vectorbt -> metrics.

Run with: ``python -m app.phase1_slice``
"""

from app.data.market_data import fetch_daily_bars
from app.engine.backtest import BacktestResult, run_rsi_backtest

TICKER = "SPY"
START = "2010-01-01"

# Robinhood-tier retail: ~0 commission, but slippage/spread is real.
RETAIL_SLIPPAGE = 0.0005  # 5 bps


def _print_result(label: str, result: BacktestResult) -> None:
    print(f"\n--- {label} ---")
    print(f"  Effective window:   {result.start} to {result.end}")
    print(f"  Trades:             {result.num_trades}")
    print(f"  Total return:       {result.total_return:.2%}")
    print(f"  Annualized return:  {result.annualized_return:.2%}")
    print(f"  Sharpe ratio:       {result.sharpe_ratio:.2f}")
    print(f"  Max drawdown:       {result.max_drawdown:.2%}")
    win_rate = result.win_rate
    print(f"  Win rate:           {win_rate:.2%}" if win_rate == win_rate else "  Win rate:           n/a (no trades)")


def main() -> None:
    df = fetch_daily_bars(TICKER, start=START)
    print(f"Fetched {len(df)} daily bars for {TICKER}: {df.index[0].date()} to {df.index[-1].date()}")

    with_costs = run_rsi_backtest(df["Close"], fees=0.0, slippage=RETAIL_SLIPPAGE)
    _print_result(f"With retail costs (slippage={RETAIL_SLIPPAGE:.2%})", with_costs)

    no_costs = run_rsi_backtest(df["Close"], fees=0.0, slippage=0.0)
    _print_result("Without costs (idealized)", no_costs)


if __name__ == "__main__":
    main()
