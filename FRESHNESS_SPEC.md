# FRESHNESS_SPEC.md

Source of truth: `classifyFreshness()` / `combineFreshness()` in
`netlify/functions/lib/gamma-status.js`.

## Why spot and options freshness are tracked separately

A fresh equity quote proves nothing about how current the options chain is
— they come from different upstream computations on Massive's side, and
under a delayed-data plan there is no guarantee they lag by the same
amount. Prior to this remediation, Gamma staleness was derived only from
the equity spot's timestamp; this was a real correctness gap.

## Timestamp sources

- **Spot**: `day.last_updated` (or `.updated`) from the equity snapshot
  endpoint, nanoseconds since epoch.
- **Options**: the MOST RECENT `day.last_updated` across all returned
  option contracts. This is the only per-contract timestamp signal this
  endpoint provides; there is no single chain-level "as of" timestamp.
  `contractsWithTimestamp` reports how many contracts actually carried one
  — if it's 0, `optionsAsOfUtc` is `null` and `optionsFreshnessStatus` is
  `UNKNOWN`, never silently inherited from the spot timestamp.

## Thresholds

The confirmed account plan (Options Starter + Stocks Starter) is
documented by Massive as "15-minute delayed." We do not treat that as an
exact SLA (`STALE_THRESHOLD_MINUTES = 15` in the pre-remediation code was
exactly this mistake — assuming delayed data arrives at precisely 15
minutes). Named thresholds, with buffer built in:

```
DOCUMENTED_DELAY_MINUTES = 15   // what the plan promises, not a guarantee
FRESH_THRESHOLD_MINUTES  = 20   // documented delay + 5min buffer -> "on time for a delayed feed"
DELAYED_THRESHOLD_MINUTES = 45  // beyond fresh-for-delayed but still usable
// beyond DELAYED_THRESHOLD_MINUTES -> STALE
```

```
classifyFreshness(ageMinutes):
  null                                -> "UNKNOWN"
  ageMinutes <= 20                    -> "FRESH"
  20 < ageMinutes <= 45                -> "DELAYED"
  ageMinutes > 45                      -> "STALE"
```

## Combining spot + options into overall Gamma freshness

`gammaFreshnessStatus = combineFreshness(spotFreshnessStatus, optionsFreshnessStatus)`
takes the WORSE of the two, using the rank order `FRESH < DELAYED < UNKNOWN
< STALE`. A fresh spot can never mask stale or unknown options data, and
vice versa — verified by `tests/remediation.test.js` items 7-8.

## dataMode vs freshnessStatus — two different concepts

- **`dataMode`** (`"REALTIME" | "DELAYED" | "UNKNOWN"`) describes the
  *account plan's* nature — currently hardcoded to `"DELAYED"` because that
  is the confirmed, documented plan tier. This is a static fact about
  entitlement, not a per-request measurement.
- **`spotFreshnessStatus` / `optionsFreshnessStatus` / `gammaFreshnessStatus`**
  (`"FRESH" | "DELAYED" | "STALE" | "UNKNOWN"`) describe how old *this
  specific response's* data actually is, measured against the thresholds
  above. A `DELAYED`-mode account can still return `FRESH`-status data (if
  it arrives within the expected ~15-20 min window) or `STALE`-status data
  (if something's actually lagging beyond that).

Do not conflate these two fields — a UI or caller checking only `dataMode`
would incorrectly treat all data as uniformly "fine," which is exactly the
false-confidence problem this remediation exists to prevent.

## Confidence penalties

| gammaFreshnessStatus | freshnessModifier |
|---|---|
| FRESH | 1.00 |
| DELAYED | 0.85 |
| STALE | 0.35 |
| UNKNOWN | 0.70 |

Multiplicative against `baseScore` alongside the chain-completeness
modifier — see CHAIN_COMPLETENESS_SPEC.md and `computeConfidenceBreakdown()`.

## Known limitation

There is no live network access in this environment to verify Massive's
actual observed delay distribution (i.e., whether 15-min-plan data
typically arrives at 15, 18, or 25 minutes in practice). The 20/45-minute
thresholds are a reasoned, documented default, not empirically calibrated
against live traffic. Recommend revisiting after a period of live
production use — see TEST_REPORT.md.
