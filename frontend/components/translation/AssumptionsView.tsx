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
 * The backend's "You specified" text is a newline-joined bullet list
 * (`renderer.py`'s `_stated_summary`, one `"- item"` line per stated
 * field) -- splitting it into rows is a structural unpacking of THAT
 * existing list, not a re-categorization: every line here was already
 * inside the backend's "You specified" block before this function ran.
 */
function splitBulletLines(block: string): string[] {
  return block
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => line.slice(2));
}

/**
 * Renders `renderer.py`'s output as two structurally distinct, clearly
 * separated sections -- "You specified" and "I assumed" -- per the
 * display-side corollary: every piece of text here is the backend's own
 * string, displayed verbatim (`strategy`/the stated rows are a structural
 * unpacking of the restatement; `reason` text below is the literal
 * `Assumption.reason` field). Nothing in this component synthesizes,
 * rewords, or re-buckets backend prose -- which bucket an item is in was
 * decided entirely by `renderer.py`/`apply_defaults`, never here.
 *
 * Severity drives a STRUCTURALLY different render path, not just a style
 * tweak: a warning-severity assumption renders via `WarningAssumption`
 * (its own element, `role="alert"`, distinct testid), elevated WITHIN "I
 * assumed" -- it is an assumption, the most important one, so it stays
 * inside that section rather than floating outside the stated/assumed
 * structure -- but it can never be mistaken for one of the plain `<li>`
 * rows in the ordinary notes list.
 */
export function AssumptionsView({ restatement, assumptions }: AssumptionsViewProps) {
  const { strategy, youSpecified } = parseRestatementSections(restatement);
  const statedItems = splitBulletLines(youSpecified);
  const warnings = assumptions.filter((a) => a.severity === "warning");
  const notes = assumptions.filter((a) => a.severity !== "warning");
  const nothingAssumed = warnings.length === 0 && notes.length === 0;

  return (
    <div data-testid="assumptions-view" className="space-y-8 text-sm">
      <section data-testid="strategy-summary">
        <pre className="whitespace-pre-wrap font-sans text-foreground">{strategy}</pre>
      </section>

      <section data-testid="you-specified-section" className="space-y-3">
        <SectionHeading title="You specified" description="What you stated, reflected back." />
        {statedItems.length === 0 ? (
          <p className="text-muted-foreground">Nothing beyond the basic strategy structure.</p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {statedItems.map((item, i) => (
              <li key={i} className="px-4 py-2.5 text-foreground">
                {item}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div role="separator" aria-hidden="true" className="border-t border-border" />

      <section data-testid="note-assumptions-section" className="space-y-3">
        <SectionHeading
          title="I assumed"
          description="Defaults the system invented to fill the gaps you left."
        />

        {nothingAssumed ? (
          <p className="text-muted-foreground">No assumptions needed &mdash; you specified everything.</p>
        ) : (
          <div className="space-y-4">
            {warnings.map((a, i) => (
              <WarningAssumption key={`warning-${i}`} assumption={a} />
            ))}

            {notes.length > 0 && (
              <ul className="divide-y divide-border rounded-lg border border-border text-muted-foreground">
                {notes.map((a, i) => (
                  <li key={i} data-testid="assumption-note" className="px-4 py-2.5">
                    <span className="font-medium text-foreground">{a.field}</span>: {formatAssumptionValue(a.value)}{" "}
                    &mdash; {a.reason}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="space-y-1">
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      <p className="text-sm text-muted-foreground">{description}</p>
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
