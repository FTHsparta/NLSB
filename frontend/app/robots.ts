import type { MetadataRoute } from "next";

/**
 * Served at /robots.txt. Allows the whole site, disallows /api/ (the backend
 * proxy path — nothing there is a page to index), and points crawlers at the
 * absolute sitemap URL on the production origin.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: "/api/",
    },
    sitemap: "https://deflate.app/sitemap.xml",
  };
}
