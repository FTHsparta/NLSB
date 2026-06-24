import type { RobustnessResult } from "@/lib/robustness/types";
import { BuyHoldComparison } from "./BuyHoldComparison";
import { RobustnessPanel } from "./RobustnessPanel";
import { VerdictCard } from "./VerdictCard";

export interface RobustnessResultViewProps {
  result: RobustnessResult;
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
  if (result.kind === "no_exit") {
    return <BuyHoldComparison noExit={result.no_exit} />;
  }

  return (
    <div data-testid="robustness-result-view">
      <VerdictCard verdict={result.verdict.verdict} reasons={result.verdict.reasons} />
      <RobustnessPanel
        sensitivity={result.sensitivity}
        walkForward={result.walk_forward}
        deflatedSharpe={result.deflated_sharpe}
        regime={result.regime}
      />
    </div>
  );
}
