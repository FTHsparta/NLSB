"use client";

import { useState } from "react";
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
 * The full input -> translate -> confirm gate. State machine, by design,
 * has exactly one path to a result: `result` is set ONLY inside
 * `handleConfirm`, which is wired ONLY to `ConfirmGate`'s button -- there
 * is no other call to `api.confirm` anywhere in this component, and
 * `ConfirmGate` itself is the only place that calls it. `RobustnessResultView`
 * (the 5a renderer) is rendered only when `result` is non-null, so it is
 * structurally unreachable from `translate`/`correct` alone.
 */
export function TranslateFlow({ api = httpTranslationApi }: TranslateFlowProps) {
  const [originalNl, setOriginalNl] = useState<string | null>(null);
  const [translation, setTranslation] = useState<TranslationPayload | null>(null);
  const [result, setResult] = useState<RobustnessResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleTranslate(nlText: string) {
    setError(null);
    setResult(null);
    try {
      const response = await api.translate(nlText);
      setOriginalNl(nlText);
      setTranslation(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleCorrect(correctionText: string) {
    if (!originalNl || !translation?.ir) return;
    setError(null);
    try {
      const response = await api.correct(originalNl, translation.ir, correctionText);
      setTranslation(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleConfirm(start: string, end: string | null) {
    if (!translation?.ir) return;
    setError(null);
    try {
      const ticker = (translation.ir.asset as { ticker: string }).ticker;
      const response = await api.confirm(translation.ir, translation.assumptions, ticker, start, end);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div data-testid="translate-flow" className="mx-auto max-w-2xl space-y-6 p-6">
      {error && <p data-testid="translate-flow-error" className="text-red-600">{error}</p>}

      {!result && <TranslateInputView onSubmit={handleTranslate} />}

      {!result && translation?.status === "ok" && translation.restatement && (
        <>
          <AssumptionsView restatement={translation.restatement} assumptions={translation.assumptions} />
          <CorrectionBox onSubmit={handleCorrect} />
          <ConfirmGate
            defaultTicker={(translation.ir?.asset as { ticker: string })?.ticker ?? ""}
            onConfirm={handleConfirm}
          />
        </>
      )}

      {!result && translation && translation.status !== "ok" && (
        <p data-testid="translate-flow-message" className="text-zinc-700 dark:text-zinc-300">
          {translation.message}
        </p>
      )}

      {result && <RobustnessResultView result={result} />}
    </div>
  );
}

function CorrectionBox({ onSubmit }: { onSubmit: (text: string) => void }) {
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
        placeholder="Something wrong? Describe the correction in plain text."
        className="w-full rounded-md border border-zinc-300 p-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        rows={2}
      />
      <button
        type="submit"
        data-testid="correction-submit"
        disabled={!text.trim()}
        className="rounded-md border border-zinc-400 px-3 py-1.5 text-sm disabled:opacity-50"
      >
        Submit correction
      </button>
    </form>
  );
}
