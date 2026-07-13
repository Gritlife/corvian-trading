# CHAIN_COMPLETENESS_SPEC.md

Source of truth: `classifyCompleteness()` in `netlify/functions/lib/gamma-status.js`.

## Pagination behavior

`ocm-gamma-snapshot.js` fetches `GET /v3/snapshot/options/{symbol}?limit=250`
and follows `next_url` up to `PAGE_LIMIT = 4` times (≤1000 contracts total).
Four raw facts are tracked per fetch:

- `upstreamPaginationObserved` — did we get at least one successful (non-error) page?
- `sawExplicitEnd` — did a page response come back with NO `next_url`
  (Massive's own signal that there are no more pages)?
- `hasMorePages` — is there a pending `next_url` we didn't follow (either
  because we hit `PAGE_LIMIT`, or a later page errored)?
- `pageLimitReached` — did we stop specifically because `pages >= PAGE_LIMIT`
  while `hasMorePages` was still true?

## Truncation detection

```
if (!upstreamPaginationObserved)          -> UNKNOWN   (we never even confirmed pagination worked)
else if (sawExplicitEnd && !hasMorePages) -> COMPLETE  (Massive told us there's nothing more)
else if (pageLimitReached)                -> TRUNCATED (we stopped, but more existed)
else                                       -> UNKNOWN   (stopped for some other reason)
```

This is intentionally conservative: the only way to get `COMPLETE` is to
have actually observed the upstream "no more pages" signal. Nothing is
inferred or assumed complete by default.

## Unknown completeness

`UNKNOWN` occurs when every page request failed before any success, or
when parsing `next_url` itself threw (malformed provider response). Either
way we stop, but we do not claim we know the result is complete or
incomplete — it gets its own status distinct from both.

`UNKNOWN` is never silently treated as `COMPLETE`. It produces
`GAMMA DEGRADED — UNKNOWN COMPLETENESS`, a status distinct from
`TRUNCATED`, with its own confidence modifier.

## Confidence penalties

| completenessStatus | chainCompletenessModifier |
|---|---|
| COMPLETE | 1.00 (no penalty) |
| UNKNOWN | 0.75 (meaningful penalty) |
| TRUNCATED | 0.40 (major penalty) |

These multiply against `baseScore` (open-interest coverage + greeks
coverage + contract-count floor), alongside the separate freshness
modifier — see `computeConfidenceBreakdown()` in `ocm-engine.js`. The
values are a documented judgment call guaranteeing the ordering property
(TRUNCATED penalty > UNKNOWN penalty > no penalty), not a derived formula.

For very large/liquid chains a truncated snapshot can still numerically
clear the LOW_CONFIDENCE threshold on coverage strength alone — which is
exactly why completeness has its own status that outranks LOW_CONFIDENCE
in the precedence order (see GAMMA_STATUS_SPEC.md), so a high numeric score
can never by itself produce GAMMA VALID for a chain known to be incomplete.

## Fields exposed on the snapshot

`pagesFetched`, `contractsFetched`, `pageLimit`, `pageLimitReached`,
`hasMorePages`, `truncated`, `chainComplete`, `completenessStatus`,
`completenessConfidenceModifier`, `upstreamPaginationObserved`,
`lastPageContractCount`. All truthful, none fabricated — verified by
`tests/remediation.test.js` items 1-4.

## Known limitation

For very liquid names with genuinely more than 1000 contracts across all
expirations/strikes (SPY and QQQ are the most likely candidates),
TRUNCATED will be the routine expected status rather than an edge case.
This is disclosed, not hidden — see TEST_REPORT.md's suggestion to test
SPY specifically as part of live validation.
