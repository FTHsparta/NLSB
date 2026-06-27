import type { Verdict } from "@/lib/robustness/types";

/**
 * The ONLY saturated color on the entire screen, and the ONLY place these
 * four tokens (`--verdict-*`, defined in `app/globals.css`) are referenced
 * anywhere in the codebase -- see `tests/visual/color-invariants.test.tsx`.
 * Selected by a static lookup keyed on the backend's verdict enum string;
 * there is no numeric comparison anywhere in this file. UNTESTABLE gets
 * its own neutral token, not a reused PASS/SHAKY/LIKELY_OVERFIT hue -- "we
 * can't tell you, honestly" hasn't earned a judgment color.
 */
interface VerdictCopy {
  label: string;
  /** Full literal Tailwind class strings, not interpolated at render time
   * -- Tailwind's compiler only generates utilities it can find as a
   * complete string in source, so `border-l-${accent}` would silently
   * produce no CSS at all. Keeping each verdict's classes fully spelled
   * out here is also a stronger form of the same static-lookup
   * discipline: there is nothing for any code path to compute. */
  borderClass: string;
  tintClass: string;
  textClass: string;
}

const VERDICT_COPY: Record<Verdict, VerdictCopy> = {
  PASS: { label: "Pass", borderClass: "border-l-verdict-pass", tintClass: "bg-verdict-pass/10", textClass: "text-verdict-pass" },
  SHAKY: { label: "Shaky", borderClass: "border-l-verdict-shaky", tintClass: "bg-verdict-shaky/10", textClass: "text-verdict-shaky" },
  LIKELY_OVERFIT: {
    label: "Likely overfit",
    borderClass: "border-l-verdict-overfit",
    tintClass: "bg-verdict-overfit/10",
    textClass: "text-verdict-overfit",
  },
  // Deliberately the SAME structure/prominence as the other three -- an
  // honest "we can't tell you" is the point of this project, not a
  // second-class result. No grey-out, no spinner, no footnote treatment.
  UNTESTABLE: {
    label: "Untestable",
    borderClass: "border-l-verdict-untestable",
    tintClass: "bg-verdict-untestable/10",
    textClass: "text-verdict-untestable",
  },
};

export interface VerdictCardProps {
  verdict: Verdict;
  reasons: string[];
}

/**
 * The headline. Always rendered before any raw Sharpe/return figure
 * (enforced by render order in `RobustnessResultView`, not by anything in
 * this component) -- this is the ONE place in the UI that states a verdict
 * word; everything below it is supporting detail for a verdict already
 * rendered here. It is also the largest, most prominent element in the
 * results view, and the only one carrying color -- the visual system's
 * version of the same discipline the component tree already enforces.
 */
export function VerdictCard({ verdict, reasons }: VerdictCardProps) {
  const copy = VERDICT_COPY[verdict];
  return (
    <section
      data-testid="verdict-card"
      data-verdict={verdict}
      className={`rounded-lg border border-border bg-card border-l-4 p-6 ${copy.borderClass} ${copy.tintClass}`}
    >
      <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">Verdict</p>
      <h2 data-testid="verdict-label" className={`mt-1 text-3xl font-semibold ${copy.textClass}`}>
        {copy.label}
      </h2>
      <ul data-testid="verdict-reasons" className="mt-4 space-y-2 text-foreground">
        {reasons.map((reason, i) => (
          <li key={i} data-testid="verdict-reason">
            {reason}
          </li>
        ))}
      </ul>
    </section>
  );
}
