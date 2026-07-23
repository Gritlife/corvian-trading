from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.core.enums import DataStatus, GammaRegime, SignModel


class HealthResponse(BaseModel):
    status: str
    engine_version: str
    active_provider: str


class GammaLevelSchema(BaseModel):
    strike: float
    net_gex: float
    absolute_gex: float
    label: str
    distance_from_spot: float
    distance_from_spot_pct: float


class GammaAnalyzeRequest(BaseModel):
    symbol: str
    sign_model: SignModel = SignModel.NAIVE_CONVENTION
    min_dte: Optional[float] = None
    max_dte: Optional[float] = None
    include_0dte: bool = True
    spot_range_pct: Optional[float] = None
    spot_step_pct: Optional[float] = None
    top_n: Optional[int] = None


class GammaCrossingSchema(BaseModel):
    spot_level: float
    left_spot: float
    right_spot: float
    left_net_gex: float
    right_net_gex: float


class HistogramBarSchema(BaseModel):
    strike: float
    net_gex_usd_per_1pct_move: float
    absolute_gex_usd_per_1pct_move: float
    normalized_bar: float
    side: str
    distance_from_spot: float
    distance_from_spot_pct: float
    rank_by_absolute_gex: int


class TopLevelSchema(BaseModel):
    strike: float
    net_gex: float
    label: str


class ZeroDteContributionSchema(BaseModel):
    net_gex: float
    absolute_gex: float
    pct_of_total: float


class ExpirationBucketSchema(BaseModel):
    count: int
    net_gex: float
    absolute_gex: float


class SPXMarketFoundationTVPayload(BaseModel):
    """Locked TV output schema for the SPX Market Foundation screen
    (section 15). schema_version and engine_version are fixed constants
    for this build, not free-form strings."""

    schema_version: str
    engine_version: str
    snapshot_id: str
    symbol: str
    timestamp_utc: str
    timestamp_et: str
    source_data_timestamp: str
    calculation_timestamp: str
    spot: float
    market_gamma_regime: GammaRegime
    gamma_gauge: float
    gamma_gauge_components: Dict[str, float]
    total_net_gex_usd_per_1pct_move: float
    total_absolute_gex_usd_per_1pct_move: float
    gamma_flip: Optional[float]
    all_gamma_crossings: List[GammaCrossingSchema]
    positive_gamma_wall: Optional[float]
    negative_gamma_pit: Optional[float]
    nearest_positive_level_above_spot: Optional[float]
    nearest_negative_level_below_spot: Optional[float]
    top_positive_levels: List[TopLevelSchema]
    top_negative_levels: List[TopLevelSchema]
    histogram: List[HistogramBarSchema]
    expiration_buckets: Dict[str, ExpirationBucketSchema]
    zero_dte_contribution: ZeroDteContributionSchema
    gex_over_time: List[Dict[str, Any]]
    confidence_score: float
    confidence_reasons: List[str]
    sign_model: SignModel
    provider: str
    provider_status: str
    cache_age_seconds: float
    is_stale: bool
    refresh_status: str


class IndividualGammaTVPayload(BaseModel):
    """Locked TV output schema for an individual underlying screen
    (section 17), e.g. TSLA."""

    schema_version: str
    engine_version: str
    snapshot_id: str
    symbol: str
    timestamp_utc: str
    timestamp_et: str
    source_data_timestamp: str
    calculation_timestamp: str
    spot: float
    gamma_regime: GammaRegime
    gamma_gauge: float
    gamma_gauge_label: str
    gamma_gauge_components: Dict[str, float]
    net_gex_usd_per_1pct_move: float
    absolute_gex_usd_per_1pct_move: float
    gamma_flip: Optional[float]
    all_gamma_crossings: List[GammaCrossingSchema]
    positive_gamma_wall: Optional[float]
    negative_gamma_pit: Optional[float]
    nearest_major_gamma_level_above: Optional[float]
    nearest_major_gamma_level_below: Optional[float]
    dealer_pressure: str
    expected_behavior: str
    acceleration_risk: str
    pinning_probability_estimate: Optional[float]
    confidence_score: float
    confidence_reasons: List[str]
    sign_model: SignModel
    provider: str
    provider_status: str
    cache_age_seconds: float
    is_stale: bool
    refresh_status: str


class DashboardSynchronizationSchema(BaseModel):
    spx_snapshot_id: str
    asset_snapshot_id: str
    timestamp_difference_seconds: float
    synchronization_threshold_seconds: float
    synchronized: bool


class TVDashboardPayload(BaseModel):
    schema_version: str
    engine_version: str
    dashboard_timestamp: str
    market_foundation: SPXMarketFoundationTVPayload
    individual_asset: IndividualGammaTVPayload
    synchronization: DashboardSynchronizationSchema


class ProviderCapabilitiesSchema(BaseModel):
    supports_underlying_quote: bool
    supports_full_chain: bool
    supports_contract_snapshot: bool
    supports_market_clock: bool
    required_env_vars: List[str]


class ProviderMetadataSchema(BaseModel):
    provider: str
    status: str
    capabilities: ProviderCapabilitiesSchema
    active: bool
    health_status: Optional[str]
    last_successful_request_timestamp: Optional[str]


class TVManifestResponse(BaseModel):
    schema_version: str
    engine_version: str
    architecture_designation: str
    supported_symbols: List[str]
    market_foundation_endpoint: str
    individual_asset_endpoint_pattern: str
    dashboard_endpoint_pattern: str
    refresh_recommendations: Dict[str, float]
    histogram_semantics: Dict[str, str]
    gauge_semantics: Dict[str, Any]
    timestamp_semantics: Dict[str, str]


class ErrorDetailSchema(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = {}


class ErrorResponseSchema(BaseModel):
    error: ErrorDetailSchema
    symbol: str
    spot: float
    timestamp_utc: str
    sign_model: SignModel
    total_net_gex_usd_per_1pct_move: float
    total_absolute_gex_usd_per_1pct_move: float
    gamma_flip: Optional[float]
    all_gamma_crossings: List[Dict[str, Any]]
    flip_interpolation_method: str
    flip_confidence: float
    gamma_regime: GammaRegime
    gamma_gauge: float
    gauge_interpretation: str
    gauge_components: Dict[str, float]
    zero_dte_net_gex: float
    zero_dte_absolute_gex: float
    zero_dte_pct_of_total: float
    non_zero_dte_absolute_gex: float
    confidence_score: float
    confidence_reason_codes: List[str]
    data_status: DataStatus
    key_levels: Dict[str, Optional[GammaLevelSchema]]
    top_positive_levels: List[GammaLevelSchema]
    top_negative_levels: List[GammaLevelSchema]
