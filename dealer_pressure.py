"""
Dealer-hedging pressure estimate (MODELED, derived from the gamma regime).

All outputs here are labeled ESTIMATED / MODELED / PROBABLE per section 18
of the spec — never presented as observed dealer behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.enums import GammaRegime


@dataclass
class DealerPressureEstimate:
    dealer_pressure: str
    expected_behavior: str
    acceleration_risk: str
    pinning_probability_estimate: float  # 0-1, MODELED


def estimate_dealer_pressure(
    regime: GammaRegime,
    gamma_gauge: float,
    spot: float,
    gamma_flip: Optional[float],
    concentration_near_spot: float,
) -> DealerPressureEstimate:
    if regime == GammaRegime.POSITIVE:
        dealer_pressure = "MODELED_STABILIZING"
        expected_behavior = "MODELED_SELL_RIPS_BUY_DIPS"
        acceleration_risk = "LOW" if abs(gamma_gauge) > 50 else "MODERATE"
    elif regime == GammaRegime.NEGATIVE:
        dealer_pressure = "MODELED_DESTABILIZING"
        expected_behavior = "MODELED_BUY_RIPS_SELL_DIPS"
        acceleration_risk = "HIGH" if abs(gamma_gauge) > 50 else "MODERATE"
    elif regime == GammaRegime.TRANSITION:
        dealer_pressure = "MODELED_MIXED_HEDGING_RESPONSE"
        expected_behavior = "MODELED_UNSTABLE_REGIME"
        acceleration_risk = "ELEVATED_UNCERTAINTY"
    else:
        dealer_pressure = "MODELED_UNKNOWN"
        expected_behavior = "INSUFFICIENT_DATA"
        acceleration_risk = "UNKNOWN"

    # Pinning probability estimate: higher when in a positive-gamma regime
    # with strong concentration of open interest/gamma near current spot.
    # Purely a heuristic combination, not a calibrated probability.
    base = 0.5 if regime == GammaRegime.POSITIVE else 0.15
    pinning = min(1.0, max(0.0, base + 0.4 * concentration_near_spot))

    return DealerPressureEstimate(
        dealer_pressure=dealer_pressure,
        expected_behavior=expected_behavior,
        acceleration_risk=acceleration_risk,
        pinning_probability_estimate=round(pinning, 3),
    )
