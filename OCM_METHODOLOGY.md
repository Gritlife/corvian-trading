# OCM_METHODOLOGY.md — Gamma Calculation Methodology

This document exists because the directive explicitly requires the GEX
methodology to be disclosed, not hidden. Read this before trusting any
number OCM produces.

## Data source and its limits

- Options chain: `GET /v3/snapshot/options/{symbol}` on Massive (confirmed
  live endpoint, documented at
  https://massive.com/docs/rest/options/snapshots/option-chain-snapshot).
- Account plan confirmed: **Options Starter, $29/mo, 15-minute delayed.**
  This means: option greeks/IV/open-interest come from Massive's own
  calculation pipeline (not computed by us), but are themselves derived
  from 15-min-delayed underlying data, not real-time. `last_quote`/
  `last_trade` on each contract may or may not be present — Starter's exact
  quote/trade inclusion wasn't confirmed from the docs (plan-access tables
  are rendered client-side and weren't retrievable via static fetch); the
  code does not assume either way and simply passes through whatever the
  provider returns for those two fields.
- Open interest is **end-of-previous-trading-day**, per Massive's own field
  description ("quantity held at end of last trading day") — it is not
  intraday-live OI. This is a real limitation of the underlying data, not
  something OCM can fix.

## GEX formula (per contract, aggregated per strike)

```
GEX_call(strike) = +1 * OI_call * gamma_call * multiplier * spot^2 * 0.01
GEX_put(strike)  = -1 * OI_put  * gamma_put  * multiplier * spot^2 * 0.01
NetGEX(strike)   = GEX_call(strike) + GEX_put(strike)
```

- **multiplier**: `details.shares_per_contract` from the contract, or 100
  if absent (standard US equity option multiplier).
- **spot**: from Massive's equity snapshot endpoint (`day.c` / `prevDay.c` /
  last quote midpoint, in that preference order) — **not** anything from
  the options payload itself. This is the one place equity and options data
  are combined, and only as a scalar input, never merged field-by-field.
- **0.01 scale**: standard "dollar gamma exposure per 1% move" convention
  used in most public GEX write-ups. This is a normalization choice, not a
  law of physics.

## Sign convention — an assumption, stated plainly

We assume dealers are **net short calls and net short puts** to customers
(the common simplified convention behind most public GEX approximations).
Under that assumption:

- Dealer hedging of short calls is gamma-**positive** (stabilizing —
  dealers buy dips / sell rallies to stay hedged).
- Dealer hedging of short puts is gamma-**negative** (destabilizing).

**This is not verified against actual dealer books.** Real dealer
positioning varies by strike, expiration, and counterparty, and can differ
materially from this simplified convention. Treat OCM's output as a proxy
for aggregate options-market structure, not a measured fact about who holds
what.

## Missing data handling

- A contract with missing OI **or** missing gamma is excluded from GEX at
  its strike — it does not contribute a 0. `quality.contractsUsed` vs
  `quality.contractsSeen` tells you how many were actually usable.
- If **zero** contracts had both OI and gamma, `totalNetGex` and
  `zeroDteNetGex` are `null`, not `0`. A `0` in these fields means the
  usable contracts summed to exactly zero; `null` means there was nothing
  usable to sum.
- `openInterestCoveragePct` / `greeksCoveragePct` / `ivCoveragePct` report
  what fraction of all contracts *seen* actually had that field.

## gexByStrike — canonical strike-level state (Item #17, additive)

`computeOcmGammaSnapshot()` exposes the full sorted strike-level array on
the snapshot as:

```
gexByStrike: [ { strike, call, put, net } ] | null
gexByStrikeScope: "ALL_EXPIRATIONS"
gexByStrikeConvention: "DEALER_SHORT_+CALL_-PUT_SPOT2_x0.01"
```

- This is **exposure of already-computed state** from `aggregateByStrike()`
  — not a second GEX model. The values are exactly those that feed the
  flip/wall/pit/gauge/total computations on the same snapshot.
- **Scope**: all expirations collapsed per strike (matching the engine's
  existing aggregation). Expiration-bucketed variants are a possible
  future additive field, not present today.
- **Null discipline**: `gexByStrike` is `null` (never `[]`) when zero
  contracts contributed usable GEX; a leg (`call`/`put`) is `null` at a
  strike when no contract of that leg contributed there — matching the
  engine-wide null-not-zero rule.
- **Ordering**: sorted ascending by strike, guaranteed.
- **Completeness/freshness**: the array carries no private metadata — the
  snapshot's existing `completenessStatus`, `truncated`, freshness fields,
  and `quality` coverage percentages apply to it exactly as they do to the
  summary fields, since both derive from the same fetch.
- **Payload**: bounded by the 4-page/1,000-contract pagination cap;
  worst-case ~70KB of JSON, typical 15-35KB for liquid names.
- **Consumers**: intended for the future M-EOD GEX histogram. The frontend
  must consume this state as-is and never recompute Gamma/GEX math.

## Level derivation

- **Positive Gamma Wall**: the strike with the maximum positive `NetGEX`
  (largest aggregated positive-gamma concentration) — not the highest
  strike, not the nearest call strike.
- **Negative Gamma Pit**: the strike with the minimum (most negative)
  `NetGEX` — not the lowest strike, not the nearest put strike.
- **Gamma Flip**: found by walking strikes ascending, summing `NetGEX`
  cumulatively, and linearly interpolating the strike where that cumulative
  sum crosses zero. Returns `null` if no crossing exists in the data (we do
  not invent a flip when the chain doesn't support one).
  - **Known limitation**: this cumulative walk uses each contract's gamma
    *as computed at the current spot* — it does not reprice gamma at each
    hypothetical spot level along the walk (that would require a full vol
    surface / model reprice, which a single snapshot's greeks can't
    support). This is the standard simplified public-calculator
    approximation, not a fully repriced flip.

## Gamma Gauge normalization

```
gauge = 100 * totalNetGEX / sum(|NetGEX per strike|)
```

Naturally bounded in [-100, 100] without an arbitrary external scale
constant — it's literally "what fraction of total gamma magnitude is net
positive vs negative." Returns `null` if there's no usable GEX data at all.

## Regime classification

- `UNKNOWN` if gauge or flip couldn't be computed.
- `TRANSITION` if spot is within 0.5% of the flip level (too close to call
  a clean regime either way), regardless of gauge magnitude.
- `POSITIVE` if gauge > +10.
- `NEGATIVE` if gauge < -10.
- Otherwise `TRANSITION`.

## Confidence score

```
confidence = round(100 * (oiCoverage*0.4 + greeksCoverage*0.4 + min(1, contractsUsed/50)*0.2))
```

Documented weights: 40% OI coverage, 40% greeks coverage, 20% floor on
absolute usable-contract count (50 treated as "ample"). This is a
transparency/data-quality score, not a statistical confidence interval.

## What is NOT computed

- 0DTE Net GEX is computed only from contracts whose `expiration_date`
  equals today (US/Eastern). If none exist for a given symbol/day, it's
  `null`.
- No forecasting, no probability-weighted outcomes, no "expected move" —
  OCM reports structure as observed in the current chain snapshot only.

## Validation status

See `ocm-gamma-snapshot.js`: `valid` requires usable contracts AND a spot
price; `stale` is based on the equity quote's own age vs a 15-minute
threshold (matching the confirmed Options Starter delay); `status` is one
of `GAMMA VALID / GAMMA STALE / GAMMA LOW CONFIDENCE / GAMMA INVALID /
GAMMA UNAVAILABLE`, mirroring the discipline already used in
`gamma-spine.js`'s Pine-derived validation cascade.
