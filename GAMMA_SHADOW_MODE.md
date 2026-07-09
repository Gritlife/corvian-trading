# GAMMA_SHADOW_MODE.md

## What GAMMA_MODE controls

`GAMMA_MODE` is a persisted setting (`cts-v1-gamma-mode` in localStorage,
values `OFF | SHADOW | ACTIVE`) that governs whether Gamma is computed/shown
at all — it does **not** and structurally **cannot** control whether Gamma
affects trading, because trading (`processEngineSignals`, the paper ledger,
session state, scanner ranking) is wired only to the legacy engine, with no
gamma-related parameter anywhere in its call chain, regardless of mode.

Default: `SHADOW`. Verified by `tests/integration.test.js`. The app source
never programmatically sets it to `ACTIVE` — only a human toggling UI can.

## Mode behaviors

- **OFF**: Gamma is not fetched, not computed, not displayed. Legacy ToF
  runs exactly as before this integration.
- **SHADOW** (default): Live OCM Gamma is fetched, computed, and displayed
  in the Deck's Gamma panel. `GAMMA_PARITY_AUDIT` (when enabled) logs a
  comparison record for every evaluated ticker. Legacy signals are
  completely unaffected.
- **ACTIVE**: Currently has **no implemented behavioral difference from
  SHADOW** in this build. It exists as a labeled, auditable placeholder for
  a future, separately-reviewed integration step — the directive explicitly
  prohibits building that step now ("CATS must not be built into this
  task... DO NOT enable Gamma ACTIVE mode by default"). Selecting it today
  changes nothing except the badge shown in the UI.

## Why Shadow safety holds structurally, not just by convention

`processEngineSignals({ ticker, engine, bars, atr, ledger, execState,
account, riskProfile, sessions, currentPrices, trendGate })` — inspect the
parameter list: there is no `gamma`-anything in it, anywhere. The Deck
component's Gamma-aware hooks (`gammaAddFavorable`, `gammaTPPressure`,
`gammaExitPressure`) are computed *after* `runGammaSpine()` and are only
ever passed into the read-only `GammaSpinePanel` for display. Nothing in
`Deck` calls `setLedger` or `setExecState` directly (verified by
`tests/integration.test.js`, test 16).

This means: even if `GAMMA_MODE` were flipped to `ACTIVE` today, no trade
would fire differently, because there is no code path connecting Gamma's
output to a mutation function. Making Gamma actually influence trades would
require *new* code, not a flag flip — which is exactly the deliberate
friction the directive asked for.

## What "Shadow Comparison Record" looks like

Every time `GAMMA_PARITY_AUDIT` is enabled and a valid Gamma snapshot
exists, `buildParityAuditRecord()` produces a record with (among other
fields) `classification: "CONFIRMS" | "CONFLICTS" | "NEUTRAL" |
"UNAVAILABLE"` — comparing the legacy engine's open direction against the
Gamma Spine's alignment score, without ever changing the legacy engine's
decision. These records live in an in-memory ring buffer
(`createParityAuditLog`, capped at 500 records) — not persisted to
localStorage or the ledger, by design (this is a diagnostics view).

## Known limitation

Live OCM polling in this build is scoped to whichever ticker is currently
open in the Deck view — not all ~20 scanner tickers on every poll. Widening
that to the full scanner set was deliberately deferred (see
INTEGRATION_REPORT.md "known limitations") since it would multiply Massive
Options API call volume ~20x for a feature that's still Shadow-only.
