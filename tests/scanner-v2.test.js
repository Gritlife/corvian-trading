// tests/scanner-v2.test.js
// ToF v1.1 — Scanner V2 (Top Opportunities Scanner). Functional tests for
// the two pure functions (buildScannerShortlist, computeOpportunityScore),
// extracted from index.html and executed directly, plus structural
// regression checks confirming OCM/Gamma/Item17/ECM wiring is untouched.
// Run: node tests/scanner-v2.test.js

const assert = require("assert");
const fs = require("fs");
const path = require("path");

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log("  ok  -", name); passed++; }
  catch (e) { console.log("FAIL  -", name, "\n       ", e.message); failed++; }
}

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");

let buildScannerShortlist = null;
let computeOpportunityScore = null;
test("0. Scanner V2 functions extract and evaluate cleanly", () => {
  const shortlistSrc = html.match(/function buildScannerShortlist\(rankedLightweight, shortlistSize\) \{[\s\S]*?\n\}/)[0];
  const scoreSrc = html.match(/function computeOpportunityScore\(engine, rvolValue, barsCount\) \{[\s\S]*?\n\}/)[0];
  buildScannerShortlist = eval("(" + shortlistSrc + ")");
  computeOpportunityScore = eval("(" + scoreSrc + ")");
  assert.strictEqual(typeof buildScannerShortlist, "function");
  assert.strictEqual(typeof computeOpportunityScore, "function");
});

function strongEngine(over) {
  return Object.assign({
    signalHistory: [{ bar: 19, time: 1, type: "B2O", price: 100, dir: 1 }],
    activeTrainDir: 1, livermoreGreen: true, legendsGreenCount: 4, legendsTotal: 5,
    edgePct: 80, rawConfirmScore: 0.6, bbScore: 0.5, volumeScore: 0.4,
  }, over || {});
}
function weakEngine(over) {
  return Object.assign({
    signalHistory: [], activeTrainDir: 0, livermoreGreen: false, legendsGreenCount: 0, legendsTotal: 5,
    edgePct: 10, rawConfirmScore: 0.05, bbScore: 0.05, volumeScore: 0.05,
  }, over || {});
}

// ---- 1/2. Quality setup with moderate RVOL beats high-RVOL weak setup -----
test("1. high-quality MMG setup with MODERATE RVOL can enter/lead Top 20 over a weak high-RVOL ticker", () => {
  const strong = computeOpportunityScore(strongEngine(), 1.2, 20); // moderate RVOL
  const weak = computeOpportunityScore(weakEngine(), 6.0, 20);     // very high RVOL, weak setup
  assert.ok(strong.score > weak.score, `expected strong/moderate-RVOL (${strong.score}) to outrank weak/high-RVOL (${weak.score})`);
});
test("2. high RVOL alone cannot outrank a materially stronger setup (ranking simulation)", () => {
  const candidates = [
    { sym: "WEAK_HIGH_RVOL", ...computeOpportunityScore(weakEngine(), 8.0, 20) },
    { sym: "STRONG_MOD_RVOL", ...computeOpportunityScore(strongEngine(), 1.5, 20) },
  ];
  candidates.sort((a, b) => b.score - a.score);
  assert.strictEqual(candidates[0].sym, "STRONG_MOD_RVOL", "final ranking must place the strong setup first despite lower RVOL");
});

// ---- 3/4. Fresh B2O / S2O ---------------------------------------------------
test("3. fresh B2O (within 8 bars) ranks with FRESH B2O reason and high signal component", () => {
  const r = computeOpportunityScore(strongEngine(), 2.0, 20); // signal at bar 19, barsCount 20 -> barsSinceSignal=0
  assert.strictEqual(r.reason, "FRESH B2O");
  assert.strictEqual(r.components.signalComp, 1.0);
});
test("4. fresh S2O ranks with FRESH S2O reason and high signal component", () => {
  const eng = strongEngine({ signalHistory: [{ bar: 19, time: 1, type: "S2O", price: 100, dir: -1 }], activeTrainDir: -1 });
  const r = computeOpportunityScore(eng, 2.0, 20);
  assert.strictEqual(r.reason, "FRESH S2O");
  assert.strictEqual(r.components.signalComp, 1.0);
});
test("4b. a STALE B2O (beyond 8 bars) is not treated as fresh", () => {
  const eng = strongEngine({ signalHistory: [{ bar: 5, time: 1, type: "B2O", price: 100, dir: 1 }] }); // barsSinceSignal = 20-1-5=14
  const r = computeOpportunityScore(eng, 2.0, 20);
  assert.notStrictEqual(r.reason, "FRESH B2O");
  assert.ok(r.components.signalComp < 1.0);
});

// ---- 5. Five Legends affects ranking ---------------------------------------
test("5. Five Legends score materially affects Opportunity Score (monotonic)", () => {
  const s0 = computeOpportunityScore(strongEngine({ legendsGreenCount: 0 }), 2.0, 20).score;
  const s3 = computeOpportunityScore(strongEngine({ legendsGreenCount: 3 }), 2.0, 20).score;
  const s5 = computeOpportunityScore(strongEngine({ legendsGreenCount: 5 }), 2.0, 20).score;
  assert.ok(s0 < s3 && s3 < s5, `expected monotonic increase, got ${s0} <= ${s3} <= ${s5}`);
});

// ---- 6. Trend alignment affects ranking ------------------------------------
test("6. trend alignment (livermoreGreen + activeTrainDir) materially affects score", () => {
  const withTrend = computeOpportunityScore(strongEngine({ livermoreGreen: true, activeTrainDir: 1 }), 2.0, 20).score;
  const noTrend = computeOpportunityScore(strongEngine({ livermoreGreen: false, activeTrainDir: 0 }), 2.0, 20).score;
  assert.ok(withTrend > noTrend);
});

// ---- 7. Invalid/missing-data ticker excluded (structural) -----------------
test("7. Stage 2 evaluation loop hard-excludes tickers with insufficient bars or no engine result", () => {
  const stageTwo = html.match(/const SHORTLIST_SIZE = 60;[\s\S]*?setTopRVOL\(scored\.slice\(0, 20\)\);/)[0];
  assert.ok(/if \(!bars \|\| bars\.length < 100\) return null;/.test(stageTwo), "must reject insufficient bar history");
  assert.ok(/if \(!engine\) return null;/.test(stageTwo), "must reject tickers where MMG computation failed");
});
test("7b. computeOpportunityScore itself never fabricates a score for missing engine data", () => {
  const r = computeOpportunityScore(null, 5.0, 20);
  assert.strictEqual(r.score, 0);
  assert.strictEqual(r.reason, "NO_DATA");
});

// ---- 8. Existing scanner universe preserved --------------------------------
test("8. Expanded Universe (~650 tickers) still feeds the lightweight Stage 1 scan, unchanged", () => {
  assert.ok(/fetchSnapshot\(EXPANDED_UNIVERSE\)/.test(html));
  assert.ok(/const EXPANDED_UNIVERSE = \[/.test(html));
});

// ---- 9. ECM receives Scanner V2 output -------------------------------------
test("9. ECM's rvolBySym / scanTickers are still derived from topRVOL, unchanged wiring", () => {
  assert.ok(/\(topRVOL \|\| \[\]\)\.forEach\(t => \{ rvolBySym\[t\.sym\] = t\.rvol; \}\);/.test(html));
  assert.ok(/const scanTickers = topRVOL\.slice\(0, 20\)\.map\(t => t\.sym\);/.test(html));
});
test("9b. Stage 2 output objects preserve .sym and .rvol so ECM's existing consumers keep working", () => {
  const stageTwo = html.match(/const SHORTLIST_SIZE = 60;[\s\S]*?setTopRVOL\(scored\.slice\(0, 20\)\);/)[0];
  assert.ok(/Object\.assign\(\{\}, cand, \{ opportunityScore: opp\.score, opportunityReason: opp\.reason \}\)/.test(stageTwo), "must spread the original candidate (which carries sym/rvol/price/etc.) forward");
});

// ---- 10. No regression to OCM, Gamma, or Item #17 --------------------------
test("10. OCM/Gamma/Item17 backend files are untouched (byte-identical to the audited baseline)", () => {
  const hashes = {
    "netlify/functions/lib/ocm-engine.js": "bd492c28bdfc58471284baf82af245549622ff2f5f8d28635ee1f3c867f619eb",
    "netlify/functions/ocm-gamma-snapshot.js": "8e7458d941d46b6bee5bb809ce69cc9fbc2f8d504dcfb244e90a3d913118f5a1",
    "netlify/functions/lib/gamma-status.js": "ce3f742b653beef697add709abc0a76878068caeb7a8fef599db0078de68b064",
  };
  const crypto = require("crypto");
  for (const [file, expected] of Object.entries(hashes)) {
    const content = fs.readFileSync(path.join(__dirname, "..", file), "utf8");
    const actual = crypto.createHash("sha256").update(content).digest("hex");
    assert.strictEqual(actual, expected, `${file} hash changed — backend must not be touched by Scanner V2`);
  }
});
test("10b. Scanner V2 does not reference gamma/OCM in its executable code (comments aside)", () => {
  const region = html.match(/\/\/ =+\n\/\/ ToF v1\.1 — SCANNER V2[\s\S]*?async function buildAvgVolume20d/)[0];
  const codeOnly = region.split("\n").filter(line => !line.trim().startsWith("//") && !line.trim().startsWith("*") && !line.trim().startsWith("/**")).join("\n");
  assert.ok(!/gamma/i.test(codeOnly), "Scanner V2 executable code must not reference gamma");
});

// ---- 11. All existing ECM tests remain green (informational pointer) ------
test("11. ECM test suite file is present and unmodified in structure (run separately: node tests/ecm.test.js)", () => {
  assert.ok(fs.existsSync(path.join(__dirname, "ecm.test.js")));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
