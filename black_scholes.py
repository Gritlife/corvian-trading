"""
Black-Scholes gamma (DERIVED mathematics).

Gamma is identical for calls and puts under Black-Scholes, so option_type
does not enter the formula. This module is vectorized over numpy arrays for
performance on large chains (see app.quant.gex).

    d1 = [ln(S/K) + (r - q + 0.5*sigma^2) * T] / (sigma * sqrt(T))
    gamma = exp(-q*T) * phi(d1) / (S * sigma * sqrt(T))

where phi is the standard normal PDF.

Numerical floors (see app.core.config.Settings) are applied by the caller
(typically app.services.normalization) before contracts reach this module,
but this module also defends against zero/negative T and sigma directly so
it is safe to call in isolation (e.g. from tests or the spot-shock grid).
"""
from __future__ import annotations

import numpy as np

from app.core.config import settings

_SQRT_2PI = np.sqrt(2.0 * np.pi)


def _norm_pdf(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / _SQRT_2PI


def d1(
    spot: np.ndarray,
    strike: np.ndarray,
    time_to_expiration_years: np.ndarray,
    sigma: np.ndarray,
    risk_free_rate: np.ndarray,
    dividend_yield: np.ndarray,
) -> np.ndarray:
    s = np.asarray(spot, dtype=float)
    k = np.asarray(strike, dtype=float)
    t = np.clip(np.asarray(time_to_expiration_years, dtype=float), settings.min_time_to_expiration_years, None)
    sig = np.clip(np.asarray(sigma, dtype=float), settings.min_implied_vol, settings.max_implied_vol)
    r = np.asarray(risk_free_rate, dtype=float)
    q = np.asarray(dividend_yield, dtype=float)

    s_safe = np.clip(s, 1e-8, None)
    k_safe = np.clip(k, 1e-8, None)

    numerator = np.log(s_safe / k_safe) + (r - q + 0.5 * sig * sig) * t
    denominator = sig * np.sqrt(t)
    return numerator / denominator


def black_scholes_gamma(
    spot: np.ndarray,
    strike: np.ndarray,
    time_to_expiration_years: np.ndarray,
    sigma: np.ndarray,
    risk_free_rate: np.ndarray,
    dividend_yield: np.ndarray,
) -> np.ndarray:
    """Returns gamma_per_share (DERIVED), a scalar or numpy array.

    gamma_per_share is the change in an option's delta per $1 change in
    the underlying spot price, per share of underlying (not per contract).
    """
    s = np.asarray(spot, dtype=float)
    t = np.clip(np.asarray(time_to_expiration_years, dtype=float), settings.min_time_to_expiration_years, None)
    sig = np.clip(np.asarray(sigma, dtype=float), settings.min_implied_vol, settings.max_implied_vol)
    q = np.asarray(dividend_yield, dtype=float)

    _d1 = d1(spot, strike, time_to_expiration_years, sigma, risk_free_rate, dividend_yield)
    s_safe = np.clip(s, 1e-8, None)

    numerator = np.exp(-q * t) * _norm_pdf(_d1)
    denominator = s_safe * sig * np.sqrt(t)
    gamma = numerator / denominator
    return np.where(np.isfinite(gamma), gamma, 0.0)
