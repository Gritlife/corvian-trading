"""
Snapshot service: the caching pipeline required by section 8.

    Provider -> Normalized Chain Cache -> Gamma Computation ->
    Analysis Snapshot Cache -> TV Payload Cache -> FastAPI

This module is the single place that wires TTL caching, single-flight
concurrency protection, and stale-while-revalidate fallback around the
existing (unmodified) quant/service pipeline. Routes call into this
module instead of calling run_gamma_analysis/build_spx_foundation/
build_asset_gamma directly, so caching is centralized and consistent
across every TV/API endpoint.
"""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.core.enums import RefreshStatus, SignModel
from app.core.errors import AnalysisFailed
from app.providers.base import OptionsDataProvider
from app.services.asset_engine import AssetGammaResult, build_asset_gamma
from app.services.cache import analysis_cache, tv_payload_cache
from app.services.spx_foundation import SpxFoundationResult, build_spx_foundation
from app.tv.payloads import build_spx_tv_payload, build_symbol_tv_payload

# Severity ordering used to reconcile the TV-payload cache's own status
# with the status of the analysis snapshot it wraps: a fresh TV-cache
# entry built from a stale analysis is still stale overall, so the more
# severe of the two statuses always wins rather than the outer layer
# silently overwriting the inner one.
_SEVERITY = {
    RefreshStatus.FRESH: 0,
    RefreshStatus.CACHED: 1,
    RefreshStatus.REFRESHING: 2,
    RefreshStatus.STALE_FALLBACK: 3,
    RefreshStatus.ERROR: 4,
}


def _more_severe(a: RefreshStatus, b: RefreshStatus) -> RefreshStatus:
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def _analysis_key(symbol: str, sign_model: SignModel) -> str:
    return f"analysis:{symbol.upper()}:{sign_model.value}"


def _tv_key(symbol: str, sign_model: SignModel) -> str:
    return f"tv:{symbol.upper()}:{sign_model.value}"


def get_spx_foundation_cached(
    provider: OptionsDataProvider, sign_model: SignModel = SignModel.NAIVE_CONVENTION
) -> tuple[SpxFoundationResult, RefreshStatus, float]:
    key = _analysis_key("SPX", sign_model)

    def compute() -> SpxFoundationResult:
        return build_spx_foundation(provider, sign_model=sign_model)

    try:
        value, status, age = analysis_cache.get_or_refresh(key, settings.analysis_ttl_seconds, compute)
        return value, status, age
    except Exception as exc:  # noqa: BLE001
        raise AnalysisFailed(f"SPX foundation analysis failed with no prior snapshot: {exc}") from exc


def get_asset_gamma_cached(
    provider: OptionsDataProvider, symbol: str, sign_model: SignModel = SignModel.NAIVE_CONVENTION
) -> tuple[AssetGammaResult, RefreshStatus, float]:
    key = _analysis_key(symbol, sign_model)

    def compute() -> AssetGammaResult:
        return build_asset_gamma(provider, symbol.upper(), sign_model=sign_model)

    try:
        value, status, age = analysis_cache.get_or_refresh(key, settings.analysis_ttl_seconds, compute)
        return value, status, age
    except Exception as exc:  # noqa: BLE001
        raise AnalysisFailed(f"Gamma analysis for '{symbol}' failed with no prior snapshot: {exc}") from exc


def _cache_meta(status: RefreshStatus, age: float) -> dict:
    return {
        "cache_age_seconds": round(age, 3),
        "is_stale": status in (RefreshStatus.STALE_FALLBACK, RefreshStatus.REFRESHING),
        "refresh_status": status.value,
    }


def get_spx_tv_payload_cached(
    provider: OptionsDataProvider, sign_model: SignModel = SignModel.NAIVE_CONVENTION, gex_over_time: Optional[list] = None
) -> dict:
    key = _tv_key("SPX", sign_model)
    inner_meta_holder: dict = {}

    def compute() -> dict:
        foundation, analysis_status, analysis_age = get_spx_foundation_cached(provider, sign_model)
        cache_meta = _cache_meta(analysis_status, analysis_age)
        inner_meta_holder["status"] = analysis_status
        inner_meta_holder["age"] = analysis_age
        return build_spx_tv_payload(
            foundation,
            gex_over_time=gex_over_time,
            cache_meta=cache_meta,
            provider_name=provider.name,
            provider_status=provider.status.value,
        )

    try:
        payload, outer_status, outer_age = tv_payload_cache.get_or_refresh(key, settings.tv_payload_ttl_seconds, compute)
    except Exception as exc:  # noqa: BLE001
        raise AnalysisFailed(f"SPX TV payload generation failed with no prior snapshot: {exc}") from exc

    payload = dict(payload)
    # If this call actually recomputed (inner_meta_holder populated), the
    # true status is whichever is more severe: the TV-cache's own outer
    # status, or the analysis snapshot status it was built from. If this
    # call was itself served from a cached TV payload (no recompute), the
    # payload's own embedded cache_meta from when it was built already
    # reflects the correct (possibly stale) status, so only the outer
    # cache_age_seconds is refreshed to reflect elapsed time since then.
    if inner_meta_holder:
        combined_status = _more_severe(outer_status, inner_meta_holder["status"])
        payload.update(_cache_meta(combined_status, max(outer_age, inner_meta_holder["age"])))
    else:
        payload["cache_age_seconds"] = round(outer_age, 3)
    return payload


def get_symbol_tv_payload_cached(
    provider: OptionsDataProvider, symbol: str, sign_model: SignModel = SignModel.NAIVE_CONVENTION
) -> dict:
    key = _tv_key(symbol, sign_model)
    inner_meta_holder: dict = {}

    def compute() -> dict:
        asset_result, analysis_status, analysis_age = get_asset_gamma_cached(provider, symbol, sign_model)
        cache_meta = _cache_meta(analysis_status, analysis_age)
        inner_meta_holder["status"] = analysis_status
        inner_meta_holder["age"] = analysis_age
        return build_symbol_tv_payload(
            asset_result,
            cache_meta=cache_meta,
            provider_name=provider.name,
            provider_status=provider.status.value,
        )

    try:
        payload, outer_status, outer_age = tv_payload_cache.get_or_refresh(key, settings.tv_payload_ttl_seconds, compute)
    except Exception as exc:  # noqa: BLE001
        raise AnalysisFailed(f"TV payload generation for '{symbol}' failed with no prior snapshot: {exc}") from exc

    payload = dict(payload)
    if inner_meta_holder:
        combined_status = _more_severe(outer_status, inner_meta_holder["status"])
        payload.update(_cache_meta(combined_status, max(outer_age, inner_meta_holder["age"])))
    else:
        payload["cache_age_seconds"] = round(outer_age, 3)
    return payload
