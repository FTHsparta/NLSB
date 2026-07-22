import { ImageResponse } from "next/og";

/**
 * The link-preview card for https://deflate.app, generated at build time.
 *
 * This is a MARKETING asset, not app UI — it is deliberately NOT bound by
 * the "verdict card is the only saturated color" invariant. It stays
 * monochrome anyway (Bloomberg-terminal restraint, same as the site), with
 * a single subtle hairline accent. Colors mirror globals.css's dark palette
 * as concrete hex, since Satori needs literal values, not CSS variables:
 * background hsl(240 6% 8%) = #131316, foreground #f5f5f5, muted #94949e,
 * border #2b2b30.
 *
 * No custom font is loaded on purpose: ImageResponse ships a bundled default
 * sans, and the documented file-based example renders text without a `fonts`
 * option. A working card in the default font is worth more than a build that
 * breaks trying to load Geist into Satori — the task's explicit call.
 *
 * `app/twitter-image.tsx` re-exports this module so the Twitter card is the
 * identical asset with zero duplication.
 */

export const alt = "Deflate — an honest backtester";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

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
          background: "#131316",
        }}
      >
        <div
          style={{
            fontSize: 168,
            fontWeight: 700,
            letterSpacing: -4,
            color: "#f5f5f5",
            display: "flex",
          }}
        >
          Deflate
        </div>

        {/* The one subtle accent: a short monochrome hairline. */}
        <div
          style={{
            width: 96,
            height: 3,
            background: "#2b2b30",
            marginTop: 36,
            marginBottom: 36,
          }}
        />

        <div
          style={{
            fontSize: 46,
            letterSpacing: 2,
            color: "#94949e",
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
