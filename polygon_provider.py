"""
Polygon.io options-chain provider adapter.

This adapter is ISOLATED behind the OptionsDataProvider interface so the
quant core has zero dependency on Polygon's API shape. It requires
EGE_PROVIDER_API_KEY (and optionally EGE_PROVIDER_BASE_URL) to be set; if
credentials are missing, construction raises ProviderUnavailableError
immediately with a clear message rather than failing deep inside a
request. The engine as a whole never depends on this adapter — it always
has the mock provider as a fallback (see app.providers.factory).

Endpoint shapes for Polygon's options snapshot/chain APIs are
version-sensitive and may change; treat the request builders below as a
documented starting point that should be verified against current
Polygon API documentation before enabling in production. Do not assume
these paths are correct without verifying against Polygon's current docs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import httpx

from app.core.config import settings
from app.core.enums import OptionType, ProviderStatus
from app.models.contract import RawOptionContract
from app.providers.base import MarketClock, OptionsDataProvider, ProviderCapabilities, ProviderUnavailableError

DEFAULT_BASE_URL = "https://api.polygon.io"


class PolygonOptionsDataProvider(OptionsDataProvider):
    name = "polygon"
    # Honest classification (section 6): underlying quote / full chain /
    # market clock endpoints are implemented against Polygon's documented
    # API shape but UNVERIFIED against a live account in this build;
    # get_contract_snapshot is a genuine gap (see below). EXPERIMENTAL,
    # not PRODUCTION_READY, until verified end-to-end against live data.
    status = ProviderStatus.EXPERIMENTAL

    @classmethod
    def capabilities(cls) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_underlying_quote=True,
            supports_full_chain=True,
            supports_contract_snapshot=False,
            supports_market_clock=True,
            required_env_vars=["EGE_PROVIDER_API_KEY"],
        )

    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float | None = None):
        self.api_key = api_key or settings.provider_api_key
        if not self.api_key:
            raise ProviderUnavailableError(
                "Polygon provider requires EGE_PROVIDER_API_KEY to be set. "
                "Falling back to MockOptionsDataProvider is recommended if unset."
            )
        self.base_url = base_url or settings.provider_base_url or DEFAULT_BASE_URL
        self.timeout = timeout or settings.provider_timeout_seconds
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def _get(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        params["apiKey"] = self.api_key
        try:
            resp = self._client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Polygon request failed for {path}: {exc}") from exc

    def get_underlying_quote(self, symbol: str) -> dict:
        # NOTE: verify against current Polygon docs; this targets the
        # v2 last-trade / snapshot family of endpoints conceptually.
        data = self._get(f"/v2/last/trade/{symbol}")
        price = data.get("results", {}).get("p")
        return {"symbol": symbol, "spot": price, "timestamp": datetime.now(timezone.utc)}

    def get_expirations(self, symbol: str) -> List[datetime]:
        data = self._get("/v3/reference/options/contracts", params={"underlying_ticker": symbol, "limit": 1000})
        raw_dates = {item.get("expiration_date") for item in data.get("results", []) if item.get("expiration_date")}
        return sorted(datetime.fromisoformat(d).replace(tzinfo=timezone.utc) for d in raw_dates)

    def get_option_chain(self, symbol: str) -> List[RawOptionContract]:
        data = self._get(
            f"/v3/snapshot/options/{symbol}",
            params={"limit": 250},
        )
        results = data.get("results", [])
        now = datetime.now(timezone.utc)
        contracts: List[RawOptionContract] = []
        for item in results:
            details = item.get("details", {})
            greeks = item.get("greeks", {})
            quote = item.get("last_quote", {})
            day = item.get("day", {})
            underlying = item.get("underlying_asset", {})

            option_type_raw = (details.get("contract_type") or "").upper()
            if option_type_raw not in ("CALL", "PUT"):
                continue

            expiration_raw = details.get("expiration_date")
            if not expiration_raw:
                continue

            contracts.append(
                RawOptionContract(
                    underlying_symbol=symbol,
                    option_symbol=details.get("ticker", f"{symbol}_UNKNOWN"),
                    option_type=OptionType(option_type_raw),
                    strike=float(details.get("strike_price", 0.0)),
                    expiration=datetime.fromisoformat(expiration_raw).replace(tzinfo=timezone.utc),
                    quote_timestamp=now,
                    underlying_spot=underlying.get("price"),
                    bid=quote.get("bid"),
                    ask=quote.get("ask"),
                    last_price=day.get("close"),
                    volume=day.get("volume"),
                    open_interest=item.get("open_interest"),
                    implied_volatility=item.get("implied_volatility"),
                    vendor_delta=greeks.get("delta"),
                    vendor_gamma=greeks.get("gamma"),
                    vendor_theta=greeks.get("theta"),
                    vendor_vega=greeks.get("vega"),
                    risk_free_rate=settings.risk_free_rate,
                    dividend_yield=settings.dividend_yield_default,
                    data_source="polygon",
                )
            )
        return contracts

    def get_contract_snapshot(self, option_symbol: str) -> RawOptionContract:
        # Genuine capability gap: Polygon's single-contract snapshot path
        # requires the underlying ticker, which this method's signature
        # does not provide. Rather than raise a raw NotImplementedError,
        # this is exposed as a typed, documented capability limitation
        # (section 6) so callers can branch on it instead of crashing.
        raise self.unsupported("get_contract_snapshot")

    def get_market_clock(self) -> MarketClock:
        data = self._get("/v1/marketstatus/now")
        market = data.get("market", "closed")
        return MarketClock(
            is_open=(market == "open"),
            session=market.upper(),
            as_of=datetime.now(timezone.utc),
        )

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass
