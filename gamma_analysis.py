"""
Main orchestration service: raw provider data -> full GammaAnalysisResult.

This is the single place that wires together normalization, gamma math,
sign models, aggregation, spot-shock, gamma-flip, key levels, the gauge,
and confidence scoring. API routes and the CLI both call into this
module so behavior is identical across execution modes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.enums import DataStatus, GammaRegime, SignModel
from app.models.results import GammaAnalysisResult, GammaLevelOut
from app.providers.base import OptionsDataProvider
from app.quant.confidence import compute_confidence
from app.quant.gamma import apply_sign_and_signed_gex, compute_contract_gamma, contracts_to_dataframe
from app.quant.gamma_flip import estimate_gamma_flip
from app.quant.gamma_gauge import compute_gamma_gauge, compute_local_gamma_slope
from app.quant.gamma_levels import compute_key_levels
from app.services.aggregation import aggregate_by_expiration, aggregate_by_strike
from app.services.normalization import normalize_chain
from app.quant.spot_shock import compute_spot_shock_profile


def _level_to_out(level) -> Optional[GammaLevelOut]:
    if level is None:
        return None
    return GammaLevelOut(
        strike=level.strike,
        net_gex=level.net_gex,
        absolute_gex=level.absolute_gex,
        label=level.label,
        distance_from_spot=level.distance_from_spot,
        distance_from_spot_pct=level.distance_from_spot_pct,
    )


def classify_regime(net_gex: float, total_absolute_gex: float, spot: float, gamma_flip: Optional[float]) -> GammaRegime:
    """Classifies regime from AGGREGATE modeled gamma and proximity to the
    gamma flip — never from a single arbitrary strike.
    """
    if total_absolute_gex <= 0:
        return GammaRegime.UNKNOWN

    ratio = net_gex / total_absolute_gex

    if gamma_flip is not None and spot > 0:
        distance_pct = abs(spot - gamma_flip) / spot
        if distance_pct < 0.0025:  # within ~0.25% of the flip: treat as transitional
            return GammaRegime.TRANSITION

    if ratio > 0.05:
        return GammaRegime.POSITIVE
    if ratio < -0.05:
        return GammaRegime.NEGATIVE
    return GammaRegime.TRANSITION


def run_gamma_analysis(
    provider: OptionsDataProvider,
    symbol: str,
    sign_model: SignModel = SignModel.NAIVE_CONVENTION,
    spot_range_pct: Optional[float] = None,
    spot_step_pct: Optional[float] = None,
    top_n: Optional[int] = None,
    as_of: Optional[datetime] = None,
    custom_coefficients: Optional[Dict[Tuple[str, str, float, str], float]] = None,
) -> GammaAnalysisResult:
    spot_range_pct = spot_range_pct if spot_range_pct is not None else settings.spot_shock_range_pct
    spot_step_pct = spot_step_pct if spot_step_pct is not None else settings.spot_shock_step_pct
    top_n = top_n if top_n is not None else settings.default_top_n

    raw_contracts = provider.get_option_chain(symbol)
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    normalized, norm_stats = normalize_chain(raw_contracts, as_of=as_of)
    usable = [c for c in normalized if not c.is_rejected]

    if not usable:
        raise ValueError(f"No usable contracts for symbol '{symbol}' after normalization.")

    spot = usable[0].underlying_spot

    df = contracts_to_dataframe(usable)
    priced = compute_contract_gamma(df, contract_multiplier=settings.contract_multiplier)
    signed, mean_sign_confidence = apply_sign_and_signed_gex(priced, sign_model, custom_coefficients)

    strike_df = aggregate_by_strike(signed)
    expiration_df = aggregate_by_expiration(signed, as_of=as_of)

    total_net_gex = float(signed["signed_gex_usd_per_1pct_move"].sum())
    total_absolute_gex = float(signed["gex_usd_per_1pct_move"].abs().sum())

    spot_shock_points = compute_spot_shock_profile(
        contracts_df=df,
        current_spot=spot,
        sign_model=sign_model,
        range_pct=spot_range_pct,
        step_pct=spot_step_pct,
        contract_multiplier=settings.contract_multiplier,
        custom_coefficients=custom_coefficients,
    )
    flip_result = estimate_gamma_flip(spot_shock_points, current_spot=spot, sign_model=sign_model.value)

    key_levels = compute_key_levels(strike_df, spot=spot, top_n=top_n)

    zero_dte_rows = expiration_df[expiration_df["is_0dte"]]
    zero_dte_net_gex = float(zero_dte_rows["net_gex"].sum()) if not zero_dte_rows.empty else 0.0
    zero_dte_absolute_gex = float(zero_dte_rows["absolute_gex"].sum()) if not zero_dte_rows.empty else 0.0
    zero_dte_pct = zero_dte_absolute_gex / total_absolute_gex if total_absolute_gex else 0.0
    non_zero_dte_absolute_gex = total_absolute_gex - zero_dte_absolute_gex

    near_spot_mask = (strike_df["strike"] >= spot * 0.98) & (strike_df["strike"] <= spot * 1.02)
    near_spot_absolute_gex = float(strike_df.loc[near_spot_mask, "absolute_gex"].sum()) if not strike_df.empty else 0.0

    spot_shock_records = [
        {
            "hypothetical_spot": p.hypothetical_spot,
            "total_call_gex": p.total_call_gex,
            "total_put_gex": p.total_put_gex,
            "total_net_gex": p.total_net_gex,
            "total_absolute_gex": p.total_absolute_gex,
        }
        for p in spot_shock_points
    ]

    local_gamma_slope = compute_local_gamma_slope(spot_shock_records, spot, total_absolute_gex)

    gauge_result = compute_gamma_gauge(
        net_gex=total_net_gex,
        total_absolute_gex=total_absolute_gex,
        spot=spot,
        gamma_flip=flip_result.primary_gamma_flip,
        zero_dte_absolute_gex=zero_dte_absolute_gex,
        near_spot_absolute_gex=near_spot_absolute_gex,
        sign_confidence=mean_sign_confidence,
        local_gamma_slope=local_gamma_slope,
    )

    regime = classify_regime(total_net_gex, total_absolute_gex, spot, flip_result.primary_gamma_flip)

    # --- Confidence scoring ---
    now = as_of
    ages = [(now - c.quote_timestamp).total_seconds() for c in usable]
    avg_age = float(np.mean(ages)) if ages else 0.0
    quote_freshness = max(0.0, 1.0 - avg_age / max(settings.stale_quote_seconds * 5, 1))

    iv_completeness = float(np.mean([c.implied_volatility_observed is not None for c in usable]))
    oi_completeness = float(np.mean([c.open_interest > 0 for c in usable]))
    chain_completeness = 1.0 if norm_stats["total_raw"] > 0 else 0.0
    spread_quality = float(
        np.mean(
            [
                1.0 if (c.bid is not None and c.ask is not None and c.ask >= c.bid) else 0.0
                for c in usable
            ]
        )
    )
    provider_quality = 1.0 if usable[0].data_source == "mock_synthetic" else 0.8
    expiration_coverage = 1.0 if not expiration_df.empty else 0.0

    extra_reasons = list(flip_result.reason_codes)
    if zero_dte_pct > 0.35:
        extra_reasons.append("HIGH_0DTE_SENSITIVITY")
    if sign_model == SignModel.HEURISTIC_POSITIONING:
        extra_reasons.append("HEURISTIC_SIGN_MODEL")

    confidence_result = compute_confidence(
        quote_freshness=quote_freshness,
        iv_completeness=iv_completeness,
        oi_completeness=oi_completeness,
        chain_completeness=chain_completeness,
        spread_quality=spread_quality,
        provider_quality=provider_quality,
        sign_model_certainty=mean_sign_confidence,
        expiration_coverage=expiration_coverage,
        extra_reason_codes=extra_reasons,
    )

    data_status = DataStatus.FRESH
    if quote_freshness < 0.3:
        data_status = DataStatus.STALE
    if norm_stats["rejected"] > 0 and norm_stats["accepted"] > 0:
        data_status = DataStatus.PARTIAL if data_status == DataStatus.FRESH else data_status
    if not usable:
        data_status = DataStatus.UNAVAILABLE

    top_positive = [_level_to_out(l) for l in key_levels["top_positive_levels"]]
    top_negative = [_level_to_out(l) for l in key_levels["top_negative_levels"]]
    key_levels_out = {
        k: _level_to_out(v)
        for k, v in key_levels.items()
        if k not in ("top_positive_levels", "top_negative_levels")
    }

    crossings_records = [
        {
            "spot_level": c.spot_level,
            "left_spot": c.left_spot,
            "right_spot": c.right_spot,
            "left_net_gex": c.left_net_gex,
            "right_net_gex": c.right_net_gex,
        }
        for c in flip_result.all_gamma_crossings
    ]

    strike_records = strike_df.assign(
        nearest_expiration=strike_df["nearest_expiration"].apply(lambda x: x.isoformat() if pd.notna(x) else None),
        dominant_expiration=strike_df["dominant_expiration"].apply(
            lambda x: x.isoformat() if pd.notna(x) else None
        ),
    ).to_dict(orient="records")

    expiration_records = expiration_df.assign(
        expiration=expiration_df["expiration"].apply(lambda x: pd.Timestamp(x).isoformat())
    ).to_dict(orient="records")

    snapshot_id = str(uuid.uuid4())
    calculation_timestamp = datetime.now(timezone.utc)
    source_data_timestamp = min((c.quote_timestamp for c in usable), default=as_of)

    return GammaAnalysisResult(
        symbol=symbol.upper(),
        spot=spot,
        timestamp_utc=as_of,
        sign_model=sign_model,
        snapshot_id=snapshot_id,
        calculation_timestamp=calculation_timestamp,
        source_data_timestamp=source_data_timestamp,
        strike_df_records=strike_records,
        expiration_df_records=expiration_records,
        spot_shock_profile=spot_shock_records,
        total_net_gex=total_net_gex,
        total_absolute_gex=total_absolute_gex,
        gamma_flip=flip_result.primary_gamma_flip,
        all_gamma_crossings=crossings_records,
        flip_interpolation_method=flip_result.interpolation_method,
        flip_confidence=flip_result.confidence,
        key_levels=key_levels_out,
        top_positive_levels=top_positive,
        top_negative_levels=top_negative,
        gamma_regime=regime,
        gamma_gauge=gauge_result.gamma_gauge,
        gauge_interpretation=gauge_result.interpretation,
        gauge_components=gauge_result.components,
        gamma_gauge_components=gauge_result.gamma_gauge_components,
        zero_dte_net_gex=zero_dte_net_gex,
        zero_dte_absolute_gex=zero_dte_absolute_gex,
        zero_dte_pct_of_total=zero_dte_pct,
        non_zero_dte_absolute_gex=non_zero_dte_absolute_gex,
        confidence_score=confidence_result.confidence_score,
        confidence_reason_codes=confidence_result.reason_codes,
        data_status=data_status,
        normalization_stats=norm_stats,
        provider_name=getattr(provider, "name", "unknown"),
        provider_status=getattr(getattr(provider, "status", None), "value", "UNKNOWN"),
    )
