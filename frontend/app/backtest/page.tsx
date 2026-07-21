import type { Metadata } from "next";

import { TranslateFlow } from "@/components/translation/TranslateFlow";

export const metadata: Metadata = {
  title: "Backtest — Deflate",
  description: "Describe a strategy in plain English; review every assumption before it runs.",
};

/**
 * The ENTIRE backtest flow lives on this one route (Phase 11 route
 * architecture): input → translating → gate → confirming → results, the
 * correction loop, and the no-exit branch all run inside `TranslateFlow`'s
 * state machine. Gate and results deliberately have NO URLs of their own —
 * a results surface with its own route could mount without /confirm having
 * returned in-session, which the state machine makes impossible.
 *
 * `?s=` carries a landing-page example into the strategy box. It prefills
 * text only — nothing translates or runs without the user's own submit.
 */
export default async function BacktestPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { s } = await searchParams;
  return (
    <div className="flex flex-1 flex-col bg-background font-sans">
      <TranslateFlow initialText={typeof s === "string" ? s : undefined} />
    </div>
  );
}
