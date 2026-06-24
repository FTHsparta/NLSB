# Build Log

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
