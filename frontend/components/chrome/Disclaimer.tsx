/**
 * Legal / trust chrome (Phase 9). This is a fact about the PRODUCT, not a
 * judgment about any strategy -- so it is the frontend's own copy, written
 * in NLSB's plain, direct voice (no boilerplate hedging wall). Muted-gray
 * tier, monochrome, no saturated color.
 *
 * Two surfaces:
 *  - `DisclaimerFooter`: one compact permanent line, present on every screen.
 *  - `ResultsDisclaimer`: a slightly fuller block shown on the results
 *    surface, where a number that looks like a return most needs the caveat.
 */

export function DisclaimerFooter() {
  return (
    <footer
      data-testid="disclaimer-footer"
      className="mx-auto max-w-2xl px-6 pb-8 pt-4 text-xs leading-relaxed text-muted-foreground"
    >
      Backtested, hypothetical results — not a prediction, not investment advice, and no
      guarantee of future performance. Market data may contain errors.
    </footer>
  );
}

export function ResultsDisclaimer() {
  return (
    <aside
      data-testid="results-disclaimer"
      className="mt-8 rounded-lg border border-border bg-card p-4 text-xs leading-relaxed text-muted-foreground"
    >
      <p>
        These figures are <span className="font-medium text-foreground">hypothetical and backtested</span> — they
        describe how this strategy would have behaved on past data, run once with hindsight over a fixed window. Past
        performance does not indicate future results.
      </p>
      <p className="mt-2">
        Nothing here is investment advice or a recommendation to trade. Price data comes from third parties and can
        contain errors, gaps, or survivorship bias. Treat every number as an estimate, not a promise.
      </p>
    </aside>
  );
}
