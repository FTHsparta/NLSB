/**
 * Contract tests for the dedicated confirm view (post-Phase-13 polish): at
 * the gate, the input surface is now REPLACED, not supplemented -- before
 * this, `TranslateInputView` and the assumptions/warning/confirm-button
 * block rendered simultaneously (the input's `!isLoading` gate never
 * excluded `atGate`), so a user could still see and edit the raw textarea
 * while reviewing what was already translated.
 *
 * This is a `gate`-phase change, not the literal reducer `confirming`
 * phase (the in-flight /confirm call), which already replaces the input
 * with a generic loading view (CONTRACT 12, flow-ux.test.tsx) and is left
 * untouched here -- those pinned assertions are not modified by this file.
 *
 * "Back to edit" is a new BACK_TO_EDIT reducer action, lighter than RESET:
 * it returns to phase "idle" without discarding `translation`/`result`,
 * reusing the same `draft` field the loading view already relies on to
 * preserve the user's exact submitted text across the unmount/remount.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const TYPED = "buy SPY when RSI < 30";

async function reachGate(api: TranslationApi) {
  render(<TranslateFlow api={api} />);
  fireEvent.change(screen.getByTestId("nl-input"), { target: { value: TYPED } });
  fireEvent.click(screen.getByTestId("translate-submit"));
  await waitFor(() => expect(screen.getByTestId("gate")).toBeInTheDocument());
}

describe("dedicated confirm view: the gate REPLACES the input, not appends beneath it", () => {
  it("at the gate, the input is not in the document and the confirm view (assumptions + confirm button) is", async () => {
    const api = fakeApi();
    await reachGate(api);

    expect(screen.queryByTestId("translate-input-view")).not.toBeInTheDocument();
    expect(screen.getByTestId("gate")).toBeInTheDocument();
    expect(screen.getByTestId("assumptions-view")).toBeInTheDocument();
    expect(screen.getByTestId("confirm-gate")).toBeInTheDocument();
  });

  it("stays replaced during the correcting sub-loop (the disabled correction box is the right in-place treatment, not the raw input)", async () => {
    const d = new Promise<TranslationPayload>(() => {}); // never resolves -- holds "correcting"
    const api = fakeApi({ correct: vi.fn(() => d) });
    await reachGate(api);

    fireEvent.change(screen.getByTestId("correction-input"), { target: { value: "use RSI(20) instead" } });
    fireEvent.click(screen.getByTestId("correction-submit"));

    expect(screen.queryByTestId("translate-input-view")).not.toBeInTheDocument();
    expect(screen.getByTestId("gate")).toBeInTheDocument();
  });

  it("the literal in-flight confirming phase is untouched: it still shows the generic loading view, not this confirm view", async () => {
    const d = new Promise<RobustnessResult>(() => {}); // never resolves -- holds "confirming"
    const api = fakeApi({ confirm: vi.fn(() => d) });
    await reachGate(api);

    fireEvent.click(screen.getByTestId("confirm-run-button"));

    expect(screen.queryByTestId("gate")).not.toBeInTheDocument();
    expect(screen.queryByTestId("confirm-gate")).not.toBeInTheDocument();
    expect(screen.getByTestId("loading-view")).toBeInTheDocument();
    expect(screen.getByTestId("confirming-indicator")).toBeInTheDocument();
  });
});

describe("'Back to edit' restores the input with the draft intact", () => {
  it("dispatches back to the input phase, prefilled with the exact text that was submitted", async () => {
    const api = fakeApi();
    await reachGate(api);

    fireEvent.click(screen.getByTestId("back-to-edit"));

    expect(screen.queryByTestId("gate")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assumptions-view")).not.toBeInTheDocument();
    expect(screen.getByTestId("translate-input-view")).toBeInTheDocument();
    expect(screen.getByTestId("nl-input")).toHaveValue(TYPED);
  });

  it("a full translate -> confirm cycle still works after using back to edit", async () => {
    const api = fakeApi();
    await reachGate(api);
    fireEvent.click(screen.getByTestId("back-to-edit"));

    fireEvent.change(screen.getByTestId("nl-input"), { target: { value: TYPED } });
    fireEvent.click(screen.getByTestId("translate-submit"));
    await waitFor(() => expect(screen.getByTestId("gate")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("confirm-run-button"));
    await waitFor(() => expect(screen.getByTestId("robustness-result-view")).toBeInTheDocument());
    expect(api.translate).toHaveBeenCalledTimes(2);
  });

  it("is disabled while a correction is in flight, so it cannot abandon an in-progress correction silently", async () => {
    const d = new Promise<TranslationPayload>(() => {});
    const api = fakeApi({ correct: vi.fn(() => d) });
    await reachGate(api);

    fireEvent.change(screen.getByTestId("correction-input"), { target: { value: "use RSI(20) instead" } });
    fireEvent.click(screen.getByTestId("correction-submit"));

    expect(screen.getByTestId("back-to-edit")).toBeDisabled();
  });
});
