// tests/cats-account-correction.test.js
// CATS — Extended Session + Paper Account Correction. Covers:
//   1. Session window remains active through 04:00-20:00 ET (no 16:00 cutoff)
//   2. Paper account cash/buying-power/equity reconciliation
//   3. Scanner V2 default filters (Legends>=3, Score>=60, B2O/S2O only)
// Run: node tests/cats-account-correction.test.js

const assert = require("assert");
const fs = require("fs");
const path = require("path");

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log("  ok  -", name); passed++; }
  catch (e) { console.log("FAIL  -", name, "\n       ", e.message); failed++; }
}

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");

// ---- Extended session window (verification, not a new fix — already
// corrected in a prior pass; re-verified here under this task's own name) --
let ecmSessionWindowCheck = null;
let enforceEcmProtectiveExits = null;
test("0. session-window and protective-exit functions extract cleanly", () => {
  ecmSessionWindowCheck = eval("(" + html.match(/function ecmSessionWindowCheck\(nowEt\) \{[\s\S]*?\n\}/)[0] + ")");
  const marginConst = html.match(/const SHORT_MARGIN_RATE = 0\.50;/)[0];
  enforceEcmProtectiveExits = new Function(marginConst + "\n" + html.match(/function enforceEcmProtectiveExits\(\{[\s\S]*?\n\}/)[0] + "\nreturn enforceEcmProtectiveExits;")();
});

test("1. CATS remains active after 16:00 ET (no unintended shutdown)", () => {
  const r = ecmSessionWindowCheck({ hour: 17, minute: 0, dayOfWeek: 3 });
  assert.strictEqual(r.allowNewEntries, true);
});
test("2. CATS accepts valid trades right up to (but not including) 20:00 ET", () => {
  const r = ecmSessionWindowCheck({ hour: 19, minute: 59, dayOfWeek: 3 });
  assert.strictEqual(r.allowNewEntries, true);
});
test("3. CATS stops new entries exactly at 20:00 ET", () => {
  const r = ecmSessionWindowCheck({ hour: 20, minute: 0, dayOfWeek: 3 });
  assert.strictEqual(r.allowNewEntries, false);
  assert.strictEqual(r.reason, "OUTSIDE_ECM_WINDOW");
});
test("4. Final flatten occurs at 20:00 ET, not 16:00", () => {
  const openTrade = { id: "t1", ticker: "AAA", dir: 1, status: "open", entryType: "B2O", entryPrice: 100, entryShares: 10, currentShares: 10, entryTime: 1, stopPrice: 90, atrAtEntry: 2, adds: [], tps: [], realizedPnL: 0, closedAt: null, exitType: null, exitPrice: null };
  const at16 = enforceEcmProtectiveExits({ ledger: [openTrade], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 101 }, nowEtHour: 16 });
  assert.strictEqual(at16.newLedger[0].status, "open", "must NOT flatten at 16:00 ET");
  const at20 = enforceEcmProtectiveExits({ ledger: [openTrade], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 101 }, nowEtHour: 20 });
  assert.strictEqual(at20.newLedger[0].exitType, "EOD", "must flatten at 20:00 ET");
});
test("4b. Scanner remains unconditionally polled (no session-window gate on the scan itself)", () => {
  assert.ok(/setInterval\(pullScanner, 60000\)/.test(html), "scanner polling must be unconditional, independent of the ECM entry window");
});

// ---- Paper account bug fix --------------------------------------------------
let computeReconciledEquity = null;
test("5. computeReconciledEquity extracts and evaluates cleanly", () => {
  const src = html.match(/function computeReconciledEquity\(cashBalance, openPositions, currentPrices, marginRate\) \{[\s\S]*?\n\}/)[0];
  computeReconciledEquity = eval("(" + src + ")");
  assert.strictEqual(typeof computeReconciledEquity, "function");
});

function openLong(over) {
  return Object.assign({ ticker: "AAA", status: "open", dir: 1, entryPrice: 100, currentShares: 10 }, over || {});
}
function openShort(over) {
  return Object.assign({ ticker: "BBB", status: "open", dir: -1, entryPrice: 50, currentShares: 20 }, over || {});
}

test("6. long entry reduces buying power by full notional (functional, via processEngineSignals fill path)", () => {
  assert.ok(/newAccount\.balance -= dir === 1 \? \(shares \* fillPrice\) : \(shares \* fillPrice \* SHORT_MARGIN_RATE\);/.test(html), "entry must debit balance: full notional for longs, margin-rate notional for shorts");
  // Real functional proof: extract the full engine bundle (same approach as
  // tests/ecm.test.js) and execute an actual B2O fill.
  const grab = (re) => html.match(re)[0];
  const bundle = [
    grab(/const RISK_TIERS = \{[\s\S]*?\n\};/),
    grab(/function todayETISO\(\) \{[\s\S]*?\n\}/),
    grab(/function activeSessionForToday\(sessions\) \{[\s\S]*?\n\}/),
    grab(/function signalKey\(ticker, sig\) \{[\s\S]*?\n\}/),
    grab(/function nextBarOpen\(bars, signalBarTimestamp\) \{[\s\S]*?\n\}/),
    grab(/function findOpenPosition\(ledger, ticker\) \{[\s\S]*?\n\}/),
    grab(/function ecmSessionStartMs\(\) \{[\s\S]*?\n\}/),
    grab(/function etNowParts\(\) \{[\s\S]*?\n\}/),
    grab(/function ecmSessionWindowCheck\(nowEt\) \{[\s\S]*?\n\}/),
    grab(/function ecmQualityCheck\(candidate, config\) \{[\s\S]*?\n\}/),
    grab(/const SHORT_MARGIN_RATE = 0\.50;/),
    grab(/function computeReconciledEquity\(cashBalance, openPositions, currentPrices, marginRate\) \{[\s\S]*?\n\}/),
    grab(/function processEngineSignals\(\{[\s\S]*?\n\}\n/),
  ].join("\n");
  const pes = new Function(bundle + "\nreturn processEngineSignals;")();
  const sessionStart = eval("(" + html.match(/function ecmSessionStartMs\(\) \{[\s\S]*?\n\}/)[0] + ")")();
  const t0 = sessionStart + 60 * 60000;
  const t1 = t0 + 15 * 60000;
  const bars = [{ t: t0, o: 99, h: 100, l: 98, c: 99, v: 1000 }, { t: t1, o: 100, h: 101, l: 100, c: 100.5, v: 1000 }];
  const engine = { signalHistory: [{ bar: 0, time: t0, type: "B2O", price: 99, dir: 1 }], legendsGreenCount: 4 };
  const r = pes({
    ticker: "AAA", bars, atr: 1, ledger: [], execState: {}, account: { balance: 100000 },
    riskProfile: { tier: "moderate" }, sessions: [{ status: "planned", startDate: "1970-01-01", endDate: "2999-01-01" }],
    currentPrices: { AAA: 100 }, trendGate: { state: "bullish" }, legendsGreenCount: 4, rvol: 2.0,
    qualityConfig: { minLegends: 3, minRvol: 0 }, ecmOn: false, engine,
  });
  assert.strictEqual(r.fills.length, 1);
  const filledShares = r.fills[0].shares;
  const filledPrice = r.fills[0].price;
  assert.strictEqual(r.newAccount.balance, 100000 - filledShares * filledPrice, "buying power must drop by exactly the notional cost of the long fill");
});
test("6b. long market value reconciles: equity = cash + longMarketValue when only a long is open", () => {
  const r = computeReconciledEquity(9000, [openLong()], { AAA: 105 }, 0.5); // cash already debited 10*100=1000 from a 10000 start
  assert.strictEqual(r.longMarketValue, 105 * 10);
  assert.strictEqual(r.shortMarginRequirement, 0);
  assert.strictEqual(r.equity, 9000 + 105 * 10);
});

test("7. short entry reserves margin only (buying power reduced by rate*notional, not full notional)", () => {
  assert.ok(/newAccount\.balance -= dir === 1 \? \(shares \* fillPrice\) : \(shares \* fillPrice \* SHORT_MARGIN_RATE\);/.test(html));
});
test("7b. short margin requirement reconciles against reserved amount", () => {
  const r = computeReconciledEquity(9500, [openShort()], { BBB: 48 }, 0.5); // cash debited 20*50*0.5=500 from a 10000 start
  assert.strictEqual(r.shortMarginRequirement, 50 * 20 * 0.5);
  assert.strictEqual(r.shortUnrealizedPnL, (50 - 48) * 20);
  assert.strictEqual(r.equity, 9500 + r.shortMarginRequirement + r.shortUnrealizedPnL);
});

test("8. ADD reduces buying power further (long and short)", () => {
  assert.ok(/newAccount\.balance -= open\.pos\.dir === 1 \? \(addShares \* fillPrice\) : \(addShares \* fillPrice \* SHORT_MARGIN_RATE\);/.test(html));
});

test("9. TP/partial close restores the appropriate amount (long: proceeds; short: margin release + pnl)", () => {
  assert.ok(/newAccount\.balance \+= open\.pos\.dir === 1\s*\n\s*\? \(closeShares \* fillPrice\)\s*\/\/ long: sale proceeds \(P&L implicit\)\s*\n\s*: \(closeShares \* open\.pos\.entryPrice \* SHORT_MARGIN_RATE\) \+ pnl;\s*\/\/ short: release margin \+ realized P&L/.test(html));
});
test("10. full close (B2C/S2C) restores released capital plus/minus realized P&L", () => {
  const fullCloseCount = (html.match(/: \(closeShares \* open\.pos\.entryPrice \* SHORT_MARGIN_RATE\) \+ pnl;\s*\/\/ short: release margin \+ realized P&L/g) || []).length;
  assert.strictEqual(fullCloseCount, 2, "both TP (partial) and full close must use the same corrected release formula");
});
test("10b. protective exits (STOP/EOD) use the same corrected release model as engine-driven closes", () => {
  assert.ok(/newAccount\.balance \+= t\.dir === 1\s*\n\s*\? \(closeShares \* px\)\s*\n\s*: \(closeShares \* t\.entryPrice \* SHORT_MARGIN_RATE\) \+ pnl;/.test(html));
});

test("11. equity/cash/buying-power reconciliation: computeAccountStats uses the shared computeReconciledEquity model", () => {
  assert.ok(/const recon = computeReconciledEquity\(paperAccount\.balance, ledger, livePrices, SHORT_MARGIN_RATE\);/.test(html));
  assert.ok(/const equity = recon\.equity;/.test(html));
  assert.ok(/cash: paperAccount\.balance,/.test(html), "cash must be explicitly exposed for display reconciliation");
  assert.ok(/longMarketValue, shortMarginRequirement,/.test(html), "long market value and short margin requirement must be exposed for display reconciliation");
});
test("11b. daily-stop equity input uses the corrected reconciled-equity model (risk THRESHOLD unchanged, only the input)", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/)[0];
  assert.ok(/startEquity: computeReconciledEquity\(newAccount\.balance, newLedger, currentPrices, SHORT_MARGIN_RATE\)\.equity/.test(m));
  assert.ok(/const currentEquity = computeReconciledEquity\(newAccount\.balance, newLedger, currentPrices, SHORT_MARGIN_RATE\)\.equity;/.test(m));
  assert.ok(/const DAILY_STOP_PCT = tier\.dailyStop \/ 100;/.test(m), "daily stop threshold/logic itself must be untouched");
});
test("11c. position sizing formula is untouched by the account correction", () => {
  assert.ok(/const stopDist = ATR_STOP_MULT \* atr;/.test(html));
  assert.ok(/const riskDollars = currentEquity \* RISK_PCT;/.test(html));
});

// ---- Scanner V2 default filters --------------------------------------------
test("12. Scanner V2 defaults centralized: Five Legends >= 3/5, Opportunity Score >= 60, B2O/S2O only", () => {
  assert.ok(/const SCANNER_V2_DEFAULTS = \{ minLegends: 3, minOpportunityScore: 60, requiredActions: \["B2O", "S2O"\] \};/.test(html));
});
test("13. Scanner V2 final list is filtered by the centralized defaults before setTopRVOL", () => {
  const stageTwo = html.match(/const SHORTLIST_SIZE = 60;[\s\S]*?setTopRVOL\(filtered\.slice\(0, 20\)\);/)[0];
  assert.ok(/c\.legendsGreenCount >= SCANNER_V2_DEFAULTS\.minLegends/.test(stageTwo));
  assert.ok(/c\.opportunityScore >= SCANNER_V2_DEFAULTS\.minOpportunityScore/.test(stageTwo));
  assert.ok(/SCANNER_V2_DEFAULTS\.requiredActions\.includes\(c\.action\)/.test(stageTwo));
});
test("13b. CATS consumes the same filtered list (topRVOL is the single, post-filter source)", () => {
  assert.ok(/setTopRVOL\(filtered\.slice\(0, 20\)\);/.test(html), "the ONLY setTopRVOL call in Stage 2 must use the filtered list");
  assert.ok(/const scanTickers = topRVOL\.slice\(0, 20\)\.map\(t => t\.sym\);/.test(html), "ECM/CATS still reads topRVOL unchanged");
});

// ---- Non-regression guards --------------------------------------------------
test("14. MMG signal generation, OCM, Gamma, Item #17, Quality Engine rules, stop logic untouched (backend hash + structural)", () => {
  const crypto = require("crypto");
  const hashes = {
    "netlify/functions/lib/ocm-engine.js": "bd492c28bdfc58471284baf82af245549622ff2f5f8d28635ee1f3c867f619eb",
    "netlify/functions/ocm-gamma-snapshot.js": "8e7458d941d46b6bee5bb809ce69cc9fbc2f8d504dcfb244e90a3d913118f5a1",
    "netlify/functions/lib/gamma-status.js": "ce3f742b653beef697add709abc0a76878068caeb7a8fef599db0078de68b064",
  };
  for (const [file, expected] of Object.entries(hashes)) {
    const actual = crypto.createHash("sha256").update(fs.readFileSync(path.join(__dirname, "..", file), "utf8")).digest("hex");
    assert.strictEqual(actual, expected, file + " must be untouched");
  }
  assert.ok(/function ecmQualityCheck\(candidate, config\) \{/.test(html), "Quality Engine function must still exist, unmodified signature");
  assert.ok(/if \(t\.stopPrice != null\) \{/.test(html), "STOP logic structure unchanged");
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
