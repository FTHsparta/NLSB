import type { DeflatedSharpeResult, ParamSensitivity, RegimeReport, WalkForwardResult } from "@/lib/robustness/types";
import { formatNumberOrNA, formatPercentOrNA } from "@/lib/robustness/format";

export interface RobustnessPanelProps {
  sensitivity: ParamSensitivity[];
  walkForward: WalkForwardResult;
  deflatedSharpe: DeflatedSharpeResult;
  regime: RegimeReport;
}

/**
 * Supporting detail for the verdict already rendered above this component
 * (see `RobustnessResultView` for render order). Every figure here is
 * displayed verbatim from the backend result, formatted only -- nothing in
 * this component computes a pass/fail or re-derives the verdict.
 * Collapsible (`<details>`) and visually secondary: this is the "show your
 * work," not the headline.
 */
export function RobustnessPanel({ sensitivity, walkForward, deflatedSharpe, regime }: RobustnessPanelProps) {
  return (
    <section data-testid="robustness-panel" className="mt-6 space-y-3 text-sm">
      <details data-testid="section-walk-forward" className="rounded-md border border-zinc-200 p-4 dark:border-zinc-700">
        <summary className="cursor-pointer font-medium text-zinc-700 dark:text-zinc-300">
          Walk-forward validation
        </summary>
        <div className="mt-3 space-y-1 text-zinc-600 dark:text-zinc-400">
          <p>
            Aggregate in-sample Sharpe:{" "}
            <span data-testid="stat-aggregate-is-sharpe">{formatNumberOrNA(walkForward.aggregate_is_sharpe)}</span>
          </p>
          <p>
            Aggregate out-of-sample Sharpe:{" "}
            <span data-testid="stat-aggregate-oos-sharpe">{formatNumberOrNA(walkForward.aggregate_oos_sharpe)}</span>
          </p>
          <p>
            Degradation (IS - OOS): <span data-testid="stat-degradation">{formatNumberOrNA(walkForward.degradation)}</span>
          </p>
          <table className="mt-2 w-full text-left">
            <thead>
              <tr>
                <th className="pr-3 font-medium">Fold</th>
                <th className="pr-3 font-medium">IS Sharpe</th>
                <th className="pr-3 font-medium">OOS Sharpe</th>
                <th className="pr-3 font-medium">Low confidence</th>
              </tr>
            </thead>
            <tbody>
              {walkForward.folds.map((fold) => (
                <tr key={fold.fold_index}>
                  <td className="pr-3">{fold.fold_index}</td>
                  <td className="pr-3" data-testid={`stat-fold-${fold.fold_index}-is-sharpe`}>
                    {formatNumberOrNA(fold.is_sharpe)}
                  </td>
                  <td className="pr-3" data-testid={`stat-fold-${fold.fold_index}-oos-sharpe`}>
                    {formatNumberOrNA(fold.oos_sharpe)}
                  </td>
                  <td className="pr-3">{fold.low_confidence ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <details data-testid="section-sensitivity" className="rounded-md border border-zinc-200 p-4 dark:border-zinc-700">
        <summary className="cursor-pointer font-medium text-zinc-700 dark:text-zinc-300">
          Parameter sensitivity
        </summary>
        <table className="mt-3 w-full text-left text-zinc-600 dark:text-zinc-400">
          <thead>
            <tr>
              <th className="pr-3 font-medium">Parameter</th>
              <th className="pr-3 font-medium">Peakiness</th>
              <th className="pr-3 font-medium">Robustness</th>
            </tr>
          </thead>
          <tbody>
            {sensitivity.map((param) => (
              <tr key={param.param_id}>
                <td className="pr-3">{param.param_id}</td>
                <td className="pr-3" data-testid={`stat-sensitivity-${param.param_id}-peakiness`}>
                  {formatNumberOrNA(param.peakiness)}
                </td>
                <td className="pr-3">{param.robustness_label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      <details data-testid="section-dsr" className="rounded-md border border-zinc-200 p-4 dark:border-zinc-700">
        <summary className="cursor-pointer font-medium text-zinc-700 dark:text-zinc-300">
          Deflated Sharpe Ratio
        </summary>
        <div className="mt-3 space-y-1 text-zinc-600 dark:text-zinc-400">
          <p>
            DSR: <span data-testid="stat-dsr">{formatNumberOrNA(deflatedSharpe.dsr)}</span>
          </p>
          <p>Trials evaluated: {deflatedSharpe.n_trials}</p>
        </div>
      </details>

      <details data-testid="section-regime" className="rounded-md border border-zinc-200 p-4 dark:border-zinc-700">
        <summary className="cursor-pointer font-medium text-zinc-700 dark:text-zinc-300">
          Regime breakdown
        </summary>
        <div className="mt-3 space-y-1 text-zinc-600 dark:text-zinc-400">
          {regime.concentrated_regime && (
            <p data-testid="stat-concentrated-regime">
              {regime.concentrated_regime}: {formatPercentOrNA(regime.concentration_share)} of gains
            </p>
          )}
          {regime.marginal_flags.map((flag) => (
            <p
              key={flag.flag}
              data-testid={`stat-marginal-${flag.flag}`}
              className={
                flag.confidence === "confirmed"
                  ? "font-medium text-amber-700 dark:text-amber-400"
                  : "text-zinc-400 dark:text-zinc-500"
              }
            >
              Bull-concentrated: +{(flag.excess * 100).toFixed(1)} pp vs benchmark
              {flag.confidence === "provisional" ? " (provisional)" : ""}
            </p>
          ))}
          <table className="mt-2 w-full text-left">
            <thead>
              <tr>
                <th className="pr-3 font-medium">Regime</th>
                <th className="pr-3 font-medium">Share of time</th>
                <th className="pr-3 font-medium">Sharpe</th>
              </tr>
            </thead>
            <tbody>
              {regime.breakdowns.map((b) => (
                <tr key={b.regime}>
                  <td className="pr-3">{b.regime}</td>
                  <td className="pr-3">{formatPercentOrNA(b.share_of_time)}</td>
                  <td className="pr-3" data-testid={`stat-regime-${b.regime}-sharpe`}>
                    {formatNumberOrNA(b.sharpe_ratio)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
