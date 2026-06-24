/**
 * Mirrors `backend/app/main.py`'s pydantic payload shapes verbatim --
 * snake_case field names kept exactly as the backend serializes them, same
 * convention `lib/robustness/types.ts` established in Phase 5a. This file
 * describes the contract; it computes nothing.
 */

export type AssumptionSeverity = "note" | "warning";

export interface Assumption {
  field: string;
  value: unknown;
  reason: string;
  severity: AssumptionSeverity;
}

export interface TranslationPayload {
  status: "ok" | "unsupported" | "error";
  ir: Record<string, unknown> | null;
  assumptions: Assumption[];
  restatement: string | null;
  message: string | null;
  retries: number;
}
