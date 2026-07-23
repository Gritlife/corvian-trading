"""
Provider factory.

Selects an OptionsDataProvider based on EGE_PROVIDER. Always falls back to
MockOptionsDataProvider if a real provider cannot be constructed (e.g.
missing credentials), so the engine never fails to start.
"""
from __future__ import annotations

import logging
from typing import List

from app.core.config import settings
from app.providers.base import OptionsDataProvider
from app.core.errors import ProviderUnavailable
from app.providers.mock_provider import MockOptionsDataProvider
from app.providers.polygon_provider import PolygonOptionsDataProvider

logger = logging.getLogger(__name__)

_PROVIDER_CLASSES = {
    "mock": MockOptionsDataProvider,
    "polygon": PolygonOptionsDataProvider,
}


def get_provider() -> OptionsDataProvider:
    provider_name = (settings.active_provider or "mock").lower()

    if provider_name == "mock":
        return MockOptionsDataProvider()

    if provider_name == "polygon":
        try:
            return PolygonOptionsDataProvider()
        except ProviderUnavailable as exc:
            logger.warning("Polygon provider unavailable (%s); falling back to mock provider.", exc)
            return MockOptionsDataProvider()

    logger.warning("Unknown EGE_PROVIDER '%s'; falling back to mock provider.", provider_name)
    return MockOptionsDataProvider()


def list_provider_metadata() -> List[dict]:
    """Static capability/status metadata for every known provider class,
    callable without instantiating providers that require credentials
    the current environment may not have (section 6/7)."""
    active_name = (settings.active_provider or "mock").lower()
    results = []
    for name, cls in _PROVIDER_CLASSES.items():
        caps = cls.capabilities()
        is_active = name == active_name
        health_status = None
        if name == "mock":
            health_status = "OK"
        elif name == "polygon":
            health_status = "OK" if settings.provider_api_key else "MISSING_CREDENTIALS"
        results.append(
            {
                "provider": name,
                "status": cls.status.value,
                "capabilities": caps.as_dict(),
                "active": is_active,
                "health_status": health_status,
                "last_successful_request_timestamp": None,
            }
        )
    return results

