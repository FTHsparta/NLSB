/**
 * Phase 12B: every result states which data produced it.
 *
 * The backend guarantees a `window` block on every result kind; these pin the
 * render side of that contract, including the display-side corollary — the
 * component prints backend values and derives no judgment from them.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RobustnessResultView } from "../RobustnessResultView";
import { TestedWindow } from "../TestedWindow";

import likelyOverfitFixture from "@/fixtures/robustness/likely_overfit.json";
import noExitFixture from "@/fixtures/robustness/no_exit.json";
import passFixture from "@/fixtures/robustness/pass.json";
import untestableFixture from "@/fixtures/robustness/untestable.json";

import type { RealizedWindow, RobustnessResult } from "@/lib/robustness/types";

const PASS_RESULT = passFixture as unknown as RobustnessResult;
const UNTESTABLE_RESULT = untestableFixture as unknown as RobustnessResult;
const LIKELY_OVERFIT_RESULT = likelyOverfitFixture as unknown as RobustnessResult;
const NO_EXIT_RESULT = noExitFixture as unknown as RobustnessResult;

describe("every result kind states the window it was judged on", () => {
  it.each([
    ["pass", PASS_RESULT],
    ["untestable", UNTESTABLE_RESULT],
    ["likely overfit", LIKELY_OVERFIT_RESULT],
    ["no exit", NO_EXIT_RESULT],
  ])("renders the tested window for a %s result", (_label, result) => {
    render(<RobustnessResultView result={result} />);

    const line = screen.getByTestId("tested-window");
    expect(line).toBeInTheDocument();
    expect(screen.getByTestId("tested-window-range")).toHaveTextContent(
      `${result.window.realized_start} to ${result.window.realized_end}`
    );
    expect(screen.getByTestId("tested-window-bars")).toHaveTextContent(
      result.window.bar_count.toLocaleString("en-US")
    );
  });

  it("reports the window even on a correct, unremarkable run", () => {
    // Not a diagnostic that appears only when something is wrong.
    render(<RobustnessResultView result={PASS_RESULT} />);
    expect(screen.getByTestId("tested-window")).toBeInTheDocument();
  });
});

describe("display-side corollary: renders values, derives no judgment", () => {
  const shortWindow: RealizedWindow = {
    realized_start: "2020-01-02",
    realized_end: "2020-01-10",
    bar_count: 7,
    requested_start: "2010-01-01",
    requested_end: "2020-01-10",
  };
  const longWindow: RealizedWindow = {
    realized_start: "2010-01-04",
    realized_end: "2024-12-31",
    bar_count: 3771,
    requested_start: "2010-01-01",
    requested_end: "2024-12-31",
  };

  it("gives a tiny window and a huge one byte-identical classes", () => {
    const { container: shortEl } = render(<TestedWindow window={shortWindow} />);
    const shortClasses = shortEl.querySelector("[data-testid='tested-window']")?.className;

    const { container: longEl } = render(<TestedWindow window={longWindow} />);
    const longClasses = longEl.querySelector("[data-testid='tested-window']")?.className;

    expect(shortClasses).toBe(longClasses);
  });

  it("emits no evaluative prose about the window", () => {
    render(<TestedWindow window={shortWindow} />);
    const text = screen.getByTestId("tested-window").textContent ?? "";

    // The frontend never decides a window is short/insufficient/suspicious.
    // If that judgment is ever wanted, the backend emits the string.
    for (const word of ["short", "insufficient", "limited", "too few", "warning", "only"]) {
      expect(text.toLowerCase()).not.toContain(word);
    }
  });

  it("formats the bar count for presentation without changing it", () => {
    render(<TestedWindow window={longWindow} />);
    expect(screen.getByTestId("tested-window-bars")).toHaveTextContent("3,771");
  });
});

describe("degrades rather than inventing a window", () => {
  it("renders nothing when the payload has no window", () => {
    const { container } = render(<TestedWindow window={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the realized dates are missing", () => {
    const { container } = render(
      <TestedWindow
        window={{
          realized_start: null,
          realized_end: null,
          bar_count: 0,
          requested_start: "2015-01-01",
          requested_end: null,
        }}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("still renders the rest of the result when the window is absent", () => {
    // An older backend or a clipped body must not blank the results page.
    const withoutWindow = { ...PASS_RESULT, window: undefined } as unknown as RobustnessResult;
    render(<RobustnessResultView result={withoutWindow} />);

    expect(screen.getByTestId("verdict-label")).toBeInTheDocument();
    expect(screen.queryByTestId("tested-window")).not.toBeInTheDocument();
  });
});
