import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Pin the workspace root: the user's home directory (an ancestor) has its
  // own package-lock.json from an unrelated project, which otherwise makes
  // Next.js infer the wrong root.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
