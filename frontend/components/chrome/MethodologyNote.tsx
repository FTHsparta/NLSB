/**
 * "How to read a verdict" — educational chrome (Phase 9), reachable from the
 * results surface as an expandable panel. It explains the checks GENERICALLY:
 * it never restates or interprets a specific strategy's numbers (that would
 * cross the display-side corollary). Two-tier type, monochrome, ~350 words.
 */

const VERDICTS: { key: string; title: string; body: string }[] = [
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

const CHECKS: { title: string; body: string }[] = [
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

export function MethodologyNote() {
  return (
    <details data-testid="methodology-note" className="mt-6 rounded-lg border border-border bg-card p-4">
      <summary
        data-testid="methodology-summary"
        className="cursor-pointer select-none text-sm font-semibold text-foreground"
      >
        How to read a verdict
      </summary>

      <div className="mt-4 space-y-6 text-sm">
        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">What each verdict means</h3>
          <dl className="space-y-3">
            {VERDICTS.map((v) => (
              <div key={v.key}>
                <dt data-testid={`methodology-heading-${v.key}`} className="font-semibold text-foreground">
                  {v.title}
                </dt>
                <dd className="text-muted-foreground">{v.body}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">What each check asks</h3>
          <dl className="space-y-3">
            {CHECKS.map((c) => (
              <div key={c.title}>
                <dt className="font-semibold text-foreground">{c.title}</dt>
                <dd className="text-muted-foreground">{c.body}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Why a great-looking curve can still be overfit
          </h3>
          <p className="text-muted-foreground">
            Try enough parameter combinations on one slice of history and some will look brilliant by chance alone —
            the equity curve fits the noise, not a repeatable edge. These checks exist to separate a real signal from a
            flattering coincidence, which is exactly what a single backtest number can hide.
          </p>
        </section>
      </div>
    </details>
  );
}
