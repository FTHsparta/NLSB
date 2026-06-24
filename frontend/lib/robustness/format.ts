/**
 * Display formatting only -- every function here takes a value the backend
 * already computed and returns a string. None of them branch on a
 * threshold, combine multiple fields, or otherwise re-derive anything
 * `verdict.py` is responsible for. If a number is missing/non-finite
 * (`null`/`NaN`), that is itself information ("not enough data to compute
 * this") and is rendered as "N/A", never silently coerced to 0.
 */

export function formatNumberOrNA(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  return value.toFixed(digits);
}

export function formatPercentOrNA(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDateOrNA(value: string | null | undefined): string {
  return value ?? "N/A";
}
