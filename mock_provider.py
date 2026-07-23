"""
MockOptionsDataProvider — mandatory offline provider.

Produces deterministic synthetic data for SPX and TSLA via versioned
scenarios (see app.providers.sample_data). Fully offline, no credentials
required. Freezes "as_of" at construction time so repeated calls within a
session are internally consistent. Scenario selection lets tests and
tools exercise specific known engine behaviors (positive/negative/
transition regimes, single/multiple/no gamma crossings) deterministically
across processes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.enums import ProviderStatus
from app.providers.base import MarketClock, OptionsDataProvider, ProviderCapabilities, ProviderUnavailableError
from app.providers.sample_data import (
    SPX_SCENARIOS,
    TSLA_SCENARIOS,
    generate_chain_for_scenario,
)
from app.models.contract import RawOptionContract

DEFAULT_SCENARIOS = {
    "SPX": "SPX_DEFAULT_DEMO",
    "TSLA": "TSLA_DEFAULT_DEMO",
}

_REGISTRIES = {"SPX": SPX_SCENARIOS, "TSLA": TSLA_SCENARIOS}


class MockOptionsDataProvider(OptionsDataProvider):
    name = "mock"
    status = ProviderStatus.MOCK

    def __init__(self, as_of: datetime | None = None, scenarios: Optional[Dict[str, str]] = None):
        """
        scenarios: optional override mapping, e.g. {"SPX": "SPX_NO_CROSSING",
        "TSLA": "TSLA_NEGATIVE_GAMMA"}. Any symbol not present falls back to
        DEFAULT_SCENARIOS.
        """
        self._as_of = as_of or datetime.now(timezone.utc)
        self._scenarios = dict(DEFAULT_SCENARIOS)
        if scenarios:
            self._scenarios.update({k.upper(): v for k, v in scenarios.items()})
        self._chain_cache: Dict[str, List[RawOptionContract]] = {}

    @classmethod
    def capabilities(cls) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_underlying_quote=True,
            supports_full_chain=True,
            supports_contract_snapshot=True,
            supports_market_clock=True,
            required_env_vars=[],
        )

    def available_scenarios(self, symbol: str) -> List[str]:
        registry = _REGISTRIES.get(symbol.upper())
        if registry is None:
            return []
        return sorted(registry.keys())

    def active_scenario(self, symbol: str) -> Optional[str]:
        return self._scenarios.get(symbol.upper())

    def _get_chain(self, symbol: str) -> List[RawOptionContract]:
        symbol = symbol.upper()
        if symbol not in self._chain_cache:
            registry = _REGISTRIES.get(symbol)
            if registry is None:
                raise ProviderUnavailableError(
                    f"MockOptionsDataProvider has no synthetic dataset for symbol '{symbol}'. "
                    f"Supported: {list(_REGISTRIES.keys())}"
                )
            scenario_name = self._scenarios.get(symbol, DEFAULT_SCENARIOS.get(symbol))
            self._chain_cache[symbol] = generate_chain_for_scenario(symbol, scenario_name, self._as_of)
        return self._chain_cache[symbol]

    def get_underlying_quote(self, symbol: str) -> dict:
        chain = self._get_chain(symbol)
        spot = chain[0].underlying_spot if chain else None
        return {"symbol": symbol.upper(), "spot": spot, "timestamp": self._as_of}

    def get_expirations(self, symbol: str) -> List[datetime]:
        chain = self._get_chain(symbol)
        return sorted({c.expiration for c in chain})

    def get_option_chain(self, symbol: str) -> List[RawOptionContract]:
        return list(self._get_chain(symbol))

    def get_contract_snapshot(self, option_symbol: str) -> RawOptionContract:
        for chain in self._chain_cache.values():
            for c in chain:
                if c.option_symbol == option_symbol:
                    return c
        for symbol in _REGISTRIES:
            for c in self._get_chain(symbol):
                if c.option_symbol == option_symbol:
                    return c
        raise ProviderUnavailableError(f"Unknown option_symbol '{option_symbol}' in mock data.")

    def get_market_clock(self) -> MarketClock:
        is_weekend = self._as_of.weekday() >= 5
        return MarketClock(
            is_open=not is_weekend,
            session="REGULAR" if not is_weekend else "CLOSED",
            as_of=self._as_of,
        )
