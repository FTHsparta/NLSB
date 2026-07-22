import type { MetadataRoute } from "next";

/**
 * Served at /sitemap.xml. Lists the three INDEXABLE, human-navigable routes
 * only — /_not-found is excluded (it's an error page, never a destination),
 * and there is no /api on the frontend. URLs are absolute to the production
 * origin so a Vercel preview deployment can't advertise itself for indexing.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  return [
    {
      url: "https://deflate.app",
      lastModified,
      changeFrequency: "monthly",
      priority: 1.0,
    },
    {
      url: "https://deflate.app/backtest",
      lastModified,
      changeFrequency: "monthly",
      priority: 0.9,
    },
    {
      url: "https://deflate.app/methodology",
      lastModified,
      changeFrequency: "monthly",
      priority: 0.7,
    },
  ];
}
