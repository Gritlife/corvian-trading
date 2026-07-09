// netlify/functions/lib/massive-client.js
// Shared helper for all Netlify functions that call Massive's REST API.
//
// v.2 (remediation pass) changes:
//   - Auth migrated from `?apiKey=` query string to `Authorization: Bearer`
//     header. Confirmed as Massive's own official-client behavior (the
//     massive-com/client-python debug output shows
//     `'Authorization': 'Bearer REDACTED'` on every request) — this is not
//     an invented scheme. Query-string keys are more prone to appearing in
//     server access logs and proxy logs than headers; header auth avoids
//     that.
//   - Added a short in-memory response cache (best-effort, instance-local
//     — see caveats in SECURITY_LIMITATIONS.md).
//   - Added a simple in-memory token-bucket rate limiter (same caveats).
//   - Added HTTP method validation helper.

const MASSIVE_BASE = "https://api.massive.com";
const DEFAULT_TIMEOUT_MS = 10000;

// Ticker validation: plain equities (AAPL), share classes (BRK.B), or an
// options contract ticker (O:AAPL240119C00150000), or an index (I:SPX).
const TICKER_RE = /^(O:|I:)?[A-Z]{1,6}(\.[A-Z])?[0-9A-Z]*$/;

function redact(str) {
  const key = process.env.MASSIVE_API_KEY;
  if (!key || !str) return str;
  return String(str).split(key).join("[REDACTED]");
}

function validateSymbol(sym) {
  if (typeof sym !== "string" || sym.length === 0 || sym.length > 32) return false;
  return TICKER_RE.test(sym);
}

// ---- Method validation (remediation #5A) -----------------------------------
function requireMethod(event, allowed) {
  const method = (event.httpMethod || "GET").toUpperCase();
  if (!allowed.includes(method)) {
    return errorResponse(405, "method_not_allowed", `Method ${method} not allowed. Allowed: ${allowed.join(", ")}`, {}, { "Allow": allowed.join(", ") });
  }
  return null; // null = OK, proceed
}

// ---- Best-effort in-memory cache + rate limiter (remediation #5C/#5D) -----
// CAVEAT (documented honestly in SECURITY_LIMITATIONS.md): Netlify Functions
// run on Lambda-like infrastructure. A warm instance can be reused across
// nearby invocations (making this cache/limiter effective for bursts on the
// SAME warm instance), but there is NO guarantee of a single shared
// instance, and cold starts reset all of this state. This is a real,
// meaningful reduction in duplicate-upstream-call volume for a single
// user's rapid repeated requests — it is NOT a distributed rate limiter and
// NOT a substitute for real abuse protection at scale (see doc).
const _cache = new Map(); // key -> { expiresAt, value }
const _rateBuckets = new Map(); // key -> { count, windowStart }

function cacheGet(key) {
  const entry = _cache.get(key);
  if (!entry) return undefined;
  if (Date.now() > entry.expiresAt) { _cache.delete(key); return undefined; }
  return entry.value;
}
function cacheSet(key, value, ttlMs) {
  _cache.set(key, { value, expiresAt: Date.now() + ttlMs });
  if (_cache.size > 500) {
    const firstKey = _cache.keys().next().value;
    _cache.delete(firstKey);
  }
}

/**
 * Very simple fixed-window limiter. Returns true if the call should be
 * allowed, false if the caller has exceeded `maxCalls` within `windowMs`
 * for this `bucketKey` on THIS warm instance.
 */
function rateLimitCheck(bucketKey, maxCalls, windowMs) {
  const now = Date.now();
  const bucket = _rateBuckets.get(bucketKey);
  if (!bucket || now - bucket.windowStart > windowMs) {
    _rateBuckets.set(bucketKey, { count: 1, windowStart: now });
    return true;
  }
  bucket.count++;
  return bucket.count <= maxCalls;
}

/**
 * Fetch a Massive REST endpoint with the server-side API key attached via
 * the Authorization header. Optionally cached.
 * @param {string} path - path + query string, WITHOUT apiKey
 * @param {Object} opts - { timeoutMs, cacheTtlMs }
 * @returns {Promise<{ok: boolean, status: number, json: any, error: string|null, fromCache: boolean}>}
 */
async function fetchMassive(path, opts) {
  opts = opts || {};
  const timeoutMs = opts.timeoutMs || DEFAULT_TIMEOUT_MS;
  const cacheTtlMs = opts.cacheTtlMs || 0;
  const apiKey = process.env.MASSIVE_API_KEY;
  if (!apiKey) {
    return { ok: false, status: 500, json: null, error: "server_misconfigured_no_api_key", fromCache: false };
  }

  const cacheKey = "GET:" + path;
  if (cacheTtlMs > 0) {
    const cached = cacheGet(cacheKey);
    if (cached !== undefined) return Object.assign({}, cached, { fromCache: true });
  }

  const url = `${MASSIVE_BASE}${path}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let result;
  try {
    const resp = await fetch(url, {
      signal: controller.signal,
      headers: { "Authorization": `Bearer ${apiKey}` },
    });
    const text = await resp.text();
    let json = null;
    try { json = JSON.parse(text); } catch (e) { /* non-JSON body */ }

    if (!resp.ok) {
      const providerMsg = (json && (json.error || json.message)) || `HTTP ${resp.status}`;
      result = { ok: false, status: resp.status, json, error: redact(String(providerMsg)), fromCache: false };
    } else {
      result = { ok: true, status: resp.status, json, error: null, fromCache: false };
    }
  } catch (e) {
    if (e.name === "AbortError") {
      result = { ok: false, status: 504, json: null, error: "upstream_timeout", fromCache: false };
    } else {
      result = { ok: false, status: 502, json: null, error: redact(e.message || "upstream_fetch_failed"), fromCache: false };
    }
  } finally {
    clearTimeout(timer);
  }

  if (result.ok && cacheTtlMs > 0) cacheSet(cacheKey, result, cacheTtlMs);
  return result;
}

function jsonResponse(statusCode, bodyObj, extraHeaders) {
  return {
    statusCode,
    headers: Object.assign(
      { "content-type": "application/json", "cache-control": "no-store" },
      extraHeaders || {}
    ),
    body: JSON.stringify(bodyObj),
  };
}

function errorResponse(statusCode, code, message, extra, extraHeaders) {
  return jsonResponse(statusCode, Object.assign({
    error: code,
    message: message,
    timestampUtc: new Date().toISOString(),
  }, extra || {}), extraHeaders);
}

module.exports = {
  fetchMassive, validateSymbol, jsonResponse, errorResponse, MASSIVE_BASE,
  requireMethod, rateLimitCheck, cacheGet, cacheSet,
};
