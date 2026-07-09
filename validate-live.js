// netlify/functions/validate-live.js
// REMEDIATION Phase 10 — live validation harness.
//
// Purely diagnostic. Calls the SAME code path as ocm-gamma-snapshot.js (by
// calling that function's logic indirectly via HTTP-equivalent internal
// invocation) for a set of symbols and returns a structured report. This
// function does NOT touch trading logic, the paper ledger, or any
// execution path — it exists solely to let a human (or a monitoring job)
// verify the deployed pipeline is actually working with real data.
//
// Request: GET /.netlify/functions/validate-live?symbols=SPY,QQQ,TSLA
//   (defaults to the directive's suggested mix if symbols is omitted)

const { validateSymbol, jsonResponse, errorResponse, requireMethod } = require("./lib/massive-client");
const ocmHandler = require("./ocm-gamma-snapshot").handler;

const DEFAULT_SYMBOLS = ["SPY", "QQQ", "TSLA", "NVDA", "AMD", "F"]; // F = smaller/less liquid optionable equity per directive suggestion

exports.handler = async function handler(event) {
  const methodErr = requireMethod(event, ["GET"]);
  if (methodErr) return methodErr;

  const qs = event.queryStringParameters || {};
  let symbols = DEFAULT_SYMBOLS;
  if (qs.symbols) {
    symbols = qs.symbols.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
  }
  if (symbols.length === 0) return errorResponse(400, "no_symbols", "no valid symbols provided");
  if (symbols.length > 10) return errorResponse(400, "too_many_symbols", "max 10 symbols per validation run");
  for (const s of symbols) {
    if (!validateSymbol(s)) return errorResponse(400, "invalid_symbol", `symbol failed validation: ${s}`);
  }

  const results = [];
  for (const symbol of symbols) {
    const requestTime = new Date().toISOString();
    const startedAt = Date.now();
    try {
      // Invoke the real ocm-gamma-snapshot handler in-process — this is the
      // ACTUAL code path used by the app, not a reimplementation, so the
      // harness can never silently drift from real behavior.
      const fakeEvent = { httpMethod: "GET", queryStringParameters: { symbol } };
      const resp = await ocmHandler(fakeEvent);
      const body = JSON.parse(resp.body);
      const latencyMs = Date.now() - startedAt;

      if (resp.statusCode !== 200) {
        results.push({
          ticker: symbol, requestTime, error: body.message || "non-200 response",
          statusCode: resp.statusCode, endpointLatencyMs: latencyMs,
        });
        continue;
      }

      results.push({
        ticker: symbol,
        requestTime,
        spotPrice: body.underlyingSpot,
        spotTimestamp: body.spotAsOfUtc,
        spotAgeMinutes: body.spotAgeMinutes,
        optionsTimestamp: body.optionsAsOfUtc,
        optionsAgeMinutes: body.optionsAgeMinutes,
        pagesFetched: body.pagesFetched,
        contractsFetched: body.contractsFetched,
        chainComplete: body.chainComplete,
        truncated: body.truncated,
        dataMode: body.dataMode,
        gammaFlip: body.gammaFlip,
        positiveGammaWall: body.positiveGammaWall,
        negativeGammaPit: body.negativeGammaPit,
        totalNetGex: body.totalNetGex,
        confidenceScore: body.confidenceScore,
        confidenceBreakdown: body.confidenceBreakdown,
        gammaStatus: body.gammaStatus,
        gammaStatusReasons: body.gammaStatusReasons,
        endpointLatencyMs: latencyMs,
        upstreamErrorState: body.warnings && body.warnings.length > 0 ? body.warnings : null,
      });
    } catch (e) {
      results.push({
        ticker: symbol, requestTime, error: e.message,
        endpointLatencyMs: Date.now() - startedAt,
      });
    }
  }

  // Note re: index/SPX options — Massive supports index options via the
  // I: prefix (e.g. I:SPX) per their documented knowledge-base article, but
  // this harness does not include SPX by default since it requires a
  // different underlying-spot lookup (indices aren't in the equity
  // snapshot endpoint the same way) that hasn't been implemented/tested in
  // this pass. Do not assume it works without adding & testing that path.
  return jsonResponse(200, {
    generatedAtUtc: new Date().toISOString(),
    symbolsRequested: symbols,
    results,
    note: "Diagnostic only. Does not touch trading logic, paper ledger, or execution. SPX/index options are NOT validated by this harness — see code comment.",
  });
};
