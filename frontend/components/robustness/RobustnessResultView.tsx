import Link from "next/link";

import type { RobustnessResult } from "@/lib/robustness/types";
import { ResultsDisclaimer } from "@/components/chrome/Disclaimer";
import { MethodologyNote } from "@/components/chrome/MethodologyNote";
import { MOTION, staggerDelay } from "@/lib/motion";
import { BuyHoldComparison } from "./BuyHoldComparison";
import { RobustnessPanel } from "./RobustnessPanel";
import { TestedWindow } from "./TestedWindow";
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
          <TestedWindow window={result.window} />
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
        {/* Directly under the headline, and a SIBLING of VerdictCard so it
            never inherits the verdict color scoping (INV-2). Constant classes
            regardless of the values -- the window is information, not a
            judgment channel. */}
        <TestedWindow window={result.window} />
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
      {/* Static limitations pointer (pre-launch honesty pass): a SIBLING of
          the verdict/checks wrappers, never inside VerdictCard or
          RobustnessPanel — it must not touch their verdict color/motion
          scoping. Generic chrome about the system's fixed cost/fill model:
          constant text, constant classes, no per-run value (display-side
          corollary), so the motion signature stays verdict-blind. */}
      <div className={MOTION.enterSlide} style={staggerDelay(2)}>
        <p data-testid="results-limitations-pointer" className="mt-6 text-sm text-muted-foreground">
          These results are close to gross and assume next-day-close fills —{" "}
          <Link
            href="/methodology#limitations"
            className={`underline underline-offset-2 ${MOTION.interactive} hover:text-foreground`}
          >
            see what Deflate does not model
          </Link>{" "}
          before relying on them.
        </p>
      </div>
      <div className={MOTION.enterSlide} style={staggerDelay(3)}>
        <MethodologyNote />
      </div>
      <div className={MOTION.enterSlide} style={staggerDelay(4)}>
        <ResultsDisclaimer />
      </div>
    </div>
  );
}
