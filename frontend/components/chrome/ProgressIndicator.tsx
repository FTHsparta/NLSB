"use client";

import { useEffect, useState } from "react";

import { MOTION } from "@/lib/motion";
import { useReducedMotion } from "@/lib/useReducedMotion";

export interface ProgressStage {
  /** Show this stage's text once elapsed seconds reach `after`. */
  after: number;
  text: string;
}

export interface ProgressIndicatorProps {
  testId: string;
  /** The steady headline for the whole wait (e.g. "Translating your strategy…"). */
  label: string;
  /**
   * Optional elapsed-driven sub-labels. These are an HONEST approximation --
   * the backend is a single synchronous call, so we cannot know the true
   * step, only how long we have been waiting. They are ordered to match the
   * real backend sequence and phrased as activity, never as a completion
   * percentage. No fake progress bar: an honesty tool does not draw a
   * precise-looking bar over an indeterminate wait.
   */
  stages?: ProgressStage[];
  /** Show a subtle "Ns elapsed" counter (useful for the long /confirm wait). */
  showElapsed?: boolean;
}

function currentStage(stages: ProgressStage[], elapsed: number): string | null {
  let text: string | null = null;
  for (const stage of stages) {
    if (elapsed >= stage.after) text = stage.text;
  }
  return text;
}

/**
 * A monochrome, indeterminate progress indicator (Phase 9 chrome; Phase 11
 * motion pass). It makes a wait honest, not precise: an indeterminate
 * spinner + a steady label + optional activity sub-labels + an elapsed
 * counter. It carries NO saturated color (INV-2) -- prominence and motion,
 * never hue. Still NO fake percentage/progress bar: indeterminate + honest
 * stage text remains the design.
 *
 * Under prefers-reduced-motion the spinner becomes a static glyph and the
 * stage label's soft pulse never applies (the pulse class is motion-safe
 * gated in CSS as well; the hook handles the spinner, which has no
 * sensible "static spin" rendering). All timing logic -- the elapsed tick,
 * the stage thresholds -- is identical in both modes: motion is
 * presentation, never behavior.
 */
export function ProgressIndicator({ testId, label, stages, showElapsed }: ProgressIndicatorProps) {
  const [elapsed, setElapsed] = useState(0);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    // Only tick when we actually display time-driven content.
    if (!showElapsed && !stages) return;
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, [showElapsed, stages]);

  const stage = stages ? currentStage(stages, elapsed) : null;

  return (
    <div
      data-testid={testId}
      role="status"
      aria-live="polite"
      className="flex items-start gap-3 rounded-lg border border-border bg-card p-4"
    >
      {reducedMotion ? (
        <span
          aria-hidden="true"
          data-testid={`${testId}-static-glyph`}
          className="mt-1 h-3 w-3 shrink-0 rounded-full bg-foreground/40"
        />
      ) : (
        <span
          aria-hidden="true"
          data-testid={`${testId}-spinner`}
          className="mt-0.5 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-foreground/25 border-t-foreground"
        />
      )}
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">{label}</p>
        {stage && (
          <p data-testid={`${testId}-stage`} className={`text-sm text-muted-foreground ${MOTION.pulse}`}>
            {stage}
          </p>
        )}
        {showElapsed && (
          <p data-testid={`${testId}-elapsed`} className="text-xs tabular-nums text-muted-foreground">
            {elapsed}s elapsed
          </p>
        )}
      </div>
    </div>
  );
}

/** Ordered to match the real backend sequence: fetch → backtest → the four
 * robustness checks. Thresholds are a rough, honest approximation of a
 * ~15–20s run, not a measured per-step clock. */
export const CONFIRM_STAGES: ProgressStage[] = [
  { after: 0, text: "Fetching price history…" },
  { after: 4, text: "Running the backtest…" },
  { after: 9, text: "Checking robustness: walk-forward, sensitivity, deflated Sharpe, and regime…" },
];
