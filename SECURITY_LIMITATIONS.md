# SECURITY_LIMITATIONS.md

Honest accounting, per the remediation directive's explicit instruction not
to implement or claim fake security.

## What IS protected

- **The Massive API key never reaches the browser.** Verified by automated
  test across three test files (0 occurrences of the key literal, 0
  `apiKey=` query construction, 0 direct `api.massive.com` calls from
  `index.html`).
- **Auth to Massive uses the `Authorization: Bearer` header**, not a
  query-string parameter — reduces the chance of the key appearing in
  server access logs or intermediate proxy logs (confirmed as Massive's own
  official-client pattern, not an invented scheme).
- **HTTP method validation**: all four functions (`health`,
  `equity-snapshot`, `options-chain`, `ocm-gamma-snapshot`) reject anything
  but `GET` with a structured `405` + `Allow` header.
- **Ticker/symbol validation**: a strict regex (`validateSymbol`) rejects
  malformed input before any upstream call — tested against SQL-injection-
  style and path-traversal-style strings.
- **Structured errors**: every error path returns `{error, message,
  timestampUtc}` — never a raw stack trace, never an echoed upstream body
  that could contain request-identifying details.
- **Best-effort in-memory rate limiting and caching** (see below for the
  honest caveat on how much this actually protects).

## What is NOT protected (stated plainly)

- **There is no user authentication on these endpoints.** Anyone who knows
  (or guesses) your Netlify site's URL can call
  `/.netlify/functions/equity-snapshot`, `/.netlify/functions/options-chain`,
  and `/.netlify/functions/ocm-gamma-snapshot` directly — via curl, a
  script, another website's server, whatever — with no login, session, or
  API key of their own required. Every such call is billed against **your**
  Massive account.
- **Origin/Referer headers are not checked, and if they were, that would
  not be real authentication** — they are trivially spoofable by any
  non-browser client (curl, server-to-server calls, etc.). This directive
  explicitly warned against claiming otherwise, and we're not claiming it.
- **CORS**: no `Access-Control-Allow-Origin` header is set on any response.
  This means a **browser** running JavaScript from a different origin
  cannot read the response (the browser's CORS policy blocks it) — but this
  is not a server-side access control; it only affects browser-based
  cross-origin fetches. Direct server-to-server or curl requests are
  unaffected by CORS entirely.
- **Rate limiting is instance-local, not distributed.** `rateLimitCheck()`
  keeps its counters in an in-memory `Map` inside the running function
  instance. Netlify Functions run on Lambda-like infrastructure: a burst of
  requests may hit the same warm instance (where the limiter works as
  intended), but concurrent requests can just as easily be routed to
  different, independently-cold instances, each with its own empty counter
  — meaning a sufficiently parallel abuser can exceed the intended limit by
  simply spreading requests across instances. This is a **real, partial**
  mitigation against a single slow/repeated caller, not a hard cap.
- **Caching is similarly instance-local and best-effort**, not a shared
  cache layer (no Redis/KV store is in use). It reduces duplicate upstream
  calls within a warm instance's TTL window; it does not prevent
  distributed callers from each generating their own upstream traffic.
- **No API usage quotas or billing alerts are configured** by this codebase
  — that's a Massive/Netlify account-level setting, out of scope for code
  changes.

## Recommended future authentication work (not built in this pass)

Per the directive's explicit instruction not to redesign the app to add
this now, but to document what's needed:

1. **Simplest**: require a shared secret header (e.g.
   `X-ToF-Client-Secret`) that the frontend sends and the function checks
   against an env var. This is NOT real per-user auth (anyone who extracts
   the secret from the frontend bundle can also call the endpoints), but it
   does stop casual/opportunistic abuse from search-engine crawlers or
   randomly-discovered URLs.
2. **Better**: put the existing `LoginPage`'s session behind real
   server-side session tokens (currently `loggedIn` is pure client-side
   React state with no server verification at all — logging in doesn't
   call any backend), and have the Netlify functions verify that token.
   This is a genuine architecture change (a real backend auth system) and
   was explicitly out of scope for "do not redesign the app in this pass."
3. **For production-scale abuse protection**: Netlify's own edge/DDoS
   protections, plus a real distributed rate limiter (e.g. Netlify's own
   rate-limiting feature if available on your plan, or an external service)
   rather than the in-memory approximation shipped here.

## Summary

This pass added real, meaningful hardening (method validation, input
validation, structured errors, header-based auth, best-effort
caching/limiting) without pretending any of it constitutes user
authentication. **The endpoints are, today, publicly callable by anyone who
finds the URL, and every call is billed to your Massive account.** If that
risk is unacceptable before going live, implement recommendation #1 at
minimum before deploying.
