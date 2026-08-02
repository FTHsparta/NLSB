/**
 * Phase 12E: the sink swap.
 *
 * Phase 12D's seam, funnel points, sanitizer, and tests are all unchanged --
 * only the transport moved, from Vercel's `track` to the backend's
 * POST /events. These pin the transport's two load-bearing properties:
 * sendBeacon is preferred so `gate_abandoned` survives page unload, and the
 * body is text/plain so the request skips a CORS preflight it could not
 * survive during unload.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EVENTS, sanitizeProps, setAnalyticsSink, trackEvent } from "@/lib/analytics";

const STRATEGY_TEXT = "Buy SPY when RSI(14) drops below 30, sell when it rises above 70";

/**
 * `trackEvent` is inert unless it is running in a production browser, which
 * is exactly what keeps it silent in dev and the suite. To exercise the real
 * transport we have to stand in that one configuration deliberately.
 */
function asProductionBrowser<T>(run: () => T): T {
  vi.stubEnv("NODE_ENV", "production");
  try {
    return run();
  } finally {
    vi.unstubAllEnvs();
  }
}

let beacon: ReturnType<typeof vi.fn>;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  setAnalyticsSink(null); // no test sink: exercise the real transport
  beacon = vi.fn().mockReturnValue(true);
  fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }));
  vi.stubGlobal("fetch", fetchMock);
  Object.defineProperty(navigator, "sendBeacon", { value: beacon, configurable: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
  setAnalyticsSink(null);
});

describe("inertness is unchanged", () => {
  it("sends nothing outside a production browser", () => {
    trackEvent(EVENTS.gateShown);

    expect(beacon).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("still routes to an installed sink instead of the network", () => {
    const events: string[] = [];
    const dispose = setAnalyticsSink((name) => events.push(name));

    asProductionBrowser(() => trackEvent(EVENTS.gateConfirmed));

    expect(events).toEqual([EVENTS.gateConfirmed]);
    expect(beacon).not.toHaveBeenCalled();
    dispose();
  });
});

describe("transport", () => {
  it("prefers sendBeacon so an unloading page still reports abandonment", () => {
    asProductionBrowser(() => trackEvent(EVENTS.gateAbandoned));

    expect(beacon).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
    const [url] = beacon.mock.calls[0];
    expect(String(url)).toContain("/events");
  });

  it("sends text/plain so the beacon skips a CORS preflight", async () => {
    asProductionBrowser(() => trackEvent(EVENTS.resultShown, { verdict: "PASS" }));

    const [, blob] = beacon.mock.calls[0] as [string, Blob];
    // application/json is not a CORS-simple type and would trigger a
    // preflight the browser will not complete during unload.
    expect(blob.type).toContain("text/plain");
    expect(JSON.parse(await blob.text())).toEqual({
      name: "result_shown",
      props: { verdict: "PASS" },
    });
  });

  it("falls back to keepalive fetch when the browser refuses the beacon", () => {
    beacon.mockReturnValue(false);

    asProductionBrowser(() => trackEvent(EVENTS.strategySubmitted));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.keepalive).toBe(true);
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("omit");
  });

  it("falls back to fetch when sendBeacon does not exist at all", () => {
    Object.defineProperty(navigator, "sendBeacon", { value: undefined, configurable: true });

    asProductionBrowser(() => trackEvent(EVENTS.gateShown));

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("failures stay silent", () => {
  it("does not throw when the beacon throws", () => {
    beacon.mockImplementation(() => {
      throw new Error("beacon exploded");
    });

    expect(() => asProductionBrowser(() => trackEvent(EVENTS.gateShown))).not.toThrow();
  });

  it("swallows a rejected fetch without an unhandled rejection", async () => {
    beacon.mockReturnValue(false);
    fetchMock.mockRejectedValue(new Error("network down"));

    expect(() => asProductionBrowser(() => trackEvent(EVENTS.gateShown))).not.toThrow();
    await Promise.resolve();
  });
});

describe("the sanitizer is still the client's first line of defense", () => {
  it("never puts strategy text on the wire", async () => {
    asProductionBrowser(() =>
      trackEvent(EVENTS.strategySubmitted, { nlText: STRATEGY_TEXT, verdict: "PASS" })
    );

    const [, blob] = beacon.mock.calls[0] as [string, Blob];
    const body = await blob.text();
    expect(body).not.toContain("SPY");
    expect(body).not.toContain(STRATEGY_TEXT);
    expect(JSON.parse(body).props).toEqual({ verdict: "PASS" });
  });

  it("is unchanged from Phase 12D", () => {
    // The swap must not have weakened it; the server's copy is the boundary,
    // this one is the convenience, and both have to hold.
    expect(sanitizeProps({ long: "x".repeat(41), ok: "yes", n: 1 })).toEqual({ ok: "yes", n: 1 });
  });
});
