import { ImageResponse } from "next/og";

/**
 * The link-preview card for https://deflate.app, generated at build time.
 *
 * Composition: the mark + wordmark lockup, centered — the two-candlestick
 * brand mark, then "Deflate", then the tagline — on a #0A0A0A field, the
 * same near-black as the app icons. This is a MARKETING asset, not app UI,
 * so it is NOT bound by the "verdict card is the only saturated color"
 * invariant; it stays monochrome anyway (mark/wordmark #FAFAFA, tagline
 * #8B8B8B), Bloomberg-terminal restraint, same as the site.
 *
 * The mark is drawn with absolutely-positioned divs, NOT inline <svg>:
 * Satori's SVG support varies, while plain divs rasterize identically and
 * reliably. The two wicks are full-height continuous strips drawn FIRST;
 * the bodies are drawn SECOND, on top — same #FAFAFA, so the overlap is
 * seamless and no rectangle is ever detached from its wick.
 *
 * No custom font is loaded on purpose: ImageResponse ships a bundled default
 * sans, and the documented file-based example renders text without a `fonts`
 * option. A working card in the default font is worth more than a build that
 * breaks trying to load Geist into Satori.
 *
 * `app/twitter-image.tsx` re-exports this module so the Twitter card is the
 * identical asset with zero duplication.
 */

export const alt = "Deflate — an honest backtester";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// The four bars of the mark, in a 154x178 local coordinate space. Wicks
// before bodies so the bodies paint over them (Satori honors DOM order for
// overlapping absolute elements) — guaranteeing a seamless, gap-free mark.
const MARK_BARS = [
  { left: 23, top: 29, width: 12, height: 149 }, // left wick (full-height)
  { left: 119, top: 0, width: 12, height: 178 }, // right wick (full-height)
  { left: 0, top: 58, width: 58, height: 96 }, //  left body
  { left: 96, top: 144, width: 58, height: 34 }, // right body
];

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#0A0A0A",
        }}
      >
        {/* MARK — 154x178 relative container; bars positioned absolutely
            within it. display:flex is set because Satori requires it on any
            element with multiple children, even absolutely-positioned ones. */}
        <div style={{ position: "relative", width: 154, height: 178, display: "flex" }}>
          {MARK_BARS.map((bar, i) => (
            <div
              key={i}
              style={{
                position: "absolute",
                left: bar.left,
                top: bar.top,
                width: bar.width,
                height: bar.height,
                background: "#FAFAFA",
              }}
            />
          ))}
        </div>

        {/* WORDMARK */}
        <div
          style={{
            marginTop: 48,
            fontSize: 88,
            fontWeight: 500,
            letterSpacing: -2,
            color: "#FAFAFA",
            display: "flex",
          }}
        >
          Deflate
        </div>

        {/* TAGLINE */}
        <div
          style={{
            marginTop: 12,
            fontSize: 32,
            color: "#8B8B8B",
            display: "flex",
          }}
        >
          An honest backtester
        </div>
      </div>
    ),
    { ...size },
  );
}
