// netlify/functions/equity-snapshot.js
// Phase 2 — secure server-side proxy for the FOUR Massive stock endpoints
// the current ToF HTML currently calls directly from the browser with the
// API key in the query string (confirmed in Phase 1 audit):
//   1. treasury-yields
//   2. aggs/ticker/{symbol}/range/{mult}/{span}/{from}/{to}   (bars)
//   3. snapshot/locale/us/markets/stocks/tickers               (batched snapshot)
//   4. aggs/grouped/locale/us/market/stocks/{date}              (grouped daily)
//
// EQUITY DATA ONLY (directive Section "SEPARATE DATA DOMAINS" A). This
// function does not touch options data — see options-chain.js / ocm-gamma-snapshot.js.
//
// Request shape: GET /.netlify/functions/equity-snapshot?op=<op>&...params
//   op=treasuryYields
//   op=bars&ticker=AAPL&multiplier=15&timespan=minute&from=2026-06-01&to=2026-07-01
//   op=snapshot&tickers=AAPL,MSFT,NVDA   (comma-separated, batched server-side same as before)
//   op=grouped&date=2026-07-01

const { fetchMassive, validateSymbol, jsonResponse, errorResponse, requireMethod, rateLimitCheck } = require("./lib/massive-client");

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const ALLOWED_TIMESPANS = new Set(["minute", "hour", "day"]);
const BATCH_SIZE = 300; // mirrors existing client-side batching logic

exports.handler = async function handler(event) {
  const methodErr = requireMethod(event, ["GET"]);
  if (methodErr) return methodErr;

  const qs = event.queryStringParameters || {};
  const op = qs.op;

  // Coarse per-op rate limit on this warm instance (see SECURITY_LIMITATIONS.md).
  if (!rateLimitCheck("equity:" + op, 60, 60000)) {
    return errorResponse(429, "rate_limited", "Too many requests to this operation from this instance in the last minute.");
  }

  if (op === "treasuryYields") {
    const r = await fetchMassive(`/fed/v1/treasury-yields?limit=1&sort=date.desc`, { cacheTtlMs: 3600000 }); // yields change ~daily
    if (!r.ok) return errorResponse(r.status >= 400 && r.status < 600 ? r.status : 502, "upstream_error", r.error);
    return jsonResponse(200, r.json);
  }

  if (op === "bars") {
    const { ticker, multiplier, timespan, from, to } = qs;
    if (!validateSymbol(ticker || "")) return errorResponse(400, "invalid_symbol", "ticker failed validation");
    const mult = parseInt(multiplier, 10);
    if (!Number.isInteger(mult) || mult < 1 || mult > 1440) return errorResponse(400, "invalid_multiplier", "multiplier must be an integer 1-1440");
    if (!ALLOWED_TIMESPANS.has(timespan)) return errorResponse(400, "invalid_timespan", "timespan must be one of: minute, hour, day");
    if (!DATE_RE.test(from || "") || !DATE_RE.test(to || "")) return errorResponse(400, "invalid_date", "from/to must be YYYY-MM-DD");
    const r = await fetchMassive(`/v2/aggs/ticker/${encodeURIComponent(ticker)}/range/${mult}/${timespan}/${from}/${to}?adjusted=true&sort=asc&limit=5000`, { cacheTtlMs: 20000 });
    if (!r.ok) return errorResponse(r.status >= 400 && r.status < 600 ? r.status : 502, "upstream_error", r.error);
    return jsonResponse(200, r.json);
  }

  if (op === "snapshot") {
    const tickersRaw = qs.tickers || "";
    const tickers = tickersRaw.split(",").map(s => s.trim()).filter(Boolean);
    if (tickers.length === 0) return errorResponse(400, "missing_tickers", "tickers query param required (comma-separated)");
    if (tickers.length > 1000) return errorResponse(400, "too_many_tickers", "max 1000 tickers per request");
    for (const t of tickers) {
      if (!validateSymbol(t)) return errorResponse(400, "invalid_symbol", `ticker failed validation: ${t}`);
    }
    const all = [];
    const warnings = [];
    for (let i = 0; i < tickers.length; i += BATCH_SIZE) {
      const batch = tickers.slice(i, i + BATCH_SIZE);
      const r = await fetchMassive(`/v2/snapshot/locale/us/markets/stocks/tickers?tickers=${batch.join(",")}`, { cacheTtlMs: 15000 });
      if (!r.ok) { warnings.push(`batch_${i / BATCH_SIZE + 1}_failed: ${r.error}`); continue; }
      if (r.json && r.json.tickers) all.push(...r.json.tickers);
    }
    return jsonResponse(200, { status: "OK", tickers: all, warnings });
  }

  if (op === "grouped") {
    const date = qs.date;
    if (!DATE_RE.test(date || "")) return errorResponse(400, "invalid_date", "date must be YYYY-MM-DD");
    const r = await fetchMassive(`/v2/aggs/grouped/locale/us/market/stocks/${date}?adjusted=true`, { cacheTtlMs: 3600000 }); // a past day's grouped data never changes
    if (!r.ok) return errorResponse(r.status >= 400 && r.status < 600 ? r.status : 502, "upstream_error", r.error);
    return jsonResponse(200, r.json);
  }

  return errorResponse(400, "unknown_op", "op must be one of: treasuryYields, bars, snapshot, grouped");
};
