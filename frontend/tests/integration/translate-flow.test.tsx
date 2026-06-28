/**
 * Phase 6 integration tests: `TranslateFlow` rendered with its REAL default
 * `api` (the actual `httpTranslationApi`, doing real `fetch` calls to
 * `/translate`/`/correct`/`/confirm`) -- only the network is mocked, via MSW
 * (`tests/msw/server.ts`, wired up in `vitest.setup.ts`). Every other
 * component in the tree (`TranslateInputView`, `AssumptionsView`,
 * `ConfirmGate`, `RobustnessResultView`, ...) is the real, already-tested
 * component; this file's only job is proving the WIRING between them holds
 * once the routes are real, not re-testing what 5a/5b's component-level
 * contract tests (which inject a fake `api` prop directly) already cover.
 *
 * Response bodies reuse real backend fixtures where one already exists
 * (`ordinary_assumptions.json`, `no_exit_warning.json`, `pass.json`,
 * `no_exit.json`) -- the same schema-true-fixture discipline the rest of
 * this project holds to. The correction-loop test's "updated" /correct
 * response is a hand-typed literal matching the `TranslationPayload` type
 * (not a real fixture): its job is only to prove the gate re-renders
 * whatever /correct returns, not to model a specific real correction.
 */
import { delay, http, HttpResponse } from "msw";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { TranslateFlow } from "@/components/translation/TranslateFlow";
import { server } from "../msw/server";

import noExitWarningFixture from "@/fixtures/translation/no_exit_warning.json";
import ordinaryFixture from "@/fixtures/translation/ordinary_assumptions.json";
import noExitResultFixture from "@/fixtures/robustness/no_exit.json";
import passResultFixture from "@/fixtures/robustness/pass.json";

import type { RobustnessResult } from "@/lib/robustness/types";
import type { TranslationPayload } from "@/lib/translation/types";

const ORDINARY = ordinaryFixture as unknown as TranslationPayload;
const NO_EXIT_WARNING = noExitWarningFixture as unknown as TranslationPayload;
const PASS_RESULT = passResultFixture as unknown as RobustnessResult;
const NO_EXIT_RESULT = noExitResultFixture as unknown as RobustnessResult;

function mockTranslate(payload: TranslationPayload, status = 200) {
  server.use(http.post("/translate", () => HttpResponse.json(payload, { status })));
}

function mockCorrect(payload: TranslationPayload, status = 200) {
  server.use(http.post("/correct", () => HttpResponse.json(payload, { status })));
}

function mockConfirm(payload: RobustnessResult, status = 200) {
  server.use(http.post("/confirm", () => HttpResponse.json(payload, { status })));
}

function mockTranslateError(status = 500, body = "LLM call failed") {
  server.use(http.post("/translate", () => new HttpResponse(body, { status })));
}

function mockCorrectError(status = 500, body = "LLM call failed") {
  server.use(http.post("/correct", () => new HttpResponse(body, { status })));
}

function mockConfirmError(status = 500, body = "backtest failed") {
  server.use(http.post("/confirm", () => new HttpResponse(body, { status })));
}

async function typeAndTranslate(text = "buy SPY when RSI < 30, sell when RSI > 70") {
  const user = userEvent.setup();
  render(<TranslateFlow />);
  await user.type(screen.getByTestId("nl-input"), text);
  await user.click(screen.getByTestId("translate-submit"));
  return user;
}

describe("INTEGRATION: gate integrity holds with the real fetch boundary", () => {
  it("never mounts a results testid at any point before /confirm resolves -- typing, translating, sitting at the gate, correcting", async () => {
    mockTranslate(ORDINARY);
    mockCorrect(ORDINARY);
    // /confirm deliberately left unstubbed for this test -- if anything
    // here reached it, MSW's onUnhandledRequest: "error" setting would
    // fail the test even before the results-testid assertion did.

    const user = await typeAndTranslate();
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByTestId("assumptions-view")).toBeInTheDocument());
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verdict-card")).not.toBeInTheDocument();

    await user.type(screen.getByTestId("correction-input"), "use RSI(20) instead");
    await user.click(screen.getByTestId("correction-submit"));
    await waitFor(() => expect(screen.getByTestId("assumptions-view")).toBeInTheDocument());

    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verdict-card")).not.toBeInTheDocument();
  });

  it("mounts results only after the confirm button is clicked AND /confirm has resolved -- not on the click itself", async () => {
    mockTranslate(ORDINARY);
    // A deliberately delayed /confirm response: with an instantly-resolving
    // mock there is no reliable window in which to observe "clicked, but
    // not yet resolved" -- the promise can settle before the next assertion
    // even runs. Delaying it gives that window an actual duration to assert
    // against, rather than asserting on a race.
    server.use(
      http.post("/confirm", async () => {
        await delay(50);
        return HttpResponse.json(PASS_RESULT);
      }),
    );

    await typeAndTranslate();
    await waitFor(() => expect(screen.getByTestId("confirm-gate")).toBeInTheDocument());

    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByTestId("confirm-run-button"));
    // Immediately after the click, before the mocked network round-trip
    // resolves, results must still be absent.
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByTestId("robustness-result-view")).toBeInTheDocument());
    expect(screen.getByTestId("verdict-card")).toHaveAttribute("data-verdict", "PASS");
  });
});

describe("INTEGRATION: happy path -- idle to a rendered verdict, through real fetch calls", () => {
  it("idle -> type -> /translate resolves -> gate shows stated-vs-assumed -> confirm -> /confirm resolves -> verdict renders", async () => {
    mockTranslate(ORDINARY);
    mockConfirm(PASS_RESULT);

    const user = await typeAndTranslate();

    await waitFor(() => expect(screen.getByTestId("assumptions-view")).toBeInTheDocument());
    expect(screen.getByTestId("you-specified-section")).toHaveTextContent("Ticker: SPY");
    expect(screen.getByTestId("confirm-gate")).toBeInTheDocument();

    await user.click(screen.getByTestId("confirm-run-button"));

    await waitFor(() => expect(screen.getByTestId("verdict-card")).toBeInTheDocument());
    expect(screen.getByTestId("verdict-label")).toHaveTextContent("Pass");
    // The gate/input surfaces are gone once results has mounted.
    expect(screen.queryByTestId("confirm-gate")).not.toBeInTheDocument();
    expect(screen.queryByTestId("translate-input-view")).not.toBeInTheDocument();
  });
});

describe("INTEGRATION: correction loop -- /correct returns a full re-translation, and stays at the gate", () => {
  it("a correction at the gate triggers /correct and re-renders an UPDATED gate, never reaching results", async () => {
    mockTranslate(ORDINARY);
    const updatedTranslation: TranslationPayload = {
      status: "ok",
      ir: { ...ORDINARY.ir, indicators: [{ id: "rsi20", type: "RSI", params: { period: 20 }, source: "close" }] },
      assumptions: ORDINARY.assumptions,
      restatement: "UPDATED: Buy SPY when RSI(20) drops below 30; sell when it rises above 70.\n\nYou specified:\n- ticker: SPY\n- entry condition\n- exit condition",
      message: null,
      retries: 1,
    };
    mockCorrect(updatedTranslation);

    const user = await typeAndTranslate();
    await waitFor(() => expect(screen.getByTestId("assumptions-view")).toBeInTheDocument());
    const originalStrategyText = screen.getByTestId("strategy-summary").textContent;

    await user.type(screen.getByTestId("correction-input"), "use RSI(20) instead");
    await user.click(screen.getByTestId("correction-submit"));

    // The /correct contract found in orientation: `service.correct` is
    // literally `translate()` re-run with the correction folded into the
    // prompt, so its response is a FULL TranslationPayload, the same shape
    // /translate returns -- not a targeted patch. The gate must therefore
    // be re-rendered from this new payload wholesale, which this asserts
    // by checking the strategy text actually changed.
    await waitFor(() => expect(screen.getByTestId("strategy-summary")).toHaveTextContent("UPDATED"));
    expect(screen.getByTestId("strategy-summary").textContent).not.toBe(originalStrategyText);

    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verdict-card")).not.toBeInTheDocument();
  });
});

describe("INTEGRATION: no-exit branch through the real /confirm route", () => {
  it("a /confirm response with kind 'no_exit' routes to BuyHoldComparison, with no verdict card anywhere in the tree", async () => {
    mockTranslate(NO_EXIT_WARNING);
    mockConfirm(NO_EXIT_RESULT);

    const user = await typeAndTranslate("buy SPY when RSI < 30");
    await waitFor(() => expect(screen.getByTestId("confirm-gate")).toBeInTheDocument());

    await user.click(screen.getByTestId("confirm-run-button"));

    await waitFor(() => expect(screen.getByTestId("buy-hold-comparison")).toBeInTheDocument());
    expect(screen.queryByTestId("verdict-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("robustness-panel")).not.toBeInTheDocument();
  });
});

describe("INTEGRATION: error states -- each of the three calls surfaces an error and does not advance the machine", () => {
  it("a failing /translate surfaces an error and never reaches the gate", async () => {
    mockTranslateError(500, "Anthropic API call failed");

    await typeAndTranslate();

    await waitFor(() => expect(screen.getByTestId("translate-error")).toBeInTheDocument());
    expect(screen.getByTestId("translate-error")).toHaveAttribute("role", "alert");
    expect(screen.queryByTestId("assumptions-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("confirm-gate")).not.toBeInTheDocument();
  });

  it("a failing /correct surfaces an error, stays at the gate with the prior translation, and never reaches results", async () => {
    mockTranslate(ORDINARY);
    mockCorrectError(500, "Anthropic API call failed");

    const user = await typeAndTranslate();
    await waitFor(() => expect(screen.getByTestId("assumptions-view")).toBeInTheDocument());

    await user.type(screen.getByTestId("correction-input"), "use RSI(20) instead");
    await user.click(screen.getByTestId("correction-submit"));

    await waitFor(() => expect(screen.getByTestId("correct-error")).toBeInTheDocument());
    expect(screen.getByTestId("correct-error")).toHaveAttribute("role", "alert");
    // The gate is still there, showing the PRIOR (pre-correction) translation.
    expect(screen.getByTestId("assumptions-view")).toBeInTheDocument();
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
  });

  it("a failing /confirm surfaces an error, stays at the gate, and results never mounts", async () => {
    mockTranslate(ORDINARY);
    mockConfirmError(500, "backtest failed: insufficient price history");

    const user = await typeAndTranslate();
    await waitFor(() => expect(screen.getByTestId("confirm-gate")).toBeInTheDocument());

    await user.click(screen.getByTestId("confirm-run-button"));

    await waitFor(() => expect(screen.getByTestId("confirm-error")).toBeInTheDocument());
    expect(screen.getByTestId("confirm-error")).toHaveAttribute("role", "alert");
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verdict-card")).not.toBeInTheDocument();
    // The gate remains usable -- the user can retry without re-translating.
    expect(screen.getByTestId("confirm-gate")).toBeInTheDocument();
  });
});

describe("INTEGRATION: SEVERITY_WARNING survives the real fetch boundary, not just the isolated component test", () => {
  it("the missing-exit -> buy-and-hold warning renders at the gate with role=alert, distinct from ordinary note rows, after a real /translate round-trip", async () => {
    mockTranslate(NO_EXIT_WARNING);

    await typeAndTranslate("buy SPY when RSI < 30");

    await waitFor(() => expect(screen.getByTestId("assumption-warning")).toBeInTheDocument());
    const warning = screen.getByTestId("assumption-warning");
    expect(warning).toHaveAttribute("role", "alert");

    const warningAssumption = NO_EXIT_WARNING.assumptions.find((a) => a.severity === "warning")!;
    expect(screen.getByTestId("assumption-warning-reason")).toHaveTextContent(warningAssumption.reason);

    // Distinct from ordinary note rows -- never one of the plain <li>s.
    const notes = screen.queryAllByTestId("assumption-note");
    for (const note of notes) {
      expect(note).not.toBe(warning);
    }
  });
});
