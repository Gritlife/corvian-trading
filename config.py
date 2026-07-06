"""
Central configuration for the External Gamma Engine.

All secrets and tunable parameters are sourced from environment variables.
Never hard-code API keys. See .env.example for the full list of supported
variables and their meaning.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _get_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # --- Engine identity ---
    engine_version: str = "0.1.1"
    schema_version: str = "1.0"
    architecture_designation: str = "OCM External Gamma Engine v0.1.1"
    purpose: str = "Hardened Gamma Foundation Baseline for MTS-V30 integration"

    # --- Market conventions ---
    market_timezone: str = "America/New_York"
    contract_multiplier: int = 100
    risk_free_rate: float = field(default_factory=lambda: _get_float("EGE_RISK_FREE_RATE", 0.045))
    dividend_yield_default: float = field(default_factory=lambda: _get_float("EGE_DIVIDEND_YIELD", 0.0))

    # --- Numerical floors (avoid divide-by-zero / blow-ups) ---
    min_time_to_expiration_years: float = field(
        default_factory=lambda: _get_float("EGE_MIN_T_YEARS", 1.0 / (365.0 * 24.0 * 60.0))
    )  # 1 minute floor
    min_implied_vol: float = field(default_factory=lambda: _get_float("EGE_MIN_IV", 0.01))
    max_implied_vol: float = field(default_factory=lambda: _get_float("EGE_MAX_IV", 5.0))

    # --- Spot shock grid defaults ---
    spot_shock_range_pct: float = field(default_factory=lambda: _get_float("EGE_SPOT_RANGE_PCT", 0.10))
    spot_shock_step_pct: float = field(default_factory=lambda: _get_float("EGE_SPOT_STEP_PCT", 0.0025))

    # --- Data freshness thresholds (seconds) ---
    stale_quote_seconds: int = field(default_factory=lambda: _get_int("EGE_STALE_QUOTE_SECONDS", 120))

    # --- Provider selection ---
    active_provider: str = field(default_factory=lambda: os.environ.get("EGE_PROVIDER", "mock"))
    provider_api_key: Optional[str] = field(default_factory=lambda: os.environ.get("EGE_PROVIDER_API_KEY"))
    provider_base_url: Optional[str] = field(default_factory=lambda: os.environ.get("EGE_PROVIDER_BASE_URL"))
    provider_timeout_seconds: float = field(default_factory=lambda: _get_float("EGE_PROVIDER_TIMEOUT", 10.0))

    # --- Caching / refresh TTLs (seconds) ---
    quote_ttl_seconds: float = field(default_factory=lambda: _get_float("EGE_QUOTE_TTL_SECONDS", 2.0))
    chain_ttl_seconds: float = field(default_factory=lambda: _get_float("EGE_CHAIN_TTL_SECONDS", 30.0))
    analysis_ttl_seconds: float = field(default_factory=lambda: _get_float("EGE_ANALYSIS_TTL_SECONDS", 10.0))
    tv_payload_ttl_seconds: float = field(default_factory=lambda: _get_float("EGE_TV_PAYLOAD_TTL_SECONDS", 5.0))

    # --- Background refresh service ---
    refresh_symbols: str = field(default_factory=lambda: os.environ.get("GAMMA_REFRESH_SYMBOLS", "SPX,TSLA"))
    background_refresh_enabled: bool = field(
        default_factory=lambda: _get_bool("EGE_BACKGROUND_REFRESH_ENABLED", False)
    )
    background_refresh_interval_seconds: float = field(
        default_factory=lambda: _get_float("EGE_BACKGROUND_REFRESH_INTERVAL_SECONDS", 10.0)
    )

    # --- Dashboard synchronization ---
    dashboard_sync_threshold_seconds: float = field(
        default_factory=lambda: _get_float("EGE_DASHBOARD_SYNC_THRESHOLD_SECONDS", 30.0)
    )

    # --- Persistence ---
    sqlite_path: str = field(default_factory=lambda: os.environ.get("EGE_SQLITE_PATH", "data/gamma_history.db"))
    history_retention_days: int = field(default_factory=lambda: _get_int("EGE_HISTORY_RETENTION_DAYS", 90))

    # --- Default sign model ---
    default_sign_model: str = field(default_factory=lambda: os.environ.get("EGE_SIGN_MODEL", "NAIVE_CONVENTION"))

    # --- Top-N default ---
    default_top_n: int = field(default_factory=lambda: _get_int("EGE_TOP_N", 5))

    # --- Feature flags ---
    enable_heuristic_sign_model: bool = field(
        default_factory=lambda: _get_bool("EGE_ENABLE_HEURISTIC_SIGN_MODEL", True)
    )

    def refresh_symbols_list(self) -> list:
        return [s.strip().upper() for s in self.refresh_symbols.split(",") if s.strip()]


settings = Settings()
