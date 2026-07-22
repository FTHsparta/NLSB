import type { DeflatedSharpeResult, ParamSensitivity, RegimeReport, Verdict, WalkForwardResult } from "@/lib/robustness/types";
import { formatNumberOrNA, formatPercentOrNA } from "@/lib/robustness/format";

export interface RobustnessPanelProps {
  sensitivity: ParamSensitivity[];
  walkForward: WalkForwardResult;
  deflatedSharpe: DeflatedSharpeResult;
  regime: RegimeReport;
  /** Optional: only used to escalate an ALREADY-flagged row's tier (warn ->
   * danger) when the overall verdict is LIKELY_OVERFIT. Never used to
   * invent a flag on a row whose own data shows nothing -- a clean check
   * doesn't turn red just because another check failed. Absent is treated
   * as "no escalation." */
  verdict?: Verdict;
}

/** The one frontend-authored vocabulary for row-level outcome coloring
 * (post-Phase-13 results redesign). Every value is chosen ENTIRELY from
 * backend-emitted fields (a real enum, an emitted confidence tier, or
 * array emptiness) -- never a threshold recomputed here. "neutral" is for
 * a check that ran and has real numbers but carries NO backend-emitted
 * per-check status at all (walk-forward, DSR: see the module docstring
 * below); "not-computed" is for a check with genuinely nothing to show
 * (e.g. zero tunable parameters). Neither is a fabricated pass/fail. */
type RowSeverity = "pass" | "warn" | "danger" | "neutral" | "not-computed";

/**
 * Supporting detail for the verdict already rendered above this component
 * (see `RobustnessResultView` for render order). Every figure here is
 * displayed verbatim from the backend result, formatted only -- nothing in
 * this component computes a pass/fail or re-derives the verdict.
 * Collapsible (`<details>`) and visually secondary: this is the "show your
 * work," not the headline.
 *
 * Color rule (amended, post-Phase-13 -- see tests/visual/color-invariants.test.tsx
 * for the pinned version of this rule): performance-metric VALUES stay
 * monochrome everywhere in this component, unchanged -- a raw Sharpe/return
 * number is never colored by direction. Each check's ROW may carry semantic
 * `check-pass`/`check-warn`/`check-danger` color (a token family distinct
 * from and subordinate to `--verdict-*`, which stays VerdictCard-exclusive),
 * but ONLY when the backend itself emitted a classifiable signal for that
 * specific check:
 *   - Parameter sensitivity: the backend's own `robustness_label` per
 *     param ("fragile (sharp peak)" is the one label `verdict.py` itself
 *     treats as flag-worthy).
 *   - Regime breakdown: the backend's own `marginal_flags[].confidence`
 *     ("confirmed"/"provisional") and `concentrated_regime` presence.
 *   - Walk-forward and Deflated Sharpe Ratio have NO backend-emitted
 *     per-check status today (verdict.py's thresholds for both are
 *     internal to `compute_verdict`, never returned as a field) -- their
 *     rows render with a NEUTRAL, uncolored marker rather than a fabricated
 *     pass color. PARKED: a backend follow-up to emit an explicit status
 *     enum for these two checks, mirroring sensitivity's `robustness_label`,
 *     is needed before they can honestly carry color.
 */
export function RobustnessPanel({ sensitivity, walkForward, deflatedSharpe, regime, verdict }: RobustnessPanelProps) {
  const sensitivitySeverity = sensitivitySeverityOf(sensitivity, verdict);
  const regimeSeverityValue = regimeSeverityOf(regime, verdict);

  return (
    <section data-testid="robustness-panel" className="mt-8 space-y-6 text-sm">
      <details data-testid="section-walk-forward" className={detailsClass("neutral")}>
        <summary className={summaryClass()}>
          <RowHeader severity="neutral" name="Walk-forward validation" read="Out-of-sample performance across rolling folds." />
        </summary>
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

      <details data-testid="section-sensitivity" className={detailsClass(sensitivitySeverity)}>
        <summary className={summaryClass()}>
          <RowHeader severity={sensitivitySeverity} name="Parameter sensitivity" read={sensitivityRead(sensitivitySeverity)} />
        </summary>
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

      <details data-testid="section-dsr" className={detailsClass("neutral")}>
        <summary className={summaryClass()}>
          <RowHeader
            severity="neutral"
            name="Deflated Sharpe Ratio"
            read="Sharpe ratio adjusted for the number of parameter configurations tried."
          />
        </summary>
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

      <details data-testid="section-regime" className={detailsClass(regimeSeverityValue)}>
        <summary className={summaryClass()}>
          <RowHeader severity={regimeSeverityValue} name="Regime breakdown" read={regimeRead(regimeSeverityValue)} />
        </summary>
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
              // re-thresholded, and no color is introduced either way. This
              // element is UNCHANGED by the results redesign; the new
              // semantic color lives on the row header above, not here.
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

/** `fragile_params` in verdict.py's own `compute_verdict` is built from this
 * EXACT string equality -- reusing the same literal here is reading the
 * backend's classification, not recomputing a threshold. */
const FRAGILE_LABEL = "fragile (sharp peak)";
const INSUFFICIENT_DATA_LABEL = "insufficient_data";

function sensitivitySeverityOf(sensitivity: ParamSensitivity[], verdict?: Verdict): RowSeverity {
  if (sensitivity.length === 0) return "not-computed";
  if (sensitivity.every((s) => s.robustness_label === INSUFFICIENT_DATA_LABEL)) return "not-computed";
  const flagged = sensitivity.some((s) => s.robustness_label === FRAGILE_LABEL);
  if (!flagged) return "pass";
  return verdict === "LIKELY_OVERFIT" ? "danger" : "warn";
}

function regimeSeverityOf(regime: RegimeReport, verdict?: Verdict): RowSeverity {
  const hasConcentration = regime.concentrated_regime != null;
  const hasFlags = regime.marginal_flags.length > 0;
  if (!hasConcentration && !hasFlags) return "pass";
  // Concentration and a "confirmed" flag are backend's OWN stronger tier
  // (not a frontend threshold) -- either escalates to danger on its own;
  // LIKELY_OVERFIT can also escalate an already-flagged row, same as
  // sensitivity, but never invents a flag where the data shows none.
  const backendStrong = hasConcentration || regime.marginal_flags.some((f) => f.confidence === "confirmed");
  if (backendStrong || verdict === "LIKELY_OVERFIT") return "danger";
  return "warn";
}

function sensitivityRead(severity: RowSeverity): string {
  if (severity === "not-computed") return NOT_COMPUTED_FALLBACK;
  if (severity === "pass") return "Performance holds across the tested parameter range.";
  return "One or more parameters have a narrow, sensitive optimum.";
}

function regimeRead(severity: RowSeverity): string {
  if (severity === "pass") return "No single market regime dominates this strategy's gains.";
  return "Gains lean on a specific market regime more than a buy-and-hold benchmark.";
}

/** The ONE generic fallback string this component is authorized to invent
 * (display-side corollary) -- used only when a check has genuinely nothing
 * to show, never as a guess at why. */
const NOT_COMPUTED_FALLBACK = "Not computed for this strategy";

const SEVERITY_COPY: Record<RowSeverity, { glyph: string; textClass: string; accentClass: string; tintClass: string }> = {
  pass: { glyph: "✓", textClass: "text-check-pass", accentClass: "", tintClass: "" },
  warn: { glyph: "!", textClass: "text-check-warn", accentClass: "border-l-4 border-l-check-warn", tintClass: "bg-check-warn/10" },
  danger: {
    glyph: "!",
    textClass: "text-check-danger",
    accentClass: "border-l-4 border-l-check-danger",
    tintClass: "bg-check-danger/10",
  },
  neutral: { glyph: "–", textClass: "text-muted-foreground", accentClass: "", tintClass: "" },
  "not-computed": { glyph: "–", textClass: "text-muted-foreground", accentClass: "", tintClass: "" },
};

function detailsClass(severity: RowSeverity): string {
  const { accentClass, tintClass } = SEVERITY_COPY[severity];
  return `rounded-lg border border-border bg-card p-4 sm:p-6 ${accentClass} ${tintClass}`.trim().replace(/\s+/g, " ");
}

function summaryClass(): string {
  return "flex w-full cursor-pointer items-baseline gap-3 py-2 sm:py-0";
}

// A passed/neutral/not-computed check keeps its READ text neutral -- only
// the icon carries color for a quiet pass; only warn/danger carry color
// on the read text too, per the asymmetric-emphasis rule ("problems are
// louder than passes").
const READ_TEXT_COLORED: Record<RowSeverity, boolean> = {
  pass: false,
  neutral: false,
  "not-computed": false,
  warn: true,
  danger: true,
};

function RowHeader({ severity, name, read }: { severity: RowSeverity; name: string; read: string }) {
  const copy = SEVERITY_COPY[severity];
  const readClass = READ_TEXT_COLORED[severity] ? copy.textClass : "text-muted-foreground";
  return (
    <>
      <span aria-hidden="true" data-testid="check-outcome-icon" data-severity={severity} className={`font-semibold ${copy.textClass}`}>
        {copy.glyph}
      </span>
      <span className="font-medium text-foreground">{name}</span>
      <span data-testid="check-outcome-read" className={`text-xs font-normal ${readClass}`}>
        {read}
      </span>
    </>
  );
}
