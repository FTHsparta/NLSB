import Link from "next/link";

import { MOTION } from "@/lib/motion";

export interface ErrorSurfaceProps {
  /** Short, mechanical statement of what happened. Never interpretive. */
  title: string;
  body: string;
  /** Optional recovery affordance, rendered before the navigation links. */
  action?: { label: string; onClick: () => void };
  testId: string;
}

/**
 * The shared body for every error surface (404, route error, root error).
 *
 * Copy discipline lives at the call sites, but two rules are structural here:
 *
 *  * Every surface offers a real way forward. A 404 that only says "not
 *    found" wastes the single interaction you get with someone who mistyped
 *    the URL, so both links are part of the component rather than something
 *    each page remembers to add.
 *  * Nothing about the underlying error is rendered. No message, no stack,
 *    no digest -- this component has no prop that could carry one. The
 *    display-side corollary applies to failures too: these pages state what
 *    happened mechanically and interpret nothing.
 */
export function ErrorSurface({ title, body, action, testId }: ErrorSurfaceProps) {
  return (
    <div
      data-testid={testId}
      className={`mx-auto w-full max-w-2xl space-y-6 p-6 pt-16 ${MOTION.enter}`}
    >
      <h1 className="text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
      <p className="max-w-prose text-muted-foreground">{body}</p>

      <div className="flex flex-wrap items-center gap-3 pt-2">
        {action ? (
          <button
            type="button"
            data-testid={`${testId}-retry`}
            onClick={action.onClick}
            className={`inline-flex min-h-11 items-center rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground ${MOTION.interactive} hover:opacity-90 active:opacity-80`}
          >
            {action.label}
          </button>
        ) : null}
        <Link
          href="/backtest"
          data-testid={`${testId}-backtest-link`}
          className={`inline-flex min-h-11 items-center rounded-md border border-border bg-card px-5 text-sm font-medium text-foreground ${MOTION.interactive} hover:border-foreground/40 hover:bg-muted`}
        >
          Backtest a strategy
        </Link>
        <Link
          href="/"
          data-testid={`${testId}-home-link`}
          className={`text-sm font-medium text-foreground underline underline-offset-4 ${MOTION.interactive} hover:opacity-80`}
        >
          Back to the home page
        </Link>
      </div>
    </div>
  );
}
