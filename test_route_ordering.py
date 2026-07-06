"""
Regression test for a real routing bug found before the v0.1.1 baseline
lock: /v1/tv/{symbol} was registered before /v1/tv/manifest. FastAPI/
Starlette matches path operations in registration order, and {symbol} is
an unconstrained single-segment parameter that greedily matches literal
segments like "manifest" -- so GET /v1/tv/manifest was being routed to
get_tv_symbol("manifest") instead of get_tv_manifest(), which would
either 404/500 (manifest is not a supported symbol) or silently return
asset-shaped data under the manifest path.

Fixed by moving /v1/tv/manifest (and /v1/tv/dashboard/{symbol}, as a
defensive convention) above the generic /v1/tv/{symbol} catch-all in
app/api/routes.py. This test uses FastAPI's real TestClient so it
exercises the actual route registration order, not a manually-addressed
handler lookup.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_tv_manifest_returns_200():
    response = client.get("/v1/tv/manifest")
    assert response.status_code == 200


def test_tv_manifest_returns_manifest_shape_not_symbol_shape():
    response = client.get("/v1/tv/manifest")
    body = response.json()

    # Manifest-specific fields must be present.
    assert body.get("schema_version") == "1.0"
    assert "supported_symbols" in body
    assert "market_foundation_endpoint" in body
    assert "dashboard_endpoint_pattern" in body

    # Fields that only exist on the per-symbol TV payload must be absent
    # -- if the {symbol} route had swallowed "manifest" as a symbol, some
    # of these would appear (or the request would 404/500 instead).
    asset_only_fields = {"gamma_flip", "dealer_pressure", "acceleration_risk", "pinning_probability_estimate"}
    assert not (asset_only_fields & set(body.keys()))


def test_tv_symbol_route_still_works_for_real_symbols():
    """Confirms the reordering didn't break the actual {symbol} route."""
    response = client.get("/v1/tv/TSLA")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TSLA"
    assert "gamma_flip" in body


def test_tv_dashboard_route_still_works_after_reordering():
    response = client.get("/v1/tv/dashboard/TSLA")
    assert response.status_code == 200
    body = response.json()
    assert "market_foundation" in body
    assert "individual_asset" in body
    assert "synchronization" in body


def test_unsupported_symbol_still_returns_typed_404_not_confused_with_manifest():
    response = client.get("/v1/tv/AAPL")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "SYMBOL_UNSUPPORTED"
