"""
SPX Market Foundation service (section 15 of the spec).

Wraps run_gamma_analysis with SPX-specific output shaping: regime
classification uses aggregate modeled gamma and flip proximity (never a
single strike), and the payload includes the strike histogram and
expiration dataset required for the MTS-V30 TV visual.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.enums import SignModel
from app.models.results import GammaAnalysisResult
from app.providers.base import OptionsDataProvider
from app.services.gamma_analysis import run_gamma_analysis
from app.tv.histogram import build_histogram


@dataclass
class SpxFoundationResult:
    analysis: GammaAnalysisResult
    histogram: List[Dict[str, Any]]


def build_spx_foundation(
    provider: OptionsDataProvider,
    sign_model: SignModel = SignModel.NAIVE_CONVENTION,
    spot_range_pct: Optional[float] = None,
    spot_step_pct: Optional[float] = None,
    top_n: Optional[int] = None,
    as_of: Optional[datetime] = None,
) -> SpxFoundationResult:
    analysis = run_gamma_analysis(
        provider=provider,
        symbol="SPX",
        sign_model=sign_model,
        spot_range_pct=spot_range_pct,
        spot_step_pct=spot_step_pct,
        top_n=top_n,
        as_of=as_of,
    )
    histogram = build_histogram(analysis.strike_df_records, analysis.spot)
    return SpxFoundationResult(analysis=analysis, histogram=histogram)
