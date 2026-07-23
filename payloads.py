"""
MTS-V30 TV output contract, v0.1.1 (sections 14-17 of the hardening spec).

Builders never hard-code example values — every field is populated from a
live (or mock-provider) GammaAnalysisResult / SpxFoundationResult /
AssetGammaResult plus cache metadata computed at call time. Field shapes
here are the single source of truth for the corresponding Pydantic
response models in app.api.schemas (SPXMarketFoundationTVPayload,
IndividualGammaTVPayload) — FastAPI validates/serializes through those
schemas at the route layer.
"""
from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.enums import RefreshStatus
from app.services.aggregation import bucket_expirations
from app.services.asset_engine import AssetGammaResult
from app.services.spx_foundation import SpxFoundationResult

_ET = ZoneInfo("America/New_York")


def _level_dict(level) -> Optional[Dict[str, Any]]:
    if level is None:
        return None
    return {"strike": level.strike, "net_gex": level.net_gex, "label": level.label}


def default_cache_meta() -> Dict[str, Any]:
    """Cache metadata for a payload computed synchronously with no cache
    layer involved (e.g. CLI/demo usage) — always reports FRESH, age 0."""
    return {"cache_age_seconds": 0.0, "is_stale": False, "refresh_status": RefreshStatus.FRESH.value}


def build_spx_tv_payload(
    foundation: SpxFoundationResult,
    gex_over_time: Optional[List[dict]] = None,
    cache_meta: Optional[Dict[str, Any]] = None,
    provider_name: Optional[str] = None,
    provider_status: Optional[str] = None,
) -> Dict[str, Any]:
    a = foundation.analysis
    cache_meta = cache_meta or default_cache_meta()
    ts_utc = a.timestamp_utc.astimezone(timezone.utc)
    ts_et = a.timestamp_utc.astimezone(_ET)

    positive_wall = a.key_levels.get("positive_gamma_wall")
    negative_pit = a.key_levels.get("negative_gamma_pit")
    nearest_above = a.key_levels.get("nearest_positive_level_above_spot")
    nearest_below = a.key_levels.get("nearest_negative_level_below_spot")

    return {
        "schema_version": settings.schema_version,
        "engine_version": settings.engine_version,
        "snapshot_id": a.snapshot_id,
        "symbol": "SPX",
        "timestamp_utc": ts_utc.isoformat(),
        "timestamp_et": ts_et.isoformat(),
        "source_data_timestamp": a.source_data_timestamp.astimezone(timezone.utc).isoformat(),
        "calculation_timestamp": a.calculation_timestamp.astimezone(timezone.utc).isoformat(),
        "spot": a.spot,
        "market_gamma_regime": a.gamma_regime.value,
        "gamma_gauge": round(a.gamma_gauge, 2),
        "gamma_gauge_components": a.gamma_gauge_components,
        "total_net_gex_usd_per_1pct_move": a.total_net_gex,
        "total_absolute_gex_usd_per_1pct_move": a.total_absolute_gex,
        "gamma_flip": a.gamma_flip,
        "all_gamma_crossings": a.all_gamma_crossings,
        "positive_gamma_wall": positive_wall.strike if positive_wall else None,
        "negative_gamma_pit": negative_pit.strike if negative_pit else None,
        "nearest_positive_level_above_spot": nearest_above.strike if nearest_above else None,
        "nearest_negative_level_below_spot": nearest_below.strike if nearest_below else None,
        "top_positive_levels": [_level_dict(l) for l in a.top_positive_levels],
        "top_negative_levels": [_level_dict(l) for l in a.top_negative_levels],
        "histogram": foundation.histogram,
        "expiration_buckets": bucket_expirations(a.expiration_df_records),
        "zero_dte_contribution": {
            "net_gex": a.zero_dte_net_gex,
            "absolute_gex": a.zero_dte_absolute_gex,
            "pct_of_total": a.zero_dte_pct_of_total,
        },
        "gex_over_time": gex_over_time or [],
        "confidence_score": a.confidence_score,
        "confidence_reasons": a.confidence_reason_codes,
        "sign_model": a.sign_model.value,
        "provider": provider_name or a.provider_name,
        "provider_status": provider_status or a.provider_status,
        "cache_age_seconds": cache_meta["cache_age_seconds"],
        "is_stale": cache_meta["is_stale"],
        "refresh_status": cache_meta["refresh_status"],
    }


def build_symbol_tv_payload(
    asset_result: AssetGammaResult,
    cache_meta: Optional[Dict[str, Any]] = None,
    provider_name: Optional[str] = None,
    provider_status: Optional[str] = None,
) -> Dict[str, Any]:
    a = asset_result.analysis
    cache_meta = cache_meta or default_cache_meta()
    ts_utc = a.timestamp_utc.astimezone(timezone.utc)
    ts_et = a.timestamp_utc.astimezone(_ET)

    positive_wall = a.key_levels.get("positive_gamma_wall")
    negative_pit = a.key_levels.get("negative_gamma_pit")
    nearest_above = a.key_levels.get("nearest_positive_level_above_spot")
    nearest_below = a.key_levels.get("nearest_negative_level_below_spot")

    return {
        "schema_version": settings.schema_version,
        "engine_version": settings.engine_version,
        "snapshot_id": a.snapshot_id,
        "symbol": a.symbol,
        "timestamp_utc": ts_utc.isoformat(),
        "timestamp_et": ts_et.isoformat(),
        "source_data_timestamp": a.source_data_timestamp.astimezone(timezone.utc).isoformat(),
        "calculation_timestamp": a.calculation_timestamp.astimezone(timezone.utc).isoformat(),
        "spot": a.spot,
        "gamma_regime": a.gamma_regime.value,
        "gamma_gauge": round(a.gamma_gauge, 2),
        "gamma_gauge_label": a.gauge_interpretation,
        "gamma_gauge_components": a.gamma_gauge_components,
        "net_gex_usd_per_1pct_move": a.total_net_gex,
        "absolute_gex_usd_per_1pct_move": a.total_absolute_gex,
        "gamma_flip": a.gamma_flip,
        "all_gamma_crossings": a.all_gamma_crossings,
        "positive_gamma_wall": positive_wall.strike if positive_wall else None,
        "negative_gamma_pit": negative_pit.strike if negative_pit else None,
        "nearest_major_gamma_level_above": nearest_above.strike if nearest_above else None,
        "nearest_major_gamma_level_below": nearest_below.strike if nearest_below else None,
        "dealer_pressure": asset_result.dealer_pressure.dealer_pressure,
        "expected_behavior": asset_result.dealer_pressure.expected_behavior,
        "acceleration_risk": asset_result.dealer_pressure.acceleration_risk,
        "pinning_probability_estimate": asset_result.dealer_pressure.pinning_probability_estimate,
        "confidence_score": a.confidence_score,
        "confidence_reasons": a.confidence_reason_codes,
        "sign_model": a.sign_model.value,
        "provider": provider_name or a.provider_name,
        "provider_status": provider_status or a.provider_status,
        "cache_age_seconds": cache_meta["cache_age_seconds"],
        "is_stale": cache_meta["is_stale"],
        "refresh_status": cache_meta["refresh_status"],
    }


def build_dashboard_payload(
    spx_payload: Dict[str, Any], asset_payload: Dict[str, Any], sync_threshold_seconds: Optional[float] = None
) -> Dict[str, Any]:
    """Combined two-screen snapshot (section 21/22). Computes an honest
    synchronization verdict from the two underlying calculation
    timestamps — never reports synchronized=true merely because both
    payloads exist."""
    from datetime import datetime as _dt

    threshold = sync_threshold_seconds if sync_threshold_seconds is not None else settings.dashboard_sync_threshold_seconds

    spx_ts = _dt.fromisoformat(spx_payload["calculation_timestamp"])
    asset_ts = _dt.fromisoformat(asset_payload["calculation_timestamp"])
    diff_seconds = abs((spx_ts - asset_ts).total_seconds())
    synchronized = diff_seconds <= threshold

    dashboard_ts = max(spx_ts, asset_ts).astimezone(timezone.utc).isoformat()

    return {
        "schema_version": settings.schema_version,
        "engine_version": settings.engine_version,
        "dashboard_timestamp": dashboard_ts,
        "market_foundation": spx_payload,
        "individual_asset": asset_payload,
        "synchronization": {
            "spx_snapshot_id": spx_payload["snapshot_id"],
            "asset_snapshot_id": asset_payload["snapshot_id"],
            "timestamp_difference_seconds": diff_seconds,
            "synchronization_threshold_seconds": threshold,
            "synchronized": synchronized,
        },
    }
