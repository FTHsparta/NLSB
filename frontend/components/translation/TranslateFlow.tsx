"use client";

import { useReducer, useState } from "react";
import { RobustnessResultView } from "@/components/robustness/RobustnessResultView";
import { CONFIRM_STAGES, ProgressIndicator } from "@/components/chrome/ProgressIndicator";
import { MOTION, staggerDelay } from "@/lib/motion";
import type { RobustnessResult } from "@/lib/robustness/types";
import { httpTranslationApi, type TranslationApi } from "@/lib/translation/api";
import { describeError } from "@/lib/translation/errors";
import type { TranslationPayload } from "@/lib/translation/types";
import { AssumptionsView } from "./AssumptionsView";
import { ConfirmGate } from "./ConfirmGate";
import { TranslateInputView } from "./TranslateInputView";

export interface TranslateFlowProps {
  /** Defaults to the real HTTP implementation; tests inject a fake. */
  api?: TranslationApi;
  /** Prefill for the strategy box (landing-page example via /backtest?s=). */
  initialText?: string;
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
  detail?: string;
}

interface FlowState {
  phase: Phase;
  originalNl: string | null;
  translation: TranslationPayload | null;
  result: RobustnessResult | null;
  error: ActionError | null;
  /**
   * Seed for the strategy textarea on (re)mount. The loading view unmounts
   * `TranslateInputView` during "translating", destroying its internal text
   * state, so the submitted text is carried here and seeded back when the
   * input remounts (TRANSLATE_ERROR, unsupported). `null` means "defer to
   * the ?s= prefill prop"; RESET sets `""` so a reset input is empty even
   * when the page was opened with a prefill.
   */
  draft: string | null;
}

type FlowAction =
  | { type: "TRANSLATE_START"; nlText: string }
  | { type: "TRANSLATE_SUCCESS"; nlText: string; payload: TranslationPayload }
  | { type: "TRANSLATE_ERROR"; message: string; detail?: string }
  | { type: "CORRECT_START" }
  | { type: "CORRECT_SUCCESS"; payload: TranslationPayload }
  | { type: "CORRECT_ERROR"; message: string; detail?: string }
  | { type: "CONFIRM_START" }
  | { type: "CONFIRM_SUCCESS"; payload: RobustnessResult }
  | { type: "CONFIRM_ERROR"; message: string; detail?: string }
  | { type: "RESET" };

const INITIAL_STATE: FlowState = {
  phase: "idle",
  originalNl: null,
  translation: null,
  result: null,
  error: null,
  draft: null,
};

function reducer(state: FlowState, action: FlowAction): FlowState {
  switch (action.type) {
    case "TRANSLATE_START":
      return { ...state, phase: "translating", draft: action.nlText, error: null };
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
      return {
        ...state,
        phase: "idle",
        error: { action: "translate", message: action.message, detail: action.detail },
      };
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
      return {
        ...state,
        phase: "gate",
        error: { action: "correct", message: action.message, detail: action.detail },
      };
    case "CONFIRM_START":
      return { ...state, phase: "confirming", error: null };
    case "CONFIRM_SUCCESS":
      return { ...state, phase: "results", result: action.payload, error: null };
    case "CONFIRM_ERROR":
      // Back to the gate, not results -- a failed confirm must never set
      // `result`, which is the only thing that can mount the renderer.
      return {
        ...state,
        phase: "gate",
        error: { action: "confirm", message: action.message, detail: action.detail },
      };
    case "RESET":
      // Whole-machine reset: back to a clean idle. `result` is cleared and
      // `phase` leaves "results" in the same dispatch, so the results
      // surface (gated on BOTH) cannot survive the transition. `draft: ""`
      // (not null) makes the remounted input empty even under a ?s= prefill.
      return { ...INITIAL_STATE, draft: "" };
    default:
      return state;
  }
}

export function TranslateFlow({ api = httpTranslationApi, initialText }: TranslateFlowProps) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  async function handleTranslate(nlText: string) {
    // Double-submit guard: never launch a second in-flight request. The
    // buttons also disable during a request, but this makes it structural,
    // not merely visual -- a programmatic or racing double-fire is a no-op.
    if (state.phase === "translating") return;
    dispatch({ type: "TRANSLATE_START", nlText });
    try {
      const response = await api.translate(nlText);
      dispatch({ type: "TRANSLATE_SUCCESS", nlText, payload: response });
    } catch (err) {
      const { message, detail } = describeError(err, "translate");
      dispatch({ type: "TRANSLATE_ERROR", message, detail });
    }
  }

  async function handleCorrect(correctionText: string) {
    if (!state.originalNl || !state.translation?.ir) return;
    if (state.phase === "correcting") return;
    dispatch({ type: "CORRECT_START" });
    try {
      const response = await api.correct(state.originalNl, state.translation.ir, correctionText);
      dispatch({ type: "CORRECT_SUCCESS", payload: response });
    } catch (err) {
      const { message, detail } = describeError(err, "correct");
      dispatch({ type: "CORRECT_ERROR", message, detail });
    }
  }

  async function handleConfirm(start: string, end: string | null) {
    if (!state.translation?.ir) return;
    if (state.phase === "confirming") return;
    dispatch({ type: "CONFIRM_START" });
    try {
      const ticker = (state.translation.ir.asset as { ticker: string }).ticker;
      const response = await api.confirm(state.translation.ir, state.translation.assumptions, ticker, start, end);
      dispatch({ type: "CONFIRM_SUCCESS", payload: response });
    } catch (err) {
      const { message, detail } = describeError(err, "confirm");
      dispatch({ type: "CONFIRM_ERROR", message, detail });
    }
  }

  const isTranslating = state.phase === "translating";
  const isCorrecting = state.phase === "correcting";
  const isConfirming = state.phase === "confirming";
  // The full-surface loading treatment: while /translate or /confirm is in
  // flight the input/gate surface is REPLACED (unmounted, not dimmed) by a
  // centered progress view -- the wait is the page's only content, never
  // progress text appended under a still-visible surface. "correcting" is
  // deliberately NOT a loading phase: it's an in-gate sub-loop whose
  // disabled correction box is the right in-place treatment.
  const isLoading = isTranslating || isConfirming;
  const atGate =
    state.translation?.status === "ok" && !!state.translation.restatement && state.phase !== "results" && !isLoading;

  return (
    <div data-testid="translate-flow" className="mx-auto max-w-2xl space-y-8 p-6">
      {state.error?.action === "translate" && (
        <ErrorBanner testId="translate-error" message={state.error.message} detail={state.error.detail} />
      )}

      {state.phase !== "results" && !isLoading && (
        <TranslateInputView
          onSubmit={handleTranslate}
          disabled={isTranslating}
          initialText={state.draft ?? initialText}
        />
      )}

      {isTranslating && (
        <div data-testid="loading-view" className={`flex min-h-[40vh] items-center justify-center ${MOTION.enter}`}>
          <ProgressIndicator testId="translating-indicator" label="Translating your strategy…" />
        </div>
      )}

      {isConfirming && (
        <div data-testid="loading-view" className={`flex min-h-[40vh] items-center justify-center ${MOTION.enter}`}>
          <ProgressIndicator
            testId="confirming-indicator"
            label="Running backtest and robustness checks…"
            stages={CONFIRM_STAGES}
            showElapsed
          />
        </div>
      )}

      {atGate && (
        <div data-testid="gate" className={`space-y-8 ${MOTION.enterSlide}`}>
          <header className="space-y-1 border-b border-border pb-6">
            <h2 className="text-xl font-semibold text-foreground">Review before you run it</h2>
            <p className="text-sm text-muted-foreground">
              Nothing has run yet. Check what you stated against what the system assumed,
              then confirm below to run the backtest.
            </p>
          </header>

          <AssumptionsView restatement={state.translation!.restatement!} assumptions={state.translation!.assumptions} />

          <div className="space-y-4 border-t border-border pt-6">
            <header className="space-y-1">
              <h3 className="text-lg font-semibold text-foreground">Ready to run this backtest?</h3>
              <p className="text-sm text-muted-foreground">
                Confirm to run it exactly as stated above, or describe a correction first.
              </p>
            </header>

            {state.error?.action === "confirm" && (
              <ErrorBanner testId="confirm-error" message={state.error.message} detail={state.error.detail} />
            )}
            <ConfirmGate
              defaultTicker={(state.translation!.ir?.asset as { ticker: string })?.ticker ?? ""}
              onConfirm={handleConfirm}
              disabled={isConfirming}
            />

            <div className="space-y-2">
              <p className="text-sm font-medium text-foreground">Not right? Correct it instead.</p>
              {state.error?.action === "correct" && (
                <ErrorBanner testId="correct-error" message={state.error.message} detail={state.error.detail} />
              )}
              <CorrectionBox onSubmit={handleCorrect} disabled={isCorrecting} />
            </div>
          </div>
        </div>
      )}

      {state.phase !== "results" && !isLoading && state.translation && state.translation.status !== "ok" && (
        <p data-testid="translate-flow-message" className="text-foreground">
          {state.translation.message}
        </p>
      )}

      {state.phase === "results" && state.result && (
        <>
          <RobustnessResultView result={state.result} />
          {/* A flow control, not part of the result: lives here (after the
              renderer, dispatching into the state machine) so
              RobustnessResultView stays a pure renderer of backend judgment.
              Secondary monochrome styling -- it must not compete with the
              verdict. Constant classes/delay: motion stays judgment-blind. */}
          <div className={MOTION.enterSlide} style={staggerDelay(4)}>
            <button
              type="button"
              data-testid="reset-flow"
              onClick={() => dispatch({ type: "RESET" })}
              className={`rounded-md border border-border px-4 py-2 text-sm text-foreground ${MOTION.interactive} hover:border-foreground/40 hover:bg-muted`}
            >
              Run another backtest
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Monochrome by design, same as everything outside `VerdictCard` -- a
 * failed network call is a UI-level fact, not a judgment about the
 * strategy, but the strict palette rule for this phase draws no
 * exception for it. Prominence (border, filled background, near-white
 * text) carries the "something went wrong" weight instead of color.
 *
 * `message` is `describeError`'s friendly copy -- the only thing visible
 * by default. `detail` is the raw, preserved error text (a "(500): ..."
 * string, a fetch `TypeError`, etc.) -- it renders inside a collapsed
 * `<details>` so it never appears as the headline, but stays one click
 * away for anyone who wants it.
 */
function ErrorBanner({ testId, message, detail }: { testId: string; message: string; detail?: string }) {
  return (
    <div data-testid={testId} role="alert" className={`rounded-lg border-2 border-foreground/40 bg-muted p-4 text-foreground ${MOTION.enterSlide}`}>
      <p data-testid={`${testId}-message`}>{message}</p>
      {detail && (
        <details className="mt-2">
          <summary className="cursor-pointer select-none text-sm font-medium text-foreground">
            Technical details
          </summary>
          <p data-testid={`${testId}-detail`} className="mt-1 whitespace-pre-wrap font-mono text-xs text-muted-foreground">
            {detail}
          </p>
        </details>
      )}
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
        className="w-full rounded-lg border border-input bg-card p-2 text-sm text-foreground placeholder:text-muted-foreground"
        rows={2}
      />
      <button
        type="submit"
        data-testid="correction-submit"
        disabled={disabled || !text.trim()}
        className={`rounded-md border border-border px-3 py-1.5 text-sm text-foreground disabled:opacity-50 ${MOTION.interactive} hover:border-foreground/40 hover:bg-muted`}
      >
        Submit correction
      </button>
    </form>
  );
}
