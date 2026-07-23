from app.core.enums import SignModel
from app.providers.mock_provider import MockOptionsDataProvider
from app.services import snapshot_service
from app.services.cache import analysis_cache, tv_payload_cache


def _reset_caches():
    analysis_cache.clear()
    tv_payload_cache.clear()


def test_spx_tv_payload_reports_fresh_on_first_call():
    _reset_caches()
    provider = MockOptionsDataProvider()
    payload = snapshot_service.get_spx_tv_payload_cached(provider)
    assert payload["refresh_status"] == "FRESH"
    assert payload["is_stale"] is False


def test_stale_fallback_status_propagates_through_tv_cache_layer():
    """Regression test: a fresh TV-payload-cache entry built on top of a
    stale analysis snapshot must still report STALE_FALLBACK overall —
    the outer cache layer being 'fresh' must never mask a stale inner
    analysis (this was a real bug found and fixed during v0.1.1
    hardening: the outer status previously overwrote the inner one)."""
    _reset_caches()
    provider = MockOptionsDataProvider()

    good_payload = snapshot_service.get_spx_tv_payload_cached(provider)
    assert good_payload["refresh_status"] == "FRESH"

    def broken(symbol):
        raise RuntimeError("simulated provider outage")

    provider.get_option_chain = broken

    akey = snapshot_service._analysis_key("SPX", SignModel.NAIVE_CONVENTION)
    tkey = snapshot_service._tv_key("SPX", SignModel.NAIVE_CONVENTION)
    analysis_cache._store[akey].created_at -= 9999
    tv_payload_cache._store[tkey].created_at -= 9999

    stale_payload = snapshot_service.get_spx_tv_payload_cached(provider)

    assert stale_payload["refresh_status"] == "STALE_FALLBACK"
    assert stale_payload["is_stale"] is True
    assert stale_payload["snapshot_id"] == good_payload["snapshot_id"], (
        "last known good snapshot must be preserved, not blanked, on refresh failure"
    )
