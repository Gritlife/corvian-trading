"""
Individual underlying gamma engine (section 16 of the spec).

Runs the same core analysis as the SPX foundation, then layers on
dealer-pressure / expected-behavior / pinning / acceleration-risk
estimates that are specific to single-name underlyings.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.core.enums import SignModel
from app.models.results import GammaAnalysisResult
from app.providers.base import OptionsDataProvider
from app.services.dealer_pressure import DealerPressureEstimate, estimate_dealer_pressure
from app.services.gamma_analysis import run_gamma_analysis


@dataclass
class AssetGammaResult:
    analysis: GammaAnalysisResult
    dealer_pressure: DealerPressureEstimate


def build_asset_gamma(
    provider: OptionsDataProvider,
    symbol: str,
    sign_model: SignModel = SignModel.NAIVE_CONVENTION,
    spot_range_pct: Optional[float] = None,
    spot_step_pct: Optional[float] = None,
    top_n: Optional[int] = None,
    as_of: Optional[datetime] = None,
) -> AssetGammaResult:
    analysis = run_gamma_analysis(
        provider=provider,
        symbol=symbol,
        sign_model=sign_model,
        spot_range_pct=spot_range_pct,
        spot_step_pct=spot_step_pct,
        top_n=top_n,
        as_of=as_of,
    )

    total_abs = analysis.total_absolute_gex or 1.0
    near_spot_gex = sum(
        r["absolute_gex"]
        for r in analysis.strike_df_records
        if analysis.spot * 0.98 <= r["strike"] <= analysis.spot * 1.02
    )
    concentration = near_spot_gex / total_abs

    pressure = estimate_dealer_pressure(
        regime=analysis.gamma_regime,
        gamma_gauge=analysis.gamma_gauge,
        spot=analysis.spot,
        gamma_flip=analysis.gamma_flip,
        concentration_near_spot=concentration,
    )

    return AssetGammaResult(analysis=analysis, dealer_pressure=pressure)
