/**
 * `renderer.py`'s `render_confirmation` returns one joined string with a
 * fixed section order: strategy prose, then "You specified:", then
 * (optionally) the "⚠ Heads up" warning block, then "I assumed (...)".
 * The headers below are literal constants from that module, not user- or
 * model-influenced text -- slicing on them is a structural split of
 * backend-authored output, not a rewording or synthesis of it. The
 * "I assumed"/"Heads up" prose itself is NOT re-derived here: the
 * structured `assumptions` array (with its own `severity` field) is the
 * source of truth for rendering those two sections; this function only
 * recovers the "strategy" and "You specified" text, which the backend
 * doesn't expose as structured data.
 */

const YOU_SPECIFIED_HEADER = "You specified:";
const HEADS_UP_HEADER = "⚠ Heads up";
const I_ASSUMED_HEADER = "I assumed (you didn't specify these):";

export interface RestatementSections {
  /** The plain-English strategy description, before "You specified:". */
  strategy: string;
  /** Verbatim text of the "You specified" list, header excluded. */
  youSpecified: string;
}

export function parseRestatementSections(restatement: string): RestatementSections {
  const specifiedIdx = restatement.indexOf(YOU_SPECIFIED_HEADER);
  if (specifiedIdx === -1) {
    return { strategy: restatement.trim(), youSpecified: "" };
  }

  const strategy = restatement.slice(0, specifiedIdx).trim();

  const afterHeader = specifiedIdx + YOU_SPECIFIED_HEADER.length;
  const headsUpIdx = restatement.indexOf(HEADS_UP_HEADER, afterHeader);
  const assumedIdx = restatement.indexOf(I_ASSUMED_HEADER, afterHeader);
  const candidates = [headsUpIdx, assumedIdx].filter((i) => i !== -1);
  const endIdx = candidates.length > 0 ? Math.min(...candidates) : restatement.length;

  const youSpecified = restatement.slice(afterHeader, endIdx).trim();

  return { strategy, youSpecified };
}
