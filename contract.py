"""
Canonical normalized option contract schema.

Every raw vendor payload must be converted into a RawOptionContract before
any gamma mathematics is applied. Validation happens in
app.services.normalization, which annotates each contract with
data_quality_flags rather than silently discarding bad rows.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.enums import DataQualityFlag, OptionType


class RawOptionContract(BaseModel):
    """OBSERVED + minimal derived fields for a single option contract quote."""

    model_config = {"frozen": False}

    # --- Identity (OBSERVED) ---
    underlying_symbol: str
    option_symbol: str
    option_type: OptionType
    strike: float
    expiration: datetime  # timezone-aware, UTC
    quote_timestamp: datetime  # timezone-aware, UTC

    # --- Market data (OBSERVED) ---
    underlying_spot: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    last_price: Optional[float] = None
    volume: Optional[float] = None
    open_interest: Optional[float] = None
    implied_volatility: Optional[float] = None

    # --- Vendor-provided Greeks if available (OBSERVED, vendor-sourced) ---
    vendor_delta: Optional[float] = None
    vendor_gamma: Optional[float] = None
    vendor_theta: Optional[float] = None
    vendor_vega: Optional[float] = None

    # --- Model parameters (DERIVED/MODELED context, not per-contract observed) ---
    risk_free_rate: float = 0.045
    dividend_yield: float = 0.0

    # --- DERIVED ---
    time_to_expiration_years: Optional[float] = None
    midpoint: Optional[float] = None

    # --- Provenance ---
    data_source: str = "unknown"
    data_quality_flags: List[DataQualityFlag] = Field(default_factory=list)

    @field_validator("strike")
    @classmethod
    def strike_must_be_positive_finite(cls, v: float) -> float:
        return v

    def compute_midpoint(self) -> Optional[float]:
        if self.bid is not None and self.ask is not None and self.bid >= 0 and self.ask >= 0:
            return (self.bid + self.ask) / 2.0
        return self.last_price

    def is_finite(self) -> bool:
        vals = [
            self.strike,
            self.bid,
            self.ask,
            self.last_price,
            self.volume,
            self.open_interest,
            self.implied_volatility,
        ]
        for v in vals:
            if v is None:
                continue
            if not math.isfinite(v):
                return False
        return True


class NormalizedOptionContract(BaseModel):
    """Fully normalized, validated contract ready for gamma mathematics.

    Distinct from RawOptionContract: this guarantees time_to_expiration_years,
    midpoint, and an effective (floored) implied_volatility are populated so
    downstream quant modules never need to special-case None.
    """

    underlying_symbol: str
    option_symbol: str
    option_type: OptionType
    strike: float
    expiration: datetime
    quote_timestamp: datetime

    underlying_spot: float
    bid: Optional[float]
    ask: Optional[float]
    last_price: Optional[float]
    midpoint: Optional[float]
    volume: float
    open_interest: float

    implied_volatility_observed: Optional[float]  # OBSERVED, may be None
    implied_volatility_effective: float  # DERIVED, floored/imputed if needed

    vendor_delta: Optional[float]
    vendor_gamma: Optional[float]
    vendor_theta: Optional[float]
    vendor_vega: Optional[float]

    risk_free_rate: float
    dividend_yield: float
    time_to_expiration_years: float  # DERIVED, floored

    data_source: str
    data_quality_flags: List[DataQualityFlag] = Field(default_factory=list)
    is_rejected: bool = False
    rejection_reasons: List[str] = Field(default_factory=list)
