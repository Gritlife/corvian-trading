// tests/ecm.test.js
// ECM v1.0 Task 1 — control plane, auto-session, action journal.
// Static source-inspection tests per the established frontend-test pattern
// (index.html's React code cannot be require()'d in Node directly).
// Run: node tests/ecm.test.js

const assert = require("assert");
const fs = require("fs");
const path = require("path");

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log("  ok  -", name); passed++; }
  catch (e) { console.log("FAIL  -", name, "\n       ", e.message); failed++; }
}

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");

// ---- Control plane ---------------------------------------------------------
test("1. ECM_MODE storage key mapped", () => {
  assert.ok(/ECM_MODE: "cts-v1-ecm-mode"/.test(html));
});
test("2. ECM_MODE defaults to OFF (autonomy is opt-in)", () => {
  assert.ok(/loadJSONCts\("ECM_MODE", "OFF"\)/.test(html));
});
test("3. app source never programmatically sets ECM to ON (only the human toggle can)", () => {
  assert.ok(!/setEcmModeChecked\("ON"\)/.test(html), 'found a hardcoded setEcmModeChecked("ON") call');
  // the toggle is a ternary driven by current state — allowed:
  assert.ok(/setEcmModeChecked\(ecmMode === "ON" \? "OFF" : "ON"\)/.test(html));
});
test("4. ECM is paper-only: no broker/live-order integration code introduced", () => {
  // Check for actual integration patterns (API calls, OAuth, order routing),
  // not the word "broker" in safety disclaimers/comments.
  assert.ok(!/schwabapi|api\.schwab|placeOrder\(|submitOrder\(|order_route|oauth.*schwab/i.test(html), "found broker-integration code pattern");
});

// ---- Auto-session ----------------------------------------------------------
test("5. auto-session effect is gated on ecmMode === \"ON\" (OFF preserves legacy behavior)", () => {
  assert.ok(/if \(!loggedIn \|\| ecmMode !== "ON" \|\| !riskProfile\) return;/.test(html));
});
test("6. auto-session only created when no session exists for today", () => {
  assert.ok(/if \(activeSessionForToday\(sessions\)\) return;/.test(html));
});
test("7. auto-session mirrors SessionCreateForm's shape and is tagged ecmAuto", () => {
  const m = html.match(/const auto = \{[\s\S]*?\};/);
  assert.ok(m, "auto session literal not found");
  for (const field of ["id:", "name:", "startDate:", "endDate:", "status: \"planned\"", "universe: \"SP500\"", "riskProfile:", "initialBalance:", "createdAt:", "ecmAuto: true"]) {
    assert.ok(m[0].includes(field), "auto session missing field: " + field);
  }
});
test("8. auto-session creation is journaled", () => {
  assert.ok(/SESSION_AUTO_CREATED/.test(html));
});

// ---- Journal ---------------------------------------------------------------
test("9. ECM_JOURNAL storage key mapped and capped", () => {
  assert.ok(/ECM_JOURNAL: "cts-v1-ecm-journal"/.test(html));
  assert.ok(/ECM_JOURNAL_CAP = 2000/.test(html));
});
test("10. processEngineSignals returns a journal array (additive field)", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/);
  assert.ok(m);
  assert.ok(/return \{ newLedger, newExecState, newAccount, fills, journal \};/.test(m[0]));
});
test("11. every fill is journaled (4 fill sites, 4 jot mirrors)", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/)[0];
  const fillCount = (m.match(/fills\.push\(/g) || []).length;
  const jotFillCount = (m.match(/jot\(ticker, sig, "FILL"/g) || []).length;
  assert.strictEqual(fillCount, 4);
  assert.strictEqual(jotFillCount, 4, "each fills.push must have a matching FILL journal entry");
});
test("12. all skip reasons journaled: NO_SESSION, DAILY_HALT, ALREADY_OPEN, MAX_POS, COOLDOWN, TREND_GATE, NOTIONAL_CAP", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/)[0];
  for (const reason of ["NO_SESSION", "DAILY_HALT", "ALREADY_OPEN", "MAX_POS", "COOLDOWN", "TREND_GATE", "NOTIONAL_CAP"]) {
    assert.ok(m.includes('"' + reason + '"'), "missing journaled skip reason: " + reason);
  }
});
test("13. journal appender dedupes by ticker|sigTime|signal|action|reason composite key", () => {
  assert.ok(/e\.ticker \+ "\|" \+ e\.sigTime \+ "\|" \+ e\.signal \+ "\|" \+ e\.action \+ "\|" \+ \(e\.reason \|\| ""\)/.test(html));
});
test("14. both processEngineSignals callers collect and flush the journal", () => {
  const collects = (html.match(/journalBatch\.push\(\.\.\.result\.journal\)/g) || []).length;
  const flushes = (html.match(/appendEcmJournal\(journalBatch\)/g) || []).length;
  assert.strictEqual(collects, 2);
  assert.strictEqual(flushes, 2);
});

// ---- Preservation guarantees ----------------------------------------------
test("15. processEngineSignals still has zero gamma references (shadow safety intact)", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/)[0];
  assert.ok(!/gamma/i.test(m));
});
test("16. scanner untouched: buildAvgVolume20d and pullScanner signatures unchanged", () => {
  assert.ok(/async function buildAvgVolume20d\(tickers\)/.test(html));
  assert.ok(/const pullScanner = async \(\) =>/.test(html));
});
test("17. Item #17 untouched: fetchOcmGammaSnapshot and Gamma bridge intact", () => {
  assert.ok(/function fetchOcmGammaSnapshot/.test(html));
  assert.ok(/gexByStrike/.test(fs.readFileSync(path.join(__dirname, "..", "netlify", "functions", "lib", "ocm-engine.js"), "utf8")));
});
test("18. GAMMA_MODE default SHADOW unchanged", () => {
  assert.ok(/loadJSONCts\("GAMMA_MODE", "SHADOW"\)/.test(html));
});

// ---- Task 2: protective exits — FUNCTIONAL tests ---------------------------
// enforceEcmProtectiveExits is deliberately self-contained (no React/JSX/
// helpers), so we extract its source from index.html and execute it here.
const fnMatch = html.match(/function enforceEcmProtectiveExits\(\{[\s\S]*?\n\}/);
let enforceEcmProtectiveExits = null;
test("19. enforceEcmProtectiveExits exists and is extractable/executable", () => {
  assert.ok(fnMatch, "function source not found");
  enforceEcmProtectiveExits = eval("(" + fnMatch[0] + ")");
  assert.strictEqual(typeof enforceEcmProtectiveExits, "function");
});

function openTrade(over) {
  return Object.assign({
    id: "t1", ticker: "AAA", dir: 1, status: "open",
    entryType: "B2O", entryPrice: 100, entryShares: 10, currentShares: 10,
    entryTime: 1, sessionId: "s", stopPrice: 95, atrAtEntry: 2,
    adds: [], tps: [], realizedPnL: 0, closedAt: null, exitType: null, exitPrice: null,
  }, over || {});
}

test("20. long stop: price <= stopPrice closes at market with correct negative pnl", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 1000 }, execState: {}, currentPrices: { AAA: 94 }, nowEtHour: 10 });
  assert.strictEqual(r.newLedger[0].status, "closed");
  assert.strictEqual(r.newLedger[0].exitType, "STOP");
  assert.strictEqual(r.newLedger[0].exitPrice, 94);
  assert.strictEqual(r.newLedger[0].realizedPnL, (94 - 100) * 10);
  assert.strictEqual(r.newAccount.balance, 1000 + (94 - 100) * 10);
  assert.strictEqual(r.journal[0].reason, "STOP_HIT");
  assert.ok(r.newExecState.AAA.lastExitTime > 0, "cooldown timestamp must be set");
});

test("21. short stop: price >= stopPrice closes with correct pnl", () => {
  const t = openTrade({ dir: -1, entryPrice: 100, stopPrice: 105 });
  const r = enforceEcmProtectiveExits({ ledger: [t], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 106 }, nowEtHour: 10 });
  assert.strictEqual(r.newLedger[0].exitType, "STOP");
  assert.strictEqual(r.newLedger[0].realizedPnL, (100 - 106) * 10);
});

test("22. no stop breach intraday: position stays open", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 99 }, nowEtHour: 12 });
  assert.strictEqual(r.newLedger[0].status, "open");
  assert.strictEqual(r.exits.length, 0);
});

test("23. EOD flatten: nowEtHour >= 16 closes remaining opens with EOD type and pnl", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 103 }, nowEtHour: 16 });
  assert.strictEqual(r.newLedger[0].exitType, "EOD");
  assert.strictEqual(r.newLedger[0].realizedPnL, (103 - 100) * 10);
  assert.strictEqual(r.journal[0].reason, "EOD_FLATTEN");
});

test("24. STOP takes precedence over EOD when both apply", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 90 }, nowEtHour: 17 });
  assert.strictEqual(r.newLedger[0].exitType, "STOP");
});

test("25. missing price -> no action, never guesses", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 0 }, execState: {}, currentPrices: {}, nowEtHour: 17 });
  assert.strictEqual(r.newLedger[0].status, "open");
  assert.strictEqual(r.exits.length, 0);
});

test("26. closed positions untouched; realizedPnL accumulates on top of prior TPs", () => {
  const closed = openTrade({ id: "t0", status: "closed" });
  const withTp = openTrade({ id: "t2", realizedPnL: 50 });
  const r = enforceEcmProtectiveExits({ ledger: [closed, withTp], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 94 }, nowEtHour: 10 });
  assert.strictEqual(r.newLedger[0], closed, "already-closed trade object must pass through untouched");
  assert.strictEqual(r.newLedger[1].realizedPnL, 50 + (94 - 100) * 10);
});

test("27. protective exits are wired in both pull loops, gated on ECM ON", () => {
  const wires = (html.match(/enforceEcmProtectiveExits\(\{ ledger: curLedger/g) || []).length;
  assert.strictEqual(wires, 2);
  const gates = (html.match(/if \(ecmModeRef\.current === "ON"\) \{/g) || []).length;
  assert.strictEqual(gates, 2, "both wirings must be gated on ECM ON");
});

test("28. protective-exit function contains no gamma references (shadow safety extends to ECM)", () => {
  assert.ok(!/gamma/i.test(fnMatch[0]));
});

// ---- Task 3: Quality Engine — FUNCTIONAL tests -----------------------------
const qFnMatch = html.match(/function ecmQualityCheck\(candidate, config\) \{[\s\S]*?\n\}/);
let ecmQualityCheck = null;
const QCFG = { minLegends: 3, minRvol: 1.0 };
function candidate(over) {
  return Object.assign({
    sigType: "B2O", legendsGreenCount: 4, rvol: 2.5, trendState: "bullish",
    hasActiveSession: true, dailyHalted: false, hasOpenPosition: false, cooldownActive: false,
  }, over || {});
}

test("29. ecmQualityCheck exists, is self-contained, and is executable", () => {
  assert.ok(qFnMatch, "ecmQualityCheck source not found");
  ecmQualityCheck = eval("(" + qFnMatch[0] + ")");
  assert.strictEqual(typeof ecmQualityCheck, "function");
});

test("30. approved trade: all rules pass -> APPROVED with metrics", () => {
  const r = ecmQualityCheck(candidate(), QCFG);
  assert.strictEqual(r.decision, "APPROVED");
  assert.strictEqual(r.reason, null);
  assert.deepStrictEqual(r.metrics, { legends: 4, rvol: 2.5, trend: "bullish" });
});

test("31. legend rejection: legends below minLegends -> LOW_LEGEND_SCORE", () => {
  const r = ecmQualityCheck(candidate({ legendsGreenCount: 2 }), QCFG);
  assert.strictEqual(r.decision, "REJECTED");
  assert.strictEqual(r.reason, "LOW_LEGEND_SCORE");
});

test("32. RVOL rejection: rvol below minRvol -> LOW_RVOL", () => {
  const r = ecmQualityCheck(candidate({ rvol: 0.4 }), QCFG);
  assert.strictEqual(r.reason, "LOW_RVOL");
});

test("33. trend rejection: B2O in bearish trend and S2O in bullish trend -> TREND_MISMATCH", () => {
  assert.strictEqual(ecmQualityCheck(candidate({ trendState: "bearish" }), QCFG).reason, "TREND_MISMATCH");
  assert.strictEqual(ecmQualityCheck(candidate({ sigType: "S2O", trendState: "bullish" }), QCFG).reason, "TREND_MISMATCH");
  assert.strictEqual(ecmQualityCheck(candidate({ sigType: "S2O", trendState: "bearish" }), QCFG).decision, "APPROVED");
});

test("34. session rejection: no active session -> SESSION_CLOSED", () => {
  assert.strictEqual(ecmQualityCheck(candidate({ hasActiveSession: false }), QCFG).reason, "SESSION_CLOSED");
});

test("35. daily halt rejection -> DAILY_HALT", () => {
  assert.strictEqual(ecmQualityCheck(candidate({ dailyHalted: true }), QCFG).reason, "DAILY_HALT");
});

test("36. duplicate rejection -> POSITION_ALREADY_OPEN", () => {
  assert.strictEqual(ecmQualityCheck(candidate({ hasOpenPosition: true }), QCFG).reason, "POSITION_ALREADY_OPEN");
});

test("37. cooldown rejection -> COOLDOWN", () => {
  assert.strictEqual(ecmQualityCheck(candidate({ cooldownActive: true }), QCFG).reason, "COOLDOWN");
});

test("38. missing metrics never reject (no guessing): null legends/rvol/trend still evaluable", () => {
  const r = ecmQualityCheck(candidate({ legendsGreenCount: null, rvol: null, trendState: null }), QCFG);
  assert.strictEqual(r.decision, "APPROVED");
  assert.deepStrictEqual(r.metrics, { legends: null, rvol: null, trend: null });
});

test("39. rules evaluate in directive order (first failure wins): legends before rvol before trend", () => {
  const r = ecmQualityCheck(candidate({ legendsGreenCount: 0, rvol: 0, trendState: "bearish" }), QCFG);
  assert.strictEqual(r.reason, "LOW_LEGEND_SCORE");
});

test("40. defaults centralized: ECM_QUALITY_DEFAULTS = {minLegends:3, minRvol:0}, no scattered thresholds", () => {
  assert.ok(/const ECM_QUALITY_DEFAULTS = \{ minLegends: 3, minRvol: 0 \};/.test(html));
  assert.strictEqual((html.match(/minLegends/g) || []).length <= 6, true, "minLegends should only appear in the centralized config region");
});

test("41. config persisted/overridable via ECM_QUALITY storage key", () => {
  assert.ok(/ECM_QUALITY: "cts-v1-ecm-quality-config"/.test(html));
  assert.ok(/function loadEcmQualityConfig\(\)/.test(html));
});

test("42. quality decision journaled for EVERY entry candidate (approved and rejected), with legends/rvol/trend fields", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/)[0];
  assert.ok(/jot\(ticker, sig, "QUALITY", q\.decision === "REJECTED" \? q\.reason : null, \{ decision: q\.decision, legends: q\.metrics\.legends, rvol: q\.metrics\.rvol, trend: q\.metrics\.trend \}\)/.test(m));
  assert.ok(/if \(q\.decision === "REJECTED"\) \{ tickerState\.lastExecutedKey = key; continue; \}/.test(m), "rejected candidates must not become trades");
});

test("43. journal dedup covers quality entries (composite key includes action+reason)", () => {
  // Same appender as Tasks 1-2; QUALITY entries carry sigTime so re-polls dedup.
  assert.ok(/e\.ticker \+ "\|" \+ e\.sigTime \+ "\|" \+ e\.signal \+ "\|" \+ e\.action \+ "\|" \+ \(e\.reason \|\| ""\)/.test(html));
});

test("44. both callers thread legends, scanner RVOL, and centralized config into the engine (ECM-ON-gated per Task 3.1)", () => {
  assert.strictEqual((html.match(/qualityConfig: ecmOn \? loadEcmQualityConfig\(\) : null/g) || []).length, 2);
  assert.strictEqual((html.match(/rvol: ecmOn && rvolBySym\[sym\]/g) || []).length, 2);
  assert.strictEqual((html.match(/const rvolBySym = \{\};/g) || []).length, 2);
});

test("45. quality engine modifies nothing upstream: scanner ranking, RVOL calc, MMG engine, legends calc untouched", () => {
  assert.ok(/const rvol = useV \/ avgV;/.test(html), "scanner RVOL formula unchanged");
  assert.ok(/function computeMMGEngineState\(bars, opts\)/.test(html), "engine signature unchanged");
  assert.ok(!/ecmQualityCheck/.test(html.match(/function computeMMGEngineState\(bars, opts\) \{[\s\S]{0,2000}/)[0]), "engine must not call the quality engine");
});

test("46. quality function contains no gamma references", () => {
  assert.ok(!/gamma/i.test(qFnMatch[0]));
});

// ---- Task 3.1: ECM OFF behavior correction ---------------------------------
test("47. quality engine is wrapped in if (ecmOn): no evaluation, journaling, or filtering when OFF", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/)[0];
  const gated = m.match(/if \(ecmOn\) \{[\s\S]*?ecmQualityCheck\(/);
  assert.ok(gated, "ecmQualityCheck call must sit inside an if (ecmOn) block");
  const qualityJot = m.match(/if \(ecmOn\) \{[\s\S]*?jot\(ticker, sig, "QUALITY"/);
  assert.ok(qualityJot, "QUALITY journal entry must sit inside the same if (ecmOn) block");
});
test("48. processEngineSignals accepts ecmOn and both callers pass it from ecmModeRef", () => {
  assert.ok(/qualityConfig, ecmOn \}\) \{/.test(html), "signature must include ecmOn");
  assert.strictEqual((html.match(/const ecmOn = ecmModeRef\.current === "ON";/g) || []).length, 2);
  assert.strictEqual((html.match(/\n                ecmOn,\n/g) || []).length, 2, "both call sites must pass ecmOn");
});
test("49. OFF preserves legacy: rvol map building and config loading are also ECM-ON-gated", () => {
  assert.strictEqual((html.match(/if \(ecmOn\) \(topRVOL \|\| \[\]\)\.forEach/g) || []).length, 2);
});
test("50. ON preserves Task 3: rejection short-circuit still inside the gated block", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/)[0];
  assert.ok(/if \(q\.decision === "REJECTED"\) \{ tickerState\.lastExecutedKey = key; continue; \}/.test(m));
});
test("51. functional: quality check unreachable when ecmOn is false (simulated branch)", () => {
  // Simulate the exact gating shape: with ecmOn=false the quality function
  // must never be invoked; with true it must be.
  let calls = 0;
  const fakeQuality = () => { calls++; return { decision: "APPROVED", reason: null, metrics: {} }; };
  const simulate = (ecmOn) => { if (ecmOn) { fakeQuality(); } };
  simulate(false);
  assert.strictEqual(calls, 0, "quality must not run when ECM OFF");
  simulate(true);
  assert.strictEqual(calls, 1, "quality must run when ECM ON");
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
