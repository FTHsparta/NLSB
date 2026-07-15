/**
 * The motion system (Phase 11). ALL animation values live here -- no
 * component defines its own duration, easing, delay, or keyframe class.
 * Pure tokens, importable from server AND client components (the
 * reduced-motion hook lives separately in `lib/useReducedMotion.ts`
 * because a hook forces "use client", which would poison these tokens
 * for server-rendered pages).
 *
 * Language: fades and short (8-16px) slides, 150-300ms, one standard
 * easing. Motion is pure presentation: every animated class is gated on
 * `motion-safe:` so `prefers-reduced-motion` collapses everything to an
 * instant appearance, and NOTHING here ever delays a mount/unmount --
 * state changes take logical effect immediately; the animation only
 * dresses the element that is already there.
 *
 * Display-side corollary: these tokens know nothing about verdicts,
 * severities, or any backend judgment. There is deliberately no API by
 * which a caller could select motion by content -- stagger order is DOM
 * position, never meaning.
 */

/** Durations in ms. Referenced by the CSS keyframe tokens in globals.css;
 * exported so tests can pin the contract (150-300ms band). */
export const MOTION_DURATION_MS = {
  fast: 150, // micro-interactions (hover/active)
  base: 200, // plain fades
  slow: 260, // fade + slide entrances
} as const;

/** One standard easing everywhere (a gentle decelerate). */
export const MOTION_EASING = "cubic-bezier(0.2, 0, 0, 1)";

/** Gap between staggered siblings on the results reveal. */
export const STAGGER_STEP_MS = 70;

/**
 * The class vocabulary. `enter`/`enterSlide` map to the `--animate-*`
 * tokens defined in globals.css; `interactive` is the shared
 * micro-interaction base (monochrome: border/brightness only, never hue).
 */
export const MOTION = {
  /** Fade in on mount. */
  enter: "motion-safe:animate-enter",
  /** Fade + 12px rise on mount -- the standard surface entrance. */
  enterSlide: "motion-safe:animate-enter-slide",
  /** Subtle opacity pulse for indeterminate waiting text. */
  pulse: "motion-safe:animate-pulse-soft",
  /** Hover/active base for buttons and chips. */
  interactive: "transition-[border-color,background-color,opacity] duration-150 ease-out",
} as const;

/**
 * Inline style for the Nth staggered sibling. Safe under reduced motion:
 * with the motion-safe animation class inactive there is no animation for
 * the delay to apply to, so the element simply renders immediately.
 * (`backwards` fill in the keyframe token keeps delayed elements invisible
 * until their turn when motion IS active.)
 */
export function staggerDelay(index: number): { animationDelay: string } {
  return { animationDelay: `${index * STAGGER_STEP_MS}ms` };
}
