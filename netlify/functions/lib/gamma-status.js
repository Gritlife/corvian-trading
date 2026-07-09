// netlify/functions/lib/gamma-status.js
// ============================================================================
// Pure classification logic for chain completeness, freshness, and the
// Gamma health state machine. Extracted from ocm-gamma-snapshot.js so it
// can be unit-tested directly without mocking network calls — see
// GAMMA_STATUS_SPEC.md / CHAIN_COMPLETENESS_SPEC.md / FRESHNESS_SPEC.md.
// ============================================================================

const GAMMA_STATUS = Object.freeze({
  UNAVAILABLE: "GAMMA UNAVAILABLE",
  INVALID: "GAMMA INVALID",
  STALE: "GAMMA STALE",
  DEGRADED_PARTIAL_CHAIN: "GAMMA DEGRADED — PARTIAL CHAIN",
  DEGRADED_UNKNOWN_COMPLETENESS: "GAMMA DEGRADED — UNKNOWN COMPLETENESS",
  LOW_CONFIDENCE: "GAMMA LOW CONFIDENCE",
  DELAYED: "GAMMA DELAYED",
  VALID: "GAMMA VALID",
});

const PAGE_LIMIT = 4;
const COMPLETENESS_MODIFIER_COMPLETE = 1.00;
const COMPLETENESS_MODIFIER_UNKNOWN = 0.75;
const COMPLETENESS_MODIFIER_TRUNCATED = 0.40;

const DOCUMENTED_DELAY_MINUTES = 15;
const FRESH_THRESHOLD_MINUTES = 20;
const DELAYED_THRESHOLD_MINUTES = 45;
const FRESHNESS_MODIFIER_FRESH = 1.00;
const FRESHNESS_MODIFIER_DELAYED = 0.85;
const FRESHNESS_MODIFIER_UNKNOWN = 0.70;
const FRESHNESS_MODIFIER_STALE = 0.35;

const MIN_CONFIDENCE = 40;

/**
 * REMEDIATION #1 — deterministic, truthful-only chain completeness
 * classification. Never claims "complete" unless the upstream pagination
 * signal (absence of next_url) was actually observed.
 */
function classifyCompleteness({ upstreamPaginationObserved, sawExplicitEnd, hasMorePages, pageLimitReached }) {
  let chainComplete, truncated, completenessStatus;
  if (!upstreamPaginationObserved) {
    chainComplete = false; truncated = false; completenessStatus = "UNKNOWN";
  } else if (sawExplicitEnd && !hasMorePages) {
    chainComplete = true; truncated = false; completenessStatus = "COMPLETE";
  } else if (pageLimitReached) {
    chainComplete = false; truncated = true; completenessStatus = "TRUNCATED";
  } else {
    chainComplete = false; truncated = false; completenessStatus = "UNKNOWN";
  }
  const chainCompletenessModifier =
    completenessStatus === "COMPLETE" ? COMPLETENESS_MODIFIER_COMPLETE :
    completenessStatus === "TRUNCATED" ? COMPLETENESS_MODIFIER_TRUNCATED :
    COMPLETENESS_MODIFIER_UNKNOWN;
  return { chainComplete, truncated, completenessStatus, chainCompletenessModifier };
}

/** REMEDIATION #2 — freshness classification, independent per dimension. */
function classifyFreshness(ageMinutes) {
  if (ageMinutes == null) return "UNKNOWN";
  if (ageMinutes <= FRESH_THRESHOLD_MINUTES) return "FRESH";
  if (ageMinutes <= DELAYED_THRESHOLD_MINUTES) return "DELAYED";
  return "STALE";
}
function freshnessModifierFor(status) {
  if (status === "FRESH") return FRESHNESS_MODIFIER_FRESH;
  if (status === "DELAYED") return FRESHNESS_MODIFIER_DELAYED;
  if (status === "STALE") return FRESHNESS_MODIFIER_STALE;
  return FRESHNESS_MODIFIER_UNKNOWN;
}
/** Overall Gamma freshness = the WORSE of spot and options dimensions. */
function combineFreshness(spotStatus, optionsStatus) {
  const rank = { FRESH: 0, DELAYED: 1, UNKNOWN: 2, STALE: 3 };
  return rank[optionsStatus] >= rank[spotStatus] ? optionsStatus : spotStatus;
}

/**
 * REMEDIATION #3 — deterministic Gamma health state machine. Fixed
 * precedence, first match wins: UNAVAILABLE > INVALID > STALE >
 * PARTIAL_CHAIN > UNKNOWN_COMPLETENESS > LOW_CONFIDENCE > DELAYED > VALID.
 * Returns { status, reasons }.
 */
function computeGammaStatus(args) {
  const {
    valid, unavailableReason, gammaRegime, gammaFreshnessStatus, optionsFreshnessStatus,
    spotFreshnessStatus, completenessStatus, upstreamPaginationObserved,
    confidenceScore, minConfidence,
  } = args;
  const minConf = minConfidence == null ? MIN_CONFIDENCE : minConfidence;
  const reasons = [];

  if (!valid) {
    reasons.push(unavailableReason || "UNAVAILABLE");
    return { status: GAMMA_STATUS.UNAVAILABLE, reasons };
  }
  if (gammaRegime === "UNKNOWN") {
    reasons.push("GAMMA_REGIME_UNKNOWN");
    return { status: GAMMA_STATUS.INVALID, reasons };
  }
  if (gammaFreshnessStatus === "STALE") {
    reasons.push(optionsFreshnessStatus === "STALE" ? "OPTIONS_DATA_STALE" : "SPOT_DATA_STALE");
    return { status: GAMMA_STATUS.STALE, reasons };
  }
  if (completenessStatus === "TRUNCATED") {
    reasons.push("OPTIONS_CHAIN_TRUNCATED", "PAGE_LIMIT_REACHED");
    if (optionsFreshnessStatus === "UNKNOWN") reasons.push("OPTIONS_FRESHNESS_UNKNOWN");
    return { status: GAMMA_STATUS.DEGRADED_PARTIAL_CHAIN, reasons };
  }
  if (completenessStatus === "UNKNOWN") {
    reasons.push("CHAIN_COMPLETENESS_UNKNOWN");
    if (!upstreamPaginationObserved) reasons.push("UPSTREAM_PAGINATION_UNOBSERVED");
    return { status: GAMMA_STATUS.DEGRADED_UNKNOWN_COMPLETENESS, reasons };
  }
  if (confidenceScore < minConf) {
    reasons.push("CONFIDENCE_BELOW_THRESHOLD_" + minConf);
    return { status: GAMMA_STATUS.LOW_CONFIDENCE, reasons };
  }
  if (gammaFreshnessStatus === "DELAYED" || gammaFreshnessStatus === "UNKNOWN") {
    reasons.push(optionsFreshnessStatus !== "FRESH" ? "OPTIONS_DATA_DELAYED_OR_UNKNOWN" : "SPOT_DATA_DELAYED_OR_UNKNOWN");
    return { status: GAMMA_STATUS.DELAYED, reasons };
  }
  return { status: GAMMA_STATUS.VALID, reasons: [] };
}

module.exports = {
  GAMMA_STATUS, PAGE_LIMIT,
  COMPLETENESS_MODIFIER_COMPLETE, COMPLETENESS_MODIFIER_UNKNOWN, COMPLETENESS_MODIFIER_TRUNCATED,
  DOCUMENTED_DELAY_MINUTES, FRESH_THRESHOLD_MINUTES, DELAYED_THRESHOLD_MINUTES,
  FRESHNESS_MODIFIER_FRESH, FRESHNESS_MODIFIER_DELAYED, FRESHNESS_MODIFIER_UNKNOWN, FRESHNESS_MODIFIER_STALE,
  MIN_CONFIDENCE,
  classifyCompleteness, classifyFreshness, freshnessModifierFor, combineFreshness, computeGammaStatus,
};
