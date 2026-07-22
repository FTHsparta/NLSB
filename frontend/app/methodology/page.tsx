import type { Metadata } from "next";
import Link from "next/link";

import {
  GLOSSARY_TERMS,
  HOW_INTRO,
  LIMITATIONS,
  LIMITATIONS_LEAD,
} from "@/components/chrome/howDeflateWorksContent";
import {
  CHECK_EXPLANATIONS,
  OVERFIT_EXPLANATION,
  VERDICT_EXPLANATIONS,
} from "@/components/chrome/methodologyContent";
import { MOTION } from "@/lib/motion";

export const metadata: Metadata = {
  title: "Methodology — Deflate",
  description:
    "How Deflate judges a strategy: the four checks, the four verdicts, key terms, and what Deflate deliberately does not model.",
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
        <p data-testid="methodology-intro" className="max-w-prose text-muted-foreground">
          {HOW_INTRO}
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

      <section data-testid="methodology-glossary" className="space-y-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Key terms
        </h2>
        <dl className="space-y-5">
          {GLOSSARY_TERMS.map((t) => (
            <div key={t.term} data-testid="glossary-term" className="border-l-2 border-border pl-4">
              <dt className="font-semibold text-foreground">{t.term}</dt>
              <dd className="mt-1 text-sm leading-relaxed text-muted-foreground">{t.body}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* `id` is a stable deep-link target: the results view's inline
          pointer links to /methodology#limitations. Rename in both places
          or not at all. */}
      <section id="limitations" data-testid="methodology-limitations" className="space-y-5 scroll-mt-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          What Deflate does not do
        </h2>
        <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">{LIMITATIONS_LEAD}</p>
        <dl className="space-y-5">
          {LIMITATIONS.map((l) => (
            <div key={l.title} data-testid="limitation-item" className="rounded-lg border border-border bg-card p-5">
              <dt className="font-semibold text-foreground">{l.title}</dt>
              <dd className="mt-1 text-sm leading-relaxed text-muted-foreground">{l.body}</dd>
            </div>
          ))}
        </dl>
      </section>

      <div className="border-t border-border pt-8">
        <Link
          href="/backtest"
          data-testid="methodology-cta"
          className={`inline-flex min-h-11 items-center rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground sm:min-h-0 ${MOTION.interactive} hover:opacity-90 active:opacity-80`}
        >
          Backtest a strategy
        </Link>
      </div>
    </div>
  );
}
