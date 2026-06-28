"use client";

import { useState } from "react";

export interface TranslateInputViewProps {
  onSubmit: (nlText: string) => void;
  disabled?: boolean;
}

const STRATEGY_PLACEHOLDER =
  "Buy SPY when RSI(14) drops below 30, sell when it rises above 70.";

/** Plain-English strategy input -- the app's front door. Submitting calls
 * `/translate` (via the parent flow) -- never anything that runs a backtest. */
export function TranslateInputView({ onSubmit, disabled }: TranslateInputViewProps) {
  const [text, setText] = useState("");

  return (
    <div data-testid="translate-input-view" className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">NLSB</h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          Describe a trading strategy in plain English and get an honest backtest --
          one built to surface what other backtesters hide, not flatter you with a
          curve.
        </p>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) onSubmit(text.trim());
        }}
        className="space-y-4"
      >
        <div className="space-y-2">
          <label htmlFor="nl-input" className="block text-sm font-medium text-foreground">
            Your strategy
          </label>
          <textarea
            id="nl-input"
            data-testid="nl-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={disabled}
            placeholder={STRATEGY_PLACEHOLDER}
            className="w-full rounded-lg border border-input bg-card p-4 text-base leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-foreground/30"
            rows={6}
          />
        </div>
        <button
          type="submit"
          data-testid="translate-submit"
          disabled={disabled || !text.trim()}
          className="rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-50"
        >
          Translate
        </button>
      </form>
    </div>
  );
}
