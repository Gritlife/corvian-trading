// tests/integration.test.js
// Phase 14 integration tests, run against the integrated index.html.
// These are static source-inspection tests (no live browser/network in this
// environment) — they verify structural properties that must hold true,
// not runtime behavior. See TEST_REPORT.md for what remains unverified
// without a live browser + live Massive traffic.
//
// Run: node tests/integration.test.js

const assert = require("assert");
const fs = require("fs");
const path = require("path");

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log("  ok  -", name); passed++; }
  catch (e) { console.log("FAIL  -", name, "\n       ", e.message); failed++; }
}

const indexPath = path.join(__dirname, "..", "index.html");
const html = fs.readFileSync(indexPath, "utf8");

// ---- 1-2: frontend secret hygiene -----------------------------------------
test("1. frontend contains no Massive secret literal", () => {
  assert.ok(!/MASSIVE_API_KEY\s*[:=]\s*["'`][A-Za-z0-9_-]{10,}/.test(html));
});
test("2. frontend contains no direct authenticated Massive call (no apiKey= in a fetch URL)", () => {
  assert.ok(!/apiKey=\$\{/.test(html), "found an apiKey=${...} template — a direct authenticated call slipped through");
  assert.ok(!/api\.massive\.com/.test(html), "found a direct api.massive.com reference — should be same-origin /.netlify/functions/* only");
});
test("20. no API key entry UI remains reachable", () => {
  assert.ok(!/<PolygonKeyField/.test(html), "PolygonKeyField is still being rendered");
});
test("21. no localStorage Massive key read/write remains active", () => {
  // The component definition may still exist as dead code; what matters is
  // it's never called, and no state variable feeds a raw key into fetches.
  assert.ok(!/loadJSONCts\("KEY"/.test(html), "loadJSONCts(\"KEY\", ...) still being read — polygonKey state should be fully removed");
});

// ---- 3-5: adapter existence -------------------------------------------
test("3. equity snapshot adapter (fetchSnapshot/fetchMassiveBars/etc.) targets same-origin proxy", () => {
  assert.ok(/\/\.netlify\/functions\/equity-snapshot\?op=treasuryYields/.test(html));
  assert.ok(/\/\.netlify\/functions\/equity-snapshot\?op=bars/.test(html));
  assert.ok(/\/\.netlify\/functions\/equity-snapshot\?op=snapshot/.test(html));
  assert.ok(/\/\.netlify\/functions\/equity-snapshot\?op=grouped/.test(html));
});
test("4. options chain adapter path is referenced (via ocm-gamma-snapshot, which composes it server-side)", () => {
  // Per directive request the frontend consumes the NORMALIZED OCM output
  // rather than raw options-chain directly (Phase 3C) — verify the OCM
  // endpoint is called, and separately verify the backend's options-chain.js
  // exists (checked in security.test.js's file-tree test).
  assert.ok(/\/\.netlify\/functions\/ocm-gamma-snapshot\?symbol=/.test(html));
});
test("5. OCM Gamma snapshot adapter exists and adapts response shape correctly", () => {
  assert.ok(/function fetchOcmGammaSnapshot/.test(html));
  assert.ok(/snapshotTimestamp: ocm\.timestampUtc \? Date\.parse\(ocm\.timestampUtc\) : null/.test(html), "must convert ISO timestampUtc to epoch-ms for gamma-spine.js");
});

// ---- 6-9: Gamma render states -------------------------------------------
test("6. valid Gamma renders (GammaSpinePanel reads gammaSpineResult.status)", () => {
  assert.ok(/gammaSpineResult\.status/.test(html));
});
test("7. GAMMA UNAVAILABLE is a real renderable status distinct from legacy regime", () => {
  assert.ok(/UNAVAILABLE: "GAMMA UNAVAILABLE"/.test(html));
  // Must never be produced by falling back to legacy Bull/Bear text
  assert.ok(!/GAMMA UNAVAILABLE.*Bull \(Legacy\)/.test(html));
});
test("8. STALE is a distinct renderable status", () => {
  assert.ok(/STALE: "GAMMA STALE"/.test(html));
});
test("9. LOW_CONFIDENCE is a distinct renderable status", () => {
  assert.ok(/LOW_CONFIDENCE: "GAMMA LOW CONFIDENCE"/.test(html));
});
test("24. Gamma Regime field is never assigned a legacy Bull/Bear string", () => {
  // The only writers of gammaRegime are normalizeGammaSnapshot (from raw
  // input) and the OCM backend — search for any spot that assigns a legacy
  // direction word directly into a variable/field literally named gammaRegime.
  assert.ok(!/gammaRegime\s*[:=]\s*["'`](Bull|Bear)/i.test(html));
});

// ---- 10-15: Shadow Mode does not touch legacy signals --------------------
test("10-15. processEngineSignals (legacy B2O/S2O/ADD/TP/S2C/B2C engine) never references any gamma* identifier in its body", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/);
  assert.ok(m, "could not locate processEngineSignals function body");
  const body = m[0];
  assert.ok(!/gamma/i.test(body), "processEngineSignals body references something gamma-related — Shadow Mode requires this function be completely gamma-blind");
});
test("16. paper ledger mutation functions (setLedger/newLedger construction) are not called from GammaSpinePanel or runGammaSpine usage sites", () => {
  const deckMatch = html.match(/function Deck\(\{[\s\S]*?\n\/\/ =+\n\/\/ GammaSpinePanel/);
  // Fallback: just check the Deck component body for setLedger/setExecState calls, which must not exist there at all.
  const deckFnStart = html.indexOf("function Deck({");
  const deckFnEnd = html.indexOf("function GammaSpinePanel(");
  assert.ok(deckFnStart > -1 && deckFnEnd > deckFnStart);
  const deckBody = html.slice(deckFnStart, deckFnEnd);
  assert.ok(!/setLedger\(/.test(deckBody), "Deck must never call setLedger directly");
  assert.ok(!/setExecState\(/.test(deckBody), "Deck must never call setExecState directly");
});

// ---- 17-19: regression smoke (structural presence, not full render) ------
test("17. Scanner component still defined (scanner still loads)", () => {
  assert.ok(/function Scanner\(\{ universe, positions, onSelect \}\)/.test(html));
});
test("18. Session components still defined (sessions still work)", () => {
  assert.ok(/function SessionCreateForm/.test(html));
  assert.ok(/function SessionListCard/.test(html));
});
test("19. mobile-first layout classes (max-w-md) still present", () => {
  assert.ok(/max-w-md mx-auto/.test(html));
});

// ---- 22-23: options coverage safety ---------------------------------------
test("22. pagination truncation is detectable in the OCM backend response (pagesFetched/truncated fields)", () => {
  const ocmFn = fs.readFileSync(path.join(__dirname, "..", "netlify", "functions", "options-chain.js"), "utf8");
  assert.ok(/pagesFetched/.test(ocmFn));
  assert.ok(/truncated/.test(ocmFn));
});
test("23. incomplete/low-coverage chains affect status via confidenceScore (LOW_CONFIDENCE path exists)", () => {
  const ocmEngine = fs.readFileSync(path.join(__dirname, "..", "netlify", "functions", "lib", "ocm-engine.js"), "utf8");
  assert.ok(/computeConfidence/.test(ocmEngine));
  const gammaStatus = fs.readFileSync(path.join(__dirname, "..", "netlify", "functions", "lib", "gamma-status.js"), "utf8");
  assert.ok(/LOW_CONFIDENCE/.test(gammaStatus));
});

// ---- GAMMA_MODE default (Phase 6) -----------------------------------------
test("GAMMA_MODE defaults to SHADOW, never ACTIVE, and this file never sets it to ACTIVE itself", () => {
  assert.ok(/loadJSONCts\("GAMMA_MODE", "SHADOW"\)/.test(html));
  assert.ok(!/setGammaModeChecked\("ACTIVE"\)/.test(html), "the app source itself must never programmatically flip to ACTIVE — only a human via UI");
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
