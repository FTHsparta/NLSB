"use client";

import Link from "next/link";

import { EVENTS, trackEvent } from "@/lib/analytics";
import { backtestHref, EXAMPLE_STRATEGIES } from "@/lib/examples";
import { MOTION } from "@/lib/motion";

/**
 * The landing page's example chips, extracted from `app/page.tsx` into a
 * client boundary ONLY so the click can be instrumented. The markup and
 * classes are unchanged; the page stays a Server Component.
 *
 * The event carries the chip's INDEX and label from the fixed
 * `EXAMPLE_STRATEGIES` list -- both bounded, low-cardinality values from a
 * four-item constant. It never carries `example.text`, which is the strategy
 * description itself.
 *
 * Tracking is fire-and-forget and sits beside navigation, never in front of
 * it: `trackEvent` cannot throw, and the <Link> is not conditional on it, so
 * a tracking failure can never swallow a click.
 */
export function ExampleChips() {
  return (
    <div className="flex flex-wrap gap-2">
      {EXAMPLE_STRATEGIES.map((example, index) => (
        <Link
          key={example.label}
          href={backtestHref(example.text)}
          data-testid="landing-example-chip"
          onClick={() => trackEvent(EVENTS.exampleClicked, { index, label: example.label })}
          className={`inline-flex min-h-11 items-center rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground sm:min-h-0 sm:px-3 sm:py-1.5 sm:text-xs ${MOTION.interactive} hover:border-foreground/40 hover:bg-muted`}
        >
          {example.label}
        </Link>
      ))}
    </div>
  );
}
