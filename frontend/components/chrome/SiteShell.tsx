import { DisclaimerFooter } from "./Disclaimer";
import { SiteNav } from "./SiteNav";

/**
 * The shared chrome around every route (Phase 11): nav on top, the
 * permanent disclaimer footer on the bottom, content between. Lives as its
 * own component (rather than inline in app/layout.tsx) so tests can render
 * a page inside the real chrome without jsdom fighting <html>/<body>.
 *
 * The footer moved here FROM TranslateFlow: same component, same copy,
 * now guaranteed on every route by construction instead of by each page
 * remembering to include it.
 */
export function SiteShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteNav />
      <main className="flex flex-1 flex-col">{children}</main>
      <DisclaimerFooter />
    </>
  );
}
