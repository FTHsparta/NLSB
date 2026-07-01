"use client";

import { useState } from "react";

export interface TranslateInputViewProps {
  onSubmit: (nlText: string) => void;
  disabled?: boolean;
}

const STRATEGY_PLACEHOLDER =
  "Buy SPY when RSI(14) drops below 30, sell when it rises above 70.";

/** Beginner-friendly prefills -- each has a clean entry AND exit so none
 * trips the missing-exit SEVERITY_WARNING when actually translated. */
const EXAMPLE_STRATEGIES: { label: string; text: string }[] = [
  {
    label: "Golden cross (SPY)",
    text: "Buy SPY when SMA(50) crosses above SMA(200), sell when SMA(50) crosses below SMA(200).",
  },
  {
    label: "RSI mean reversion (QQQ)",
    text: "Buy QQQ when RSI(14) drops below 30, sell when RSI(14) rises above 70.",
  },
  {
    label: "200-day trend follow (AAPL)",
    text: "Buy AAPL when close crosses above SMA(200), sell when close crosses below SMA(200).",
  },
  {
    label: "20/50 crossover (MSFT)",
    text: "Buy MSFT when SMA(20) crosses above SMA(50), sell when SMA(20) crosses below SMA(50).",
  },
];

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

        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">New here? Try an example:</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_STRATEGIES.map((example) => (
              <button
                key={example.label}
                type="button"
                data-testid="example-strategy"
                disabled={disabled}
                onClick={() => setText(example.text)}
                className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground disabled:opacity-50"
              >
                {example.label}
              </button>
            ))}
          </div>
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
