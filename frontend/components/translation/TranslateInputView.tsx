"use client";

import { useState } from "react";

export interface TranslateInputViewProps {
  onSubmit: (nlText: string) => void;
  disabled?: boolean;
}

/** Plain-English strategy input. Submitting calls `/translate` (via the
 * parent flow) -- never anything that runs a backtest. */
export function TranslateInputView({ onSubmit, disabled }: TranslateInputViewProps) {
  const [text, setText] = useState("");

  return (
    <form
      data-testid="translate-input-view"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) onSubmit(text.trim());
      }}
      className="space-y-3"
    >
      <textarea
        data-testid="nl-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        placeholder="Describe your strategy in plain English, e.g. 'Buy SPY when RSI(14) drops below 30, sell when it rises above 70.'"
        className="w-full rounded-lg border border-input bg-card p-3 text-sm text-foreground placeholder:text-muted-foreground"
        rows={4}
      />
      <button
        type="submit"
        data-testid="translate-submit"
        disabled={disabled || !text.trim()}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
      >
        Translate
      </button>
    </form>
  );
}
