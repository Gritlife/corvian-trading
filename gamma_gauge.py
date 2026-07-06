"""
Gamma Gauge: normalized -100..+100 score (MODELED, built from DERIVED
inputs).

v0.1.1 change (section 18): the gauge is now an explicit additive
point-contribution decomposition, so `gamma_gauge_components` sums
(before clamping) to exactly the gauge score — fully auditable, not just
descriptive factors. Weights are documented and exposed via
GAUGE_WEIGHTS so they are inspectable/testable without re-deriving them
from the code.

    signed_ratio    = clamp(net_gex / max(|total_absolute_gex|, eps), -1, 1)
    flip_proximity  = 1 - clamp(|spot - gamma_flip| / (spot * flip_norm_pct), 0, 1)
                      (0 if no flip is available)
    concentration   = clamp(near_spot_absolute_gex / max(total_absolute_gex, eps), 0, 1)
    zero_dte_factor = clamp(zero_dte_absolute_gex / max(total_absolute_gex, eps), 0, 1)
    sign_confidence = clamp(mean dealer-sign confidence, 0, 1)
    slope_factor    = clamp(|local_gamma_slope|, 0, 1)   (normalized d(net_gex)/d(spot) near spot;
                                                            0.0 if the spot-shock profile is unavailable)

Point contributions (all in gauge points, i.e. already *100), computed as
signed_ratio times a fixed weight per factor -- this is what makes the
decomposition additive and auditable:

    signed_ratio_component         = W_BASE                 * signed_ratio * 100
    distance_to_flip_component     = W_FLIP_PROXIMITY        * signed_ratio * flip_proximity   * 100
    near_spot_concentration_component = W_CONCENTRATION      * signed_ratio * concentration     * 100
    confidence_adjustment          = W_SIGN_CONFIDENCE       * signed_ratio * sign_confidence    * 100
    zero_dte_component             = -W_ZERO_DTE             * signed_ratio * zero_dte_factor    * 100
    local_gamma_slope_component    = W_SLOPE                 * signed_ratio * slope_factor       * 100

    gamma_gauge = clamp(sum(all components above), -100, 100)

Interpretation bands:
    -100..-70 EXTREME NEGATIVE
    -69..-30  NEGATIVE
    -29..+29  TRANSITION / NEUTRAL
    +30..+69  POSITIVE
    +70..+100 EXTREME POSITIVE
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

EPSILON = 1e-9

# Documented, inspectable weights. Sum of positive weights = 0.90 (<=1.0
# headroom retained deliberately so clamping is rarely the binding
# constraint for a single dominant factor).
GAUGE_WEIGHTS: Dict[str, float] = {
    "signed_ratio_component": 0.50,
    "distance_to_flip_component": 0.15,
    "near_spot_concentration_component": 0.10,
    "confidence_adjustment": 0.10,
    "zero_dte_component": -0.10,
    "local_gamma_slope_component": 0.05,
}


@dataclass
class GammaGaugeResult:
    gamma_gauge: float
    interpretation: str
    components: Dict[str, float] = field(default_factory=dict)
    gamma_gauge_components: Dict[str, float] = field(default_factory=dict)


def _clamp(x: float, lo: float, hi: float) -> float:
    if math.isnan(x):
        return 0.0
    return max(lo, min(hi, x))


def interpret_gauge(score: float) -> str:
    if score <= -70:
        return "EXTREME_NEGATIVE"
    if score <= -30:
        return "NEGATIVE"
    if score < 30:
        return "TRANSITION_NEUTRAL"
    if score < 70:
        return "POSITIVE"
    return "EXTREME_POSITIVE"


def compute_local_gamma_slope(
    spot_shock_profile: Optional[List[dict]], spot: float, total_absolute_gex: float
) -> float:
    """Normalized, dimensionless local slope of net GEX around current
    spot, derived from the spot-shock profile (points with keys
    'hypothetical_spot' and 'total_net_gex'). Returns 0.0 if the profile
    is missing or too sparse to bracket spot. Clamped to [-1, 1] by the
    caller via slope_factor = |value|.
    """
    if not spot_shock_profile or spot <= 0 or total_absolute_gex <= 0:
        return 0.0

    sorted_profile = sorted(spot_shock_profile, key=lambda p: p["hypothetical_spot"])
    left = None
    right = None
    for i in range(len(sorted_profile) - 1):
        a, b = sorted_profile[i], sorted_profile[i + 1]
        if a["hypothetical_spot"] <= spot <= b["hypothetical_spot"]:
            left, right = a, b
            break
    if left is None or right is None or right["hypothetical_spot"] == left["hypothetical_spot"]:
        return 0.0

    d_gex = right["total_net_gex"] - left["total_net_gex"]
    d_spot = right["hypothetical_spot"] - left["hypothetical_spot"]
    raw_slope = d_gex / d_spot  # $ per $1 of spot

    # Normalize: a slope that would flip the entire absolute GEX base
    # over a 1% move in spot is treated as "maximal" (1.0).
    normalizer = total_absolute_gex / (spot * 0.01) if spot > 0 else EPSILON
    normalizer = max(normalizer, EPSILON)
    return raw_slope / normalizer


def compute_gamma_gauge(
    net_gex: float,
    total_absolute_gex: float,
    spot: float,
    gamma_flip: Optional[float],
    zero_dte_absolute_gex: float,
    near_spot_absolute_gex: float,
    sign_confidence: float,
    flip_norm_pct: float = 0.05,
    local_gamma_slope: float = 0.0,
) -> GammaGaugeResult:
    total_abs_safe = max(abs(total_absolute_gex), EPSILON)

    signed_ratio = _clamp(net_gex / total_abs_safe, -1.0, 1.0)

    if gamma_flip is not None and spot > 0:
        distance_pct = abs(spot - gamma_flip) / spot
        flip_proximity = 1.0 - _clamp(distance_pct / flip_norm_pct, 0.0, 1.0)
    else:
        flip_proximity = 0.0

    zero_dte_factor = _clamp(zero_dte_absolute_gex / total_abs_safe, 0.0, 1.0)
    concentration = _clamp(near_spot_absolute_gex / total_abs_safe, 0.0, 1.0)
    sign_conf = _clamp(sign_confidence, 0.0, 1.0)
    slope_factor = _clamp(abs(local_gamma_slope), 0.0, 1.0)

    gamma_gauge_components = {
        "signed_ratio_component": GAUGE_WEIGHTS["signed_ratio_component"] * signed_ratio * 100.0,
        "distance_to_flip_component": GAUGE_WEIGHTS["distance_to_flip_component"]
        * signed_ratio
        * flip_proximity
        * 100.0,
        "near_spot_concentration_component": GAUGE_WEIGHTS["near_spot_concentration_component"]
        * signed_ratio
        * concentration
        * 100.0,
        "confidence_adjustment": GAUGE_WEIGHTS["confidence_adjustment"] * signed_ratio * sign_conf * 100.0,
        "zero_dte_component": GAUGE_WEIGHTS["zero_dte_component"] * signed_ratio * zero_dte_factor * 100.0,
        "local_gamma_slope_component": GAUGE_WEIGHTS["local_gamma_slope_component"]
        * signed_ratio
        * slope_factor
        * 100.0,
    }

    raw_score = sum(gamma_gauge_components.values())
    gauge = _clamp(raw_score, -100.0, 100.0)
    if math.isinf(gauge):
        gauge = 100.0 if gauge > 0 else -100.0

    # Legacy/introspection factor dict (pre-weighting, in [0,1] or [-1,1]).
    components = {
        "signed_ratio": signed_ratio,
        "flip_proximity": flip_proximity,
        "zero_dte_factor": zero_dte_factor,
        "concentration": concentration,
        "sign_confidence": sign_conf,
        "slope_factor": slope_factor,
    }

    return GammaGaugeResult(
        gamma_gauge=gauge,
        interpretation=interpret_gauge(gauge),
        components=components,
        gamma_gauge_components={k: round(v, 6) for k, v in gamma_gauge_components.items()},
    )
