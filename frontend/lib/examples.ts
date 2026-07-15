/**
 * Beginner-friendly example strategies, shared between the landing page's
 * chips (which link to /backtest with the example prefilled via the `s`
 * query param) and the backtest input's chips (which prefill the textarea
 * in place). Each has a clean entry AND exit so none trips the
 * missing-exit SEVERITY_WARNING when actually translated.
 */
export const EXAMPLE_STRATEGIES: { label: string; text: string }[] = [
  {
    label: "Golden cross (SPY)",
    text: "Buy SPY when SMA(50) crosses above SMA(200), sell when SMA(50) crosses below SMA(200).",
  },
  {
    label: "RSI mean reversion (QQQ)",
    text: "Buy QQQ when RSI(14) drops below 30, sell when RSI(14) rises above 70.",
  },
  {
    label: "200-day trend follow (AAPL)",
    text: "Buy AAPL when close crosses above SMA(200), sell when close crosses below SMA(200).",
  },
  {
    label: "20/50 crossover (MSFT)",
    text: "Buy MSFT when SMA(20) crosses above SMA(50), sell when SMA(20) crosses below SMA(50).",
  },
];

/** The /backtest URL that lands with `text` prefilled in the strategy box. */
export function backtestHref(text: string): string {
  return `/backtest?s=${encodeURIComponent(text)}`;
}
