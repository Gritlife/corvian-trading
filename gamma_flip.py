"""
Gamma Flip / zero-gamma level estimation (DERIVED from a MODELED spot-shock
profile).

The flip is estimated from linear interpolation of sign changes in
total_net_gex across the spot-shock grid — never from "the strike whose
GEX happens to be closest to zero" at current spot, which is a common but
mathematically weak shortcut.

If no sign change exists in the grid, the engine returns null rather than
fabricating a flip. If multiple crossings exist, all are returned along
with a documented rule for selecting the "primary" one: the crossing
nearest to current spot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from app.core.enums import ConfidenceReasonCode
from app.quant.spot_shock import SpotShockPoint


@dataclass
class GammaCrossing:
    spot_level: float
    left_spot: float
    right_spot: float
    left_net_gex: float
    right_net_gex: float


@dataclass
class GammaFlipResult:
    primary_gamma_flip: Optional[float]
    all_gamma_crossings: List[GammaCrossing]
    interpolation_method: str
    confidence: float
    calculation_timestamp: datetime
    sign_model: str
    reason_codes: List[str]


def estimate_gamma_flip(
    profile: List[SpotShockPoint], current_spot: float, sign_model: str
) -> GammaFlipResult:
    crossings: List[GammaCrossing] = []

    sorted_profile = sorted(profile, key=lambda p: p.hypothetical_spot)

    for i in range(len(sorted_profile) - 1):
        left = sorted_profile[i]
        right = sorted_profile[i + 1]
        left_val = left.total_net_gex
        right_val = right.total_net_gex

        if left_val == 0.0:
            crossings.append(
                GammaCrossing(
                    spot_level=left.hypothetical_spot,
                    left_spot=left.hypothetical_spot,
                    right_spot=left.hypothetical_spot,
                    left_net_gex=left_val,
                    right_net_gex=left_val,
                )
            )
            continue

        sign_change = (left_val < 0.0) != (right_val < 0.0)
        if sign_change and (right.hypothetical_spot != left.hypothetical_spot):
            # Linear interpolation for the zero crossing.
            fraction = (0.0 - left_val) / (right_val - left_val)
            spot_level = left.hypothetical_spot + fraction * (right.hypothetical_spot - left.hypothetical_spot)
            crossings.append(
                GammaCrossing(
                    spot_level=float(spot_level),
                    left_spot=left.hypothetical_spot,
                    right_spot=right.hypothetical_spot,
                    left_net_gex=left_val,
                    right_net_gex=right_val,
                )
            )

    reason_codes: List[str] = []
    now = datetime.now(timezone.utc)

    if not crossings:
        return GammaFlipResult(
            primary_gamma_flip=None,
            all_gamma_crossings=[],
            interpolation_method="linear_zero_crossing_on_spot_shock_grid",
            confidence=0.0,
            calculation_timestamp=now,
            sign_model=sign_model,
            reason_codes=[ConfidenceReasonCode.NO_GAMMA_CROSSING.value],
        )

    # Documented primary-crossing rule: nearest crossing to current spot.
    primary = min(crossings, key=lambda c: abs(c.spot_level - current_spot))

    confidence = 0.85
    if len(crossings) > 1:
        reason_codes.append(ConfidenceReasonCode.MULTIPLE_GAMMA_CROSSINGS.value)
        confidence = 0.6

    return GammaFlipResult(
        primary_gamma_flip=primary.spot_level,
        all_gamma_crossings=crossings,
        interpolation_method="linear_zero_crossing_on_spot_shock_grid",
        confidence=confidence,
        calculation_timestamp=now,
        sign_model=sign_model,
        reason_codes=reason_codes,
    )
