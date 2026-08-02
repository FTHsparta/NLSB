/**
 * Phase 12D: funnel instrumentation.
 *
 * Events are inert by default (see `lib/analytics.ts`) -- the suite opts in by
 * installing a sink, the same "off unless a test asks for it" shape the
 * backend uses for the rate limiter and the translation cache. Nothing here
 * touches the network.
 *
 * The two assertions that matter most:
 *   * no event payload can carry the submitted strategy text, and
 *   * instrumentation observes the state machine without driving it.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExampleChips } from "@/components/landing/ExampleChips";
import { TranslateFlow } from "@/components/translation/TranslateFlow";
import { EVENTS, sanitizeProps, setAnalyticsSink, trackEvent } from "@/lib/analytics";
import type { TranslationApi } from "@/lib/translation/api";

import passFixture from "@/fixtures/robustness/pass.json";
import type { RobustnessResult } from "@/lib/robustness/types";

const PASS_RESULT = passFixture as unknown as RobustnessResult;

const STRATEGY_TEXT = "Buy SPY when RSI(14) drops below 30, sell when it rises above 70";

const TRANSLATION_OK = {
  status: "ok" as const,
  ir: {
    asset: { ticker: "SPY", asset_class: "equity" },
    indicators: [{ id: "rsi14", type: "RSI", params: { period: 14 }, source: "close" }],
    entry: { left: "rsi14", op: "<", right: 30 },
    exit: { left: "rsi14", op: ">", right: 70 },
    position: { direction: "long", size: "full" },
    risk: null,
  },
  assumptions: [],
  restatement: "Buy SPY when RSI(14) is below 30; sell when RSI(14) is above 70.",
  message: null,
  retries: 0,
};

type Emitted = { name: string; props?: Record<string, unknown> };

let events: Emitted[];
let disposeSink: () => void;

beforeEach(() => {
  events = [];
  disposeSink = setAnalyticsSink((name, props) => events.push({ name, props }));
});

afterEach(() => {
  disposeSink();
});

function names() {
  return events.map((e) => e.name);
}

function fakeApi(overrides: Partial<TranslationApi> = {}): TranslationApi {
  return {
    translate: vi.fn().mockResolvedValue(TRANSLATION_OK),
    correct: vi.fn().mockResolvedValue(TRANSLATION_OK),
    confirm: vi.fn().mockResolvedValue(PASS_RESULT),
    ...overrides,
  } as TranslationApi;
}

async function submitStrategy(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByTestId("nl-input"), STRATEGY_TEXT);
  await user.click(screen.getByTestId("translate-submit"));
}

describe("events are inert unless a sink is installed", () => {
  it("emits nothing after the sink is disposed", () => {
    disposeSink();
    trackEvent(EVENTS.gateShown);
    expect(events).toHaveLength(0);
    // Re-install so afterEach's dispose stays valid.
    disposeSink = setAnalyticsSink((name, props) => events.push({ name, props }));
  });

  it("never throws, even when the sink does", () => {
    disposeSink();
    disposeSink = setAnalyticsSink(() => {
      throw new Error("analytics backend exploded");
    });
    // Fire-and-forget: a tracking failure is never the user's problem.
    expect(() => trackEvent(EVENTS.strategySubmitted)).not.toThrow();
  });
});

describe("payload rules", () => {
  it("drops any property long enough to be free text", () => {
    const clean = sanitizeProps({ nlText: STRATEGY_TEXT, verdict: "PASS", index: 2 });

    expect(clean).not.toHaveProperty("nlText");
    expect(clean).toEqual({ verdict: "PASS", index: 2 });
  });

  it("keeps bounded scalars including null and false", () => {
    expect(sanitizeProps({ status: 429, ok: false, verdict: null })).toEqual({
      status: 429,
      ok: false,
      verdict: null,
    });
  });

  it("NO event payload anywhere in a full run contains the strategy text", async () => {
    // The rule most likely to erode later, pinned end-to-end rather than at
    // one call site: walk a complete funnel and inspect every emitted value.
    const user = userEvent.setup();
    render(<TranslateFlow api={fakeApi()} />);

    await submitStrategy(user);
    await screen.findByTestId("confirm-gate");
    await user.click(screen.getByTestId("confirm-run-button"));
    await screen.findByTestId("robustness-result-view");

    expect(events.length).toBeGreaterThan(0);
    const serialized = JSON.stringify(events);
    expect(serialized).not.toContain("SPY");
    expect(serialized).not.toContain("RSI");
    for (const word of STRATEGY_TEXT.split(/\s+/)) {
      if (word.length > 3) expect(serialized).not.toContain(word);
    }
  });
});

describe("the funnel fires at the right transitions", () => {
  it("walks submitted -> gate shown -> confirmed -> result shown", async () => {
    const user = userEvent.setup();
    render(<TranslateFlow api={fakeApi()} />);

    await submitStrategy(user);
    await screen.findByTestId("confirm-gate");
    await user.click(screen.getByTestId("confirm-run-button"));
    await screen.findByTestId("robustness-result-view");

    expect(names()).toEqual([
      EVENTS.strategySubmitted,
      EVENTS.gateShown,
      EVENTS.gateConfirmed,
      EVENTS.resultShown,
    ]);
  });

  it("reports the verdict kind on result_shown, and nothing finer", async () => {
    const user = userEvent.setup();
    render(<TranslateFlow api={fakeApi()} />);

    await submitStrategy(user);
    await screen.findByTestId("confirm-gate");
    await user.click(screen.getByTestId("confirm-run-button"));
    await screen.findByTestId("robustness-result-view");

    const shown = events.find((e) => e.name === EVENTS.resultShown);
    expect(shown?.props).toEqual({ kind: "full", verdict: "PASS" });
  });

  it("fires request_failed with the status code", async () => {
    const user = userEvent.setup();
    render(
      <TranslateFlow
        api={fakeApi({
          translate: vi.fn().mockRejectedValue(new Error("/translate failed (429): slow down")),
        })}
      />
    );

    await submitStrategy(user);

    await waitFor(() => expect(names()).toContain(EVENTS.requestFailed));
    const failed = events.find((e) => e.name === EVENTS.requestFailed);
    expect(failed?.props).toEqual({ action: "translate", status: 429 });
  });

  it("reports a transport failure as a null status rather than inventing one", async () => {
    const user = userEvent.setup();
    render(
      <TranslateFlow
        api={fakeApi({ translate: vi.fn().mockRejectedValue(new TypeError("Failed to fetch")) })}
      />
    );

    await submitStrategy(user);

    await waitFor(() => expect(names()).toContain(EVENTS.requestFailed));
    const failed = events.find((e) => e.name === EVENTS.requestFailed);
    expect(failed?.props).toEqual({ action: "translate", status: null });
  });
});

describe("gate_abandoned — the event with no happy-path trigger", () => {
  it("fires when the user leaves the gate backwards", async () => {
    const user = userEvent.setup();
    render(<TranslateFlow api={fakeApi()} />);

    await submitStrategy(user);
    await screen.findByTestId("confirm-gate");
    await user.click(screen.getByTestId("back-to-edit"));

    await waitFor(() => expect(names()).toContain(EVENTS.gateAbandoned));
    expect(names()).not.toContain(EVENTS.gateConfirmed);
  });

  it("fires when the user navigates away from the gate", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<TranslateFlow api={fakeApi()} />);

    await submitStrategy(user);
    await screen.findByTestId("confirm-gate");
    unmount();

    expect(names()).toContain(EVENTS.gateAbandoned);
  });

  it("does NOT fire when the user confirms — the ratio has to mean something", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<TranslateFlow api={fakeApi()} />);

    await submitStrategy(user);
    await screen.findByTestId("confirm-gate");
    await user.click(screen.getByTestId("confirm-run-button"));
    await screen.findByTestId("robustness-result-view");
    unmount();

    expect(names()).toContain(EVENTS.gateConfirmed);
    expect(names()).not.toContain(EVENTS.gateAbandoned);
  });

  it("does not count a failed confirm as a second gate impression", async () => {
    const user = userEvent.setup();
    render(
      <TranslateFlow
        api={fakeApi({
          confirm: vi.fn().mockRejectedValue(new Error("/confirm failed (502): upstream")),
        })}
      />
    );

    await submitStrategy(user);
    await screen.findByTestId("confirm-gate");
    await user.click(screen.getByTestId("confirm-run-button"));
    await waitFor(() => expect(names()).toContain(EVENTS.requestFailed));

    // Returning to the gate after a failure is a re-entry, not a new view.
    expect(names().filter((n) => n === EVENTS.gateShown)).toHaveLength(1);
  });
});

describe("INVARIANT: instrumentation observes the machine, never drives it", () => {
  it("completes the whole flow with a sink that throws on every event", async () => {
    disposeSink();
    disposeSink = setAnalyticsSink(() => {
      throw new Error("analytics backend exploded");
    });

    const user = userEvent.setup();
    const api = fakeApi();
    render(<TranslateFlow api={api} />);

    await submitStrategy(user);
    await screen.findByTestId("confirm-gate");
    await user.click(screen.getByTestId("confirm-run-button"));

    // Every transition still happened, in order, with the real calls made.
    await screen.findByTestId("robustness-result-view");
    expect(api.translate).toHaveBeenCalledTimes(1);
    expect(api.confirm).toHaveBeenCalledTimes(1);
  });

  it("emits gate_shown only after the gate has actually rendered", async () => {
    const user = userEvent.setup();
    render(<TranslateFlow api={fakeApi()} />);

    await submitStrategy(user);
    await screen.findByTestId("confirm-gate");

    // Effects run after commit, so the gate is on screen by the time the
    // event exists -- instrumentation trails the machine, never leads it.
    expect(names()).toContain(EVENTS.gateShown);
    expect(screen.getByTestId("confirm-gate")).toBeInTheDocument();
  });
});

describe("example chips", () => {
  it("reports which chip was clicked, by index and label only", async () => {
    const user = userEvent.setup();
    render(<ExampleChips />);

    const chips = screen.getAllByTestId("landing-example-chip");
    await user.click(chips[1]);

    expect(events).toHaveLength(1);
    expect(events[0].name).toBe(EVENTS.exampleClicked);
    expect(events[0].props).toHaveProperty("index", 1);
    // The label is a short name from a fixed four-item list; the strategy
    // text behind the chip is never sent.
    expect(JSON.stringify(events[0].props)).not.toContain("Buy ");
  });

  it("still navigates when tracking throws", async () => {
    disposeSink();
    disposeSink = setAnalyticsSink(() => {
      throw new Error("analytics backend exploded");
    });

    const user = userEvent.setup();
    render(<ExampleChips />);
    const chip = screen.getAllByTestId("landing-example-chip")[0];

    await expect(user.click(chip)).resolves.not.toThrow();
    expect(chip).toHaveAttribute("href", expect.stringContaining("/backtest?s="));
  });
});
