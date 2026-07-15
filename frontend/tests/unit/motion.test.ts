/**
 * Phase 11 motion-system contract. The motion module is the SINGLE source
 * of animation values -- these tests pin the language (150-300ms, one
 * easing, short slides) and the reduced-motion discipline (every animated
 * class is motion-safe gated, so prefers-reduced-motion collapses all
 * non-essential motion at the CSS layer).
 */
import { describe, expect, it } from "vitest";

import {
  MOTION,
  MOTION_DURATION_MS,
  MOTION_EASING,
  STAGGER_STEP_MS,
  staggerDelay,
} from "@/lib/motion";

describe("motion tokens", () => {
  it("exports the duration/easing/stagger tokens", () => {
    expect(MOTION_DURATION_MS).toBeDefined();
    expect(MOTION_EASING).toMatch(/^cubic-bezier\(/);
    expect(STAGGER_STEP_MS).toBeGreaterThan(0);
  });

  it("keeps every duration inside the 150-300ms band", () => {
    for (const [name, ms] of Object.entries(MOTION_DURATION_MS)) {
      expect(ms, `${name} must be >= 150ms`).toBeGreaterThanOrEqual(150);
      expect(ms, `${name} must be <= 300ms`).toBeLessThanOrEqual(300);
    }
  });

  it("keeps the results-reveal stagger in the specified 60-80ms window", () => {
    expect(STAGGER_STEP_MS).toBeGreaterThanOrEqual(60);
    expect(STAGGER_STEP_MS).toBeLessThanOrEqual(80);
  });

  it("gates every animation class on motion-safe, so reduced motion collapses to instant", () => {
    const animated = [MOTION.enter, MOTION.enterSlide, MOTION.pulse];
    for (const cls of animated) {
      for (const token of cls.split(/\s+/)) {
        if (token.includes("animate-")) {
          expect(token, `${cls} must be motion-safe gated`).toMatch(/^motion-safe:/);
        }
      }
    }
  });

  it("keeps the micro-interaction base free of animation (transitions only) and free of hue", () => {
    expect(MOTION.interactive).not.toMatch(/animate-/);
    expect(MOTION.interactive).toMatch(/transition/);
    // Same saturated-hue regex as INV-2: motion must never smuggle in color.
    expect(MOTION.interactive).not.toMatch(
      /\b(?:bg|text|border(?:-[trblxy])?|ring|from|via|to|fill|stroke)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/,
    );
  });

  it("staggerDelay is pure DOM-position arithmetic -- no content-dependent branch exists in its signature", () => {
    expect(staggerDelay(0)).toEqual({ animationDelay: "0ms" });
    expect(staggerDelay(1)).toEqual({ animationDelay: `${STAGGER_STEP_MS}ms` });
    expect(staggerDelay(3)).toEqual({ animationDelay: `${3 * STAGGER_STEP_MS}ms` });
  });
});
