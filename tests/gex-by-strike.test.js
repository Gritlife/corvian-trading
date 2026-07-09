// tests/gex-by-strike.test.js
// Item #17 (Phase C) — canonical gexByStrike state. Implements the exact
// 14-test plan from the approved Phase B report, Section 10.
// Run: node tests/gex-by-strike.test.js

const assert = require("assert");
const { computeOcmGammaSnapshot, GEX_SCALE } = require("../netlify/functions/lib/ocm-engine");

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

// Shared deterministic fixture: spot 100, two strikes.
const SPOT = 100;
function fixtureContracts() {
  return [
    contract({ strike: 95, type: "put", oi: 200, gamma: 0.02 }),   // put GEX = -(200*0.02*100*100*100*0.01) = -40,000
    contract({ strike: 100, type: "call", oi: 100, gamma: 0.05 }), // call GEX = +(100*0.05*100*100*100*0.01) = +50,000
    contract({ strike: 100, type: "put", oi: 50, gamma: 0.05 }),   // put GEX = -(50*0.05*100*100*100*0.01) = -25,000
  ];
}
function snapFor(contracts, spot) {
  return computeOcmGammaSnapshot({ contracts, spot: spot === undefined ? SPOT : spot, symbol: "TEST", snapshotId: "gbs" });
}

// 1. Deterministic fixture — exact expected values
test("1. deterministic fixture produces exact {strike, call, put, net} values", () => {
  const snap = snapFor(fixtureContracts());
  assert.deepStrictEqual(snap.gexByStrike, [
    { strike: 95, call: null, put: -40000, net: -40000 },
    { strike: 100, call: 50000, put: -25000, net: 25000 },
  ]);
});

// 2. Call leg positive sign
test("2. call leg GEX is positive", () => {
  const snap = snapFor([contract({ strike: 100, type: "call", oi: 100, gamma: 0.05 })]);
  assert.ok(snap.gexByStrike[0].call > 0);
  assert.strictEqual(snap.gexByStrike[0].put, null);
});

// 3. Put leg negative sign
test("3. put leg GEX is negative", () => {
  const snap = snapFor([contract({ strike: 100, type: "put", oi: 100, gamma: 0.05 })]);
  assert.ok(snap.gexByStrike[0].put < 0);
  assert.strictEqual(snap.gexByStrike[0].call, null);
});

// 4. Same-strike netting
test("4. same-strike call+put netting: net === call + put", () => {
  const snap = snapFor(fixtureContracts());
  const row = snap.gexByStrike.find(r => r.strike === 100);
  assert.strictEqual(row.net, row.call + row.put);
});

// 5. Sorted ascending
test("5. strikes sorted ascending", () => {
  const contracts = [
    contract({ strike: 110, type: "call", oi: 10, gamma: 0.01 }),
    contract({ strike: 90, type: "call", oi: 10, gamma: 0.01 }),
    contract({ strike: 100, type: "call", oi: 10, gamma: 0.01 }),
  ];
  const snap = snapFor(contracts);
  assert.deepStrictEqual(snap.gexByStrike.map(r => r.strike), [90, 100, 110]);
});

// 6. Missing gamma
test("6. missing gamma excludes contract; sole-contributor leg stays null", () => {
  const contracts = [
    contract({ strike: 100, type: "call", oi: 100, gamma: null }), // unusable
    contract({ strike: 100, type: "put", oi: 50, gamma: 0.05 }),
  ];
  const snap = snapFor(contracts);
  const row = snap.gexByStrike.find(r => r.strike === 100);
  assert.strictEqual(row.call, null, "call leg had no usable contributor -> null, never 0");
  assert.ok(row.put < 0);
});

// 7. Missing OI
test("7. missing OI excludes contract; sole-contributor leg stays null", () => {
  const contracts = [
    contract({ strike: 100, type: "put", oi: null, gamma: 0.05 }), // unusable
    contract({ strike: 100, type: "call", oi: 100, gamma: 0.05 }),
  ];
  const snap = snapFor(contracts);
  const row = snap.gexByStrike.find(r => r.strike === 100);
  assert.strictEqual(row.put, null);
  assert.ok(row.call > 0);
});

// 8. Custom shares_per_contract
test("8. shares_per_contract=10 scales GEX exactly 10x below the default 100", () => {
  const base = snapFor([contract({ strike: 100, type: "call", oi: 100, gamma: 0.05, multiplier: 100 })]);
  const small = snapFor([contract({ strike: 100, type: "call", oi: 100, gamma: 0.05, multiplier: 10 })]);
  assert.strictEqual(base.gexByStrike[0].call, small.gexByStrike[0].call * 10);
});

// 9. Spot dependency
test("9. spot=null -> gexByStrike is null", () => {
  const snap = snapFor(fixtureContracts(), null);
  assert.strictEqual(snap.gexByStrike, null);
  assert.strictEqual(snap.valid, false);
});

// 10. Empty chain
test("10. empty chain -> gexByStrike is null, not []", () => {
  const snap = snapFor([]);
  assert.strictEqual(snap.gexByStrike, null);
});

// 11. Partial chain: array unaffected by completeness (completeness is orchestrator metadata)
test("11. gexByStrike reflects supplied contracts; completeness classification is independent metadata", () => {
  // The pure engine has no pagination knowledge — completeness enters only
  // via the orchestrator's modifier. Verify the array is built from exactly
  // the contracts given, and the completeness modifier changes ONLY the
  // confidence, never the array contents.
  const contracts = fixtureContracts();
  const full = computeOcmGammaSnapshot({ contracts, spot: SPOT, symbol: "T", snapshotId: "a" });
  const truncated = computeOcmGammaSnapshot({ contracts, spot: SPOT, symbol: "T", snapshotId: "a", chainCompletenessModifier: 0.40 });
  assert.deepStrictEqual(truncated.gexByStrike, full.gexByStrike, "array must be identical regardless of completeness modifier");
  assert.ok(truncated.confidenceScore < full.confidenceScore, "modifier must still reduce confidence");
});

// 12. Additive compatibility: every pre-existing field unchanged
test("12. all pre-existing snapshot fields present and unchanged in value for a fixed fixture", () => {
  const contracts = fixtureContracts();
  const snap = snapFor(contracts);
  const preExisting = ["schemaVersion", "snapshotId", "symbol", "underlyingSpot", "timestampUtc", "source",
    "valid", "stale", "confidenceScore", "confidenceBreakdown", "gammaGauge", "gammaRegime", "gammaFlip",
    "positiveGammaWall", "negativeGammaPit", "nearestPositiveAbove", "nearestNegativeBelow",
    "zeroDteNetGex", "totalNetGex", "levels", "quality", "warnings"];
  for (const f of preExisting) {
    assert.ok(f in snap, `pre-existing field missing after Item #17: ${f}`);
  }
  // Spot-check values that must be numerically identical to pre-change behavior:
  assert.strictEqual(snap.totalNetGex, -15000); // -40000 + 25000
  assert.strictEqual(snap.underlyingSpot, 100);
  assert.strictEqual(snap.quality.contractsSeen, 3);
});

// 13. JSON serialization round-trip
test("13. JSON.stringify/parse round-trip preserves gexByStrike exactly", () => {
  const snap = snapFor(fixtureContracts());
  const roundTripped = JSON.parse(JSON.stringify(snap));
  assert.deepStrictEqual(roundTripped.gexByStrike, snap.gexByStrike);
  assert.strictEqual(roundTripped.gexByStrikeScope, "ALL_EXPIRATIONS");
});

// 14. Top-5 levels unchanged
test("14. levels.positive/levels.negative identical to pre-change derivation for the same fixture", () => {
  const snap = snapFor(fixtureContracts());
  // Pre-change derivation, reproduced independently from the fixture:
  // strikes: 95 net -40000 (negative), 100 net +25000 (positive)
  assert.deepStrictEqual(snap.levels.positive, [100]);
  assert.deepStrictEqual(snap.levels.negative, [95]);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
