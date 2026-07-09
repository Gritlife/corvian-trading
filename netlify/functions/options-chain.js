// netlify/functions/options-chain.js
// Phase 3 — Massive Options ingestion. Proxies the real, documented endpoint:
//   GET /v3/snapshot/options/{underlyingAsset}
// (confirmed via https://massive.com/docs/rest/options/snapshots/option-chain-snapshot;
//  auth migrated to Authorization: Bearer header — see lib/massive-client.js
//  header for why. Massive is Polygon.io's post-Oct-2025 rebrand.)
//
// OPTIONS DATA ONLY (directive "SEPARATE DATA DOMAINS" B). Raw provider
// fields are passed through with pagination flattened; OCM-derived fields
// (Gamma Gauge, regime, walls, etc.) are computed downstream in
// ocm-gamma-snapshot.js, never mixed in here.
//
// NOTE (remediation pass): this endpoint is currently NOT called directly
// by the frontend — ocm-gamma-snapshot.js composes its own options-chain
// fetch internally (with its own, authoritative completeness tracking).
// This endpoint remains available as a standalone raw-data proxy (e.g. for
// the live validation harness, or future direct-consumption use cases) and
// carries the SAME completeness field set for consistency, but
// ocm-gamma-snapshot.js's copy of this logic is the one that actually
// feeds Gamma confidence/status.
//
// Request: GET /.netlify/functions/options-chain?symbol=AMD&maxPages=4

const { fetchMassive, validateSymbol, jsonResponse, errorResponse, requireMethod, rateLimitCheck } = require("./lib/massive-client");

const DEFAULT_LIMIT = 250; // Massive's documented max for this endpoint
const DEFAULT_MAX_PAGES = 4; // up to 1000 contracts per underlying per request

exports.handler = async function handler(event) {
  const methodErr = requireMethod(event, ["GET"]);
  if (methodErr) return methodErr;

  const qs = event.queryStringParameters || {};
  const symbol = qs.symbol;
  if (!symbol || !validateSymbol(symbol)) {
    return errorResponse(400, "invalid_symbol", "symbol query param required and must pass validation");
  }
  if (!rateLimitCheck("options-chain:" + symbol, 20, 60000)) {
    return errorResponse(429, "rate_limited", "Too many requests for this symbol from this instance in the last minute.");
  }
  const maxPages = Math.min(10, Math.max(1, parseInt(qs.maxPages, 10) || DEFAULT_MAX_PAGES));

  // Optional pass-through filters per Massive's documented query params.
  const allowedFilters = ["strike_price", "strike_price.gte", "strike_price.lte", "expiration_date", "expiration_date.gte", "expiration_date.lte", "contract_type"];
  const filterParams = [];
  for (const key of allowedFilters) {
    if (qs[key] != null && qs[key] !== "") filterParams.push(`${key}=${encodeURIComponent(qs[key])}`);
  }

  const contracts = [];
  let nextPath = `/v3/snapshot/options/${encodeURIComponent(symbol)}?limit=${DEFAULT_LIMIT}${filterParams.length ? "&" + filterParams.join("&") : ""}`;
  let pagesFetched = 0;
  let lastError = null;
  let lastPageContractCount = 0;
  let sawExplicitEnd = false;

  while (nextPath && pagesFetched < maxPages) {
    const r = await fetchMassive(nextPath, { cacheTtlMs: 15000 });
    pagesFetched++;
    if (!r.ok) {
      lastError = r.error;
      break;
    }
    const results = (r.json && r.json.results) || [];
    lastPageContractCount = results.length;
    contracts.push(...results);

    const nextUrl = r.json && r.json.next_url;
    if (nextUrl) {
      try {
        const u = new URL(nextUrl);
        nextPath = u.pathname + "?" + u.searchParams.toString();
      } catch (e) {
        nextPath = null;
        sawExplicitEnd = true;
      }
    } else {
      nextPath = null;
      sawExplicitEnd = true;
    }
  }

  if (contracts.length === 0 && lastError) {
    return errorResponse(502, "upstream_error", lastError, { symbol, pagesFetched });
  }

  const upstreamPaginationObserved = pagesFetched > 0 && !lastError;
  const pageLimitReached = pagesFetched >= maxPages && !!nextPath;
  const hasMorePages = !!nextPath;

  let chainComplete, truncated, completenessStatus;
  if (!upstreamPaginationObserved) {
    chainComplete = false; truncated = false; completenessStatus = "UNKNOWN";
  } else if (sawExplicitEnd && !hasMorePages) {
    chainComplete = true; truncated = false; completenessStatus = "COMPLETE";
  } else if (pageLimitReached) {
    chainComplete = false; truncated = true; completenessStatus = "TRUNCATED";
  } else {
    chainComplete = false; truncated = false; completenessStatus = "UNKNOWN";
  }

  return jsonResponse(200, {
    symbol,
    fetchedAtUtc: new Date().toISOString(),
    pagesFetched,
    contractsFetched: contracts.length,
    contractsReturned: contracts.length, // kept for backward compat with any existing caller
    pageLimit: maxPages,
    pageLimitReached,
    hasMorePages,
    truncated,
    chainComplete,
    completenessStatus,
    upstreamPaginationObserved,
    lastPageContractCount,
    warning: lastError ? `partial_result: ${lastError}` : null,
    contracts, // raw Massive per-contract objects: day, details, greeks, implied_volatility, last_quote?, last_trade?, open_interest, underlying_asset
  });
};
