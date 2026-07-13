# SECURITY.md — ToF V1.1 Secure Live OCM Pipeline

## What changed

The current deployed ToF HTML (audited in this project) stores the Massive
API key in `localStorage` (`mts-v19-polygon-key`) and calls four Massive
endpoints directly from the browser with `apiKey=<key>` in the query string
(confirmed present in the deployed source: treasury-yields, aggs bars,
snapshot, grouped-daily). Anyone with browser DevTools access, or access to
that browser's `localStorage`, can read the key in plaintext.

This delivery introduces a server-side proxy layer (Netlify Functions) so
the key never reaches the browser at all.

## Architecture

```
Browser ToF  →  /.netlify/functions/{equity-snapshot,options-chain,ocm-gamma-snapshot,health}
                     ↓ (server-side only)
                 process.env.MASSIVE_API_KEY
                     ↓
                 api.massive.com
```

## Where the secret lives now

- **Only** in the Netlify dashboard's Environment Variables (Site settings →
  Environment variables → `MASSIVE_API_KEY`), or in a local `.env` file
  (git-ignored) for `netlify dev`.
- Read exclusively via `process.env.MASSIVE_API_KEY` inside
  `netlify/functions/lib/massive-client.js`. No other file references it
  except `health.js`, which only reports a boolean (`massiveKeyConfigured`)
  — never the value, never a length/prefix/substring.

## What the browser can no longer do

- The browser no longer needs, stores, or sends any Massive API key.
- `PolygonKeyField` (the existing UI component for entering/storing the key)
  becomes dead code once the frontend is migrated to call
  `/.netlify/functions/*` instead of `api.massive.com` directly — see
  MIGRATION_REPORT.md for the exact call-site changes still required in the
  HTML app (**not yet applied** — see "What remains" in the final report).

## Defenses implemented in the function layer

- **Input validation**: `validateSymbol()` rejects anything that doesn't
  look like a real ticker/contract/index symbol before any outbound call.
- **Timeout handling**: `AbortController` with a 10s default in
  `fetchMassive()`; returns a structured `upstream_timeout` error rather
  than hanging.
- **No secret leakage in errors or logs**: `redact()` strips the literal key
  value from any string before it's returned to the client. Error responses
  are structured JSON (`{error, message, timestampUtc}`), never a raw
  proxied provider error body that could theoretically echo request
  parameters.
- **No client-supplied API key accepted**: verified by
  `tests/security.test.js` — every function's query-string handling is
  checked to confirm it never reads an `apiKey` param from the incoming
  request.
- **Same-origin**: no CORS relaxation; the browser calls the same domain
  the site is deployed on.

## What this delivery does NOT change

- It does not add authentication/authorization for who can call *your*
  Netlify functions (i.e., there's no per-user login gating the proxy
  itself yet — anyone who can reach your deployed site's `/.netlify/functions/*`
  URLs can trigger Massive calls billed to your key). If ToF is meant to be
  multi-tenant or publicly reachable, add a session/auth check inside each
  function before it calls `fetchMassive()`. This is out of scope for what
  was asked (secure the key, not add user auth) but is worth flagging.
- It does not rate-limit callers beyond Massive's own provider-side limits.
  A basic per-IP or per-session rate limit would be a reasonable follow-up.

## Verification

Run `node tests/security.test.js` — 7 static checks, all passing. These are
structural/static checks (no live key was available in this environment to
test an actual end-to-end network call); see TEST_REPORT.md for exactly
what was and wasn't exercised against live Massive traffic.
