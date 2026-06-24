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
 * field for this component to render even if it tried).
 */
export function BuyHoldComparison({ noExit }: BuyHoldComparisonProps) {
  return (
    <section data-testid="buy-hold-comparison" className="rounded-lg border-2 border-sky-500 bg-white p-6 dark:bg-zinc-900">
      <p className="text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Not a round-trip strategy
      </p>
      <p data-testid="no-exit-message" className="mt-2 text-zinc-800 dark:text-zinc-200">
        {noExit.message}
      </p>
      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
        First entry: <span data-testid="first-entry-date">{formatDateOrNA(noExit.first_entry_date)}</span>
      </p>

      {noExit.strategy_metrics && noExit.benchmark_metrics ? (
        <table className="mt-4 w-full text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-700">
              <th className="py-1 font-medium text-zinc-500 dark:text-zinc-400">Metric</th>
              <th className="py-1 font-medium text-zinc-500 dark:text-zinc-400">This strategy</th>
              <th className="py-1 font-medium text-zinc-500 dark:text-zinc-400">Buy-and-hold benchmark</th>
            </tr>
          </thead>
          <tbody>
            {METRIC_ROWS.map(({ key, label, percent }) => {
              const format = percent ? formatPercentOrNA : formatNumberOrNA;
              return (
                <tr key={key} className="border-b border-zinc-100 dark:border-zinc-800">
                  <td className="py-1 text-zinc-600 dark:text-zinc-400">{label}</td>
                  <td data-testid={`stat-strategy-${key}`} className="py-1 text-zinc-900 dark:text-zinc-100">
                    {format(noExit.strategy_metrics![key])}
                  </td>
                  <td data-testid={`stat-benchmark-${key}`} className="py-1 text-zinc-900 dark:text-zinc-100">
                    {format(noExit.benchmark_metrics![key])}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="mt-4 text-zinc-600 dark:text-zinc-400">
          No comparison available -- the entry condition never fired.
        </p>
      )}
    </section>
  );
}
