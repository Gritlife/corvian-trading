"""
OptionsDataProvider interface.

All vendor integrations (real or mock) implement this interface so the
quant core never depends on a specific vendor's API shape. New providers
are added by subclassing OptionsDataProvider — no changes to app.quant or
app.services are required.

Every provider must honestly self-report a ProviderStatus and a
ProviderCapabilities profile (section 6/7 of the v0.1.1 hardening spec)
so consumers never mistake a scaffold/experimental adapter for a
production-ready one, and so unsupported methods raise a typed
ProviderCapabilityUnsupported error instead of a raw NotImplementedError.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List

from app.core.enums import ProviderStatus
from app.core.errors import ProviderCapabilityUnsupported, ProviderUnavailable
from app.models.contract import RawOptionContract

# Backwards-compatible alias: v0.1 code raised/caught ProviderUnavailableError.
ProviderUnavailableError = ProviderUnavailable


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_underlying_quote: bool
    supports_full_chain: bool
    supports_contract_snapshot: bool
    supports_market_clock: bool
    required_env_vars: List[str]

    def as_dict(self) -> dict:
        return {
            "supports_underlying_quote": self.supports_underlying_quote,
            "supports_full_chain": self.supports_full_chain,
            "supports_contract_snapshot": self.supports_contract_snapshot,
            "supports_market_clock": self.supports_market_clock,
            "required_env_vars": self.required_env_vars,
        }


class MarketClock:
    def __init__(self, is_open: bool, session: str, as_of: datetime):
        self.is_open = is_open
        self.session = session  # "REGULAR", "PRE_MARKET", "AFTER_HOURS", "CLOSED"
        self.as_of = as_of


class OptionsDataProvider(ABC):
    """Abstract base for all options-chain data sources."""

    name: str = "abstract"
    status: ProviderStatus = ProviderStatus.SCAFFOLD_ONLY

    @classmethod
    def capabilities(cls) -> ProviderCapabilities:
        """Static capability declaration, callable WITHOUT instantiating
        the provider (so /v1/providers can report on providers that
        require credentials the current environment doesn't have)."""
        return ProviderCapabilities(
            supports_underlying_quote=False,
            supports_full_chain=False,
            supports_contract_snapshot=False,
            supports_market_clock=False,
            required_env_vars=[],
        )

    @abstractmethod
    def get_underlying_quote(self, symbol: str) -> dict:
        """Returns at least {'symbol', 'spot', 'timestamp'}."""
        raise NotImplementedError

    @abstractmethod
    def get_expirations(self, symbol: str) -> List[datetime]:
        raise NotImplementedError

    @abstractmethod
    def get_option_chain(self, symbol: str) -> List[RawOptionContract]:
        raise NotImplementedError

    @abstractmethod
    def get_contract_snapshot(self, option_symbol: str) -> RawOptionContract:
        raise NotImplementedError

    @abstractmethod
    def get_market_clock(self) -> MarketClock:
        raise NotImplementedError

    def unsupported(self, capability_name: str) -> ProviderCapabilityUnsupported:
        """Helper for providers to raise a typed, documented capability
        error instead of a bare NotImplementedError."""
        return ProviderCapabilityUnsupported(
            f"Provider '{self.name}' (status={self.status.value}) does not support '{capability_name}'.",
            details={"provider": self.name, "provider_status": self.status.value, "capability": capability_name},
        )
