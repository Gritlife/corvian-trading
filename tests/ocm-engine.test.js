// tests/ocm-engine.test.js
// Phase 14 tests — OCM engine, using synthetic (not live) contract data since
// no live Massive Options connectivity is available in this environment.
// Run: node tests/ocm-engine.test.js

const assert = require("assert");
const {
  aggregateByStrike, computeGammaFlip, computePositiveWall, computeNegativePit,
  computeGammaGauge, computeRegime, computeConfidence, computeOcmGammaSnapshot,
} = require("../netlify/functions/lib/ocm-engine");

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log("  ok  -", name); passed++; }
  catch (e) { console.log("FAIL  -", name, "\n       ", e.message); failed++; }
}

function contract({ strike, type, oi, gamma, iv, expiration, multiplier }) {
  return {
    details: { strike_price: strike, contract_type: type, expiration_date: expiration || "2099-01-01", shares_per_contract: multiplier || 100 },
    open_interest: oi === undefined ? 100 : oi,
    greeks: gamma === undefined ? { gamma: 0.02 } : (gamma === null ? undefined : { gamma }),
    implied_volatility: iv === undefined ? 0.3 : iv,
  };
}

// ---- aggregateByStrike -------------------------------------------------
test("aggregateByStrike: basic call/put net at same strike", () => {
  const spot = 100;
  const contracts = [
    contract({ strike: 100, type: "call", oi: 1000, gamma: 0.05 }),
    contract({ strike: 100, type: "put", oi: 500, gamma: 0.04 }),
  ];
  const agg = aggregateByStrike(contracts, spot);
  assert.strictEqual(agg.strikes.length, 1);
  const s = agg.strikes[0];
  // call: +1000*0.05*100*100*100*0.01 = +500000 ; put: -500*0.04*100*100*100*0.01 = -200000
  assert.ok(s.call > 0, "call GEX should be positive");
  assert.ok(s.put < 0, "put GEX should be negative");
  assert.ok(s.net > 0, "net should be dominated by larger call OI here");
});

test("aggregateByStrike: missing gamma excludes contract from GEX, still counted in coverage", () => {
  const contracts = [
    contract({ strike: 100, type: "call", oi: 1000, gamma: null }), // greeks absent
  ];
  const agg = aggregateByStrike(contracts, 100);
  assert.strictEqual(agg.contractsSeen, 1);
  assert.strictEqual(agg.contractsUsedForGex, 0, "contract with no greeks must not contribute GEX");
  assert.strictEqual(agg.greeksPresentCount, 0);
  assert.strictEqual(agg.oiPresentCount, 1);
});

test("aggregateByStrike: missing OI excludes contract from GEX", () => {
  const contracts = [contract({ strike: 100, type: "call", oi: null, gamma: 0.05 })];
  const agg = aggregateByStrike(contracts, 100);
  assert.strictEqual(agg.contractsUsedForGex, 0);
  assert.strictEqual(agg.oiPresentCount, 0);
});

test("aggregateByStrike: 0DTE contracts tracked separately and excluded when none exist", () => {
  const contracts = [contract({ strike: 100, type: "call", oi: 100, gamma: 0.05, expiration: "2099-01-01" })];
  const agg = aggregateByStrike(contracts, 100);
  assert.strictEqual(agg.zeroDteNetGex, null, "no 0DTE contracts -> null, not 0");
});

// ---- computeGammaFlip ----------------------------------------------------
test("computeGammaFlip: finds zero-crossing in CUMULATIVE net GEX walked low-to-high strike", () => {
  // Flip is defined here as the strike where cumulative NetGEX (summed
  // ascending from the lowest strike) crosses zero — see ocm-engine.js
  // header docs for why this cumulative-walk approximation is used instead
  // of a full repriced-gamma-surface flip (which snapshot greeks can't support).
  const strikes = [
    { strike: 90, net: 500 },
    { strike: 95, net: 300 },   // cumulative: 500, 800
    { strike: 100, net: -200 }, // cumulative: 600
    { strike: 105, net: -800 }, // cumulative: -200 <- sign change here
  ];
  const flip = computeGammaFlip(strikes);
  assert.ok(flip > 100 && flip < 105, "flip should interpolate between 100 and 105, got " + flip);
});

test("computeGammaFlip: returns null when no sign change exists (directive: do not invent a flip)", () => {
  const strikes = [{ strike: 90, net: 100 }, { strike: 100, net: 200 }, { strike: 110, net: 300 }];
  assert.strictEqual(computeGammaFlip(strikes), null);
});

test("computeGammaFlip: empty strikes -> null", () => {
  assert.strictEqual(computeGammaFlip([]), null);
});

// ---- wall / pit -----------------------------------------------------------
test("computePositiveWall: picks strike with MAX positive net, not highest strike", () => {
  const strikes = [{ strike: 90, net: 50 }, { strike: 100, net: 900 }, { strike: 200, net: 10 }];
  assert.strictEqual(computePositiveWall(strikes), 100, "wall must be the max-magnitude positive strike, not the highest strike (200)");
});

test("computeNegativePit: picks strike with MIN (most negative) net, not lowest strike", () => {
  const strikes = [{ strike: 10, net: -5 }, { strike: 90, net: -900 }, { strike: 100, net: -50 }];
  assert.strictEqual(computeNegativePit(strikes), 90, "pit must be the most-negative strike, not the lowest strike (10)");
});

test("computePositiveWall/Pit: null when no strikes qualify", () => {
  assert.strictEqual(computePositiveWall([{ strike: 100, net: -5 }]), null);
  assert.strictEqual(computeNegativePit([{ strike: 100, net: 5 }]), null);
});

// ---- gauge / regime ---------------------------------------------------
test("computeGammaGauge: all-positive strikes -> gauge = 100", () => {
  const strikes = [{ strike: 90, net: 100 }, { strike: 100, net: 200 }];
  assert.strictEqual(computeGammaGauge(strikes), 100);
});
test("computeGammaGauge: all-negative strikes -> gauge = -100", () => {
  const strikes = [{ strike: 90, net: -100 }, { strike: 100, net: -200 }];
  assert.strictEqual(computeGammaGauge(strikes), -100);
});
test("computeGammaGauge: balanced -> gauge near 0", () => {
  const strikes = [{ strike: 90, net: 100 }, { strike: 100, net: -100 }];
  assert.strictEqual(computeGammaGauge(strikes), 0);
});
test("computeGammaGauge: no data -> null", () => {
  assert.strictEqual(computeGammaGauge([]), null);
});

test("computeRegime: POSITIVE/NEGATIVE/TRANSITION/UNKNOWN branches", () => {
  assert.strictEqual(computeRegime(50, 90, 100), "POSITIVE");
  assert.strictEqual(computeRegime(-50, 90, 100), "NEGATIVE");
  assert.strictEqual(computeRegime(50, 99.8, 100), "TRANSITION", "within 0.5% of flip -> TRANSITION even if gauge is high");
  assert.strictEqual(computeRegime(null, 90, 100), "UNKNOWN");
  assert.strictEqual(computeRegime(50, null, 100), "UNKNOWN");
});

// ---- confidence -------------------------------------------------------
test("computeConfidence: full coverage + ample contracts -> 100", () => {
  const agg = { contractsSeen: 100, oiPresentCount: 100, greeksPresentCount: 100, contractsUsedForGex: 100 };
  assert.strictEqual(computeConfidence(agg), 100);
});
test("computeConfidence: zero contracts -> 0", () => {
  assert.strictEqual(computeConfidence({ contractsSeen: 0 }), 0);
});
test("computeConfidence: partial coverage produces intermediate score", () => {
  const agg = { contractsSeen: 100, oiPresentCount: 50, greeksPresentCount: 50, contractsUsedForGex: 25 };
  const c = computeConfidence(agg);
  assert.ok(c > 0 && c < 100, "expected intermediate confidence, got " + c);
});

// ---- top-level orchestration -------------------------------------------
test("computeOcmGammaSnapshot: empty contracts -> UNAVAILABLE-shaped (valid=false), no fabricated zeros", () => {
  const snap = computeOcmGammaSnapshot({ contracts: [], spot: 100, symbol: "TEST", snapshotId: "s1" });
  assert.strictEqual(snap.valid, false);
  assert.strictEqual(snap.gammaFlip, null);
  assert.strictEqual(snap.positiveGammaWall, null);
  assert.strictEqual(snap.totalNetGex, null);
  assert.ok(snap.warnings.includes("no_contracts_returned"));
});

test("computeOcmGammaSnapshot: null spot -> valid=false, warning present", () => {
  const contracts = [contract({ strike: 100, type: "call", oi: 100, gamma: 0.05 })];
  const snap = computeOcmGammaSnapshot({ contracts, spot: null, symbol: "TEST", snapshotId: "s2" });
  assert.strictEqual(snap.valid, false);
  assert.ok(snap.warnings.includes("no_spot_price_available"));
});

test("computeOcmGammaSnapshot: realistic mixed chain produces a full valid snapshot", () => {
  const spot = 100;
  const contracts = [
    contract({ strike: 90, type: "put", oi: 5000, gamma: 0.01 }),
    contract({ strike: 95, type: "put", oi: 3000, gamma: 0.02 }),
    contract({ strike: 100, type: "call", oi: 4000, gamma: 0.03 }),
    contract({ strike: 100, type: "put", oi: 1000, gamma: 0.03 }),
    contract({ strike: 105, type: "call", oi: 6000, gamma: 0.015 }),
    contract({ strike: 110, type: "call", oi: 2000, gamma: 0.008 }),
  ];
  const snap = computeOcmGammaSnapshot({ contracts, spot, symbol: "TEST", snapshotId: "s3" });
  assert.strictEqual(snap.valid, true);
  assert.ok(typeof snap.gammaGauge === "number");
  assert.ok(["POSITIVE", "NEGATIVE", "TRANSITION", "UNKNOWN"].includes(snap.gammaRegime));
  assert.strictEqual(snap.quality.contractsSeen, 6);
  assert.strictEqual(snap.quality.contractsUsed, 6);
  assert.strictEqual(snap.quality.openInterestCoveragePct, 100);
  assert.strictEqual(snap.quality.greeksCoveragePct, 100);
  assert.strictEqual(snap.schemaVersion, "1.0");
  assert.strictEqual(snap.source, "MASSIVE_OPTIONS");
  // Item #17: gexByStrike present, correct shape, sorted ascending
  assert.ok(Array.isArray(snap.gexByStrike), "gexByStrike must be an array on a valid snapshot");
  assert.strictEqual(snap.gexByStrike.length, 5, "6 contracts across 5 distinct strikes -> 5 rows");
  for (const row of snap.gexByStrike) {
    assert.ok(typeof row.strike === "number");
    assert.ok("call" in row && "put" in row && "net" in row);
  }
  for (let i = 1; i < snap.gexByStrike.length; i++) {
    assert.ok(snap.gexByStrike[i].strike > snap.gexByStrike[i - 1].strike, "strikes must be sorted ascending");
  }
  assert.strictEqual(snap.gexByStrikeScope, "ALL_EXPIRATIONS");
  assert.ok(typeof snap.gexByStrikeConvention === "string" && snap.gexByStrikeConvention.length > 0);
});

test("computeOcmGammaSnapshot: never returns 0 for missing zeroDteNetGex/totalNetGex when no usable strikes", () => {
  const contracts = [contract({ strike: 100, type: "call", oi: null, gamma: 0.05 })]; // no OI -> unusable
  const snap = computeOcmGammaSnapshot({ contracts, spot: 100, symbol: "TEST", snapshotId: "s4" });
  assert.strictEqual(snap.totalNetGex, null, "must be null, not 0, when no strikes were usable");
  assert.strictEqual(snap.zeroDteNetGex, null);
  // Item #17: gexByStrike follows the same null discipline — null, never []
  assert.strictEqual(snap.gexByStrike, null, "gexByStrike must be null (not []) when no contracts contributed usable GEX");
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
