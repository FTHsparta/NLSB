/**
 * Phase 12D: the custom error surfaces.
 *
 * Before this, a mistyped URL or a render error showed Next's stock unstyled
 * default on a site whose every other surface is deliberately voiced. These
 * pin the two things that actually matter about the replacements: every one
 * offers a real way forward, and none of them ever renders the error.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RouteError from "@/app/error";
import GlobalError from "@/app/global-error";
import NotFound from "@/app/not-found";

const SECRET = "Error: connect ECONNREFUSED 10.0.0.1:5432 at Socket.emit (node:net:1234)";

function makeError(): Error & { digest?: string } {
  const err = new Error(SECRET) as Error & { digest?: string };
  err.digest = "3892174650";
  return err;
}

let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  // The pages log the error on purpose; keep it out of the test output while
  // still asserting it happened.
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  consoleError.mockRestore();
});

describe("not-found", () => {
  it("renders voiced copy with both ways forward", () => {
    render(<NotFound />);

    expect(screen.getByTestId("not-found-page")).toBeInTheDocument();
    expect(screen.getByTestId("not-found-page-home-link")).toHaveAttribute("href", "/");
    expect(screen.getByTestId("not-found-page-backtest-link")).toHaveAttribute("href", "/backtest");
  });

  it("carries no apology theater or exclamation marks", () => {
    render(<NotFound />);
    const text = screen.getByTestId("not-found-page").textContent ?? "";

    expect(text).not.toContain("!");
    expect(text.toLowerCase()).not.toContain("sorry");
    expect(text.toLowerCase()).not.toContain("oops");
  });
});

describe("route error boundary", () => {
  it("renders, offers retry, and links onward", () => {
    const retry = vi.fn();
    render(<RouteError error={makeError()} unstable_retry={retry} />);

    expect(screen.getByTestId("route-error-page")).toBeInTheDocument();
    expect(screen.getByTestId("route-error-page-home-link")).toHaveAttribute("href", "/");
    expect(screen.getByTestId("route-error-page-backtest-link")).toHaveAttribute("href", "/backtest");
    screen.getByTestId("route-error-page-retry").click();
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("uses `reset` when the unstable retry prop is absent", () => {
    // `unstable_retry` is the documented prop in Next 16.2; the fallback
    // keeps the button working if that unstable name changes.
    const reset = vi.fn();
    render(<RouteError error={makeError()} reset={reset} />);

    screen.getByTestId("route-error-page-retry").click();
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("never renders the error message, stack, or digest", () => {
    render(<RouteError error={makeError()} unstable_retry={vi.fn()} />);
    const text = screen.getByTestId("route-error-page").textContent ?? "";

    expect(text).not.toContain("ECONNREFUSED");
    expect(text).not.toContain("10.0.0.1");
    expect(text).not.toContain("3892174650");
    expect(text).not.toContain("node:net");
  });

  it("logs the error where the platform can see it", () => {
    const error = makeError();
    render(<RouteError error={error} unstable_retry={vi.fn()} />);
    expect(consoleError).toHaveBeenCalledWith(error);
  });
});

describe("global error boundary", () => {
  it("renders self-contained markup with plain anchors", () => {
    // The router may be part of what failed, so these must be real anchors
    // that force a document load, not client-side <Link>s.
    render(<GlobalError error={makeError()} unstable_retry={vi.fn()} />);

    expect(screen.getByTestId("global-error-page")).toBeInTheDocument();
    expect(screen.getByTestId("global-error-page-home-link")).toHaveAttribute("href", "/");
    expect(screen.getByTestId("global-error-page-backtest-link")).toHaveAttribute(
      "href",
      "/backtest"
    );
  });

  it("never renders the error message, stack, or digest", () => {
    render(<GlobalError error={makeError()} unstable_retry={vi.fn()} />);
    const text = screen.getByTestId("global-error-page").textContent ?? "";

    expect(text).not.toContain("ECONNREFUSED");
    expect(text).not.toContain("3892174650");
  });

  it("exposes the retry affordance", () => {
    const retry = vi.fn();
    render(<GlobalError error={makeError()} unstable_retry={retry} />);
    screen.getByTestId("global-error-page-retry").click();
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
