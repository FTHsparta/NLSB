"use client";

import { useState } from "react";

import { EXAMPLE_STRATEGIES } from "@/lib/examples";
import { MOTION } from "@/lib/motion";

export interface TranslateInputViewProps {
  onSubmit: (nlText: string) => void;
  disabled?: boolean;
  /** Prefill (e.g. an example carried from the landing page via ?s=). */
  initialText?: string;
}

const STRATEGY_PLACEHOLDER =
  "Buy SPY when RSI(14) drops below 30, sell when it rises above 70.";

/** Plain-English strategy input -- the app's front door. Submitting calls
 * `/translate` (via the parent flow) -- never anything that runs a backtest. */
export function TranslateInputView({ onSubmit, disabled, initialText }: TranslateInputViewProps) {
  const [text, setText] = useState(initialText ?? "");

  return (
    <div data-testid="translate-input-view" className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Backtest a strategy
        </h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          Describe it in plain English. You&apos;ll review every assumption before
          anything runs.
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
                className={`inline-flex min-h-11 items-center rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground disabled:opacity-50 sm:min-h-0 sm:px-3 sm:py-1.5 sm:text-xs ${MOTION.interactive} hover:border-foreground/40 hover:bg-muted`}
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
          className={`min-h-11 rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-50 sm:min-h-0 ${MOTION.interactive} hover:opacity-90 active:opacity-80`}
        >
          Translate
        </button>
      </form>
    </div>
  );
}
