"use client";

import { useState } from "react";

export interface ConfirmGateProps {
  defaultTicker: string;
  onConfirm: (start: string, end: string | null) => void;
  disabled?: boolean;
}

/**
 * The hard gate: this is the ONLY UI control in the app that can trigger a
 * run. It renders only after a translate/correct has produced a
 * stated/assumed restatement (see `TranslateFlow`) -- there is no
 * auto-run, no run-on-translate path; a run only happens when the user
 * presses this button.
 */
export function ConfirmGate({ defaultTicker, onConfirm, disabled }: ConfirmGateProps) {
  const [start, setStart] = useState("2015-01-01");
  const [end, setEnd] = useState("");

  return (
    <div data-testid="confirm-gate" className="mt-6 space-y-4 rounded-lg border border-border bg-card p-6">
      <p className="text-sm text-muted-foreground">
        Backtest window for <span className="font-medium text-foreground">{defaultTicker}</span>:
      </p>
      <div className="flex gap-3">
        <input
          data-testid="confirm-start-date"
          type="date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          className="rounded-md border border-input bg-background px-2 py-1 text-sm text-foreground"
        />
        <input
          data-testid="confirm-end-date"
          type="date"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
          placeholder="(optional) end date"
          className="rounded-md border border-input bg-background px-2 py-1 text-sm text-foreground"
        />
      </div>
      <button
        type="button"
        data-testid="confirm-run-button"
        disabled={disabled}
        onClick={() => onConfirm(start, end || null)}
        className="rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-50"
      >
        Run this backtest
      </button>
    </div>
  );
}
