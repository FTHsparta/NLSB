"use client";

import { useEffect, useState } from "react";

/**
 * True when the OS asks for reduced motion (part of the Phase 11 motion
 * system -- tokens live in `lib/motion.ts`; this hook is separate because
 * "use client" would poison the tokens for server components). For the few
 * places CSS motion-safe variants can't express the fallback (e.g.
 * swapping a spinner for a static glyph). Defensive about environments
 * without matchMedia; defaults to false.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    try {
      const query = window.matchMedia("(prefers-reduced-motion: reduce)");
      setReduced(query.matches);
      const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
      query.addEventListener?.("change", onChange);
      return () => query.removeEventListener?.("change", onChange);
    } catch {
      // No matchMedia support: keep motion on; CSS motion-safe still governs.
    }
  }, []);

  return reduced;
}
