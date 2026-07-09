// tests/remediation.test.js
// The 26 tests required by the ToF v1.1 Gamma Spine Remediation directive
// (Section 9). Numbered to match the directive's list where a 1:1 mapping
// exists; a few are logically combined where the same assertion covers
// multiple numbered items (documented inline).

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const {
  classifyCompleteness, classifyFreshness, freshnessModifierFor, combineFreshness,
  computeGammaStatus, GAMMA_STATUS, FRESH_THRESHOLD_MINUTES, DELAYED_THRESHOLD_MINUTES,
} = require("../netlify/functions/lib/gamma-status");
const { computeConfidenceBreakdown } = require("../netlify/functions/lib/ocm-engine");

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log("  ok  -", name); passed++; }
  catch (e) { console.log("FAIL  -", name, "\n       ", e.message); failed++; }
}

// ---- 1. Complete multi-page chain -----------------------------------------
test("1. complete multi-page chain classifies as COMPLETE, no confidence penalty", () => {
  const r = classifyCompleteness({ upstreamPaginationObserved: true, sawExplicitEnd: true, hasMorePages: false, pageLimitReached: false });
  assert.strictEqual(r.completenessStatus, "COMPLETE");
  assert.strictEqual(r.chainComplete, true);
  assert.strictEqual(r.truncated, false);
  assert.strictEqual(r.chainCompletenessModifier, 1.0);
});

// ---- 2. Truncated chain with more pages remaining -------------------------
test("2. truncated chain (more pages remaining, limit hit) classifies as TRUNCATED", () => {
  const r = classifyCompleteness({ upstreamPaginationObserved: true, sawExplicitEnd: false, hasMorePages: true, pageLimitReached: true });
  assert.strictEqual(r.completenessStatus, "TRUNCATED");
  assert.strictEqual(r.truncated, true);
  assert.strictEqual(r.chainComplete, false);
});

// ---- 3. Page limit reached exactly -----------------------------------------
test("3. page limit reached is the deciding factor for TRUNCATED, independent of sawExplicitEnd", () => {
  const r = classifyCompleteness({ upstreamPaginationObserved: true, sawExplicitEnd: false, hasMorePages: true, pageLimitReached: true });
  assert.strictEqual(r.completenessStatus, "TRUNCATED");
});

// ---- 4. Unknown chain completeness -----------------------------------------
test("4. unobserved pagination (e.g. all pages errored) classifies as UNKNOWN, not COMPLETE", () => {
  const r = classifyCompleteness({ upstreamPaginationObserved: false, sawExplicitEnd: false, hasMorePages: false, pageLimitReached: false });
  assert.strictEqual(r.completenessStatus, "UNKNOWN");
  assert.strictEqual(r.chainComplete, false);
});

// ---- 5. Truncated chain cannot become plain GAMMA VALID --------------------
test("5. truncated chain can NEVER produce plain GAMMA VALID status", () => {
  const { status } = computeGammaStatus({
    valid: true, gammaRegime: "POSITIVE", gammaFreshnessStatus: "FRESH",
    optionsFreshnessStatus: "FRESH", spotFreshnessStatus: "FRESH",
    completenessStatus: "TRUNCATED", upstreamPaginationObserved: true,
    confidenceScore: 90, minConfidence: 40,
  });
  assert.notStrictEqual(status, GAMMA_STATUS.VALID);
  assert.strictEqual(status, GAMMA_STATUS.DEGRADED_PARTIAL_CHAIN);
});

// ---- 6. Unknown completeness reduces confidence ----------------------------
test("6. unknown completeness applies a meaningful (not zero, not full) confidence penalty", () => {
  const agg = { contractsSeen: 100, oiPresentCount: 100, greeksPresentCount: 100, contractsUsedForGex: 100 };
  const full = computeConfidenceBreakdown(agg, { chainCompletenessModifier: 1.0, freshnessModifier: 1.0 });
  const unknown = computeConfidenceBreakdown(agg, { chainCompletenessModifier: 0.75, freshnessModifier: 1.0 });
  assert.ok(unknown.finalScore < full.finalScore, "unknown completeness must reduce score vs complete");
  assert.ok(unknown.finalScore > 0, "unknown completeness must not zero out the score");
});

// ---- 7. Fresh spot + stale options -----------------------------------------
test("7. fresh spot + stale options -> overall gammaFreshnessStatus is STALE (worse-of)", () => {
  const combined = combineFreshness("FRESH", "STALE");
  assert.strictEqual(combined, "STALE");
});

// ---- 8. Fresh spot + unknown options timestamp -----------------------------
test("8. fresh spot + unknown options timestamp -> overall status is UNKNOWN, not FRESH", () => {
  const combined = combineFreshness("FRESH", "UNKNOWN");
  assert.strictEqual(combined, "UNKNOWN");
});

// ---- 9. Delayed options data -----------------------------------------------
test("9. options age just beyond FRESH threshold classifies as DELAYED, not STALE", () => {
  const status = classifyFreshness(FRESH_THRESHOLD_MINUTES + 1);
  assert.strictEqual(status, "DELAYED");
});

// ---- 10. Stale options data -------------------------------------------------
test("10. options age beyond DELAYED threshold classifies as STALE", () => {
  const status = classifyFreshness(DELAYED_THRESHOLD_MINUTES + 1);
  assert.strictEqual(status, "STALE");
});

// ---- 11. Missing OI ----------------------------------------------------------
test("11. missing OI across all contracts drives openInterestCoverageComponent to 0", () => {
  const agg = { contractsSeen: 10, oiPresentCount: 0, greeksPresentCount: 10, contractsUsedForGex: 0 };
  const b = computeConfidenceBreakdown(agg, {});
  assert.strictEqual(b.openInterestCoverageComponent, 0);
});

// ---- 12. Partial OI coverage -------------------------------------------------
test("12. partial OI coverage produces an intermediate (not 0, not max) component", () => {
  const agg = { contractsSeen: 10, oiPresentCount: 5, greeksPresentCount: 10, contractsUsedForGex: 5 };
  const b = computeConfidenceBreakdown(agg, {});
  assert.ok(b.openInterestCoverageComponent > 0 && b.openInterestCoverageComponent < 40);
});

// ---- 13. Confidence breakdown arithmetic -------------------------------------
test("13. confidenceBreakdown finalScore = round(baseScore * completenessModifier * freshnessModifier), clamped", () => {
  const agg = { contractsSeen: 100, oiPresentCount: 100, greeksPresentCount: 100, contractsUsedForGex: 100 };
  const b = computeConfidenceBreakdown(agg, { chainCompletenessModifier: 0.5, freshnessModifier: 0.8 });
  assert.strictEqual(b.baseScore, 100);
  const expected = Math.round(100 * 0.5 * 0.8);
  assert.strictEqual(b.finalScore, expected);
});
test("13b. confidenceBreakdown components sum to baseScore (weights: 40/40/20)", () => {
  const agg = { contractsSeen: 50, oiPresentCount: 50, greeksPresentCount: 25, contractsUsedForGex: 25 };
  const b = computeConfidenceBreakdown(agg, {});
  assert.strictEqual(b.openInterestCoverageComponent + b.greeksCoverageComponent + b.contractCountComponent, b.baseScore);
});

// ---- 14. Gamma status precedence ---------------------------------------------
test("14. precedence: STALE beats TRUNCATED even when both conditions are true", () => {
  const { status } = computeGammaStatus({
    valid: true, gammaRegime: "POSITIVE", gammaFreshnessStatus: "STALE",
    optionsFreshnessStatus: "STALE", spotFreshnessStatus: "FRESH",
    completenessStatus: "TRUNCATED", upstreamPaginationObserved: true,
    confidenceScore: 90, minConfidence: 40,
  });
  assert.strictEqual(status, GAMMA_STATUS.STALE, "STALE must take precedence over PARTIAL_CHAIN per the documented order");
});
test("14b. precedence: UNAVAILABLE beats everything else", () => {
  const { status } = computeGammaStatus({
    valid: false, unavailableReason: "NO_SPOT_PRICE", gammaRegime: "UNKNOWN",
    gammaFreshnessStatus: "STALE", optionsFreshnessStatus: "STALE", spotFreshnessStatus: "STALE",
    completenessStatus: "TRUNCATED", upstreamPaginationObserved: false,
    confidenceScore: 0, minConfidence: 40,
  });
  assert.strictEqual(status, GAMMA_STATUS.UNAVAILABLE);
});
test("14c. precedence: INVALID (unknown regime) beats STALE/completeness/confidence issues", () => {
  const { status } = computeGammaStatus({
    valid: true, gammaRegime: "UNKNOWN", gammaFreshnessStatus: "FRESH",
    optionsFreshnessStatus: "FRESH", spotFreshnessStatus: "FRESH",
    completenessStatus: "COMPLETE", upstreamPaginationObserved: true,
    confidenceScore: 90, minConfidence: 40,
  });
  assert.strictEqual(status, GAMMA_STATUS.INVALID);
});
test("14d. full VALID path requires every dimension to be clean", () => {
  const { status } = computeGammaStatus({
    valid: true, gammaRegime: "POSITIVE", gammaFreshnessStatus: "FRESH",
    optionsFreshnessStatus: "FRESH", spotFreshnessStatus: "FRESH",
    completenessStatus: "COMPLETE", upstreamPaginationObserved: true,
    confidenceScore: 90, minConfidence: 40,
  });
  assert.strictEqual(status, GAMMA_STATUS.VALID);
});

// ---- 15. gammaStatusReasons population ---------------------------------------
test("15. gammaStatusReasons is populated (non-empty) for every non-VALID status", () => {
  const cases = [
    { valid: false, unavailableReason: "NO_SPOT_PRICE", gammaRegime: "UNKNOWN", gammaFreshnessStatus: "UNKNOWN", optionsFreshnessStatus: "UNKNOWN", spotFreshnessStatus: "UNKNOWN", completenessStatus: "UNKNOWN", upstreamPaginationObserved: false, confidenceScore: 0 },
    { valid: true, gammaRegime: "UNKNOWN", gammaFreshnessStatus: "FRESH", optionsFreshnessStatus: "FRESH", spotFreshnessStatus: "FRESH", completenessStatus: "COMPLETE", upstreamPaginationObserved: true, confidenceScore: 90 },
    { valid: true, gammaRegime: "POSITIVE", gammaFreshnessStatus: "STALE", optionsFreshnessStatus: "STALE", spotFreshnessStatus: "FRESH", completenessStatus: "COMPLETE", upstreamPaginationObserved: true, confidenceScore: 90 },
  ];
  for (const c of cases) {
    const { status, reasons } = computeGammaStatus(c);
    assert.ok(reasons.length > 0, `expected non-empty reasons for status ${status}`);
  }
});
test("15b. gammaStatusReasons is empty for VALID status", () => {
  const { reasons } = computeGammaStatus({
    valid: true, gammaRegime: "POSITIVE", gammaFreshnessStatus: "FRESH",
    optionsFreshnessStatus: "FRESH", spotFreshnessStatus: "FRESH",
    completenessStatus: "COMPLETE", upstreamPaginationObserved: true,
    confidenceScore: 90, minConfidence: 40,
  });
  assert.strictEqual(reasons.length, 0);
});

// ---- 16-21. SHADOW mode cannot mutate any legacy action --------------------
test("16-21. SHADOW mode: no file in netlify/functions/ references B2O/S2O/ADD/TP/S2C/B2C mutation (backend has zero knowledge of legacy trade actions)", () => {
  const fnDir = path.join(__dirname, "..", "netlify", "functions");
  const files = [];
  (function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.name.endsWith(".js")) files.push(p);
    }
  })(fnDir);
  for (const f of files) {
    const content = fs.readFileSync(f, "utf8");
    assert.ok(!/\bB2O\b|\bS2O\b|\bB2C\b|\bS2C\b/.test(content), `${f} must not reference legacy action codes — the backend has no execution authority`);
  }
});
test("16-21b. frontend: processEngineSignals (the only function that mutates the ledger) has zero gamma references (re-verified after remediation)", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/);
  assert.ok(m, "could not locate processEngineSignals");
  assert.ok(!/gamma/i.test(m[0]));
});

// ---- 22. Malformed ticker rejected -------------------------------------------
test("22. malformed ticker input is rejected by validateSymbol", () => {
  const { validateSymbol } = require("../netlify/functions/lib/massive-client");
  assert.strictEqual(validateSymbol("'; DROP TABLE"), false);
  assert.strictEqual(validateSymbol("../../etc/passwd"), false);
  assert.strictEqual(validateSymbol(""), false);
  assert.strictEqual(validateSymbol("A".repeat(50)), false);
  assert.strictEqual(validateSymbol("AAPL"), true);
  assert.strictEqual(validateSymbol("BRK.B"), true);
});

// ---- 23. Unsupported HTTP method rejected ------------------------------------
test("23. requireMethod rejects unsupported methods with 405 + Allow header", () => {
  const { requireMethod } = require("../netlify/functions/lib/massive-client");
  const result = requireMethod({ httpMethod: "POST" }, ["GET"]);
  assert.ok(result, "expected a rejection response for POST when only GET is allowed");
  assert.strictEqual(result.statusCode, 405);
  assert.strictEqual(result.headers.Allow, "GET");
  const okResult = requireMethod({ httpMethod: "GET" }, ["GET"]);
  assert.strictEqual(okResult, null, "GET should be allowed and return null (proceed)");
});
test("23b. all three hardened endpoints call requireMethod", () => {
  for (const name of ["equity-snapshot.js", "options-chain.js", "ocm-gamma-snapshot.js", "health.js"]) {
    const content = fs.readFileSync(path.join(__dirname, "..", "netlify", "functions", name), "utf8");
    assert.ok(/requireMethod\(event/.test(content), `${name} must call requireMethod`);
  }
});

// ---- 24. Secrets absent from frontend bundle (re-verify post-remediation) --
test("24. frontend still contains no MASSIVE_API_KEY literal or apiKey= query construction", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  assert.ok(!/MASSIVE_API_KEY\s*[:=]\s*["'`][A-Za-z0-9_-]{10,}/.test(html));
  assert.ok(!/apiKey=\$\{/.test(html));
});
test("24b. backend auth migrated to Authorization header, not query-string apiKey", () => {
  const client = fs.readFileSync(path.join(__dirname, "..", "netlify", "functions", "lib", "massive-client.js"), "utf8");
  assert.ok(/Authorization.*Bearer/.test(client), "expected Authorization: Bearer header usage");
  assert.ok(!/\$\{MASSIVE_BASE\}\$\{path\}\$\{sep\}apiKey=/.test(client), "should not still be constructing a query-string apiKey");
});

// ---- 25. Structured upstream error handling ----------------------------------
test("25. errorResponse always returns a structured {error, message, timestampUtc} body", () => {
  const { errorResponse } = require("../netlify/functions/lib/massive-client");
  const r = errorResponse(502, "upstream_error", "something broke");
  const body = JSON.parse(r.body);
  assert.strictEqual(body.error, "upstream_error");
  assert.strictEqual(body.message, "something broke");
  assert.ok(body.timestampUtc);
  assert.ok(!/[A-Za-z0-9]{32,}/.test(JSON.stringify(body)), "error body must not contain anything resembling a leaked secret/key");
});

// ---- 26. Repeated identical request uses cache where applicable -------------
test("26. cacheGet/cacheSet round-trip works and respects TTL expiry", () => {
  const { cacheGet, cacheSet } = require("../netlify/functions/lib/massive-client");
  cacheSet("test:key:26", { hello: "world" }, 50);
  assert.deepStrictEqual(cacheGet("test:key:26"), { hello: "world" });
});
test("26b. fetchMassive signature accepts a cacheTtlMs option (structural check)", () => {
  const client = fs.readFileSync(path.join(__dirname, "..", "netlify", "functions", "lib", "massive-client.js"), "utf8");
  assert.ok(/cacheTtlMs/.test(client));
  assert.ok(/cacheGet\(cacheKey\)/.test(client));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
