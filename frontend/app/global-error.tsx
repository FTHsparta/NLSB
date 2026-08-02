"use client"; // Error boundaries must be Client Components.

import { useEffect } from "react";

import "./globals.css";

/**
 * Last resort: this replaces the ROOT LAYOUT when the layout itself throws,
 * so none of the usual chrome exists here. Per this Next version's docs,
 * global error UI must supply its own <html> and <body> and its own global
 * styles, and cannot export `metadata` (error boundaries are Client
 * Components) -- the React <title> element is the documented alternative.
 *
 * Deliberately dependency-free beyond the stylesheet: `SiteShell`, the fonts,
 * and `ErrorSurface` are all things that could be implicated in a root-layout
 * crash, and a fallback that imports the thing that just broke is not a
 * fallback. The markup here is plain and self-contained on purpose.
 *
 * Same copy discipline as the other surfaces, and the same hard rule: the
 * error is logged, never rendered.
 */
export default function GlobalError({
  error,
  unstable_retry,
  reset,
}: {
  error: Error & { digest?: string };
  unstable_retry?: () => void;
  reset?: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  const retry = unstable_retry ?? reset;

  return (
    <html lang="en" className="dark h-full">
      <body className="min-h-full bg-background text-foreground antialiased">
        <title>Something went wrong — Deflate</title>
        <div data-testid="global-error-page" className="mx-auto w-full max-w-2xl space-y-6 p-6 pt-16">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            Something went wrong
          </h1>
          <p className="max-w-prose text-muted-foreground">
            Deflate failed to load. Trying again often works; if it doesn&apos;t, reloading the
            home page will.
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            {retry ? (
              <button
                type="button"
                data-testid="global-error-page-retry"
                onClick={retry}
                className="inline-flex min-h-11 items-center rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground hover:opacity-90"
              >
                Try again
              </button>
            ) : null}
            {/* Plain anchors, not next/link, and the lint rule is suppressed
                deliberately rather than worked around: this boundary replaces
                the ROOT LAYOUT, so the router is part of what may have failed.
                A client-side navigation here could fail exactly as the render
                just did; a full document load is the recovery. */}
            <a
              href="/backtest"
              data-testid="global-error-page-backtest-link"
              className="inline-flex min-h-11 items-center rounded-md border border-border bg-card px-5 text-sm font-medium text-foreground hover:border-foreground/40 hover:bg-muted"
            >
              Backtest a strategy
            </a>
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a
              href="/"
              data-testid="global-error-page-home-link"
              className="text-sm font-medium text-foreground underline underline-offset-4 hover:opacity-80"
            >
              Back to the home page
            </a>
          </div>
        </div>
      </body>
    </html>
  );
}
