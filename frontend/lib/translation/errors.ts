/**
 * Turns a raw thrown error from `lib/translation/api.ts` into a friendly,
 * user-facing message plus the preserved raw detail for an optional
 * disclosure. A UI-level fact about the request (the network is down, the
 * service 500'd) is not a judgment about the strategy -- the same
 * distinction `TranslateFlow`'s `ErrorBanner` comment already draws -- so
 * none of this ever blames the user's strategy text for a transport error.
 *
 * `httpTranslationApi`'s `postJson` does not expose a structured numeric
 * status on the thrown error; it only embeds it in the message string
 * (`` `${path} failed (${res.status}): ${detail}` ``). A genuine network
 * failure (the backend isn't running) throws fetch's own `TypeError`,
 * whose message ("Failed to fetch") carries no such pattern at all. This
 * module's status detection is therefore necessarily a best-effort parse
 * of that "(NNN)" pattern, not a read of a structured field -- there isn't
 * one to read. If `api.ts` ever grows a typed `status` field on its
 * thrown errors, this should switch to reading it directly instead.
 */

export type TranslationAction = "translate" | "correct" | "confirm";

export interface ErrorDescription {
  /** Friendly, user-facing copy -- never a raw "(500)"/stack/etc. */
  message: string;
  /** The original error text, preserved verbatim for an optional disclosure. */
  detail: string;
  /**
   * The parsed HTTP status, or null for a transport failure that never got
   * one. Additive (Phase 12D): the funnel's `request_failed` event needs a
   * bounded, low-cardinality value, and re-parsing `detail` at the call site
   * would mean two copies of the same best-effort regex.
   */
  status: number | null;
}

const ACTION_VERB: Record<TranslationAction, string> = {
  translate: "translating your strategy",
  correct: "applying your correction",
  confirm: "running the backtest",
};

function extractStatus(raw: string): number | null {
  const match = raw.match(/\((\d{3})\)/);
  return match ? Number(match[1]) : null;
}

export function describeError(err: unknown, action: TranslationAction): ErrorDescription {
  const detail = err instanceof Error ? err.message : String(err);
  const verb = ACTION_VERB[action];
  const status = extractStatus(detail);

  if (status === null) {
    return { message: `Couldn't reach the service while ${verb}. Make sure it's running and try again.`, detail, status };
  }
  if (status === 429) {
    return { message: `Rate-limited while ${verb}. Try again in a moment.`, detail, status };
  }
  if (status === 408 || status === 504) {
    return { message: `Timed out while ${verb}. Try again.`, detail, status };
  }
  if (status >= 500) {
    return {
      message: `Something went wrong while ${verb} -- this is not a problem with your strategy. Try again shortly.`,
      detail,
      status,
    };
  }
  return {
    message: `Your request couldn't be processed while ${verb}. Try again, or adjust your strategy.`,
    detail,
    status,
  };
}
