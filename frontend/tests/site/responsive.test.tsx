/**
 * Mobile-responsiveness contracts (post-Phase-11 polish pass). jsdom cannot
 * see pixels, so these pin only what is mechanically assertable about the
 * markup: wrap/stack/overflow classes and touch-target utilities. The
 * pixel-level outcomes (no horizontal scroll at 360px, tap comfort, hero
 * wrapping) are on the human-verification checklist in the build log.
 *
 * The conventions pinned here:
 *  - chip containers use flex-wrap; chips carry min-h-11 (44px) on mobile,
 *    with sm:min-h-0 restoring the desktop size;
 *  - every primary/secondary action button carries the same min-h-11 pair;
 *  - numeric tables are wrapped in their own overflow-x-auto container so
 *    a narrow screen scrolls the TABLE, never the page;
 *  - ConfirmGate's two date inputs stack (flex-col) below sm;
 *  - nav links carry layout-neutral touch padding (-m-3 p-3).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import LandingPage from "@/app/page";
import { SiteNav } from "@/components/chrome/SiteNav";
import { BuyHoldComparison } from "@/components/robustness/BuyHoldComparison";
import { RobustnessPanel } from "@/components/robustness/RobustnessPanel";
import { ConfirmGate } from "@/components/translation/ConfirmGate";
import { TranslateFlow } from "@/components/translation/TranslateFlow";
import { TranslateInputView } from "@/components/translation/TranslateInputView";
import type { TranslationApi } from "@/lib/translation/api";
import type { TranslationPayload } from "@/lib/translation/types";
import type { RobustnessResult } from "@/lib/robustness/types";

import noExitResultFixture from "@/fixtures/robustness/no_exit.json";
import ordinaryFixture from "@/fixtures/translation/ordinary_assumptions.json";
import passFixture from "@/fixtures/robustness/pass.json";

const ORDINARY = ordinaryFixture as unknown as TranslationPayload;
const PASS_RESULT = passFixture as unknown as RobustnessResult;
const NO_EXIT_RESULT = noExitResultFixture as unknown as RobustnessResult;

if (PASS_RESULT.kind !== "full") throw new Error("fixture is not a full result");
if (NO_EXIT_RESULT.kind !== "no_exit") throw new Error("fixture is not a no_exit result");

const TOUCH_TARGET = /\bmin-h-11\b/;
const DESKTOP_RESTORE = /\bsm:min-h-0\b/;

function expectTouchTarget(el: HTMLElement) {
  expect(el.className).toMatch(TOUCH_TARGET);
  expect(el.className).toMatch(DESKTOP_RESTORE);
}

describe("RESPONSIVE: chips wrap and stay tappable", () => {
  it("landing example chips: flex-wrap container, 44px-min touch target per chip", () => {
    render(<LandingPage />);
    const chips = screen.getAllByTestId("landing-example-chip");
    expect(chips.length).toBeGreaterThan(0);
    expect(chips[0].parentElement!.className).toMatch(/\bflex-wrap\b/);
    for (const chip of chips) expectTouchTarget(chip);
  });

  it("input-view example chips: flex-wrap container, 44px-min touch target per chip", () => {
    render(<TranslateInputView onSubmit={() => {}} />);
    const chips = screen.getAllByTestId("example-strategy");
    expect(chips.length).toBeGreaterThan(0);
    expect(chips[0].parentElement!.className).toMatch(/\bflex-wrap\b/);
    for (const chip of chips) expectTouchTarget(chip);
  });
});

describe("RESPONSIVE: action buttons carry mobile touch-target sizing", () => {
  it("Translate submit", () => {
    render(<TranslateInputView onSubmit={() => {}} />);
    expectTouchTarget(screen.getByTestId("translate-submit"));
  });

  it("ConfirmGate: run button sized, date inputs stack below sm", () => {
    render(<ConfirmGate defaultTicker="SPY" onConfirm={() => {}} />);
    expectTouchTarget(screen.getByTestId("confirm-run-button"));

    const dateRow = screen.getByTestId("confirm-start-date").parentElement!;
    expect(dateRow.className).toMatch(/\bflex-col\b/);
    expect(dateRow.className).toMatch(/\bsm:flex-row\b/);
  });

  it("correction submit (at the gate) and reset (at results)", async () => {
    const api: TranslationApi = {
      translate: vi.fn().mockResolvedValue(ORDINARY),
      correct: vi.fn(),
      confirm: vi.fn().mockResolvedValue(PASS_RESULT),
    };
    render(<TranslateFlow api={api} />);
    fireEvent.change(screen.getByTestId("nl-input"), { target: { value: "buy SPY when RSI < 30" } });
    fireEvent.click(screen.getByTestId("translate-submit"));
    await waitFor(() => expect(screen.getByTestId("gate")).toBeInTheDocument());
    expectTouchTarget(screen.getByTestId("correction-submit"));

    fireEvent.click(screen.getByTestId("confirm-run-button"));
    await waitFor(() => expect(screen.getByTestId("reset-flow")).toBeInTheDocument());
    expectTouchTarget(screen.getByTestId("reset-flow"));
  });
});

describe("RESPONSIVE: numeric tables scroll within their own container, never the page", () => {
  it("every RobustnessPanel table is wrapped in an overflow-x-auto container", () => {
    const { container } = render(
      <RobustnessPanel
        sensitivity={PASS_RESULT.sensitivity}
        walkForward={PASS_RESULT.walk_forward}
        deflatedSharpe={PASS_RESULT.deflated_sharpe}
        regime={PASS_RESULT.regime}
      />,
    );
    const tables = container.querySelectorAll("table");
    expect(tables.length).toBe(3);
    for (const table of tables) {
      expect(table.parentElement!.className).toMatch(/\boverflow-x-auto\b/);
    }
  });

  it("the buy-and-hold comparison table is wrapped in an overflow-x-auto container", () => {
    const { container } = render(<BuyHoldComparison noExit={NO_EXIT_RESULT.no_exit} />);
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(table!.parentElement!.className).toMatch(/\boverflow-x-auto\b/);
  });
});

describe("RESPONSIVE: nav links have layout-neutral expanded touch areas", () => {
  it("all three links carry the -m-3 p-3 pair", () => {
    render(<SiteNav />);
    for (const id of ["site-nav-wordmark", "site-nav-backtest", "site-nav-methodology"]) {
      const link = screen.getByTestId(id);
      expect(link.className).toMatch(/(?:^|\s)-m-3(?:\s|$)/);
      expect(link.className).toMatch(/(?:^|\s)p-3(?:\s|$)/);
    }
  });
});
