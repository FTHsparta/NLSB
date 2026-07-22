/**
 * Contract tests for the verdict-first renderer (Phase 5a). Fixtures are
 * loaded from `frontend/fixtures/robustness/*.json` -- dumped by
 * `backend/scripts/dump_robustness_fixtures.py` from the REAL orchestrator,
 * not hand-authored, so these tests can't drift from the real schema
 * without the fixture-generation script (and its pinning backend test)
 * catching it first.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BuyHoldComparison } from "../BuyHoldComparison";
import { RobustnessResultView } from "../RobustnessResultView";
import { VerdictCard } from "../VerdictCard";

import bullConcentrationConfirmedFixture from "@/fixtures/robustness/bull_concentration_confirmed.json";
import bullConcentrationProvisionalFixture from "@/fixtures/robustness/bull_concentration_provisional.json";
import bullConcentrationWithVerdictFixture from "@/fixtures/robustness/bull_concentration_with_verdict.json";
import likelyOverfitFixture from "@/fixtures/robustness/likely_overfit.json";
import noExitFixture from "@/fixtures/robustness/no_exit.json";
import passFixture from "@/fixtures/robustness/pass.json";
import untestableFixture from "@/fixtures/robustness/untestable.json";

import { RobustnessPanel } from "../RobustnessPanel";

import type { RobustnessResult } from "@/lib/robustness/types";

const PASS_RESULT = passFixture as unknown as RobustnessResult;
const UNTESTABLE_RESULT = untestableFixture as unknown as RobustnessResult;
const LIKELY_OVERFIT_RESULT = likelyOverfitFixture as unknown as RobustnessResult;
const NO_EXIT_RESULT = noExitFixture as unknown as RobustnessResult;
const BULL_CONCENTRATION_CONFIRMED_RESULT = bullConcentrationConfirmedFixture as unknown as RobustnessResult;
const BULL_CONCENTRATION_PROVISIONAL_RESULT = bullConcentrationProvisionalFixture as unknown as RobustnessResult;
const BULL_CONCENTRATION_WITH_VERDICT_RESULT = bullConcentrationWithVerdictFixture as unknown as RobustnessResult;

describe("CONTRACT 1: verdict leads, raw figures follow", () => {
  it("places the verdict label and reason before any raw Sharpe/return figure in DOM order", () => {
    render(<RobustnessResultView result={LIKELY_OVERFIT_RESULT} />);

    const verdictLabel = screen.getByTestId("verdict-label");
    const firstReason = screen.getAllByTestId("verdict-reason")[0];
    const firstRawFigure = screen.getByTestId("stat-aggregate-is-sharpe");

    // DOCUMENT_POSITION_FOLLOWING (4): verdictLabel/firstReason come BEFORE firstRawFigure.
    expect(verdictLabel.compareDocumentPosition(firstRawFigure) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(firstReason.compareDocumentPosition(firstRawFigure) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Sanity: the raw figure is not literally absent/empty (a vacuous "before" otherwise).
    expect(firstRawFigure.textContent).not.toBe("");
  });

  it("never places a raw figure before the verdict label", () => {
    render(<RobustnessResultView result={LIKELY_OVERFIT_RESULT} />);
    const verdictLabel = screen.getByTestId("verdict-label");
    const rawFigures = [
      screen.getByTestId("stat-aggregate-is-sharpe"),
      screen.getByTestId("stat-aggregate-oos-sharpe"),
      screen.getByTestId("stat-dsr"),
    ];
    for (const figure of rawFigures) {
      expect(figure.compareDocumentPosition(verdictLabel) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    }
  });
});

describe("CONTRACT 2: UNTESTABLE is a first-class verdict, not demoted", () => {
  it("renders UNTESTABLE through the same VerdictCard component, with its reason present", () => {
    render(<VerdictCard verdict="UNTESTABLE" reasons={UNTESTABLE_RESULT.kind === "full" ? UNTESTABLE_RESULT.verdict.reasons : []} />);

    const card = screen.getByTestId("verdict-card");
    expect(card).toHaveAttribute("data-verdict", "UNTESTABLE");
    expect(screen.getByTestId("verdict-label")).toHaveTextContent("Untestable");
    expect(screen.getAllByTestId("verdict-reason").length).toBeGreaterThan(0);
  });

  it("produces the identical card structure (same testids, same hierarchy) as a PASS verdict", () => {
    const { container: passContainer } = render(<VerdictCard verdict="PASS" reasons={["no flags"]} />);
    const passTestIds = Array.from(passContainer.querySelectorAll("[data-testid]")).map((el) => el.getAttribute("data-testid"));

    const { container: untestableContainer } = render(<VerdictCard verdict="UNTESTABLE" reasons={["not enough evidence"]} />);
    const untestableTestIds = Array.from(untestableContainer.querySelectorAll("[data-testid]")).map((el) =>
      el.getAttribute("data-testid"),
    );

    expect(untestableTestIds).toEqual(passTestIds);
  });

  it("renders the real UNTESTABLE fixture end to end via RobustnessResultView with full prominence", () => {
    render(<RobustnessResultView result={UNTESTABLE_RESULT} />);
    const card = screen.getByTestId("verdict-card");
    expect(card).toHaveAttribute("data-verdict", "UNTESTABLE");
    expect(screen.getByTestId("verdict-label")).toHaveTextContent("Untestable");
    // The plain-English reason ("not enough... to validate") is shown like
    // any other verdict's reasons -- not hidden, not collapsed.
    const reasons = screen.getAllByTestId("verdict-reason").map((el) => el.textContent);
    expect(reasons.some((r) => r?.toLowerCase().includes("too few") || r?.toLowerCase().includes("too thin"))).toBe(true);
  });
});

describe("CONTRACT 3: no-exit renders BuyHoldComparison only", () => {
  it("renders BuyHoldComparison and never VerdictCard/RobustnessPanel for a NoExitResult", () => {
    render(<RobustnessResultView result={NO_EXIT_RESULT} />);

    expect(screen.getByTestId("buy-hold-comparison")).toBeInTheDocument();
    expect(screen.queryByTestId("verdict-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("robustness-panel")).not.toBeInTheDocument();
  });

  it("never renders a PASS/SHAKY/LIKELY_OVERFIT/UNTESTABLE label anywhere for no-exit", () => {
    render(<RobustnessResultView result={NO_EXIT_RESULT} />);
    const verdictWords = ["PASS", "SHAKY", "LIKELY_OVERFIT", "UNTESTABLE"];
    for (const word of verdictWords) {
      expect(screen.queryByText(word, { exact: false })).not.toBeInTheDocument();
    }
  });
});

describe("CONTRACT 4: displayed figures equal the result object's figures verbatim", () => {
  it("renders walk-forward and DSR figures matching the fixture exactly (formatting only)", () => {
    if (LIKELY_OVERFIT_RESULT.kind !== "full") throw new Error("fixture is not a full result");
    render(<RobustnessResultView result={LIKELY_OVERFIT_RESULT} />);

    const expectedIsSharpe = LIKELY_OVERFIT_RESULT.walk_forward.aggregate_is_sharpe!.toFixed(2);
    const expectedOosSharpe = LIKELY_OVERFIT_RESULT.walk_forward.aggregate_oos_sharpe!.toFixed(2);
    const expectedDsr = LIKELY_OVERFIT_RESULT.deflated_sharpe.dsr!.toFixed(2);

    expect(screen.getByTestId("stat-aggregate-is-sharpe")).toHaveTextContent(expectedIsSharpe);
    expect(screen.getByTestId("stat-aggregate-oos-sharpe")).toHaveTextContent(expectedOosSharpe);
    expect(screen.getByTestId("stat-dsr")).toHaveTextContent(expectedDsr);

    for (const fold of LIKELY_OVERFIT_RESULT.walk_forward.folds) {
      const isCell = screen.getByTestId(`stat-fold-${fold.fold_index}-is-sharpe`);
      expect(isCell).toHaveTextContent(fold.is_sharpe === null ? "N/A" : fold.is_sharpe.toFixed(2));
    }
  });

  it("renders no-exit benchmark figures matching the fixture exactly", () => {
    if (NO_EXIT_RESULT.kind !== "no_exit") throw new Error("fixture is not a no_exit result");
    render(<BuyHoldComparison noExit={NO_EXIT_RESULT.no_exit} />);

    const strategy = NO_EXIT_RESULT.no_exit.strategy_metrics!;
    const benchmark = NO_EXIT_RESULT.no_exit.benchmark_metrics!;

    expect(screen.getByTestId("stat-strategy-total_return")).toHaveTextContent(`${(strategy.total_return * 100).toFixed(1)}%`);
    expect(screen.getByTestId("stat-benchmark-total_return")).toHaveTextContent(`${(benchmark.total_return * 100).toFixed(1)}%`);
    expect(screen.getByTestId("first-entry-date")).toHaveTextContent(NO_EXIT_RESULT.no_exit.first_entry_date!);
  });

  it("renders PASS figures matching the fixture exactly (positive-result sanity check, not just the failure cases)", () => {
    if (PASS_RESULT.kind !== "full") throw new Error("fixture is not a full result");
    render(<RobustnessResultView result={PASS_RESULT} />);
    const expectedDegradation = PASS_RESULT.walk_forward.degradation!.toFixed(2);
    expect(screen.getByTestId("stat-degradation")).toHaveTextContent(expectedDegradation);
    expect(within(screen.getByTestId("verdict-card")).getByTestId("verdict-label")).toHaveTextContent("Pass");
  });
});

/**
 * CONTRACT 5 (Phase 4d.1): the marginal bull-concentration render path,
 * exercised end to end via RobustnessResultView against the two REAL
 * fixtures dumped from the real orchestrator (`build_bull_concentration_confirmed`/
 * `build_bull_concentration_provisional`, pinned backend-side in
 * `test_robustness_fixtures.py`). 4d proved the flag FIRES; nothing
 * proved it RENDERS until these tests -- before this, all five orchestrator
 * fixtures had an empty `marginal_flags`, so this entire branch in
 * `RobustnessPanel` was dead code as far as the test suite could tell.
 */
describe("CONTRACT 5: marginal bull-concentration flag renders, not just fires", () => {
  it("renders a confirmed flag at full prominence, with no '(provisional)' suffix", () => {
    // Phase 7 retired the amber/zinc color tokens this assertion originally
    // checked (a per-check saturated color, forbidden under the strict
    // monochrome rule) in favor of weight-only prominence -- the contract
    // (confirmed is bolder/brighter than provisional) is unchanged.
    render(<RobustnessResultView result={BULL_CONCENTRATION_CONFIRMED_RESULT} />);
    const flagEl = screen.getByTestId("stat-marginal-bull_concentration");
    expect(flagEl).toHaveClass("text-foreground");
    expect(flagEl).not.toHaveClass("text-muted-foreground");
    expect(flagEl.textContent).not.toContain("(provisional)");
  });

  it("renders a provisional flag muted, with a '(provisional)' suffix", () => {
    render(<RobustnessResultView result={BULL_CONCENTRATION_PROVISIONAL_RESULT} />);
    const flagEl = screen.getByTestId("stat-marginal-bull_concentration");
    expect(flagEl).toHaveClass("text-muted-foreground");
    expect(flagEl).not.toHaveClass("text-foreground");
    expect(flagEl.textContent).toContain("(provisional)");
  });

  it("renders the excess margin as '+X.X pp vs benchmark' matching the fixture verbatim, with no client-side rounding/recomputation beyond display formatting", () => {
    if (BULL_CONCENTRATION_CONFIRMED_RESULT.kind !== "full") throw new Error("fixture is not a full result");
    render(<RobustnessResultView result={BULL_CONCENTRATION_CONFIRMED_RESULT} />);
    const excess = BULL_CONCENTRATION_CONFIRMED_RESULT.regime.marginal_flags[0]!.excess;
    const expectedText = `+${(excess * 100).toFixed(1)} pp vs benchmark`;
    expect(screen.getByTestId("stat-marginal-bull_concentration")).toHaveTextContent(expectedText);
  });

  it("reads the confidence field as-is and never re-thresholds excess itself", () => {
    // Controlled mutation of a REAL fixture, not a fabricated payload: the
    // confirmed fixture's excess (0.3012) is well past
    // MARGINAL_BULL_EXCESS_CONFIRMED_THRESHOLD (0.20) -- if the component
    // were re-deriving confidence from excess instead of reading the
    // backend's `confidence` field, overriding ONLY that field to
    // "provisional" would have no visible effect, since the excess value
    // still says "confirmed". Asserting the muted/provisional render wins
    // proves the client never re-thresholds.
    if (BULL_CONCENTRATION_CONFIRMED_RESULT.kind !== "full") throw new Error("fixture is not a full result");
    const mutatedRegime = {
      ...BULL_CONCENTRATION_CONFIRMED_RESULT.regime,
      marginal_flags: [{ ...BULL_CONCENTRATION_CONFIRMED_RESULT.regime.marginal_flags[0]!, confidence: "provisional" as const }],
    };

    render(
      <RobustnessPanel
        sensitivity={BULL_CONCENTRATION_CONFIRMED_RESULT.sensitivity}
        walkForward={BULL_CONCENTRATION_CONFIRMED_RESULT.walk_forward}
        deflatedSharpe={BULL_CONCENTRATION_CONFIRMED_RESULT.deflated_sharpe}
        regime={mutatedRegime}
      />,
    );

    const flagEl = screen.getByTestId("stat-marginal-bull_concentration");
    expect(flagEl).toHaveClass("text-muted-foreground");
    expect(flagEl).not.toHaveClass("text-foreground");
    expect(flagEl.textContent).toContain("(provisional)");
  });
});

/**
 * CONTRACT 6 (Phase 9): the unexpected-shape fallback. The frontend is a pure
 * renderer, but a truncated/garbled payload must degrade to a plain raw-output
 * panel, never throw and blank the page. The shape check confirms only the
 * fields this tree dereferences -- it re-derives no judgment.
 */
describe("CONTRACT 6: unexpected-shape payload degrades to a raw-output fallback, never throws", () => {
  it("renders the fallback panel (not a crash) for a truncated full payload", () => {
    const truncated = { kind: "full", verdict: null } as unknown as RobustnessResult;
    expect(() => render(<RobustnessResultView result={truncated} />)).not.toThrow();
    expect(screen.getByTestId("results-fallback")).toBeInTheDocument();
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verdict-card")).not.toBeInTheDocument();
  });

  it("renders the fallback for an unknown kind and preserves the raw JSON for debugging", () => {
    const weird = { kind: "banana", foo: 42 } as unknown as RobustnessResult;
    render(<RobustnessResultView result={weird} />);
    expect(screen.getByTestId("results-fallback-raw").textContent).toContain("banana");
  });

  it("a valid full result still renders normally -- the fallback never false-positives", () => {
    render(<RobustnessResultView result={PASS_RESULT} />);
    expect(screen.getByTestId("robustness-result-view")).toBeInTheDocument();
    expect(screen.queryByTestId("results-fallback")).not.toBeInTheDocument();
  });
});

/**
 * CONTRACT 7 (Phase 9): the methodology note ("How to read a verdict") is
 * reachable from the results surface and covers all four verdicts. Educational
 * chrome, authored generically -- it never restates a specific run's numbers.
 */
describe("CONTRACT 7: methodology note reachable from results, headings for all four verdicts", () => {
  it("renders the methodology panel with a heading for each verdict", () => {
    render(<RobustnessResultView result={PASS_RESULT} />);
    expect(screen.getByTestId("methodology-note")).toBeInTheDocument();
    for (const v of ["PASS", "SHAKY", "LIKELY_OVERFIT", "UNTESTABLE"]) {
      expect(screen.getByTestId(`methodology-heading-${v}`)).toBeInTheDocument();
    }
  });

  it("is NOT rendered on the no-exit surface (there is no verdict to explain there)", () => {
    render(<RobustnessResultView result={NO_EXIT_RESULT} />);
    expect(screen.queryByTestId("methodology-note")).not.toBeInTheDocument();
  });
});

/**
 * CONTRACT 8 (Phase 9): a real fixture pairing a NON-UNTESTABLE verdict with a
 * populated bull-concentration flag. Before this, every full fixture that
 * carried the flag was UNTESTABLE, so nothing pinned that the flag renders
 * *alongside a judgment verdict card* -- exactly the case the live smoke test
 * once showed but no automated fixture held. Dumped from the real orchestrator
 * (`build_bull_concentration_with_verdict`, pinned in `test_robustness_fixtures.py`).
 */
describe("CONTRACT 8: bull-concentration flag renders alongside a real (non-UNTESTABLE) verdict card", () => {
  it("shows both the verdict card and the confirmed flag in one result", () => {
    if (BULL_CONCENTRATION_WITH_VERDICT_RESULT.kind !== "full") throw new Error("fixture is not a full result");
    expect(BULL_CONCENTRATION_WITH_VERDICT_RESULT.verdict.verdict).not.toBe("UNTESTABLE");

    render(<RobustnessResultView result={BULL_CONCENTRATION_WITH_VERDICT_RESULT} />);

    const card = screen.getByTestId("verdict-card");
    expect(card).toHaveAttribute("data-verdict", BULL_CONCENTRATION_WITH_VERDICT_RESULT.verdict.verdict);

    const flagEl = screen.getByTestId("stat-marginal-bull_concentration");
    expect(flagEl).toBeInTheDocument();
    // Confirmed -> full-prominence (bold/foreground), no provisional suffix,
    // and the excess printed verbatim from the fixture (display formatting only).
    expect(flagEl).toHaveClass("text-foreground");
    expect(flagEl.textContent).not.toContain("(provisional)");
    const excess = BULL_CONCENTRATION_WITH_VERDICT_RESULT.regime.marginal_flags[0]!.excess;
    expect(flagEl).toHaveTextContent(`+${(excess * 100).toFixed(1)} pp vs benchmark`);
  });
});

/**
 * CONTRACT 9 (pre-launch "How Deflate works" pass): the static limitations
 * pointer on the results view. It is generic chrome about the SYSTEM's fixed
 * cost/fill model -- constant text, no per-run value -- and it must remain a
 * SIBLING of the verdict/checks wrappers: never inside VerdictCard or
 * RobustnessPanel, whose verdict color/motion scoping is pinned elsewhere.
 */
describe("CONTRACT 9: static limitations pointer is a sibling below the checks", () => {
  it("renders below the checks panel and links to /methodology#limitations", () => {
    render(<RobustnessResultView result={PASS_RESULT} />);

    const pointer = screen.getByTestId("results-limitations-pointer");
    const panel = screen.getByTestId("robustness-panel");
    // Panel comes BEFORE the pointer in DOM order (pointer sits below the checks).
    expect(panel.compareDocumentPosition(pointer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    const link = within(pointer).getByRole("link");
    expect(link).toHaveAttribute("href", "/methodology#limitations");
  });

  it("is never nested inside VerdictCard or RobustnessPanel", () => {
    render(<RobustnessResultView result={PASS_RESULT} />);
    const pointer = screen.getByTestId("results-limitations-pointer");
    expect(screen.getByTestId("verdict-card").contains(pointer)).toBe(false);
    expect(screen.getByTestId("robustness-panel").contains(pointer)).toBe(false);
  });

  it("carries byte-identical text for every verdict -- no per-run content", () => {
    const texts = [PASS_RESULT, UNTESTABLE_RESULT, LIKELY_OVERFIT_RESULT].map((result) => {
      const { unmount } = render(<RobustnessResultView result={result} />);
      const text = screen.getByTestId("results-limitations-pointer").textContent;
      unmount();
      return text;
    });
    expect(texts[1]).toBe(texts[0]);
    expect(texts[2]).toBe(texts[0]);
    expect(texts[0]).toContain("close to gross");
    expect(texts[0]).toContain("next-day-close fills");
  });
});
