// netlify/functions/lib/ocm-engine.js
// ============================================================================
// OCM (Options Chain Manager) — Gamma calculation layer.
// Phase 4-6 of the ToF V1.1 directive. Pure functions, no network/DOM/state.
//
// ----------------------------------------------------------------------------
// GEX METHODOLOGY (directive Phase 5 — must be documented, not hidden)
// ----------------------------------------------------------------------------
// Formula (per strike, per contract type):
//   GEX_call(strike) = +1 * OI_call * gamma_call * multiplier * spot^2 * 0.01
//   GEX_put(strike)  = -1 * OI_put  * gamma_put  * multiplier * spot^2 * 0.01
//   NetGEX(strike)   = GEX_call(strike) + GEX_put(strike)
//
// SIGN CONVENTION — this is an ASSUMPTION, not a measured fact:
//   We assume dealers are net short calls and net short puts to customers
//   (the common simplified "customer-long" convention used by most public
//   GEX approximations, e.g. SqueezeMetrics/SpotGamma-style public write-ups).
//   Under that assumption, dealer hedging of short calls is gamma-positive
//   (stabilizing, dealers buy into strength / sell into weakness) and dealer
//   hedging of short puts is gamma-negative (destabilizing). This is a widely
//   used convention but is NOT verified against actual dealer positioning —
//   real dealer books can differ per strike/expiration. Do not present this
//   as measured dealer positioning; it is a standard proxy.
//
// CONTRACT MULTIPLIER: shares_per_contract from the contract's `details` if
// present, else 100 (standard US equity option multiplier).
//
// SCALING (spot^2 * 0.01): standard GEX literature convention — approximates
// dollar gamma exposure per 1% move in the underlying. 0.01 = (1% of spot)^2 / spot^2
// simplification commonly used; this is a normalization choice, not a law of
// physics — documented here explicitly per Phase 5.
//
// OPEN INTEREST: OI as of the most recent daily settlement (Massive's
// `open_interest` field — "quantity held at end of last trading day").
// This is not intraday-live OI; it lags same-day changes in fresh OI. When
// combined with a 15-min-delayed price (Options Starter plan), the gamma
// snapshot is inherently NOT real-time strike-level metrics even though spot
// itself may be closer to real-time.
//
// 0DTE: contracts whose expiration_date equals "today" in US/Eastern.
// Missing OI/Greeks: contract is excluded from the sum for that specific
// missing field (not treated as 0). Quality metrics report coverage %.
//
// gexByStrike (Item #17, additive): computeOcmGammaSnapshot() exposes the
// full sorted strike-level array [{strike, call, put, net}] produced by
// aggregateByStrike() — ALL expirations collapsed per strike
// (gexByStrikeScope: "ALL_EXPIRATIONS"), signed per the dealer-short
// convention above (gexByStrikeConvention tag on the snapshot). Null (not
// []) when zero contracts contributed usable GEX; a leg is null at a
// strike when no contract of that leg contributed there. This is exposure
// of already-computed state, NOT a second GEX model.
// ============================================================================

const CONTRACT_MULTIPLIER_DEFAULT = 100;
const GEX_SCALE = 0.01;

function todayET() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
}

/**
 * @param {Array} contracts  raw Massive option-chain contract objects
 * @param {number} spot      underlying spot price (from equity data, NOT options data)
 * @returns {Object} strike-level GEX aggregation + quality counters
 */
function aggregateByStrike(contracts, spot) {
  const byStrike = new Map(); // strike -> { call: gexOrNull, put: gexOrNull, net }
  let contractsSeen = 0;
  let contractsUsedForGex = 0;
  let oiPresentCount = 0;
  let greeksPresentCount = 0;
  let ivPresentCount = 0;
  let zeroDteNet = 0;
  let zeroDteCount = 0;
  const today = todayET();

  for (const c of contracts) {
    contractsSeen++;
    const details = c.details || {};
    const strike = details.strike_price;
    const type = details.contract_type; // "call" | "put"
    const expiration = details.expiration_date;
    const multiplier = details.shares_per_contract || CONTRACT_MULTIPLIER_DEFAULT;

    const oi = (typeof c.open_interest === "number") ? c.open_interest : null;
    const gamma = (c.greeks && typeof c.greeks.gamma === "number") ? c.greeks.gamma : null;
    const iv = (typeof c.implied_volatility === "number") ? c.implied_volatility : null;

    if (oi != null) oiPresentCount++;
    if (gamma != null) greeksPresentCount++;
    if (iv != null) ivPresentCount++;

    if (strike == null || (type !== "call" && type !== "put")) continue;

    if (!byStrike.has(strike)) byStrike.set(strike, { call: null, put: null });
    const bucket = byStrike.get(strike);

    // GEX for this contract is computable ONLY when both OI and gamma are present.
    // Missing either -> this contract contributes null (excluded), not zero.
    if (oi != null && gamma != null && spot != null) {
      const gex = oi * gamma * multiplier * spot * spot * GEX_SCALE;
      const signedGex = type === "call" ? gex : -gex;
      bucket[type] = (bucket[type] || 0) + signedGex;
      contractsUsedForGex++;

      if (expiration === today) {
        zeroDteNet += signedGex;
        zeroDteCount++;
      }
    }
  }

  const strikes = [];
  for (const [strike, bucket] of byStrike.entries()) {
    const net = (bucket.call || 0) + (bucket.put || 0);
    strikes.push({ strike, call: bucket.call, put: bucket.put, net });
  }
  strikes.sort((a, b) => a.strike - b.strike);

  return {
    strikes,
    contractsSeen,
    contractsUsedForGex,
    oiPresentCount,
    greeksPresentCount,
    ivPresentCount,
    zeroDteNetGex: zeroDteCount > 0 ? zeroDteNet : null,
    zeroDteContractCount: zeroDteCount,
  };
}

/**
 * Gamma Flip: strike where cumulative NetGEX (walked from lowest to highest
 * strike) crosses zero, nearest to spot. Linear-interpolated between the two
 * bracketing strikes. Returns null if no sign change exists in the data
 * (directive: "do not invent a flip when the chain does not support one").
 *
 * METHODOLOGY LIMITATION (must be disclosed, not hidden): this is a
 * cumulative-walk approximation using each contract's greeks AS COMPUTED AT
 * THE CURRENT SPOT. A mathematically fuller "gamma flip" would reprice every
 * contract's gamma at each hypothetical spot level along the walk (since
 * gamma itself is spot-dependent), which requires a full vol surface / model
 * re-price, not just a single snapshot's greeks. This function does NOT do
 * that repricing — it is the standard simplified public-calculator
 * approximation, not a fully repriced flip. Do not present this level as
 * more precise than it is.
 */
function computeGammaFlip(strikes) {
  if (!strikes.length) return null;
  let cum = 0;
  const cumSeries = strikes.map(s => { cum += s.net; return { strike: s.strike, cum }; });
  for (let i = 1; i < cumSeries.length; i++) {
    const prev = cumSeries[i - 1], curr = cumSeries[i];
    if ((prev.cum <= 0 && curr.cum > 0) || (prev.cum >= 0 && curr.cum < 0)) {
      // Linear interpolation between prev.strike and curr.strike for the zero-crossing
      const span = curr.cum - prev.cum;
      if (span === 0) return prev.strike;
      const t = (0 - prev.cum) / span;
      return prev.strike + t * (curr.strike - prev.strike);
    }
  }
  return null; // no sign change found — chain doesn't support a flip
}

/**
 * Positive Gamma Wall: strike with the maximum positive NetGEX (aggregated
 * structure, not "highest strike" or "nearest call strike" — directive
 * explicitly requires this distinction).
 */
function computePositiveWall(strikes) {
  let best = null;
  for (const s of strikes) {
    if (s.net > 0 && (best === null || s.net > best.net)) best = s;
  }
  return best ? best.strike : null;
}

/** Negative Gamma Pit: strike with the minimum (most negative) NetGEX. */
function computeNegativePit(strikes) {
  let worst = null;
  for (const s of strikes) {
    if (s.net < 0 && (worst === null || s.net < worst.net)) worst = s;
  }
  return worst ? worst.strike : null;
}

function nearestAboveSpot(strikes, spot, predicate) {
  let best = null;
  for (const s of strikes) {
    if (s.strike > spot && predicate(s) && (best === null || s.strike < best)) best = s.strike;
  }
  return best;
}
function nearestBelowSpot(strikes, spot, predicate) {
  let best = null;
  for (const s of strikes) {
    if (s.strike < spot && predicate(s) && (best === null || s.strike > best)) best = s.strike;
  }
  return best;
}

/**
 * Gamma Gauge: normalized to -100..100 as
 *   gauge = 100 * totalNetGEX / sum(|NetGEX per strike|)
 * i.e. "what fraction of total gamma magnitude is net positive vs negative",
 * which is naturally bounded in [-100, 100] without an arbitrary external
 * scale constant. Documented per directive Phase 6 "document normalization".
 * Returns null if there is no usable GEX data at all (sumAbs === 0).
 */
function computeGammaGauge(strikes) {
  let total = 0, sumAbs = 0;
  for (const s of strikes) { total += s.net; sumAbs += Math.abs(s.net); }
  if (sumAbs === 0) return null;
  return Math.max(-100, Math.min(100, (100 * total) / sumAbs));
}

function computeRegime(gauge, flip, spot) {
  if (gauge == null || flip == null || spot == null) return "UNKNOWN";
  const distPct = Math.abs(spot - flip) / spot;
  if (distPct <= 0.005) return "TRANSITION"; // within 0.5% of spot -> too close to call
  if (gauge > 10) return "POSITIVE";
  if (gauge < -10) return "NEGATIVE";
  return "TRANSITION";
}

/**
 * Confidence score (0-100), documented weights (directive requires this be
 * derivable from real coverage, not fabricated):
 *   40% open-interest coverage, 40% greeks coverage, 20% contract-count floor
 *   (min(1, contractsUsedForGex/50) — 50 usable contracts treated as "ample").
 */
function computeConfidence(agg) {
  if (agg.contractsSeen === 0) return 0;
  const oiCov = agg.oiPresentCount / agg.contractsSeen;
  const greeksCov = agg.greeksPresentCount / agg.contractsSeen;
  const countFloor = Math.min(1, agg.contractsUsedForGex / 50);
  return Math.round(100 * (oiCov * 0.4 + greeksCov * 0.4 + countFloor * 0.2));
}

// ============================================================================
// REMEDIATION #4 — Explainable confidence breakdown
// ============================================================================
// Decomposes the confidence score into named, inspectable components, then
// applies two ADDITIONAL modifiers that are orchestration-level facts this
// pure engine doesn't otherwise see: chain completeness and data freshness.
// Both modifiers are MULTIPLICATIVE penalties in [0, 1] supplied by the
// caller (netlify/functions/ocm-gamma-snapshot.js) — this function stays
// pure (no network/clock access) and simply documents how they combine.
//
// finalScore = baseScore * chainCompletenessModifier * freshnessModifier,
// rounded and clamped to [0, 100]. Every component is returned so the
// caller/UI can show exactly why a score is what it is — never a black box.
//
// completenessModifier semantics (caller passes this in):
//   1.00 = chain confirmed complete (no penalty)
//   0.60-0.85 = completeness unknown (meaningful penalty; exact value is
//               the caller's documented choice, see CHAIN_COMPLETENESS_SPEC.md)
//   0.25-0.50 = chain confirmed truncated (major penalty)
//
// freshnessModifier semantics (caller passes this in):
//   1.00 = both spot and options data fresh
//   0.70-0.90 = one or both dimensions delayed/unknown
//   0.30-0.50 = one or both dimensions stale
// ============================================================================
function computeConfidenceBreakdown(agg, modifiers) {
  modifiers = modifiers || {};
  const chainCompletenessModifier = clamp01(modifiers.chainCompletenessModifier != null ? modifiers.chainCompletenessModifier : 1.0);
  const freshnessModifier = clamp01(modifiers.freshnessModifier != null ? modifiers.freshnessModifier : 1.0);

  if (agg.contractsSeen === 0) {
    return {
      baseScore: 0,
      openInterestCoverageComponent: 0,
      greeksCoverageComponent: 0,
      contractCountComponent: 0,
      chainCompletenessModifier,
      freshnessModifier,
      finalScore: 0,
    };
  }

  const oiCov = agg.oiPresentCount / agg.contractsSeen;
  const greeksCov = agg.greeksPresentCount / agg.contractsSeen;
  const countFloor = Math.min(1, agg.contractsUsedForGex / 50);

  const openInterestCoverageComponent = Math.round(oiCov * 40);
  const greeksCoverageComponent = Math.round(greeksCov * 40);
  const contractCountComponent = Math.round(countFloor * 20);
  const baseScore = Math.min(100, openInterestCoverageComponent + greeksCoverageComponent + contractCountComponent);

  const finalScore = Math.round(Math.max(0, Math.min(100, baseScore * chainCompletenessModifier * freshnessModifier)));

  return {
    baseScore,
    openInterestCoverageComponent,
    greeksCoverageComponent,
    contractCountComponent,
    chainCompletenessModifier,
    freshnessModifier,
    finalScore,
  };
}
function clamp01(v) { return Math.max(0, Math.min(1, v)); }


/**
 * Top-level OCM computation. Pure function: contracts + spot in, normalized
 * Gamma Snapshot contract out (directive Phase 4 schema).
 * @param {Object} args
 * @param {Array} args.contracts   raw Massive option-chain contracts
 * @param {number} args.spot       underlying spot (from equity data)
 * @param {string} args.symbol
 * @param {string} args.snapshotId
 */
function computeOcmGammaSnapshot(args) {
  const { contracts, spot, symbol, snapshotId, chainCompletenessModifier, freshnessModifier } = args;
  const warnings = [];

  if (!contracts || contracts.length === 0) {
    warnings.push("no_contracts_returned");
  }
  if (spot == null) {
    warnings.push("no_spot_price_available");
  }

  const agg = (contracts && spot != null) ? aggregateByStrike(contracts, spot) : {
    strikes: [], contractsSeen: 0, contractsUsedForGex: 0, oiPresentCount: 0,
    greeksPresentCount: 0, ivPresentCount: 0, zeroDteNetGex: null, zeroDteContractCount: 0,
  };

  const flip = computeGammaFlip(agg.strikes);
  const wall = computePositiveWall(agg.strikes);
  const pit = computeNegativePit(agg.strikes);
  const nearestPosAbove = nearestAboveSpot(agg.strikes, spot, s => s.net > 0);
  const nearestNegBelow = nearestBelowSpot(agg.strikes, spot, s => s.net < 0);
  const gauge = computeGammaGauge(agg.strikes);
  const regime = computeRegime(gauge, flip, spot);
  // REMEDIATION #4 — confidence is now a full breakdown; confidenceScore
  // below is its finalScore (chain-completeness- and freshness-adjusted),
  // never the unadjusted baseScore. See CHAIN_COMPLETENESS_SPEC.md /
  // FRESHNESS_SPEC.md for what the caller passes in as modifiers.
  const confidenceBreakdown = computeConfidenceBreakdown(agg, { chainCompletenessModifier, freshnessModifier });
  const confidence = confidenceBreakdown.finalScore;

  let totalNetGex = null;
  if (agg.contractsUsedForGex > 0) {
    totalNetGex = agg.strikes.reduce((s, x) => s + x.net, 0);
  }

  if (agg.contractsSeen > 0 && agg.contractsUsedForGex === 0) {
    warnings.push("no_contracts_had_both_oi_and_gamma");
  }
  if (flip == null && agg.strikes.length > 0) {
    warnings.push("no_gamma_flip_zero_crossing_found");
  }

  const positiveLevels = agg.strikes.filter(s => s.net > 0).sort((a, b) => b.net - a.net).slice(0, 5).map(s => s.strike);
  const negativeLevels = agg.strikes.filter(s => s.net < 0).sort((a, b) => a.net - b.net).slice(0, 5).map(s => s.strike);

  return {
    schemaVersion: "1.0",
    snapshotId: snapshotId || null,
    symbol,
    underlyingSpot: spot != null ? spot : null,
    timestampUtc: new Date().toISOString(),
    source: "MASSIVE_OPTIONS",
    valid: agg.contractsUsedForGex > 0 && spot != null,
    stale: false, // staleness is a caller concern; see ocm-gamma-snapshot.js's separate spot/options freshness dimensions
    confidenceScore: confidence,
    confidenceBreakdown,

    gammaGauge: gauge,
    gammaRegime: regime,

    gammaFlip: flip,
    positiveGammaWall: wall,
    negativeGammaPit: pit,

    nearestPositiveAbove: nearestPosAbove,
    nearestNegativeBelow: nearestNegBelow,


    zeroDteNetGex: agg.zeroDteNetGex,
    totalNetGex,

    // ---- Item #17: canonical GEX-by-strike state (ADDITIVE, v1.1) ----------
    // Full sorted strike-level array from aggregateByStrike(), previously
    // computed and discarded. null (not []) when no contract contributed
    // usable GEX — matching totalNetGex's null discipline. Legs are null
    // when no contract of that leg contributed at that strike (never 0).
    // Scope/convention tags make the array self-describing for the future
    // M-EOD consumer; see OCM_METHODOLOGY.md "gexByStrike".
    gexByStrike: agg.contractsUsedForGex > 0 ? agg.strikes : null,
    gexByStrikeScope: "ALL_EXPIRATIONS",
    gexByStrikeConvention: "DEALER_SHORT_+CALL_-PUT_SPOT2_x0.01",

    levels: { positive: positiveLevels, negative: negativeLevels },

    quality: {
      contractsSeen: agg.contractsSeen,
      contractsUsed: agg.contractsUsedForGex,
      openInterestCoveragePct: agg.contractsSeen > 0 ? Math.round(100 * agg.oiPresentCount / agg.contractsSeen) : null,
      greeksCoveragePct: agg.contractsSeen > 0 ? Math.round(100 * agg.greeksPresentCount / agg.contractsSeen) : null,
      ivCoveragePct: agg.contractsSeen > 0 ? Math.round(100 * agg.ivPresentCount / agg.contractsSeen) : null,
    },

    warnings,
  };
}

module.exports = {
  aggregateByStrike, computeGammaFlip, computePositiveWall, computeNegativePit,
  nearestAboveSpot, nearestBelowSpot, computeGammaGauge, computeRegime,
  computeConfidence, computeConfidenceBreakdown, computeOcmGammaSnapshot,
  CONTRACT_MULTIPLIER_DEFAULT, GEX_SCALE,
};
