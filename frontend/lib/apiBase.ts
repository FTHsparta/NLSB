/**
 * Single source of truth for where the backend lives.
 *
 * Unset (local dev): returns "" so callers keep posting relative paths
 * (`/translate`, ...) and `next.config.ts`'s rewrites proxy them to the
 * FastAPI dev server -- the pre-Phase-10 behavior, unchanged.
 *
 * Set (deployed, e.g. `NEXT_PUBLIC_API_BASE_URL=https://api.example.com`):
 * requests go straight to the backend origin, which must then allow this
 * frontend's origin via its `ALLOWED_ORIGINS` CORS config.
 *
 * NOTE: `process.env.NEXT_PUBLIC_API_BASE_URL` must stay written out
 * literally -- Next.js inlines NEXT_PUBLIC_* vars into the browser bundle
 * by textual substitution of that exact expression at build time.
 */

export function apiBaseUrl(
  raw: string | undefined = process.env.NEXT_PUBLIC_API_BASE_URL
): string {
  if (!raw) return "";
  // Strip trailing slashes so `${base}/translate` never doubles the "/".
  return raw.replace(/\/+$/, "");
}

export function apiUrl(path: string, base: string = apiBaseUrl()): string {
  return `${base}${path}`;
}
