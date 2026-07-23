import numpy as np

from app.quant.gex import gex_usd_per_1pct_move, gex_usd_per_1usd_move, position_gamma_per_dollar


def test_position_gamma_per_dollar_units():
    gamma_per_share = np.array([0.05])
    oi = np.array([1000.0])
    multiplier = 100
    result = position_gamma_per_dollar(gamma_per_share, oi, multiplier)
    assert result[0] == 0.05 * 1000.0 * 100


def test_gex_usd_per_1pct_move_formula():
    gamma_per_share = np.array([0.05])
    oi = np.array([1000.0])
    multiplier = 100
    spot = np.array([200.0])
    result = gex_usd_per_1pct_move(gamma_per_share, oi, multiplier, spot)
    expected = 0.05 * 1000.0 * 100 * (200.0 ** 2) * 0.01
    assert np.isclose(result[0], expected)


def test_gex_usd_per_1usd_move_formula():
    gamma_per_share = np.array([0.05])
    oi = np.array([1000.0])
    multiplier = 100
    spot = np.array([200.0])
    result = gex_usd_per_1usd_move(gamma_per_share, oi, multiplier, spot)
    expected = 0.05 * 1000.0 * 100 * 200.0
    assert np.isclose(result[0], expected)


def test_1pct_and_1usd_conventions_are_never_equal_for_nontrivial_spot():
    gamma_per_share = np.array([0.05])
    oi = np.array([1000.0])
    multiplier = 100
    spot = np.array([200.0])
    a = gex_usd_per_1pct_move(gamma_per_share, oi, multiplier, spot)
    b = gex_usd_per_1usd_move(gamma_per_share, oi, multiplier, spot)
    assert not np.isclose(a[0], b[0])
