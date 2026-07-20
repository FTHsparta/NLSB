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
 * work," not the headline. Monochrome throughout, by design -- per-check
 * status (a fragile param, a confirmed regime flag) is not something the
 * backend marks with a color, so this component never invents one; see
 * `tests/visual/color-invariants.test.tsx`.
 */
export function RobustnessPanel({ sensitivity, walkForward, deflatedSharpe, regime }: RobustnessPanelProps) {
  return (
    <section data-testid="robustness-panel" className="mt-8 space-y-6 text-sm">
      <details data-testid="section-walk-forward" className="rounded-lg border border-border bg-card p-4 sm:p-6">
        <summary className="cursor-pointer py-2 font-medium text-foreground sm:py-0">Walk-forward validation</summary>
        <div className="mt-4 space-y-2 text-muted-foreground">
          <p>
            Aggregate in-sample Sharpe:{" "}
            <span data-testid="stat-aggregate-is-sharpe" className="font-mono tabular-nums text-foreground">
              {formatNumberOrNA(walkForward.aggregate_is_sharpe)}
            </span>
          </p>
          <p>
            Aggregate out-of-sample Sharpe:{" "}
            <span data-testid="stat-aggregate-oos-sharpe" className="font-mono tabular-nums text-foreground">
              {formatNumberOrNA(walkForward.aggregate_oos_sharpe)}
            </span>
          </p>
          <p>
            Degradation (IS - OOS):{" "}
            <span data-testid="stat-degradation" className="font-mono tabular-nums text-foreground">
              {formatNumberOrNA(walkForward.degradation)}
            </span>
          </p>
          {/* Tables scroll inside their own container on narrow screens
              (min-w keeps columns readable); the page itself never scrolls
              horizontally. */}
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[26rem] text-left">
            <thead>
              <tr className="border-b border-border">
                <th className="py-2 pr-3 font-medium">Fold</th>
                <th className="py-2 pr-3 font-medium">IS Sharpe</th>
                <th className="py-2 pr-3 font-medium">OOS Sharpe</th>
                <th className="py-2 pr-3 font-medium">Low confidence</th>
              </tr>
            </thead>
            <tbody>
              {walkForward.folds.map((fold) => (
                <tr key={fold.fold_index} className="border-b border-border/50">
                  <td className="py-2 pr-3 font-mono tabular-nums">{fold.fold_index}</td>
                  <td className="py-2 pr-3 font-mono tabular-nums" data-testid={`stat-fold-${fold.fold_index}-is-sharpe`}>
                    {formatNumberOrNA(fold.is_sharpe)}
                  </td>
                  <td className="py-2 pr-3 font-mono tabular-nums" data-testid={`stat-fold-${fold.fold_index}-oos-sharpe`}>
                    {formatNumberOrNA(fold.oos_sharpe)}
                  </td>
                  <td className="py-2 pr-3">{fold.low_confidence ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
            </table>
          </div>
        </div>
      </details>

      <details data-testid="section-sensitivity" className="rounded-lg border border-border bg-card p-4 sm:p-6">
        <summary className="cursor-pointer py-2 font-medium text-foreground sm:py-0">Parameter sensitivity</summary>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[22rem] text-left text-muted-foreground">
          <thead>
            <tr className="border-b border-border">
              <th className="py-2 pr-3 font-medium">Parameter</th>
              <th className="py-2 pr-3 font-medium">Peakiness</th>
              <th className="py-2 pr-3 font-medium">Robustness</th>
            </tr>
          </thead>
          <tbody>
            {sensitivity.map((param) => (
              <tr key={param.param_id} className="border-b border-border/50">
                <td className="py-2 pr-3">{param.param_id}</td>
                <td
                  className="py-2 pr-3 font-mono tabular-nums"
                  data-testid={`stat-sensitivity-${param.param_id}-peakiness`}
                >
                  {formatNumberOrNA(param.peakiness)}
                </td>
                <td className="py-2 pr-3">{param.robustness_label}</td>
              </tr>
            ))}
          </tbody>
          </table>
        </div>
      </details>

      <details data-testid="section-dsr" className="rounded-lg border border-border bg-card p-4 sm:p-6">
        <summary className="cursor-pointer py-2 font-medium text-foreground sm:py-0">Deflated Sharpe Ratio</summary>
        <div className="mt-4 space-y-2 text-muted-foreground">
          <p>
            DSR:{" "}
            <span data-testid="stat-dsr" className="font-mono tabular-nums text-foreground">
              {formatNumberOrNA(deflatedSharpe.dsr)}
            </span>
          </p>
          <p>
            Trials evaluated: <span className="font-mono tabular-nums text-foreground">{deflatedSharpe.n_trials}</span>
          </p>
        </div>
      </details>

      <details data-testid="section-regime" className="rounded-lg border border-border bg-card p-4 sm:p-6">
        <summary className="cursor-pointer py-2 font-medium text-foreground sm:py-0">Regime breakdown</summary>
        <div className="mt-4 space-y-2 text-muted-foreground">
          {regime.concentrated_regime && (
            <p data-testid="stat-concentrated-regime">
              {regime.concentrated_regime}:{" "}
              <span className="font-mono tabular-nums text-foreground">
                {formatPercentOrNA(regime.concentration_share)}
              </span>{" "}
              of gains
            </p>
          )}
          {regime.marginal_flags.map((flag) => (
            <p
              key={flag.flag}
              data-testid={`stat-marginal-${flag.flag}`}
              // Confidence drives WEIGHT (bold/full-opacity vs muted), never
              // hue -- the backend's `confidence` field is read as-is, not
              // re-thresholded, and no color is introduced either way.
              className={flag.confidence === "confirmed" ? "font-medium text-foreground" : "text-muted-foreground"}
            >
              Bull-concentrated:{" "}
              <span className="font-mono tabular-nums">+{(flag.excess * 100).toFixed(1)} pp</span> vs benchmark
              {flag.confidence === "provisional" ? " (provisional)" : ""}
            </p>
          ))}
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[22rem] text-left">
            <thead>
              <tr className="border-b border-border">
                <th className="py-2 pr-3 font-medium">Regime</th>
                <th className="py-2 pr-3 font-medium">Share of time</th>
                <th className="py-2 pr-3 font-medium">Sharpe</th>
              </tr>
            </thead>
            <tbody>
              {regime.breakdowns.map((b) => (
                <tr key={b.regime} className="border-b border-border/50">
                  <td className="py-2 pr-3">{b.regime}</td>
                  <td className="py-2 pr-3 font-mono tabular-nums">{formatPercentOrNA(b.share_of_time)}</td>
                  <td className="py-2 pr-3 font-mono tabular-nums" data-testid={`stat-regime-${b.regime}-sharpe`}>
                    {formatNumberOrNA(b.sharpe_ratio)}
                  </td>
                </tr>
              ))}
            </tbody>
            </table>
          </div>
        </div>
      </details>
    </section>
  );
}
