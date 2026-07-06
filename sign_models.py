"""
Dealer-sign models (MODELED INFERENCE — never OBSERVED fact).

Public options-chain data does not reveal actual dealer inventory. Every
sign produced here is a documented assumption, not a measurement. Callers
must propagate the resulting confidence score and reason codes to the
final output so consumers understand the epistemic status of any
downstream GEX sign.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.core.enums import ConfidenceReasonCode, OptionType, SignModel


def apply_naive_convention(df: pd.DataFrame) -> pd.Series:
    """MODEL 1 — NAIVE_CONVENTION.

    Assumption (explicitly modeled, not observed): dealers are net short
    calls and net short puts against customer long option buying, so
    dealer gamma is treated as +1 for calls and -1 for puts. This is the
    conventional retail "dealer GEX" heuristic used throughout the
    industry; it is frequently wrong for specific strikes/expirations
    where institutional flow reverses the typical customer positioning.
    """
    sign = np.where(df["option_type"] == OptionType.CALL.value, 1.0, -1.0)
    return pd.Series(sign, index=df.index)


def apply_unsigned_gamma(df: pd.DataFrame) -> pd.Series:
    """MODEL 2 — UNSIGNED_GAMMA. No directional claim; magnitude only."""
    return pd.Series(np.ones(len(df)), index=df.index)


def apply_custom_positioning(
    df: pd.DataFrame, coefficients: Dict[Tuple[str, str, float, str], float]
) -> pd.Series:
    """MODEL 3 — CUSTOM_POSITIONING.

    coefficients keys: (underlying_symbol, option_type, strike, expiration_iso)
    -> sign coefficient (can be any real number, typically in [-1, 1]).
    Missing entries default to 0.0 (no contribution) rather than guessing.

    Implementation note: this is vectorized over columns (zip) rather
    than using df.iterrows(), which is dramatically faster for large
    chains and is called once per spot-shock grid point. Behavior is
    identical to a row-by-row dict lookup -- only the implementation
    changed, not the model's semantics.
    """
    if df.empty:
        return pd.Series([], index=df.index, dtype=float)

    expirations_iso = pd.to_datetime(df["expiration"]).map(lambda ts: ts.isoformat())
    keys = zip(df["underlying_symbol"], df["option_type"], df["strike"].astype(float), expirations_iso)
    signs = [coefficients.get(key, 0.0) for key in keys]
    return pd.Series(signs, index=df.index)


def apply_heuristic_positioning(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MODEL 4 — HEURISTIC_POSITIONING.

    Produces (sign_estimate, confidence [0-1], reason_codes) per row using
    only information already present in the normalized chain: option
    type, moneyness, and a volume/open-interest ratio as a very rough
    proxy for whether a day's volume looks like fresh opening activity
    (high volume relative to existing OI) versus closing/rolling activity.

    This is NEVER presented as observed dealer behavior. Confidence is
    deliberately capped below 1.0 for every row.
    """
    base_sign = np.where(df["option_type"] == OptionType.CALL.value, 1.0, -1.0)

    moneyness = df["underlying_spot"] / df["strike"].replace(0, np.nan)
    is_call = df["option_type"] == OptionType.CALL.value
    otm_call = is_call & (moneyness < 1.0)
    otm_put = (~is_call) & (moneyness > 1.0)
    otm_mask = (otm_call | otm_put).fillna(False)

    oi_safe = df["open_interest"].replace(0, np.nan)
    vol_oi_ratio = (df["volume"] / oi_safe).fillna(0.0)
    high_fresh_activity = vol_oi_ratio > 0.5

    # Heuristic: OTM options with heavy fresh volume are more likely to be
    # freshly opened, which somewhat increases confidence in the naive
    # customer-buy-to-open assumption underlying base_sign. This is a
    # weak, explicitly documented heuristic, not a claim of certainty.
    confidence = np.full(len(df), 0.35)
    confidence = np.where(otm_mask, confidence + 0.15, confidence)
    confidence = np.where(high_fresh_activity, confidence + 0.15, confidence)
    confidence = np.clip(confidence, 0.1, 0.75)

    reason_codes = []
    for otm, fresh in zip(otm_mask, high_fresh_activity):
        codes = [ConfidenceReasonCode.HEURISTIC_SIGN_MODEL.value]
        if otm:
            codes.append("OTM_MONEYNESS_SIGNAL")
        if fresh:
            codes.append("HIGH_VOLUME_OI_RATIO")
        reason_codes.append(codes)

    return (
        pd.Series(base_sign, index=df.index),
        pd.Series(confidence, index=df.index),
        pd.Series(reason_codes, index=df.index),
    )


def compute_dealer_sign(
    df: pd.DataFrame,
    sign_model: SignModel,
    custom_coefficients: Optional[Dict[Tuple[str, str, float, str], float]] = None,
) -> Tuple[pd.Series, pd.Series, List[str]]:
    """Dispatch to the requested sign model.

    Returns (sign_series, confidence_series [0-1], global_reason_codes).
    """
    if sign_model == SignModel.NAIVE_CONVENTION:
        sign = apply_naive_convention(df)
        confidence = pd.Series(np.full(len(df), 0.5), index=df.index)
        return sign, confidence, [ConfidenceReasonCode.HEURISTIC_SIGN_MODEL.value]

    if sign_model == SignModel.UNSIGNED_GAMMA:
        sign = apply_unsigned_gamma(df)
        confidence = pd.Series(np.ones(len(df)), index=df.index)
        return sign, confidence, []

    if sign_model == SignModel.CUSTOM_POSITIONING:
        sign = apply_custom_positioning(df, custom_coefficients or {})
        confidence = pd.Series(np.where(sign.abs() > 0, 0.9, 0.0), index=df.index)
        return sign, confidence, []

    if sign_model == SignModel.HEURISTIC_POSITIONING:
        sign, confidence, reasons_per_row = apply_heuristic_positioning(df)
        flat_reasons = sorted({code for codes in reasons_per_row for code in codes})
        return sign, confidence, flat_reasons

    raise ValueError(f"Unknown sign model: {sign_model}")
