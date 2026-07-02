/**
 * Phase 9 chrome: progress, disclaimer, and methodology components. These
 * are the frontend's OWN copy (facts about the product/UI, not judgments
 * about a strategy), so they are unit-testable in isolation. All must stay
 * monochrome -- the verdict card is the only saturated color in the app.
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "vitest";

import { CONFIRM_STAGES, ProgressIndicator } from "../ProgressIndicator";
import { DisclaimerFooter, ResultsDisclaimer } from "../Disclaimer";
import { MethodologyNote } from "../MethodologyNote";

// Same saturated-hue regex the Phase 7 INV-2 test uses: any Tailwind
// color utility at a numbered shade. New chrome must never match it.
const SATURATED_COLOR_CLASS =
  /\b(?:bg|text|border(?:-[trblxy])?|ring|from|via|to|fill|stroke)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/;

describe("ProgressIndicator: honest, indeterminate, elapsed-driven", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("ticks the elapsed counter once per second", () => {
    render(<ProgressIndicator testId="prog" label="Working…" showElapsed />);
    expect(screen.getByTestId("prog-elapsed")).toHaveTextContent("0s elapsed");

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByTestId("prog-elapsed")).toHaveTextContent("3s elapsed");
  });

  it("advances stage labels as elapsed time crosses each threshold, in backend order", () => {
    render(<ProgressIndicator testId="prog" label="Working…" stages={CONFIRM_STAGES} showElapsed />);
    expect(screen.getByTestId("prog-stage")).toHaveTextContent("Fetching price history");

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByTestId("prog-stage")).toHaveTextContent("Running the backtest");

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByTestId("prog-stage")).toHaveTextContent("Checking robustness");
  });

  it("renders no fake percentage/progress-bar and carries no saturated color", () => {
    render(<ProgressIndicator testId="prog" label="Working…" stages={CONFIRM_STAGES} showElapsed />);
    const html = screen.getByTestId("prog").innerHTML;
    expect(html).not.toMatch(SATURATED_COLOR_CLASS);
    expect(html).not.toMatch(/verdict-/);
    // No fabricated precision: an honesty tool shows activity + elapsed time,
    // never a "42%" or a determinate bar over an indeterminate wait.
    expect(html).not.toMatch(/%/);
    expect(html).not.toMatch(/role="progressbar"/);
  });
});

describe("Disclaimer chrome", () => {
  it("footer states the core caveats in plain voice, muted and monochrome", () => {
    render(<DisclaimerFooter />);
    const footer = screen.getByTestId("disclaimer-footer");
    expect(footer).toHaveTextContent(/not a prediction/i);
    expect(footer).toHaveTextContent(/not investment advice/i);
    expect(footer.className).toContain("text-muted-foreground");
    expect(footer.innerHTML).not.toMatch(SATURATED_COLOR_CLASS);
  });

  it("results disclaimer expands on hypothetical/past-performance and data-error caveats", () => {
    render(<ResultsDisclaimer />);
    const block = screen.getByTestId("results-disclaimer");
    expect(block).toHaveTextContent(/hypothetical and backtested/i);
    expect(block).toHaveTextContent(/past performance does not indicate future results/i);
    expect(block).toHaveTextContent(/investment advice/i);
    expect(block.innerHTML).not.toMatch(SATURATED_COLOR_CLASS);
  });
});

describe("MethodologyNote: educational, generic, all four verdicts", () => {
  it("renders a heading for every verdict and describes each of the four checks", () => {
    render(<MethodologyNote />);
    for (const v of ["PASS", "SHAKY", "LIKELY_OVERFIT", "UNTESTABLE"]) {
      expect(screen.getByTestId(`methodology-heading-${v}`)).toBeInTheDocument();
    }
    const html = screen.getByTestId("methodology-note").innerHTML;
    expect(html).toMatch(/Walk-forward/);
    expect(html).toMatch(/sensitivity/i);
    expect(html).toMatch(/Deflated Sharpe/);
    expect(html).toMatch(/Regime/);
    expect(html).toMatch(/overfit/i);
    expect(html).not.toMatch(SATURATED_COLOR_CLASS);
    expect(html).not.toMatch(/verdict-/);
  });

  it("stays generic — it never prints a concrete number that would read as a specific strategy's result", () => {
    render(<MethodologyNote />);
    const text = screen.getByTestId("methodology-note").textContent ?? "";
    // No digits at all: the note explains checks in words, never restates a
    // Sharpe, a percentage, or any figure tied to a run.
    expect(text).not.toMatch(/[0-9]/);
  });
});
