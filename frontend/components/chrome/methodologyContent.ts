/**
 * The methodology copy (Phase 9, promoted in Phase 11), shared verbatim by
 * the in-flow expandable `MethodologyNote` and the /methodology route so
 * the two can never drift apart. This is educational chrome about the
 * PRODUCT's checks in general -- it never restates or interprets any
 * specific strategy's numbers (display-side corollary), and it contains no
 * digits at all (pinned by test).
 */

export const VERDICT_EXPLANATIONS: { key: string; title: string; body: string }[] = [
  {
    key: "PASS",
    title: "PASS",
    body: "The edge held up across every check we could run: it survived out-of-sample periods, small parameter changes, the multiple-testing penalty, and different market regimes. Encouraging — not a guarantee.",
  },
  {
    key: "SHAKY",
    title: "SHAKY",
    body: "There is a signal, but at least one check flagged fragility — performance leaned on a narrow parameter range, one regime, or thinner out-of-sample results. Worth a closer look before trusting it.",
  },
  {
    key: "LIKELY_OVERFIT",
    title: "LIKELY OVERFIT",
    body: "The strong in-sample result mostly evaporated where it counts — out of sample, under small parameter changes, or after the multiple-testing penalty. A good-looking curve that probably won't repeat.",
  },
  {
    key: "UNTESTABLE",
    title: "UNTESTABLE",
    body: "There wasn't enough evidence to judge — too few trades, too little history, or windows too short to validate. Not a pass and not a fail: we won't pretend to know what the data can't tell us.",
  },
];

export const CHECK_EXPLANATIONS: { title: string; body: string }[] = [
  {
    title: "Walk-forward",
    body: "Re-fits the strategy on an earlier window and tests it on the next, unseen one — asking whether the edge survives on data it was never tuned on.",
  },
  {
    title: "Parameter sensitivity",
    body: "Nudges each parameter up and down — asking whether performance sits on a broad plateau or balances on a single lucky value.",
  },
  {
    title: "Deflated Sharpe",
    body: "Discounts the Sharpe ratio for how many parameter combinations were tried — asking whether the best result is better than you'd expect from luck alone across that many tries.",
  },
  {
    title: "Regime breakdown",
    body: "Splits returns by market condition — asking whether the edge is broad, or just one bull run wearing a strategy costume.",
  },
];

export const OVERFIT_EXPLANATION =
  "Try enough parameter combinations on one slice of history and some will look brilliant by chance alone — the equity curve fits the noise, not a repeatable edge. These checks exist to separate a real signal from a flattering coincidence, which is exactly what a single backtest number can hide.";
