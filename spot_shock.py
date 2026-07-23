"""
Spot-shock gamma profile (DERIVED, computed under a MODELED sign
convention).

Recomputes gamma/GEX at a grid of hypothetical spot prices around the
current spot, holding IV/T/r/q fixed for each contract. This profile is
the mandatory input to gamma-flip estimation (app.quant.gamma_flip) — the
engine never estimates a flip from a single strike or from current-spot
GEX alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.core.enums import SignModel
from app.quant.gamma import apply_sign_and_signed_gex, compute_contract_gamma


@dataclass
class SpotShockPoint:
    hypothetical_spot: float
    total_call_gex: float
    total_put_gex: float
    total_net_gex: float
    total_absolute_gex: float


def build_spot_grid(current_spot: float, range_pct: float, step_pct: float) -> np.ndarray:
    if current_spot <= 0:
        raise ValueError("current_spot must be positive")
    if step_pct <= 0:
        raise ValueError("step_pct must be positive")
    low = current_spot * (1.0 - range_pct)
    high = current_spot * (1.0 + range_pct)
    step = current_spot * step_pct
    n_steps = int(round((high - low) / step))
    grid = low + step * np.arange(n_steps + 1)
    # Ensure current spot is exactly represented for downstream lookups.
    grid = np.sort(np.unique(np.append(grid, current_spot)))
    return grid


def compute_spot_shock_profile(
    contracts_df: pd.DataFrame,
    current_spot: float,
    sign_model: SignModel,
    range_pct: float,
    step_pct: float,
    contract_multiplier: int,
    custom_coefficients: Optional[Dict[Tuple[str, str, float, str], float]] = None,
) -> List[SpotShockPoint]:
    grid = build_spot_grid(current_spot, range_pct, step_pct)
    points: List[SpotShockPoint] = []

    for hypothetical_spot in grid:
        priced = compute_contract_gamma(
            contracts_df, contract_multiplier=contract_multiplier, spot_override=float(hypothetical_spot)
        )
        signed, _conf = apply_sign_and_signed_gex(priced, sign_model, custom_coefficients)

        call_mask = signed["option_type"] == "CALL"
        put_mask = signed["option_type"] == "PUT"

        total_call_gex = float(signed.loc[call_mask, "signed_gex_usd_per_1pct_move"].sum())
        total_put_gex = float(signed.loc[put_mask, "signed_gex_usd_per_1pct_move"].sum())
        total_net_gex = total_call_gex + total_put_gex
        total_absolute_gex = float(signed["gex_usd_per_1pct_move"].abs().sum())

        points.append(
            SpotShockPoint(
                hypothetical_spot=float(hypothetical_spot),
                total_call_gex=total_call_gex,
                total_put_gex=total_put_gex,
                total_net_gex=total_net_gex,
                total_absolute_gex=total_absolute_gex,
            )
        )

    return points
