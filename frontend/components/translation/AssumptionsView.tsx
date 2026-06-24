import type { Assumption } from "@/lib/translation/types";
import { parseRestatementSections } from "@/lib/translation/restatementSections";

export interface AssumptionsViewProps {
  restatement: string;
  assumptions: Assumption[];
}

function formatAssumptionValue(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * Renders `renderer.py`'s output as two visually distinct sections --
 * "You specified" and "I assumed" -- per the display-side corollary: every
 * piece of text here is the backend's own string, displayed verbatim
 * (`strategy`/`youSpecified` are structural slices of the restatement,
 * `reason` text below is the literal `Assumption.reason` field). Nothing in
 * this component synthesizes or rewords backend prose.
 *
 * Severity drives a STRUCTURALLY different render path, not just a style
 * tweak: a warning-severity assumption renders via `WarningAssumption`
 * (its own element, `role="alert"`, distinct testid) -- it can never be
 * mistaken for one of the plain `<li>` rows in the ordinary notes list.
 */
export function AssumptionsView({ restatement, assumptions }: AssumptionsViewProps) {
  const { strategy, youSpecified } = parseRestatementSections(restatement);
  const warnings = assumptions.filter((a) => a.severity === "warning");
  const notes = assumptions.filter((a) => a.severity !== "warning");

  return (
    <div data-testid="assumptions-view" className="space-y-6 text-sm">
      <section data-testid="strategy-summary">
        <pre className="whitespace-pre-wrap font-sans text-zinc-800 dark:text-zinc-200">{strategy}</pre>
      </section>

      <section data-testid="you-specified-section">
        <h3 className="font-medium text-zinc-700 dark:text-zinc-300">You specified</h3>
        <pre className="mt-2 whitespace-pre-wrap font-sans text-zinc-600 dark:text-zinc-400">{youSpecified}</pre>
      </section>

      {warnings.length > 0 && (
        <section data-testid="warning-assumptions-section">
          {warnings.map((a, i) => (
            <WarningAssumption key={i} assumption={a} />
          ))}
        </section>
      )}

      <section data-testid="note-assumptions-section">
        <h3 className="font-medium text-zinc-700 dark:text-zinc-300">I assumed</h3>
        {notes.length === 0 ? (
          <p className="mt-2 text-zinc-500 dark:text-zinc-500">(nothing routine left to assume)</p>
        ) : (
          <ul className="mt-2 space-y-1 text-zinc-600 dark:text-zinc-400">
            {notes.map((a, i) => (
              <li key={i} data-testid="assumption-note">
                <span className="font-medium">{a.field}</span>: {formatAssumptionValue(a.value)} &mdash;{" "}
                {a.reason}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function WarningAssumption({ assumption }: { assumption: Assumption }) {
  return (
    <div
      role="alert"
      data-testid="assumption-warning"
      className="rounded-md border-2 border-amber-500 bg-amber-50 p-4 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
    >
      <p className="font-semibold uppercase tracking-wide text-xs">Heads up &mdash; this changes what the result means</p>
      <p className="mt-1" data-testid="assumption-warning-reason">
        {assumption.reason}
      </p>
    </div>
  );
}
