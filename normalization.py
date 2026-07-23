"""
Normalization and validation layer.

Converts RawOptionContract -> NormalizedOptionContract, tagging every
data-quality issue instead of silently dropping rows. Contracts that are
fundamentally unusable (e.g. expired, non-finite core fields, duplicate)
are marked is_rejected=True with rejection_reasons, but are still returned
so callers can audit what was excluded and why.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, List, Tuple

from app.core.config import settings
from app.core.enums import DataQualityFlag
from app.models.contract import NormalizedOptionContract, RawOptionContract


def _year_fraction(expiration: datetime, as_of: datetime) -> float:
    delta = expiration - as_of
    seconds = delta.total_seconds()
    years = seconds / (365.0 * 24.0 * 3600.0)
    return years


def normalize_contract(
    raw: RawOptionContract, as_of: datetime | None = None
) -> NormalizedOptionContract:
    if as_of is None:
        as_of = raw.quote_timestamp

    flags: List[DataQualityFlag] = list(raw.data_quality_flags)
    rejection_reasons: List[str] = []
    is_rejected = False

    # --- Spot ---
    spot = raw.underlying_spot
    if spot is None or spot <= 0 or not math.isfinite(spot):
        flags.append(DataQualityFlag.MISSING_SPOT)
        rejection_reasons.append("missing_or_invalid_spot")
        is_rejected = True
        spot = spot if (spot is not None and math.isfinite(spot)) else 0.0

    # --- Strike sanity ---
    if raw.strike is None or raw.strike <= 0 or not math.isfinite(raw.strike):
        flags.append(DataQualityFlag.IMPOSSIBLE_STRIKE)
        rejection_reasons.append("impossible_strike")
        is_rejected = True

    # --- OI / Volume ---
    oi = raw.open_interest if raw.open_interest is not None else 0.0
    if oi < 0:
        flags.append(DataQualityFlag.NEGATIVE_OI)
        rejection_reasons.append("negative_open_interest")
        is_rejected = True
        oi = 0.0

    vol = raw.volume if raw.volume is not None else 0.0
    if vol < 0:
        flags.append(DataQualityFlag.NEGATIVE_VOLUME)
        rejection_reasons.append("negative_volume")
        is_rejected = True
        vol = 0.0

    # --- Crossed market ---
    if raw.bid is not None and raw.ask is not None and raw.bid > raw.ask:
        flags.append(DataQualityFlag.CROSSED_MARKET)
        rejection_reasons.append("crossed_market")

    midpoint = raw.compute_midpoint()

    # --- Time to expiration ---
    t_years_raw = _year_fraction(raw.expiration, as_of)
    if t_years_raw <= 0:
        flags.append(DataQualityFlag.EXPIRED_CONTRACT)
        rejection_reasons.append("expired_contract")
        is_rejected = True

    if t_years_raw <= 0:
        flags.append(DataQualityFlag.ZERO_TIME)

    t_years_effective = max(t_years_raw, settings.min_time_to_expiration_years)

    # --- Implied volatility ---
    iv_observed = raw.implied_volatility
    if iv_observed is None or not math.isfinite(iv_observed):
        flags.append(DataQualityFlag.MISSING_IV)
        iv_effective = settings.min_implied_vol
    else:
        if iv_observed <= 0:
            flags.append(DataQualityFlag.MISSING_IV)
            iv_effective = settings.min_implied_vol
        elif iv_observed > settings.max_implied_vol:
            flags.append(DataQualityFlag.EXTREME_IV)
            iv_effective = settings.max_implied_vol
        else:
            iv_effective = max(iv_observed, settings.min_implied_vol)

    # --- Staleness ---
    age_seconds = (as_of - raw.quote_timestamp).total_seconds()
    if age_seconds > settings.stale_quote_seconds:
        flags.append(DataQualityFlag.STALE_QUOTE)

    # --- Finite check across numeric observed fields ---
    if not raw.is_finite():
        flags.append(DataQualityFlag.NON_FINITE_VALUE)
        rejection_reasons.append("non_finite_observed_value")
        is_rejected = True

    return NormalizedOptionContract(
        underlying_symbol=raw.underlying_symbol,
        option_symbol=raw.option_symbol,
        option_type=raw.option_type,
        strike=raw.strike,
        expiration=raw.expiration,
        quote_timestamp=raw.quote_timestamp,
        underlying_spot=spot,
        bid=raw.bid,
        ask=raw.ask,
        last_price=raw.last_price,
        midpoint=midpoint,
        volume=vol,
        open_interest=oi,
        implied_volatility_observed=iv_observed,
        implied_volatility_effective=iv_effective,
        vendor_delta=raw.vendor_delta,
        vendor_gamma=raw.vendor_gamma,
        vendor_theta=raw.vendor_theta,
        vendor_vega=raw.vendor_vega,
        risk_free_rate=raw.risk_free_rate,
        dividend_yield=raw.dividend_yield,
        time_to_expiration_years=t_years_effective,
        data_source=raw.data_source,
        data_quality_flags=sorted(set(flags), key=lambda f: f.value),
        is_rejected=is_rejected,
        rejection_reasons=rejection_reasons,
    )


def normalize_chain(
    raw_contracts: List[RawOptionContract], as_of: datetime | None = None
) -> Tuple[List[NormalizedOptionContract], Dict[str, int]]:
    """Normalize a full chain and detect duplicates.

    Returns (normalized_contracts, stats) where stats summarizes
    accepted/rejected/duplicate counts for confidence scoring.
    """
    seen: Dict[Tuple[str, str, float, datetime], NormalizedOptionContract] = {}
    duplicates = 0

    for raw in raw_contracts:
        normalized = normalize_contract(raw, as_of=as_of)
        key = (
            normalized.underlying_symbol,
            normalized.option_type.value,
            normalized.strike,
            normalized.expiration,
        )
        if key in seen:
            duplicates += 1
            existing = seen[key]
            existing.data_quality_flags = sorted(
                set(existing.data_quality_flags) | {DataQualityFlag.DUPLICATE_CONTRACT},
                key=lambda f: f.value,
            )
            # keep the most recent quote
            if normalized.quote_timestamp >= existing.quote_timestamp:
                seen[key] = normalized
                normalized.data_quality_flags = sorted(
                    set(normalized.data_quality_flags) | {DataQualityFlag.DUPLICATE_CONTRACT},
                    key=lambda f: f.value,
                )
        else:
            seen[key] = normalized

    result = list(seen.values())
    stats = {
        "total_raw": len(raw_contracts),
        "total_normalized": len(result),
        "rejected": sum(1 for c in result if c.is_rejected),
        "accepted": sum(1 for c in result if not c.is_rejected),
        "duplicates": duplicates,
    }
    return result, stats
