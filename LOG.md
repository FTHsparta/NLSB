# Build Log

## 2026-07-25 — OG card: swap wordmark-only for the mark + wordmark lockup

**What:** Frontend marketing asset only, no backend, no app UI. Replaced the
Open Graph card's composition — previously wordmark + hairline + tagline — with
the full brand lockup: the two-candlestick mark, then "Deflate", then the
tagline, centered on the same `#0A0A0A` near-black as the app icons. Exports
(`size` 1200×630, `contentType` image/png, `alt`), the font handling (none —
Satori's bundled default sans), and `twitter-image.tsx`'s re-export are all
untouched; only the JSX changed.

**Lesson — for a rasterized-at-build card, "renders in a browser" is the wrong
bar; "Satori rasterizes it" is the only one that counts.** The mark is a
vector shape, and the reflex is inline `<svg>`. But this card is drawn by
Satori (via `next/og`), whose SVG support is partial and version-dependent —
an `<svg>` that looks right in a browser preview can silently drop or mangle
elements at build time, and the failure only shows up when someone shares the
link. So the mark is built from four absolutely-positioned `<div>`s inside a
154×178 relative box instead: plain rects are the one thing Satori rasterizes
identically to a browser, every time. Verified by decoding the actual emitted
PNG (1200×630, valid header) rather than trusting that the build "compiled" —
compilation and rasterization are different failure surfaces here.

**Lesson — a seam-free mark is a geometry guarantee, not a paint-order hope.**
The wicks are full-height strips (left 29→178, right 0→178); the bodies are
shorter blocks that sit ON the wicks. Drawing wicks first and bodies second so
the bodies paint over them is the belt — but the suspenders is that each body's
rectangle actually OVERLAPS its wick's x-span and y-range (left body x0–58
swallows the wick's x23–35 across y58–154; right body likewise), so the shape
is one connected region regardless of order, and no rectangle floats detached.
Same `#FAFAFA` everywhere means even the overlaps are invisible. Order plus
overlap, not order alone.

**Satori's strict-mode tax, paid up front:** any element with more than one
child needs an explicit `display: flex`, and that includes the mark container
even though its four children are absolutely positioned (out of flow). Set it
explicitly on the root column and the mark box rather than discovering the
"Expected <div> to have explicit display" error at build time.

**Invariants:** no backend change; no app UI; navigable route map unchanged
(`/opengraph-image` and `/twitter-image` are file-convention endpoints, still
present). The verdict-color invariant is untouched — the card is monochrome
(`#FAFAFA` mark/wordmark, `#8B8B8B` tagline) regardless. No test pinned OG
output or alt, so none needed rewriting.

**Counts:** frontend tests 147 → 147 (marketing asset, verified through the
emitted PNG, not a component test). tsc, eslint, `next build` clean.

Next: on a real deploy, re-share the link into Slack/X/iMessage and confirm the
lockup renders as intended in an actual scraper's card, not just as a valid
local PNG.

## 2026-07-24 — Brand icon set: install icon.svg, retire favicon.ico, flag apple-icon SVG gap

**What:** Frontend chrome only, no backend, no UI. Installed the two-candlestick
brand mark as `app/icon.svg` (off-white `#FAFAFA` on near-black `#0A0A0A`,
final artwork, byte-for-byte as supplied), deleted the stale
`app/favicon.ico`, and installed the Apple touch variant as a user-supplied
`app/apple-icon.png` (180×180) — because the SVG couldn't do that job; see the
lesson below.

**Lesson — "read the guide" earned its keep by turning a silent no-op into a
caught one.** The obvious move was to drop `icon.svg` AND `apple-icon.svg` in
`app/` and call it done — both are "file-convention icons," symmetric on the
surface. The bundled Next 16.2.9 doc's file-type table is where the symmetry
breaks: the `icon` convention accepts `.svg`, but the `apple-icon` static-file
convention accepts only `.jpg/.jpeg/.png`. An `apple-icon.svg` isn't an error
— it's worse, it's INERT: Next neither serves an `/apple-icon` route nor emits
an `apple-touch-icon` link, so the file sits on disk looking installed while
doing nothing. Reading the table before writing meant this surfaced as a
flagged decision, not a "why is my iPhone home-screen icon blank" bug weeks
after launch. (It's not purely a Next quirk either — iOS Safari has never
reliably rendered SVG touch icons; PNG is the format Apple actually wants.)

**Lesson — verify chrome against the emitted `<head>`, never the source.** A
favicon "install" is easy to declare done from the file tree alone. The real
proof is what ships in the prerendered HTML: `next build` then grepping
`.next/server/app/index.html` showed exactly one icon link —
`<link rel="icon" href="/icon.svg?<hash>" sizes="any" type="image/svg+xml">`
— with zero remaining `favicon` references and no `apple-touch-icon` link.
That single grep confirmed three things at once: the new mark ships, the old
`favicon.ico` is truly gone (it wins precedence over `icon.svg`, so deleting
it was load-bearing, not cosmetic), and the apple gap is real, not assumed.
The build route table corroborated: `/icon.svg` present, no `/apple-icon`, and
the navigable map (`/`, `/backtest`, `/methodology`) unchanged — the icon
endpoints are file conventions, not routes.

**Decision, not silently taken:** rather than deviate from "install the SVG
byte-for-byte" by quietly rasterizing to PNG or redrawing the candlesticks in
`ImageResponse` JSX (a redraw, explicitly forbidden), the apple variant was
put back to the user, who exported `app/apple-icon.png` (180×180 RGB) himself.
It was copied in byte-for-byte (`cmp`-verified, not re-encoded — a re-encode
would be a redraw through the back door), and no code was needed: the
`apple-icon` file convention auto-generated the link the moment the PNG
existed. The inert `apple-icon.svg` was removed so it can't masquerade as
configured. Post-install `<head>` now carries both links — `apple-touch-icon`
(`sizes="180x180" type="image/png"`) and `icon` (`sizes="any"
type="image/svg+xml"`), each content-hashed — with still zero `favicon` refs.

**Invariants:** No backend change (`git diff backend/` empty). No app UI, no
verdict-color surface touched — the mark is monochrome regardless. No test
pinned a favicon path, head link, or route count (the only `icon` testid,
`check-outcome-icon`, is the results-view severity glyph), so nothing needed
rewriting. tsc, eslint clean; vitest 147/147 unchanged; `next build` green and
emitting `/icon.svg` with no `favicon.ico` route.

**Files:** added `app/icon.svg` and `app/apple-icon.png`; deleted
`app/favicon.ico`. (`apple-icon.svg` was written, proven inert, and removed
within this session — net zero.)

Next: after deploy, re-check the actual favicon + iOS "Add to Home Screen"
render on real devices (Next content-hashes both assets, so a stale cached
icon shouldn't linger, but confirm) — then the launch-blocking chrome is done.

## 2026-07-22 (4) — SEO + social-preview chrome: metadataBase, generated OG card, sitemap, robots

**What:** Frontend-only, static SEO/share metadata — zero backend, zero run
data. (1) `layout.tsx` metadata gains `metadataBase: https://deflate.app`, a
self-canonical, a completed `openGraph` block (url/siteName/type), and a
`twitter` summary_large_image block reusing the same title/description. (2)
Code-generated OG card at `app/opengraph-image.tsx` (dark, monochrome
wordmark + tagline) with `app/twitter-image.tsx` re-exporting it. (3)
`app/sitemap.ts` (three indexable routes, absolute URLs) and (4)
`app/robots.ts` (allow /, disallow /api/, absolute sitemap ref).

**Lesson — the honest fix for "OG image" is to set it in exactly ONE place,
and the trap is that Next gives you three.** You can declare `images` in
`openGraph`, in `twitter`, AND via the `opengraph-image` file convention —
and if you do more than one, you emit duplicate/conflicting `og:image` tags
that scrapers resolve inconsistently. The file convention is the strongest
(it auto-injects width/height/type/alt and content-hashes the URL for cache-
busting), so the right move was to declare the image NOWHERE in the metadata
object and let the convention own it. Verified structurally, not by faith:
the prerendered `index.html` carries exactly one `og:image` and one
`twitter:image`, both absolute, both content-hashed — which only holds
because `images` was omitted from both blocks. `metadataBase` is what turns
the convention's relative `/opengraph-image` into the absolute production
URL; without it, a Vercel preview deploy would stamp its own preview host
into canonical + OG and risk being indexed as the canonical site.

**Lesson — "read the guide before writing" caught a real version fork.** The
frontend's AGENTS.md insists this isn't the Next.js from training data, and
it earned its keep: the bundled docs confirmed `ImageResponse` still imports
from `next/og` (moved there in v14), that the file-based OG example renders
text with NO `fonts` option (the bundled default sans is enough), and that
Satori supports only flexbox + a CSS subset (no `grid`). So the card uses a
fontless default and pure flexbox — the task's "a working card in a fallback
font beats a broken build" made structural, not hoped-for. `next build`
statically prerenders the card at build time, so a font/layout error would
have failed the build loudly rather than at share time.

**Off-script, flagged: `main` arrived with a broken build that wasn't mine.**
Two commits landed after the last push — `47c4585 vercel analytics`,
`d81236e speed analytics` — adding `@vercel/analytics/next` and
`@vercel/speed-insights/next` imports to `layout.tsx` WITHOUT adding either
package to `package.json` or installing them. `next build` (and, identically,
the Vercel deploy) failed at module resolution before ever reaching my
endpoints. The imports are unambiguously intended, so I installed both
packages (declared now in package.json/lock) to unblock the required build
verification and repair the deploy. Called out here because it's outside the
SEO scope and modified dependency manifests — not a silent side effect.

**Routes:** the navigable route map (/, /backtest, /methodology, /_not-found)
is UNCHANGED. The build now lists four additional entries —
`/opengraph-image`, `/twitter-image`, `/robots.txt`, `/sitemap.xml` — but
these are generated file-convention endpoints, not human-navigable pages. No
test asserts a route count or pins layout metadata (checked in orientation:
the only `toHaveLength` assertions count content items — glossary terms,
limitation cards, example chips — never routes), so no test needed rewriting.

**Invariants:** INV-1: `git diff backend/` empty. INV-2: every string is
static site copy; the sitemap/OG carry no run data. INV-3: navigable routes
unchanged; only file-convention endpoints added. INV-4: canonical, og:url,
og:image, twitter:image, all sitemap `loc`s, and the robots sitemap ref are
all absolute to https://deflate.app (verified in the emitted
`sitemap.xml.body`, `robots.txt.body`, and prerendered `index.html` head).
INV-5: all 147 tests green, none touched. INV-6: tsc, eslint, `next build`
clean; build emits /sitemap.xml, /robots.txt, and /opengraph-image without
error.

**Counts:** frontend tests unchanged at 147 (SEO chrome has no component
tests — it's verified through the build's emitted artifacts, the honest
check for file-convention endpoints). Backend untouched at 251.

Next: manual steps I can't do — submit the sitemap in Google Search Console
and confirm the Vercel production domain env, then a real link-preview smoke
(paste https://deflate.app into Slack/X/iMessage) to confirm the card renders
before announcing launch.

## 2026-07-22 (3) — "How Deflate works": glossary + limitations on /methodology, inline results pointer

**What:** Static, generic chrome only — no backend changes, no new route.
(1) /methodology gains an adversarial intro lead, a seven-term "Key terms"
glossary, and a six-entry "What Deflate does not do" limitations section
(approved copy, verbatim), all alongside the existing check/verdict
explanations. (2) The results view gains ONE static line below the checks —
"These results are close to gross and assume next-day-close fills…" —
linking to /methodology#limitations, as a sibling wrapper that never
touches VerdictCard or RobustnessPanel.

**Lesson — "no digits" was never the invariant; "no digits WHERE a digit
could read as a run's own number" was.** `methodologyContent.ts` carries a
pinned no-digits test via MethodologyNote, and the new limitations copy is
full of digits (0.05% per fill, the 80% concentration threshold, the 2015
default window). The naive move — appending the new exports to the shared
module — would have forced a choice between weakening that pin or mangling
approved copy. The right move was noticing the pin's SCOPE: MethodologyNote
renders next to real results, where any figure could masquerade as the
strategy's own; the /methodology page is exactly where the system's fixed
constants must be stated precisely, because vagueness there would be its
own dishonesty. So the copy lives in a NEW module
(`howDeflateWorksContent.ts`) whose docstring forbids MethodologyNote from
ever importing it, the old module's no-digits contract stays true and
pinned, and the new page tests assert those digits POSITIVELY. Same word
— "digits" — two opposite obligations, resolved by scoping, not by
compromise.

**Lesson — a well-scoped signature test absorbs change without edits, and
that's evidence FOR it, not a gap.** The motion test's `revealSignature`
reads the result view's child wrappers and asserts byte-identical
class/delay across all four verdicts. Adding the pointer wrapper (fifth
child, constant text/class/delay) passed it untouched — because the test
asserts cross-verdict EQUALITY, not a hardcoded child count. Where the
old color-invariants test (last phase) kept passing by accident — scoped
too narrowly to notice a new token family — this one keeps passing by
design: a verdict-conditional pointer would still fail it. The difference
got documented in the test's scope note rather than left as tribal
knowledge; assertions unchanged.

**Placement detail:** the pointer slots between the checks panel and
MethodologyNote (stagger index 2), shifting the note/disclaimer to 3/4 and
TranslateFlow's reset button to 5 — the reveal stays strictly sequential,
and no test pinned those literal indices (verified before shifting, not
assumed). CONTRACT 9 now pins the pointer's three obligations: below the
checks in DOM order with the #limitations href, never nested inside
VerdictCard/RobustnessPanel, byte-identical text across verdicts. The
limitations section carries `id="limitations"` and the page test asserts
that id — the deep link is pinned from both ends. One editorial call:
the old header lead ("here is exactly what each check asks…") was
REPLACED by the approved intro, not stacked above it — two overlapping
leads would have read as filler; the old lead's promise is a subset of
the new one's.

**Invariants:** INV-1: every added string is a system constant; nothing
reads run output (CONTRACT 9's byte-identical-across-verdicts test proves
it structurally). INV-2: same four-route map, /methodology extended.
INV-3: VerdictCard/RobustnessPanel diffs empty; pointer is a sibling;
verdict color/motion scoping tests unmodified and green. INV-4: this task
touched zero backend files (the pending backend diff is the previous
entry's uncommitted work). INV-5: all 141 prior tests green unmodified —
the motion test needed only a documenting scope note, no assertion
changes. INV-6: tsc, eslint, `next build` clean.

**Counts:** frontend 141 → 147 (+3 CONTRACT 9 pointer tests, +3
/methodology content tests). Backend untouched at 251.

Next: pre-launch sweep — commit the accumulated honesty work, on-device
pass over /methodology and the results pointer (anchor scroll, mobile
reflow), then launch checklist.

## 2026-07-22 (2) — Pre-launch honesty fixes: reject stops at the gate, drop asset_class from UI

**What:** Two fixes from the limitations audit, both pre-gate (validation +
display), zero engine/robustness changes. (1) An IR carrying a non-null
`risk.stop_loss_pct`/`take_profit_pct` is now rejected DETERMINISTICALLY in
our code (`service.unsimulated_risk_reason`) — at translate time via the
existing "unsupported" surface, and again at the `/confirm` run path as a
400 — because the engine has never simulated a stop and the old renderer
was printing "Stop-loss: 5.0% below entry price" onto the confirmation
anyway. (2) `asset_class` no longer appears on any user-facing surface
(restatement line, "You specified" row, "I assumed" note): nothing in the
data or cost layer reads it, so displaying it implied crypto/futures
handling that doesn't exist. The schema keeps both fields; defaults still
fill them silently.

**Lesson — the most dangerous dishonesty isn't a wrong number, it's a
confirmation screen for a strategy that won't run.** The stop-loss bug had
three cooperating parts, each individually defensible: the schema accepted
`risk` (for a future engine), the renderer displayed it (faithfully
mirroring the IR), and the interpreter ignored it (it only handles
signals). No single file lied; the SYSTEM lied — "what you confirm is what
runs" held at every layer except the composition of layers. The fix
pattern: when a capability is display-deep, cut BOTH ends — reject the
input deterministically before the gate payload exists (never trusting the
LLM prompt's self-reject, since a stop-bearing IR is schema-valid and the
model has no reason to refuse it), AND delete the render path outright, so
a future caller can't resurrect the phantom by feeding the renderer
directly. The new renderer test hands it a stop-bearing IR on purpose —
bypassing the upstream rejection — to prove the display path is gone, not
merely guarded.

**Lesson — an "assumptions" list is user-facing copy, and announcing an
assumption about a field nothing reads is itself a false claim.** The
obvious Task-3 change was deleting `(equity)` from the restatement; the
non-obvious surface was the "I assumed" list, where
`asset.asset_class: equity — defaulted to equity` implied the choice
MATTERED (as if stating "crypto" would have changed the data source or
cost model — it wouldn't). The honest fix was upstream in `defaults.py`:
fill the field for the schema, record no Assumption — which then flowed
through renderer, fixtures, and AssumptionsView with zero frontend
component changes, because the frontend renders backend content verbatim
(the display corollary paying rent). The fixture-dump discipline
(`dump_translation_fixtures.py` + the backend tests pinning it) meant the
frontend picked up the new truth by regeneration, not hand-editing.

**Rejection-path reuse, precisely:** the stop rejection returns
`status="unsupported"` with a backend-emitted reason naming exactly what
was found ("a stop-loss", "a take-profit", or both) — the same payload
shape the LLM's own `{"unsupported": true}` sentinel produces, rendered by
the SAME existing `translate-flow-message` element. No new UI. The gate is
structurally unreachable for these: `atGate` requires `status === "ok"`
AND a restatement, and the rejection produces neither. Defence in depth at
`/confirm` (the only run path) closes the direct-POST hole for API users
who never saw the frontend at all.

**Tests rewritten (2), not deleted:**
(1) `test_unstated_asset_class_defaults_to_equity` → now asserts the field
is filled WITHOUT a user-facing assumption, with the why in the docstring.
(2) The translator's ≥5-assumptions comment updated (asset_class no longer
counts; period/source/exit/position×2/risk still clear the bar unchanged).
New coverage: 4 renderer/service rejection tests + 2 route tests + 2
never-renders tests (backend), 1 confirmation-surface absence test
(frontend).

**Invariants:** INV-1: `/confirm` still the sole run path — the new checks
only ADD a refusal there, and CONTRACT 5/6 tests run unmodified. INV-2:
the rejection reason is backend-emitted prose displayed verbatim by the
existing message element. INV-3: `git diff` on `backend/app/robustness`,
`engine`, `data` is empty; schema file untouched. INV-4: rejection runs in
`service.translate` before `render_confirmation` is ever called — a
stop-bearing IR has no restatement, hence no gate. INV-5: all prior tests
green; the two rewrites documented above and here. INV-6: tsc, eslint,
`next build` clean, same four-route map.

**Counts:** backend 242 → 251 collected (all passing locally; the 1
CI-deselected `live` marker case unchanged). Frontend 140 → 141. Fixtures
regenerated from real renderer output, diff is exactly the two removals.

Next: the limitations/glossary page — static chrome sourced from the
audit's findings (gross-ish costs, next-close fills, daily-only,
survivorship shape, IR expressiveness bounds), now accurate about stops
because the engine refuses what it can't simulate instead of displaying it.

## 2026-07-22 — Deflate: dedicated confirm view + results redesign (frontend only)

**What:** Two /backtest UX changes, no new routes, no backend changes.
(1) The gate no longer sits underneath the still-visible input textarea --
it now REPLACES it, with a new "back to edit" affordance to return. (2) The
results view earns real semantic color for the first time since Phase 7's
strict monochrome rule: robustness-check rows now carry a pass/warn/danger
icon and one-line read, driven entirely by backend-emitted fields, never a
frontend threshold. Performance-metric VALUES stay monochrome throughout --
only the tool's own judgments get color.

**Lesson -- a bug report's vocabulary and the codebase's vocabulary aren't
always the same thing, and only the code can arbitrate.** The task described
the bug as being in the reducer's `confirming` phase; the actual reducer has
a phase LITERALLY named `confirming` (the in-flight `/confirm` call), and a
separate `gate` phase (the review-before-run screen) -- and a PINNED,
EXISTING test already asserted `confirming`'s current spinner-only behavior
was correct. Implementing the fix against the literal phase name would have
broken that test outright; the actual bug (input and gate both mounted
simultaneously) lives in `gate`. Grepping for every existing assertion on
the input's testid before writing a line of code turned an assumption into
a verified fact. Once fixed, a second bug surfaced immediately: `atGate`'s
condition was "translation exists and we're not in results/loading" rather
than "phase is literally gate/correcting" -- so the new BACK_TO_EDIT action
(which deliberately keeps `translation` around, unlike RESET) left the gate
rendering even after returning to `idle`. Fixed by gating on the phase name
explicitly. Two bugs, same root cause: a boolean built from *proxies* for a
state (translation shape, loading-ness) instead of the state itself drifts
the moment a new transition is added that doesn't fit the old proxy's
assumptions.

**Lesson -- a payload's TypeScript types describe what IS there; they don't
promise what a design brief ASSUMES is there.** The requested layout was
verdict card -> monochrome headline-metric cards -> per-check rows. Reading
`robustness.py` directly (not just the TS mirror) found that the "full"
result has NO overall backtest metrics anywhere -- `BacktestMetrics` only
exists on the no-exit branch's `strategy_metrics`/`benchmark_metrics`;
`run_robustness`'s round-trip path never runs a plain full-window backtest
of its own. The headline-metric-cards layer was quietly dropped for "full"
results rather than filled with the nearest-looking numbers (walk-forward's
fold-aggregated Sharpe is NOT the same claim as "the strategy's real
performance," and rendering it as if it were would be exactly the kind of
subtle flattery this tool exists to catch). Parked, not built.

**Lesson -- an existing test can keep "passing" while quietly no longer
meaning anything.** `color-invariants.test.tsx` asserted RobustnessPanel
carries no saturated color at all. Giving check rows real color with a
NEW, distinctly-named token family (`--check-pass/--check-warn/--check-danger`,
lower-saturation than `--verdict-*` so the verdict card stays visually
dominant) meant that old assertion's regex (checking for named Tailwind
hues and the literal substring "verdict-") would keep returning green --
not because the invariant still held, but because it was never written to
catch a DIFFERENT color-token family. Left as-is, the test would have been
lying about what it verifies. Rewrote it to assert the new tokens
POSITIVELY appear where expected and stay absent everywhere else
(mirroring `verdict-*`'s own exclusivity check) rather than exploit the
technicality. The motion diff test (INV-4) needed the opposite treatment:
it only ever inspected wrapper-level classes, never each section's own
content, so it had ALWAYS tolerated VerdictCard's per-verdict color --
adding regime/sensitivity color inside a sibling section changed nothing
about what it was actually scoped to check. Documented both findings in
the tests themselves, not just here.

**Row-color rule, precisely:** sensitivity's `robustness_label` (a real
backend enum -- "fragile (sharp peak)" is the one value `verdict.py` itself
treats as flag-worthy) and regime's `marginal_flags[].confidence` /
`concentrated_regime` presence are the only two checks with a genuine
backend classification to color by. An overall LIKELY_OVERFIT verdict can
escalate an ALREADY-flagged row from warn to danger, but never invents a
flag on a row whose own data shows nothing (asserted directly: a clean
regime stays pass-tier even when `verdict="LIKELY_OVERFIT"` is passed).
Walk-forward and Deflated Sharpe Ratio have no backend-emitted per-check
status today -- both render a neutral, uncolored marker rather than a
fabricated pass. "Not computed" (zero tunable parameters is a real,
honestly-possible shape) renders muted grey with the generic fallback
string "Not computed for this strategy" -- never "N/A" for THIS new
element, though the pre-existing per-cell null-number formatter (pinned by
CONTRACT 4's fold-table assertions) keeps its own, separate "N/A"
convention untouched.

**Parked (backend, not done):** (1) `run_robustness`'s full-case branch has
no overall `BacktestMetrics` for the strategy as stated over the full
window -- needed before headline metric cards can honestly exist for
round-trip results. (2) Walk-forward and DSR need a backend-emitted
per-check status enum (mirroring sensitivity's `robustness_label`) before
their rows can carry real color instead of a neutral marker.

**Invariants:** INV-1 (gate integrity) untouched -- CONTRACT 5's tests
unmodified, `/confirm` remains the sole run path, and the literal
`confirming` phase's existing loading-view behavior (CONTRACT 12) is
provably unmodified (asserted directly in the new suite). INV-2 (display
corollary): every read/value is either a real backend field or one of five
static, verdict-blind captions, proven byte-identical across two different
real fixtures landing in the same severity bucket. INV-3: no new routes.
INV-4: zero backend files touched (`git diff --stat backend/` empty);
backend suite reran anyway, unchanged at 241/1-deselected. INV-5: entrance-
only CSS motion reused as-is, no new library. INV-6: all 122 prior tests
green unmodified; the one test whose OWN assertions needed rewriting
(the confirmed-bull-concentration monochrome check) was rewritten to state
the new rule explicitly, not silently weakened.

**Counts:** frontend 122 -> 140 (+18: 6 confirm-view, 11 check-severity,
1 new color-invariants case). tsc, eslint, `next build` clean, same route
map. Backend untouched at 241/1-deselected.

Next: on-device verification of the new confirm view and check-row colors;
then the two parked backend items above, which unlock real headline
metrics and full-color walk-forward/DSR rows.

## 2026-07-21 — Rename: NLSB → Deflate (user-facing only)

**What:** Ahead of a public launch at deflate.app, every string a site visitor (or a `/docs` visitor, or a GitHub visitor) could actually see now reads "Deflate": the nav wordmark, all three page `<title>`s, the OpenGraph title/description (newly added — none existed before), the methodology page's prose, the FastAPI OpenAPI title, and the README heading. Zero backend logic changes, zero new client-side judgments, zero git-history rewriting.

**Lesson — a rename sweep needs two greps, not one.** Grepping case-insensitively for "nlsb" across the repo surfaced 18 files, but the useful move was classifying every hit into three buckets BEFORE touching any of them: USER-FACING (a visitor could see it — rename), INTERNAL-KEEP (the `NLSB_*` env-var family, or code/tests/CI comments that read those exact strings — never rename, coordinating a live env-var rename across Railway/Vercel for zero user benefit is a real production-breakage risk), and INTERNAL-COSMETIC (code comments, historical LOG.md prose, a test's arbitrary example.com fixture domain, the literal `nlsb/` folder name in a README diagram — default to leaving these alone). Writing the table first is what turned up the one genuinely ambiguous case: `render.yaml`'s `name: nlsb-backend` isn't an `NLSB_*` env var, but renaming it changes the Render service's default URL, which is exactly the same cross-platform coordination risk the env-var rule exists to avoid. Flagged it and asked rather than guessing; the answer was to leave it, same treatment as the env namespace.

**Gotcha — the old acronym's *expansion* is also the old name.** The brief called out replacing spelled-out forms like "Natural Language Strategy Backtester," not just the letters "NLSB," and it was right to: the site `<title>`, the new OpenGraph title, and the README heading all read "NLSB — Natural Language Strategy Backtester" — acronym, then literally what the acronym stood for. Swapping only the acronym half produces "Deflate — Natural Language Strategy Backtester," a title that no longer parses (Deflate isn't an acronym for anything). Collapsed the whole construction to just "Deflate," matching the nav wordmark — the existing `description` field and README's next line already carry the tagline, so nothing needed inventing. A `replace_all` edit on that exact string also silently missed the top-level `metadata.title` because its indentation differed by two spaces from the `openGraph.title` copy I'd just added — a reminder that `replace_all` matches the literal string including whitespace, not "this text wherever it conceptually appears."

**Also added:** the frontend had no OpenGraph metadata at all before this — `openGraph.title`/`.description` are new in `app/layout.tsx`, reusing the existing title/description text verbatim (no invented marketing copy), so a shared link now previews as "Deflate" instead of falling back to a bare domain.

**Files changed:** `frontend/components/chrome/SiteNav.tsx`, `frontend/app/layout.tsx`, `frontend/app/backtest/page.tsx`, `frontend/app/methodology/page.tsx`, `frontend/tests/site/site-shell.test.tsx` (one assertion updated to match the renamed wordmark), `backend/app/main.py` (FastAPI `title=`), `README.md`.

**Invariants:** INV-1 (env namespace): every `NLSB_*` hit post-change greps byte-identical to the pre-change list — `abuse.py`, `main.py`'s `NLSB_ENV`, `conftest.py`, every test's `monkeypatch.setenv`, `render.yaml`'s service name, DEPLOY.md's env table, all untouched. INV-2/gate integrity: untouched, no state-machine files were in scope. INV-3: frontend 122/122 unchanged, backend 241 passed/1 deselected unchanged, tsc/eslint/`next build` clean. INV-4: no history rewrite; this entry is additive, older entries untouched.

**Counts:** frontend still 122, backend still 241/1-deselected — a pure rename touches no test count, only content. tsc, eslint, `next build` clean.

Next: DEPLOY.md's own heading ("Deploying NLSB") and the `nlsb-backend` Render service name were deliberately left as internal ops artifacts, not app-user-facing — worth a final look together with the actual domain/hosting cutover when that work happens, since that's the point at which the Render URL either gets fronted by a custom domain (making the old name invisible) or needs the coordinated rename this pass explicitly avoided.

## 2026-07-03 — Phase 11: website shell & motion pass (frontend only)

**What:** Turned "a page" into "a site": a landing page at `/`, the entire backtest flow moved intact to `/backtest`, methodology promoted to a real `/methodology` route, a shared nav+footer layout, and a small centralized motion system animating state transitions and loading states. Zero backend changes, zero feature-logic changes. (Phase 10's deployment work is untouched; CI runs the same suites.)

**Route map:** `/` (landing, static) · `/backtest` (the whole state machine: idle → translating → gate → confirming → results, correction loop, no-exit branch — dynamic, reads `?s=`) · `/methodology` (static). Gate and results deliberately have NO URLs of their own — gate integrity stays a state-machine invariant, so a results surface can never mount without `/confirm` having returned in-session. Landing chips carry their example to `/backtest?s=<encoded text>` (query param over client state: shareable, survives refresh, and lets the backtest page stay a server component reading `searchParams` — no client router hooks for tests to mock). Prefill fills the textarea only; nothing translates or runs without the user's own submit.

**Shared layout (`SiteShell` = `SiteNav` + `DisclaimerFooter`):** mounted once in `app/layout.tsx`, so nav and the disclaimer are on every route by construction. The footer MOVED out of `TranslateFlow` (where Phase 9 had it) into the shell — CONTRACT 11's assertions are byte-identical, only its render entry changed to wrap the flow in the real shell (the one allowed test-update category this phase). Nav is a static server component: wordmark in plain type, Backtest + Methodology links, monochrome throughout.

**Methodology:** copy extracted verbatim into `methodologyContent.ts`, shared by the in-flow expandable `MethodologyNote` (unchanged behavior, tests untouched) and the new full page — the two can't drift. The note gained a "Read the full methodology" link (the in-flow link the brief required); the page adds only layout and a CTA back to `/backtest`, no new claims, still no digits.

**Motion system (`lib/motion.ts` + keyframes in globals.css):** tokens — durations 150/200/260ms (fast/base/slow), easing `cubic-bezier(0.2, 0, 0, 1)`, stagger step 70ms; classes `enter` (fade), `enterSlide` (fade + 12px rise), `pulse` (soft opacity pulse for waiting text), `interactive` (hover/active transition base). Applied to: state-machine entrances (translating indicator, gate, confirming indicator, error banners), the results reveal (verdict card first, then panel/methodology/disclaimer at 0/70/140/210ms — **byte-identical classes and delays for every verdict**, pinned by a test that diffs the wrapper signature across all four verdict fixtures; motion is never a judgment channel), the Phase 9 stage indicator (pulse on the stage label, elapsed counter kept, still no fake percentages), and button/chip hovers (border/brightness only, never hue). **No framer-motion** — its exit animations (AnimatePresence) keep outgoing surfaces mounted during transition, which is exactly what the gate-integrity tests forbid; CSS entrance-only motion is sufficient and structurally safer. Entrances only, no exit animation: outgoing state unmounts the same instant the new state's data arrives, pinned by a fake-timers test asserting gate/results content is present with ZERO timer advancement after the API promise settles.

**Reduced motion (INV-5):** every keyframe class is `motion-safe:` gated (a unit test enforces the prefix on every animated token), so `prefers-reduced-motion` collapses all entrances/pulses to instant at the CSS layer. The one thing CSS variants can't express — a spinner has no sensible "static spin" — is handled by a `useReducedMotion` hook (own module, `lib/useReducedMotion.ts`) that swaps the spinner for a static glyph; jsdom matchMedia-mock tests cover both modes and prove timing LOGIC (stage thresholds, elapsed ticks) is identical under reduced motion.

**Gotchas:** (a) the motion module originally carried the hook, whose `"use client"` poisoned the pure tokens for server components — `next build` failed prerendering `/` ("Attempted to call staggerDelay() from the server"); fixed by splitting tokens (server-safe) from the hook (client). The suite alone did NOT catch this — jsdom has no server/client boundary — the build did; keep `next build` in the definition of green. (b) Repeated Phase 9's own lesson back at myself: a `landing-verdict-strip` testid false-flagged the `/verdict-/` token scan; renamed `landing-verdicts` — testids must never contain the literal token substring the scan bans. (c) `TranslateInputView`'s old "NLSB" h1 + product tagline became the landing page's job; the flow's header is now "Backtest a strategy" (frontend chrome copy, no test pinned the old text).

**Invariants:** INV-1/INV-2 green untouched; landing + methodology + nav covered by the same saturated-hue + `verdict-` token scans (verdict NAMES appear on landing/methodology in plain foreground type — color still exists only on the real verdict card). INV-3: gate-integrity tests pass with assertions unmodified. INV-4: stagger order is DOM position; `staggerDelay` has no content-dependent input by construction. INV-6: all 83 prior tests green (one render-entry update in CONTRACT 11, zero assertion changes).

**Counts:** frontend **83 → 108** (+25: 6 motion-token unit, 6 reduced-motion/immediacy/identical-stagger behavior, 13 site shell/landing/prefill/methodology-route). Backend untouched at 240. tsc, eslint, `next build` clean (route map above).

Next: the ~18s synchronous `/confirm` remains the open async/job-queue question. The landing page intentionally makes no performance or accuracy claims — copy stays a candidate for a future voice pass.

## 2026-07-02 — Phase 9: latency UX, trust layer, parked cleanup (frontend + copy)

**What:** Closed the gap between "works" and "feels trustworthy to a stranger" — staged progress, double-submit protection, a legal disclaimer, a methodology note, an unexpected-shape fallback, and the last two parked fixtures/items. Almost all frontend chrome; the only backend change is one new fixture builder + its pin. Corollary-safe: progress/disclaimer/methodology are facts about the product (frontend's own copy), not judgments about a strategy.

**Orientation measurement (the number this phase was told to capture, not act on):** a full real `/confirm` run on SPY 2015–2025 with the SMA-50/200 golden-cross example took **~18.1s wall-clock** (3.4s yfinance fetch + 14.7s `run_robustness` compute, 2516 bars). That ~15–20s wait is what the confirming-stage progress copy is sized for; it also frames the eventual sync-vs-async decision (deferred).

**Task 1 — staged progress (`ProgressIndicator`, chrome).** An indeterminate monochrome spinner + a steady label, and for the long confirm wait: elapsed-driven activity sub-labels ("Fetching price history…" → "Running the backtest…" → "Checking robustness…", ordered to match the backend sequence) plus a subtle "Ns elapsed" counter. Deliberately **no fake percentage / progress bar** — fabricated precision in an honesty tool is off-thesis; the test asserts no `%` and no `role="progressbar"`. Wired into `TranslateFlow`: `translating-indicator` mounts only while `phase==="translating"`, `confirming-indicator` only while `"confirming"`, each unmounting on transition.

**Task 2 — double-submit protection.** Buttons already disabled in-flight (visual); added structural guards at the top of each handler (`if (state.phase === "translating"/"correcting"/"confirming") return;`) so a programmatic/racing double-fire is a no-op too. Tests fire three rapid clicks against a hand-resolved deferred promise and assert the api was called exactly once.

**Task 3 — disclaimer (`DisclaimerFooter` on every screen; `ResultsDisclaimer` fuller block on results).** NLSB's own plain voice — hypothetical/backtested, not a prediction, not advice, data may contain errors — muted-gray, monochrome. Footer lives in `TranslateFlow`'s root so it renders in every phase; the fuller block renders on both the full and no-exit results surfaces.

**Task 4 — methodology note ("How to read a verdict", ~350 words).** An expandable `<details>` on the results surface with a heading for each of the four verdicts, what each of the four checks asks, and why a great-looking curve can still be overfit. Generic by construction — a test asserts it prints **no digits at all**, so it can never read as a specific run's numbers. Rendered only on the full-result surface (not no-exit, which has no verdict — this also keeps CONTRACT 3's "no verdict words on no-exit" green).

**Task 5 — unexpected-shape fallback in `RobustnessResultView`.** A minimal runtime shape check (only the fields this tree dereferences); on failure it renders a plain "These results couldn't be displayed — raw output below" with the JSON in a collapsed `<details>`, instead of throwing and blanking the page. Re-derives no judgment. Tests: truncated payload → fallback, no throw; valid result → never false-positives.

**Task 6 — PASS/SHAKY-with-flag fixture (was parked, now DONE).** Every prior full fixture carrying a bull-concentration flag was UNTESTABLE (their single bull-then-bear series gives the trend-follower ~0 OOS trades). Root-caused via the confirmed fixture's folds (all `oos_num_trades==0`). Added a `_multi_cycle_series` generator (repeated up/down ramps with net upward bias + noise) so the trend-follower crosses its SMA every cycle → real OOS trades → genuinely testable, while still sitting out down-ramps → more bull-concentrated than its benchmark. A short (period, cycles, seed, noise) search found `build_bull_concentration_with_verdict` — **SHAKY verdict + confirmed flag (excess 0.2023), OOS trades [4,3,2]**, deterministic. Pinned in `test_robustness_fixtures.py` (verdict ≠ UNTESTABLE, confirmed flag, every fold has OOS trades) and a frontend CONTRACT 8 asserts the verdict card and the confirmed flag render together.

**Invariants:** INV-1/INV-2 (color) untouched and green; extended the negative color scan to the five new chrome surfaces + the fallback. One gotcha: methodology verdict testids were first `methodology-verdict-PASS`, which the `verdict-` CSS-token scan false-flagged — renamed to `methodology-heading-*` so the invariant stays literal. INV-3 (gate integrity), INV-4 (no re-derived judgment — all new copy is chrome), INV-5 (existing tests unmodified; tsc/eslint/build clean) all hold.

**Judgment calls:** (a) methodology + disclaimer are corollary-safe chrome, so authored in-component. (b) The fixture search succeeded within minutes, so Task 6 landed rather than re-parking; the winning tuple is load-bearing (cliff-like space) and documented as such. (c) Double-submit is defended in two layers (disabled attribute + handler guard) rather than relying on the visual disabled state alone.

**Counts:** frontend **55 → 75** (+20: 7 chrome, +6 translation, +5 robustness fallback/methodology, +2 color-invariants — and CONTRACT 8 for the new fixture); backend **230 → 231** (+1 fixture pin). tsc, eslint, `next build` clean.

Next: the ~18s `/confirm` latency is now honestly surfaced but still synchronous — a real async/job-queue decision is the open follow-up. Not started: deployment configuration (explicitly out of scope this phase).

## 2026-07-01 — Phase 8B: adversarial hardening of the IR boundary (backend)

**What:** A red-team pass on the /confirm IR boundary before public exposure. /confirm accepts a *client-supplied* IR, so a hostile client can POST arbitrary JSON there without ever using the translator. Mostly new tests proving the boundary holds; four real holes were found and fixed. Security boundary unchanged: the LLM emits only validated IR JSON; no model output is ever exec'd/eval'd.

**Orientation (authoritative):** Entry points — `interpreter.validate_ir` (jsonschema against `strategy_ir.schema.json`, `additionalProperties:false` at every level) and the interpreter's independent whitelist (`_ALLOWED_INDICATOR_TYPES`/`_ALLOWED_OPERATORS`). /confirm re-validates via `service.confirm_robustness` → `validate_ir` before `run_robustness`; the single deepest run point is `vbt.Portfolio.from_signals`. Translator: `{"unsupported": true}` returns immediately (1 call); otherwise a bounded `range(1, MAX_RETRIES+1)` loop (MAX_RETRIES=3) that ends in a clean `status="error"`. Starting count: 193 backend tests.

**Holes found → fix → test (4):**
1. **Deep nesting → RecursionError → 500.** ~200 `all_of` levels blew Python's recursion limit *inside* jsonschema, before it could reject. Fix: `abuse.enforce_ir_complexity(ir)` — an *iterative* (never-recursive) pre-validation walk capping depth/node-count → clean 422. Test: `test_ir_fuzzing.py` deep_nesting_400/5000 + `test_ir_property.py::test_arbitrary_nesting_depth_never_recursion_errors` (0–5000).
2. **Period > data length → uncaught ValueError → 500.** A schema-valid huge period emptied the effective window; `psr_from_stats` then raised deep in robustness. Fix: `service._require_runnable_window` (after `validate_ir`) requires ≥`MIN_EFFECTIVE_BARS` (2) bars after warmup, else a clean `IRInterpreterError` (→400). Test: fuzz period_enormous/period_gt_data_length.
3. **No body-size cap on /confirm.** Phase 8A's text cap didn't cover /confirm's IR. Fix: a Content-Length check in the request middleware → 413 over `NLSB_MAX_BODY_BYTES` (default 65536). Test: fuzz oversized-body (a byte-huge but node-small IR).
4. **Non-finite numbers (NaN/Infinity) → 500.** A lenient client can send them (json.loads accepts them); jsonschema treats them as valid numbers, then `int(nan)` crashed in the sensitivity grid. Fix: folded a finiteness check into the same `enforce_ir_complexity` pass → clean 422. Test: `test_non_finite_numeric_operands_are_rejected_cleanly_before_the_engine` (nan/inf/-inf via raw body).

**Pinned decisions (behavior was acceptable, now nailed down):**
- **Unknown/extra keys are REJECTED, not stripped** — `additionalProperties:false` everywhere. At /confirm → 400; through the translator, extra keys fail validation, the retry loop re-asks, and after 3 attempts it returns the clean `error` path (`test_prompt_injection.py::test_extra_injection_key_is_rejected_by_schema_not_stripped`).
- **Instruction-looking strings are carried INERTLY as data** — a schema-valid string operand like `"IGNORE ALL PREVIOUS INSTRUCTIONS…"` passes /translate as opaque data (never executed); if placed where an operand is expected it is rejected at /confirm by the interpreter as unresolvable. Pinned by the injection probes + fuzz `operand_out_of_vocab`.
- Wrong top-level IR types (list/string/number/null) → pydantic 422 before any app code. Out-of-vocab indicator/operator names and lookalikes (`"RSI "`, `"rsi"`, `"__import__"`, `"eval"`, `"os.system"`, unicode homoglyphs, null bytes, RTL marks) → clean 400/422, engine never reached. Date-range abuse (end<start, far-future) → InsufficientDataError at the fetch boundary → 422.

**INV coverage:** INV-1 (no fuzz input reaches the engine without full validation) — the fuzz suite hard-spies `vbt.Portfolio.from_signals` and asserts it is never reached for any hostile case. INV-2 (the boundary's only failure modes are clean rejections) — hypothesis property tests (650+ generated inputs across free-form JSON and IR-shaped fuzz) assert the boundary raises only `jsonschema.ValidationError` or `HTTPException`, never RecursionError/KeyError/TypeError. INV-3 — all 193 prior tests pass unmodified.

**New env vars** (call-time reads; defaults): `NLSB_MAX_BODY_BYTES` (65536, request body cap), `NLSB_MAX_IR_DEPTH` (40), `NLSB_MAX_IR_NODES` (2000). New dep: `hypothesis==6.155.7`.

**Tests:** +37 (30 hostile-IR fuzz, 3 hypothesis property, 4 injection probes) → **230 backend**, all green. Plus a skip-by-default live-LLM smoke script (`tests/smoke_injection_live.py`, non-`test_*` filename so it's never auto-collected; `NLSB_RUN_LIVE_SMOKE=1` + a real key to run) with 5 classic NL injections. No frontend or deployment work.

## 2026-07-01 — Phase 8A: abuse protection & boundary hardening (backend)

**What:** Prepared the backend for public exposure without changing the security boundary — the LLM still emits only validated IR JSON, and no model-emitted code is ever executed. All new gating lives in `app/abuse.py`, composed in front of the existing route handlers in `app/main.py`; the translation/defaulting/rendering/backtest layers were not touched.

**Why / the five guards:**
1. **Per-IP rate limiting** (`slowapi`, in-memory `memory://` storage). `/translate` + `/correct` share one budget per IP (`shared_limit`, scope `"llm"`); `/confirm` has its own. Exceeding a limit → 429 with a plain-English `{"detail": ...}` body (the frontend already special-cases 429). A `RateLimitExceeded` handler renders that body.
2. **Daily LLM spend circuit breaker** — a process-level counter of LLM-calling *requests* per UTC day (`SpendBreaker`). Checked (no mutation) before the client is reachable; the budget is reserved (`record()`) only after the other gates pass, then the model is called. Tripped → 503 plain-English detail. **V1 limitation (documented):** the counter is in-memory and single-process — not shared across workers, resets on restart, and counts allowed *requests* (each may make up to `MAX_RETRIES` model calls), not individual API calls.
3. **Input caps** — NL text > 2000 chars → 422 before the model; `/confirm` ticker validated against `^[A-Z0-9.\-]{1,10}$` → 422 before yfinance.
4. **Failure boundaries** — LLM transport failures → 502 (real exception logged, never in the body); yfinance empty frame / `InsufficientDataError` → 422 naming the ticker, other fetch failures → 502; a global `Exception` handler is the final net → generic 500 JSON with no traceback (traceback to server log only). IR-validation errors at `/confirm` still → 400 (unchanged).
5. **Structured logging** — stdlib `logging` configured once at startup; an HTTP middleware logs method/path/status/duration per request. No secrets logged.

**INV-1 ordering** (rate limiter → spend breaker → size cap, then the client): enforced in each LLM route as decorator → `spend_breaker.check()` → `enforce_text_size()` → `spend_breaker.record()` → service call; proven by the cap/breaker tests (oversized text and a tripped breaker each reach the fake client zero / exactly-once times). **INV-2** (/confirm is the only path to a run and re-validates the IR) untouched, still pinned by the existing `test_api_routes.py` contract tests. **INV-3** (no traceback in any user-visible response) covered by the global-handler and 502 tests. **INV-4**: all 183 prior tests pass unmodified.

**New env vars** (all read at call time; production defaults): `NLSB_RATE_LIMIT_ENABLED` (`true`), `NLSB_RATE_LIMIT_LLM_PER_MIN` (`10`), `NLSB_RATE_LIMIT_LLM_PER_DAY` (`60`), `NLSB_RATE_LIMIT_CONFIRM_PER_MIN` (`20`), `NLSB_LLM_DAILY_CAP` (`200`), `NLSB_MAX_NL_CHARS` (`2000`), `NLSB_LOG_LEVEL` (`INFO`).

**Judgment calls:** (a) A new `conftest.py` turns the limiter/breaker *off* by default for the suite and resets their process-global state before each test — the two are shared mutable state that would otherwise throttle the suite's own same-IP requests and leak counts between cases; the dedicated tests opt back in via env. This isolates state without weakening any existing assertion. (b) The spend breaker counts allowed *requests* rather than individual model calls — the simplest honest V1 semantic that matches the brief's own test (one translate → second 503, fake called exactly once). (c) `slowapi` was chosen (per the brief's suggestion) and pinned with its transitive deps (`limits`, `Deprecated`, `wrapt`).

**Tests:** +10 in `tests/test_abuse_protection.py` (rate-limit 429 + shared budget + confirm limit; breaker short-circuit; oversized-text and malformed-ticker caps; LLM→502, empty-frame→clean 422, global→generic 500; middleware log record). Final count: **193 backend** (183 + 10), all green; frontend unchanged at 55. No frontend or deployment work performed.

## 2026-06-28 — Phase 7.2: gate layout (stated-vs-assumed as structure, not a list)

**Lesson first: a test that asserts "the warning has X and its neighbor doesn't" is a coin flip waiting for the neighbor to change, and this phase's own layout work flipped that coin within hours of Phase 7.1 landing.** 7.1's INV-A asserted `note.className).toBe("")` -- true the moment it was written, because note rows carried no classes of their own. This phase gave note rows their own row styling (`px-4 py-2.5`, a bordered/divided list) as part of making "I assumed" read as clean rows instead of a cramped `<ul>`, and that one assertion broke immediately -- not because the warning lost any prominence, but because the test's premise (the neighbor stays bare) was never something this phase owed it. Rewritten to assert ONLY the warning's own classes (`font-bold`, `border-l-4`, `p-6`, `text-foreground`, no muted tone, no saturated hue) -- positive claims about the element itself, which is exactly what the Phase 7.2 brief flagged as the right fix before this phase even started. The general lesson: a prominence test should describe the prominent element, not describe the absence of prominence everywhere else.

**Orientation: the stated-vs-assumed split was ALREADY fully backend-categorized before this phase touched anything** -- two independent mechanisms, both already correct. "You specified" is a structural slice of `renderer.py`'s `render_confirmation` restatement string (sliced by `parseRestatementSections` between the `"You specified:"` and next-header markers -- the backend decided what's in that block via `_stated_summary`, which only lists fields NOT present in `assumed_fields`). "I assumed" is driven entirely by the structured `assumptions[]` array's `severity` field, never re-derived from text. Frontend `AssumptionsView.tsx` already routed each correctly: it never moved an item between buckets, never read assumption text out of the restatement string. This phase's job was therefore pure layout -- give the existing, already-honored split actual visual structure -- confirmed by writing CONTRACT 6 (INV-A) to assert the categorization explicitly rather than trusting it: every `ORDINARY` fixture assumption's `field` appears under "I assumed" and NEVER under "You specified", and vice versa for stated items; the SEVERITY_WARNING item specifically renders inside `note-assumptions-section`, never floated outside it. 45 frontend / 183 backend confirmed green before any edit, matching the brief exactly -- no stale-count correction needed this time.

**One new structural unpacking, not a re-categorization: `splitBulletLines`.** The backend's "You specified" block was a single newline-joined string (`"- Ticker: SPY\n- Entry condition\n..."`) rendered into one `<pre>` blob -- visually a wall of text, not "clean rows." Splitting it on `\n- ` into individual `<li>` rows doesn't decide what's stated; the backend already decided that by what it put in the block. It only unpacks an existing list into rows, the same category of operation `parseRestatementSections` itself already does one level up (slicing the restatement into sections). No assumption text is parsed this way -- assumptions still come exclusively from the structured array, never from string-splitting restatement text.

**Bounded "You specified" casing cleanup, 7 fixed-label fragments recapitalized in `renderer.py`'s `_stated_summary`, 0 reworded:**
| Before | After |
|---|---|
| `ticker: {ticker}` | `Ticker: {ticker}` |
| `asset class: {class}` | `Asset class: {class}` |
| `entry condition` | `Entry condition` |
| `exit condition` | `Exit condition` |
| `position sizing` | `Position sizing` |
| `stop-loss` | `Stop-loss` |
| `take-profit` | `Take-profit` |

**One fragment deliberately left alone and flagged, per the brief's own escape hatch:** the per-indicator stated line (`f"{ind_id}: {ind['type']}({ind['params']['period']}) on {ind['source']}"`, e.g. `"rsi14: RSI(14) on close"`) leads with `ind_id`, a free-form identifier the translator chose -- not a fixed English word. Capitalizing it (`"Rsi14: ..."`) would alter the identifier's actual text, not just its case, which is exactly the "can't capitalize without rewording" case the brief says to leave untouched rather than force. Also left alone, consistent with Phase 7.1's own precedent: the three lowercase parenthetical fallback fragments in `renderer.py` (`"(nothing beyond the basic strategy structure)"` etc.) -- an established, deliberate fragment style across all three, not informal copy that drifted.

**One backend test and two frontend tests needed casing-only updates** (`test_translation_renderer.py`'s `"exit condition" in you_specified` → `"Exit condition"`; the integration test's and the contract test's literal `"ticker: SPY"`/`"entry condition"`/`"exit condition"` assertions → capitalized). Both translation fixtures (`ordinary_assumptions.json`, `no_exit_warning.json`) regenerated via `dump_translation_fixtures.py`, never hand-edited, same discipline as 7.1.

**Layout: two clearly-separated sections inside `AssumptionsView`** ("You specified" / "I assumed", each with a bold header + a muted one-line description authored as new frontend chrome, not backend copy), a `role="separator"` rule between them, stated items as a bordered/divided row list, and an explicit empty state ("No assumptions needed — you specified everything.") for the all-stated case that previously had no real edge-state copy at all. The SEVERITY_WARNING stays exactly where Phase 7.1 put it prominence-wise, but now renders structurally INSIDE `note-assumptions-section` (verified by `toContainElement`) rather than in its own sibling section -- it's an assumption, the most important one, and the layout now says so. `TranslateFlow.tsx` got a gate-level framing header ("Review before you run it" + a "nothing has run yet" line) and a bottom "Ready to run this backtest?" block that puts `ConfirmGate` (the sole path to a run, untouched) and the correction path ("Not right? Correct it instead." + `CorrectionBox`) under one visible, ordered structure -- the commit action and its back-out are both visible before the user commits, exactly as asked.

**Gate integrity untouched, verified, not assumed.** No code in `TranslateFlow`'s reducer changed; `CONFIRM_SUCCESS`/`phase === "results"` gating is byte-identical to Phase 6/7. The full integration suite (`tests/integration/translate-flow.test.tsx`, including the delayed-`/confirm` "clicked but not yet resolved" test) passed unmodified except for the one casing-only literal noted above -- proof the restructuring touched layout, not the state machine.

**47 frontend tests** (45 existing + 2 new CONTRACT 6/INV-A categorization tests in `contracts.test.tsx`; the existing Phase 7.1 prominence test was hardened in place, not added to, so the net new count is +2). **183 backend tests** (1 literal updated, casing-only). `tsc --noEmit`, `eslint`, `next build` all clean.

Next: no open items from this phase. The recurring deferred items remain deferred: the unexpected-shape fallback in `RobustnessResultView`, a PASS/SHAKY fixture that also fires bull-concentration, the dropped volatility-axis marginal check, and a real browser smoke run with an actual `ANTHROPIC_API_KEY`.

## 2026-06-28 — Phase 7.1: warning prominence, copy polish, entry page

**Lesson first: "the SEVERITY_WARNING box reads as flat gray text" was a real visual complaint even though the component already had its own structurally-distinct render path (`role="alert"`, its own testid, a filled `bg-muted` panel) -- structural distinctness and visual prominence are different claims, and Phase 7 had only secured the first.** The warning's headline was `text-xs font-semibold` -- smaller than the body text around it -- and its border was a uniform `border-2 border-foreground/40` indistinguishable in weight from an ordinary card border. Structurally unmistakable to a test; visually unremarkable to an eye skimming the page. Fixed by making the headline `text-base font-bold`, the body `text-base font-medium text-foreground` (up from inherited muted), padding `p-6`, and swapping the uniform border for a `border-l-4 border-foreground` rule -- a "stop and read this" mark, not a thicker version of the same box. No hue anywhere in the diff; INV-2 (`tests/visual/color-invariants.test.tsx`) still passes unmodified, and a new INV-A test in the same file pins the structural gap (bold vs. not, `border-l-4`+`p-6` vs. no border/padding at all on a note row, full vs. muted foreground) so the distinction can't quietly erode back to "just another box" in a future styling pass.

**Orientation corrected the brief on nothing this time** (44 frontend / 183 backend both confirmed exactly as stated) but did surface a routing question the brief anticipated: every displayed assumption/warning reason string is authored in `app/translation/defaults.py` (the `Assumption.reason` field) and reaches the screen completely unmodified through `renderer.py`'s `render_confirmation` (string interpolation only, no rewording) and then `AssumptionsView.tsx` (renders `assumption.reason` verbatim, confirmed by grep -- no `.toUpperCase`/`.charAt`/text-transform anywhere in the component). That makes `defaults.py` the single source of truth for every reason string's casing; fixing it there fixes both the JSON `assumptions[].reason` field AND the renderer's plain-text restatement in one edit, with no duplicate string to drift out of sync.

**9 reason strings recased, 0 reworded** (sentence-case + a closing period, since each renders as either a whole bullet line on its own -- the SEVERITY_WARNING case -- or as the tail of a `field: value — reason` line, and both read as complete sentences once capitalized):
- `asset class not stated; defaulted to equity` -> `Asset class not stated; defaulted to equity.`
- `source price field for {id} not stated; defaulted to close` -> `Source price field for {id} not stated; defaulted to close.`
- `period for {type} indicator {id} not stated; defaulted to {n}` -> `Period for {type} indicator {id} not stated; defaulted to {n}.`
- `no exit condition stated; ... rather than a round-trip strategy` -> `No exit condition stated; ... rather than a round-trip strategy.` (the SEVERITY_WARNING reason)
- `position direction not stated; defaulted to long (v1 is long-only)` -> `Position direction not stated; defaulted to long (v1 is long-only).`
- `position sizing not stated; defaulted to full capital per trade` -> `Position sizing not stated; defaulted to full capital per trade.`
- `no stop-loss/take-profit stated; defaulted to none` -> `No stop-loss/take-profit stated; defaulted to none.`
- `no stop-loss stated; defaulted to none` -> `No stop-loss stated; defaulted to none.`
- `no take-profit stated; defaulted to none` -> `No take-profit stated; defaulted to none.`

No ticker/acronym ever appears inside these reason strings (RSI/SMA/EMA only appear via `{ind_type}` f-string interpolation from the IR itself, untouched). Deliberately left alone: the parenthetical fragments in `renderer.py` (`(nothing beyond the basic strategy structure)`, `(nothing routine — see the heads-up above)`, `(nothing — you specified every field)`) and the `_stated_summary` "You specified" list items (`ticker: SPY`, `entry condition`, `stop-loss`, ...) -- these are deliberately lowercase fragment style, not assumption/warning prose, and the brief scoped this pass to "displayed assumption/warning copy" specifically; flagging here rather than quietly expanding scope.

**Backend tests needed zero changes** -- nothing in `test_translation_defaults.py`/`test_translation_renderer.py`/`test_translation_fixtures.py` asserts a reason string by exact equality; all are substring/membership checks (`"buy-and-hold" in text`, etc.) that survive casing changes untouched. The two real fixtures consumed by frontend contract tests (`ordinary_assumptions.json`, `no_exit_warning.json`) were regenerated by re-running `scripts/dump_translation_fixtures.py` against the new strings -- never hand-edited -- keeping the "never hand-author the text the frontend tests against" discipline 5a/5b established. Frontend contract tests needed zero changes either, since they compare against `a.reason` dynamically (`textContent.includes(a.reason)`), not a hardcoded literal.

**Entry page (`TranslateInputView.tsx`) was the one component with real design latitude this phase** -- no judgment renders there, so no corollary constraint. Added an `<h1>NLSB</h1>` plus a one-line honesty-stance framing sentence, a `<label>` for the textarea, a larger `rows={6}` textarea with a concrete example placeholder (the prior placeholder's example text now lives as the placeholder verbatim, not in a separate "e.g." clause), and a heavier primary button (`px-5 py-2.5 font-semibold`, up from `px-4 py-2 font-medium`). The outer `data-testid="translate-input-view"` moved from the `<form>` element to a wrapping `<div>` so the header could sit above the form -- confirmed safe by grepping every test that touches this testid (`color-invariants.test.tsx`, `translate-flow.test.tsx`): none depends on it being a `<form>` specifically, only on `nl-input`/`translate-submit` existing inside it.

**45 frontend tests** (44 existing + 1 new INV-A prominence test). **183 backend tests, unchanged** (copy edits only, no asserted-literal changes needed). `tsc --noEmit`, `eslint`, and `next build` all clean.

Next: no open items from this phase. The recurring deferred items remain deferred: the unexpected-shape fallback in `RobustnessResultView`, a PASS/SHAKY fixture that also fires bull-concentration, the dropped volatility-axis marginal check, and a real browser smoke run with an actual `ANTHROPIC_API_KEY`.

## 2026-06-27 — Phase 7: visual design pass (the honesty thesis, made visible)

**Lesson first: a discipline enforced in component logic doesn't automatically survive contact with a stylesheet, because color is a second, parallel channel a corollary written for DOM structure and prop shapes never named.** Every prior phase enforced "the frontend is a pure renderer" at the level of what gets rendered -- no client-side verdict computation, no synthesized text, no reachable result without a confirm. None of that discipline says anything about what COLOR something is rendered in, and it turns out the codebase had quietly been making exactly the kind of client-side judgment call the corollary forbids, just in CSS instead of JavaScript: the confirmed-vs-provisional bull-concentration flag was amber, the SEVERITY_WARNING box was amber, the confirm button was green, the no-exit comparison card was blue. None of those colors came from the backend. Every one of them was this codebase deciding, on its own, that something was alarming/safe/distinct enough to deserve a hue -- the same category of error as coloring a 0.94 DSR red, just smaller and easier to miss because nobody was looking for it in a `className` string.

**Orientation found the brief's "shadcn/ui for primitives" claim was simply wrong** -- there is no `components.json`, no `components/ui`, no CVA/Radix/lucide dependency anywhere in this repo; `app/globals.css` was still the unmodified `create-next-app` scaffold (light-by-default, dark only behind a `prefers-color-scheme` media query, no design tokens at all). Treated literally, "define the shadcn theme tokens" doesn't require installing shadcn's component library -- it requires the CSS variable NAMING CONVENTION shadcn uses (`--background`, `--card`, `--muted-foreground`, etc.) wired into Tailwind v4's CSS-first `@theme inline` block, which is what got built; no new component-library dependency was added, since that would have been a far larger, riskier change than "styling only" was asking for. The verdict enum (`PASS`/`SHAKY`/`LIKELY_OVERFIT`/`UNTESTABLE`) and `VerdictCard`'s static `Record<Verdict, ...>` lookup matched the brief exactly, confirmed by reading `verdict.py` and `VerdictCard.tsx` directly -- that structure was sound and is what the new palette was built ONTO, not around.

**The full color-violation inventory, found by grepping every component for a saturated Tailwind hue before writing a single new style:** `VerdictCard.tsx` (legitimate -- retoned to the new `verdict-*` tokens, same static-lookup shape); `RobustnessPanel.tsx`'s bull-concentration flag (amber, confirmed-vs-provisional -- a per-check judgment color the brief names by category); `AssumptionsView.tsx`'s SEVERITY_WARNING box (amber); `ConfirmGate.tsx`'s submit button (emerald); `BuyHoldComparison.tsx`'s card border (sky blue); `TranslateFlow.tsx`'s three error banners (red). All five non-`VerdictCard` violations are now monochrome, carrying their distinctness through WEIGHT and PROMINENCE instead of hue -- a confirmed flag is bold near-white text where a provisional one is muted gray, the warning box is a heavier border and a filled `bg-muted` panel rather than an amber tint, an error banner is the same treatment. The structural distinctness (`role="alert"`, distinct testids) that made these elements unmistakable before is completely unchanged; only their color channel was disarmed.

**The verdict palette itself is four new CSS variables (`--verdict-pass`/`-shaky`/`-overfit`/`-untestable`) referenced by exactly one file.** `UNTESTABLE` got its own neutral token rather than reusing or interpolating toward any of the other three, so there is no code path where "untestable" could visually drift toward "probably bad" (amber-ish) or "probably fine" (green-ish) -- it's a fourth, independent color, not a blend. One implementation trap worth recording: the first draft built each verdict's Tailwind classes via template-literal interpolation (`` `border-l-${accent}` ``), which silently produces NO CSS at all, because Tailwind's compiler only generates utilities it can find as a complete literal string in source -- a dynamically-assembled class name is invisible to it. Fixed by storing each verdict's three full class strings (border/tint/text) as complete literals in the lookup object, which is also a strictly STRONGER form of the same static-lookup discipline the brief asked for: there is now nothing left for any code path to compute, not even string concatenation.

**INV-1 (12 tests, `tests/visual/color-invariants.test.tsx`) verifies the accent-selection mechanism itself**, not just that the four colors look different: each of the four enum strings maps to its own `verdict-*` token and to no numbered Tailwind shade; PASS/SHAKY/LIKELY_OVERFIT map to three DIFFERENT tokens from each other; UNTESTABLE's token is checked by name to be `verdict-untestable`, explicitly NOT `verdict-pass`/`-shaky`/`-overfit`; and UNTESTABLE's card renders with the identical size/structure classes as PASS's, modulo only the color token itself, pinning the "full prominence, never demoted" contract at the className level, not just the component-identity level 5b's tests already covered. **INV-2** renders every non-`VerdictCard` component against the fixture that would have triggered its OLD color under the prior code (the confirmed bull-concentration fixture, the SEVERITY_WARNING fixture, the no-exit fixture, a forced `/translate` failure) and regex-scans the rendered HTML for any saturated-hue-plus-numbered-shade utility class, or any `verdict-` token -- finding none. Building this test caught a self-inflicted near-miss: the regex's own doc-comment, written as literal example class strings (`` `text-amber-700` ``, etc.), got picked up by Tailwind's content scanner and generated real (if unreachable) dead CSS for the very hues this phase exists to ban from the bundle -- fixed by describing them as concatenation in prose instead of spelling out the literal class strings, confirmed clean by grepping the actual built `.next` output afterward.

**3 of 4d.1's CONTRACT 5 tests needed updating, not preserving** -- they asserted the literal removed amber/zinc class names (`text-amber-700`, `text-zinc-400`) as part of proving the confirmed/provisional render distinction existed. The underlying contract (confirmed renders bolder than provisional, the suffix appears) is completely intact under the new monochrome tokens (`text-foreground`/`text-muted-foreground`); only the specific CSS class strings the assertions checked for changed, which is exactly the kind of test update this phase's own instructions anticipated as in-bounds, distinct from changing DOM structure or ordering (which nothing in this phase touched).

**No DOM structure changed.** The one structural-looking edit -- wrapping the gate's `AssumptionsView`/`CorrectionBox`/`ConfirmGate` trio in a `<div className="space-y-8">` instead of a bare React fragment, purely for spacing -- adds a wrapper element with no testid, which doesn't affect `getByTestId` lookups or `compareDocumentPosition`-based ordering assertions; verified by running the full existing suite rather than assuming it. Nothing else required a DOM change to style.

**44 frontend tests** (32 existing, retuned where the color token itself was the assertion, plus 12 new INV-1/INV-2 tests). **183 backend tests, unchanged** -- no backend file touched this phase. `tsc --noEmit`, `eslint`, and `next build` all clean; the built CSS was inspected directly (not just trusted) to confirm all four verdict tokens generate real `hsl()`/`color-mix()` rules and that zero saturated-hue utility classes survive anywhere in the production bundle.

Next: no open visual-pass items -- this phase's scope (tokens, monochrome chassis, verdict card, no-exit branch) is complete. The recurring deferred items remain deferred: the unexpected-shape fallback in `RobustnessResultView`, a PASS/SHAKY fixture that also fires bull-concentration, the dropped volatility-axis marginal check, and a real browser smoke run with an actual `ANTHROPIC_API_KEY` (still owed from Phase 6).

## 2026-06-26 — Phase 6: integration page (live input -> gate -> results, end to end)

**Lesson first: components that pass in isolation and a system that holds together are two different claims, and the gap between them is exactly where a gate stops being a component contract and becomes a state-machine invariant.** 5b's `TranslateFlow` already enforced "no result without an explicit confirm" -- but it proved that by injecting a fake `api` object directly as a prop, which sidesteps the actual question this phase exists to answer: does the invariant survive once `/translate`/`/correct`/`/confirm` are real HTTP round-trips, with real latency, real failure modes, and a real (if relative-path, same-origin) network boundary in between? A fake object resolves synchronously-ish and never disagrees with its own contract. A real fetch can fail, can be slow, can return a shape nobody hand-typed -- and the gate has to hold through all of that or it was never really a gate, just a well-behaved mock agreeing with itself.

**Orientation findings, against the real code, not the brief's assumptions.** (a) `app/page.tsx` already existed and already rendered `TranslateFlow` with no fake injected -- meaning the "page that wires these into a live flow" was already ~90% built in 5b, not a fresh build. What was missing relative to THIS phase's explicit requirements: no loading state during any of the three network calls (the user got no feedback that anything was in flight), a single shared `error` string with no way to tell which action failed, and -- the part 5b's own tests couldn't have caught -- zero tests exercising the real `httpTranslationApi`/fetch path, since every existing test injected a fake `api` prop. (b) Comparing every route's pydantic response model against every component's expected TypeScript prop shape, field by field, turned up ZERO mismatches: `TranslationPayload`, `Assumption`, and `RobustnessResult` on the frontend mirror `main.py`'s pydantic models and `RESULT_KEYS` exactly, because 5a/5b were built in lockstep with the backend from the start. What WASN'T a shape problem but absolutely would have broken the live flow: `lib/translation/api.ts` posts to relative paths (`/translate`, `/correct`, `/confirm`) with no configured destination, and neither a Next.js rewrite nor backend CORS existed -- in a real browser those requests would have 404'd against the Next.js dev server itself, never reaching FastAPI at all. (c) `/correct`'s contract, read directly from `service.py`: `correct()` is, literally, `translate()` called again with the correction folded into the prompt -- it returns a FULL `TranslationResponse`, the exact same shape `/translate` returns, never a targeted patch to the existing assumptions list. `TranslateFlow` already did the right thing here (`setTranslation(response)`, full replacement) without anyone having stated the contract this explicitly before. (d) `NoExitResult` IS reachable through the real `/confirm` route, not just constructed in tests: `confirm_robustness` branches on `is_no_exit_strategy(assumptions)` before running any round-trip machinery, and `assumptions` is round-tripped verbatim from whatever `/translate`/`/correct` actually produced -- so a real LLM translating a strategy with no stated exit rule would hit this path for real, no test scaffolding required.

**Zero adapters needed -- a real finding, not an absence of one.** [2] asked for adapters only where shapes mismatched; none did, anywhere, so this phase wrote no adapter module. The gap that DID need fixing wasn't a shape problem at all: `next.config.ts` now rewrites the three routes to `http://127.0.0.1:8000` (overridable via `BACKEND_ORIGIN`), server-side, so the browser only ever talks to one origin and the backend needs no CORS config -- wiring, not route logic, on either side of that line.

**The state machine itself: `TranslateFlow` rewritten onto `useReducer`** with an explicit `phase` (`idle` / `translating` / `gate` / `correcting` / `confirming` / `results`) and a tagged `error: {action, message} | null` instead of one undifferentiated string. The render gate changed from "show results if `result` is truthy" to "show results only if `phase === \"results\"\"` -- a deliberately stronger condition, since a stale `result` object surviving a subsequent correction could otherwise leak through if the phase logic ever drifted from the data. `CONFIRM_ERROR` and `CORRECT_ERROR` both route back to `"gate"`, never clearing the existing translation, so a failed retry doesn't cost the user their place. All three existing input components (`TranslateInputView`, `ConfirmGate`) already had unused `disabled` props sitting there from 5b/5a -- this phase was the first thing to actually wire them up.

**MSW installed (no existing fetch-mocking equivalent in this repo) and wired into `vitest.setup.ts`** with `onUnhandledRequest: "error"`, specifically so a test that accidentally lets a real network call through (e.g. a gate-integrity test that should never reach `/confirm`) fails loudly instead of silently passing or hanging. The 9 new integration tests in `tests/integration/translate-flow.test.tsx` render the REAL `TranslateFlow` with its REAL default `api` -- no fake injected anywhere in this file -- against MSW-stubbed routes, reusing real backend fixtures (`ordinary_assumptions.json`, `no_exit_warning.json`, `pass.json`, `no_exit.json`) as response bodies wherever one already existed. The gate-integrity test needed a deliberately delayed `/confirm` response (via `msw`'s `delay()`) to even have a "clicked but not yet resolved" window worth asserting against -- an instantly-resolving mock settles before the very next line of test code can check anything, which would have made that assertion a coin flip dressed up as a contract.

**The manual smoke test hit a real, pre-existing gap: no `ANTHROPIC_API_KEY` is configured anywhere in this repo (no `.env` file exists), and none was supplied for this phase.** Asked directly, the call was to skip the real-LLM step rather than supply one. What was verified instead, with both servers actually running: the backend's `/health` responds; the Next.js rewrite correctly proxies all three routes to FastAPI (confirmed by diffing the request log -- a `curl` through `localhost:3000/translate` and a `curl` straight to `127.0.0.1:8000/translate` produced the identical traceback, the missing-API-key `TypeError` from the Anthropic SDK, proving the proxy reached the real backend rather than 404ing against Next.js); `/correct` and `/confirm` rewrites likewise return real FastAPI 422 validation errors, not Next 404s; and the root page serves the real `TranslateFlow` markup (`nl-input`, `translate-submit`, etc.) verbatim. What was NOT verified: an actual LLM translation, gate, confirm, and rendered verdict in a browser, since that requires a real API key this environment doesn't have. That's a real gap in this phase's "done," not a rounding error -- noted below.

**One unrelated fix, found and corrected with explicit sign-off first.** `backend/tests/test_ir.py` had an uncommitted, accidental line-split (`assert with_` / `unused_result.num_trades == ...`) predating this session -- not something this phase's work touched or caused. Asked before fixing; the trivial one-line rejoin was approved and applied, restoring the backend suite to fully green rather than reporting a phantom regression that was never this phase's to begin with.

**9 new frontend integration tests** (`tests/integration/translate-flow.test.tsx`, covering gate integrity, the happy path, the correction loop, the no-exit branch, all three error states, and the SEVERITY_WARNING survival check), plus the `TranslateFlow` rewrite and the `next.config.ts` rewrite. Frontend: 23 -> 32. Backend: 183 -> 183 (no robustness/route logic touched; the one fix was an unrelated pre-existing typo). `tsc --noEmit`, `eslint`, and `next build` all clean.

Next: a real end-to-end browser run with an actual `ANTHROPIC_API_KEY` is still owed -- everything up to the LLM call itself is now verified live (server, proxy, error surfacing, page markup), but no one has watched a real plain-English strategy survive translate -> gate -> confirm -> verdict in an actual browser yet. The unexpected-shape fallback in `RobustnessResultView` remains deferred (orientation found no shape the live route can produce that the fixtures don't already cover, so it was never promoted into scope this phase), and the parked items from 4d/4d.1 (volatility-axis marginal check, a PASS/SHAKY fixture that also fires bull-concentration) are still parked.

## 2026-06-25 — Phase 4d.1: frontend coverage for the now-live bull-concentration flag

**Lesson first: proving a signal FIRES and proving it RENDERS are two different claims, and 4d only made the first one.** The whole point of reworking the marginal-trend flag to be benchmark-relative was to make it a usable, displayed warning -- but 4d shipped a backend integration test that proved `_detect_bull_concentration` could fire, then committed a frontend render branch that no fixture in the repo ever triggered. All five orchestrator fixtures had `marginal_flags: []` before and after 4d. That's not a contradiction in 4d's own report -- it explicitly said as much -- but it left a render path with a TypeScript type, a className branch, and zero evidence it produces the pixels anyone described. A flag that fires in a unit test and never renders in an integration test is, from the user's chair, indistinguishable from a flag that doesn't exist.

**Closing the gap meant getting a REAL fixture to fire, not hand-authoring one.** The display-side corollary this project holds to (the frontend renders backend-computed values only) cuts against synthesizing a `marginal_flags` payload directly in a test fixture -- that would pin the frontend to a shape the backend might never actually emit. 4d's integration test proved the mechanism using a monkeypatched `run_ir_backtest_returns` (synthetic returns assigned directly: +1% on every bull bar, -1% on every bear bar), which is exactly right for unit-testing `_detect_bull_concentration` in isolation but cannot be reused for a fixture, since `dump_robustness_fixtures.py` has to run the REAL, unmocked orchestrator end to end. The translation: a trend-following strategy (long while price is above its own 200-day SMA, flat otherwise -- using the SAME period as `regime.py`'s own `MA_PERIOD`) earns close to zero real gains during bear-labeled bars, while a same-window buy-and-hold benchmark stays exposed throughout and keeps collecting whatever up-day noise the bear segment has. Whether that produces an actual flag-worthy excess turned out to be less of a dial than a cliff: a strategy's entries/exits are discrete crossing events, so excess jumps abruptly between ~0 and 0.3+ as the bear segment's noise parameter crosses certain values, rather than sliding smoothly. Landing in the narrow 0.15-0.20 "provisional" band specifically required a small grid search over (seed, bear_noise) pairs run against the fast `run_regime_analysis` path alone before confirming the winning pair through the full `run_robustness` orchestrator -- found at seed=174, bear_noise=1.84, excess=0.1635. The confirmed fixture (seed=4, bear_noise=1.85) landed at excess=0.3012, comfortably past the 0.20 confirmed threshold, on the first informal search pass.

**Both fixtures are pinned backend-side, the same as every other orchestrator fixture in this repo.** `test_robustness_fixtures.py` now asserts `build_bull_concentration_confirmed()`'s flag has `confidence == "confirmed"` and `excess > MARGINAL_BULL_EXCESS_CONFIRMED_THRESHOLD`, and the provisional builder's flag lands strictly inside the band -- so a future threshold change or an incautious edit to the series construction fails the backend suite instead of silently leaving a frontend contract test exercising a fixture that no longer demonstrates what its name claims.

**Four frontend contract tests, the fourth doing the real proving.** The first three assert the documented render rule against the two real fixtures: confirmed renders full-prominence (`text-amber-700`, no "(provisional)" suffix) and provisional renders muted (`text-zinc-400`, with the suffix), and the excess margin displays as `"+X.X pp vs benchmark"` matching the fixture's `excess` field through formatting only (multiply by 100, `toFixed(1)`) -- no independent recomputation. The fourth is the one that actually closes the gap the display-side corollary exists to catch: take the confirmed fixture (excess 0.3012, well past the confirmed threshold) and override ONLY its `confidence` field to `"provisional"`, a controlled mutation of a real fixture rather than a fabricated payload, documented as such inline. If `RobustnessPanel` were silently re-deriving confidence from excess instead of trusting the backend's field, this mutation would have no visible effect -- the excess value still says "confirmed". Asserting the muted/provisional render wins anyway is the proof that the component reads the field and never re-thresholds.

**4 new backend tests** (2 fixture builders in `dump_robustness_fixtures.py` -- `build_bull_concentration_confirmed`/`build_bull_concentration_provisional` -- plus their 2 pinning tests in `test_robustness_fixtures.py`). Backend: 181 -> 183. **4 new frontend contract tests** against the real fixtures (CONTRACT 5 in `contracts.test.tsx`). Frontend: 19 -> 23. `tsc --noEmit`, `eslint`, and `next build` all clean.

Next: the two new bull-concentration fixtures both happen to land on UNTESTABLE verdicts (an artifact of the trend-following strategy's sparse, lumpy trade count on these particular series, not something this phase optimized for) -- a future phase wanting a PASS- or SHAKY-verdict fixture that ALSO fires the bull-concentration flag would need its own search. The volatility-axis marginal check remains parked (dropped in 4d, not rebuilt), and the structured field editor and `RobustnessResultView`'s unexpected-shape fallback remain deferred.

## 2026-06-25 — Phase 4d: marginal bull-concentration rework (benchmark-relative excess)

**Lesson first: a threshold that looks principled in isolation can be pure noise if the thing you're comparing it against clears it just as easily.** The old marginal-trend check flagged any strategy where 80%+ of gains-only returns landed in bull-labeled bars (price above its own 200-day MA) -- and on this codebase's own definition of "bull," the market itself parks the overwhelming majority of its gains there, so a flag meant to catch "this only worked in the 2020-21 bull run" was actually catching "this is a long-only strategy," full stop. An absolute share is base-rate-blind: it can't distinguish a strategy that's bull-dependent from a strategy that's exactly as bull-dependent as buying and holding the thing it trades. The fix isn't a different absolute number, it's a different question -- not "how much of this strategy's gains are bull-regime gains" but "how much MORE of its gains are bull-regime gains than a same-window buy-and-hold benchmark's are."

**What changed in `regime.py`.** `_detect_bull_concentration` (replacing `_detect_marginal_concentration`) now derives a benchmark internally from the same `price_data` already passed in -- `price_data["Close"].pct_change()` computed on the FULL series and reindexed to the effective window afterward, not computed on an already-trimmed series, so the first eff-window bar gets a real day-over-day return instead of a spurious NaN. The benchmark is never accepted as a caller-supplied parameter precisely so nothing upstream can hand it a flattering number; it's recomputed from the same bull/bear labels (`trend_labels`) already used for the strategy's own attribution, so the comparison isn't confounded by two different regime definitions. `excess = strategy_bull_share - benchmark_bull_share`; the flag fires only past `MARGINAL_BULL_EXCESS_THRESHOLD = 0.15`, with a `MARGINAL_BULL_EXCESS_CONFIRMED_THRESHOLD = 0.20` band above which confidence is "confirmed" rather than "provisional" -- an explicit acknowledgment that `excess` is the difference of two noisy share estimates and a strategy landing just past the bare threshold deserves a hedge, not a flat accusation.

**Judgment call: the volatility-axis marginal check is gone, not just reshaped.** The old mechanism ran identically over BOTH the trend axis (bull/bear) and the volatility axis (high/low), emitting a `MarginalConcentration` dataclass per axis. Reading `tests/test_regime.py` before touching anything showed the volatility-axis path was live code nobody had ever exercised -- no test, no fixture, no mention in this log's prior provisional note, which was specifically about bull/bear. The benchmark-relative reasoning that motivates this whole rework (the market structurally favors bull-regime gains, so an absolute bull-share threshold is uninformative) has no obvious analog for volatility regimes -- there's no comparable base-rate argument that a buy-and-hold benchmark is intrinsically high-vol- or low-vol-dependent. Rather than bolt a benchmark-relative volatility check onto a brief that never asked for one, the volatility axis was dropped from `marginal_flags` entirely; `verdict.py`'s consumption of the field (now reading `flag["strategy_bull_share"]`/`flag["excess"]`/`flag["confidence"]` instead of `flag.share`/`flag.dependence_label`, since flags are now plain JSON-serializable dicts, not dataclasses) only ever needed updating for the shape change, not for any other verdict threshold -- the hard stop on touching other verdict logic held.

**Fixtures, unexpectedly, didn't move at all.** Re-running `dump_robustness_fixtures.py` produced a byte-identical `marginal_flags: []` in all four full-result fixtures (`pass`, `shaky`, `likely_overfit`, `untestable`) -- `git status` showed zero diff on any fixture file. None of those synthetic scenarios (Ornstein-Uhlenbeck mean-reversion, oscillation-then-crash) were ever bull-trending enough to trip even the OLD absolute threshold, so there was nothing for the new benchmark-relative version to change either. That's the correct outcome, not a sign the rework did nothing: it confirms the existing fixture suite was never exercising this flag in the first place, which is also why a frontend contract test had to be added from scratch rather than updated -- the "dead render branch" this phase's brief described really was dead against every fixture in the repo until a new integration test (`test_marginal_flag_trips_when_strategy_is_more_bull_concentrated_than_benchmark`, backend-only, via a monkeypatched `run_ir_backtest_returns`) deliberately constructed a strategy that earns gains only in bull bars on a series whose own buy-and-hold benchmark earns some real gains in bear bars too.

**4 invariant-level unit tests** against `_detect_bull_concentration` directly (zero excess never flags regardless of absolute share; excess just past threshold is "provisional"; excess past the confirmed band is "confirmed"; a strategy benchmarked against itself nets to ~zero excess and never flags) plus **1 integration test** through `run_regime_analysis` with a real benchmark derived end to end, replacing the 2 old per-axis tests that asserted against the removed dataclass shape. Backend: 178 -> 181 (net +5 after removing the 2 obsolete ones). Frontend: `RobustnessPanel`'s render branch for `marginal_flags` updated to the new shape (excess shown as "+X.X pp vs benchmark," provisional flags rendered muted with a "(provisional)" suffix, confirmed flags full-weight amber) -- no frontend test exercises this branch yet since no fixture trips it, the same gap the backend integration test above had to manufacture synthetic input to close. `tsc --noEmit`, `eslint`, and `next build` all clean; frontend suite holds at 19 (fixture content didn't change, so nothing to re-assert).

Next: the volatility-axis marginal check was removed outright rather than rebuilt benchmark-relative -- if a future phase wants a vol-regime-dependence signal, it needs its own base-rate argument for what a "benchmark" vol-share even means, not a copy-paste of the bull logic. Also still pending: the structured field editor and the unexpected-shape fallback in `RobustnessResultView`, both deferred from 5b and untouched here.

## 2026-06-24 — Phase 5b: input -> translate -> confirm gate, wired to a real HTTP boundary

**Lesson first: a "pure renderer" promise is worthless if the layer underneath it can be coaxed into running something without an explicit confirm — so the hard gate has to be a property of the call graph, not a UI affordance.** Phase 3's Python-level guarantee ("`translate`/`correct` never reach the backtester; `confirm` is the only path to a run") had no HTTP analog yet — `main.py` only exposed `/health`. The risk this phase is actually about isn't "can the user find the button," it's "is there any code path — a bug, a future feature, a race — that produces a robustness result without a user-initiated `/confirm` POST." Solved at three layers simultaneously: (1) the route layer — `/translate` and `/confirm` are two separate FastAPI functions; `translate_route`/`correct_route` literally do not import or reference `run_robustness`, confirmed by `test_translate_and_correct_routes_have_no_dependency_on_price_fetcher`'s signature-inspection test and by monkeypatching `run_robustness`/`run_ir_backtest` to raise inside `test_api_routes.py` and posting to `/translate`/`/correct` anyway; (2) the service layer — added `service.confirm_robustness(ir, price_data, assumptions)` as a new function (did NOT change `service.confirm`'s existing signature/behavior, which would have silently broken `test_translation_service.py`'s passing assertions about it) that composes `validate_ir` + `run_robustness`, the same way `confirm` already composed `validate_ir` + `run_ir_backtest` — no new backtest logic, just orchestration; (3) the frontend — `TranslateFlow`'s `result` state is set in exactly one function (`handleConfirm`), wired to exactly one button (`ConfirmGate`), and `RobustnessResultView` only renders when `result` is non-null. `CONTRACT 5`'s tests assert this by calling translate, then correct, and confirming `api.confirm` was never invoked and no robustness-result testid exists in the tree either time — only clicking the actual confirm button produces both.

**Orientation findings ([0]), confirmed by reading the code rather than assuming the brief's description:** `service.translate`/`service.correct` return a `TranslationResponse` dataclass (`status`, `ir`, `assumptions: list[Assumption]`, `restatement`, `message`, `retries`) — `assumptions` is already structured data with a `severity` field per item (`"note"` or `"warning"`), not just embedded in the prose. `renderer.render_confirmation` is a pure function returning ONE joined string with a fixed section order (strategy prose -> "You specified:" -> optional "⚠ Heads up" block -> "I assumed (...)"), not a structured `{stated: [...], assumed: [...]}` object — there is no field-level "you specified" list exposed outside that string. `service.confirm(ir, price_data)` returns a raw `BacktestResult`, not a robustness dict — it doesn't call `run_robustness` at all, which is why a new `confirm_robustness` function was needed rather than reusing `confirm` as-is. `defaults.py`'s `Assumption.severity` (`SEVERITY_WARNING = "warning"`) is the only marker — there is no separate boolean flag or distinct dataclass for the no-exit case; severity-filtering the assumptions list is the whole mechanism. `main.py` had only `/health`, confirmed directly (it's a 9-line file).

**Why the "You specified" / "I assumed" split isn't done by re-deriving structure from the IR client-side, and isn't done by guessing at backend internals either.** The display corollary forbids the frontend from synthesizing stated/assumed lists from the IR itself (that would be re-implementing `_stated_summary`'s logic — exactly the kind of client-side judgment call that could drift from the backend's). Two real options existed: (a) parse the prose string on fixed literal headers (`"You specified:"`, `"⚠ Heads up"`, `"I assumed (you didn't specify these):"` — these are Python string constants in `renderer.py`, not data, so slicing on them is structural, not a rewording), or (b) add a new structured-sections function to `renderer.py` itself. Chose (a) for the strategy/"you specified" portions specifically because the backend doesn't expose them as separate fields and refactoring `renderer.py`'s return type would have changed `render_confirmation`'s signature and risked the eight passing tests in `test_translation_renderer.py` that assert against the joined string. For the "I assumed" / "⚠ Heads up" split, used (the better option) the already-structured `assumptions` array's `severity` field directly — no parsing at all — since that data was already there and is strictly more reliable than text-sniffing. `lib/translation/restatementSections.ts` documents this split exactly: it only slices the prose for the two sections the backend doesn't expose structurally, and is explicit in its own docstring that the warning/note split is NOT its job.

**API surface ([1]):** `POST /translate` (`{nl_text}` -> `TranslationPayload`), `POST /correct` (`{original_nl, prior_ir, correction_text}` -> `TranslationPayload`), `POST /confirm` (`{ir, assumptions, ticker, start, end?}` -> the `RESULT_KEYS` dict or `NoExitResult`, both verbatim from `run_robustness`). `/translate` and `/correct` use a `get_llm_client` FastAPI dependency that returns `None` in production (telling `service.translate`/`correct` to build their own default `AnthropicLLMClient`) and is overridden with a `FakeLLMClient` in tests — same dependency-injection shape `/confirm`'s `get_price_fetcher` uses to avoid a real `yfinance` network call in tests. `/confirm`'s `assumptions` field is round-tripped from the client's prior `/translate`/`/correct` response, not re-derived server-side from the IR — `is_no_exit_strategy` reads the `SEVERITY_WARNING` off the assumptions list, by design (see Phase 4c), so the route has to receive exactly what defaulting produced, the same object the user actually saw in the confirmation screen.

**8 new backend HTTP tests** (`test_api_routes.py` — 2 for CONTRACT 1 variants on `/translate`, 1 on `/correct`, 1 unsupported-status passthrough, 3 for CONTRACT 2 on `/confirm` including the no-exit short-circuit and IR-rejection, 1 signature-inspection check), **2 new backend fixture-pinning tests** (`test_translation_fixtures.py`, mirroring 5a's `test_robustness_fixtures.py` pattern for `backend/scripts/dump_translation_fixtures.py`'s two real `apply_defaults`+`render_confirmation` outputs), **9 new frontend contract tests** (`components/translation/__tests__/contracts.test.tsx`). Backend: 168 -> 178 (8 route + 2 fixture tests). Frontend: 10 -> 19. `npx tsc --noEmit`, `npx eslint .`, and `next build` all clean — the build initially failed on three components missing `"use client"` (stateful components — `ConfirmGate`, `TranslateInputView`, `TranslateFlow` — imported transitively from `app/page.tsx`, a Server Component by default in this Next.js version); fixed by adding the directive to each, the same fix in three places since each is independently a leaf that uses `useState`.

**The five contracts, each with a dedicated test:**
1. **No backtester access from `/translate`/`/correct`** — `test_api_routes.py` monkeypatches `service.run_ir_backtest` and `service.run_robustness` to raise, then posts to both routes and asserts 200 with no exception, for both the "ok" and "unsupported" translation outcomes.
2. **`/confirm` is the only path to a robustness result** — `test_confirm_route_is_the_only_path_to_a_robustness_result` posts a full IR and asserts the exact `RESULT_KEYS` keys come back with `kind: "full"`; a second test posts the same shape but with a `SEVERITY_WARNING` exit assumption attached and asserts `kind: "no_exit"` with `verdict: None` — proving the route defers entirely to `is_no_exit_strategy`'s read of the assumptions list, not some route-level heuristic.
3. **SEVERITY_WARNING renders via a structurally distinct element** — `AssumptionsView`'s warning assumption renders as its own `role="alert"` block (`assumption-warning` testid), never one of the plain `<li data-testid="assumption-note">` rows; the frontend test diffs the two and confirms neither identity nor role overlaps.
4. **Verbatim text** — the rendered warning/note text is asserted to literally contain the backend's `Assumption.reason` string (not a paraphrase), and the "You specified" section is asserted to contain the exact phrases (`"ticker: SPY"`, `"entry condition"`, `"exit condition"`) that `_stated_summary` actually emits for that fixture.
5. **Gate integrity** — `TranslateFlow` rendered with a fake `api`: after `translate()` resolves, no `robustness-result-view`/`verdict-card` testid exists and `api.confirm` was never called; same after a `correct()` round-trip; only clicking `confirm-run-button` produces both the `api.confirm` call and the rendered verdict card, with the exact `ir`/`assumptions` it was given.

**Judgment call: ticker for `/confirm`'s price fetch is read from the already-confirmed IR (`ir.asset.ticker`), never a separately editable field.** A free-text ticker input next to the confirm button would let the frontend silently fetch price data for a different instrument than what the user just reviewed in the stated/assumed screen — exactly the kind of frontend-introduces-a-disagreement-with-the-backend gap the display corollary exists to prevent. The only editable inputs on `ConfirmGate` are the backtest start/end dates, which don't change what strategy is being tested.

Next: structured field editor (explicitly deferred, not built) and the marginal-concentration benchmark-relative rework flagged in 4c (also explicitly out of scope this round) are the two known remaining gaps — neither touched per the hard stop.

## 2026-06-24 — Phase 5a: results renderer (verdict-first, honest display)

**Lesson first: a renderer that does no math can still lie, just by ordering or omission — so the contract has to be enforced at the component-tree level, not trusted to "good design."** The backend's entire 4c effort was getting the verdict computation honest (PASS vs SHAKY vs LIKELY_OVERFIT vs, critically, UNTESTABLE). None of that matters if the UI buries the verdict below a wall of Sharpe ratios, or quietly demotes UNTESTABLE to a greyed-out footnote because it "isn't a real answer." `RobustnessResultView` enforces both failure modes structurally rather than by convention: it renders exactly one of `BuyHoldComparison` OR (`VerdictCard` then `RobustnessPanel`) — there is no code path where both a verdict and a buy-and-hold comparison render together, and no code path where `RobustnessPanel`'s JSX appears before `VerdictCard`'s in the tree. `VerdictCard` itself is the SAME component, with the same testid structure, for all four states — `UNTESTABLE` differs from `PASS` only in label text and accent color, confirmed directly by a test that renders both and diffs their `data-testid` trees for equality.

**Orientation findings ([0]):** the backend has no robustness HTTP endpoint yet — `main.py` only exposes `GET /health`. The frontend is the untouched `create-next-app` skeleton (one page, the default template) with no test runner installed at all. Given this, and that the task explicitly scopes out the input/translate/confirm flow (5b) and says to build a renderer, not wire a live endpoint: these components are pure presentational components that take the already-fetched result object as a prop (`RobustnessResultView({ result })`), not components that fetch anything themselves. Wiring an actual `/robustness` endpoint and a page that calls it is 5b's job, not built here. **Test runner**: none existed; added Vitest + `@testing-library/react` + jsdom + `@testing-library/jest-dom` (`frontend/vitest.config.ts`, `npm run test`) — chosen over Jest because it needs zero extra config for this stack's TypeScript/ESM/React 19 combination. `RobustnessResult`'s TypeScript shape (`frontend/lib/robustness/types.ts`) mirrors `backend/app/robustness/robustness.py`'s `RESULT_KEYS` dict exactly, snake_case field names preserved verbatim (no camelCase remapping layer that could itself drift from the schema).

**Schema-true fixtures, not hand-authored JSON ([1]).** `backend/scripts/dump_robustness_fixtures.py` runs the REAL `run_robustness` on five canned, seeded (no network), deterministic inputs and dumps one JSON fixture per state into `frontend/fixtures/robustness/`: `pass.json`, `shaky.json`, `likely_overfit.json`, `untestable.json`, `no_exit.json`. Finding inputs that actually land in each bucket took direct experimentation against the real thresholds in `verdict.py` (documented in the script's docstrings) — notably, RSI-based strategies kept landing "fragile" on sensitivity due to threshold-grid sweeps alone, which masked the PASS case; switching to an SMA-crossover (`close crosses_below/above SMA(20)`, both operands non-numeric) removed the threshold-tunable dimension entirely, leaving only the period sweep and reliably producing "robust (broad plateau)." The `untestable` fixture stacks BOTH the WF-thin-evidence and DSR-fail-on-thin-data reasons in one result — a direct exercise of the Phase 4c calibration fix. One real wrinkle caught while building this: a smooth, low-amplitude sine-wave price series for the no-exit fixture never moved RSI(14) below 30 at all (the entry condition never fired) — switched to the sharp-block oscillation pattern already proven to fire in `test_translation_no_exit_backtest.py` rather than guessing at a second synthetic shape. A second wrinkle: real regime breakdowns can legitimately contain `NaN` (a zero-variance regime cell has no defined Sharpe) — `json.dump`'s default `allow_nan=True` would have silently written non-standard `NaN` tokens into the fixture files that `JSON.parse` can't read; the dump script now converts non-finite floats to `null` explicitly (`_null_out_non_finite_floats`) and calls `json.dumps(..., allow_nan=False)` so a future occurrence fails loudly instead of producing a corrupt fixture. `backend/tests/test_robustness_fixtures.py` pins each builder function to its target verdict state so a future `verdict.py` threshold change that silently reclassifies one of these canned inputs fails a backend test, not just "the frontend tests started looking weird." `run_robustness` also gained two more passthrough kwargs (`min_trades_for_confidence`, on top of 4c's window-size kwargs) purely to make small, fast synthetic fixtures practical — same pattern as the existing window kwargs, no change to defaults.

**Components (`frontend/components/robustness/`):** `VerdictCard` (the headline: verdict label + plain-English reasons, identical structure across all four states), `RobustnessPanel` (the four checks as collapsible `<details>` sections — walk-forward folds, sensitivity peakiness, DSR, regime breakdown/marginal flags — strictly supporting detail, rendered second), `BuyHoldComparison` (the no-exit message, first entry date, and a strategy-vs-benchmark metrics table), and `RobustnessResultView` (the single entry point: branches on `result.kind`, calls exactly one of the above paths). None of the four computes anything beyond display formatting (`frontend/lib/robustness/format.ts`: number-to-string, fraction-to-percent-string, null-to-"N/A" — no thresholds, no branching on a number's value to decide a label). The one judgment call: `MarginalConcentration.dependence_label` (e.g. "bull-dependent") is a Python `@property`, not a serialized field, so it doesn't reach the frontend at all — rather than reimplementing that classification in TypeScript (which would be exactly the kind of UI-side verdict logic the security boundary's display corollary forbids), `RobustnessPanel` renders the raw `axis`/`dominant_label`/`share` fields literally ("trend axis dominated by bull: 95% of gains").

**10 new frontend tests** (`components/robustness/__tests__/contracts.test.tsx`), **6 new backend tests** (5 fixture-state pins + the `run_robustness` kwarg passthrough exercised implicitly). Backend suite: 163 -> 168. Frontend: 0 -> 10, all green. `npx tsc --noEmit`, `npm run lint`, and `next build` all clean.

**The four contracts, each with a dedicated test:**
1. **Verdict before figures** — `compareDocumentPosition` confirms `verdict-label`/`verdict-reason` precede `stat-aggregate-is-sharpe` etc. in DOM order on the `likely_overfit` fixture (the richest one, most figures to accidentally place first).
2. **UNTESTABLE is first-class** — same `VerdictCard`, same testid tree as `PASS` (diffed structurally, not just "a verdict word appears somewhere"); the real `untestable` fixture's reason text renders with full visibility.
3. **No-exit excludes the robustness panel** — `buy-hold-comparison` present, `verdict-card`/`robustness-panel` absent, and no PASS/SHAKY/LIKELY_OVERFIT/UNTESTABLE word anywhere in the no-exit render.
4. **Figures match verbatim** — rendered text for aggregate IS/OOS Sharpe, DSR, per-fold Sharpe, and the no-exit benchmark metrics are asserted against the fixture object's own values (formatted, not transformed) on three different fixtures (`likely_overfit`, `no_exit`, `pass` — failure-state and pass-state both checked, not just the dramatic cases).

Next: 5b (input/translate/confirm flow + wiring a real `/robustness` endpoint this renderer can consume) — out of scope here per the brief's hard stop.

## 2026-06-24 — Phase 4c calibration fixes: verdict precedence + thresholds

**Lesson first: a confident-looking number can be manufactured from garbage inputs on thin data, and that failure mode doesn't only show up where you first built the guard against it.** The untestable-evidence guard added in 4c only checked walk-forward's own degradation signal before routing to `UNTESTABLE`. But DSR's `n` is period-based (hundreds of daily bars), so it stays "stable"-looking even when the underlying strategy only made a handful of round-trip trades — while DSR's skew/kurtosis inputs are computed on that *same* thin-trade return series, where higher moments are themselves unstable. A DSR-fail on a strategy with 2-3 trades per fold can be exactly the kind of dishonest confidence this project exists to expose, just arriving through a different check than the one already guarded. Fixed: `compute_verdict`'s untestable short-circuit now also fires on `wf_evidence_thin and dsr_fails` (previously only `wf_evidence_thin and wf_overfit_signature`), folding a plain-English DSR caveat into the `UNTESTABLE` reasons ("DSR also failed, but on a return series too thin to trust its higher moments") rather than reporting it as a second, independent confirmation of overfitting. `test_calibration_invariant1_thin_folds_plus_failing_dsr_is_untestable_not_overfit` pins this; `test_calibration_invariant2_confidence_bearing_folds_plus_failing_dsr_still_overfit` is the guard against over-correcting — a failing DSR with trustworthy walk-forward evidence still drives `LIKELY_OVERFIT` on its own, since the override is specifically about the untestable axis, not "any thin trade count anywhere weakens DSR forever."

**Second fix: `WF_DEGRADATION_THRESHOLD` was gating on the SIZE of the IS->OOS drop alone, which can't tell "haircut on a great number" from "sign flip into loss."** IS 3.0 -> OOS 2.4 (a 0.6-Sharpe drop, above the 0.5 threshold) and IS 0.4 -> OOS -0.2 (also a 0.6-Sharpe drop) tripped the identical wire, even though only the second is the textbook overfitting tell — the first is still a strongly-performing strategy out of sample. Fixed by adding `WF_OOS_SHARPE_OVERFIT_CEILING = 0.0`: a degradation-driven (as opposed to sign-flip-driven) `LIKELY_OVERFIT` now additionally requires OOS to land at or below that ceiling. `test_calibration_invariant3_large_drop_landing_strongly_positive_is_not_overfit` (IS 3.0 -> OOS 2.4, must not be `LIKELY_OVERFIT`) and `test_calibration_invariant4_sign_flip_into_loss_is_still_overfit` (IS 0.4 -> OOS -0.2, must still be `LIKELY_OVERFIT`, via the pre-existing `sign_flip` path which is unaffected by this change) pin both ends. `test_large_drop_landing_strongly_positive_still_contributes_to_shaky` confirms the large-but-not-damning drop isn't silently dropped entirely — it still surfaces as a `SHAKY` caution via the existing "mild degradation" branch.

**5 new tests**, all in `test_verdict.py` (4 named invariants + 1 SHAKY-fallback check). Suite: 158 -> 163, all green.

**Judgment call:** the SHAKY-fallback test (`test_large_drop_landing_strongly_positive_still_contributes_to_shaky`) confirms the existing "mild degradation" caution branch (`elif degradation > 0`, unconditional on where OOS lands) already covers the invariant-3 fixture without any code change — a large-but-not-damning drop still surfaces as `SHAKY`. No fixture forced a SHAKY-vs-harder tradeoff beyond what 4c had already worked out; this round was purely about not letting a confident verdict (LIKELY_OVERFIT, either route) get manufactured from inputs that don't support that confidence.

**Marginal bull-concentration flag (`regime.py`, not changed this round) — flagged as provisional, not relied on as a clean signal.** `MARGINAL_CONCENTRATION_SHARE_THRESHOLD = 0.8` is an ABSOLUTE share of gains-only returns. Because the market makes most of its money in above-200MA (bull) regimes across most long-biased history, nearly every long-only strategy — including buy-and-hold SPY itself — likely parks 80%+ of its gains in bull periods. That means the marginal trend flag risks being close to always-on, which would make it uninformative as a "this strategy specifically depends on bull markets" signal: it would just be re-stating "this is a long-only equity strategy and bull markets have most of the gains," true of nearly everything in this category. The principled fix is EXCESS concentration relative to a benchmark (e.g. is this strategy's gain-share-in-bull MORE concentrated than buy-and-hold's own gain-share-in-bull on the same window?) rather than an absolute cutoff — left unresolved for now, deliberately not built this round. **Do not treat the marginal trend flag as a validated, discriminating signal until that benchmark-relative version exists.** The 2x2 CELL concentration check is NOT affected by this caveat: 80% of gains landing in one of *four* cells is a genuinely high bar regardless of long-only base rates (the absolute-vs-relative distinction matters specifically because the marginal check collapses to a two-way split where one side already dominates the unconditional base rate) -- same threshold value, different base rate, different trust level.

Next: frontend wiring for the robustness result (still deferred, per the hard stop both this round and 4c's).

## 2026-06-23 — Phase 4c: verdict layer + robustness orchestrator

**Lesson first: "we tested it and it's overfit" and "we don't have enough evidence to test it" are different claims, and conflating them is exactly the kind of dishonest backtest this project exists to catch.** Walk-forward can come back with every fold trading a handful of in-sample trades; a sign-flip (positive IS Sharpe -> negative OOS Sharpe) on that thin evidence *looks* like the textbook overfitting signature but is actually just noise wearing an overfit costume. `verdict.py`'s `compute_verdict` checks whether the walk-forward evidence is confidence-bearing *before* it lets any degradation reading drive a verdict: if the share of `low_confidence` folds is at or above `LOW_CONFIDENCE_FOLD_SHARE_THRESHOLD` (0.5 — chosen because at that point most of the aggregate IS/OOS Sharpe reflects unreliable per-fold parameter picks, not a measurement worth trusting either way), the result routes to `UNTESTABLE`, never `LIKELY_OVERFIT` — regardless of how dramatic the raw degradation number looks. `UNTESTABLE` is also returned when zero walk-forward folds complete at all (not enough price history for even one fold) — same underlying problem (no trustworthy generalization evidence), same honest answer.

**Task order followed exactly as briefed:** fixed `regime.py`'s real gap first, since `verdict.py` consumes its output.

**`regime.py` fix — marginal concentration.** The existing 2x2-cell concentration flag (`concentrated_regime`, >=80% of gains in one cell) misses bull-dependence when gains split across both bull cells: a strategy that earns in 2020 (bull, high-vol crash-recover) and 2021 (bull, low-vol grind-up) splits roughly 50/50 across `bull_high_vol`/`bull_low_vol`, so neither cell hits 80% and the flag stays silent — even though bull markets alone own ~100% of the gains. Added `_axis_labels(close)` (trend and vol computed independently, not parsed back out of the combined string — `_regime_labels`/`_combine_labels` now build the combined label from the same two series) and `_detect_marginal_concentration`, which aggregates positive returns by trend alone and by volatility alone (each ignoring the other axis) and flags a `MarginalConcentration(axis, dominant_label, share)` when one side of an axis owns >= `MARGINAL_CONCENTRATION_SHARE_THRESHOLD` (0.8 — same value as the cell threshold; no documented reason to use a different number, kept as a separate constant since the two checks are conceptually independent). `RegimeReport.marginal_flags` is a new tuple field (default `()`, so existing cell-only call sites/tests didn't need updating). `MarginalConcentration.dependence_label` renders "bull-dependent"/"bear-dependent"/"volatility-dependent" for plain-English consumption downstream. New tests in `test_regime.py`: `test_bull_dependence_marginal_flag_trips_when_cell_flag_stays_silent` pins the exact scenario from the brief (gains in both bull cells, losses in both bear cells) and asserts BOTH behaviors in one test — the per-cell flag stays `None` AND the trend marginal flag fires `bull`/`bull-dependent`; `test_no_marginal_flag_when_gains_are_spread_across_both_axis_sides` is the negative control.

**`verdict.py` — new module.** `compute_verdict(*, walk_forward, sensitivity, dsr, regime) -> VerdictResult(verdict, reasons, details)`. Four states: `PASS` (no flag from any check), `SHAKY` (one or more caution signals — a fragile sensitivity param, a regime concentration/marginal flag, a DSR that's positive but not strongly above the multiple-testing bar, or thin-but-not-disqualifying degradation), `LIKELY_OVERFIT` (confidence-bearing walk-forward degradation and/or a DSR that fails the multiple-testing bar outright), `UNTESTABLE` (walk-forward evidence too thin to support any verdict about generalization — see lesson above). Reasons are plain English built from the checks; raw numbers (`details` dict) are available but don't lead.

**Thresholds chosen (all heuristic, documented in the module, none from a cited paper):**
- `DSR_FAIL_THRESHOLD = 0.5` — below this the deflated, multiple-testing-adjusted Sharpe doesn't even clear a coin flip.
- `DSR_STRONG_PASS_THRESHOLD = 0.95` — the conventional one-sided "statistically significant" bar; between 0.5 and 0.95 is the `SHAKY`-contributing "marginal" zone.
- `WF_DEGRADATION_THRESHOLD = 0.5` (Sharpe units) — a large enough IS-minus-OOS drop to call a degradation signature on its own (independent of a sign flip), on the same 252-trading-day annualization convention used everywhere else in this codebase.
- `LOW_CONFIDENCE_FOLD_SHARE_THRESHOLD = 0.5` — see lesson above.
- `MARGINAL_CONCENTRATION_SHARE_THRESHOLD = 0.8` (regime.py) — see above.

**The no-exit short-circuit is a distinct result type, not a fifth verdict state.** `is_no_exit_strategy(assumptions)` checks for the `SEVERITY_WARNING` `exit` assumption (`defaults.py`, Phase 3); `build_no_exit_result(ir, price_data)` finds the real first entry date from `run_ir_backtest_returns`'s entry-flag series, runs the strategy once (one open trade, per the Phase 3 disclosure), and runs `compute_buy_and_hold_metrics` on `price_data["Close"].loc[first_entry_date:]` with `warmup=0` — i.e. buy-and-hold starting from the *actual* first entry bar, not the warmup-trimmed start of the test window — so the comparison is apples-to-apples against what the no-exit strategy itself did. Returns `NoExitResult(message, first_entry_date, strategy_metrics, benchmark_metrics)`, structurally incapable of carrying `PASS`/`SHAKY`/`LIKELY_OVERFIT`/`UNTESTABLE` since that's not one of its fields. Edge case handled: an entry condition that never fires at all (no trade, nothing to benchmark) returns a distinct message with `first_entry_date`/both metrics `None` rather than crashing on an empty index.

**`robustness.py` — new orchestrator.** `run_robustness(ir, price_data, assumptions, ...) -> dict` with exactly the keys in `RESULT_KEYS = ("kind", "no_exit", "sensitivity", "walk_forward", "deflated_sharpe", "regime", "verdict")`. Branches on `is_no_exit_strategy` at the very top — confirmed by `test_no_exit_does_not_run_round_trip_machinery`, which monkeypatches `run_sensitivity`/`run_walk_forward`/`run_regime_analysis` to record calls and asserts none of them ran for a no-exit IR, not just that their results are unused. For the round-trip path: runs sensitivity, walk-forward, and regime exactly as 4a/4b built them, sources DSR's trial Sharpes from every sensitivity grid point actually evaluated (continuing the convention `deflated_sharpe_ratio_from_trials` was built for in 4a), then calls `compute_verdict`. All dataclass results go through `dataclasses.asdict` for a plain-dict, JSON-serializable tree (pinned with `json.dumps(result, default=str)` in tests, not just an `isinstance` check — `default=str` only covers stray non-primitives; the assertion is that nothing throws). Walk-forward window sizes (`in_sample_bars`/`out_of_sample_bars`/`step_bars`) are now optional `run_robustness` kwargs (forwarded to `run_walk_forward`, still defaulting to its existing 756/252/252) so tests can run a real, complete walk-forward without needing 1000+ bars of synthetic data.

**18 new tests:** `test_regime.py` +2, `test_verdict.py` (14), `test_robustness.py` (4). Suite: 140 -> 158, all green.

---

### Judgment calls forced by fixtures

**SHAKY vs LIKELY_OVERFIT when DSR fails alone, walk-forward looks fine.** `test_likely_overfit_from_dsr_alone` deliberately uses a walk-forward result with no degradation signature at all (confidence-bearing folds, OOS slightly *better* than IS) and a failing DSR (0.3). Verdict: `LIKELY_OVERFIT`, not `SHAKY` — a DSR that fails the multiple-testing bar outright is treated as sufficient on its own, not merely a caution signal, since it's a direct statistical statement ("this Sharpe doesn't clear the bar adjusted for how many configurations were tried") rather than a softer heuristic like sensitivity peakiness or regime concentration. The "marginal" DSR zone (0.5-0.95) is the one that only contributes to `SHAKY`.

**Untestable overrides everything, even a real-looking overfit shape.** `test_invariant2_majority_low_confidence_share_also_routes_untestable` mixes 2 low-confidence folds with 1 confidence-bearing fold (67% low-confidence, above the 50% threshold) showing a dramatic-looking degradation. Verdict: `UNTESTABLE`, even though one fold individually had enough trades — the *aggregate* IS/OOS Sharpe the degradation number is built from still mixes in the unreliable folds, so the aggregate itself isn't trustworthy enough to read either way. The fixture `test_low_confidence_share_below_threshold_does_not_block_overfit_verdict` (1 of 4, 25%) confirms this isn't reflexive distrust of any low-confidence fold — below the documented threshold, a real degradation signature still drives `LIKELY_OVERFIT`.

Next: frontend wiring for the robustness result (deferred per the brief's hard stop) — `RESULT_KEYS`/the `kind` discriminator are the contract to build against.

## 2026-06-22 — Phase 4b: walk-forward validation + regime testing

**Task 0 (done first, as instructed): fixed the warmup confound from 4a.** `compute_ir_warmup` (Phase 2, `app/translation/interpreter.py`) used to take the max lookback across *every declared indicator*, including ones the entry/exit conditions never reference. Sweeping an unused indicator's period therefore silently changed the effective backtest window — a confound that would have corrupted walk-forward's in-sample parameter search (an "optimal" period could win purely by shifting the window, not by improving the strategy). Fixed by adding `_referenced_indicator_ids(ir)` / `_operand_strings_in_condition(cond)`: warmup now only considers indicators whose `id` actually appears as an operand somewhere in `entry`/`exit`. New test `test_ir_warmup_ignores_unreferenced_indicators` (`test_ir.py`) pins this: an IR with an unused SMA(200) bolted on must produce the identical warmup, effective window, and backtest result as the IR without it. Full suite stayed green throughout (118 -> 119 after the new test, before 4b's own additions).

**Small refactor to `app/engine/backtest.py`** to support regime attribution without a second execution path: extracted `_build_ir_portfolio()` (IR -> signals -> vectorbt portfolio — the shared core `run_ir_backtest` already had) and added `run_ir_backtest_returns()`, which calls the *same* helper and returns the per-bar returns/entry-flag series that `run_ir_backtest` was computing internally and then discarding. No new vectorbt call, no new math — just exposing what was already being computed. `regime.py` is the only caller.

**New files (`backend/app/robustness/`):**

- `walk_forward.py` — `run_walk_forward(ir, price_data, in_sample_bars=756, out_of_sample_bars=252, step_bars=252, ...)`. Per fold: builds the full cartesian product of `params.py`'s tunable grids (e.g. 5x5=25 candidates for 2 tunables), backtests every candidate on the IS slice via `run_ir_backtest`, picks the highest-Sharpe candidate (deterministic tie-break: closest to stated values, then smallest total magnitude, then canonical grid order — so reruns are reproducible), freezes it, and backtests that frozen IR on the immediately-following OOS slice — again via `run_ir_backtest`, on the OOS slice alone. Reports per-fold IS/OOS Sharpe, return, and trade counts, plus a `low_confidence` flag when IS trades fall below `min_trades_for_confidence` (default 10) — optimizing Sharpe on a handful of trades is itself a form of overfitting, so that's surfaced per fold rather than silently baked into "the chosen params." Aggregates IS/OOS Sharpe across folds and reports `degradation = aggregate_is - aggregate_oos`.
- `regime.py` — `run_regime_analysis(ir, price_data)`. Two documented, independent regime axes: trend (`bull`/`bear` via price vs. its 200-day SMA) and volatility (`high_vol`/`low_vol` via 60-day trailing realized vol vs. the *sample median* of that rolling series) combined into up to 4 labels. Per-regime: share of time, compounded return, Sharpe, and entry count, all computed from `run_ir_backtest_returns`'s per-bar output (never a second simulation). Flags `concentrated_regime` when a single regime owns >=80% of the strategy's total *positive* per-bar returns (gains-only, so the share is always bounded in [0,1] regardless of how losses are distributed).

**67 new tests:** `test_ir.py` +1 (warmup fix), `test_walk_forward.py` (10), `test_regime.py` (9). Suite: 118 -> 138, all green.

---

### Walk-forward correctness invariants (each pinned with a test)

1. **No lookahead.** `test_fold_boundaries_are_strictly_sequential_and_non_overlapping` checks every OOS window starts strictly after its IS window ends. `test_chosen_params_do_not_depend_on_out_of_sample_data` runs the *same* IS slice with two wildly different OOS slices appended and asserts the chosen parameters for that fold are identical — proving the optimizer structurally cannot see OOS bars (it never receives them).
2. **Warmup handled inside each window, no cross-boundary bleed.** Each fold calls `run_ir_backtest` independently on the IS slice and (separately) the frozen IR on the OOS slice — there is no shared state between the two calls. `test_oos_result_matches_independent_standalone_backtest_on_same_window` proves this directly: the OOS metrics walk-forward reports for a fold must exactly equal calling `run_ir_backtest` by hand on that same OOS slice in isolation.
3. **Costs modeled in every fold.** `test_costs_are_passed_to_every_backtest_call` spies on every call walk-forward makes to `run_ir_backtest` (IS search *and* OOS test) and asserts the configured non-zero retail slippage was actually passed, not defaulted away.
4. **Thin-evidence visibility.** `test_low_trade_count_fold_is_flagged_low_confidence` / `..._is_not_flagged...` confirm the flag tracks the documented `min_trades_for_confidence` threshold (default 10) on the *chosen* candidate's IS trade count.

Tie-breaking and grid-coverage are also tested directly: `test_full_grid_is_evaluated_every_fold` asserts every one of the 25 IS candidates plus the 1 OOS call actually ran (26 calls/fold); `test_tie_breaking_prefers_stated_value_then_is_deterministic` forces every candidate to tie exactly and confirms the winner is the user's originally-stated configuration, reproducibly across repeated runs. `test_a_failing_candidate_does_not_crash_the_fold` confirms one candidate raising (e.g. a degenerate mutated IR) doesn't abort the search.

Most of these use a stubbed `run_ir_backtest` (deterministic, pure-Python, no vectorbt) for speed and precise control over scores/trade-counts; the lookahead and warmup-boundary tests use the real engine on small synthetic windows specifically because those invariants are about genuine data sensitivity, not arithmetic.

### Regime testing notes

`_regime_labels` is tested directly against a two-segment synthetic series (a long clean uptrend, then a long clean downtrend) — both trend labels and the MA200 warmup-exclusion are checked explicitly. Per-regime attribution and the concentration flag are tested via a monkeypatched `run_ir_backtest_returns` so the per-bar returns feeding the attribution are exactly known (rather than depending on what a real RSI strategy happens to do on a given synthetic series) — `test_concentration_flag_triggers_when_one_regime_owns_almost_all_gains` locates one real combined regime's exact bar range via `_regime_labels` itself, puts all the crafted gains only there, and asserts that exact regime gets flagged.

**Restated in code and here: regime boundaries use full-sample information** (the volatility split is the median of the *entire* trailing-vol series, computed with hindsight). This is honest, descriptive labeling — "did this strategy's results come from everywhere, or from one slice of history" — not a rule the strategy could have used in real time, and it must never be fed back into the IR.

---

### Example: RSI(14)<30/>70 on a 2000-bar synthetic series with an embedded trend-then-crash-then-recovery shift

`run_walk_forward(ir, price_data, in_sample_bars=400, out_of_sample_bars=150, step_bars=150)` — 10 folds:

```
fold IS window               OOS window              chosen params                                                          IS Sharpe  IS trades  OOS Sharpe  OOS trades  low_conf
0    2010-01-01..2011-02-04  2011-02-05..2011-07-04  period=12, entry=33, exit=63                                          1.49       4          nan         0           True
1    2010-05-31..2011-07-04  2011-07-05..2011-12-01  period=12, entry=36, exit=63                                          1.70       5          0.48        2           True
2    2010-10-28..2011-12-01  2011-12-02..2012-04-29  period=10, entry=33, exit=84                                          1.74       2          1.00        1           True
3    2011-03-27..2012-04-29  2012-04-30..2012-09-26  period=12, entry=24, exit=70                                          1.71       2         -2.02        1           True
4    2011-08-24..2012-09-26  2012-09-27..2013-02-23  period=14, entry=27, exit=56                                          0.77       3         -2.73        2           True
5    2012-01-21..2013-02-23  2013-02-24..2013-07-23  period=10, entry=24, exit=56                                         -0.87       5         -4.42        1           True
6    2012-06-19..2013-07-23  2013-07-24..2013-12-20  period=14, entry=24, exit=70                                         -2.80       2          nan         0           True
7    2012-11-16..2013-12-20  2013-12-21..2014-05-19  period=16, entry=24, exit=70                                         -1.40       2          nan         0           True
8    2013-04-15..2014-05-19  2014-05-20..2014-10-16  period=14, entry=30, exit=84                                          0.34       1          nan         0           True
9    2013-09-12..2014-10-16  2014-10-17..2015-03-15  period=10, entry=33, exit=84                                          2.07       2          2.09        1           True

aggregate IS Sharpe: 0.474   aggregate OOS Sharpe: -0.932   degradation: 1.406
```

Every single fold is `low_confidence` (IS trade counts of 1-5, all below the default threshold of 10) — exactly the "thin evidence" case the brief called out: this strategy on this data never has enough in-sample trades for the IS Sharpe used to pick parameters to mean much, and the large positive degradation (IS averages positive, OOS averages negative) is consistent with that noise being chased rather than a real edge.

`run_regime_analysis` on the same IR/data:

```
regime          share_time  total_return  sharpe  entries  bars
bear_high_vol   0.218       -0.175        -1.55   78       392
bear_low_vol    0.142       -0.214        -3.85   75       255
bull_high_vol   0.298        0.122         2.28    0       537
bull_low_vol    0.343        0.146         1.43    5       617
```

No concentration flag here — gains are split across both bull sub-regimes rather than owned by one, despite the strategy clearly performing worse in both bear regimes.

## 2026-06-21 — Phase 4a: parameter sensitivity + Deflated Sharpe Ratio

**New files (all under `backend/app/robustness/`):**
- `params.py` — `extract_tunable_params(ir)`: walks a full IR and returns every indicator period and every numeric comparison threshold in the entry/exit condition tree as a `TunableParam` (id, path into the IR, stated value, kind, neighborhood grid). `get_in`/`set_in_copy` read/write a value at a path without mutating the original IR. Grid rule (ours, documented in the module docstring): periods get a 5-point grid at +/-{0,2,4} bars clipped to >=1 (period=14 -> [10,12,14,16,18]); thresholds get a 5-point grid at +/-{0,1,2}*step where step=max(1, round(10% of the value)) (threshold=30 -> step=3 -> [24,27,30,33,36]).
- `sensitivity.py` — `run_sensitivity(ir, price_data)`: for every tunable param, sweeps its grid one-at-a-time (others held at their current IR value), running each grid point through `run_ir_backtest` (never reimplements backtest math). Scores peakiness as the grid's Sharpe range normalized by the Sharpe at the stated value, and labels each param "robust (broad plateau)" / "moderate" / "fragile (sharp peak)" against documented thresholds (<=0.25 / 0.25-0.75 / >=0.75). A grid point whose mutated IR makes the engine raise has the error captured on that point, not propagated — one bad neighborhood value can't crash the sweep.
- `deflated_sharpe.py` — PSR and DSR per Bailey & Lopez de Prado. See verification below.
- 34 new tests: `test_robustness_params.py` (11), `test_sensitivity.py` (8), `test_deflated_sharpe.py` (15). Suite: 84 -> 118, all green.

---

### DSR/PSR verification (the brief said: verify, don't trust the formula — done)

Reference: Bailey & Lopez de Prado, **"The Sharp Razor: Deflating the Sharpe Ratio by asking for a Minimum Track Record Length"** (SSRN 2150879), pp. 16-17 — fetched and read directly (PDF), not recalled from memory. Worked example: a 2-year monthly track record with mean=0.036, stdev=0.079, skew=-2.448, kurtosis=10.164 (non-excess; Gaussian=3), per-period SR=0.458, n=24 monthly observations. The slides state **PSR(0)=0.913** for that fund, and **PSR(0)=0.982** for a fund with the *same* per-period Sharpe but Gaussian returns (skew=0, kurtosis=3).

Hand-verified before writing any test: plugging these numbers into `PSR(SR*) = Phi[(SR_hat-SR*)*sqrt(n-1) / sqrt(1 - skew*SR_hat + ((kurt-1)/4)*SR_hat^2)]` reproduces 0.9134 and 0.9817 respectively — matching the published 0.913/0.982 to the slides' own rounding. Both are pinned in `test_deflated_sharpe.py::test_psr_matches_published_*`. The DSR/SR0 multiple-testing formula (no published worked numeric example found) was checked against an independently-written second computation using `scipy.stats.norm.ppf` directly in the test, rather than re-running the same code path.

Also cross-checked the formula shape against a third-party open implementation by the same author (github.com/rubenbriones/Probabilistic-Sharpe-Ratio, linked from search) — confirms per-period (not annualized) SR and `fisher=False` (non-excess) kurtosis, consistent with the slides.

**Two traps, guarded and tested:**
1. **Per-period vs. annualized SR.** Using the same fund's annualized SR (1.585, also given on the slide) instead of the per-period SR (0.458) in the formula gives PSR(0) ~= 0.99 instead of 0.913 — a different, still-plausible-looking number. `test_trap_1_using_annualized_sharpe_corrupts_psr` pins both values and asserts they differ by >0.05. All public functions in `deflated_sharpe.py` take/expect per-period figures only.
2. **Non-excess kurtosis.** `scipy.stats.kurtosis()` defaults to *excess* kurtosis (Gaussian=0); the formula needs *non-excess* (Gaussian=3). `sample_kurtosis()` always passes `fisher=False`. `test_sample_kurtosis_convention_is_non_excess_gaussian_equals_three` checks a 200k-sample Gaussian reads ~3, not ~0. `test_trap_2_excess_kurtosis_mislabeled_as_non_excess_corrupts_psr` shows feeding the excess value (7.164) where non-excess (10.164) is expected moves PSR(0) from 0.913 to ~0.920 — a smaller but real, silent corruption.

**N sourcing:** `deflated_sharpe_ratio_from_trials(returns, trial_sharpes)` takes `n_trials = len(trial_sharpes)` directly from the list of per-period Sharpes actually evaluated — in practice, every grid point `sensitivity.run_sensitivity` ran (`sensitivity.py` converts each grid point's annualized Sharpe to per-period via `/sqrt(252)` for exactly this purpose). `test_sr0_threshold_increases_with_more_trials` confirms more trials -> higher deflation threshold holding variance fixed.

---

### Example: RSI(14) entry/exit thresholds on a synthetic oscillating series

Ran `run_sensitivity` on `{ticker: SPY, RSI(14)<30 entry, RSI(14)>70 exit}` against the repo's existing 300-bar synthetic oscillating fixture (no network). All three tunables came back **"fragile (sharp peak)"**:

```
indicators.rsi14.period (stated=14): peakiness=1.21
  period=10 -> Sharpe 1.51   period=14 -> Sharpe 5.26   period=18 -> Sharpe 7.88
entry.right (stated=30): peakiness=0.82
  threshold=24 -> Sharpe 8.08   threshold=30 -> Sharpe 5.26   threshold=36 -> Sharpe 3.77
exit.right (stated=70): peakiness=1.33
  threshold=63 -> Sharpe 3.84   threshold=70 -> Sharpe 5.26   threshold=84 -> Sharpe -0.15 (1 trade)
```

This is expected and somewhat artificial: the synthetic series is a clean, regular square wave, so RSI thresholds/periods land on genuinely different numbers of oscillation cycles — real fragility, just exaggerated by a toy fixture rather than evidence the *implementation* is biased toward "fragile." A flat-plateau case is also covered (`test_broad_plateau_strategy_is_labeled_robust`): an exit threshold set far outside the price range never fires for any grid value, giving identical results everywhere and `peakiness=0.0`.

**Known wrinkle, not a bug:** `compute_ir_warmup` (Phase 2) takes the max lookback across *every declared indicator*, even ones not referenced in entry/exit. So sweeping a period changes warmup-trimming (and therefore the effective test window) even for an indicator the conditions never use — confirmed directly while writing `test_broad_plateau_strategy_is_labeled_robust`, which originally tried sweeping an unreferenced indicator's period expecting zero effect and failed for exactly this reason. The test now sweeps an exit threshold instead. Worth a closer look in 4b if walk-forward folds turn out sensitive to this.

## 2026-06-21 — Phase 3 fixes: honest no-exit disclosure + unsupported-before-defaulting ordering

**Problem 1 (the important one):** the no-exit default (`defaults.NO_EXIT_CONDITION`, an always-false sentinel) was being treated as a routine fill-in on par with "RSI period = 14." It isn't: it silently turns the strategy into buy-and-hold-from-first-entry, not a round-trip strategy, and the project's whole premise is *not* burying that kind of thing in a routine assumptions list.

**Fix:**
- `Assumption` (`defaults.py`) now carries a `severity` field (`SEVERITY_NOTE` default, `SEVERITY_WARNING` for anything that changes what the result *means*, not just a parameter value). The no-exit assumption is the only `SEVERITY_WARNING` case today.
- `renderer.py` special-cases the sentinel: the "Exit:" line never renders the literal condition (no "sell when close price is below close price"). It renders explicit prose instead: *"No exit rule given — I held the position from your first entry signal to the end of the data. These results approximate buy-and-hold from that date, not a round-trip strategy."*
- The restatement now has three sections, in order: the plain-English strategy (with the prose above where the exit would be), "You specified," a **"⚠ Heads up — these assumptions change what the result means"** section listing only warning-severity items (ahead of, not mixed into, the routine list), then "I assumed (you didn't specify these)" for note-severity items only.
- New test `test_translation_no_exit_backtest.py::test_no_exit_sentinel_produces_exactly_one_open_trade_held_to_final_bar` pins the actual engine behavior on an all-False exit array: confirmed via a manual vectorbt probe first (`pf.trades.count() == 1`, status `"Open"`) before writing the assertion, rather than guessing — `run_ir_backtest` produces exactly one trade, held open through the final bar, with `total_return`/`max_drawdown`/`annualized_return` all finite.
- 8 new tests total (renderer: no-leak + section-ordering checks; defaults: severity tagging; translator: see Problem 2 below). Suite: 76 → 84, all green.

**Problem 2:** `apply_defaults` raises `DefaultingError` when `asset.ticker`/`entry` are missing — fields the `{"unsupported": true, ...}` sentinel never has. The sentinel check in `translate_to_ir` already ran *before* the defaulting/validation block (confirmed by re-reading the code before changing anything), so this was already correct; added `test_unsupported_sentinel_short_circuits_before_defaulting` to pin it explicitly, monkeypatching `apply_defaults` to raise if called so a future refactor that reorders the checks fails loudly instead of silently losing the clean "not supported in v1" message.

**Known ceiling, not a bug:** unsupported-detection relies on the model self-classifying scope (emitting the sentinel) rather than a pattern match on the user's text. The failure mode this doesn't catch is silent shoehorning — an intraday-ish or multi-asset-ish request the model maps onto a *plausible-looking* daily single-asset IR instead of recognizing it's out of scope. That's a model-reliability ceiling for v1, not something `translate_to_ir`'s retry loop can detect (a malformed IR triggers a retry; a well-formed but wrong-scope IR doesn't). Revisit if this shows up in practice.

## 2026-06-21 — Phase 3: NL → IR translation + confirmation layer

**New files (all under `backend/app/translation/`):**
- `translator.py` — `translate_to_ir(nl_text, llm_client)`: calls the Anthropic API (model from `ANTHROPIC_MODEL` env var, default `claude-sonnet-4-6`; key from `ANTHROPIC_API_KEY`), parses the response as a *sparse* IR, defaults it, schema-validates it, and retries (max 3) by appending the exact failure to the next prompt. Detects an `{"unsupported": true, "reason": ...}` sentinel for out-of-scope requests (intraday, options, multi-asset, portfolio) and returns cleanly instead of forcing a malformed IR.
- `defaults.py` — `apply_defaults(sparse_ir) -> (full_ir, assumptions)`. The only place in the system that invents values for unstated fields. Documented defaults: RSI period 14, SMA/EMA period 20, indicator source `close`, asset class `equity`, position `{direction: long, size: full}`, risk `null`, and exit defaults to a sentinel condition (`close < close`, structurally valid but always false) meaning "never explicitly closed." `asset.ticker` and `entry` have no default — missing either raises `DefaultingError` rather than guessing the one thing that defines the strategy.
- `renderer.py` — `render_confirmation(full_ir, assumptions) -> str`. Pure function, no network/LLM. Walks the *same* IR object the interpreter will run and renders the strategy in English, then splits "You specified" vs. "I assumed (you didn't specify these)" straight from the `assumptions` list `apply_defaults` produced.
- `service.py` — orchestration. `translate(nl)` and `correct(nl, prior_ir, fix)` only ever produce `(ir, assumptions, restatement)`; `confirm(ir, price_data)` is the sole place `run_ir_backtest` is invoked, and it re-validates the IR against the schema first (defence in depth, matching the interpreter's own pattern from Phase 2).
- 32 new tests across `test_translation_defaults.py`, `test_translation_renderer.py`, `test_translation_translator.py`, `test_translation_service.py` — all mock the LLM via an injected `FakeLLMClient`; none hit the real Anthropic API. Total now 76, all green.

**New dependency:** `anthropic==0.74.1` (added to `requirements.txt`; installs cleanly on Python 3.14.2 here).

---

### Security boundary (still holds, restated for Phase 3)

The LLM's only output in this pipeline is JSON text, parsed with `json.loads`. Nothing in `translator.py`, `defaults.py`, `renderer.py`, or `service.py` calls `exec`/`eval` on anything the model produces, and none of them touch vectorbt directly — `service.confirm()` hands the validated IR to `run_ir_backtest`, which routes through `interpreter.py`'s existing whitelist (unchanged from Phase 2). Phase 3 adds a network call and a JSON parser in front of an already-safe pipeline; it does not move the trust boundary.

---

### Why the renderer is a deterministic function, not a second LLM call

The confirmation step exists so the user can catch a mistranslation before a backtest runs on bad assumptions. If the restatement were generated by a second model call, two failure modes open up: the second call could itself misdescribe the IR (model error compounding model error), and — worse — there's no guarantee the text shown to the user and the IR actually executed stay in sync, since they'd come from two independent generations. By making `render_confirmation` a pure function of the exact `full_ir` object that `confirm()` later passes to `run_ir_backtest`, "what you confirm is what runs" is a structural property of the code path, not a claim that could silently go stale.

The same reasoning is why `apply_defaults` lives in our code rather than being left to the model: the system prompt tells the LLM to *omit* fields it isn't sure about (producing a "sparse IR"), and a deterministic function — not the model — decides what to fill in. This means the "I assumed" list shown to the user is generated from the same code path that actually fills those fields, so the model has no opportunity to hide an assumption or claim it specified something it didn't.

**Validation timing:** the original design called for "validate the LLM's JSON against the schema" directly, but the sparse-IR convention means the raw model output usually *won't* pass the strict schema (optional fields are deliberately missing). The retry loop therefore validates the *defaulted* IR (`apply_defaults` → `validate_ir`) on each attempt — so a schema or defaulting failure still produces the exact error text fed back into the re-prompt, just measured after defaulting rather than before it.

**Fields mentioned in the original Phase 3 brief that don't exist in the Phase 2 IR schema** (date range, cost model, timeframe) were not given defaults here — the schema has no such fields; date range/costs are applied later by `service.confirm()` (retail cost model: `fees=0.0`, `slippage=0.0005`, matching `phase1_slice.py`) and timeframe is fixed to daily bars by v1 scope, not by the IR.

---

## 2026-06-19 — Phase 2: strategy IR + safe interpreter

**New files:**
- `backend/app/translation/strategy_ir.schema.json` — formal JSON Schema (draft 2020-12) for the strategy intermediate representation.
- `backend/app/translation/interpreter.py` — safe interpreter: IR dict → vectorbt-ready signals.
- `backend/tests/test_ir.py` — 21 new tests; total now 43, all green.

**New additions to existing files:**
- `app/engine/indicators.py`: `sma(close, period)` (rolling mean) and `ema(close, period)` (pandas `ewm`, alpha=2/(period+1), no SMA seed).
- `app/engine/backtest.py`: `run_ir_backtest(ir, price_data, fees, slippage)` — generic counterpart to `run_rsi_backtest`, wires interpreter → vectorbt.
- `requirements.txt`: `jsonschema==4.26.0`.

---

### Security boundary (restated and formalised)

`backend/app/translation/interpreter.py` is the **sole code path from LLM-generated IR → vectorbt signals**. No `exec`, no `eval`, no dynamic dispatch. The interpreter enforces two independent layers of whitelisting:

1. **Schema layer** (`validate_ir`): `jsonschema.validate` against `strategy_ir.schema.json` rejects any IR that contains an unknown indicator `type` (enum: `["RSI","SMA","EMA"]`) or unknown `op` (enum of 6 operators). This is the first gate.

2. **Interpreter layer** (defence in depth): even if a malformed IR somehow bypasses schema validation, `interpret_ir` re-checks every indicator type and every operator against `_ALLOWED_INDICATOR_TYPES` / `_ALLOWED_OPERATORS` frozensets before computing anything. Unknown values raise `IRInterpreterError`.

Operand resolution is a dict lookup: a string operand is looked up in `indicator_series` (computed from the IR) and then in `price_series` (OHLC columns). If it matches neither, `IRInterpreterError` is raised. There is no fallback that would allow an attacker-controlled string to reach any Python interpreter primitive.

`crosses_above` / `crosses_below` are implemented as pandas boolean series operations (`shift(1)` + comparison), not as string-evaled expressions.

---

### IR design decisions

**Why a recursive condition tree (`all_of` / `any_of` / comparison) instead of a flat list?**
- Flat lists can only express AND of comparisons. A tree supports compound strategies like `(RSI<30 AND SMA50>SMA200) OR (close < previous_low)` without schema changes.
- The recursion depth is bounded by the schema (`minItems: 1` prevents infinite nesting in practice) and the interpreter evaluates it non-recursively enough to be auditable.

**Why are indicator IDs user-defined strings (not enumerated in the schema)?**
- The schema cannot know what indicator IDs the LLM will generate (`"rsi14"`, `"rsi_signal"`, etc.). The schema enforces the *shape* (must match `^[a-zA-Z][a-zA-Z0-9_]*$`) and the interpreter enforces *resolution* (every string operand must match a known ID at runtime).

**Why does `compute_ir_warmup` use `period + 1` for RSI but `period` for SMA/EMA?**
- `wilder_rsi(period=p)` produces its first non-NaN value at bar `p` (it seeds with a SMA of the first `p` changes, so it needs `p+1` bars). After the no-lookahead shift, the first actionable signal is at bar `p+1`. Warmup = `p+1`.
- `rolling(p).mean()` produces its first non-NaN at bar `p-1`. After shift, first actionable at bar `p`. Warmup = `p`. This matches the Phase 1 convention exactly for RSI(14) → warmup = 15.

**Why is `risk` optional and nullable (not required)?**
- v1 has no stop-loss/take-profit interpreter support. Making `risk` required would force every IR to carry a key the interpreter ignores; making it optional/nullable is honest about its v1 status.

**Regression gate (`test_ir_regression_matches_hardcoded_rsi_strategy`)**
Uses the same deterministic synthetic oscillating series as `test_backtest.py` (no network). The IR path (`run_ir_backtest`) must produce values identical (to `rel=1e-9`) to the hardcoded `run_rsi_backtest` path on the same data across **all six `BacktestResult` fields**: `total_return`, `num_trades`, `start`, `end`, `max_drawdown`, `sharpe_ratio`, and `win_rate`. A `_assert_approx_or_nan()` helper handles the NaN case (win_rate is NaN when num_trades==0) without pytest.approx false-failing.

**Execution-price alignment test (`test_ir_regression_with_distinct_open_close`)**
A second regression test repeats the same six-metric gate on an OHLC frame where Open is 0.5% above Close (High=Open×1.001, Low=Close×0.999; OHLC ordering holds). When Open==Close any bug that accidentally uses Open instead of Close for RSI computation or order fill is invisible by construction; with a spread, such a bug produces different RSI values → different signals → assertion failure. Both paths must agree because both use Close exclusively.

**Compound subset test non-vacuity**
The flat oscillating series kept SMA50 ≈ SMA200 (flat long-run mean), so the AND condition (RSI<30 AND SMA50>SMA200) in `_COMPOUND_IR` never fired and the subset check trivially passed on an empty set. The test now uses `_uptrend_then_crash_close()` (280-bar gentle uptrend + 70-bar −2.5/bar crash): SMA50 >> SMA200 through the early crash while RSI dives to ≈0, guaranteeing compound entries fire. `assert compound_entries.sum() > 0` is added as an explicit non-vacuity guard.

**Fix 5 (SPY snapshot) — skipped**: reproducing the live Phase 1 headline numbers (265.99% total return, 16 trades, 0.67 Sharpe) without a network call would require bundling ≈4 000 rows of SPY OHLCV into the repo and refreshing them as more bars accumulate. Deferred.

---

## 2026-06-19 — Phase 1 addendum: buy-and-hold benchmark

Added a reusable `compute_buy_and_hold_metrics(close, warmup, fees, slippage, init_cash) -> BacktestResult` to `app/engine/backtest.py`. It trims the same `warmup` bars as the strategy so the comparison window is identical, applies the same vectorbt cost model (entry slippage on the single buy, no exit since the position is never closed), and returns `BacktestResult` with `win_rate=nan` / `num_trades=0` (trade stats are not meaningful for a single held position).

`phase1_slice.py` now prints three blocks — strategy (with retail costs), strategy (idealized), buy-and-hold — followed by a one-line verdict of annualized excess return and whether the strategy beat or lagged B&H.

**Three new tests (22 total, all green):**
- `test_buy_and_hold_window_matches_strategy` — B&H `start`/`end` matches strategy's effective window on the same close series.
- `test_buy_and_hold_trade_stats_are_not_applicable` — confirms `num_trades == 0` and `win_rate` is NaN.
- `test_strategy_lags_buy_and_hold_on_trending_series` — uses a steadily rising synthetic series where RSI never crosses 30 (strategy never enters, return ≈ 0%) to assert strategy annualized return < B&H annualized return.

## 2026-06-14 — Phase 0/1 kickoff: scaffold, dependency pins, security boundary

**Repo scaffolded from scratch.** No prior `README.md`/`LOG.md`/`docs/` existed,
so they were created as part of this session (per the build prompt's
fallback instruction for a fresh directory).

**Python environment:** the only Python available is **3.14.2**. This is
newer than `vectorbt`'s historically-tested range, so the full dependency
chain was installed and smoke-tested before locking versions. Result: it
works cleanly, including numba JIT compilation. Pinned in
`backend/requirements.txt`:

- `vectorbt==1.0.0`
- `numpy==2.4.6`
- `pandas==2.3.3`
- `numba==0.65.1`
- `llvmlite==0.47.0`
- `scipy==1.17.1`

Verified with a `Portfolio.from_signals` smoke test (synthetic price series,
fees + slippage set) — JIT-compiled numba functions ran without error and
produced sane total return / Sharpe values. `yfinance` data fetch for SPY
(2015–2024, 2264 daily bars) also verified working.

**Note on `yfinance`:** recent versions return a `MultiIndex` column DataFrame
(`('Close', 'SPY')` etc.) even for a single ticker. The market-data layer
flattens this to a simple `Open/High/Low/Close/Volume` frame.

**Security boundary (restated from the build prompt):** the LLM translation
layer (Phase 3+) will produce a JSON intermediate representation only. A safe
interpreter (`backend/app/engine/`) is the sole code path from IR → vectorbt
signals. `exec`/`eval` on model output will never be used. This is a hard
requirement, not an optimization to be relaxed later.

**`docs/architecture.png` → `docs/architecture.md`:** the prompt referenced a
PNG architecture diagram from "earlier scoping" that doesn't exist in this
fresh repo. Substituted a text/ASCII diagram in `docs/architecture.md`
(same content as the prompt's architecture section) — can be replaced with a
rendered image later without changing structure.

## 2026-06-14 — Phase 0 complete

- **Backend:** FastAPI skeleton (`backend/app/main.py`) with `GET /health` →
  `{"status": "ok"}`. Package layout for `translation/`, `data/`, `engine/`,
  `engines/naive/`, `robustness/`, `storage/` created (empty, populated in
  later phases). `pytest` passes (`tests/test_health.py`).
- **Frontend:** `create-next-app` skeleton in `frontend/` — Next.js 16.2.9
  (App Router, Turbopack), TypeScript, Tailwind v4, ESLint. `npm run build`
  succeeds. Added `turbopack.root` to `next.config.ts` because Next.js was
  picking up an unrelated `package-lock.json` in the parent home directory
  as the workspace root.
- **Environment note:** in Git Bash (and this session's shells generally),
  `ComSpec` is unset, which makes `npm run <script>` crash with
  `ERR_INVALID_ARG_TYPE`. Documented the workaround in the README. This is an
  environment quirk, not a project bug — `next build`/`next dev` invoked
  directly work fine.

## 2026-06-14 — Phase 1 complete: dumbest end-to-end slice

Hard-coded strategy (buy SPY when RSI(14) < 30, sell when RSI(14) > 70),
fetched via yfinance, run through vectorbt. `python -m app.phase1_slice`
prints metrics with and without retail costs. 19 tests pass
(`pytest`, `backend/tests/`).

**New modules:**
- `app/data/market_data.py` — `fetch_daily_bars()`: adjusted-close OHLCV via
  yfinance, flattens the MultiIndex columns recent yfinance versions return,
  validates min bar count and rejects suspicious gaps (>10 calendar days).
- `app/engine/indicators.py` — `wilder_rsi()`.
- `app/engine/signals.py` — `rsi_threshold_signals()` (raw conditions) +
  `shift_for_next_bar_execution()` (the no-lookahead shift).
- `app/engine/backtest.py` — `run_rsi_backtest()`: wires indicators → signals
  → `vbt.Portfolio.from_signals()` → `BacktestResult`.

**Design decisions (the correctness requirements, addressed):**

1. **No lookahead bias.** Convention: *signal computed from bar i's close →
   executes at bar i+1's close*. Every raw condition (`rsi < 30`, `rsi > 70`)
   goes through `shift_for_next_bar_execution()` before vectorbt sees it
   (vectorbt fills at the same bar's close by default, so shifting first is
   what makes this next-bar). `test_signals.py::test_no_lookahead_entry_executes_on_bar_after_signal`
   constructs a price series where same-bar vs next-bar fill prices differ
   and asserts the fill is the next-bar price.

2. **Wilder's RSI**, not SMA-of-gains/losses. `wilder_rsi()` seeds the
   average gain/loss with an SMA of the first `period` changes, then applies
   the recursive `(prev*(period-1) + current) / period` smoothing — the same
   "RMA" definition TradingView's `ta.rma()`/built-in RSI uses.
   `test_indicators.py` checks it against an independently-written recursive
   reference implementation, bounds (0-100), saturation on monotonic
   series, and that it diverges from a naive rolling-SMA RSI after the seed
   bar.

3. & 4. **Entry-price tracking / stop-loss persistence** — not yet
   applicable: the Phase 1 strategy has no stop-loss. vectorbt's
   `Portfolio.from_signals` tracks entry price internally and exposes it via
   `trades.records_readable`. Dedicated tests land in **Phase 2** once the IR
   adds `stop_loss`/`take_profit`, using vectorbt's `sl_stop`/`tp_stop`
   (which are entry-price-relative and persist until a fresh entry signal —
   exactly what's required).

5. **Warmup / lookback.** RSI(14) is undefined for the first 14 bars, and the
   no-lookahead shift consumes one more — `run_rsi_backtest` drops the first
   `rsi_period + 1` bars and returns the *actual* tested date range
   (`BacktestResult.start`/`.end`), which `phase1_slice.py` prints. Verified
   by `test_warmup_window_drops_first_period_plus_one_bars`.

6. **Transaction costs.** `run_rsi_backtest` takes `fees`/`slippage` and is
   run twice in `phase1_slice.py` — once at Robinhood-tier retail (0
   commission, 5bps slippage) and once idealized (no costs) — so the cost
   impact is visible side by side.
   `test_costs_reduce_returns_relative_to_no_cost_baseline` asserts the
   cost-adjusted run never beats the no-cost run.

7. **Data sanity.** `fetch_daily_bars` uses `auto_adjust=True` (splits/
   dividends handled via adjusted close), requires ≥252 bars, and rejects
   gaps >10 calendar days. Tested with synthetic data (no live-network
   dependency for the validation logic) plus one live integration test
   against real SPY data.

**Annualization convention.** yfinance's daily index has no fixed pandas
`freq` (weekend/holiday gaps), so vectorbt's own `annualized_return()` /
`sharpe_ratio()` can't infer a `year_freq` and raise. Instead,
`annualized_return = (1 + total_return) ** (252 / num_bars) - 1` and
`sharpe = mean(daily_returns) / std(daily_returns) * sqrt(252)`
(risk-free rate = 0 for v1) — the standard 252-trading-day convention.

**Naive baseline engine (`app/engines/naive/`)** — still empty. The build
prompt says to port the user's existing hand-rolled RSI backtester here as a
comparison baseline; that needs the user's existing code, so it's deferred to
Phase 2 (when the IR/interpreter exist and the "run both engines, report
divergence" script makes sense).

**Live Phase 1 numbers (SPY, 2010-01-26 to 2026-06-12, 4136 bars fetched):**
16 trades either way; with 5bps slippage: total return 265.99% / annualized
8.26% / Sharpe 0.67 / max drawdown -28.32% / win rate 93.75%. Without costs:
271.89% / 8.36% / 0.68 / -28.32% / 93.75%. (Numbers will drift as more bars
accumulate over time — this is a snapshot, not a target to match.)

## 2026-07-15 — Phase 12: Deployment (backend to Railway, frontend to Vercel)

NLSB is live. Getting there was less about new code than about discovering
which assumptions only hold on my own machine — every failure in this phase
was configuration meeting reality, and each one taught the same lesson from
a different angle: exactness is everything at a boundary.

**Getting the repo public first.** The remote turned out to hold an older,
unrelated history, so making local canonical meant a force-push — but not
before rescuing the one asset only the remote had (the architecture
diagram) and running a secret scan across all history. The scan's single
hit was the deliberately fake key inside the health endpoint's own
leak test, which is the right kind of grep result. Force-push is normally
the reckless option; with no collaborators and strictly-superseded remote
work, it was the correct one. The moment before first publish is the one
free chance to have never leaked a secret — scan before push, not after.

**CI's first real run failed honestly.** A lint error (setState-in-effect
in the reduced-motion hook) that "passed" locally had never passed at all —
the local run piped output through `tail` and read the pipe's exit code,
not eslint's. The fix was better than the workaround: `useSyncExternalStore`
is the purpose-built primitive for subscribing to a media query, and it
removed a mount-time double render while satisfying the rule. Lesson twice
over: check the exit status you think you're checking, and when a linter
complains about a pattern, sometimes the pattern really is the problem.

**Deploy failures, in order of appearance:** Railpack built a Python-less
container because the root directory wasn't set (a monorepo isn't
self-announcing); the health endpoint reported `anthropic_key_present:
false` because dashboard variables are the production replacement for
`.env` and nobody had filled them in — that field existing in the health
check is exactly why it exists; the frontend 404'd its own domain because
the API base URL was set without `https://`, which silently turns an
absolute URL into a relative path; and CORS rejected the first real
cross-origin call because the allowlisted origin was a Vercel per-branch
alias while the browser sat on a per-deployment hash URL. Origins match
exactly or not at all — the allowlist wants the canonical production
domain, and so does the address bar.

**Also closed:** FastAPI's auto-docs (`/docs`, `/redoc`, and — the one
people forget — `/openapi.json`) are now disabled in production behind
`NLSB_ENV`, matching the existing env-var family. An interactive console
inviting strangers to script against the API bypasses the gate flow for
zero upside. Suite 239 → 241, with the test reloading the module cleanly
so no other test file inherits production mode.

The friendly-error layer earned its keep on day one: its first production
save turned a raw HTML 404 dump into a calm one-line message with the guts
collapsed under "technical details." Built two sessions ago on a hunch;
vindicated before launch.

Next: the flow's loading and reset UX, then mobile.

## 2026-07-19 — Phase 13: Flow UX (loading view, reset) and mobile pass

Two gaps a stranger would hit in their first minute: during a run, progress
text rendered beneath a still-visible input instead of taking the stage;
and after results, there was no way to run another strategy short of
finding the nav wordmark.

**Loading became a real phase.** `translating` and `confirming` now unmount
the input/gate surface entirely and mount a centered loading view hosting
the same staged-progress indicators — same stages, same elapsed counter,
still no fake percentages. The subtlety this forced was state-preserving:
unmounting the input destroys its text, so the submitted strategy now rides
through the reducer as a `draft` field, and a failed translate hands back
the input with the user's words intact. `correcting` deliberately stayed
in-place — a disabled correction box inside the gate is the right treatment
for an in-gate sub-loop.

**Reset is a state-machine citizen.** "Run another backtest" dispatches a
single `RESET` action returning to initial state. Because the results
surface is gated on `phase === "results"`, stale results structurally
cannot survive the transition — asserted, not hoped. The button lives in
the flow, after the renderer, keeping the renderer a pure display of
backend judgment.

**The mobile pass found exactly one true overflow** — the gate's
side-by-side date inputs at 360px — which now stack below `sm:`. Everything
else was fitting: tables gained `overflow-x-auto` wrappers so narrow
screens scroll the table inside its card rather than the page; every
action and chip gained 44px touch targets on mobile; the nav got the
`-m-3 p-3` trick, growing thumb hit-areas with zero layout shift. Desktop
is visually unchanged by construction — base styles are mobile, `sm:`
restores the desktop values. The disclaimer stays `text-xs` on purpose:
legal fine print earns exactly that much visual weight.

Suite: frontend 108 → 122 across both passes (+6 flow UX, +8 responsive
mechanics), all prior tests unchanged — no pinned assertion touched.
tsc, eslint, next build clean throughout.

Next: on-device verification, production confirm wall-clock, analytics
toggle, custom domain decision — then the launch post.

## 2026-07-22 — Analytics, SEO chrome, and a dependency that wasn't declared

Two pieces of pre-launch instrumentation, plus a lesson about what
"it builds on my machine" is worth.

Vercel Analytics and Speed Insights went in so launch day produces real
numbers instead of an anecdote. The trap they carried: both were imported
in application code before either was declared in package.json, so the
build was broken at those commits and would have failed the Vercel deploy.
It surfaced only when a later session ran the full build. The rule that
would have caught it is the one already in force everywhere else here —
green before handback, and the build is part of green. A commit that
passes tests but not `next build` isn't green, it's untested.

The SEO/social layer landed clean: metadataBase pinned to the production
origin, complete OpenGraph and Twitter tags reusing the existing
title/description verbatim rather than inventing new marketing copy, a
code-generated OG card in the site's dark register, plus sitemap.ts and
robots.ts. Every canonical and OG URL is absolute to the production
domain by design — preview deployments must never get indexed under the
wrong host, and a relative canonical is exactly how that happens.

The OG card is the piece with the worst failure mode: it's invisible
until someone shares a link, and then it's the first thing they see.
Worth verifying by hand rather than trusting the build.

Suite: [FINAL BACKEND] / [FINAL FRONTEND], tsc, eslint, next build clean.

Next: point the real domain at it.

## 2026-07-23 — Domain cutover to deflate.app, and search indexing

The site moved to its own domain, which turned out to be a good test of
whether the deployment's moving parts were actually understood or just
happened to be working.

Attaching the domain broke the app immediately, in the way it should
have: the browser's origin changed, and the backend's CORS allowlist
still named the old Vercel host. Origins match exactly or not at all —
scheme included, no trailing slash, apex and www distinct. The fix was a
one-variable change on the backend host with no rebuild, because the
allowlist is read at startup rather than compiled in. Worth noting the
asymmetry that keeps catching me out: frontend env vars are inlined at
build time and need a redeploy to change, backend ones are read at
runtime and don't. Same word, two different lifetimes.

A related non-bug: preview deployments still fail CORS, since their
hostnames are ephemeral and deliberately not allowlisted. That's correct
behavior — a preview build shouldn't be able to spend the production API
budget — but it looks like a break if you forget why.

Search Console: property verified, sitemap submitted [after Google's
sitemaps field rejected a relative path and wanted the absolute URL —
the Domain property type doesn't assume a scheme], all three indexable
routes submitted for indexing. Being honest about what this buys:
nobody is searching for an honest backtester yet, so search isn't the
distribution channel. The point is that when someone hears the name and
looks it up, the real thing comes back.

Next: [icon set, link-preview verification, on-device runthrough, and
the confirm wall-clock — still unmeasured].

## 2026-07-27 — The rate limiter was counting the proxy, not the visitor

**Lesson — a fail-safe bug is still a bug, and it hides in the direction
you don't test.** The per-IP limiter has been keying on
`request.client.host` since Phase 8A, which is correct on localhost and
wrong the moment anything sits in front of the process. Behind Railway's
edge proxy that address is the *proxy* for every visitor, so all traffic
landed in one bucket: ten translates a minute for the entire internet,
with real users blocking each other. It never showed up in testing
because the failure is over-protection — nothing errors, nothing gets
overspent, the graph just looks quiet. The class of bug worth watching
for is the one whose symptom is "fewer requests than expected."

Worth being precise about why uvicorn didn't already handle this.
`ProxyHeadersMiddleware` ships enabled, but `--forwarded-allow-ips`
defaults to `127.0.0.1`, and Railway's proxy connects from `100.0.0.0/8`
— so the middleware saw an untrusted peer and correctly left `scope`
alone. Enabled but not trusting is indistinguishable from off unless you
read the trust list. "The framework handles it" is a claim to verify,
not inherit.

The fix is a `client_identity` key function that takes the leftmost
`X-Forwarded-For` entry, gated behind `NLSB_TRUST_PROXY_HEADERS`
(default off) so local dev is byte-identical and the header is only
believed where a known proxy actually sets it. The gate is the whole
design: an unconditional trust of that header on a directly-reachable
process hands every client a free bucket-rotation knob.

Two calls that came out of reading the platform docs rather than
guessing. `X-Real-IP` was on the table as a secondary source and is
*not* in the code — Railway currently sets it to the CDN edge IP when
traffic routes through the CDN, so it would have quietly rebuilt the
exact shared-bucket bug the change exists to kill. And leftmost vs
rightmost XFF has Railway's own forums arguing both sides; leftmost is
their current recommendation and is stable across hop-count changes,
rightmost is spoof-proof but breaks when the topology moves. Took
leftmost, wrote the tradeoff into the docstring: a determined attacker
can rotate that header, and that's accepted, because the per-IP limit
was never the thing protecting spend. The global daily circuit breaker
is, and it counts every request regardless of who claims to send it.
Per-IP exists to stop accidents and casual overuse, and it still does.

The test that justifies the whole change: two requests with different
`X-Forwarded-For` values, one exhausting its limit, the other still
getting a 200. Its twin pins the old behavior with the gate off — both
collapsing into one bucket — so the diff between them *is* the bug,
asserted in both directions.

Suite: backend 250 → 263 (+13: 11 key-function unit cases, 2 bucket-
isolation integration tests), every prior test unchanged, all green. No
new dependencies, no frontend diff. `NLSB_TRUST_PROXY_HEADERS=true` is
committed in `render.yaml` and documented in DEPLOY.md — on Railway it
has to be set in the dashboard, and until it is, the fix is inert.

Next: set the var on Railway and confirm two devices get separate
buckets in production — then the launch post.

## 2026-07-28 — Phase 12A: the LLM cost boundary, and what was under it

**Lesson — a spend cap is only as honest as the layers beneath it.** The
daily circuit breaker counted one thing and LOG.md described it as
another. It counts *requests allowed to call the model*; the translator
retries up to three times per request; and the Anthropic client was
constructed bare, inheriting the SDK's own `max_retries=2`. Three
application retries sitting on two SDK retries meant one counted unit was
up to nine billable calls — a cap of 200 was a cap of up to 1800. The
same bareness inherited a 600-second timeout, so a single counted request
could hold one of the forty threadpool slots for half an hour. Neither
number was wrong in the code; both were invisible, because nothing in the
suite ever asserted what the layer underneath was doing. The fix is
small — pass `max_retries` and `timeout` explicitly, default 0 and 60s —
and the point is that the config now means what it says.

The breaker had a second gap, structural rather than arithmetic. It
exposed `check()` and `record()` as separate calls with real work between
them, and route handlers are sync `def`, so FastAPI runs them in anyio's
forty-thread pool. Every thread could pass the cap check before any of
them incremented, and `self._count += 1` is not atomic either. That is
now one locked `reserve()`.

Writing the test for it produced the more uncomfortable finding. The
first version — sixteen threads on a barrier, all racing a cap of one —
passed. It also passed against a faithful reimplementation of the OLD
check/record pair: zero of ten runs overshot. At CPython's default 5ms
switch interval the window between the two calls is a few microseconds,
so a thread is essentially never preempted inside it. Dropping the switch
interval to 1e-6 flipped it to ten of ten, overshooting the cap by four
to sixteen times. A concurrency test that passes against the broken
implementation is not a test, and the only way to know which kind you
have written is to go build the broken thing and run it. Production hits
that window not because it is wide but because it runs it thousands of
times.

The cache is the cheap half: identical normalized input, same model, same
prompt/schema version, bounded LRU, and a hit skips the model entirely.
The four landing-page example chips are fixed strings that were being
re-translated from scratch on every submit. Three rules keep it from
being a liability rather than a saving. Only the fully-validated success
path is stored — never a failure, never an "unsupported" verdict. A hit
re-runs the schema validator and evicts anything that no longer passes,
because a cached IR is exactly as untrusted as a fresh one; the cache is
a cost optimization and never a trust boundary. And the size is bounded
on purpose: an unbounded map keyed on arbitrary user text is a
memory-exhaustion primitive. A hit costs no daily budget, because no API
call happened — but it is still rate-limited, still cannot reach a
backtest without an explicit /confirm, and the security boundary is
unchanged: the model emits only validated IR JSON, and nothing
model-emitted is ever executed.

Gate order moved as a consequence. Budget used to be read before the
size cap and incremented after it; now that claiming is atomic, it has to
come last, or a request that was always going to be rejected consumes a
unit it can never spend. Rate limiter, then size cap, then budget —
reserved at the instant the model is about to be called.

Then the suite found something none of this was looking for. The new
tests passed alone and failed fourteen ways in the full run.
`test_docs_exposure.py` rebuilds `app.main` with `importlib.reload` to
check the production docs switch, which replaces the dependency
*functions*; any test file sorting after it alphabetically overrides a
key the live app's routes no longer reference. The override is ignored in
silence — and because `backend/.env` holds a working API key that
`load_dotenv()` picks up at import, the fallthrough is not an error. It
is a real call to the real Anthropic API, returning a real 200. The suite
was quietly spending money, and the only reason the older abuse tests
never caught it is that "abuse" sorts before "docs". The same reload also
re-registers the shared rate-limit decorator, so one request consumes
(reloads + 1) units of its per-minute budget: measured at a limit of six,
six requests get through with no reloads, three after one, two after two.
Both are test-infrastructure debt, both are reported rather than
quietly patched. What did change: a conftest guard that makes reaching
the real client an immediate, loud assertion failure instead of an
invoice.

Suite: backend 263 → 287 (+24), frontend 147 unchanged, all green;
tsc, eslint, next build clean. No frontend diff, no new dependencies.

Next: measure /confirm's wall-clock, then the concurrency limit and
request timeout that the audit flagged — the spend boundary is honest
now, the compute boundary still isn't.

## 2026-07-28 — Phase 12B: four guards, all passing, and the answer still wrong

**Lesson — every check asked the data whether it was self-consistent, and
none asked whether it was what had been requested.** The price path had
four guards: reject an empty frame, reject fewer than 252 bars, reject an
internal gap over ten days, reject a window the indicator warmup would
consume. Each is a real check and each one passes on a clean, gapless,
1500-bar frame covering 2015-2020 — including when the user asked for
2015-2026. Nothing anywhere compared the returned index against the range
that was requested. Six years of history answered an eleven-year question,
silently, and the result had no field capable of mentioning it. Four
guards is not defense in depth if all four are looking the same direction.

The two halves of the fix are separable and both matter. The coverage
guard compares realized against requested and refuses outside a tolerance
— seven days at each end, absorbing a start date that lands on a weekend
and vendor lag on the trailing edge. It refuses rather than clamps, and
that is the deliberate part: a ticker that did not exist yet is not a bug,
but quietly narrowing the window to whatever happened to exist is exactly
the failure being removed, so the message names both windows and the user
re-asks with real dates.

The other half is that every result now carries the window it ran on —
realized first bar, realized last bar, bar count, and the requested dates
beside them — unconditionally, on every path including no-exit and
untestable. Not as a diagnostic that appears when something looks wrong.
A correct run reports its window too, because a reader should not have to
already suspect a problem before being told which data produced the
answer. A product whose whole claim is honesty about what the numbers
support cannot have results that are structurally unable to say what they
were computed from.

The effective-bar floor moved from 2 to 5, and the number was measured
rather than chosen. N bars give N-1 daily returns, and the deflated Sharpe
corrects for the skew and kurtosis of those returns. Over 400 random
samples at each size: at 2 returns the sample skew is always exactly 0.000
and the kurtosis always exactly 1.000; at 3 returns the skew finally
varies but the kurtosis is always exactly 1.500; at 4 both move with the
data. Below four returns the fat-tail term in the PSR denominator is a
constant of the sample SIZE, so the deflated Sharpe was returning a
confident number that structurally could not reflect the distribution it
claimed to be correcting. That is the floor below which results are
meaningless — a different and far lower bar than the floor below which
they are uncertain, which already has a designed answer in the UNTESTABLE
verdict and was deliberately left alone.

The fetch is now bounded in all three directions it wasn't: an explicit
30s timeout (yfinance 1.4.1's download() takes one directly, so no wrapper
layer was needed), at most two retries after the first attempt with
exponential backoff, and a bounded LRU of validated frames. Worst-case
wall time is 3 x 30s plus 1.5s of backoff — 91.5 seconds, stated because
an unstated bound is not a bound. Transport failures are retried; a frame
that failed a validation guard is not, since re-asking only delays a 422
the caller can act on. Nothing that failed any guard is ever cached, and
the realized window is a pure function of the returned index, which is
what makes a cache hit report coverage identically to a fresh fetch by
construction rather than by bookkeeping.

Security boundary unchanged: the LLM emits only validated IR JSON and no
model-emitted code is ever executed. Cached price data is data, never
judgment — it is returned as a copy, and it re-enters the same validators.

The fixture regeneration was the pleasant surprise. Adding a key to a
pinned schema was expected to churn the frontend's fixture tests; the
diff came to 57 insertions and one deletion, that deletion being a comma,
and all 147 existing frontend tests passed untouched. The reason is that
those tests assert on named fields rather than whole-object equality —
a property worth noticing, because it is what made a schema addition
cheap. The dumper now fills the requested dates from the synthetic
series' own bounds, so the fixtures model what /confirm actually returns
instead of leaving those fields null.

Recording a measurement that was taken and never written down: production
/confirm wall-clock is under 15 seconds, single user, no contention,
measured by hand on the phone pass at the domain cutover. The audit was
right to flag its absence as the largest open unknown — a number that
exists only in someone's memory is not a number the project has.

Suite: backend 287 -> 321 (+34), frontend 147 -> 158 (+11), all green;
tsc, eslint, next build clean. One existing test changed meaning and is
called out rather than quietly edited: the hardcoded key set in
test_api_routes.py gained "window". It stays a literal set on purpose —
it is the only place the frontend's key names are spelled out
independently of RESULT_KEYS, so a rename fails there instead of renaming
both sides at once.

Next: the compute boundary — /confirm still has no concurrency limit and
no request timeout, and one uvicorn process with a 40-thread pool is the
whole capacity story.

## 2026-08-02 — Phase 12D: surfaces and instrumentation, before the traffic

**Lesson — instrumentation is the only work here with an expiring
window.** Every other item on the pre-flight list shares a forgiving
property: it can be fixed after it is observed failing. A missing
timeout gets added once something hangs. A wrong rate-limit key gets
fixed once users block each other. The gap is visible, the evidence
survives, the repair is always available. An un-instrumented traffic
event has none of that. If four hundred people arrive from a link and
nothing is counted, "how many actually ran a backtest" and "what
fraction accepted the gate" are not questions that get answered later —
they are answered never. That asymmetry, not urgency, is why this phase
came before the compute-boundary work that is objectively more likely to
break something.

The two events carrying the most information are gate_confirmed and
gate_abandoned, because their ratio is the only direct measurement of
whether strangers accept this product's central mechanism — being shown
what was assumed on their behalf and being asked to agree before
anything runs. Abandonment is the one with no happy-path trigger, so it
is derived twice: leaving the gate backwards, and unmounting while still
at it, which is what closing the tab looks like. With only the first,
the ratio would read silently, flatteringly high.

The rule most likely to erode later is that no event may carry the
user's strategy text, so it is enforced by shape rather than by
discipline. `sanitizeProps` whitelists bounded scalars and drops
anything longer than forty characters, which means a future call site
that passes `{ nlText }` by accident emits an event with that property
missing instead of shipping free-text user input to a third party and
waiting for someone to notice. The end-to-end test walks a full funnel
and asserts no emitted value contains any word from the submitted
strategy.

Instrumentation sits in an effect watching `phase`, never inside a
handler, and that placement is the invariant rather than a preference.
Effects run after commit, so nothing in the observer can cause, block,
or reorder a transition even if tracking misbehaves — pinned by a test
that runs the entire flow with a sink that throws on every single event
and still reaches results with both API calls made. A tracking call
sitting inside `handleConfirm` would sit on the confirm path itself,
which is precisely how gate integrity stops being structural.

Two findings worth recording because both contradicted a reasonable
assumption. First, this Next version's error boundary prop is
`unstable_retry`, not `reset`; retry was added in 16.2.0 and the
framework's own docs say to prefer it, because `reset` re-renders the
children without re-fetching, and a boundary that most often catches a
failed fetch would just fail again. Both props are accepted, retry
preferred. Second, `next build` still prints `○ /_not-found` after a
custom `not-found.tsx` exists — that line is Next's internal route
identifier for the 404 boundary, present either way, and is not evidence
of the stock default. What actually settles it is the artifact:
`_not-found.html` now contains this site's copy, and Next's "This page
could not be found" appears nowhere in the build. Reading a route table
as a content check would have been wrong in both directions.

ESLint caught something the type checker could not: a ref written during
render. The unmount cleanup needs the last committed phase, and assigning
`phaseRef.current` in the render body is the obvious way to keep it
fresh and also a way for the ref to desync from what was actually
committed. Moved into its own effect.

Suite: frontend 158 -> 184 (+26: 9 error-surface, 17 funnel), backend
321 unchanged and untouched — zero backend diff. tsc, eslint, next build
clean. No new dependencies.

Next: the compute boundary — /confirm still has no concurrency limit and
no request timeout, and one uvicorn process with a 40-thread pool is the
whole capacity story.
