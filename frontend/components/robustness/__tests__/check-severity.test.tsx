/**
 * Contract tests for the post-Phase-13 results redesign's per-check
 * semantic color (see `RobustnessPanel.tsx`'s module docstring for the
 * full rule, and `tests/visual/color-invariants.test.tsx` for the amended
 * blanket-monochrome invariant this narrows).
 *
 * Every severity bucket asserted here is driven ENTIRELY by a real,
 * backend-emitted field -- `robustness_label`, `marginal_flags[].confidence`,
 * `concentrated_regime`, or array emptiness -- read from real fixtures
 * (dumped from the actual orchestrator) wherever one exists for that
 * bucket. The one exception is the LIKELY_OVERFIT escalation case, where no
 * real fixture pairs a fragile sensitivity param with a LIKELY_OVERFIT
 * verdict: that test passes `verdict` directly as a component prop (an
 * override of a REAL fixture's own sensitivity array, the same controlled-
 * mutation pattern `contracts.test.tsx`'s CONTRACT 5 already uses), not a
 * hand-invented payload shape.
 *
 * VerdictCard's own verdict-enum -> color/icon mapping is unchanged by this
 * phase and already exhaustively covered by
 * `tests/visual/color-invariants.test.tsx`'s INV-1 block; it is not
 * duplicated here.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RobustnessPanel } from "../RobustnessPanel";
import type { RobustnessResult } from "@/lib/robustness/types";

import bullConcentrationConfirmedFixture from "@/fixtures/robustness/bull_concentration_confirmed.json";
import bullConcentrationProvisionalFixture from "@/fixtures/robustness/bull_concentration_provisional.json";
import passFixture from "@/fixtures/robustness/pass.json";
import shakyFixture from "@/fixtures/robustness/shaky.json";

const PASS_RESULT = passFixture as unknown as RobustnessResult;
const SHAKY_RESULT = shakyFixture as unknown as RobustnessResult;
const BULL_CONFIRMED = bullConcentrationConfirmedFixture as unknown as RobustnessResult;
const BULL_PROVISIONAL = bullConcentrationProvisionalFixture as unknown as RobustnessResult;

if (PASS_RESULT.kind !== "full") throw new Error("fixture is not a full result");
if (SHAKY_RESULT.kind !== "full") throw new Error("fixture is not a full result");
if (BULL_CONFIRMED.kind !== "full") throw new Error("fixture is not a full result");
if (BULL_PROVISIONAL.kind !== "full") throw new Error("fixture is not a full result");

function iconFor(container: HTMLElement, testId: "section-sensitivity" | "section-regime" | "section-walk-forward" | "section-dsr") {
  const section = screen.getByTestId(testId);
  return section.querySelector('[data-testid="check-outcome-icon"]') as HTMLElement;
}

describe("Parameter sensitivity: severity comes ONLY from the backend's own robustness_label", () => {
  it("a real PASS fixture with no fragile params renders the pass tier", () => {
    const { container } = render(
      <RobustnessPanel
        sensitivity={PASS_RESULT.sensitivity}
        walkForward={PASS_RESULT.walk_forward}
        deflatedSharpe={PASS_RESULT.deflated_sharpe}
        regime={PASS_RESULT.regime}
        verdict={PASS_RESULT.verdict.verdict}
      />,
    );
    expect(iconFor(container, "section-sensitivity")).toHaveAttribute("data-severity", "pass");
  });

  it("zero tunable parameters (a real, honestly-possible shape) renders the not-computed tier with the generic fallback string, never a fabricated cause", () => {
    render(
      <RobustnessPanel
        sensitivity={[]}
        walkForward={PASS_RESULT.walk_forward}
        deflatedSharpe={PASS_RESULT.deflated_sharpe}
        regime={PASS_RESULT.regime}
      />,
    );
    const icon = screen.getByTestId("section-sensitivity").querySelector('[data-testid="check-outcome-icon"]');
    expect(icon).toHaveAttribute("data-severity", "not-computed");
    expect(screen.getByTestId("section-sensitivity")).toHaveTextContent("Not computed for this strategy");
    expect(screen.getByTestId("section-sensitivity")).not.toHaveTextContent("N/A");
  });

  it("a real fragile-param fixture (UNTESTABLE, not LIKELY_OVERFIT) renders warn, not danger -- verdict alone doesn't escalate an untouched check", () => {
    expect(BULL_CONFIRMED.verdict.verdict).toBe("UNTESTABLE");
    const { container } = render(
      <RobustnessPanel
        sensitivity={BULL_CONFIRMED.sensitivity}
        walkForward={BULL_CONFIRMED.walk_forward}
        deflatedSharpe={BULL_CONFIRMED.deflated_sharpe}
        regime={BULL_CONFIRMED.regime}
        verdict={BULL_CONFIRMED.verdict.verdict}
      />,
    );
    expect(iconFor(container, "section-sensitivity")).toHaveAttribute("data-severity", "warn");
  });

  it("the SAME fragile-param data escalates to danger when the overall verdict is LIKELY_OVERFIT", () => {
    const { container } = render(
      <RobustnessPanel
        sensitivity={BULL_CONFIRMED.sensitivity}
        walkForward={BULL_CONFIRMED.walk_forward}
        deflatedSharpe={BULL_CONFIRMED.deflated_sharpe}
        regime={BULL_CONFIRMED.regime}
        verdict="LIKELY_OVERFIT"
      />,
    );
    expect(iconFor(container, "section-sensitivity")).toHaveAttribute("data-severity", "danger");
  });

  it("the pass-tier one-line read is byte-identical across two different real strategies -- proving it's a static caption, never strategy-specific prose", () => {
    const { container: c1 } = render(
      <RobustnessPanel
        sensitivity={PASS_RESULT.sensitivity}
        walkForward={PASS_RESULT.walk_forward}
        deflatedSharpe={PASS_RESULT.deflated_sharpe}
        regime={PASS_RESULT.regime}
      />,
    );
    const read1 = c1.querySelector('[data-testid="check-outcome-read"]')?.textContent;
    c1.remove();

    const { container: c2 } = render(
      <RobustnessPanel
        sensitivity={SHAKY_RESULT.sensitivity}
        walkForward={SHAKY_RESULT.walk_forward}
        deflatedSharpe={SHAKY_RESULT.deflated_sharpe}
        regime={SHAKY_RESULT.regime}
      />,
    );
    const read2 = c2.querySelector('[data-testid="check-outcome-read"]')?.textContent;

    // Different fixtures (different verdicts, different underlying runs),
    // same severity bucket -> same text.
    expect(PASS_RESULT.verdict.verdict).not.toBe(SHAKY_RESULT.verdict.verdict);
    expect(read1).toBe(read2);
  });
});

describe("Regime breakdown: severity comes ONLY from the backend's own confidence/concentration fields", () => {
  it("a real PASS fixture with no marginal flags and no concentration renders the pass tier", () => {
    const { container } = render(
      <RobustnessPanel
        sensitivity={PASS_RESULT.sensitivity}
        walkForward={PASS_RESULT.walk_forward}
        deflatedSharpe={PASS_RESULT.deflated_sharpe}
        regime={PASS_RESULT.regime}
      />,
    );
    expect(iconFor(container, "section-regime")).toHaveAttribute("data-severity", "pass");
  });

  it("a real PROVISIONAL bull-concentration fixture renders warn", () => {
    const { container } = render(
      <RobustnessPanel
        sensitivity={BULL_PROVISIONAL.sensitivity}
        walkForward={BULL_PROVISIONAL.walk_forward}
        deflatedSharpe={BULL_PROVISIONAL.deflated_sharpe}
        regime={BULL_PROVISIONAL.regime}
      />,
    );
    expect(iconFor(container, "section-regime")).toHaveAttribute("data-severity", "warn");
  });

  it("a real CONFIRMED bull-concentration fixture renders danger on its own -- confirmed is backend's own stronger tier, no verdict escalation needed", () => {
    const { container } = render(
      <RobustnessPanel
        sensitivity={BULL_CONFIRMED.sensitivity}
        walkForward={BULL_CONFIRMED.walk_forward}
        deflatedSharpe={BULL_CONFIRMED.deflated_sharpe}
        regime={BULL_CONFIRMED.regime}
      />,
    );
    expect(iconFor(container, "section-regime")).toHaveAttribute("data-severity", "danger");
  });

  it("a LIKELY_OVERFIT verdict never invents a regime flag on a clean check -- the pass tier holds even when passed verdict='LIKELY_OVERFIT'", () => {
    const { container } = render(
      <RobustnessPanel
        sensitivity={PASS_RESULT.sensitivity}
        walkForward={PASS_RESULT.walk_forward}
        deflatedSharpe={PASS_RESULT.deflated_sharpe}
        regime={PASS_RESULT.regime}
        verdict="LIKELY_OVERFIT"
      />,
    );
    expect(iconFor(container, "section-regime")).toHaveAttribute("data-severity", "pass");
  });
});

describe("Walk-forward and Deflated Sharpe Ratio: no backend-emitted per-check status exists yet -- neutral, never a fabricated pass/fail", () => {
  it("both stay neutral even under a LIKELY_OVERFIT verdict with a flagged sensitivity/regime alongside them", () => {
    const { container } = render(
      <RobustnessPanel
        sensitivity={BULL_CONFIRMED.sensitivity}
        walkForward={BULL_CONFIRMED.walk_forward}
        deflatedSharpe={BULL_CONFIRMED.deflated_sharpe}
        regime={BULL_CONFIRMED.regime}
        verdict="LIKELY_OVERFIT"
      />,
    );
    expect(iconFor(container, "section-walk-forward")).toHaveAttribute("data-severity", "neutral");
    expect(iconFor(container, "section-dsr")).toHaveAttribute("data-severity", "neutral");
    // Neutral means muted, not colored -- distinct from the danger-tier
    // sensitivity/regime rows rendered alongside them in this same payload.
    expect(iconFor(container, "section-walk-forward").className).toMatch(/text-muted-foreground/);
    expect(iconFor(container, "section-dsr").className).toMatch(/text-muted-foreground/);
  });
});

describe("Performance-metric VALUES stay monochrome regardless of row severity (the metrics-vs-judgments split)", () => {
  it("a danger-tier row's own pinned figures carry no check-* color", () => {
    render(
      <RobustnessPanel
        sensitivity={BULL_CONFIRMED.sensitivity}
        walkForward={BULL_CONFIRMED.walk_forward}
        deflatedSharpe={BULL_CONFIRMED.deflated_sharpe}
        regime={BULL_CONFIRMED.regime}
        verdict="LIKELY_OVERFIT"
      />,
    );
    expect(screen.getByTestId("stat-dsr").className).not.toMatch(/check-(?:pass|warn|danger)/);
    expect(screen.getByTestId(`stat-sensitivity-${BULL_CONFIRMED.sensitivity[0]!.param_id}-peakiness`).className).not.toMatch(
      /check-(?:pass|warn|danger)/,
    );
  });
});
