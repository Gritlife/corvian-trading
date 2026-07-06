"""
Contract-level gamma computation.

Converts a DataFrame of NormalizedOptionContract rows into a DataFrame
with gamma_per_share (DERIVED), position_gamma_per_dollar (DERIVED),
gex_usd_per_1pct_move (DERIVED, unsigned magnitude), and, once a sign
model is applied, signed_gex_usd_per_1pct_move (MODELED).
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import pandas as pd

from app.core.config import settings
from app.core.enums import SignModel
from app.models.contract import NormalizedOptionContract
from app.quant.black_scholes import black_scholes_gamma
from app.quant.gex import gex_usd_per_1pct_move, gex_usd_per_1usd_move, position_gamma_per_dollar
from app.quant.sign_models import compute_dealer_sign


def contracts_to_dataframe(contracts: list[NormalizedOptionContract]) -> pd.DataFrame:
    rows = []
    for c in contracts:
        rows.append(
            {
                "underlying_symbol": c.underlying_symbol,
                "option_symbol": c.option_symbol,
                "option_type": c.option_type.value,
                "strike": c.strike,
                "expiration": c.expiration,
                "quote_timestamp": c.quote_timestamp,
                "underlying_spot": c.underlying_spot,
                "open_interest": c.open_interest,
                "volume": c.volume,
                "implied_volatility_effective": c.implied_volatility_effective,
                "implied_volatility_observed": c.implied_volatility_observed,
                "risk_free_rate": c.risk_free_rate,
                "dividend_yield": c.dividend_yield,
                "time_to_expiration_years": c.time_to_expiration_years,
                "is_rejected": c.is_rejected,
                "data_source": c.data_source,
            }
        )
    return pd.DataFrame(rows)


def compute_contract_gamma(
    df: pd.DataFrame,
    contract_multiplier: int = settings.contract_multiplier,
    spot_override: Optional[float] = None,
) -> pd.DataFrame:
    """Adds DERIVED gamma/GEX columns to a contract dataframe.

    If spot_override is provided, all contracts are repriced at that
    hypothetical spot (used by the spot-shock grid) while keeping strike,
    IV, T, r, q fixed — a standard "shock the spot, hold vol/time fixed"
    approximation.
    """
    out = df.copy()
    spot = spot_override if spot_override is not None else out["underlying_spot"]

    out["gamma_per_share"] = black_scholes_gamma(
        spot=spot,
        strike=out["strike"].values,
        time_to_expiration_years=out["time_to_expiration_years"].values,
        sigma=out["implied_volatility_effective"].values,
        risk_free_rate=out["risk_free_rate"].values,
        dividend_yield=out["dividend_yield"].values,
    )

    spot_arr = spot if hasattr(spot, "__len__") else pd.Series([spot] * len(out), index=out.index)

    out["position_gamma_per_dollar"] = position_gamma_per_dollar(
        out["gamma_per_share"].values, out["open_interest"].values, contract_multiplier
    )
    out["gex_usd_per_1pct_move"] = gex_usd_per_1pct_move(
        out["gamma_per_share"].values, out["open_interest"].values, contract_multiplier, spot_arr
    )
    out["gex_usd_per_1usd_move"] = gex_usd_per_1usd_move(
        out["gamma_per_share"].values, out["open_interest"].values, contract_multiplier, spot_arr
    )
    return out


def apply_sign_and_signed_gex(
    df: pd.DataFrame,
    sign_model: SignModel,
    custom_coefficients: Optional[Dict[Tuple[str, str, float, str], float]] = None,
) -> Tuple[pd.DataFrame, float]:
    """Applies a dealer-sign model and adds signed GEX columns.

    Returns (dataframe_with_sign_columns, mean_sign_confidence).
    """
    out = df.copy()
    sign, confidence, _reasons = compute_dealer_sign(out, sign_model, custom_coefficients)
    out["dealer_sign"] = sign.values
    out["sign_confidence"] = confidence.values
    out["signed_gex_usd_per_1pct_move"] = out["gex_usd_per_1pct_move"] * out["dealer_sign"]
    mean_confidence = float(confidence.mean()) if len(confidence) else 0.0
    return out, mean_confidence
