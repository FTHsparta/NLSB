import { describe, expect, it } from "vitest";

import { apiBaseUrl, apiUrl } from "@/lib/apiBase";

// The helpers take the raw env value / base as an argument (defaulting to
// process.env at call time), so set/unset cases are tested by passing values
// explicitly -- no fragile env mutation between cases.

describe("apiBaseUrl", () => {
  it("returns \"\" when the env var is unset, keeping dev's relative-path behavior", () => {
    expect(apiBaseUrl(undefined)).toBe("");
  });

  it("returns \"\" when the env var is set but empty", () => {
    expect(apiBaseUrl("")).toBe("");
  });

  it("passes through an absolute origin unchanged", () => {
    expect(apiBaseUrl("https://api.example.com")).toBe("https://api.example.com");
  });

  it("strips trailing slashes so joined URLs never double the '/'", () => {
    expect(apiBaseUrl("https://api.example.com/")).toBe("https://api.example.com");
    expect(apiBaseUrl("https://api.example.com//")).toBe("https://api.example.com");
  });
});

describe("apiUrl", () => {
  it("returns the path as-is when no base is configured (dev proxy case)", () => {
    expect(apiUrl("/translate", apiBaseUrl(undefined))).toBe("/translate");
  });

  it("prefixes the configured base URL (deployed case)", () => {
    expect(apiUrl("/translate", apiBaseUrl("https://api.example.com/"))).toBe(
      "https://api.example.com/translate"
    );
  });

  it("covers all three backend routes", () => {
    const base = apiBaseUrl("https://api.example.com");
    expect(apiUrl("/translate", base)).toBe("https://api.example.com/translate");
    expect(apiUrl("/correct", base)).toBe("https://api.example.com/correct");
    expect(apiUrl("/confirm", base)).toBe("https://api.example.com/confirm");
  });

  it("defaults to the process.env-derived base when none is passed", () => {
    // NEXT_PUBLIC_API_BASE_URL is unset in the test environment, so the
    // default-argument path must produce the relative dev URL.
    expect(apiUrl("/translate")).toBe("/translate");
  });
});
