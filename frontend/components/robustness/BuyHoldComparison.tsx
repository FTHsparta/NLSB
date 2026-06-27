import type { NoExitResult } from "@/lib/robustness/types";
import { formatDateOrNA, formatNumberOrNA, formatPercentOrNA } from "@/lib/robustness/format";

export interface BuyHoldComparisonProps {
  noExit: NoExitResult;
}

const METRIC_ROWS: Array<{ key: "total_return" | "annualized_return" | "sharpe_ratio" | "max_drawdown"; label: string; percent: boolean }> = [
  { key: "total_return", label: "Total return", percent: true },
  { key: "annualized_return", label: "Annualized return", percent: true },
  { key: "sharpe_ratio", label: "Sharpe ratio", percent: false },
  { key: "max_drawdown", label: "Max drawdown", percent: true },
];

/**
 * Rendered INSTEAD OF VerdictCard/RobustnessPanel for a no-exit result --
 * never alongside them (see `RobustnessResultView`). This is not a
 * verdict: there is no PASS/SHAKY/LIKELY_OVERFIT/UNTESTABLE label anywhere
 * in this component, by construction (`NoExitResult` carries no such
 * field for this component to render even if it tried). Same card chrome
 * and padding as `VerdictCard` (border, bg-card, p-6) so it reads as a
 * first-class result, not an error or an empty state -- monochrome, the
 * same as everything outside the verdict card.
 */
export function BuyHoldComparison({ noExit }: BuyHoldComparisonProps) {
  return (
    <section data-testid="buy-hold-comparison" className="rounded-lg border border-border bg-card p-6">
      <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">Not a round-trip strategy</p>
      <p data-testid="no-exit-message" className="mt-2 text-lg text-foreground">
        {noExit.message}
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        First entry:{" "}
        <span data-testid="first-entry-date" className="font-mono tabular-nums text-foreground">
          {formatDateOrNA(noExit.first_entry_date)}
        </span>
      </p>

      {noExit.strategy_metrics && noExit.benchmark_metrics ? (
        <table className="mt-6 w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="py-2 font-medium text-muted-foreground">Metric</th>
              <th className="py-2 font-medium text-muted-foreground">This strategy</th>
              <th className="py-2 font-medium text-muted-foreground">Buy-and-hold benchmark</th>
            </tr>
          </thead>
          <tbody>
            {METRIC_ROWS.map(({ key, label, percent }) => {
              const format = percent ? formatPercentOrNA : formatNumberOrNA;
              return (
                <tr key={key} className="border-b border-border/50">
                  <td className="py-2 text-muted-foreground">{label}</td>
                  <td data-testid={`stat-strategy-${key}`} className="py-2 font-mono tabular-nums text-foreground">
                    {format(noExit.strategy_metrics![key])}
                  </td>
                  <td data-testid={`stat-benchmark-${key}`} className="py-2 font-mono tabular-nums text-foreground">
                    {format(noExit.benchmark_metrics![key])}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="mt-6 text-muted-foreground">No comparison available -- the entry condition never fired.</p>
      )}
    </section>
  );
}
