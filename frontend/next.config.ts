import type { NextConfig } from "next";
import path from "path";

// Backend dev server (`uvicorn app.main:app --reload`, per README.md)
// listens here. `lib/translation/api.ts` posts to relative paths
// (`/translate`, `/correct`, `/confirm`) with no origin -- those would
// otherwise resolve against the Next.js dev server itself (which has no
// routes there) rather than FastAPI. The rewrite below is server-side
// proxying, so the browser never makes a cross-origin request and the
// backend needs no CORS config; this is wiring, not route logic, on
// either side.
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Pin the workspace root: the user's home directory (an ancestor) has its
  // own package-lock.json from an unrelated project, which otherwise makes
  // Next.js infer the wrong root.
  turbopack: {
    root: path.join(__dirname),
  },
  async rewrites() {
    return [
      { source: "/translate", destination: `${BACKEND_ORIGIN}/translate` },
      { source: "/correct", destination: `${BACKEND_ORIGIN}/correct` },
      { source: "/confirm", destination: `${BACKEND_ORIGIN}/confirm` },
    ];
  },
};

export default nextConfig;
