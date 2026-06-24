/**
 * Contract tests for Phase 5b's input -> translate -> confirm gate.
 * Translation fixtures come from `backend/scripts/dump_translation_fixtures.py`,
 * which runs the REAL `apply_defaults` + `render_confirmation` (no hand-
 * authored text) -- the same schema-true-fixture discipline 5a established
 * for the robustness side. The robustness fixture (`pass.json`) reused here
 * is the real `run_robustness` output from 5a, used only to prove the
 * confirm path hands its result to the existing 5a renderer unmodified.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssumptionsView } from "../AssumptionsView";
import { TranslateFlow } from "../TranslateFlow";
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
    expect(youSpecified.textContent).toContain("ticker: SPY");
    expect(youSpecified.textContent).toContain("entry condition");
    expect(youSpecified.textContent).toContain("exit condition");
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
