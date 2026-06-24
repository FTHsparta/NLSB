import type { Verdict } from "@/lib/robustness/types";

const VERDICT_COPY: Record<Verdict, { label: string; accent: string }> = {
  PASS: { label: "Pass", accent: "border-emerald-500" },
  SHAKY: { label: "Shaky", accent: "border-amber-500" },
  LIKELY_OVERFIT: { label: "Likely overfit", accent: "border-red-500" },
  // Deliberately the SAME structure/prominence as the other three -- an
  // honest "we can't tell you" is the point of this project, not a
  // second-class result. No grey-out, no spinner, no footnote treatment.
  UNTESTABLE: { label: "Untestable", accent: "border-slate-500" },
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
 * rendered here.
 */
export function VerdictCard({ verdict, reasons }: VerdictCardProps) {
  const copy = VERDICT_COPY[verdict];
  return (
    <section
      data-testid="verdict-card"
      data-verdict={verdict}
      className={`rounded-lg border-2 ${copy.accent} bg-white p-6 dark:bg-zinc-900`}
    >
      <p className="text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Verdict
      </p>
      <h2 data-testid="verdict-label" className="mt-1 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">
        {copy.label}
      </h2>
      <ul data-testid="verdict-reasons" className="mt-4 space-y-2 text-zinc-700 dark:text-zinc-300">
        {reasons.map((reason, i) => (
          <li key={i} data-testid="verdict-reason">
            {reason}
          </li>
        ))}
      </ul>
    </section>
  );
}
