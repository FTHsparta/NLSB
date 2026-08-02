import { track } from "@vercel/analytics";

/**
 * Funnel instrumentation.
 *
 * Instrumentation is the one category of work here with an expiring window.
 * Every other gap can be fixed after it is observed failing; a traffic event
 * that arrives un-instrumented is unmeasurable forever. That is the whole
 * reason this exists before it is obviously needed.
 *
 * Three rules, all enforced below rather than left to call sites:
 *
 *   1. NO USER TEXT, EVER. Strategy descriptions are free-text input that
 *      could contain anything -- credentials, personal details, a pasted
 *      email. Only bounded, low-cardinality values are permitted, and
 *      `sanitizeProps` drops anything that isn't one instead of trusting
 *      each caller to remember.
 *   2. FIRE AND FORGET. A tracking failure must never break the flow, block
 *      a state transition, or reach the user, so every call is wrapped.
 *   3. INERT UNLESS PRODUCTION IN A BROWSER. No event fires during SSR, and
 *      none fires in dev or under the test runner -- the same "off by
 *      default in the suite, opted into explicitly" shape the rate limiter
 *      and the translation cache already use on the backend.
 */

/** The full event vocabulary. Constants so the set stays greppable. */
export const EVENTS = {
  exampleClicked: "example_clicked",
  strategySubmitted: "strategy_submitted",
  gateShown: "gate_shown",
  gateConfirmed: "gate_confirmed",
  gateAbandoned: "gate_abandoned",
  resultShown: "result_shown",
  requestFailed: "request_failed",
} as const;

export type EventName = (typeof EVENTS)[keyof typeof EVENTS];

/** Only these shapes are ever sent. Strings are additionally length-capped. */
export type EventProps = Record<string, string | number | boolean | null>;

export type AnalyticsSink = (name: EventName, props?: EventProps) => void;

/**
 * A string long enough for a verdict name or a chip slug and far too short
 * for a strategy description. A value that hits this cap is a bug in the
 * caller, so it is dropped rather than truncated -- silently sending half a
 * sentence would be worse than sending nothing.
 */
const MAX_STRING_LENGTH = 40;

let sink: AnalyticsSink | null = null;

/**
 * Test seam. The suite installs a sink to assert on emitted events; without
 * one, events are inert everywhere except a production browser. Returns a
 * disposer so a test can't leak its sink into the next one.
 */
export function setAnalyticsSink(next: AnalyticsSink | null): () => void {
  sink = next;
  return () => {
    sink = null;
  };
}

/**
 * Drop anything that isn't a bounded scalar.
 *
 * This is the enforcement point for "no strategy text in any payload". It is
 * deliberately a whitelist on VALUE SHAPE rather than a blacklist of known-
 * bad keys: a future call site that passes `{ nlText }` by accident emits an
 * event with that property dropped, instead of shipping user input to a
 * third party and waiting for someone to notice.
 */
export function sanitizeProps(props?: EventProps): EventProps | undefined {
  if (!props) return undefined;
  const clean: EventProps = {};
  for (const [key, value] of Object.entries(props)) {
    if (value === null || typeof value === "number" || typeof value === "boolean") {
      clean[key] = value;
      continue;
    }
    if (typeof value === "string" && value.length > 0 && value.length <= MAX_STRING_LENGTH) {
      clean[key] = value;
    }
  }
  return clean;
}

function isProductionBrowser(): boolean {
  if (typeof window === "undefined") return false; // never during SSR
  return process.env.NODE_ENV === "production";
}

/**
 * Emit one funnel event. Never throws, never returns a promise the caller
 * could await, and never participates in control flow -- callers must be
 * able to treat this as a no-op that happens to be observable.
 */
export function trackEvent(name: EventName, props?: EventProps): void {
  try {
    const safe = sanitizeProps(props);
    if (sink) {
      sink(name, safe);
      return;
    }
    if (!isProductionBrowser()) return;
    track(name, safe);
  } catch {
    // Fire and forget: instrumentation failure is never the user's problem.
  }
}
