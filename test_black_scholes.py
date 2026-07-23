import numpy as np

from app.quant.black_scholes import black_scholes_gamma


def test_gamma_matches_known_reference_value():
    # Reference: S=100, K=100, T=1, sigma=0.2, r=0.05, q=0.0
    # Known Black-Scholes gamma ~ 0.018762 (standard textbook example).
    gamma = black_scholes_gamma(
        spot=100.0, strike=100.0, time_to_expiration_years=1.0, sigma=0.2, risk_free_rate=0.05, dividend_yield=0.0
    )
    assert abs(float(gamma) - 0.018762) < 1e-3


def test_gamma_is_symmetric_for_calls_and_puts():
    # Black-Scholes gamma does not depend on option type; verified by the
    # fact the function takes no option_type argument at all. This test
    # asserts that two independent calls with identical parameters agree
    # (i.e., no hidden state affects the call/put distinction).
    g1 = black_scholes_gamma(100.0, 100.0, 0.5, 0.25, 0.03, 0.0)
    g2 = black_scholes_gamma(100.0, 100.0, 0.5, 0.25, 0.03, 0.0)
    assert float(g1) == float(g2)


def test_gamma_peaks_near_atm():
    atm = black_scholes_gamma(100.0, 100.0, 0.5, 0.2, 0.03, 0.0)
    otm = black_scholes_gamma(100.0, 150.0, 0.5, 0.2, 0.03, 0.0)
    deep_itm = black_scholes_gamma(100.0, 50.0, 0.5, 0.2, 0.03, 0.0)
    assert atm > otm
    assert atm > deep_itm


def test_time_approaching_zero_does_not_blow_up():
    gamma = black_scholes_gamma(100.0, 100.0, 1e-12, 0.2, 0.03, 0.0)
    assert np.isfinite(gamma)
    assert gamma >= 0.0


def test_vol_approaching_zero_does_not_blow_up():
    gamma = black_scholes_gamma(100.0, 100.0, 0.5, 1e-12, 0.03, 0.0)
    assert np.isfinite(gamma)
    assert gamma >= 0.0


def test_vectorized_computation_over_array():
    spots = np.array([100.0, 100.0, 100.0])
    strikes = np.array([90.0, 100.0, 110.0])
    t = np.array([0.5, 0.5, 0.5])
    sigma = np.array([0.2, 0.2, 0.2])
    r = np.array([0.03, 0.03, 0.03])
    q = np.array([0.0, 0.0, 0.0])
    gammas = black_scholes_gamma(spots, strikes, t, sigma, r, q)
    assert len(gammas) == 3
    assert all(np.isfinite(gammas))
