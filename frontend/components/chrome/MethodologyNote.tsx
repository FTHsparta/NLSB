import Link from "next/link";

import {
  CHECK_EXPLANATIONS,
  OVERFIT_EXPLANATION,
  VERDICT_EXPLANATIONS,
} from "./methodologyContent";

/**
 * "How to read a verdict" — educational chrome (Phase 9), reachable from the
 * results surface as an expandable panel. Content lives in
 * `methodologyContent.ts`, shared verbatim with the /methodology route
 * (Phase 11); this component stays the compact in-flow rendering and links
 * to the full page. It explains the checks GENERICALLY: it never restates
 * or interprets a specific strategy's numbers (that would cross the
 * display-side corollary). Two-tier type, monochrome.
 */
export function MethodologyNote() {
  return (
    <details data-testid="methodology-note" className="mt-6 rounded-lg border border-border bg-card p-4">
      <summary
        data-testid="methodology-summary"
        className="cursor-pointer select-none py-2 text-sm font-semibold text-foreground sm:py-0"
      >
        How to read a verdict
      </summary>

      <div className="mt-4 space-y-6 text-sm">
        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">What each verdict means</h3>
          <dl className="space-y-3">
            {VERDICT_EXPLANATIONS.map((v) => (
              <div key={v.key}>
                <dt data-testid={`methodology-heading-${v.key}`} className="font-semibold text-foreground">
                  {v.title}
                </dt>
                <dd className="text-muted-foreground">{v.body}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">What each check asks</h3>
          <dl className="space-y-3">
            {CHECK_EXPLANATIONS.map((c) => (
              <div key={c.title}>
                <dt className="font-semibold text-foreground">{c.title}</dt>
                <dd className="text-muted-foreground">{c.body}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Why a great-looking curve can still be overfit
          </h3>
          <p className="text-muted-foreground">{OVERFIT_EXPLANATION}</p>
        </section>

        <p>
          <Link
            href="/methodology"
            data-testid="methodology-page-link"
            className="font-medium text-foreground underline underline-offset-4 hover:opacity-80"
          >
            Read the full methodology
          </Link>
        </p>
      </div>
    </details>
  );
}
