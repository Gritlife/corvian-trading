"""
Gamma Exposure (GEX) unit definitions.

CRITICAL: this module is the single source of truth for GEX unit
conventions. Every field name below carries explicit unit semantics.
Never rename or repurpose a field to mean a different unit.

Definitions
-----------
gamma_per_share (DERIVED):
    Black-Scholes gamma, i.e. d(delta)/d(spot) per single share of
    underlying, dimensionless-per-$1-of-spot.

position_gamma_per_dollar (DERIVED):
    gamma_per_share * open_interest * contract_multiplier
    Units: change in aggregate delta (shares) per $1 move in spot,
    for the full open-interest position.

gex_usd_per_1pct_move (DERIVED, the primary GEX convention used
throughout this engine):
    gamma_per_share * open_interest * contract_multiplier * spot^2 * 0.01
    Units: US dollars of notional delta change induced by a 1% move in
    the underlying. This is the standard "dealer GEX" convention used in
    most public gamma-exposure commentary.

gex_usd_per_1usd_move (DERIVED, alternative convention):
    gamma_per_share * open_interest * contract_multiplier * spot
    Units: US dollars of notional delta change induced by a $1 move in
    the underlying. Provided for completeness; NEVER conflated with the
    1%-move convention above. Any output using this convention is
    explicitly labeled with the "_1usd_" infix.
"""
from __future__ import annotations

import numpy as np


def position_gamma_per_dollar(
    gamma_per_share: np.ndarray, open_interest: np.ndarray, contract_multiplier: int
) -> np.ndarray:
    return np.asarray(gamma_per_share, dtype=float) * np.asarray(open_interest, dtype=float) * contract_multiplier


def gex_usd_per_1pct_move(
    gamma_per_share: np.ndarray,
    open_interest: np.ndarray,
    contract_multiplier: int,
    spot: np.ndarray,
) -> np.ndarray:
    g = np.asarray(gamma_per_share, dtype=float)
    oi = np.asarray(open_interest, dtype=float)
    s = np.asarray(spot, dtype=float)
    return g * oi * contract_multiplier * (s ** 2) * 0.01


def gex_usd_per_1usd_move(
    gamma_per_share: np.ndarray,
    open_interest: np.ndarray,
    contract_multiplier: int,
    spot: np.ndarray,
) -> np.ndarray:
    g = np.asarray(gamma_per_share, dtype=float)
    oi = np.asarray(open_interest, dtype=float)
    s = np.asarray(spot, dtype=float)
    return g * oi * contract_multiplier * s
