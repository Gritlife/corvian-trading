"""
Shared test fixtures computed ONCE per test session (module-level code
runs exactly once per process, on first import, regardless of how many
test files import from here). This exists purely to avoid redundantly
re-running the full normalize -> gamma -> GEX -> spot-shock -> flip ->
gauge -> confidence pipeline for the same default-demo SPX/TSLA analysis
across many independent test files -- it does not change the pipeline,
the math, or any engine default in any way. Tests that specifically need
their own fresh/independent computation (e.g. verifying two calls
produce different snapshot_ids, or testing a different as_of/sign_model)
still build their own provider/result rather than using these shared
objects.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.enums import SignModel
from app.providers.mock_provider import MockOptionsDataProvider
from app.services.asset_engine import build_asset_gamma
from app.services.spx_foundation import build_spx_foundation

SHARED_AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)

# A single shared provider instance: its internal per-symbol chain cache
# means even code that intentionally re-runs analysis against this same
# provider (e.g. testing distinct snapshot_ids) skips regenerating the
# raw synthetic chain a second time.
SHARED_PROVIDER = MockOptionsDataProvider(as_of=SHARED_AS_OF)

SPX_FOUNDATION = build_spx_foundation(SHARED_PROVIDER, sign_model=SignModel.NAIVE_CONVENTION, as_of=SHARED_AS_OF)
TSLA_ASSET_RESULT = build_asset_gamma(SHARED_PROVIDER, "TSLA", sign_model=SignModel.NAIVE_CONVENTION, as_of=SHARED_AS_OF)
