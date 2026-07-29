import type { RealizedWindow } from "@/lib/robustness/types";
import { formatDateOrNA } from "@/lib/robustness/format";

export interface TestedWindowProps {
  window: RealizedWindow | null | undefined;
}

/**
 * States which data produced the result, on every result.
 *
 * Deliberately NOT conditional on anything being wrong: a correct run reports
 * its window too, because a reader should not have to suspect a problem
 * before being told what was judged.
 *
 * Display-side corollary, strictly: this renders backend-emitted values and
 * formats them for presentation. It derives NO judgment — no "short window"
 * warning, no comparison verdict between requested and realized, no styling
 * that varies with the values. If evaluative copy is ever wanted here, the
 * backend emits the string and this component prints it.
 *
 * Renders nothing at all for a payload with no window (an older backend, a
 * clipped body) rather than inventing one — the same defensive posture as
 * `RobustnessResultView`'s shape check.
 */
export function TestedWindow({ window }: TestedWindowProps) {
  if (!window || typeof window !== "object") return null;

  const { realized_start, realized_end, bar_count } = window;
  if (!realized_start || !realized_end) return null;

  const bars = Number.isFinite(bar_count) ? bar_count : null;

  return (
    <p data-testid="tested-window" className="mt-4 text-sm text-muted-foreground">
      Tested on{" "}
      <span data-testid="tested-window-range" className="text-foreground">
        {formatDateOrNA(realized_start)} to {formatDateOrNA(realized_end)}
      </span>
      {bars !== null ? (
        <>
          {" "}
          — <span data-testid="tested-window-bars">{bars.toLocaleString("en-US")}</span> daily bars
        </>
      ) : null}
      .
    </p>
  );
}
