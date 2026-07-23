from datetime import datetime, timedelta, timezone

from app.core.enums import SignModel
from app.services.asset_engine import build_asset_gamma
from app.tv.payloads import build_dashboard_payload, build_spx_tv_payload, build_symbol_tv_payload
from tests._shared import SHARED_AS_OF, SHARED_PROVIDER, SPX_FOUNDATION, TSLA_ASSET_RESULT

REQUIRED_SPX_FIELDS = {
    "schema_version", "engine_version", "snapshot_id", "symbol", "timestamp_utc", "timestamp_et",
    "source_data_timestamp", "calculation_timestamp", "spot", "market_gamma_regime", "gamma_gauge",
    "total_net_gex_usd_per_1pct_move", "total_absolute_gex_usd_per_1pct_move", "gamma_flip",
    "all_gamma_crossings", "positive_gamma_wall", "negative_gamma_pit",
    "nearest_positive_level_above_spot", "nearest_negative_level_below_spot",
    "top_positive_levels", "top_negative_levels", "histogram", "expiration_buckets",
    "zero_dte_contribution", "gex_over_time", "confidence_score", "confidence_reasons",
    "sign_model", "provider", "provider_status", "cache_age_seconds", "is_stale", "refresh_status",
}

REQUIRED_ASSET_FIELDS = {
    "schema_version", "engine_version", "snapshot_id", "symbol", "timestamp_utc", "timestamp_et",
    "source_data_timestamp", "calculation_timestamp", "spot", "gamma_regime", "gamma_gauge",
    "gamma_gauge_label", "net_gex_usd_per_1pct_move", "absolute_gex_usd_per_1pct_move", "gamma_flip",
    "all_gamma_crossings", "positive_gamma_wall", "negative_gamma_pit",
    "nearest_major_gamma_level_above", "nearest_major_gamma_level_below", "dealer_pressure",
    "expected_behavior", "acceleration_risk", "pinning_probability_estimate", "confidence_score",
    "confidence_reasons", "sign_model", "provider", "provider_status", "cache_age_seconds",
    "is_stale", "refresh_status",
}

# These payload-shape/histogram/dashboard tests only need *a* valid,
# fully-computed default-demo analysis -- they don't need a fresh
# computation each time, so they reuse the shared, session-computed-once
# SPX_FOUNDATION / TSLA_ASSET_RESULT (see tests/_shared.py) instead of
# re-running the full pipeline per test. This is a test-performance
# optimization only; it does not change what is being asserted.
_SPX_PAYLOAD = build_spx_tv_payload(SPX_FOUNDATION)
_TSLA_PAYLOAD = build_symbol_tv_payload(TSLA_ASSET_RESULT)


def test_spx_tv_payload_has_all_required_fields():
    missing = REQUIRED_SPX_FIELDS - set(_SPX_PAYLOAD.keys())
    assert not missing, f"Missing SPX TV payload fields: {missing}"
    assert _SPX_PAYLOAD["schema_version"] == "1.0"
    assert _SPX_PAYLOAD["engine_version"] == "0.1.1"


def test_asset_tv_payload_has_all_required_fields():
    missing = REQUIRED_ASSET_FIELDS - set(_TSLA_PAYLOAD.keys())
    assert not missing, f"Missing asset TV payload fields: {missing}"


def test_spx_histogram_bounds_and_sign_correctness_and_ordering():
    histogram = _SPX_PAYLOAD["histogram"]
    assert len(histogram) > 0

    strikes = [row["strike"] for row in histogram]
    assert strikes == sorted(strikes), "histogram must be ascending by strike"

    for row in histogram:
        assert -1.0 <= row["normalized_bar"] <= 1.0
        if row["net_gex_usd_per_1pct_move"] > 0:
            assert row["side"] == "POSITIVE"
        elif row["net_gex_usd_per_1pct_move"] < 0:
            assert row["side"] == "NEGATIVE"


def test_snapshot_id_present_and_unique_per_analysis_call():
    # This test specifically needs two independent computations, so it
    # cannot reuse a single shared result -- but it does reuse
    # SHARED_PROVIDER (whose per-symbol chain is already generated and
    # cached), so only the analysis pipeline itself re-runs twice, not
    # the raw synthetic chain generation.
    r1 = build_asset_gamma(SHARED_PROVIDER, "TSLA", sign_model=SignModel.NAIVE_CONVENTION, as_of=SHARED_AS_OF)
    r2 = build_asset_gamma(SHARED_PROVIDER, "TSLA", sign_model=SignModel.NAIVE_CONVENTION, as_of=SHARED_AS_OF)
    assert r1.analysis.snapshot_id
    assert r2.analysis.snapshot_id
    assert r1.analysis.snapshot_id != r2.analysis.snapshot_id  # two independent computations


def test_gamma_gauge_components_present_and_bounded():
    a = TSLA_ASSET_RESULT.analysis
    expected_keys = {
        "signed_ratio_component", "distance_to_flip_component", "near_spot_concentration_component",
        "confidence_adjustment", "zero_dte_component", "local_gamma_slope_component",
    }
    assert expected_keys <= set(a.gamma_gauge_components.keys())
    assert -100.0 <= a.gamma_gauge <= 100.0


def test_dashboard_synchronized_true_when_snapshots_are_close():
    dashboard = build_dashboard_payload(_SPX_PAYLOAD, _TSLA_PAYLOAD)
    assert dashboard["synchronization"]["synchronized"] is True
    assert dashboard["synchronization"]["timestamp_difference_seconds"] < 30.0


def test_dashboard_synchronized_false_when_snapshots_are_far_apart():
    # Artificially push the asset snapshot's calculation_timestamp far in the past.
    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    asset_payload = dict(_TSLA_PAYLOAD)
    asset_payload["calculation_timestamp"] = old_ts

    dashboard = build_dashboard_payload(_SPX_PAYLOAD, asset_payload)
    assert dashboard["synchronization"]["synchronized"] is False
    assert dashboard["synchronization"]["timestamp_difference_seconds"] >= 30.0
