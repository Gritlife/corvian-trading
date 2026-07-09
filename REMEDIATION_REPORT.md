# REMEDIATION_REPORT.md — ToF V1.1 Gamma Spine Remediation

## Exact files changed

| File | What changed |
|---|---|
| `netlify/functions/lib/massive-client.js` | Auth migrated `?apiKey=` -> `Authorization: Bearer` header; added `requireMethod()`, `rateLimitCheck()`, `cacheGet`/`cacheSet`; `fetchMassive()` signature gained an `opts` param (`timeoutMs`, `cacheTtlMs`) - backward compatible, all existing call sites still work with defaults. |
| `netlify/functions/lib/ocm-engine.js` | Added `computeConfidenceBreakdown()` (decomposed, explainable confidence with completeness/freshness modifiers). `computeOcmGammaSnapshot()` now accepts `chainCompletenessModifier`/`freshnessModifier` and exposes `confidenceBreakdown` on its return. `computeConfidence()` (the old single-number function) is kept, unchanged, for backward compatibility. |
| `netlify/functions/lib/gamma-status.js` | New file. Pure, directly-unit-tested chain-completeness classification, freshness classification, and the Gamma health state machine (8 states, deterministic precedence, reason codes). |
| `netlify/functions/ocm-gamma-snapshot.js` | Rewritten to wire in chain completeness tracking (page-limit/next-URL bookkeeping), separated spot/options freshness (independent timestamps), and the gamma-status.js state machine. Method validation and rate limiting added. |
| `netlify/functions/options-chain.js` | Same completeness field set added for consistency. Method validation, caching added. |
| `netlify/functions/equity-snapshot.js` | Method validation, per-op rate limiting, response caching (TTLs chosen per data volatility: 1hr for grouped/treasury, 15-20s for bars/snapshot). |
| `netlify/functions/health.js` | Method validation added. |
| `netlify/functions/validate-live.js` | New file. Live validation harness (Phase 10) - diagnostic-only, invokes the real ocm-gamma-snapshot handler in-process for a symbol list and returns a structured report. |
| `index.html` | GammaSpinePanel extended to show: backend gammaStatus (preferred over the local Pine-port's own status when live data exists), dataMode, separated spot/options freshness with ages, chain completeness status, and OCM reason codes. No other UI changed. |
| `tests/integration.test.js` | One test (#23) updated to check the new location (gamma-status.js) of the LOW_CONFIDENCE string after the extraction - same assertion, correct file. |
| `tests/remediation.test.js` | New file. The 26 required remediation tests (30 assertions; a few directive items share one assertion where the same code path proves both). |

## Exact defects fixed

1. False-positive "GAMMA VALID" on a truncated chain - previously, hitting the 4-page pagination limit had zero effect on status or confidenceScore. Now: TRUNCATED chains can never produce GAMMA VALID (proven by test), and always carry a 0.40 confidence multiplier plus an explicit GAMMA DEGRADED - PARTIAL CHAIN status.
2. Freshness conflated spot and options data - previously, only the equity spot's timestamp fed `stale`. Now spot and options timestamps are independent measurements, combined as "worse of the two."
3. STALE_THRESHOLD_MINUTES = 15 treated a documented 15-min-delay plan as an exact SLA - replaced with named, buffered thresholds (FRESH_THRESHOLD_MINUTES = 20, DELAYED_THRESHOLD_MINUTES = 45) that don't assume delayed data always arrives at exactly 15:00.
4. Confidence score was an opaque single number - now decomposed into confidenceBreakdown: { baseScore, openInterestCoverageComponent, greeksCoverageComponent, contractCountComponent, chainCompletenessModifier, freshnessModifier, finalScore }.
5. No method validation - POST/PUT/DELETE previously reached the Massive-calling logic unchanged. Now rejected with 405.
6. Query-string API key auth - migrated to Authorization: Bearer, Massive's own documented/observed pattern, reducing key exposure in logs.

## Exact logic added

See GAMMA_STATUS_SPEC.md, CHAIN_COMPLETENESS_SPEC.md, FRESHNESS_SPEC.md for full detail. In brief: classifyCompleteness(), classifyFreshness(), combineFreshness(), computeGammaStatus() in the new lib/gamma-status.js; computeConfidenceBreakdown() in lib/ocm-engine.js.

## Test results

```
tests/ocm-engine.test.js:     22 passed, 0 failed  (pre-existing, unchanged)
tests/security.test.js:        7 passed, 0 failed  (pre-existing, unchanged)
tests/integration.test.js:    20 passed, 0 failed  (1 test updated for refactor, still same assertion)
tests/remediation.test.js:    30 passed, 0 failed  (new - covers all 26 required items)
-----------------------------------------------------
Total:                        79 passed, 0 failed
```

Baseline preserved exactly: the original 49 all still pass unmodified in
behavior (one test's file path changed to match a pure refactor, not its
assertion).

## Known limitations

1. No live network access in this environment. All 79 tests are static source-inspection or synthetic-data unit tests - see TEST_REPORT.md for what specifically remains unverified against real Massive traffic.
2. Freshness thresholds (20/45 min) are reasoned defaults, not empirically calibrated against observed real-world delay distribution - see FRESHNESS_SPEC.md.
3. Completeness confidence-penalty values (0.75/0.40) are a documented judgment call, chosen to guarantee correct ordering, not derived from a formula - see CHAIN_COMPLETENESS_SPEC.md.
4. No real user authentication exists on these endpoints - stated plainly, with a concrete recommendation, in SECURITY_LIMITATIONS.md. Rate limiting and caching are real but instance-local, not distributed.
5. validate-live.js does not cover SPX/index options - Massive supports index options via an I: ticker prefix per their docs, but the underlying-spot lookup path for indices differs from equities and was not implemented or tested in this pass. The harness explicitly reports this rather than silently omitting or faking support.
6. Large/liquid chains (SPY, QQQ) will routinely report TRUNCATED under the current 1000-contract cap - this is disclosed as expected behavior, not a bug, but it means those specific tickers may rarely if ever reach GAMMA VALID until the page limit is raised (a deliberate choice not made in this pass, since raising it changes Massive call volume/latency tradeoffs outside this remediation's scope).

## Acceptance gate - self-check against Section 14

- [x] Existing 49 tests still pass
- [x] New remediation tests pass (30/30)
- [x] Known truncated chain cannot show plain GAMMA VALID (test #5)
- [x] Unknown completeness cannot silently equal complete (test #4)
- [x] Spot freshness is separate from options freshness (tests #7, #8)
- [x] Gamma confidence exposes a breakdown (tests #13, #13b)
- [x] Gamma status exposes reason codes (tests #15, #15b)
- [x] SHADOW mode remains default (GAMMA_MODE unchanged from prior pass)
- [x] Gamma cannot mutate legacy trade actions (tests #16-21, #16-21b)
- [x] Massive secret remains server-side only (tests #24, #24b, plus original security.test.js)
- [x] Frontend contains no API secret (test #24)
- [x] Unsupported HTTP methods are rejected (tests #23, #23b)
- [x] Ticker input is validated (test #22)
- [x] Upstream errors are structured (test #25)
- [x] Live validation harness exists (validate-live.js)
- [x] Documentation states remaining limitations honestly (this file + SECURITY_LIMITATIONS.md)
- [x] Updated ZIP is returned
