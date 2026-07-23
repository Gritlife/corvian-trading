import random

from app.quant.gamma_gauge import compute_gamma_gauge
from app.tv.histogram import build_histogram


def test_histogram_normalized_bars_within_bounds():
    strike_records = [
        {"strike": 95.0, "net_gex": -500.0},
        {"strike": 100.0, "net_gex": 1000.0},
        {"strike": 105.0, "net_gex": -1000.0},
    ]
    histogram = build_histogram(strike_records, spot=100.0)
    for row in histogram:
        assert -1.0 <= row["normalized_bar"] <= 1.0
    # The largest-magnitude strike(s) should hit +/-1.0 exactly.
    bars = {row["strike"]: row["normalized_bar"] for row in histogram}
    assert bars[100.0] == 1.0
    assert bars[105.0] == -1.0


def test_histogram_sides_and_ranks():
    strike_records = [
        {"strike": 100.0, "net_gex": 500.0},
        {"strike": 105.0, "net_gex": -1000.0},
        {"strike": 110.0, "net_gex": 0.0},
    ]
    histogram = build_histogram(strike_records, spot=100.0)
    by_strike = {r["strike"]: r for r in histogram}
    assert by_strike[100.0]["side"] == "POSITIVE"
    assert by_strike[105.0]["side"] == "NEGATIVE"
    assert by_strike[110.0]["side"] == "NEUTRAL"
    assert by_strike[105.0]["rank_by_absolute_gex"] == 1  # largest absolute value


def test_gamma_gauge_stays_within_bounds_across_random_inputs():
    random.seed(0)
    for _ in range(200):
        net_gex = random.uniform(-1e10, 1e10)
        total_abs = random.uniform(1, 1e10)
        spot = random.uniform(1, 10000)
        flip = random.choice([None, random.uniform(1, 10000)])
        zero_dte = random.uniform(0, total_abs)
        near_spot = random.uniform(0, total_abs)
        conf = random.uniform(0, 1)
        result = compute_gamma_gauge(net_gex, total_abs, spot, flip, zero_dte, near_spot, conf)
        assert -100.0 <= result.gamma_gauge <= 100.0


def test_gamma_gauge_sign_matches_net_gex_sign_when_weight_positive():
    result_pos = compute_gamma_gauge(
        net_gex=1000.0, total_absolute_gex=1000.0, spot=100.0, gamma_flip=None,
        zero_dte_absolute_gex=0.0, near_spot_absolute_gex=0.0, sign_confidence=0.5,
    )
    result_neg = compute_gamma_gauge(
        net_gex=-1000.0, total_absolute_gex=1000.0, spot=100.0, gamma_flip=None,
        zero_dte_absolute_gex=0.0, near_spot_absolute_gex=0.0, sign_confidence=0.5,
    )
    assert result_pos.gamma_gauge > 0
    assert result_neg.gamma_gauge < 0
