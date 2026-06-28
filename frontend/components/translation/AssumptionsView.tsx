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
        <pre className="whitespace-pre-wrap font-sans text-foreground">{strategy}</pre>
      </section>

      <section data-testid="you-specified-section">
        <h3 className="font-medium text-foreground">You specified</h3>
        <pre className="mt-2 whitespace-pre-wrap font-sans text-muted-foreground">{youSpecified}</pre>
      </section>

      {warnings.length > 0 && (
        <section data-testid="warning-assumptions-section">
          {warnings.map((a, i) => (
            <WarningAssumption key={i} assumption={a} />
          ))}
        </section>
      )}

      <section data-testid="note-assumptions-section">
        <h3 className="font-medium text-foreground">I assumed</h3>
        {notes.length === 0 ? (
          <p className="mt-2 text-muted-foreground">(nothing routine left to assume)</p>
        ) : (
          <ul className="mt-2 space-y-1 text-muted-foreground">
            {notes.map((a, i) => (
              <li key={i} data-testid="assumption-note">
                <span className="font-medium text-foreground">{a.field}</span>: {formatAssumptionValue(a.value)}{" "}
                &mdash; {a.reason}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/**
 * Distinct from an ordinary note row by PROMINENCE (a heavier border, a
 * filled background, near-white text) rather than by color -- per this
 * phase's strict palette rule, even a backend-flagged severity doesn't
 * get a saturated hue. `role="alert"` and its own testid (asserted by
 * Phase 5b/6's contract tests) still make it structurally unmistakable.
 */
function WarningAssumption({ assumption }: { assumption: Assumption }) {
  return (
    <div
      role="alert"
      data-testid="assumption-warning"
      className="rounded-lg border-l-4 border-foreground bg-muted p-6 text-foreground"
    >
      <p className="text-base font-bold uppercase tracking-wide text-foreground">
        Heads up &mdash; this changes what the result means
      </p>
      <p className="mt-2 text-base font-medium text-foreground" data-testid="assumption-warning-reason">
        {assumption.reason}
      </p>
    </div>
  );
}
