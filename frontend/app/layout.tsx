import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { SiteShell } from "@/components/chrome/SiteShell";
import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// One source of truth for the shared title/description so the base tags,
// the OG block, and the Twitter block can never drift apart.
const SITE_TITLE = "Deflate";
const SITE_DESCRIPTION =
  "An honest backtester: plain-English strategy in, a verdict you can trust out.";

export const metadata: Metadata = {
  // Absolute base for every resolved URL (canonical, OG, the generated OG
  // image). Pinned to the production origin ON PURPOSE: without it, Vercel
  // preview deployments would emit their own preview host into canonical/OG
  // tags and could get indexed under the wrong domain. The file-convention
  // endpoints (opengraph-image, sitemap, robots) resolve against this.
  metadataBase: new URL("https://deflate.app"),
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  alternates: {
    // Self-canonical at the root; metadataBase makes this absolute.
    canonical: "/",
  },
  openGraph: {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    url: "https://deflate.app",
    siteName: "Deflate",
    type: "website",
    // No `images` here on purpose: app/opengraph-image.tsx injects the card
    // automatically. Listing it here too would emit a duplicate/conflicting
    // og:image tag.
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    // Likewise no `images`: app/twitter-image.tsx (re-exporting the OG card)
    // supplies twitter:image automatically.
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`dark ${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <SiteShell>{children}</SiteShell>
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}
