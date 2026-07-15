/**
 * Phase 11 motion behavior. Three claims, all about DISCIPLINE rather than
 * aesthetics:
 *
 *  1. Reduced motion is fully supported (INV-5): under
 *     prefers-reduced-motion the spinner swaps for a static glyph and all
 *     timing LOGIC (stage thresholds, elapsed counter) behaves identically.
 *  2. Motion never delays or blocks a state change's logical effect: with
 *     fake timers running, the next state's content is in the document the
 *     moment its API promise settles -- no timer advance needed.
 *  3. Motion is never a judgment channel (INV-4): the results reveal emits
 *     byte-identical animation classes and delays for every verdict.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProgressIndicator, CONFIRM_STAGES } from "@/components/chrome/ProgressIndicator";
import { RobustnessResultView } from "@/components/robustness/RobustnessResultView";
import { TranslateFlow } from "@/components/translation/TranslateFlow";
import type { TranslationApi } from "@/lib/translation/api";
import type { RobustnessResult } from "@/lib/robustness/types";
import type { TranslationPayload } from "@/lib/translation/types";

import likelyOverfitFixture from "@/fixtures/robustness/likely_overfit.json";
import ordinaryFixture from "@/fixtures/translation/ordinary_assumptions.json";
import passFixture from "@/fixtures/robustness/pass.json";
import shakyFixture from "@/fixtures/robustness/shaky.json";
import untestableFixture from "@/fixtures/robustness/untestable.json";

const ORDINARY = ordinaryFixture as unknown as TranslationPayload;
const PASS_RESULT = passFixture as unknown as RobustnessResult;

function stubMatchMedia(matches: boolean) {
  const original = window.matchMedia;
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? matches : false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
  return () => {
    window.matchMedia = original;
  };
}

describe("INV-5: prefers-reduced-motion", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("swaps the spinner for a static glyph when reduced motion is set", async () => {
    restore = stubMatchMedia(true);
    render(<ProgressIndicator testId="prog" label="Working…" />);

    expect(await screen.findByTestId("prog-static-glyph")).toBeInTheDocument();
    expect(screen.queryByTestId("prog-spinner")).not.toBeInTheDocument();
    // The static glyph itself carries no animation class.
    expect(screen.getByTestId("prog-static-glyph").className).not.toMatch(/animate-/);
  });

  it("keeps the animated spinner when reduced motion is NOT set", async () => {
    restore = stubMatchMedia(false);
    render(<ProgressIndicator testId="prog" label="Working…" />);

    expect(await screen.findByTestId("prog-spinner")).toBeInTheDocument();
    expect(screen.queryByTestId("prog-static-glyph")).not.toBeInTheDocument();
  });

  it("timing LOGIC is identical under reduced motion: stages and elapsed still advance", async () => {
    restore = stubMatchMedia(true);
    vi.useFakeTimers();
    try {
      render(<ProgressIndicator testId="prog" label="Working…" stages={CONFIRM_STAGES} showElapsed />);
      expect(screen.getByTestId("prog-stage")).toHaveTextContent("Fetching price history");

      act(() => {
        vi.advanceTimersByTime(5000);
      });
      expect(screen.getByTestId("prog-stage")).toHaveTextContent("Running the backtest");
      expect(screen.getByTestId("prog-elapsed")).toHaveTextContent("5s elapsed");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("motion never delays a state change's logical effect", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("gate content and results content are present the moment their API call settles -- zero timer advancement", async () => {
    const api: TranslationApi = {
      translate: vi.fn().mockResolvedValue(ORDINARY),
      correct: vi.fn(),
      confirm: vi.fn().mockResolvedValue(PASS_RESULT),
    };
    render(<TranslateFlow api={api} />);

    fireEvent.change(screen.getByTestId("nl-input"), { target: { value: "buy SPY when RSI < 30" } });
    fireEvent.click(screen.getByTestId("translate-submit"));
    // Flush ONLY microtasks (the resolved promise) -- no vi.advanceTimersByTime.
    // If any animation timer gated the mount, this would fail.
    await act(async () => {});
    expect(screen.getByTestId("gate")).toBeInTheDocument();
    expect(screen.getByTestId("assumptions-view")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("confirm-run-button"));
    await act(async () => {});
    expect(screen.getByTestId("robustness-result-view")).toBeInTheDocument();
    expect(screen.getByTestId("verdict-card")).toBeInTheDocument();
    // And the outgoing surfaces are GONE the same instant -- entrance-only
    // motion, no exit animation holding stale DOM (gate integrity).
    expect(screen.queryByTestId("gate")).not.toBeInTheDocument();
    expect(screen.queryByTestId("confirm-gate")).not.toBeInTheDocument();
  });
});

describe("INV-4: identical entrance for every verdict -- motion is not a judgment channel", () => {
  const fixtures: Array<[string, RobustnessResult]> = [
    ["PASS", passFixture as unknown as RobustnessResult],
    ["SHAKY", shakyFixture as unknown as RobustnessResult],
    ["LIKELY_OVERFIT", likelyOverfitFixture as unknown as RobustnessResult],
    ["UNTESTABLE", untestableFixture as unknown as RobustnessResult],
  ];

  function revealSignature(result: RobustnessResult): string[] {
    const { unmount } = render(<RobustnessResultView result={result} />);
    const view = screen.getByTestId("robustness-result-view");
    const signature = Array.from(view.children).map((child) => {
      const el = child as HTMLElement;
      return `${el.className}|${el.style.animationDelay}`;
    });
    unmount();
    return signature;
  }

  it("all four verdicts produce byte-identical wrapper classes and stagger delays, verdict card first", () => {
    const signatures = fixtures.map(([, result]) => revealSignature(result));
    for (const signature of signatures.slice(1)) {
      expect(signature).toEqual(signatures[0]);
    }
    // Sanity: it IS a stagger (delays ascend from 0) and the first slot is
    // the verdict card's wrapper.
    const first = signatures[0];
    expect(first.length).toBeGreaterThanOrEqual(3);
    expect(first[0]).toMatch(/animate-enter-slide/);
    expect(first[0].endsWith("|0ms")).toBe(true);
  });
});
