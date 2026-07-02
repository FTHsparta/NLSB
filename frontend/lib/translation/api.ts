import type { Assumption, TranslationPayload } from "./types";
import type { RobustnessResult } from "@/lib/robustness/types";
import { apiUrl } from "@/lib/apiBase";

/**
 * Thin fetch wrappers over the three routes `app/main.py` wires to
 * `app.translation.service`. No logic lives here -- each function posts
 * the request body and returns the parsed JSON response verbatim. This is
 * the production implementation injected as `TranslateFlow`'s default
 * `api` prop; tests inject a fake instead, the same dependency-override
 * pattern `main.py` uses for the LLM client / price fetcher in its own
 * tests.
 */

export interface TranslationApi {
  translate(nlText: string): Promise<TranslationPayload>;
  correct(originalNl: string, priorIr: Record<string, unknown>, correctionText: string): Promise<TranslationPayload>;
  confirm(
    ir: Record<string, unknown>,
    assumptions: Assumption[],
    ticker: string,
    start: string,
    end?: string | null
  ): Promise<RobustnessResult>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${path} failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const httpTranslationApi: TranslationApi = {
  translate(nlText) {
    return postJson<TranslationPayload>("/translate", { nl_text: nlText });
  },
  correct(originalNl, priorIr, correctionText) {
    return postJson<TranslationPayload>("/correct", {
      original_nl: originalNl,
      prior_ir: priorIr,
      correction_text: correctionText,
    });
  },
  confirm(ir, assumptions, ticker, start, end) {
    return postJson<RobustnessResult>("/confirm", { ir, assumptions, ticker, start, end: end ?? null });
  },
};
