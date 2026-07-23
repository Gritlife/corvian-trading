from app.quant.gamma_flip import estimate_gamma_flip
from app.quant.spot_shock import SpotShockPoint


def _point(spot, net):
    return SpotShockPoint(hypothetical_spot=spot, total_call_gex=0.0, total_put_gex=0.0, total_net_gex=net, total_absolute_gex=abs(net))


def test_single_crossing_is_interpolated():
    profile = [_point(95, -100.0), _point(100, 0.0 + 1e-9), _point(105, 100.0)]
    # Force a clean sign change between 95 and 105 with a crossing near 100
    profile = [_point(95, -100.0), _point(105, 100.0)]
    result = estimate_gamma_flip(profile, current_spot=100.0, sign_model="NAIVE_CONVENTION")
    assert result.primary_gamma_flip is not None
    assert 95.0 < result.primary_gamma_flip < 105.0
    assert len(result.all_gamma_crossings) == 1


def test_no_crossing_returns_null_not_fabricated():
    profile = [_point(95, 50.0), _point(100, 60.0), _point(105, 70.0)]
    result = estimate_gamma_flip(profile, current_spot=100.0, sign_model="NAIVE_CONVENTION")
    assert result.primary_gamma_flip is None
    assert result.all_gamma_crossings == []
    assert "NO_GAMMA_CROSSING" in result.reason_codes


def test_multiple_crossings_returns_all_and_picks_nearest_as_primary():
    profile = [_point(90, -10.0), _point(95, 10.0), _point(100, -10.0), _point(105, 10.0)]
    result = estimate_gamma_flip(profile, current_spot=100.0, sign_model="NAIVE_CONVENTION")
    assert len(result.all_gamma_crossings) >= 2
    assert result.primary_gamma_flip is not None
    # Primary should be the crossing closest to current spot (100).
    distances = [abs(c.spot_level - 100.0) for c in result.all_gamma_crossings]
    assert abs(result.primary_gamma_flip - 100.0) == min(distances)
    assert "MULTIPLE_GAMMA_CROSSINGS" in result.reason_codes


def test_interpolation_method_is_documented():
    profile = [_point(95, -100.0), _point(105, 100.0)]
    result = estimate_gamma_flip(profile, current_spot=100.0, sign_model="NAIVE_CONVENTION")
    assert result.interpolation_method == "linear_zero_crossing_on_spot_shock_grid"
