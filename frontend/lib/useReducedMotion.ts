"use client";

import { useSyncExternalStore } from "react";

/**
 * True when the OS asks for reduced motion (part of the Phase 11 motion
 * system -- tokens live in `lib/motion.ts`; this hook is separate because
 * "use client" would poison the tokens for server components). For the few
 * places CSS motion-safe variants can't express the fallback (e.g.
 * swapping a spinner for a static glyph). Defensive about environments
 * without matchMedia; defaults to false.
 */
const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {};
  }
  try {
    const query = window.matchMedia(QUERY);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  } catch {
    // No matchMedia support: keep motion on; CSS motion-safe still governs.
    return () => {};
  }
}

function getSnapshot(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  try {
    return window.matchMedia(QUERY).matches;
  } catch {
    return false;
  }
}

function getServerSnapshot(): boolean {
  return false;
}

export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
