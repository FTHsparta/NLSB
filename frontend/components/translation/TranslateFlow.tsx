"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import { RobustnessResultView } from "@/components/robustness/RobustnessResultView";
import { CONFIRM_STAGES, ProgressIndicator } from "@/components/chrome/ProgressIndicator";
import { EVENTS, trackEvent } from "@/lib/analytics";
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
  /** Parsed HTTP status, for the `request_failed` funnel event only. */
  status?: number | null;
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
  | { type: "TRANSLATE_ERROR"; message: string; detail?: string; status?: number | null }
  | { type: "CORRECT_START" }
  | { type: "CORRECT_SUCCESS"; payload: TranslationPayload }
  | { type: "CORRECT_ERROR"; message: string; detail?: string; status?: number | null }
  | { type: "CONFIRM_START" }
  | { type: "CONFIRM_SUCCESS"; payload: RobustnessResult }
  | { type: "CONFIRM_ERROR"; message: string; detail?: string; status?: number | null }
  | { type: "RESET" }
  | { type: "BACK_TO_EDIT" };

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
        error: { action: "translate", message: action.message, detail: action.detail, status: action.status },
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
        error: { action: "correct", message: action.message, detail: action.detail, status: action.status },
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
        error: { action: "confirm", message: action.message, detail: action.detail, status: action.status },
      };
    case "RESET":
      // Whole-machine reset: back to a clean idle. `result` is cleared and
      // `phase` leaves "results" in the same dispatch, so the results
      // surface (gated on BOTH) cannot survive the transition. `draft: ""`
      // (not null) makes the remounted input empty even under a ?s= prefill.
      return { ...INITIAL_STATE, draft: "" };
    case "BACK_TO_EDIT":
      // Lighter than RESET: returns to the input from the confirm view
      // without discarding the last translation, so a same-text resubmit
      // isn't required -- draft already holds the right text (set once at
      // TRANSLATE_START, untouched since), so the remounted input is
      // prefilled with exactly what the user submitted, reusing the same
      // draft-preservation mechanism the loading view already relies on.
      return { ...state, phase: "idle", error: null };
    default:
      return state;
  }
}

/**
 * Funnel instrumentation as a pure OBSERVER of the state machine.
 *
 * This is an effect watching `phase`, not a call inside any handler, and that
 * placement is the invariant rather than a style preference: effects run after
 * commit, so nothing here can cause, block, or reorder a transition even if
 * `trackEvent` were to misbehave. A tracking call sitting inside
 * `handleConfirm` would sit on the confirm path itself, which is exactly how
 * gate integrity erodes.
 *
 * `gate_abandoned` is the one event with no happy-path trigger, so it is
 * derived two ways: leaving the gate backwards (gate/correcting -> idle) and
 * unmounting while still at the gate, which is what navigating away looks
 * like. Without both, the confirmed/abandoned ratio -- the only direct
 * measurement of whether strangers accept the gate -- silently reads high.
 */
function useFunnelEvents(state: FlowState) {
  const previousPhase = useRef<Phase | null>(null);
  // Read by the unmount cleanup, which would otherwise close over a stale
  // phase from the render that installed it. Written in an effect, never
  // during render -- a ref mutated mid-render can desync from what was
  // actually committed.
  const phaseRef = useRef<Phase>(state.phase);
  useEffect(() => {
    phaseRef.current = state.phase;
  }, [state.phase]);

  useEffect(() => {
    const from = previousPhase.current;
    const to = state.phase;
    previousPhase.current = to;
    if (from === to) return;

    switch (to) {
      case "translating":
        trackEvent(EVENTS.strategySubmitted);
        break;
      case "gate":
        // Only a genuine arrival at the gate. Returning from a failed confirm
        // or correction is a re-entry, not a new gate impression.
        if (from !== "confirming" && from !== "correcting") trackEvent(EVENTS.gateShown);
        break;
      case "confirming":
        trackEvent(EVENTS.gateConfirmed);
        break;
      case "results":
        trackEvent(EVENTS.resultShown, { kind: state.result?.kind ?? null, verdict: verdictKind(state.result) });
        break;
      case "idle":
        if (from === "gate" || from === "correcting") trackEvent(EVENTS.gateAbandoned);
        break;
      default:
        break;
    }
  }, [state.phase, state.result]);

  // Errors are reported off the error object, not the phase: a failed confirm
  // and a failed correction both land back on "gate", so phase alone can't
  // distinguish them from an ordinary return.
  const lastError = useRef<ActionError | null>(null);
  useEffect(() => {
    if (state.error && state.error !== lastError.current) {
      trackEvent(EVENTS.requestFailed, { action: state.error.action, status: state.error.status ?? null });
    }
    lastError.current = state.error;
  }, [state.error]);

  useEffect(() => {
    return () => {
      const phase = phaseRef.current;
      if (phase === "gate" || phase === "correcting") trackEvent(EVENTS.gateAbandoned);
    };
  }, []);
}

/** Bounded, low-cardinality: one of the four verdict names, or null. */
function verdictKind(result: RobustnessResult | null): string | null {
  if (!result || result.kind !== "full") return null;
  return result.verdict?.verdict ?? null;
}

export function TranslateFlow({ api = httpTranslationApi, initialText }: TranslateFlowProps) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  useFunnelEvents(state);

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
      const { message, detail, status } = describeError(err, "translate");
      dispatch({ type: "TRANSLATE_ERROR", message, detail, status });
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
      const { message, detail, status } = describeError(err, "correct");
      dispatch({ type: "CORRECT_ERROR", message, detail, status });
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
      const { message, detail, status } = describeError(err, "confirm");
      dispatch({ type: "CONFIRM_ERROR", message, detail, status });
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
  // Phase-gated explicitly (not just "not results/not loading"): BACK_TO_EDIT
  // deliberately leaves `translation` intact so a same-text resubmit isn't
  // required, which means checking translation-shape alone would leave the
  // gate incorrectly "on" once phase returns to "idle".
  const atGate =
    (state.phase === "gate" || state.phase === "correcting") &&
    state.translation?.status === "ok" &&
    !!state.translation.restatement;

  return (
    <div data-testid="translate-flow" className="mx-auto max-w-2xl space-y-8 p-6">
      {state.error?.action === "translate" && (
        <ErrorBanner testId="translate-error" message={state.error.message} detail={state.error.detail} />
      )}

      {state.phase !== "results" && !isLoading && !atGate && (
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
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-xl font-semibold text-foreground">Review before you run it</h2>
              <button
                type="button"
                data-testid="back-to-edit"
                disabled={isCorrecting}
                onClick={() => dispatch({ type: "BACK_TO_EDIT" })}
                className={`min-h-11 shrink-0 rounded-md border border-border px-3 py-1.5 text-sm text-foreground disabled:opacity-50 sm:min-h-0 ${MOTION.interactive} hover:border-foreground/40 hover:bg-muted`}
              >
                ← Back to edit
              </button>
            </div>
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
          {/* Index 5 keeps the reveal strictly sequential after the result
              view's own wrappers (0..4, the limitations pointer included). */}
          <div className={MOTION.enterSlide} style={staggerDelay(5)}>
            <button
              type="button"
              data-testid="reset-flow"
              onClick={() => dispatch({ type: "RESET" })}
              className={`min-h-11 rounded-md border border-border px-4 py-2 text-sm text-foreground sm:min-h-0 ${MOTION.interactive} hover:border-foreground/40 hover:bg-muted`}
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
          <summary className="cursor-pointer select-none py-2 text-sm font-medium text-foreground sm:py-0">
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
        className={`min-h-11 rounded-md border border-border px-3 py-1.5 text-sm text-foreground disabled:opacity-50 sm:min-h-0 ${MOTION.interactive} hover:border-foreground/40 hover:bg-muted`}
      >
        Submit correction
      </button>
    </form>
  );
}
