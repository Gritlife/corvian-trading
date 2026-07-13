# GAMMA_STATUS_SPEC.md

Source of truth: `netlify/functions/lib/gamma-status.js` — this document
describes that code; if they ever disagree, the code is authoritative and
this doc is stale (update it).

## States

| Status | Meaning |
|---|---|
| `GAMMA UNAVAILABLE` | No usable Gamma data at all — no spot, no contracts, or no contract had both OI and gamma. |
| `GAMMA INVALID` | Data exists but the computed regime is `UNKNOWN` (e.g. no gamma flip could be found and gauge is ambiguous). |
| `GAMMA STALE` | Either the spot or the options timestamp (whichever is worse) is beyond the STALE threshold (45 min). |
| `GAMMA DEGRADED — PARTIAL CHAIN` | Chain pagination hit the page limit (4 pages / ~1000 contracts) while more pages existed upstream. |
| `GAMMA DEGRADED — UNKNOWN COMPLETENESS` | Could not determine whether the chain was fully paginated (e.g. every page request failed). |
| `GAMMA LOW CONFIDENCE` | Confidence score (post completeness/freshness penalty) is below 40. |
| `GAMMA DELAYED` | Everything else is fine, but freshness is `DELAYED` or `UNKNOWN` (not `FRESH`, not `STALE`). |
| `GAMMA VALID` | Every dimension is clean: valid, known regime, fresh, complete chain, confidence ≥ 40. |

## Precedence (deterministic, first match wins)

```
1. UNAVAILABLE   (!valid)
2. INVALID       (gammaRegime === "UNKNOWN")
3. STALE         (gammaFreshnessStatus === "STALE")
4. PARTIAL_CHAIN (completenessStatus === "TRUNCATED")
5. UNKNOWN_COMPLETENESS (completenessStatus === "UNKNOWN")
6. LOW_CONFIDENCE (confidenceScore < 40)
7. DELAYED       (gammaFreshnessStatus is DELAYED or UNKNOWN)
8. VALID         (everything else)
```

This exact order is implemented in `computeGammaStatus()` and is covered by
`tests/remediation.test.js` items 14/14b/14c/14d — including the specific
case (item 14) where a snapshot is simultaneously "stale" AND "truncated,"
proving STALE wins deterministically rather than either being ambiguous or
order-dependent.

Rationale for this order: a stale snapshot is dangerous regardless of how
complete the chain was — the price levels themselves may no longer be
relevant. A merely-incomplete-but-fresh chain is a lesser problem (some
gamma structure is missing, but what's there is current) — hence PARTIAL
CHAIN outranks LOW_CONFIDENCE (an incomplete chain should be labeled for
*what's wrong*, not folded into a generic low score) but is outranked by
STALE (freshness is a harder problem than completeness).

## Reason codes

`gammaStatusReasons` is always an array (empty only for `VALID`). Known
codes: `NO_SPOT_PRICE`, `NO_CONTRACTS_RETURNED`, `NO_USABLE_CONTRACTS`,
`UNAVAILABLE`, `GAMMA_REGIME_UNKNOWN`, `OPTIONS_DATA_STALE`,
`SPOT_DATA_STALE`, `OPTIONS_CHAIN_TRUNCATED`, `PAGE_LIMIT_REACHED`,
`OPTIONS_FRESHNESS_UNKNOWN`, `CHAIN_COMPLETENESS_UNKNOWN`,
`UPSTREAM_PAGINATION_UNOBSERVED`, `CONFIDENCE_BELOW_THRESHOLD_40`,
`OPTIONS_DATA_DELAYED_OR_UNKNOWN`, `SPOT_DATA_DELAYED_OR_UNKNOWN`.

## Confidence interaction

`confidenceScore` (0-100) already has the chain-completeness and freshness
modifiers baked into it (see `confidenceBreakdown.finalScore` in
`ocm-engine.js`) — it is not a separate, unrelated number from `gammaStatus`.
A truncated chain will show BOTH a degraded status AND a reduced confidence
score, consistently, because they're derived from the same underlying
modifier values passed into `computeOcmGammaSnapshot()`.

## Frontend display rule

`GammaSpinePanel` (in `index.html`) prefers the backend's `gammaStatus`
(from a live OCM fetch) over the local `gamma-spine.js` port's own
`gammaSpineResult.status` whenever a live snapshot is present, specifically
because the local Pine-derived validation has no concept of chain
completeness and could otherwise show `GAMMA VALID` for a chain the backend
knows is truncated. This is covered by `tests/integration.test.js` item 7
("GAMMA UNAVAILABLE is a real renderable status distinct from legacy
regime") and manually verified by inspection of the Status row's color/text
logic.
