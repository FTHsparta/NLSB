"use client"; // Error boundaries must be Client Components.

import { useEffect } from "react";

import { ErrorSurface } from "@/components/chrome/ErrorSurface";

/**
 * Route-segment error boundary.
 *
 * The recovery prop is `unstable_retry`, NOT `reset` -- this Next version
 * (16.2.9) added `unstable_retry` in 16.2.0 and its own docs say to prefer
 * it: retry re-fetches and re-renders the boundary's children, where `reset`
 * only clears the error state and re-renders without re-fetching. Since a
 * failure here is most often a failed fetch, re-rendering the same stale
 * tree would just fail again. `reset` is accepted as a fallback so the
 * button keeps working if the unstable prop is renamed.
 *
 * The error object is logged, never rendered. No message, no stack, no
 * digest reaches the user -- `ErrorSurface` has no prop that could carry one.
 */
export default function RouteError({
  error,
  unstable_retry,
  reset,
}: {
  error: Error & { digest?: string };
  unstable_retry?: () => void;
  reset?: () => void;
}) {
  useEffect(() => {
    // Goes to the browser console and, in production, to Vercel's logs --
    // somewhere the platform can see it and the user cannot.
    console.error(error);
  }, [error]);

  const retry = unstable_retry ?? reset;

  return (
    <ErrorSurface
      testId="route-error-page"
      title="Something went wrong on this page"
      body="The page failed to load. Trying again often works; if it doesn't, the two links below still do."
      action={retry ? { label: "Try again", onClick: retry } : undefined}
    />
  );
}
