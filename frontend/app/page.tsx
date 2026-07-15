import Link from "next/link";

import { backtestHref, EXAMPLE_STRATEGIES } from "@/lib/examples";
import { MOTION, staggerDelay } from "@/lib/motion";

/**
 * The landing page (Phase 11): monochrome, spare, on-voice. Pure frontend
 * chrome — it makes claims about what the PRODUCT does, never about any
 * strategy. The four verdict names appear here in plain foreground type
 * only: verdict color exists solely on the real verdict card (INV-2), and
 * a marketing strip has not earned it.
 */

const WHAT_IT_DOES: { title: string; body: string }[] = [
  {
    title: "Plain English in",
    body: "Describe the strategy the way you'd say it aloud. It becomes exact, inspectable rules — never code you have to trust blindly.",
  },
  {
    title: "Every assumption surfaced",
    body: "Before anything runs, you see what you stated and what was assumed on your behalf — and you can correct either.",
  },
  {
    title: "Judged for robustness",
    body: "Walk-forward, parameter sensitivity, deflated Sharpe, regime breakdown — then a verdict in plain language, not a flattering curve.",
  },
];

/** Compact strip only — the full explanations live on /methodology. */
const VERDICT_STRIP: { title: string; line: string }[] = [
  { title: "PASS", line: "The edge survived every check. Encouraging — not a guarantee." },
  { title: "SHAKY", line: "There's a signal, but at least one check flagged fragility." },
  { title: "LIKELY OVERFIT", line: "A good-looking curve that probably won't repeat." },
  { title: "UNTESTABLE", line: "Too little evidence to judge — and we say so instead of guessing." },
];

export default function LandingPage() {
  return (
    <div data-testid="landing-page" className="mx-auto w-full max-w-3xl space-y-20 px-6 pb-20 pt-16">
      {/* Hero */}
      <section className={`space-y-6 ${MOTION.enterSlide}`}>
        <h1 className="max-w-[26ch] text-4xl font-semibold leading-tight tracking-tight text-foreground">
          The backtester that tells you when your strategy is fooling you.
        </h1>
        <p className="max-w-prose text-lg text-muted-foreground">
          Plain English in, an honest verdict out — built to surface what other
          backtesters hide.
        </p>
        <Link
          href="/backtest"
          data-testid="landing-cta"
          className={`inline-block rounded-md bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground ${MOTION.interactive} hover:opacity-90 active:opacity-80`}
        >
          Backtest a strategy
        </Link>
      </section>

      {/* What it does */}
      <section aria-label="What it does" className="grid gap-6 sm:grid-cols-3">
        {WHAT_IT_DOES.map((item, i) => (
          <div
            key={item.title}
            data-testid="landing-what-item"
            className={`rounded-lg border border-border bg-card p-5 ${MOTION.enterSlide}`}
            style={staggerDelay(i)}
          >
            <h2 className="text-sm font-semibold text-foreground">{item.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{item.body}</p>
          </div>
        ))}
      </section>

      {/* How the verdict works — names only, no verdict color (INV-2) */}
      <section aria-label="How the verdict works" className="space-y-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Every run ends in one of four verdicts
        </h2>
        <div data-testid="landing-verdicts" className="divide-y divide-border rounded-lg border border-border">
          {VERDICT_STRIP.map((v) => (
            <div key={v.title} className="flex flex-col gap-1 p-4 sm:flex-row sm:items-baseline sm:gap-4">
              <span className="w-40 shrink-0 text-sm font-semibold tracking-wide text-foreground">{v.title}</span>
              <span className="text-sm text-muted-foreground">{v.line}</span>
            </div>
          ))}
        </div>
        <p className="text-sm text-muted-foreground">
          <Link
            href="/methodology"
            data-testid="landing-methodology-link"
            className="font-medium text-foreground underline underline-offset-4 hover:opacity-80"
          >
            How the checks work
          </Link>
        </p>
      </section>

      {/* Example chips — land on /backtest with the example prefilled */}
      <section aria-label="Try an example" className="space-y-3">
        <h2 className="text-sm text-muted-foreground">Or start from an example:</h2>
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_STRATEGIES.map((example) => (
            <Link
              key={example.label}
              href={backtestHref(example.text)}
              data-testid="landing-example-chip"
              className={`rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground ${MOTION.interactive} hover:border-foreground/40 hover:bg-muted`}
            >
              {example.label}
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
