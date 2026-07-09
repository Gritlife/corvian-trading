# INTEGRATION_REPORT.md — ToF V1.1 Secure OCM Live Integration

## Phase 0 — Authority check

| Field | Original (input) | Final (delivered) |
|---|---|---|
| Filename | `index.html` | `index.html` |
| Byte size | 328,775 | 341,127 |
| Line count | 6,017 | 6,219 |
| SHA-256 | `11f171c2d235ffc6975066707b6474e1775dda217ccfc1dd1c7d8921e07427d7` | `612ed6e7e55fbc66dade85000016a18dec57e343c259da9b86c6ce68bb7de4f4` |

The original was confirmed by the user as the current live deployed file
(pasted directly, matched a previously-delivered build byte-for-byte based
on structural comparison). The backend package input
(`tof-v1.1-secure-ocm-backend`) was unpacked and verified to match exactly
what was previously delivered and tested (12 files, all present).

## Exact changed sections

All changes are additive or narrowly substitutive — no component was
rewritten from scratch, no UI was redesigned.

1. **`fetchTreasuryYields()`, `fetchMassiveBars()`, `fetchSnapshot()`,
   `fetchGroupedDaily()`** — bodies replaced to call
   `/.netlify/functions/equity-snapshot?op=...` instead of
   `https://api.massive.com/...?apiKey=${apiKey}`. Signatures had their
   trailing `apiKey` parameter removed.
2. **`fetchHourlyBars()`, `fetchDailyBars()`, `fetchFiveMinBars()`,
   `fetchFourHourBars()`, `buildAvgVolume20d()`** — `apiKey` parameter
   removed (was only ever forwarded to the functions in #1).
3. **`MTSApp()`** — `polygonKey` state (`useState(() => loadJSONCts("KEY",
   ""))`) removed entirely. Every `if (!polygonKey || !loggedIn) return;`
   gate in the six existing polling `useEffect`s became `if (!loggedIn)
   return;` (mechanically verified via regex — 5 gate sites, 5 dependency
   arrays, 8 trailing-argument call sites, all updated consistently).
4. **`AccountSummary`** — `polygonKey`/`onSetPolygonKey` props removed from
   its signature and call site; `<PolygonKeyField .../>` render replaced
   with a static "Massive Data Connection: Server-managed" status card.
   `PolygonKeyField`'s component *definition* was left in place (unused,
   harmless dead code) rather than deleted, to minimize risk of an
   unrelated syntax slip in a very large single-pass edit.
5. **New**: `fetchOcmGammaSnapshot(symbol)` — calls
   `/.netlify/functions/ocm-gamma-snapshot`, adapts its response
   (`timestampUtc` ISO string → `snapshotTimestamp` epoch-ms, field renames)
   into the shape `normalizeGammaSnapshot()` already expected.
6. **New**: `GAMMA_MODE` state (`"OFF" | "SHADOW" | "ACTIVE"`, default
   `"SHADOW"`, persisted), plus a live-polling `useEffect` scoped to
   whichever ticker is open in the Deck view (60s interval, matching the
   cadence of the app's other polls).
7. **`Deck`** — now accepts `liveGammaSnapshots`, `gammaMode`, `ocmStatus`
   props; `gammaSnapshotRaw` derivation changed from "manual paste only" to
   "manual override, else live OCM snapshot, else null."
8. **`GammaSpinePanel`** — added a MODE / OCM / SOURCE status row, a
   Dealer Pressure / Expected Behavior interpretation block, and a
   Freshness/Coverage block sourced from the live OCM response, all
   visually and structurally separate from the legacy WHERE/WHEN cards
   above it in `Deck`.
9. **`buildParityAuditRecord()`** — extended with `classification`
   (`CONFIRMS | CONFLICTS | NEUTRAL | UNAVAILABLE`) and
   `distance_to_flip_pct`, satisfying the directive's Shadow Comparison
   Record field list; the existing `disagreement_flag` mechanism was kept
   for backward compatibility with the already-shipped
   `GAMMA_PARITY_AUDIT` toggle.
10. **`ScannerStatus`** — the disclaimer text "Scanner shows top 20 S&P
    stocks..." (false — `EXPANDED_UNIVERSE` includes BITO, WULF, and ~650
    non-S&P-exclusive tickers, confirmed in the Phase 1 audit) corrected to
    accurately describe the Expanded Universe.
11. **`STORAGE_CTS`** — added `GAMMA_SNAPSHOTS` and `GAMMA_MODE` key
    mappings (both were already being used via `loadJSONCts` with
    unmapped-key fallback before this change; this formalizes them, no
    data loss).

## Exact preserved sections (unchanged)

Every one of these was diffed for presence and left untouched: `Scanner`,
`Active`, `WatchlistView`, `Library`/`LibraryArticleDetail`, `Ring`,
`ActionCell`, `ConfirmModal`, `BottomTabBar`, `PaperLedger`,
`RiskAssessmentWizard`, `RiskProfileCard`, `PaperAccountCard`,
`SessionCreateForm`, `SessionListCard`, `MarketHeartbeat`, `LoginPage`,
`computeMMGEngineState` (the entire B2O/S2O/ADD/TP/S2C/B2C state machine —
zero references to anything gamma-related, verified by
`tests/integration.test.js`), `processEngineSignals` (the paper-trading
execution loop — same zero-gamma-reference verification), `computeScores`,
`topAction`, all Five Legends logic (Livermore/Wyckoff/Simons/
Seykota/Dennis), RVOL calculation, session logic, dark mode, mobile
`max-w-md` responsive layout, and all CSS/Tailwind styling.

## Endpoint mapping

| Old (browser → Massive directly) | New (browser → same-origin proxy) |
|---|---|
| `GET https://api.massive.com/fed/v1/treasury-yields?...&apiKey=X` | `GET /.netlify/functions/equity-snapshot?op=treasuryYields` |
| `GET https://api.massive.com/v2/aggs/ticker/{t}/range/...&apiKey=X` | `GET /.netlify/functions/equity-snapshot?op=bars&ticker=...` |
| `GET https://api.massive.com/v2/snapshot/.../tickers?tickers=...&apiKey=X` | `GET /.netlify/functions/equity-snapshot?op=snapshot&tickers=...` |
| `GET https://api.massive.com/v2/aggs/grouped/.../{date}?apiKey=X` | `GET /.netlify/functions/equity-snapshot?op=grouped&date=...` |
| *(did not exist)* | `GET /.netlify/functions/options-chain?symbol=...` (available, not yet called directly by the frontend — see limitations) |
| *(did not exist)* | `GET /.netlify/functions/ocm-gamma-snapshot?symbol=...` (called by `fetchOcmGammaSnapshot`) |
| *(did not exist)* | `GET /.netlify/functions/health` |

## Security migration

See `SECURITY.md` (backend) — updated summary: the frontend now contains
**zero** references to `MASSIVE_API_KEY`, **zero** `apiKey=` query-string
construction, and **zero** direct `api.massive.com` calls (all three
verified by automated test). The key entry UI (`PolygonKeyField`) is no
longer rendered anywhere. `localStorage["mts-v19-polygon-key"]` and
`localStorage["cts-v1-polygon-key"]` are simply never written to again by
this build (not actively wiped, per the "preserve storage compatibility"
principle — a stale value sitting there is inert, not a live secret in
use).

## Gamma Shadow Mode behavior

See `GAMMA_SHADOW_MODE.md` for the full explanation. Summary: `GAMMA_MODE`
defaults to `SHADOW` and the app source never sets it to `ACTIVE`
programmatically. Shadow safety is structural, not just conventional —
`processEngineSignals` (the only function that ever writes to the paper
ledger) has no gamma-related parameter anywhere in its signature or body,
verified by automated test.

## Test results

```
tests/ocm-engine.test.js:    22 passed, 0 failed
tests/security.test.js:       7 passed, 0 failed
tests/integration.test.js:   20 passed, 0 failed
—————————————————————————————————————
Total:                       49 passed, 0 failed
```

Coverage against the directive's 24-item Phase 14 list: items 1-24 are
covered by `tests/integration.test.js` (mapped 1:1 in most cases; a few
were combined where the underlying property is the same check, e.g.
10-15 collapse into one "processEngineSignals is gamma-blind" assertion
since that single structural fact implies all six legacy signal types are
equally unaffected).

## Known limitations

1. **No live network in this environment.** All tests are static source
   inspection or synthetic-data unit tests. Nothing here has been proven
   against a live browser hitting a live Netlify deployment with a real
   Massive key. See TEST_REPORT.md.
2. **Live OCM polling is scoped to the open Deck ticker only**, not all
   ~20 scanner tickers. Widening this would multiply Massive Options API
   call volume roughly 20x for a still-Shadow-only feature — deliberately
   deferred rather than silently done. Phase 7's "for every legacy signal
   event, record Gamma context" is therefore only fully live for whichever
   ticker a human has open in the Deck at signal time; it is not yet
   running continuously across the whole scanner.
3. **`options-chain.js` (raw chain proxy) is deployed but not yet called
   directly by the frontend** — the frontend only calls the higher-level
   `ocm-gamma-snapshot` endpoint, which internally composes the options
   chain fetch. This satisfies the directive's normalized-consumption
   requirement ("Do not recalculate a conflicting second Gamma model in
   the browser") but means `options-chain.js`'s raw-data path is currently
   backend-only/unused by the UI.
4. **`PolygonKeyField` component definition still exists in source**
   (unused, unreachable) rather than being physically deleted — a
   deliberate choice to minimize edit risk in a 6,000+ line single file;
   it renders nothing and reads no state.
5. **The 20-day average-volume cache warmup (`buildAvgVolume20d`) and
   session-universe label ("S&P 500 (locked)" in `SessionCreateForm`)**
   were left untouched — they're a related but distinct mislabeling
   (session creation, not the scanner) outside this pass's explicit scope;
   flagged here rather than silently fixed or silently ignored.

## Blockers encountered

None that stopped the integration — the two blocking questions from the
prior session (authority check, Massive Options plan tier) were both
resolved before this phase began.

## Rollback instructions

See `MIGRATION_REPORT.md`.
