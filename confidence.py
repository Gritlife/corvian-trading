"""
Data-quality / confidence scoring framework.

Produces a single 0-100 confidence_score plus reason codes, combining
several independently interpretable sub-scores. This score describes how
much an OCM consumer should trust a given gamma output, not a prediction
of market direction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from app.core.enums import ConfidenceReasonCode


@dataclass
class ConfidenceResult:
    confidence_score: float  # 0-100
    reason_codes: List[str] = field(default_factory=list)
    components: dict = field(default_factory=dict)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_confidence(
    quote_freshness: float,  # 1.0 = fresh, 0.0 = very stale
    iv_completeness: float,  # fraction of contracts with real observed IV
    oi_completeness: float,  # fraction of contracts with nonzero OI
    chain_completeness: float,  # fraction of expected strikes/expirations present (1.0 if unknown -> assume complete)
    spread_quality: float,  # 1.0 tight spreads, 0.0 very wide/crossed
    provider_quality: float,  # 0-1 vendor reliability weight
    sign_model_certainty: float,  # 0-1, from sign model mean confidence
    expiration_coverage: float,  # fraction of relevant DTE buckets populated
    extra_reason_codes: List[str] | None = None,
) -> ConfidenceResult:
    components = {
        "quote_freshness": _clamp01(quote_freshness),
        "iv_completeness": _clamp01(iv_completeness),
        "oi_completeness": _clamp01(oi_completeness),
        "chain_completeness": _clamp01(chain_completeness),
        "spread_quality": _clamp01(spread_quality),
        "provider_quality": _clamp01(provider_quality),
        "sign_model_certainty": _clamp01(sign_model_certainty),
        "expiration_coverage": _clamp01(expiration_coverage),
    }

    weights = {
        "quote_freshness": 0.15,
        "iv_completeness": 0.15,
        "oi_completeness": 0.15,
        "chain_completeness": 0.10,
        "spread_quality": 0.10,
        "provider_quality": 0.10,
        "sign_model_certainty": 0.15,
        "expiration_coverage": 0.10,
    }

    score01 = sum(components[k] * weights[k] for k in weights)
    score = round(score01 * 100.0, 2)

    reason_codes: List[str] = list(extra_reason_codes or [])
    if components["quote_freshness"] < 0.5:
        reason_codes.append(ConfidenceReasonCode.STALE_QUOTES.value)
    if components["iv_completeness"] < 0.7:
        reason_codes.append(ConfidenceReasonCode.MISSING_IV.value)
    if components["oi_completeness"] < 0.5:
        reason_codes.append(ConfidenceReasonCode.LOW_OI_COVERAGE.value)
    if components["chain_completeness"] < 0.8:
        reason_codes.append(ConfidenceReasonCode.PARTIAL_CHAIN.value)

    return ConfidenceResult(confidence_score=score, reason_codes=sorted(set(reason_codes)), components=components)
