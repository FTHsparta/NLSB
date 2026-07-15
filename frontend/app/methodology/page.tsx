import type { Metadata } from "next";
import Link from "next/link";

import {
  CHECK_EXPLANATIONS,
  OVERFIT_EXPLANATION,
  VERDICT_EXPLANATIONS,
} from "@/components/chrome/methodologyContent";
import { MOTION } from "@/lib/motion";

export const metadata: Metadata = {
  title: "Methodology — NLSB",
  description: "How NLSB judges a strategy: the four checks, the four verdicts, and why.",
};

/**
 * Methodology as a first-class route (Phase 11). Renders the SAME shared
 * content module as the in-flow MethodologyNote — page-level layout, no new
 * claims, no numbers, no judgment about any specific strategy. Verdict
 * names appear in plain foreground type: verdict COLOR exists only on the
 * real verdict card (INV-2).
 */
export default function MethodologyPage() {
  return (
    <div data-testid="methodology-page" className={`mx-auto w-full max-w-2xl space-y-12 p-6 pt-10 ${MOTION.enter}`}>
      <header className="space-y-3 border-b border-border pb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">Methodology</h1>
        <p className="max-w-prose text-muted-foreground">
          A single backtest number is easy to like and easy to be fooled by. NLSB runs
          every strategy through the same four checks and reports a verdict in plain
          language — here is exactly what each check asks and what each verdict means.
        </p>
      </header>

      <section className="space-y-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          What each check asks
        </h2>
        <dl className="space-y-5">
          {CHECK_EXPLANATIONS.map((c) => (
            <div key={c.title} className="rounded-lg border border-border bg-card p-5">
              <dt className="font-semibold text-foreground">{c.title}</dt>
              <dd className="mt-1 text-sm leading-relaxed text-muted-foreground">{c.body}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="space-y-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          What each verdict means
        </h2>
        <dl className="space-y-5">
          {VERDICT_EXPLANATIONS.map((v) => (
            <div key={v.key} className="border-l-2 border-border pl-4">
              <dt data-testid={`methodology-page-heading-${v.key}`} className="font-semibold text-foreground">
                {v.title}
              </dt>
              <dd className="mt-1 text-sm leading-relaxed text-muted-foreground">{v.body}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Why a great-looking curve can still be overfit
        </h2>
        <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">{OVERFIT_EXPLANATION}</p>
      </section>

      <div className="border-t border-border pt-8">
        <Link
          href="/backtest"
          data-testid="methodology-cta"
          className={`inline-block rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground ${MOTION.interactive} hover:opacity-90 active:opacity-80`}
        >
          Backtest a strategy
        </Link>
      </div>
    </div>
  );
}
