import type { RobustnessResult } from "@/lib/robustness/types";
import { ResultsDisclaimer } from "@/components/chrome/Disclaimer";
import { MethodologyNote } from "@/components/chrome/MethodologyNote";
import { MOTION, staggerDelay } from "@/lib/motion";
import { BuyHoldComparison } from "./BuyHoldComparison";
import { RobustnessPanel } from "./RobustnessPanel";
import { VerdictCard } from "./VerdictCard";

export interface RobustnessResultViewProps {
  result: RobustnessResult;
}

/**
 * A minimal, defensive shape check (Phase 9). The frontend is a pure renderer
 * of backend judgment, but a truncated/garbled payload (a proxy that clipped
 * the body, a partial deploy, a shape drift) should degrade to a plain "raw
 * output" panel, NEVER throw and blank the page mid-render. This checks only
 * the fields this component and its children dereference -- it does not
 * re-derive or re-validate any judgment, just confirms the object is
 * structurally renderable.
 */
function isRenderableResult(result: unknown): result is RobustnessResult {
  if (!result || typeof result !== "object") return false;
  const r = result as Record<string, unknown>;

  if (r.kind === "no_exit") {
    return r.no_exit != null && typeof r.no_exit === "object";
  }
  if (r.kind === "full") {
    const verdict = r.verdict as Record<string, unknown> | null | undefined;
    return (
      verdict != null &&
      typeof verdict === "object" &&
      typeof verdict.verdict === "string" &&
      Array.isArray(verdict.reasons) &&
      Array.isArray(r.sensitivity) &&
      r.walk_forward != null &&
      r.deflated_sharpe != null &&
      r.regime != null
    );
  }
  return false;
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/**
 * The single entry point for rendering a `run_robustness` result. Branches
 * on `kind` exactly the way the backend orchestrator does -- a no-exit
 * result renders `BuyHoldComparison` and NOTHING else; it is structurally
 * impossible for `VerdictCard`/`RobustnessPanel` to appear alongside it,
 * because this function only calls one or the other, never both.
 *
 * For a "full" result, `VerdictCard` is rendered before `RobustnessPanel`
 * in JSX/DOM order -- the verdict is the headline, the four checks are
 * supporting detail underneath it. This component does no computation: it
 * passes the result object's fields straight through to the two render
 * components.
 */
export function RobustnessResultView({ result }: RobustnessResultViewProps) {
  if (!isRenderableResult(result)) {
    return (
      <div
        data-testid="results-fallback"
        role="alert"
        className={`rounded-lg border border-border bg-card p-6 text-sm text-foreground ${MOTION.enterSlide}`}
      >
        <p>These results couldn&apos;t be displayed — raw output below.</p>
        <details className="mt-3">
          <summary className="cursor-pointer select-none text-sm font-medium text-foreground">Raw output</summary>
          <pre
            data-testid="results-fallback-raw"
            className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap font-mono text-xs text-muted-foreground"
          >
            {safeStringify(result)}
          </pre>
        </details>
      </div>
    );
  }

  if (result.kind === "no_exit") {
    return (
      <>
        <div className={MOTION.enterSlide} style={staggerDelay(0)}>
          <BuyHoldComparison noExit={result.no_exit} />
        </div>
        <div className={MOTION.enterSlide} style={staggerDelay(1)}>
          <ResultsDisclaimer />
        </div>
      </>
    );
  }

  // Results reveal (Phase 11): panels stagger in, verdict card first. The
  // stagger order is DOM position and NOTHING else -- a PASS card and a
  // LIKELY_OVERFIT card get byte-identical animation classes and delays
  // (display-side corollary: motion is never a judgment channel).
  return (
    <div data-testid="robustness-result-view">
      <div className={MOTION.enterSlide} style={staggerDelay(0)}>
        <VerdictCard verdict={result.verdict.verdict} reasons={result.verdict.reasons} />
      </div>
      <div className={MOTION.enterSlide} style={staggerDelay(1)}>
        <RobustnessPanel
          sensitivity={result.sensitivity}
          walkForward={result.walk_forward}
          deflatedSharpe={result.deflated_sharpe}
          regime={result.regime}
          verdict={result.verdict.verdict}
        />
      </div>
      <div className={MOTION.enterSlide} style={staggerDelay(2)}>
        <MethodologyNote />
      </div>
      <div className={MOTION.enterSlide} style={staggerDelay(3)}>
        <ResultsDisclaimer />
      </div>
    </div>
  );
}
