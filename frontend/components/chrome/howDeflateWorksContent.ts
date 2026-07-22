/**
 * "How Deflate works" copy (glossary + limitations), rendered ONLY by the
 * /methodology page. Static, generic chrome: it describes the SYSTEM in
 * general and never references or interpolates a specific run's numbers
 * (display-side corollary).
 *
 * Deliberately a SEPARATE module from `methodologyContent.ts`: that module's
 * contract (and its pinned test, via MethodologyNote) is "no digits at all",
 * because the in-flow note sits next to real results where any figure could
 * read as the strategy's own. The limitations copy below DOES contain
 * numbers — the fixed 0.05%-per-fill cost model, the 80% concentration
 * threshold, the 2015 default window — but they are constants of the system
 * itself, identical for every run, stated here precisely because being vague
 * about them would be dishonest. Keeping the two modules separate keeps both
 * contracts true at once. MethodologyNote must never import from this file.
 */

export const HOW_INTRO =
  "Most backtesters are cheerleaders — feed them a strategy and they hand back a flattering equity curve. Deflate is built to do the opposite: to assume your edge is a mirage until it survives being actively challenged, and to tell you plainly where it breaks. Here is what each check does, in plain terms, and — just as importantly — what Deflate cannot do.";

export const GLOSSARY_TERMS: { term: string; body: string }[] = [
  {
    term: "In-sample vs. out-of-sample",
    body: "In-sample is the data a strategy was tuned on; out-of-sample is data it never saw. A strategy that performs well in-sample and poorly out-of-sample was memorized, not discovered. Nearly every overfit strategy looks strong in-sample — that is precisely the problem.",
  },
  {
    term: "Overfitting",
    body: "Fitting the noise of one historical period instead of a real, repeatable pattern. The signature is fragility: small changes to the parameters or the time window cause the returns to collapse.",
  },
  {
    term: "Walk-forward validation",
    body: "Rather than testing on all history at once, the data is divided into sequential segments: the strategy is tuned on one, tested on the next, then rolled forward and repeated. It approximates running the strategy through time instead of grading it with hindsight. A large gap between tuned and walk-forward performance indicates the edge does not travel.",
  },
  {
    term: "Deflated Sharpe ratio",
    body: "A conventional Sharpe ratio becomes more flattering the more variants are tried, because with enough attempts something scores well by chance. The Deflated Sharpe ratio corrects for how many effective variations could have been tested, then asks whether the result remains convincing once that search is accounted for.",
  },
  {
    term: "Regime concentration",
    body: "Whether returns were earned across varied market conditions or accumulated during a single favorable period. A strategy that produced its gains in one bull run, and little elsewhere, is not robust — it is a wager on that condition recurring.",
  },
  {
    term: "Parameter sensitivity",
    body: "How sharply performance depends on exact parameter values. A robust edge occupies a broad plateau: adjusting a threshold barely moves returns. A fragile one sits on a narrow peak, where the tuned values look strong and everything around them falls away — a hallmark of curve-fitting.",
  },
  {
    term: "Verdict (Pass / Shaky / Likely overfit / Untestable)",
    body: "Deflate's single summary judgment after all checks. Untestable does not indicate a poor strategy; it means the data or structure did not permit an honest test, which Deflate reports rather than disguising as a grade.",
  },
];

export const LIMITATIONS_LEAD =
  "Deflate is deliberately narrow. Understanding exactly where it stops is part of trusting what it reports, so its boundaries are stated plainly below.";

export const LIMITATIONS: { title: string; body: string }[] = [
  {
    title: "Returns are close to gross.",
    body: "Each backtest applies roughly 0.05% per fill for slippage and nothing for commissions, spread, or market impact — the same modest cost whether the instrument is highly liquid or thinly traded. Real-world friction is typically higher, particularly for strategies that trade frequently, so every return shown here should be read as optimistic.",
  },
  {
    title: "Fills occur at the following day's close.",
    body: "A signal on today's close is executed at the next day's close, a full session later. This is deliberate: it ensures the strategy never trades on information it could not have had. It is, however, a specific and unconventional assumption — execution is modeled at the closing price 24 hours after the signal, rather than the next open — and any intraday movement in between is not captured.",
  },
  {
    title: "Daily bars, one asset, long or flat.",
    body: "Deflate uses daily data only, with no intraday or weekly resolution, no short positions, and no multi-asset or cross-asset conditions. Positions are all-in or all-out, with no sizing, scaling, or rebalancing, and idle capital earns nothing. Any symbol entered — including crypto or futures tickers — is treated as equity-style daily data, with the same assumptions and costs.",
  },
  {
    title: "It can only observe survivors.",
    body: "Price data comes from a single source and is split- and dividend-adjusted. Any ticker with a significant data gap, often a sign of delisting, is rejected rather than modeled, so only instruments that still trade cleanly today can be tested — a bias toward past winners. The default window begins in 2015, a period dominated by a prolonged bull market. Deflate flags when an edge depends on a single regime, but it cannot detect bias in which ticker was selected.",
  },
  {
    title: "A limited strategy vocabulary.",
    body: "Deflate understands the RSI, SMA, and EMA indicators, compared against one another, against price, or against constants, and combined with and/or logic. It does not support other indicators such as MACD, Bollinger Bands, ATR, or volume-based conditions, nor seasonality or calendar rules, trailing or limit orders, or lookback references such as the highest high of the last N days. Strategies requiring these are declined rather than silently approximated. Stop-loss and take-profit orders are also not yet simulated, and strategies specifying them are declined for the same reason.",
  },
  {
    title: "Several thresholds reflect considered defaults rather than established standards.",
    body: "A number of the cutoffs Deflate applies — where parameter sensitivity is judged excessive, the 80% regime-concentration threshold, and the pass and fail boundaries for the Deflated Sharpe ratio — are values we selected and documented deliberately, not figures drawn from published literature. They reflect reasonable judgments, and other analysts may legitimately set them differently.",
  },
];
