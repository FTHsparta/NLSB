"use client";

import { useReducer, useState } from "react";
import { RobustnessResultView } from "@/components/robustness/RobustnessResultView";
import type { RobustnessResult } from "@/lib/robustness/types";
import { httpTranslationApi, type TranslationApi } from "@/lib/translation/api";
import type { TranslationPayload } from "@/lib/translation/types";
import { AssumptionsView } from "./AssumptionsView";
import { ConfirmGate } from "./ConfirmGate";
import { TranslateInputView } from "./TranslateInputView";

export interface TranslateFlowProps {
  /** Defaults to the real HTTP implementation; tests inject a fake. */
  api?: TranslationApi;
}

/**
 * The page's state machine: idle -> translating -> gate -> confirming ->
 * results, with a correcting sub-loop off the gate. `result` is set ONLY
 * by `CONFIRM_SUCCESS`, which is dispatched ONLY inside `handleConfirm`,
 * which is wired ONLY to `ConfirmGate`'s button -- there is no other call
 * to `api.confirm` anywhere in this component. `phase` only ever reaches
 * `"results"` through that one path, and `RobustnessResultView` is gated
 * on `phase === "results"` (not merely on `result` being non-null), so a
 * stale `result` from an earlier confirm can't leak through after a
 * subsequent correction resets the gate.
 */
type Phase = "idle" | "translating" | "gate" | "correcting" | "confirming" | "results";

interface ActionError {
  action: "translate" | "correct" | "confirm";
  message: string;
}

interface FlowState {
  phase: Phase;
  originalNl: string | null;
  translation: TranslationPayload | null;
  result: RobustnessResult | null;
  error: ActionError | null;
}

type FlowAction =
  | { type: "TRANSLATE_START" }
  | { type: "TRANSLATE_SUCCESS"; nlText: string; payload: TranslationPayload }
  | { type: "TRANSLATE_ERROR"; message: string }
  | { type: "CORRECT_START" }
  | { type: "CORRECT_SUCCESS"; payload: TranslationPayload }
  | { type: "CORRECT_ERROR"; message: string }
  | { type: "CONFIRM_START" }
  | { type: "CONFIRM_SUCCESS"; payload: RobustnessResult }
  | { type: "CONFIRM_ERROR"; message: string };

const INITIAL_STATE: FlowState = {
  phase: "idle",
  originalNl: null,
  translation: null,
  result: null,
  error: null,
};

function reducer(state: FlowState, action: FlowAction): FlowState {
  switch (action.type) {
    case "TRANSLATE_START":
      return { ...state, phase: "translating", error: null };
    case "TRANSLATE_SUCCESS":
      return {
        ...state,
        phase: action.payload.status === "ok" ? "gate" : "idle",
        originalNl: action.nlText,
        translation: action.payload,
        result: null,
        error: null,
      };
    case "TRANSLATE_ERROR":
      return { ...state, phase: "idle", error: { action: "translate", message: action.message } };
    case "CORRECT_START":
      return { ...state, phase: "correcting", error: null };
    case "CORRECT_SUCCESS":
      return {
        ...state,
        phase: action.payload.status === "ok" ? "gate" : "idle",
        translation: action.payload,
        error: null,
      };
    case "CORRECT_ERROR":
      // Stay at the gate with the prior translation intact -- a failed
      // correction must not discard the last good stated/assumed split.
      return { ...state, phase: "gate", error: { action: "correct", message: action.message } };
    case "CONFIRM_START":
      return { ...state, phase: "confirming", error: null };
    case "CONFIRM_SUCCESS":
      return { ...state, phase: "results", result: action.payload, error: null };
    case "CONFIRM_ERROR":
      // Back to the gate, not results -- a failed confirm must never set
      // `result`, which is the only thing that can mount the renderer.
      return { ...state, phase: "gate", error: { action: "confirm", message: action.message } };
    default:
      return state;
  }
}

export function TranslateFlow({ api = httpTranslationApi }: TranslateFlowProps) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  async function handleTranslate(nlText: string) {
    dispatch({ type: "TRANSLATE_START" });
    try {
      const response = await api.translate(nlText);
      dispatch({ type: "TRANSLATE_SUCCESS", nlText, payload: response });
    } catch (err) {
      dispatch({ type: "TRANSLATE_ERROR", message: err instanceof Error ? err.message : String(err) });
    }
  }

  async function handleCorrect(correctionText: string) {
    if (!state.originalNl || !state.translation?.ir) return;
    dispatch({ type: "CORRECT_START" });
    try {
      const response = await api.correct(state.originalNl, state.translation.ir, correctionText);
      dispatch({ type: "CORRECT_SUCCESS", payload: response });
    } catch (err) {
      dispatch({ type: "CORRECT_ERROR", message: err instanceof Error ? err.message : String(err) });
    }
  }

  async function handleConfirm(start: string, end: string | null) {
    if (!state.translation?.ir) return;
    dispatch({ type: "CONFIRM_START" });
    try {
      const ticker = (state.translation.ir.asset as { ticker: string }).ticker;
      const response = await api.confirm(state.translation.ir, state.translation.assumptions, ticker, start, end);
      dispatch({ type: "CONFIRM_SUCCESS", payload: response });
    } catch (err) {
      dispatch({ type: "CONFIRM_ERROR", message: err instanceof Error ? err.message : String(err) });
    }
  }

  const isTranslating = state.phase === "translating";
  const isCorrecting = state.phase === "correcting";
  const isConfirming = state.phase === "confirming";
  const atGate = state.translation?.status === "ok" && !!state.translation.restatement && state.phase !== "results";

  return (
    <div data-testid="translate-flow" className="mx-auto max-w-2xl space-y-6 p-6">
      {state.error?.action === "translate" && (
        <p data-testid="translate-error" role="alert" className="text-red-600">
          {state.error.message}
        </p>
      )}

      {state.phase !== "results" && (
        <TranslateInputView onSubmit={handleTranslate} disabled={isTranslating} />
      )}

      {atGate && (
        <>
          <AssumptionsView restatement={state.translation!.restatement!} assumptions={state.translation!.assumptions} />

          {state.error?.action === "correct" && (
            <p data-testid="correct-error" role="alert" className="text-red-600">
              {state.error.message}
            </p>
          )}
          <CorrectionBox onSubmit={handleCorrect} disabled={isCorrecting} />

          {state.error?.action === "confirm" && (
            <p data-testid="confirm-error" role="alert" className="text-red-600">
              {state.error.message}
            </p>
          )}
          <ConfirmGate
            defaultTicker={(state.translation!.ir?.asset as { ticker: string })?.ticker ?? ""}
            onConfirm={handleConfirm}
            disabled={isConfirming}
          />
        </>
      )}

      {state.phase !== "results" && state.translation && state.translation.status !== "ok" && (
        <p data-testid="translate-flow-message" className="text-zinc-700 dark:text-zinc-300">
          {state.translation.message}
        </p>
      )}

      {state.phase === "results" && state.result && <RobustnessResultView result={state.result} />}
    </div>
  );
}

function CorrectionBox({ onSubmit, disabled }: { onSubmit: (text: string) => void; disabled?: boolean }) {
  const [text, setText] = useState("");
  return (
    <form
      data-testid="correction-box"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) {
          onSubmit(text.trim());
          setText("");
        }
      }}
      className="space-y-2"
    >
      <textarea
        data-testid="correction-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        placeholder="Something wrong? Describe the correction in plain text."
        className="w-full rounded-md border border-zinc-300 p-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        rows={2}
      />
      <button
        type="submit"
        data-testid="correction-submit"
        disabled={disabled || !text.trim()}
        className="rounded-md border border-zinc-400 px-3 py-1.5 text-sm disabled:opacity-50"
      >
        Submit correction
      </button>
    </form>
  );
}
