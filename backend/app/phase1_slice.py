"""Phase 1: dumbest end-to-end slice. No LLM, no IR, no frontend.

Hard-coded strategy: buy SPY when RSI(14) < 30, sell when RSI(14) > 70.
Proves the core pipeline: yfinance -> Wilder's RSI -> next-bar signals ->
vectorbt -> metrics.

Run with: ``python -m app.phase1_slice``
"""

from app.data.market_data import fetch_daily_bars
from app.engine.backtest import BacktestResult, compute_buy_and_hold_metrics, run_rsi_backtest

TICKER = "SPY"
START = "2010-01-01"
RSI_PERIOD = 14
WARMUP = RSI_PERIOD + 1

# Robinhood-tier retail: ~0 commission, but slippage/spread is real.
RETAIL_SLIPPAGE = 0.0005  # 5 bps


def _print_result(label: str, result: BacktestResult, include_trade_stats: bool = True) -> None:
    print(f"\n--- {label} ---")
    print(f"  Effective window:   {result.start} to {result.end}")
    if include_trade_stats:
        print(f"  Trades:             {result.num_trades}")
    print(f"  Total return:       {result.total_return:.2%}")
    print(f"  Annualized return:  {result.annualized_return:.2%}")
    print(f"  Sharpe ratio:       {result.sharpe_ratio:.2f}")
    print(f"  Max drawdown:       {result.max_drawdown:.2%}")
    if include_trade_stats:
        win_rate = result.win_rate
        print(f"  Win rate:           {win_rate:.2%}" if win_rate == win_rate else "  Win rate:           n/a (no trades)")


def main() -> None:
    df = fetch_daily_bars(TICKER, start=START)
    print(f"Fetched {len(df)} daily bars for {TICKER}: {df.index[0].date()} to {df.index[-1].date()}")

    close = df["Close"]
    with_costs = run_rsi_backtest(close, rsi_period=RSI_PERIOD, fees=0.0, slippage=RETAIL_SLIPPAGE)
    no_costs = run_rsi_backtest(close, rsi_period=RSI_PERIOD, fees=0.0, slippage=0.0)
    bah = compute_buy_and_hold_metrics(close, warmup=WARMUP, fees=0.0, slippage=RETAIL_SLIPPAGE)

    _print_result(f"Strategy — with retail costs (slippage={RETAIL_SLIPPAGE:.2%})", with_costs)
    _print_result("Strategy — without costs (idealized)", no_costs)
    _print_result("Buy-and-hold benchmark", bah, include_trade_stats=False)

    excess = with_costs.annualized_return - bah.annualized_return
    verdict = "BEAT" if excess >= 0 else "LAGGED"
    print(f"\nVerdict: strategy {verdict} buy-and-hold by {abs(excess):.2%} annualized.")


if __name__ == "__main__":
    main()
