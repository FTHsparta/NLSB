/**
 * Phase 11 site shell + routes. The shell (nav + disclaimer footer) wraps
 * every route via app/layout.tsx; these tests render each route's page
 * component inside the REAL SiteShell -- the same composition the layout
 * performs -- and pin the route architecture: landing at "/", the entire
 * flow on /backtest (state machine, not URL-split), methodology as a page.
 *
 * INV-2 extension: the landing page and methodology page are wholly
 * monochrome -- verdict NAMES appear in plain type; verdict COLOR exists
 * only on the real verdict card.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import BacktestPage from "@/app/backtest/page";
import LandingPage from "@/app/page";
import MethodologyPage from "@/app/methodology/page";
import { SiteShell } from "@/components/chrome/SiteShell";
import { EXAMPLE_STRATEGIES, backtestHref } from "@/lib/examples";

const SATURATED_COLOR_CLASS =
  /\b(?:bg|text|border(?:-[trblxy])?|ring|from|via|to|fill|stroke)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/;

async function renderBacktestPage(params: Record<string, string> = {}) {
  return render(<SiteShell>{await BacktestPage({ searchParams: Promise.resolve(params) })}</SiteShell>);
}

describe("shared layout: nav and footer are present on every route", () => {
  const routes: Array<[string, () => Promise<React.ReactElement> | React.ReactElement]> = [
    ["/", () => <LandingPage />],
    ["/methodology", () => <MethodologyPage />],
    ["/backtest", () => BacktestPage({ searchParams: Promise.resolve({}) })],
  ];

  it.each(routes)("route %s renders inside nav + disclaimer footer", async (_route, page) => {
    render(<SiteShell>{await page()}</SiteShell>);

    const nav = screen.getByTestId("site-nav");
    expect(within(nav).getByTestId("site-nav-wordmark")).toHaveTextContent("NLSB");
    expect(within(nav).getByTestId("site-nav-backtest")).toHaveAttribute("href", "/backtest");
    expect(within(nav).getByTestId("site-nav-methodology")).toHaveAttribute("href", "/methodology");

    expect(screen.getByTestId("disclaimer-footer")).toBeInTheDocument();
  });

  it("the nav itself is monochrome and never references a verdict token", () => {
    render(<SiteShell><div /></SiteShell>);
    const html = screen.getByTestId("site-nav").innerHTML;
    expect(html).not.toMatch(SATURATED_COLOR_CLASS);
    expect(html).not.toMatch(/verdict-/);
  });
});

describe("landing page", () => {
  it("hero CTA navigates to /backtest", () => {
    render(<LandingPage />);
    expect(screen.getByTestId("landing-cta")).toHaveAttribute("href", "/backtest");
  });

  it("names all four verdicts in the strip -- in plain type, with no verdict token and no saturated hue", () => {
    render(<LandingPage />);
    const strip = screen.getByTestId("landing-verdicts");
    for (const name of ["PASS", "SHAKY", "LIKELY OVERFIT", "UNTESTABLE"]) {
      expect(strip).toHaveTextContent(name);
    }
    expect(strip.innerHTML).not.toMatch(SATURATED_COLOR_CLASS);
    expect(strip.innerHTML).not.toMatch(/verdict-/);
  });

  it("is wholly monochrome (INV-2): no saturated hue, no verdict token anywhere on the page", () => {
    render(<LandingPage />);
    const html = screen.getByTestId("landing-page").innerHTML;
    expect(html).not.toMatch(SATURATED_COLOR_CLASS);
    expect(html).not.toMatch(/verdict-/);
  });

  it("renders the three 'what it does' items", () => {
    render(<LandingPage />);
    expect(screen.getAllByTestId("landing-what-item")).toHaveLength(3);
  });

  it("each example chip links to /backtest with that example's full text in the ?s= param", () => {
    render(<LandingPage />);
    const chips = screen.getAllByTestId("landing-example-chip");
    expect(chips).toHaveLength(EXAMPLE_STRATEGIES.length);
    chips.forEach((chip, i) => {
      expect(chip).toHaveAttribute("href", backtestHref(EXAMPLE_STRATEGIES[i].text));
      expect(chip.getAttribute("href")).toContain("/backtest?s=");
    });
  });
});

describe("/backtest: the whole flow on one route, with ?s= prefill", () => {
  it("mounts the flow at its input state (state machine intact, no URL-split gate/results)", async () => {
    await renderBacktestPage();
    expect(screen.getByTestId("translate-flow")).toBeInTheDocument();
    expect(screen.getByTestId("translate-input-view")).toBeInTheDocument();
    // Nothing beyond idle exists at mount -- gate and results are states,
    // not routes, and neither can exist before its API call returns.
    expect(screen.queryByTestId("gate")).not.toBeInTheDocument();
    expect(screen.queryByTestId("robustness-result-view")).not.toBeInTheDocument();
  });

  it("prefills the strategy box from ?s= (a landing chip's target) without submitting anything", async () => {
    const example = EXAMPLE_STRATEGIES[0].text;
    await renderBacktestPage({ s: example });
    expect(screen.getByTestId("nl-input")).toHaveValue(example);
    // Prefill only -- still idle, nothing translated, nothing run.
    expect(screen.queryByTestId("translating-indicator")).not.toBeInTheDocument();
    expect(screen.queryByTestId("gate")).not.toBeInTheDocument();
  });

  it("leaves the strategy box empty when ?s= is absent (dev behavior unchanged)", async () => {
    await renderBacktestPage();
    expect(screen.getByTestId("nl-input")).toHaveValue("");
  });
});

describe("/methodology: first-class route with the shared content", () => {
  it("renders a heading for every verdict and stays wholly monochrome", () => {
    render(<MethodologyPage />);
    for (const v of ["PASS", "SHAKY", "LIKELY_OVERFIT", "UNTESTABLE"]) {
      expect(screen.getByTestId(`methodology-page-heading-${v}`)).toBeInTheDocument();
    }
    const html = screen.getByTestId("methodology-page").innerHTML;
    expect(html).not.toMatch(SATURATED_COLOR_CLASS);
    expect(html).not.toMatch(/verdict-/);
  });

  it("describes all four checks and links back to /backtest", () => {
    render(<MethodologyPage />);
    const page = screen.getByTestId("methodology-page");
    for (const check of ["Walk-forward", "Parameter sensitivity", "Deflated Sharpe", "Regime breakdown"]) {
      expect(page).toHaveTextContent(check);
    }
    expect(screen.getByTestId("methodology-cta")).toHaveAttribute("href", "/backtest");
  });
});
