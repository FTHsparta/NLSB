/**
 * Phase 7 visual-pass invariants. The display-side corollary's visual
 * extension: the verdict accent is the ONLY saturated color anywhere on
 * screen, selected solely by the backend's verdict enum string through
 * `VerdictCard`'s static lookup -- never by a client-side threshold, and
 * never reused by any other component.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssumptionsView } from "@/components/translation/AssumptionsView";
import { ConfirmGate } from "@/components/translation/ConfirmGate";
import { TranslateFlow } from "@/components/translation/TranslateFlow";
import { TranslateInputView } from "@/components/translation/TranslateInputView";
import { BuyHoldComparison } from "@/components/robustness/BuyHoldComparison";
import { RobustnessPanel } from "@/components/robustness/RobustnessPanel";
import { VerdictCard } from "@/components/robustness/VerdictCard";

import type { TranslationApi } from "@/lib/translation/api";
import type { RobustnessResult, Verdict } from "@/lib/robustness/types";
import type { TranslationPayload } from "@/lib/translation/types";

import bullConcentrationConfirmedFixture from "@/fixtures/robustness/bull_concentration_confirmed.json";
import noExitResultFixture from "@/fixtures/robustness/no_exit.json";
import noExitWarningFixture from "@/fixtures/translation/no_exit_warning.json";

const BULL_CONCENTRATION_CONFIRMED = bullConcentrationConfirmedFixture as unknown as RobustnessResult;
const NO_EXIT_RESULT = noExitResultFixture as unknown as RobustnessResult;
const NO_EXIT_WARNING = noExitWarningFixture as unknown as TranslationPayload;

if (BULL_CONCENTRATION_CONFIRMED.kind !== "full") throw new Error("fixture is not a full result");
if (NO_EXIT_RESULT.kind !== "no_exit") throw new Error("fixture is not a no_exit result");

/**
 * Any Tailwind utility applying a saturated hue at a numbered shade, e.g.
 * a text/bg/border utility built from "amber" + "-700", or "sky" + "-500".
 * (Spelled out as concatenation, not a literal class string, so this
 * comment itself doesn't get picked up by Tailwind's content scanner and
 * generate dead CSS for the very thing it's banning.) Deliberately does
 * NOT match the `verdict-*`/`background`/`foreground`/`card`/`muted`/
 * `border`/`input`/`primary`/`accent` tokens, which carry no such hue name
 * and no numbered shade -- those are the monochrome (or, for `verdict-*`,
 * intentionally-scoped) tokens this phase introduces.
 */
const SATURATED_COLOR_CLASS = /\b(?:bg|text|border(?:-[trblxy])?|ring|from|via|to|fill|stroke)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/;

const VERDICTS: Verdict[] = ["PASS", "SHAKY", "LIKELY_OVERFIT", "UNTESTABLE"];

describe("INV-1: verdict accent is selected solely by the verdict enum string, via the static lookup", () => {
  it.each(VERDICTS)("%s maps to its own verdict-* token, not a numeric Tailwind shade", (verdict) => {
    render(<VerdictCard verdict={verdict} reasons={["a reason"]} />);
    const card = screen.getByTestId("verdict-card");
    const label = screen.getByTestId("verdict-label");

    // The accent comes from a `verdict-*` token (this enum value's own
    // entry in the static lookup) -- never a bare numeric Tailwind shade,
    // which would mean some other code path picked the color.
    expect(card.className).toMatch(/verdict-/);
    expect(label.className).toMatch(/verdict-/);
    expect(card.className).not.toMatch(SATURATED_COLOR_CLASS);
    expect(label.className).not.toMatch(SATURATED_COLOR_CLASS);
  });

  it("PASS, SHAKY, and LIKELY_OVERFIT each map to a DIFFERENT verdict token from one another", () => {
    const tokens = new Map<Verdict, string>();
    for (const verdict of (["PASS", "SHAKY", "LIKELY_OVERFIT"] as Verdict[])) {
      const { unmount } = render(<VerdictCard verdict={verdict} reasons={[]} />);
      const match = screen.getByTestId("verdict-label").className.match(/verdict-[a-z]+/);
      tokens.set(verdict, match?.[0] ?? "");
      unmount();
    }
    const values = Array.from(tokens.values());
    expect(new Set(values).size).toBe(3);
  });

  it("UNTESTABLE maps to the NEUTRAL verdict-untestable token, never one of PASS/SHAKY/LIKELY_OVERFIT's judgment hues", () => {
    render(<VerdictCard verdict="UNTESTABLE" reasons={[]} />);
    const label = screen.getByTestId("verdict-label");
    expect(label.className).toMatch(/verdict-untestable/);
    expect(label.className).not.toMatch(/verdict-pass\b/);
    expect(label.className).not.toMatch(/verdict-shaky\b/);
    expect(label.className).not.toMatch(/verdict-overfit\b/);
  });

  it("UNTESTABLE renders at the SAME structural prominence as PASS -- same component, same testids, same size classes", () => {
    const { container: passContainer } = render(<VerdictCard verdict="PASS" reasons={["x"]} />);
    const passLabel = screen.getByTestId("verdict-label");
    const passSizeClasses = passLabel.className.replace(/verdict-pass/g, "");
    passContainer.remove();

    render(<VerdictCard verdict="UNTESTABLE" reasons={["x"]} />);
    const untestableLabel = screen.getByTestId("verdict-label");
    const untestableSizeClasses = untestableLabel.className.replace(/verdict-untestable/g, "");

    expect(untestableSizeClasses).toBe(passSizeClasses);
  });
});

describe("INV-A: SEVERITY_WARNING renders at structurally higher prominence than a standard assumption row, by weight/size/space, never by hue", () => {
  it("the warning headline carries heavier weight and a larger size than a note row's text, plus a set-apart border and padding", () => {
    render(<AssumptionsView restatement={NO_EXIT_WARNING.restatement!} assumptions={NO_EXIT_WARNING.assumptions} />);

    const warning = screen.getByTestId("assumption-warning");
    const note = screen.getAllByTestId("assumption-note")[0];

    // Heavier weight: the warning's headline carries bold/semibold; a
    // plain note row never does (it inherits muted, regular-weight text).
    expect(warning.innerHTML).toMatch(/font-bold/);
    expect(note.className).not.toMatch(/font-bold|font-semibold/);

    // Set apart by a rule + generous padding, not merely the same box a
    // note row sits in (notes have no border/padding of their own at all).
    expect(warning.className).toMatch(/border-l-4/);
    expect(warning.className).toMatch(/p-6/);
    expect(note.className).toBe("");

    // Full foreground, not the muted tone the surrounding note list uses.
    expect(warning.className).toMatch(/text-foreground/);
    expect(warning.className).not.toMatch(/text-muted-foreground/);

    // No saturated hue anywhere in the warning -- prominence is weight and
    // space, never color (INV-2 covers this too; re-asserted here as the
    // same invariant from the prominence angle).
    expect(warning.className).not.toMatch(SATURATED_COLOR_CLASS);
  });
});

describe("INV-2: the verdict palette is referenced ONLY by VerdictCard -- no other component applies a saturated color", () => {
  it("RobustnessPanel renders a CONFIRMED bull-concentration flag with no saturated color and no verdict-* token", () => {
    render(
      <RobustnessPanel
        sensitivity={BULL_CONCENTRATION_CONFIRMED.sensitivity}
        walkForward={BULL_CONCENTRATION_CONFIRMED.walk_forward}
        deflatedSharpe={BULL_CONCENTRATION_CONFIRMED.deflated_sharpe}
        regime={BULL_CONCENTRATION_CONFIRMED.regime}
      />,
    );
    const html = screen.getByTestId("robustness-panel").innerHTML;
    expect(html).not.toMatch(SATURATED_COLOR_CLASS);
    expect(html).not.toMatch(/verdict-/);
  });

  it("BuyHoldComparison (the no-exit, non-verdict result) carries no saturated color and no verdict-* token", () => {
    render(<BuyHoldComparison noExit={NO_EXIT_RESULT.no_exit} />);
    const html = screen.getByTestId("buy-hold-comparison").innerHTML;
    expect(html).not.toMatch(SATURATED_COLOR_CLASS);
    expect(html).not.toMatch(/verdict-/);
  });

  it("AssumptionsView's SEVERITY_WARNING box carries no saturated color and no verdict-* token, despite its high prominence", () => {
    render(<AssumptionsView restatement={NO_EXIT_WARNING.restatement!} assumptions={NO_EXIT_WARNING.assumptions} />);
    const html = screen.getByTestId("assumptions-view").innerHTML;
    expect(html).not.toMatch(SATURATED_COLOR_CLASS);
    expect(html).not.toMatch(/verdict-/);
    // The warning element still exists and is still structurally distinct
    // (role=alert) -- this phase changes its COLOR, not its structure.
    expect(screen.getByTestId("assumption-warning")).toHaveAttribute("role", "alert");
  });

  it("ConfirmGate and TranslateInputView carry no saturated color and no verdict-* token", () => {
    render(<ConfirmGate defaultTicker="SPY" onConfirm={() => {}} />);
    expect(screen.getByTestId("confirm-gate").innerHTML).not.toMatch(SATURATED_COLOR_CLASS);
    expect(screen.getByTestId("confirm-gate").innerHTML).not.toMatch(/verdict-/);

    render(<TranslateInputView onSubmit={() => {}} />);
    expect(screen.getByTestId("translate-input-view").innerHTML).not.toMatch(SATURATED_COLOR_CLASS);
    expect(screen.getByTestId("translate-input-view").innerHTML).not.toMatch(/verdict-/);
  });

  it("TranslateFlow's error banner (a failed /translate) carries no saturated color and no verdict-* token", async () => {
    const api: TranslationApi = {
      translate: vi.fn().mockRejectedValue(new Error("network down")),
      correct: vi.fn(),
      confirm: vi.fn(),
    };
    render(<TranslateFlow api={api} />);
    fireEvent.change(screen.getByTestId("nl-input"), { target: { value: "buy SPY when RSI < 30" } });
    fireEvent.click(screen.getByTestId("translate-submit"));

    await waitFor(() => expect(screen.getByTestId("translate-error")).toBeInTheDocument());
    const html = screen.getByTestId("translate-error").outerHTML;
    expect(html).not.toMatch(SATURATED_COLOR_CLASS);
    expect(html).not.toMatch(/verdict-/);
  });
});
