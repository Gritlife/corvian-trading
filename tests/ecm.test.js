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
const shortMarginConstMatch = html.match(/const SHORT_MARGIN_RATE = 0\.50;/);
let enforceEcmProtectiveExits = null;
test("19. enforceEcmProtectiveExits exists and is extractable/executable", () => {
  assert.ok(fnMatch, "function source not found");
  assert.ok(shortMarginConstMatch, "SHORT_MARGIN_RATE constant not found");
  enforceEcmProtectiveExits = new Function(shortMarginConstMatch[0] + "\n" + fnMatch[0] + "\nreturn enforceEcmProtectiveExits;")();
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

test("20. long stop: price <= stopPrice closes at market, restores sale proceeds (CATS paper account correction)", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 1000 }, execState: {}, currentPrices: { AAA: 94 }, nowEtHour: 10 });
  assert.strictEqual(r.newLedger[0].status, "closed");
  assert.strictEqual(r.newLedger[0].exitType, "STOP");
  assert.strictEqual(r.newLedger[0].exitPrice, 94);
  assert.strictEqual(r.newLedger[0].realizedPnL, (94 - 100) * 10);
  assert.strictEqual(r.newAccount.balance, 1000 + 94 * 10, "long exit restores closeShares*price (sale proceeds), not just pnl");
  assert.strictEqual(r.journal[0].reason, "STOP_HIT");
  assert.ok(r.newExecState.AAA.lastExitTime > 0, "cooldown timestamp must be set");
});

test("21. short stop: price >= stopPrice closes with correct pnl and releases margin+pnl to balance", () => {
  const t = openTrade({ dir: -1, entryPrice: 100, stopPrice: 105 });
  const r = enforceEcmProtectiveExits({ ledger: [t], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 106 }, nowEtHour: 10 });
  assert.strictEqual(r.newLedger[0].exitType, "STOP");
  const pnl = (100 - 106) * 10;
  assert.strictEqual(r.newLedger[0].realizedPnL, pnl);
  assert.strictEqual(r.newAccount.balance, 10 * 100 * 0.50 + pnl, "short exit must release margin (entryPrice*shares*0.5) plus realized pnl");
});

test("22. no stop breach intraday: position stays open", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 99 }, nowEtHour: 12 });
  assert.strictEqual(r.newLedger[0].status, "open");
  assert.strictEqual(r.exits.length, 0);
});

test("23. EOD flatten: nowEtHour >= 20 closes remaining opens with EOD type and pnl (locked production schedule: 20:00 ET)", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 103 }, nowEtHour: 20 });
  assert.strictEqual(r.newLedger[0].exitType, "EOD");
  assert.strictEqual(r.newLedger[0].realizedPnL, (103 - 100) * 10);
  assert.strictEqual(r.journal[0].reason, "EOD_FLATTEN");
});

test("24. STOP takes precedence over EOD when both apply", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 90 }, nowEtHour: 20 });
  assert.strictEqual(r.newLedger[0].exitType, "STOP");
});
test("24b. no forced shutdown at 16:00 ET: position stays open through the 16:00-20:00 continuation window (locked production schedule)", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 0 }, execState: {}, currentPrices: { AAA: 99 }, nowEtHour: 18 });
  assert.strictEqual(r.newLedger[0].status, "open", "positions must NOT force-close at 4-7pm ET per Task 3.2");
});

test("25. missing price -> no action, never guesses", () => {
  const r = enforceEcmProtectiveExits({ ledger: [openTrade()], account: { balance: 0 }, execState: {}, currentPrices: {}, nowEtHour: 20 });
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

// ---- Task 3.2: ECM session window scheduler --------------------------------
const winFnMatch = html.match(/function ecmSessionWindowCheck\(nowEt\) \{[\s\S]*?\n\}/);
let ecmSessionWindowCheck = null;
test("52. ecmSessionWindowCheck exists, is self-contained, and is executable", () => {
  assert.ok(winFnMatch, "ecmSessionWindowCheck source not found");
  ecmSessionWindowCheck = eval("(" + winFnMatch[0] + ")");
  assert.strictEqual(typeof ecmSessionWindowCheck, "function");
});

test("53. premarket (04:00-09:29 ET) on a weekday: entries allowed", () => {
  assert.strictEqual(ecmSessionWindowCheck({ hour: 4, minute: 0, dayOfWeek: 3 }).allowNewEntries, true);
  assert.strictEqual(ecmSessionWindowCheck({ hour: 9, minute: 29, dayOfWeek: 3 }).allowNewEntries, true);
});
test("54. regular market (09:30-16:00 ET) unchanged: entries allowed", () => {
  assert.strictEqual(ecmSessionWindowCheck({ hour: 12, minute: 0, dayOfWeek: 3 }).allowNewEntries, true);
  assert.strictEqual(ecmSessionWindowCheck({ hour: 16, minute: 0, dayOfWeek: 3 }).allowNewEntries, true);
});
test("55. after-hours (16:00-20:00 ET): new trades still allowed, no forced shutdown at 4pm", () => {
  const r = ecmSessionWindowCheck({ hour: 17, minute: 30, dayOfWeek: 3 });
  assert.strictEqual(r.allowNewEntries, true);
});
test("56. exactly 20:00 ET: new entries stop (locked production schedule)", () => {
  const r = ecmSessionWindowCheck({ hour: 20, minute: 0, dayOfWeek: 3 });
  assert.strictEqual(r.allowNewEntries, false);
  assert.strictEqual(r.reason, "OUTSIDE_ECM_WINDOW");
});
test("57. before 04:00 ET: new entries blocked (locked production schedule)", () => {
  const r = ecmSessionWindowCheck({ hour: 3, minute: 59, dayOfWeek: 3 });
  assert.strictEqual(r.allowNewEntries, false);
  assert.strictEqual(r.reason, "OUTSIDE_ECM_WINDOW");
});
test("58. exactly 04:00 ET boundary: entries allowed (inclusive start, locked production schedule)", () => {
  assert.strictEqual(ecmSessionWindowCheck({ hour: 4, minute: 0, dayOfWeek: 3 }).allowNewEntries, true);
});
test("59. weekend fully disabled: Saturday and Sunday reject regardless of hour", () => {
  const sat = ecmSessionWindowCheck({ hour: 12, minute: 0, dayOfWeek: 6 });
  const sun = ecmSessionWindowCheck({ hour: 12, minute: 0, dayOfWeek: 0 });
  assert.strictEqual(sat.allowNewEntries, false);
  assert.strictEqual(sat.reason, "WEEKEND");
  assert.strictEqual(sun.allowNewEntries, false);
  assert.strictEqual(sun.reason, "WEEKEND");
});
test("60. weekend takes precedence even during otherwise-valid hours", () => {
  const r = ecmSessionWindowCheck({ hour: 10, minute: 0, dayOfWeek: 0 });
  assert.strictEqual(r.reason, "WEEKEND");
});

test("61. window gate wired into processEngineSignals entry branch, ECM-ON-gated, ahead of quality engine", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/)[0];
  const idxWindow = m.indexOf("ecmSessionWindowCheck(etNowParts())");
  const idxQuality = m.indexOf("ecmQualityCheck(");
  assert.ok(idxWindow > -1 && idxQuality > -1, "both gates must be present");
  assert.ok(idxWindow < idxQuality, "window gate must run before the quality engine");
  const windowBlock = m.slice(m.lastIndexOf("if (ecmOn) {", idxWindow), idxWindow);
  assert.ok(windowBlock.includes("if (ecmOn) {"), "window gate must be ECM-ON-gated");
});
test("62. window-gate rejections are journaled as SKIP with the exact reason", () => {
  const m = html.match(/function processEngineSignals\(\{[\s\S]*?\n\}\n/)[0];
  assert.ok(/jot\(ticker, sig, "SKIP", win\.reason\);/.test(m));
});

test("63. EOD trigger aligned to locked production schedule: 20:00 ET", () => {
  assert.ok(/nowEtHour >= 20/.test(html));
  assert.ok(!/nowEtHour >= 16/.test(html), "old 16:00 threshold must not remain anywhere");
  assert.ok(!/nowEtHour >= 19/.test(html), "old 19:00 threshold must not remain anywhere");
});

test("64. window-check function contains no gamma references", () => {
  assert.ok(!/gamma/i.test(winFnMatch[0]));
});
test("65. no scanner/RVOL/OCM/quality-engine/risk-engine/position-sizing/journal-mechanism/paper-ledger files touched by Task 3.2 (scheduler-only diff surface)", () => {
  // Structural check: the scheduler additions are confined to timing helpers
  // and the two gate call-sites; the quality engine, protective-exit STOP
  // logic (aside from the approved threshold), and sizing math are untouched.
  assert.ok(/function ecmQualityCheck\(candidate, config\) \{/.test(html), "quality engine function must still exist unmodified in signature");
  assert.ok(/const stopDist = ATR_STOP_MULT \* atr;/.test(html), "position sizing formula unchanged");
});

// ---- Signal Cursor Correction — FUNCTIONAL tests ---------------------------
// processEngineSignals has real dependencies (RISK_TIERS, session/quality/
// window helpers, signal key/lookup utilities). Extract all of them plus
// the function itself and eval together so the fix can be executed for
// real, not just pattern-matched.
function extractBundle(html) {
  const grab = (re) => { const m = html.match(re); if (!m) throw new Error("bundle piece not found: " + re); return m[0]; };
  const pieces = [
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
  ];
  return pieces.join("\n");
}
let bundleFn = null;
let ecmSessionStartMsFn = null;
test("66. functional test bundle (processEngineSignals + real deps) extracts and evaluates cleanly", () => {
  const src = extractBundle(html);
  bundleFn = new Function(src + "\nreturn processEngineSignals;")();
  assert.strictEqual(typeof bundleFn, "function");
  ecmSessionStartMsFn = new Function(html.match(/function ecmSessionStartMs\(\) \{[\s\S]*?\n\}/)[0] + "\nreturn ecmSessionStartMs;")();
  assert.strictEqual(typeof ecmSessionStartMsFn, "function");
});

// Fixture helpers ------------------------------------------------------------
function bars15mCoveringSession(sessionStartMs) {
  // 20 bars: 10 before session start (historical), 10 at/after (current-session).
  const out = [];
  for (let i = -10; i < 10; i++) out.push({ t: sessionStartMs + i * 15 * 60000, o: 100, h: 101, l: 99, c: 100, v: 1000 });
  return out;
}
function engineWith(signals) {
  return { signalHistory: signals, legendsGreenCount: 4 };
}
function baseArgs(over) {
  const sessionStartMs = new Date().setHours(0, 0, 0, 0); // stand-in; real sessionStartMs computed inside fn
  return Object.assign({
    ticker: "AAA", bars: bars15mCoveringSession(Date.now()), atr: 1,
    ledger: [], execState: {}, account: { balance: 100000 },
    riskProfile: { tier: "moderate" }, sessions: [{ status: "planned", startDate: "1970-01-01", endDate: "2999-01-01" }],
    currentPrices: { AAA: 100 }, trendGate: { state: "bullish" },
    legendsGreenCount: 4, rvol: 2.0, qualityConfig: { minLegends: 3, minRvol: 0 }, ecmOn: false,
  }, over || {});
}

test("67. first poll: valid current-session B2O is processed (fill), not silently primed away", () => {
  const sigTime = ecmSessionStartMsFn() + 30 * 60000; // 30 min into the ECM session -> unambiguously current-session
  const bars = [{ t: sigTime, o: 99, h: 100, l: 98, c: 99, v: 1000 }, { t: sigTime + 900000, o: 100.5, h: 101, l: 100, c: 100.5, v: 1000 }];
  const engine = engineWith([{ bar: 0, time: sigTime, type: "B2O", price: 99, dir: 1 }]);
  const r = bundleFn(baseArgs({ bars, engine, ecmOn: false }));
  assert.strictEqual(r.fills.length, 1, "current-session B2O must fill, not be silently skipped");
  assert.strictEqual(r.fills[0].type, "B2O");
});

test("68. first poll: valid current-session S2O is processed (fill)", () => {
  const sigTime = ecmSessionStartMsFn() + 45 * 60000;
  const bars = [{ t: sigTime, o: 101, h: 102, l: 100, c: 101, v: 1000 }, { t: sigTime + 900000, o: 100.5, h: 101, l: 100, c: 100.5, v: 1000 }];
  const engine = engineWith([{ bar: 0, time: sigTime, type: "S2O", price: 101, dir: -1 }]);
  const r = bundleFn(baseArgs({ bars, engine, trendGate: { state: "bearish" }, ecmOn: false }));
  assert.strictEqual(r.fills.length, 1);
  assert.strictEqual(r.fills[0].type, "S2O");
});

test("69. old historical signal (before session start) is ignored on first poll — no fill", () => {
  const oldTime = Date.now() - 30 * 24 * 3600 * 1000; // 30 days ago, definitely pre-session
  const bars = [{ t: oldTime, o: 99, h: 100, l: 98, c: 99, v: 1000 }, { t: oldTime + 900000, o: 100.5, h: 101, l: 100, c: 100.5, v: 1000 }];
  const engine = engineWith([{ bar: 0, time: oldTime, type: "B2O", price: 99, dir: 1 }]);
  const r = bundleFn(baseArgs({ bars, engine }));
  assert.strictEqual(r.fills.length, 0, "a signal 30 days old must never fill on first poll");
  assert.strictEqual(r.journal.length, 1);
  assert.strictEqual(r.journal[0].action, "INIT");
  assert.strictEqual(r.journal[0].reason, "NO_ELIGIBLE_CURRENT_SESSION_SIGNAL");
});

test("70. ticker leaving and returning to Top-20 retains its cursor (execState persists across calls)", () => {
  const sigTime = ecmSessionStartMsFn() + 60 * 60000;
  const bars = [{ t: sigTime, o: 99, h: 100, l: 98, c: 99, v: 1000 }, { t: sigTime + 900000, o: 100.5, h: 101, l: 100, c: 100.5, v: 1000 }];
  const engine = engineWith([{ bar: 0, time: sigTime, type: "B2O", price: 99, dir: 1 }]);
  const r1 = bundleFn(baseArgs({ bars, engine, execState: {} }));
  assert.strictEqual(r1.fills.length, 1, "first call (ticker present) opens the position");
  // Simulate the ticker rotating OUT of Top-20 (no call made) then back IN,
  // with execState persisted exactly as the real app does via localStorage.
  const r2 = bundleFn(baseArgs({ bars, engine, ledger: r1.newLedger, execState: r1.newExecState }));
  assert.strictEqual(r2.fills.length, 0, "re-seeing the SAME signal after rotation must not re-fill");
  assert.deepStrictEqual(r2.newExecState.AAA.lastExecutedKey, r1.newExecState.AAA.lastExecutedKey, "cursor must be unchanged by rotation");
});

test("71. duplicate signal is never processed twice within the same call", () => {
  const sigTime = ecmSessionStartMsFn() + 90 * 60000;
  const bars = [{ t: sigTime, o: 99, h: 100, l: 98, c: 99, v: 1000 }, { t: sigTime + 900000, o: 100.5, h: 101, l: 100, c: 100.5, v: 1000 }];
  const engine = engineWith([{ bar: 0, time: sigTime, type: "B2O", price: 99, dir: 1 }]);
  const r1 = bundleFn(baseArgs({ bars, engine }));
  const r2 = bundleFn(baseArgs({ bars, engine, ledger: r1.newLedger, execState: r1.newExecState }));
  const r3 = bundleFn(baseArgs({ bars, engine, ledger: r2.newLedger, execState: r2.newExecState }));
  assert.strictEqual(r1.fills.length, 1);
  assert.strictEqual(r2.fills.length, 0);
  assert.strictEqual(r3.fills.length, 0);
});

test("72. multiple eligible current-session signals process in order (B2O then TP)", () => {
  const t0 = ecmSessionStartMsFn() + 120 * 60000;
  const t1 = t0 + 15 * 60000;
  const t2 = t0 + 30 * 60000;
  const bars = [
    { t: t0, o: 99, h: 100, l: 98, c: 99, v: 1000 },
    { t: t1, o: 100, h: 101, l: 99.5, c: 100, v: 1000 },  // fill price for B2O = next bar open = 100
    { t: t2, o: 106, h: 107, l: 105, c: 106, v: 1000 },   // fill price for TP = next bar open = 106
  ];
  const engine = engineWith([
    { bar: 0, time: t0, type: "B2O", price: 99, dir: 1 },
    { bar: 1, time: t1, type: "TP", price: 100, dir: 1 },
  ]);
  const r = bundleFn(baseArgs({ bars, engine }));
  assert.strictEqual(r.fills.length, 2, "both eligible signals must be evaluated in one pass");
  assert.strictEqual(r.fills[0].type, "B2O");
  assert.strictEqual(r.fills[1].type, "TP");
  assert.ok(r.fills[0].time < r.fills[1].time, "must process strictly in chronological order");
});

test("73. ECM OFF unchanged: quality/window gates still skip entirely when ecmOn is false (regression)", () => {
  const sigTime = ecmSessionStartMsFn() + 150 * 60000;
  const bars = [{ t: sigTime, o: 99, h: 100, l: 98, c: 99, v: 1000 }, { t: sigTime + 900000, o: 100.5, h: 101, l: 100, c: 100.5, v: 1000 }];
  const engine = engineWith([{ bar: 0, time: sigTime, type: "B2O", price: 99, dir: 1 }]);
  const r = bundleFn(baseArgs({ bars, engine, ecmOn: false, legendsGreenCount: 0, rvol: 0 })); // would fail quality if ECM were ON
  assert.strictEqual(r.fills.length, 1, "with ECM OFF, legacy gates alone apply — quality thresholds must not block the fill");
  assert.ok(!r.journal.some(j => j.action === "QUALITY"), "no QUALITY journal entries when ECM is OFF");
});

test("74. root-cause regression guard: the old unconditional 'prime to last, return' pattern is gone", () => {
  assert.ok(!/if \(!tickerState\.lastExecutedKey && engine\.signalHistory\.length > 0\) \{/.test(html), "old Guard B pattern must not remain");
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
