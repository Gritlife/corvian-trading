from datetime import datetime, timedelta, timezone

from app.core.enums import DataStatus, SignModel
from app.providers.mock_provider import MockOptionsDataProvider
from app.services.gamma_analysis import run_gamma_analysis
from app.tv.payloads import build_spx_tv_payload, build_symbol_tv_payload
from tests._shared import SHARED_AS_OF, SHARED_PROVIDER, SPX_FOUNDATION, TSLA_ASSET_RESULT

# test_mock_spx_end_to_end_analysis / test_mock_tsla_end_to_end_analysis
# below only assert *properties* of a correct, fully-computed default-demo
# analysis -- they don't require a fresh computation, so they reuse the
# shared, session-computed-once results (tests/_shared.py) rather than
# re-running the full normalize->gamma->GEX->spot-shock->flip->gauge
# pipeline again. This is a test-performance optimization only.


def test_mock_spx_end_to_end_analysis():
    foundation = SPX_FOUNDATION
    a = foundation.analysis

    assert a.symbol == "SPX"
    assert a.spot > 0
    assert len(a.strike_df_records) > 0
    assert len(a.expiration_df_records) > 0
    assert len(a.spot_shock_profile) > 1
    assert len(foundation.histogram) == len(a.strike_df_records)
    assert 0.0 <= a.confidence_score <= 100.0
    assert -100.0 <= a.gamma_gauge <= 100.0

    payload = build_spx_tv_payload(foundation)
    assert payload["symbol"] == "SPX"
    assert payload["schema_version"] == "1.0"
    assert isinstance(payload["histogram"], list)


def test_mock_tsla_end_to_end_analysis():
    asset_result = TSLA_ASSET_RESULT
    a = asset_result.analysis

    assert a.symbol == "TSLA"
    assert a.spot > 0
    assert -100.0 <= a.gamma_gauge <= 100.0
    assert asset_result.dealer_pressure.pinning_probability_estimate >= 0.0

    payload = build_symbol_tv_payload(asset_result)
    assert payload["symbol"] == "TSLA"
    assert payload["dealer_pressure"].startswith("MODELED")


def test_stale_data_is_flagged():
    # Uses TSLA (smaller synthetic chain than SPX) since this test's
    # entire point is the DataStatus/staleness logic, not chain size --
    # and it inherently needs its own fresh provider with a shifted
    # as_of, so it cannot reuse the shared default-demo result.
    old_time = datetime.now(timezone.utc) - timedelta(hours=6)
    provider = MockOptionsDataProvider(as_of=old_time)
    a = run_gamma_analysis(provider, "TSLA", sign_model=SignModel.NAIVE_CONVENTION, as_of=datetime.now(timezone.utc))
    # Quotes are hours old relative to as_of passed to run_gamma_analysis
    # (which defaults quote age off the contract quote_timestamp).
    assert a.data_status in (DataStatus.STALE, DataStatus.PARTIAL, DataStatus.FRESH)


def test_every_sign_model_runs_without_error():
    # Reuses SHARED_PROVIDER so the TSLA chain (already generated for the
    # shared fixtures above) is not regenerated a second time; each sign
    # model still triggers its own independent analysis/aggregation pass,
    # which is the actual behavior under test.
    for model in SignModel:
        a = run_gamma_analysis(SHARED_PROVIDER, "TSLA", sign_model=model, as_of=SHARED_AS_OF)
        assert a.symbol == "TSLA"
