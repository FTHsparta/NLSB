import Link from "next/link";

import { MOTION } from "@/lib/motion";

/**
 * Slim top nav (Phase 11 site chrome). Monochrome by the same rule as
 * everything outside VerdictCard: the wordmark is plain type, links are
 * two-tier gray-to-white on hover. Deliberately a server component with no
 * active-route state -- the pages are few and self-evident, and keeping it
 * static means no client router hooks for tests to mock.
 */
export function SiteNav() {
  return (
    <header data-testid="site-nav" className="border-b border-border">
      <nav className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
        <Link
          href="/"
          data-testid="site-nav-wordmark"
          className={`text-sm font-semibold tracking-widest text-foreground ${MOTION.interactive} hover:opacity-80`}
        >
          NLSB
        </Link>
        <div className="flex items-center gap-6">
          <Link
            href="/backtest"
            data-testid="site-nav-backtest"
            className={`text-sm text-muted-foreground ${MOTION.interactive} hover:text-foreground`}
          >
            Backtest
          </Link>
          <Link
            href="/methodology"
            data-testid="site-nav-methodology"
            className={`text-sm text-muted-foreground ${MOTION.interactive} hover:text-foreground`}
          >
            Methodology
          </Link>
        </div>
      </nav>
    </header>
  );
}
