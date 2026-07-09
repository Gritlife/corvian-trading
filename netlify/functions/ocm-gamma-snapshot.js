// netlify/functions/ocm-gamma-snapshot.js
// Orchestrator. Fetches underlying spot (equity data) + options chain
// (options data), runs the pure OCM engine, and applies chain completeness
// / freshness / Gamma health classification via lib/gamma-status.js (the
// same module exercised directly by tests/gamma-status.test.js — this
// function is a thin wiring layer around that pure, tested logic, not a
// second copy of it).
//
// Request: GET /.netlify/functions/ocm-gamma-snapshot?symbol=AMD

const crypto = require("crypto");
const { fetchMassive, validateSymbol, jsonResponse, errorResponse, requireMethod, rateLimitCheck } = require("./lib/massive-client");
const { computeOcmGammaSnapshot } = require("./lib/ocm-engine");
const {
  PAGE_LIMIT, classifyCompleteness, classifyFreshness, freshnessModifierFor,
  combineFreshness, computeGammaStatus, MIN_CONFIDENCE,
} = require("./lib/gamma-status");

exports.handler = async function handler(event) {
  const methodErr = requireMethod(event, ["GET"]);
  if (methodErr) return methodErr;

  const qs = event.queryStringParameters || {};
  const symbol = qs.symbol;
  if (!symbol || !validateSymbol(symbol)) {
    return errorResponse(400, "invalid_symbol", "symbol query param required and must pass validation");
  }
  if (!rateLimitCheck("ocm:" + symbol, 20, 60000)) {
    return errorResponse(429, "rate_limited", "Too many requests for this symbol from this instance in the last minute.");
  }

  const startedAt = Date.now();

  // 1. Underlying spot (equity domain).
  const snapR = await fetchMassive(`/v2/snapshot/locale/us/markets/stocks/tickers?tickers=${encodeURIComponent(symbol)}`, { cacheTtlMs: 15000 });
  let spot = null;
  let spotAsOfUtc = null;
  if (snapR.ok && snapR.json && snapR.json.tickers && snapR.json.tickers[0]) {
    const t = snapR.json.tickers[0];
    spot = (t.day && t.day.c) || (t.prevDay && t.prevDay.c) || (t.lastQuote && t.lastQuote.P) || null;
    const lastUpdated = (t.day && t.day.last_updated) || (t.updated) || null;
    spotAsOfUtc = lastUpdated ? new Date(lastUpdated / 1e6).toISOString() : null; // Massive ns -> ms
  }

  // 2. Options chain (options domain), paginated up to PAGE_LIMIT pages.
  const contracts = [];
  let optionsWarning = null;
  let nextPath = `/v3/snapshot/options/${encodeURIComponent(symbol)}?limit=250`;
  let pages = 0;
  let lastPageContractCount = 0;
  let sawExplicitEnd = false;
  while (nextPath && pages < PAGE_LIMIT) {
    const r = await fetchMassive(nextPath, { cacheTtlMs: 15000 });
    pages++;
    if (!r.ok) { optionsWarning = r.error; break; }
    const results = (r.json && r.json.results) || [];
    lastPageContractCount = results.length;
    contracts.push(...results);
    const nextUrl = r.json && r.json.next_url;
    if (nextUrl) {
      try {
        const u = new URL(nextUrl);
        nextPath = u.pathname + "?" + u.searchParams.toString();
      } catch (e) { nextPath = null; sawExplicitEnd = true; }
    } else {
      nextPath = null;
      sawExplicitEnd = true;
    }
  }
  const pageLimitReached = pages >= PAGE_LIMIT && !!nextPath;
  const hasMorePages = !!nextPath;
  const upstreamPaginationObserved = pages > 0 && !optionsWarning;

  const { chainComplete, truncated, completenessStatus, chainCompletenessModifier } =
    classifyCompleteness({ upstreamPaginationObserved, sawExplicitEnd, hasMorePages, pageLimitReached });

  // Options timestamp: MOST RECENT per-contract day.last_updated (ns).
  let optionsTimestampNs = null;
  let contractsWithTimestamp = 0;
  for (const c of contracts) {
    const t = c.day && c.day.last_updated;
    if (typeof t === "number") {
      contractsWithTimestamp++;
      if (optionsTimestampNs == null || t > optionsTimestampNs) optionsTimestampNs = t;
    }
  }
  const optionsAsOfUtc = optionsTimestampNs != null ? new Date(optionsTimestampNs / 1e6).toISOString() : null;

  const now = Date.now();
  const spotAgeMinutes = spotAsOfUtc ? (now - new Date(spotAsOfUtc).getTime()) / 60000 : null;
  const optionsAgeMinutes = optionsAsOfUtc ? (now - new Date(optionsAsOfUtc).getTime()) / 60000 : null;
  const spotFreshnessStatus = classifyFreshness(spotAgeMinutes);
  const optionsFreshnessStatus = classifyFreshness(optionsAgeMinutes);
  const gammaFreshnessStatus = combineFreshness(spotFreshnessStatus, optionsFreshnessStatus);
  const freshnessModifier = freshnessModifierFor(gammaFreshnessStatus);
  const dataMode = "DELAYED"; // confirmed plan tier (Options Starter + Stocks Starter); see FRESHNESS_SPEC.md

  const snapshotId = crypto.randomUUID ? crypto.randomUUID() : `snap_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const snapshot = computeOcmGammaSnapshot({
    contracts, spot, symbol, snapshotId,
    chainCompletenessModifier, freshnessModifier,
  });
  if (optionsWarning) snapshot.warnings.push(`options_chain_partial: ${optionsWarning}`);

  snapshot.pagesFetched = pages;
  snapshot.contractsFetched = contracts.length;
  snapshot.pageLimit = PAGE_LIMIT;
  snapshot.pageLimitReached = pageLimitReached;
  snapshot.hasMorePages = hasMorePages;
  snapshot.truncated = truncated;
  snapshot.chainComplete = chainComplete;
  snapshot.completenessStatus = completenessStatus;
  snapshot.completenessConfidenceModifier = chainCompletenessModifier;
  snapshot.upstreamPaginationObserved = upstreamPaginationObserved;
  snapshot.lastPageContractCount = lastPageContractCount;

  snapshot.spotAsOfUtc = spotAsOfUtc;
  snapshot.spotAgeMinutes = spotAgeMinutes;
  snapshot.spotFreshnessStatus = spotFreshnessStatus;
  snapshot.optionsAsOfUtc = optionsAsOfUtc;
  snapshot.optionsAgeMinutes = optionsAgeMinutes;
  snapshot.optionsFreshnessStatus = optionsFreshnessStatus;
  snapshot.contractsWithTimestamp = contractsWithTimestamp;
  snapshot.snapshotGeneratedAtUtc = new Date(now).toISOString();
  snapshot.snapshotAgeMinutes = 0;
  snapshot.gammaFreshnessStatus = gammaFreshnessStatus;
  snapshot.dataMode = dataMode;
  snapshot.stale = gammaFreshnessStatus === "STALE";

  let unavailableReason = null;
  if (!snapshot.valid) {
    if (snapshot.warnings.includes("no_spot_price_available")) unavailableReason = "NO_SPOT_PRICE";
    else if (snapshot.warnings.includes("no_contracts_returned")) unavailableReason = "NO_CONTRACTS_RETURNED";
    else if (snapshot.warnings.includes("no_contracts_had_both_oi_and_gamma")) unavailableReason = "NO_USABLE_CONTRACTS";
    else unavailableReason = "UNAVAILABLE";
  }

  const { status, reasons } = computeGammaStatus({
    valid: snapshot.valid,
    unavailableReason,
    gammaRegime: snapshot.gammaRegime,
    gammaFreshnessStatus,
    optionsFreshnessStatus,
    spotFreshnessStatus,
    completenessStatus,
    upstreamPaginationObserved,
    confidenceScore: snapshot.confidenceScore,
    minConfidence: MIN_CONFIDENCE,
  });
  snapshot.status = status;
  snapshot.gammaStatus = status; // alias, directive uses both names
  snapshot.gammaStatusReasons = reasons;
  snapshot.endpointLatencyMs = Date.now() - startedAt;

  return jsonResponse(200, snapshot);
};
