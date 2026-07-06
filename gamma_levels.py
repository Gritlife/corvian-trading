"""
Key gamma level identification (DERIVED from strike-level aggregation,
under a MODELED sign convention).

Explicitly avoids assuming high call-OI implies resistance or high put-OI
implies support — levels are labeled purely by their gamma magnitude/sign
role (wall, pit, largest absolute), not by a directional trading claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd


@dataclass
class GammaLevel:
    strike: float
    net_gex: float
    absolute_gex: float
    label: str
    distance_from_spot: float
    distance_from_spot_pct: float


def _make_level(row: pd.Series, spot: float, label: str) -> GammaLevel:
    strike = float(row["strike"])
    distance = strike - spot
    distance_pct = (distance / spot) if spot else 0.0
    return GammaLevel(
        strike=strike,
        net_gex=float(row["net_gex"]),
        absolute_gex=float(row["absolute_gex"]),
        label=label,
        distance_from_spot=distance,
        distance_from_spot_pct=distance_pct,
    )


def compute_key_levels(strike_df: pd.DataFrame, spot: float, top_n: int = 5) -> dict:
    """strike_df must contain columns: strike, net_gex, absolute_gex,
    positive_gex, negative_gex (all at current, unshocked spot).
    """
    if strike_df.empty:
        return {
            "largest_positive_gamma_strike": None,
            "largest_negative_gamma_strike": None,
            "largest_absolute_gamma_strike": None,
            "positive_gamma_wall": None,
            "negative_gamma_pit": None,
            "top_positive_levels": [],
            "top_negative_levels": [],
            "nearest_positive_level_above_spot": None,
            "nearest_negative_level_below_spot": None,
            "strongest_gamma_concentration_near_spot": None,
        }

    df = strike_df.sort_values("strike").reset_index(drop=True)

    pos_df = df[df["net_gex"] > 0]
    neg_df = df[df["net_gex"] < 0]

    largest_positive = pos_df.loc[pos_df["net_gex"].idxmax()] if not pos_df.empty else None
    largest_negative = neg_df.loc[neg_df["net_gex"].idxmin()] if not neg_df.empty else None
    largest_absolute_idx = df["absolute_gex"].idxmax()
    largest_absolute = df.loc[largest_absolute_idx]

    # "Wall" = strongest positive concentration; "pit" = strongest negative
    # concentration. These are magnitude-based labels, not directional
    # support/resistance claims.
    positive_wall = largest_positive
    negative_pit = largest_negative

    top_positive = pos_df.sort_values("net_gex", ascending=False).head(top_n)
    top_negative = neg_df.sort_values("net_gex", ascending=True).head(top_n)

    above = df[df["strike"] > spot]
    below = df[df["strike"] < spot]

    nearest_positive_above = None
    above_positive = above[above["net_gex"] > 0]
    if not above_positive.empty:
        nearest_positive_above = above_positive.iloc[(above_positive["strike"] - spot).abs().argsort().iloc[0]]

    nearest_negative_below = None
    below_negative = below[below["net_gex"] < 0]
    if not below_negative.empty:
        nearest_negative_below = below_negative.iloc[(spot - below_negative["strike"]).abs().argsort().iloc[0]]

    # Strongest concentration within +/- 2% of spot, by absolute gex.
    band = df[(df["strike"] >= spot * 0.98) & (df["strike"] <= spot * 1.02)]
    strongest_near_spot = band.loc[band["absolute_gex"].idxmax()] if not band.empty else None

    def opt(row: Optional[pd.Series], label: str) -> Optional[GammaLevel]:
        return _make_level(row, spot, label) if row is not None else None

    return {
        "largest_positive_gamma_strike": opt(largest_positive, "LARGEST_POSITIVE_GAMMA"),
        "largest_negative_gamma_strike": opt(largest_negative, "LARGEST_NEGATIVE_GAMMA"),
        "largest_absolute_gamma_strike": opt(largest_absolute, "LARGEST_ABSOLUTE_GAMMA"),
        "positive_gamma_wall": opt(positive_wall, "POSITIVE_GAMMA_WALL"),
        "negative_gamma_pit": opt(negative_pit, "NEGATIVE_GAMMA_PIT"),
        "top_positive_levels": [_make_level(r, spot, "TOP_POSITIVE") for _, r in top_positive.iterrows()],
        "top_negative_levels": [_make_level(r, spot, "TOP_NEGATIVE") for _, r in top_negative.iterrows()],
        "nearest_positive_level_above_spot": opt(nearest_positive_above, "NEAREST_POSITIVE_ABOVE"),
        "nearest_negative_level_below_spot": opt(nearest_negative_below, "NEAREST_NEGATIVE_BELOW"),
        "strongest_gamma_concentration_near_spot": opt(strongest_near_spot, "STRONGEST_NEAR_SPOT"),
    }
