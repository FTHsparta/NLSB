import type { Metadata } from "next";

import { ErrorSurface } from "@/components/chrome/ErrorSurface";

export const metadata: Metadata = {
  title: "Page not found — Deflate",
  // A 404 is not content; keeping it out of the index costs nothing and
  // stops a mistyped URL from ever becoming a search result.
  robots: { index: false, follow: true },
};

/**
 * Replaces Next's stock /_not-found default, which rendered unstyled
 * framework copy on a site whose every other surface is deliberately voiced.
 */
export default function NotFound() {
  return (
    <ErrorSurface
      testId="not-found-page"
      title="That page doesn't exist"
      body="The link may be out of date, or the address may have a typo. Everything Deflate does lives on the two pages below."
    />
  );
}
