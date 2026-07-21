import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { SiteShell } from "@/components/chrome/SiteShell";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Deflate",
  description: "An honest backtester: plain-English strategy in, a verdict you can trust out.",
  // No OpenGraph tags existed before this rename; adding the minimum so a
  // shared link preview reads "Deflate" too, reusing the title/description
  // above verbatim -- no new copy. Page-level metadata below only
  // overrides `title`, so this object is inherited unchanged site-wide.
  openGraph: {
    title: "Deflate",
    description: "An honest backtester: plain-English strategy in, a verdict you can trust out.",
    type: "website",
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
      </body>
    </html>
  );
}
