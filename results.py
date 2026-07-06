from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.enums import DataStatus, GammaRegime, SignModel


@dataclass
class GammaLevelOut:
    strike: float
    net_gex: float
    absolute_gex: float
    label: str
    distance_from_spot: float
    distance_from_spot_pct: float


@dataclass
class GammaAnalysisResult:
    symbol: str
    spot: float
    timestamp_utc: datetime
    sign_model: SignModel

    snapshot_id: str
    calculation_timestamp: datetime
    source_data_timestamp: datetime

    strike_df_records: List[Dict[str, Any]]
    expiration_df_records: List[Dict[str, Any]]
    spot_shock_profile: List[Dict[str, Any]]

    total_net_gex: float
    total_absolute_gex: float

    gamma_flip: Optional[float]
    all_gamma_crossings: List[Dict[str, Any]]
    flip_interpolation_method: str
    flip_confidence: float

    key_levels: Dict[str, Optional[GammaLevelOut]]
    top_positive_levels: List[GammaLevelOut]
    top_negative_levels: List[GammaLevelOut]

    gamma_regime: GammaRegime
    gamma_gauge: float
    gauge_interpretation: str
    gauge_components: Dict[str, float]
    gamma_gauge_components: Dict[str, float]

    zero_dte_net_gex: float
    zero_dte_absolute_gex: float
    zero_dte_pct_of_total: float
    non_zero_dte_absolute_gex: float

    confidence_score: float
    confidence_reason_codes: List[str]
    data_status: DataStatus

    normalization_stats: Dict[str, int]

    provider_name: str = "unknown"
    provider_status: str = "UNKNOWN"
