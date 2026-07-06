from __future__ import annotations

from datetime import timezone
from typing import Optional

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.enums import SignModel
from app.core.errors import SymbolUnsupported
from app.models.results import GammaAnalysisResult
from app.providers.factory import get_provider, list_provider_metadata
from app.repositories.gex_history import GexHistoryRecord, SQLiteGexHistoryRepository
from app.services.gamma_analysis import run_gamma_analysis
from app.services.snapshot_service import (
    get_asset_gamma_cached,
    get_spx_foundation_cached,
    get_spx_tv_payload_cached,
    get_symbol_tv_payload_cached,
)
from app.tv.payloads import build_dashboard_payload

router = APIRouter()

_provider = get_provider()
_history_repo = SQLiteGexHistoryRepository()

_SUPPORTED_SYMBOLS = ("SPX", "TSLA")


def _analysis_to_response_dict(analysis: GammaAnalysisResult) -> dict:
    return {
        "symbol": analysis.symbol,
        "spot": analysis.spot,
        "timestamp_utc": analysis.timestamp_utc.astimezone(timezone.utc).isoformat(),
        "snapshot_id": analysis.snapshot_id,
        "sign_model": analysis.sign_model,
        "total_net_gex_usd_per_1pct_move": analysis.total_net_gex,
        "total_absolute_gex_usd_per_1pct_move": analysis.total_absolute_gex,
        "gamma_flip": analysis.gamma_flip,
        "all_gamma_crossings": analysis.all_gamma_crossings,
        "flip_interpolation_method": analysis.flip_interpolation_method,
        "flip_confidence": analysis.flip_confidence,
        "gamma_regime": analysis.gamma_regime,
        "gamma_gauge": analysis.gamma_gauge,
        "gauge_interpretation": analysis.gauge_interpretation,
        "gauge_components": analysis.gauge_components,
        "gamma_gauge_components": analysis.gamma_gauge_components,
        "zero_dte_net_gex": analysis.zero_dte_net_gex,
        "zero_dte_absolute_gex": analysis.zero_dte_absolute_gex,
        "zero_dte_pct_of_total": analysis.zero_dte_pct_of_total,
        "non_zero_dte_absolute_gex": analysis.non_zero_dte_absolute_gex,
        "confidence_score": analysis.confidence_score,
        "confidence_reason_codes": analysis.confidence_reason_codes,
        "data_status": analysis.data_status,
        "key_levels": analysis.key_levels,
        "top_positive_levels": analysis.top_positive_levels,
        "top_negative_levels": analysis.top_negative_levels,
        "provider": analysis.provider_name,
        "provider_status": analysis.provider_status,
    }


def _validate_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol not in _SUPPORTED_SYMBOLS:
        raise SymbolUnsupported(
            f"Symbol '{symbol}' is not supported by the active provider ('{_provider.name}').",
            details={"symbol": symbol, "supported_symbols": list(_SUPPORTED_SYMBOLS)},
        )
    return symbol


def _run(symbol: str, sign_model: SignModel, spot_range_pct=None, spot_step_pct=None, top_n=None):
    symbol = _validate_symbol(symbol)
    return run_gamma_analysis(
        provider=_provider,
        symbol=symbol,
        sign_model=sign_model,
        spot_range_pct=spot_range_pct,
        spot_step_pct=spot_step_pct,
        top_n=top_n,
    )


def _record_history(analysis: GammaAnalysisResult) -> None:
    positive_wall = analysis.key_levels.get("positive_gamma_wall")
    negative_pit = analysis.key_levels.get("negative_gamma_pit")
    _history_repo.append(
        GexHistoryRecord(
            snapshot_id=analysis.snapshot_id,
            timestamp_utc=analysis.timestamp_utc.astimezone(timezone.utc).isoformat(),
            symbol=analysis.symbol,
            spot=analysis.spot,
            net_gex=analysis.total_net_gex,
            absolute_gex=analysis.total_absolute_gex,
            gamma_gauge=analysis.gamma_gauge,
            gamma_flip=analysis.gamma_flip,
            positive_wall=positive_wall.strike if positive_wall else None,
            negative_pit=negative_pit.strike if negative_pit else None,
            confidence_score=analysis.confidence_score,
            sign_model=analysis.sign_model.value,
            provider=analysis.provider_name,
            source_data_timestamp=analysis.source_data_timestamp.astimezone(timezone.utc).isoformat(),
        )
    )


# --- Health & metadata ---


@router.get("/health")
def health():
    return {
        "status": "ok",
        "engine_version": settings.engine_version,
        "architecture_designation": settings.architecture_designation,
        "purpose": settings.purpose,
        "active_provider": _provider.name,
        "active_provider_status": _provider.status.value,
    }


@router.get("/v1/providers")
def get_providers():
    return {"providers": list_provider_metadata()}


# --- Core gamma endpoints (preserved from v0.1) ---


@router.get("/v1/gamma/{symbol}")
def get_gamma(
    symbol: str,
    sign_model: SignModel = Query(default=SignModel.NAIVE_CONVENTION),
    spot_range_pct: Optional[float] = None,
    spot_step_pct: Optional[float] = None,
    top_n: Optional[int] = None,
):
    analysis = _run(symbol, sign_model, spot_range_pct, spot_step_pct, top_n)
    return _analysis_to_response_dict(analysis)


@router.get("/v1/gamma/{symbol}/strikes")
def get_gamma_strikes(symbol: str, sign_model: SignModel = Query(default=SignModel.NAIVE_CONVENTION)):
    analysis = _run(symbol, sign_model)
    return {"symbol": analysis.symbol, "strikes": analysis.strike_df_records}


@router.get("/v1/gamma/{symbol}/expirations")
def get_gamma_expirations(
    symbol: str,
    sign_model: SignModel = Query(default=SignModel.NAIVE_CONVENTION),
    min_dte: Optional[float] = None,
    max_dte: Optional[float] = None,
    include_0dte: bool = True,
):
    analysis = _run(symbol, sign_model)
    records = analysis.expiration_df_records
    if not include_0dte:
        records = [r for r in records if not r["is_0dte"]]
    if min_dte is not None:
        records = [r for r in records if r["dte"] >= min_dte]
    if max_dte is not None:
        records = [r for r in records if r["dte"] <= max_dte]
    return {"symbol": analysis.symbol, "expirations": records}


@router.get("/v1/gamma/{symbol}/profile")
def get_gamma_profile(
    symbol: str,
    sign_model: SignModel = Query(default=SignModel.NAIVE_CONVENTION),
    spot_range_pct: Optional[float] = None,
    spot_step_pct: Optional[float] = None,
):
    analysis = _run(symbol, sign_model, spot_range_pct, spot_step_pct)
    return {"symbol": analysis.symbol, "spot_shock_profile": analysis.spot_shock_profile}


@router.get("/v1/gamma/{symbol}/flip")
def get_gamma_flip(symbol: str, sign_model: SignModel = Query(default=SignModel.NAIVE_CONVENTION)):
    analysis = _run(symbol, sign_model)
    return {
        "symbol": analysis.symbol,
        "primary_gamma_flip": analysis.gamma_flip,
        "all_gamma_crossings": analysis.all_gamma_crossings,
        "interpolation_method": analysis.flip_interpolation_method,
        "confidence": analysis.flip_confidence,
        "sign_model": analysis.sign_model,
    }


@router.get("/v1/gamma/{symbol}/gauge")
def get_gamma_gauge(symbol: str, sign_model: SignModel = Query(default=SignModel.NAIVE_CONVENTION)):
    analysis = _run(symbol, sign_model)
    return {
        "symbol": analysis.symbol,
        "gamma_gauge": analysis.gamma_gauge,
        "interpretation": analysis.gauge_interpretation,
        "components": analysis.gauge_components,
        "gamma_gauge_components": analysis.gamma_gauge_components,
    }


@router.get("/v1/market/spx/foundation")
def get_spx_foundation():
    foundation, status, age = get_spx_foundation_cached(_provider)
    a = foundation.analysis
    _record_history(a)
    return {
        **_analysis_to_response_dict(a),
        "strike_histogram": foundation.histogram,
        "expiration_dataset": a.expiration_df_records,
        "spot_shock_profile": a.spot_shock_profile,
        "zero_dte_contribution": a.zero_dte_absolute_gex,
        "non_zero_dte_contribution": a.non_zero_dte_absolute_gex,
        "cache_age_seconds": round(age, 3),
        "refresh_status": status.value,
    }


# --- TV endpoints (cached, stale-while-revalidate) ---
#
# ROUTE ORDER IS LOAD-BEARING: FastAPI matches path operations in
# registration order, and {symbol} is an unconstrained single-segment
# path parameter that would greedily match literal segments like
# "manifest". More specific literal paths (/v1/tv/manifest,
# /v1/tv/dashboard/{symbol}) MUST be registered before the generic
# /v1/tv/{symbol} catch-all, or GET /v1/tv/manifest would be
# misrouted to get_tv_symbol("manifest") instead of get_tv_manifest().
# (/v1/tv/dashboard/{symbol} has an extra path segment vs /v1/tv/{symbol}
# so it wouldn't actually collide, but it is kept above the catch-all
# here too, as a defensive convention: specific routes before wildcards.)


@router.get("/v1/tv/spx")
def get_tv_spx():
    history = _history_repo.query("SPX", limit=200)
    gex_over_time = [
        {"timestamp": h.timestamp_utc, "spot": h.spot, "net_gex": h.net_gex, "gamma_gauge": h.gamma_gauge}
        for h in reversed(history)
    ]
    payload = get_spx_tv_payload_cached(_provider, gex_over_time=gex_over_time)

    foundation, _status, _age = get_spx_foundation_cached(_provider)
    _record_history(foundation.analysis)
    return payload


@router.get("/v1/tv/manifest")
def get_tv_manifest():
    return {
        "schema_version": settings.schema_version,
        "engine_version": settings.engine_version,
        "architecture_designation": settings.architecture_designation,
        "supported_symbols": list(_SUPPORTED_SYMBOLS),
        "market_foundation_endpoint": "/v1/tv/spx",
        "individual_asset_endpoint_pattern": "/v1/tv/{symbol}",
        "dashboard_endpoint_pattern": "/v1/tv/dashboard/{symbol}",
        "refresh_recommendations": {
            "quote_ttl_seconds": settings.quote_ttl_seconds,
            "chain_ttl_seconds": settings.chain_ttl_seconds,
            "analysis_ttl_seconds": settings.analysis_ttl_seconds,
            "tv_payload_ttl_seconds": settings.tv_payload_ttl_seconds,
        },
        "histogram_semantics": {
            "strike_order": "ascending",
            "normalized_bar_range": "[-1.0, 1.0]",
            "zero_axis": "mathematical center; positive GEX renders positive, negative GEX renders negative",
            "rank_field": "rank_by_absolute_gex (1 = largest magnitude, ties broken by strike order)",
        },
        "gauge_semantics": {
            "range": "[-100, 100]",
            "bands": {
                "EXTREME_NEGATIVE": "<= -70",
                "NEGATIVE": "-69..-30",
                "TRANSITION_NEUTRAL": "-29..+29",
                "POSITIVE": "+30..+69",
                "EXTREME_POSITIVE": ">= +70",
            },
            "components_are_additive": True,
        },
        "timestamp_semantics": {
            "timestamp_utc": "wall-clock time this snapshot's as_of anchor represents, UTC",
            "timestamp_et": "same instant, America/New_York local time",
            "source_data_timestamp": "OBSERVED — earliest underlying quote timestamp feeding this snapshot",
            "calculation_timestamp": "DERIVED — when the engine computed this snapshot, UTC",
            "cache_age_seconds": "CACHE freshness (distinct from data freshness) — seconds since this snapshot was computed",
        },
    }


@router.get("/v1/tv/dashboard/{symbol}")
def get_tv_dashboard(symbol: str):
    symbol = _validate_symbol(symbol)

    history = _history_repo.query("SPX", limit=200)
    gex_over_time = [
        {"timestamp": h.timestamp_utc, "spot": h.spot, "net_gex": h.net_gex, "gamma_gauge": h.gamma_gauge}
        for h in reversed(history)
    ]
    spx_payload = get_spx_tv_payload_cached(_provider, gex_over_time=gex_over_time)
    asset_payload = get_symbol_tv_payload_cached(_provider, symbol)

    foundation, _s1, _a1 = get_spx_foundation_cached(_provider)
    asset_result, _s2, _a2 = get_asset_gamma_cached(_provider, symbol)
    _record_history(foundation.analysis)
    _record_history(asset_result.analysis)

    return build_dashboard_payload(spx_payload, asset_payload)


@router.get("/v1/tv/{symbol}")
def get_tv_symbol(symbol: str):
    symbol = _validate_symbol(symbol)
    payload = get_symbol_tv_payload_cached(_provider, symbol)

    asset_result, _status, _age = get_asset_gamma_cached(_provider, symbol)
    _record_history(asset_result.analysis)
    return payload


# --- Legacy analyze endpoint (preserved) ---


@router.post("/v1/gamma/analyze")
def post_gamma_analyze(request: dict):
    symbol = request.get("symbol")
    if not symbol:
        raise SymbolUnsupported("symbol is required", details={"provided": request})
    sign_model = SignModel(request.get("sign_model", SignModel.NAIVE_CONVENTION.value))
    spot_range_pct = request.get("spot_range_pct")
    spot_step_pct = request.get("spot_step_pct")
    top_n = request.get("top_n")

    analysis = _run(symbol, sign_model, spot_range_pct, spot_step_pct, top_n)
    return _analysis_to_response_dict(analysis)
