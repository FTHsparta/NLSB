/**
 * Contract tests for Phase 5b's input -> translate -> confirm gate.
 * Translation fixtures come from `backend/scripts/dump_translation_fixtures.py`,
 * which runs the REAL `apply_defaults` + `render_confirmation` (no hand-
 * authored text) -- the same schema-true-fixture discipline 5a established
 * for the robustness side. The robustness fixture (`pass.json`) reused here
 * is the real `run_robustness` output from 5a, used only to prove the
 * confirm path hands its result to the existing 5a renderer unmodified.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssumptionsView } from "../AssumptionsView";
import { TranslateFlow } from "../TranslateFlow";
import { TranslateInputView } from "../TranslateInputView";
import { SiteShell } from "@/components/chrome/SiteShell";
import type { TranslationApi } from "@/lib/translation/api";
import type { TranslationPayload } from "@/lib/translation/types";
import type { RobustnessResult } from "@/lib/robustness/types";

import ordinaryFixture from "@/fixtures/translation/ordinary_assumptions.json";
import noExitWarningFixture from "@/fixtures/translation/no_exit_warning.json";
import passFixture from "@/fixtures/robustness/pass.json";

const ORDINARY = ordinaryFixture as unknown as TranslationPayload;
const NO_EXIT_WARNING = noExitWarningFixture as unknown as TranslationPayload;
const PASS_RESULT = passFixture as unknown as RobustnessResult;

function fakeApi(overrides: Partial<TranslationApi> = {}): TranslationApi & {
  translate: ReturnType<typeof vi.fn>;
  correct: ReturnType<typeof vi.fn>;
  confirm: ReturnType<typeof vi.fn>;
} {
  return {
    translate: vi.fn().mockResolvedValue(ORDINARY),
    correct: vi.fn().mockResolvedValue(ORDINARY),
    confirm: vi.fn().mockResolvedValue(PASS_RESULT),
    ...overrides,
  } as TranslationApi & {
    translate: ReturnType<typeof vi.fn>;
    correct: ReturnType<typeof vi.fn>;
    confirm: ReturnType<typeof vi.fn>;
  };
}

async function translateInto(api: TranslationApi, text = "buy SPY when RSI < 30") {
  render(<TranslateFlow api={api} />);
  fireEvent.change(screen.getByTestId("nl-input"), { target: { value: text } });
  fireEvent.click(screen.getByTestId("translate-submit"));
  await waitFor(() => expect(screen.getByTestId("assumptions-view")).toBeInTheDocument());
}

describe("CONTRACT 3: SEVERITY_WARNING assumption renders with distinct, higher-prominence treatment", () => {
  it("renders the warning via a different element/testid/role than an ordinary note", () => {
    render(<AssumptionsView restatement={NO_EXIT_WARNING.restatement!} assumptions={NO_EXIT_WARNING.assumptions} />);

    const warning = screen.getByTestId("assumption-warning");
    expect(warning).toHaveAttribute("role", "alert");

    const notes = screen.getAllByTestId("assumption-note");
    expect(notes.length).toBeGreaterThan(0);

    // structurally distinct: the warning is never one of the plain note <li> rows
    for (const note of notes) {
      expect(note).not.toBe(warning);
      expect(note.getAttribute("role")).not.toBe("alert");
    }
  });

  it("does not render a warning element at all when no assumption is warning-severity", () => {
    render(<AssumptionsView restatement={ORDINARY.restatement!} assumptions={ORDINARY.assumptions} />);
    expect(screen.queryByTestId("assumption-warning")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("assumption-note").length).toBeGreaterThan(0);
  });
});

describe("CONTRACT 4: displayed assumption/restatement text equals renderer.py's output verbatim", () => {
  it("renders the warning reason text exactly as the backend's Assumption.reason field", () => {
    render(<AssumptionsView restatement={NO_EXIT_WARNING.restatement!} assumptions={NO_EXIT_WARNING.assumptions} />);
    const warningAssumption = NO_EXIT_WARNING.assumptions.find((a) => a.severity === "warning")!;
    expect(screen.getByTestId("assumption-warning-reason")).toHaveTextContent(warningAssumption.reason);
  });

  it("renders every ordinary note's reason text exactly as the backend's Assumption.reason field", () => {
    render(<AssumptionsView restatement={ORDINARY.restatement!} assumptions={ORDINARY.assumptions} />);
    for (const a of ORDINARY.assumptions) {
      const match = screen.getAllByTestId("assumption-note").find((el) => el.textContent?.includes(a.reason));
      expect(match).toBeTruthy();
    }
  });

  it("renders the 'You specified' text as the exact substring of the backend restatement", () => {
    render(<AssumptionsView restatement={ORDINARY.restatement!} assumptions={ORDINARY.assumptions} />);
    const youSpecified = screen.getByTestId("you-specified-section");
    // The backend's "You specified" list items must appear verbatim.
    expect(youSpecified.textContent).toContain("Ticker: SPY");
    expect(youSpecified.textContent).toContain("Entry condition");
    expect(youSpecified.textContent).toContain("Exit condition");
  });

  it("never displays asset_class or a stop-loss/take-profit anywhere in the confirmation surface", () => {
    // Pre-launch honesty pass: asset_class is decorative (nothing in the
    // engine's data or cost layer reads it), and stop/target orders are not
    // simulated (stop-bearing IRs are rejected before a gate payload
    // exists). The fixtures are real backend output — if either ever leaks
    // back into renderer.py/apply_defaults, this fails here too, not just
    // in the backend suite.
    render(<AssumptionsView restatement={ORDINARY.restatement!} assumptions={ORDINARY.assumptions} />);
    const view = screen.getByTestId("assumptions-view");
    expect(view.textContent).not.toContain("equity");
    expect(view.textContent).not.toContain("asset_class");
    expect(view.textContent).not.toContain("Stop-loss");
    expect(view.textContent).not.toContain("Take-profit");
  });
});

describe("CONTRACT 6 (INV-A): the gate's layout honors the backend's stated-vs-assumed split -- it lays the categorization out, it never re-derives it", () => {
  it("every stated item renders under 'You specified' and every assumption's field renders under 'I assumed', with no crossover", () => {
    render(<AssumptionsView restatement={ORDINARY.restatement!} assumptions={ORDINARY.assumptions} />);

    const youSpecified = screen.getByTestId("you-specified-section");
    const iAssumed = screen.getByTestId("note-assumptions-section");

    expect(youSpecified).toHaveTextContent("Ticker: SPY");
    expect(youSpecified).toHaveTextContent("Entry condition");
    expect(youSpecified).toHaveTextContent("Exit condition");

    for (const a of ORDINARY.assumptions) {
      // Every assumption the backend produced lands in "I assumed" ...
      expect(iAssumed).toHaveTextContent(a.field);
      // ... and never duplicates into "You specified" -- the frontend
      // never moves an item between the backend's two buckets.
      expect(youSpecified).not.toHaveTextContent(a.field);
    }

    // Nothing stated leaks the other way either.
    expect(iAssumed).not.toHaveTextContent("Entry condition");
    expect(iAssumed).not.toHaveTextContent("Exit condition");
  });

  it("the SEVERITY_WARNING assumption renders INSIDE 'I assumed', elevated but not floated outside the stated/assumed structure", () => {
    render(<AssumptionsView restatement={NO_EXIT_WARNING.restatement!} assumptions={NO_EXIT_WARNING.assumptions} />);

    const iAssumed = screen.getByTestId("note-assumptions-section");
    const warning = screen.getByTestId("assumption-warning");
    expect(iAssumed).toContainElement(warning);

    // It's still categorized as an assumption, not a stated item.
    const youSpecified = screen.getByTestId("you-specified-section");
    expect(youSpecified).not.toContainElement(warning);
  });
});

describe("CONTRACT 5: gate integrity -- results view unreachable without an explicit confirm", () => {
  it("never renders the robustness result view after translate alone", async () => {
    const api = fakeApi();
    await translateInto(api);

    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verdict-card")).not.toBeInTheDocument();
    expect(api.confirm).not.toHaveBeenCalled();
  });

  it("never renders the robustness result view after a correction alone", async () => {
    const api = fakeApi();
    await translateInto(api);

    fireEvent.change(screen.getByTestId("correction-input"), {
      target: { value: "use RSI(20) instead" },
    });
    fireEvent.click(screen.getByTestId("correction-submit"));

    await waitFor(() => expect(api.correct).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
    expect(api.confirm).not.toHaveBeenCalled();
  });

  it("renders the robustness result view only after the confirm button is clicked, via /confirm and nothing else", async () => {
    const api = fakeApi();
    await translateInto(api);

    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("confirm-run-button"));

    await waitFor(() => expect(api.confirm).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("verdict-card")).toBeInTheDocument());

    expect(api.confirm).toHaveBeenCalledTimes(1);
    const callArgs = api.confirm.mock.calls[0];
    expect(callArgs[0]).toEqual(ORDINARY.ir);
    expect(callArgs[1]).toEqual(ORDINARY.assumptions);
    expect(callArgs[2]).toBe("SPY");
    expect(typeof callArgs[3]).toBe("string");
  });

  it("an unsupported translation never shows assumptions, a confirm gate, or a result", async () => {
    const api = fakeApi({
      translate: vi.fn().mockResolvedValue({
        status: "unsupported",
        ir: null,
        assumptions: [],
        restatement: null,
        message: "Options aren't supported in v1.",
        retries: 0,
      }),
    });
    render(<TranslateFlow api={api} />);
    fireEvent.change(screen.getByTestId("nl-input"), { target: { value: "buy SPY call options" } });
    fireEvent.click(screen.getByTestId("translate-submit"));

    await waitFor(() => expect(screen.getByTestId("translate-flow-message")).toBeInTheDocument());
    expect(screen.queryByTestId("assumptions-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("confirm-gate")).not.toBeInTheDocument();
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
  });
});

describe("CONTRACT 7: example strategy chips prefill the textarea, never submit on their own", () => {
  it("renders all 4 example chips", () => {
    render(<TranslateInputView onSubmit={() => {}} />);
    expect(screen.getAllByTestId("example-strategy")).toHaveLength(4);
  });

  it("clicking a chip prefills the textarea with that example's full strategy text", () => {
    render(<TranslateInputView onSubmit={() => {}} />);
    const chip = screen.getAllByTestId("example-strategy")[0];
    const expectedText = chip.textContent;
    fireEvent.click(chip);

    const textarea = screen.getByTestId("nl-input") as HTMLTextAreaElement;
    expect(textarea.value.length).toBeGreaterThan(0);
    // The chip's own label is short ("Golden cross (SPY)"); the prefilled
    // text is the full sentence -- they are never the same string, which
    // also proves this isn't accidentally echoing the label itself.
    expect(textarea.value).not.toBe(expectedText);
    expect(textarea.value.endsWith(".")).toBe(true);
  });

  it("every chip is type=button, never type=submit -- clicking one must not submit the form", () => {
    const onSubmit = vi.fn();
    render(<TranslateInputView onSubmit={onSubmit} />);
    for (const chip of screen.getAllByTestId("example-strategy")) {
      expect(chip).toHaveAttribute("type", "button");
    }
    fireEvent.click(screen.getAllByTestId("example-strategy")[0]);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("chips are disabled when the parent passes disabled=true, same as the textarea/submit button", () => {
    render(<TranslateInputView onSubmit={() => {}} disabled />);
    for (const chip of screen.getAllByTestId("example-strategy")) {
      expect(chip).toBeDisabled();
    }
  });
});

describe("CONTRACT 8: friendly error fallback -- a raw HTTP status never reaches the user as the visible message", () => {
  function fakeApiThatRejects(action: "translate" | "confirm", error: Error) {
    return fakeApi(
      action === "translate"
        ? { translate: vi.fn().mockRejectedValue(error) }
        : { confirm: vi.fn().mockRejectedValue(error) },
    );
  }

  it("a 500-style /translate failure shows friendly copy, not the raw '(500)' string, with the raw text tucked inside collapsed technical details", async () => {
    const api = fakeApiThatRejects("translate", new Error("/translate failed (500): Anthropic API call failed"));
    render(<TranslateFlow api={api} />);
    fireEvent.change(screen.getByTestId("nl-input"), { target: { value: "buy SPY when RSI < 30" } });
    fireEvent.click(screen.getByTestId("translate-submit"));

    await waitFor(() => expect(screen.getByTestId("translate-error")).toBeInTheDocument());

    const visibleMessage = screen.getByTestId("translate-error-message");
    expect(visibleMessage.textContent).not.toMatch(/\(500\)/);
    expect(visibleMessage.textContent).toMatch(/translating your strategy/i);
    expect(visibleMessage.textContent).toMatch(/not a problem with your strategy/i);

    // The raw text IS present, but only inside the collapsed disclosure --
    // never as the visible headline message.
    const detail = screen.getByTestId("translate-error-detail");
    expect(detail.textContent).toContain("(500)");
    expect(detail.closest("details")).not.toHaveAttribute("open");
    expect(detail.textContent).not.toBe(visibleMessage.textContent);

    // TRANSLATE_ERROR's load-bearing phase transition (-> idle) is
    // preserved: the input view is still reachable, no gate mounted.
    expect(screen.getByTestId("translate-input-view")).toBeInTheDocument();
    expect(screen.queryByTestId("confirm-gate")).not.toBeInTheDocument();
  });

  it("a 500-style /confirm failure shows friendly copy and stays at the gate (CONFIRM_ERROR -> gate, never results)", async () => {
    const api = fakeApiThatRejects("confirm", new Error("/confirm failed (500): backtest failed: insufficient price history"));
    await translateInto(api);

    fireEvent.click(screen.getByTestId("confirm-run-button"));
    await waitFor(() => expect(screen.getByTestId("confirm-error")).toBeInTheDocument());

    const visibleMessage = screen.getByTestId("confirm-error-message");
    expect(visibleMessage.textContent).not.toMatch(/\(500\)/);
    expect(visibleMessage.textContent).toMatch(/running the backtest/i);

    const detail = screen.getByTestId("confirm-error-detail");
    expect(detail.textContent).toContain("(500)");
    expect(detail.textContent).not.toBe(visibleMessage.textContent);

    // CONFIRM_ERROR's load-bearing phase transition (-> gate) is preserved.
    expect(screen.getByTestId("confirm-gate")).toBeInTheDocument();
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
  });

  it("a rejection with no HTTP status at all (a real network failure) shows the 'couldn't reach the service' copy", async () => {
    const api = fakeApiThatRejects("translate", new Error("Failed to fetch"));
    render(<TranslateFlow api={api} />);
    fireEvent.change(screen.getByTestId("nl-input"), { target: { value: "buy SPY when RSI < 30" } });
    fireEvent.click(screen.getByTestId("translate-submit"));

    await waitFor(() => expect(screen.getByTestId("translate-error")).toBeInTheDocument());
    const visibleMessage = screen.getByTestId("translate-error-message");
    expect(visibleMessage.textContent).toMatch(/couldn't reach the service/i);
    expect(visibleMessage.textContent).toMatch(/make sure it's running/i);
  });

  it("a 429 /correct failure is described as rate-limited, and CORRECT_ERROR's load-bearing transition (-> gate, prior translation intact) is preserved", async () => {
    const api = fakeApi({
      correct: vi.fn().mockRejectedValue(new Error("/correct failed (429): rate limited")),
    });
    await translateInto(api);

    fireEvent.change(screen.getByTestId("correction-input"), { target: { value: "use RSI(20) instead" } });
    fireEvent.click(screen.getByTestId("correction-submit"));

    await waitFor(() => expect(screen.getByTestId("correct-error")).toBeInTheDocument());
    expect(screen.getByTestId("correct-error-message").textContent).toMatch(/rate-limited/i);

    // Stayed at the gate with the prior translation intact.
    expect(screen.getByTestId("assumptions-view")).toBeInTheDocument();
  });
});

/** A promise the test resolves by hand, to hold a request "in flight" for a
 * deterministic window (no timers, no MSW delay races). */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("CONTRACT 9 (Phase 9): staged progress indicators mount during a request and unmount on transition", () => {
  it("shows the translating indicator only while /translate is in flight", async () => {
    const d = deferred<TranslationPayload>();
    const api = fakeApi({ translate: vi.fn(() => d.promise) });
    render(<TranslateFlow api={api} />);

    fireEvent.change(screen.getByTestId("nl-input"), { target: { value: "buy SPY when RSI < 30" } });
    fireEvent.click(screen.getByTestId("translate-submit"));

    expect(screen.getByTestId("translating-indicator")).toBeInTheDocument();

    await act(async () => {
      d.resolve(ORDINARY);
      await d.promise;
    });

    await waitFor(() => expect(screen.queryByTestId("translating-indicator")).not.toBeInTheDocument());
    expect(screen.getByTestId("assumptions-view")).toBeInTheDocument();
  });

  it("shows the confirming indicator with an elapsed counter only while /confirm is in flight", async () => {
    const d = deferred<RobustnessResult>();
    const api = fakeApi({ confirm: vi.fn(() => d.promise) });
    await translateInto(api);

    fireEvent.click(screen.getByTestId("confirm-run-button"));

    expect(screen.getByTestId("confirming-indicator")).toBeInTheDocument();
    expect(screen.getByTestId("confirming-indicator-elapsed")).toBeInTheDocument();

    await act(async () => {
      d.resolve(PASS_RESULT);
      await d.promise;
    });

    await waitFor(() => expect(screen.queryByTestId("confirming-indicator")).not.toBeInTheDocument());
    expect(screen.getByTestId("robustness-result-view")).toBeInTheDocument();
  });
});

describe("CONTRACT 10 (Phase 9): double-submit protection -- an in-flight request cannot be fired twice", () => {
  it("a second Translate click while /translate is in flight does not fire a second request", async () => {
    const d = deferred<TranslationPayload>();
    const translate = vi.fn(() => d.promise);
    const api = fakeApi({ translate });
    render(<TranslateFlow api={api} />);

    fireEvent.change(screen.getByTestId("nl-input"), { target: { value: "buy SPY when RSI < 30" } });
    const button = screen.getByTestId("translate-submit");
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    expect(translate).toHaveBeenCalledTimes(1);

    await act(async () => {
      d.resolve(ORDINARY);
      await d.promise;
    });
    await waitFor(() => expect(screen.getByTestId("assumptions-view")).toBeInTheDocument());
  });

  it("a second Confirm click while /confirm is in flight does not fire a second request", async () => {
    const d = deferred<RobustnessResult>();
    const confirm = vi.fn(() => d.promise);
    const api = fakeApi({ confirm });
    await translateInto(api);

    const button = screen.getByTestId("confirm-run-button");
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    expect(confirm).toHaveBeenCalledTimes(1);

    await act(async () => {
      d.resolve(PASS_RESULT);
      await d.promise;
    });
    await waitFor(() => expect(screen.getByTestId("robustness-result-view")).toBeInTheDocument());
  });
});

describe("CONTRACT 11 (Phase 9): the disclaimer footer is present on every screen", () => {
  it("renders on entry, at the gate, and on the results surface (plus the fuller results block)", async () => {
    // Phase 11 render-entry update ONLY: the footer moved from inside
    // TranslateFlow to the shared SiteShell (so it is on every ROUTE by
    // construction, not just every flow state). Rendering the flow inside
    // the real shell keeps every assertion below byte-identical.
    const api = fakeApi();
    render(
      <SiteShell>
        <TranslateFlow api={api} />
      </SiteShell>,
    );

    // entry
    expect(screen.getByTestId("disclaimer-footer")).toBeInTheDocument();

    // gate
    fireEvent.change(screen.getByTestId("nl-input"), { target: { value: "buy SPY when RSI < 30" } });
    fireEvent.click(screen.getByTestId("translate-submit"));
    await waitFor(() => expect(screen.getByTestId("assumptions-view")).toBeInTheDocument());
    expect(screen.getByTestId("disclaimer-footer")).toBeInTheDocument();

    // results
    fireEvent.click(screen.getByTestId("confirm-run-button"));
    await waitFor(() => expect(screen.getByTestId("robustness-result-view")).toBeInTheDocument());
    expect(screen.getByTestId("disclaimer-footer")).toBeInTheDocument();
    expect(screen.getByTestId("results-disclaimer")).toBeInTheDocument();
  });
});
