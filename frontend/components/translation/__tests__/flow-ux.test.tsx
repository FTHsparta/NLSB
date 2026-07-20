/**
 * Contract tests for the two flow-UX behaviors added after Phase 11:
 *
 * CONTRACT 12 -- dedicated loading view: while /translate or /confirm is in
 * flight, the input/gate surface is REPLACED (unmounted) by a centered
 * loading view hosting the existing Phase 9 staged-progress content. Error
 * paths restore the prior surface with its banner, including the typed
 * strategy text (the input's internal state dies on unmount, so the flow
 * carries the draft).
 *
 * CONTRACT 13 -- "Run another backtest": a RESET reducer action returns the
 * machine to a clean idle. Stale results MUST be structurally unmounted --
 * results render is gated on phase === "results" AND result != null, and
 * RESET clears both in one dispatch.
 *
 * Same fake-api pattern as contracts.test.tsx; fixtures are the same real
 * backend dumps.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TranslateFlow } from "../TranslateFlow";
import type { TranslationApi } from "@/lib/translation/api";
import type { TranslationPayload } from "@/lib/translation/types";
import type { RobustnessResult } from "@/lib/robustness/types";

import ordinaryFixture from "@/fixtures/translation/ordinary_assumptions.json";
import passFixture from "@/fixtures/robustness/pass.json";

const ORDINARY = ordinaryFixture as unknown as TranslationPayload;
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

/** A promise the test resolves/rejects by hand, to hold a request "in
 * flight" for a deterministic window. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const TYPED = "buy SPY when RSI < 30";

function typeAndSubmit(text = TYPED) {
  fireEvent.change(screen.getByTestId("nl-input"), { target: { value: text } });
  fireEvent.click(screen.getByTestId("translate-submit"));
}

describe("CONTRACT 12: loading view REPLACES the surface while a request is in flight", () => {
  it("translating: the input view is unmounted, the loading view (with the same indicator) is mounted; the gate mounts on success", async () => {
    const d = deferred<TranslationPayload>();
    const api = fakeApi({ translate: vi.fn(() => d.promise) });
    render(<TranslateFlow api={api} />);

    typeAndSubmit();

    // Replaced, not dimmed: the input surface is GONE from the document.
    expect(screen.queryByTestId("translate-input-view")).not.toBeInTheDocument();
    expect(screen.getByTestId("loading-view")).toBeInTheDocument();
    expect(screen.getByTestId("translating-indicator")).toBeInTheDocument();

    await act(async () => {
      d.resolve(ORDINARY);
      await d.promise;
    });

    await waitFor(() => expect(screen.getByTestId("gate")).toBeInTheDocument());
    expect(screen.queryByTestId("loading-view")).not.toBeInTheDocument();
  });

  it("translating error: the input view returns with the error banner AND the typed text preserved", async () => {
    const d = deferred<TranslationPayload>();
    const api = fakeApi({ translate: vi.fn(() => d.promise) });
    render(<TranslateFlow api={api} />);

    typeAndSubmit();
    expect(screen.queryByTestId("translate-input-view")).not.toBeInTheDocument();

    await act(async () => {
      d.reject(new Error("/translate failed (500): boom"));
      await d.promise.catch(() => {});
    });

    await waitFor(() => expect(screen.getByTestId("translate-error")).toBeInTheDocument());
    expect(screen.getByTestId("translate-input-view")).toBeInTheDocument();
    expect(screen.queryByTestId("loading-view")).not.toBeInTheDocument();
    // The unmount/remount must not eat the user's strategy text.
    expect(screen.getByTestId("nl-input")).toHaveValue(TYPED);
  });

  it("confirming: input AND gate are unmounted, the loading view (stages + elapsed) is mounted; results mount on success", async () => {
    const d = deferred<RobustnessResult>();
    const api = fakeApi({ confirm: vi.fn(() => d.promise) });
    render(<TranslateFlow api={api} />);

    typeAndSubmit();
    await waitFor(() => expect(screen.getByTestId("gate")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("confirm-run-button"));

    expect(screen.queryByTestId("gate")).not.toBeInTheDocument();
    expect(screen.queryByTestId("confirm-gate")).not.toBeInTheDocument();
    expect(screen.queryByTestId("translate-input-view")).not.toBeInTheDocument();
    expect(screen.getByTestId("loading-view")).toBeInTheDocument();
    expect(screen.getByTestId("confirming-indicator")).toBeInTheDocument();
    expect(screen.getByTestId("confirming-indicator-elapsed")).toBeInTheDocument();

    await act(async () => {
      d.resolve(PASS_RESULT);
      await d.promise;
    });

    await waitFor(() => expect(screen.getByTestId("robustness-result-view")).toBeInTheDocument());
    expect(screen.queryByTestId("loading-view")).not.toBeInTheDocument();
  });

  it("confirming error: the gate returns with the confirm error banner, never results", async () => {
    const d = deferred<RobustnessResult>();
    const api = fakeApi({ confirm: vi.fn(() => d.promise) });
    render(<TranslateFlow api={api} />);

    typeAndSubmit();
    await waitFor(() => expect(screen.getByTestId("gate")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("confirm-run-button"));
    expect(screen.queryByTestId("gate")).not.toBeInTheDocument();

    await act(async () => {
      d.reject(new Error("/confirm failed (500): backtest failed"));
      await d.promise.catch(() => {});
    });

    await waitFor(() => expect(screen.getByTestId("confirm-error")).toBeInTheDocument());
    expect(screen.getByTestId("gate")).toBeInTheDocument();
    expect(screen.getByTestId("confirm-gate")).toBeInTheDocument();
    expect(screen.queryByTestId("loading-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
  });
});

describe("CONTRACT 13: 'Run another backtest' resets the machine to a clean idle", () => {
  async function reachResults() {
    typeAndSubmit();
    await waitFor(() => expect(screen.getByTestId("gate")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("confirm-run-button"));
    await waitFor(() => expect(screen.getByTestId("robustness-result-view")).toBeInTheDocument());
  }

  it("clicking reset unmounts the results surface and remounts an EMPTY idle input, even under a ?s= prefill", async () => {
    const api = fakeApi();
    // initialText simulates arriving via /backtest?s=... -- reset must beat it.
    render(<TranslateFlow api={api} initialText="prefilled example strategy" />);
    expect(screen.getByTestId("nl-input")).toHaveValue("prefilled example strategy");

    await reachResults();
    expect(screen.getByTestId("reset-flow")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("reset-flow"));

    // Stale results are structurally gone -- phase and result were cleared
    // in the same dispatch, and the render is gated on both.
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verdict-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reset-flow")).not.toBeInTheDocument();
    expect(screen.queryByTestId("gate")).not.toBeInTheDocument();
    expect(screen.queryByTestId("loading-view")).not.toBeInTheDocument();

    // Clean idle: input mounted and EMPTY (prefill does not resurrect).
    expect(screen.getByTestId("translate-input-view")).toBeInTheDocument();
    expect(screen.getByTestId("nl-input")).toHaveValue("");
  });

  it("a full translate -> confirm cycle works again after reset", async () => {
    const api = fakeApi();
    render(<TranslateFlow api={api} />);

    await reachResults();
    fireEvent.click(screen.getByTestId("reset-flow"));
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();

    // Second full cycle on the same machine.
    await reachResults();
    expect(screen.getByTestId("verdict-card")).toBeInTheDocument();
    expect(api.translate).toHaveBeenCalledTimes(2);
    expect(api.confirm).toHaveBeenCalledTimes(2);
  });
});
