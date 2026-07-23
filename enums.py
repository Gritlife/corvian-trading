from __future__ import annotations

from enum import Enum


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class DataCategory(str, Enum):
    """Every output field/value must be traceable to one of these categories."""

    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    MODELED = "MODELED"


class SignModel(str, Enum):
    NAIVE_CONVENTION = "NAIVE_CONVENTION"
    UNSIGNED_GAMMA = "UNSIGNED_GAMMA"
    CUSTOM_POSITIONING = "CUSTOM_POSITIONING"
    HEURISTIC_POSITIONING = "HEURISTIC_POSITIONING"


class GammaRegime(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


class DataQualityFlag(str, Enum):
    NEGATIVE_OI = "NEGATIVE_OI"
    NEGATIVE_VOLUME = "NEGATIVE_VOLUME"
    CROSSED_MARKET = "CROSSED_MARKET"
    MISSING_IV = "MISSING_IV"
    STALE_QUOTE = "STALE_QUOTE"
    IMPOSSIBLE_STRIKE = "IMPOSSIBLE_STRIKE"
    EXPIRED_CONTRACT = "EXPIRED_CONTRACT"
    ZERO_TIME = "ZERO_TIME"
    DUPLICATE_CONTRACT = "DUPLICATE_CONTRACT"
    MISSING_SPOT = "MISSING_SPOT"
    EXTREME_IV = "EXTREME_IV"
    NON_FINITE_VALUE = "NON_FINITE_VALUE"


class ConfidenceReasonCode(str, Enum):
    STALE_QUOTES = "STALE_QUOTES"
    MISSING_IV = "MISSING_IV"
    LOW_OI_COVERAGE = "LOW_OI_COVERAGE"
    PARTIAL_CHAIN = "PARTIAL_CHAIN"
    HEURISTIC_SIGN_MODEL = "HEURISTIC_SIGN_MODEL"
    NO_GAMMA_CROSSING = "NO_GAMMA_CROSSING"
    MULTIPLE_GAMMA_CROSSINGS = "MULTIPLE_GAMMA_CROSSINGS"
    HIGH_0DTE_SENSITIVITY = "HIGH_0DTE_SENSITIVITY"


class DTEBucket(str, Enum):
    ZERO_DTE = "0DTE"
    ONE_TO_SEVEN = "1_7_DTE"
    EIGHT_TO_THIRTY = "8_30_DTE"
    OVER_THIRTY = "OVER_30_DTE"
    ALL = "ALL"


class DataStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class ProviderStatus(str, Enum):
    """Honest capability classification for every OptionsDataProvider.

    Never report PRODUCTION_READY unless a provider's endpoints have been
    verified against live vendor documentation and exercised successfully.
    """

    PRODUCTION_READY = "PRODUCTION_READY"
    EXPERIMENTAL = "EXPERIMENTAL"
    SCAFFOLD_ONLY = "SCAFFOLD_ONLY"
    MOCK = "MOCK"


class RefreshStatus(str, Enum):
    """Cache-freshness status, distinct from DataStatus (data freshness).

    FRESH: recomputed on this request.
    CACHED: served from a still-valid cache entry.
    REFRESHING: another request is currently recomputing; a cached value
        (if any) was returned instead of blocking.
    STALE_FALLBACK: cache expired and refresh failed; last-known-good
        snapshot returned instead of blanking the display.
    ERROR: no snapshot (fresh or cached) is available at all.
    """

    FRESH = "FRESH"
    CACHED = "CACHED"
    REFRESHING = "REFRESHING"
    STALE_FALLBACK = "STALE_FALLBACK"
    ERROR = "ERROR"


class ErrorCode(str, Enum):
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_CAPABILITY_UNSUPPORTED = "PROVIDER_CAPABILITY_UNSUPPORTED"
    SYMBOL_UNSUPPORTED = "SYMBOL_UNSUPPORTED"
    NO_CHAIN_DATA = "NO_CHAIN_DATA"
    STALE_DATA_REJECTED = "STALE_DATA_REJECTED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    NO_VALID_IV = "NO_VALID_IV"
    INTERNAL_ERROR = "INTERNAL_ERROR"
