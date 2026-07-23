"""
Deterministic synthetic sample-data generator with versioned scenarios.

All data produced here is SYNTHETIC and clearly marked as such via
data_source="mock_synthetic". Seeds are derived with SHA-256 (never
Python's built-in hash(), which is randomized per-process via
PYTHONHASHSEED and is NOT stable across processes/machines/restarts —
this was the root cause of v0.1's non-deterministic mock output).

Each named scenario below is a fixed, documented configuration designed
to exercise specific, known engine behavior (positive/negative/transition
regimes, single/multiple/no gamma crossings). Scenarios control OI
distribution via an `oi_bias_fn(strike, spot) -> (call_multiplier,
put_multiplier)` and a tighter noise band, so the intended structure
dominates over per-contract randomness while remaining fully
reproducible given the same (symbol, scenario) pair.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Tuple

import numpy as np

from app.core.enums import OptionType
from app.models.contract import RawOptionContract

SCENARIO_VERSION = "v1"

BiasFn = Callable[[float, float], Tuple[float, float]]


def stable_seed(*parts: str) -> int:
    """Derives a stable 32-bit seed from arbitrary string parts using
    SHA-256. Deterministic across processes, machines, and restarts —
    unlike Python's built-in hash(), which must never be used for this
    purpose because of per-process hash randomization (PYTHONHASHSEED).
    """
    joined = "|".join(parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


# --- Dealer-sign-agnostic OI bias functions (MODELED synthetic structure) ---


def bias_uniform_call_heavy(strike: float, spot: float) -> Tuple[float, float]:
    """Calls consistently heavier than puts at every strike. Under
    NAIVE_CONVENTION this keeps signed net GEX positive across the whole
    spot-shock grid -> deliberately produces NO zero crossing."""
    return 2.0, 0.5


def bias_uniform_put_heavy(strike: float, spot: float) -> Tuple[float, float]:
    """Puts consistently heavier than calls at every strike. Under
    NAIVE_CONVENTION this keeps signed net GEX negative across the whole
    spot-shock grid -> deliberately produces NO zero crossing."""
    return 0.5, 2.0


def bias_balanced(strike: float, spot: float) -> Tuple[float, float]:
    """Symmetric call/put OI -> near-zero net signed GEX -> TRANSITION."""
    return 1.0, 1.0


def bias_single_crossing(strike: float, spot: float) -> Tuple[float, float]:
    """Smooth strike-dependent tilt: call-heavy below spot, put-heavy
    above (a simplified stylized approximation of typical short-dated
    positioning). As the hypothetical spot in the shock grid moves, the
    weighted mixture of call-heavy vs put-heavy strikes shifts smoothly,
    producing exactly one genuine modeled zero crossing near the current
    spot under NAIVE_CONVENTION -- never fabricated, always a real
    interpolated crossing of the aggregate spot-shock profile."""
    m = (strike / spot) - 1.0
    tilt = math.tanh(m * 18.0)
    call_mult = 1.0 - tilt  # >1 below spot, <1 above spot
    put_mult = 1.0 + tilt  # <1 below spot, >1 above spot
    return max(0.15, call_mult), max(0.15, put_mult)


def bias_oscillating(strike: float, spot: float) -> Tuple[float, float]:
    """Alternates call-heavy/put-heavy by strike bucket, deliberately
    engineered to produce MULTIPLE zero crossings in the spot-shock
    profile as the grid shifts which alternating bucket dominates."""
    bucket = int(round((strike - spot) / (spot * 0.01)))
    if bucket % 2 == 0:
        return 1.8, 0.6
    return 0.6, 1.8


# --- Scenario registry ---
# Each entry fully determines a synthetic chain's structure. Changing
# SCENARIO_VERSION invalidates all cached/expected reproductions on
# purpose (it is part of the seed).

SPX_SCENARIOS: Dict[str, dict] = {
    "SPX_DEFAULT_DEMO": dict(
        spot=5425.35,
        strike_step=5.0,
        n_strikes_each_side=60,
        dtes=[0, 1, 2, 5, 9, 16, 30, 44, 65],
        base_iv=0.13,
        iv_skew_slope=-0.35,
        base_oi=4500,
        bias_fn=bias_single_crossing,
        oi_noise_range=(0.8, 1.2),
        description="Default SPX demo scenario: meaningful positive AND negative "
        "strike structure with a genuine single modeled gamma flip near spot.",
    ),
    # NOTE: SPX_POSITIVE_GAMMA / SPX_NEGATIVE_GAMMA / SPX_TRANSITION /
    # SPX_MULTIPLE_CROSSINGS / SPX_NO_CROSSING are intentionally smaller
    # than SPX_DEFAULT_DEMO (fewer strikes/expirations). They exist purely
    # to exercise specific regime/crossing behavior deterministically in
    # tests, not to demonstrate realistic chain depth -- SPX_DEFAULT_DEMO
    # (used by the CLI/offline demo and scripts/generate_sample_data.py)
    # is unchanged and carries full production-scale chain depth. Shrinking
    # these does not touch any quantitative formula; it only reduces
    # synthetic data volume for faster, still-fully-deterministic tests.
    "SPX_POSITIVE_GAMMA": dict(
        spot=5425.35,
        strike_step=5.0,
        n_strikes_each_side=15,
        dtes=[5, 30],
        base_iv=0.12,
        iv_skew_slope=-0.3,
        base_oi=4000,
        bias_fn=bias_uniform_call_heavy,
        oi_noise_range=(0.85, 1.15),
        description="Uniform call-heavy OI -> POSITIVE modeled regime, no crossing.",
    ),
    "SPX_NEGATIVE_GAMMA": dict(
        spot=5425.35,
        strike_step=5.0,
        n_strikes_each_side=15,
        dtes=[5, 30],
        base_iv=0.15,
        iv_skew_slope=-0.3,
        base_oi=4000,
        bias_fn=bias_uniform_put_heavy,
        oi_noise_range=(0.85, 1.15),
        description="Uniform put-heavy OI -> NEGATIVE modeled regime, no crossing.",
    ),
    "SPX_TRANSITION": dict(
        spot=5425.35,
        strike_step=5.0,
        n_strikes_each_side=15,
        dtes=[5, 30],
        base_iv=0.13,
        iv_skew_slope=-0.3,
        base_oi=4000,
        bias_fn=bias_balanced,
        oi_noise_range=(0.95, 1.05),
        description="Balanced call/put OI -> near-zero net GEX -> TRANSITION regime.",
    ),
    "SPX_MULTIPLE_CROSSINGS": dict(
        spot=5425.35,
        strike_step=5.0,
        n_strikes_each_side=35,
        dtes=[1, 9, 30],
        base_iv=0.13,
        iv_skew_slope=-0.2,
        base_oi=4000,
        bias_fn=bias_oscillating,
        oi_noise_range=(0.9, 1.1),
        description="Oscillating call/put dominance by strike bucket -> multiple "
        "genuine zero crossings in the spot-shock profile.",
    ),
    "SPX_NO_CROSSING": dict(
        spot=5425.35,
        strike_step=5.0,
        n_strikes_each_side=15,
        dtes=[9, 30],
        base_iv=0.13,
        iv_skew_slope=-0.3,
        base_oi=4000,
        bias_fn=bias_uniform_call_heavy,
        oi_noise_range=(0.85, 1.15),
        description="Uniform bias across the whole grid -> primary_gamma_flip must be null.",
    ),
}

TSLA_SCENARIOS: Dict[str, dict] = {
    "TSLA_DEFAULT_DEMO": dict(
        spot=176.55,
        strike_step=2.5,
        n_strikes_each_side=40,
        dtes=[1, 3, 8, 15, 29, 43, 71],
        base_iv=0.48,
        iv_skew_slope=-0.6,
        base_oi=1200,
        bias_fn=bias_single_crossing,
        oi_noise_range=(0.8, 1.2),
        description="Default TSLA demo scenario: engineered to contain a genuine "
        "single modeled gamma flip near spot for MTS-V30 demonstration purposes.",
    ),
    # NOTE: same rationale as the SPX block above -- these are lightweight
    # test fixtures, not production demo data. TSLA_DEFAULT_DEMO is
    # unchanged.
    "TSLA_WITH_VALID_FLIP": dict(
        spot=176.55,
        strike_step=2.5,
        n_strikes_each_side=15,
        dtes=[8, 29],
        base_iv=0.48,
        iv_skew_slope=-0.6,
        base_oi=1200,
        bias_fn=bias_single_crossing,
        oi_noise_range=(0.8, 1.2),
        description="Alias of TSLA_DEFAULT_DEMO structure, named explicitly for tests "
        "asserting a valid crossing exists.",
    ),
    "TSLA_POSITIVE_GAMMA": dict(
        spot=176.55,
        strike_step=2.5,
        n_strikes_each_side=12,
        dtes=[15, 29],
        base_iv=0.42,
        iv_skew_slope=-0.5,
        base_oi=1000,
        bias_fn=bias_uniform_call_heavy,
        oi_noise_range=(0.85, 1.15),
        description="Uniform call-heavy OI -> POSITIVE modeled regime, no crossing.",
    ),
    "TSLA_NEGATIVE_GAMMA": dict(
        spot=176.55,
        strike_step=2.5,
        n_strikes_each_side=12,
        dtes=[15, 29],
        base_iv=0.55,
        iv_skew_slope=-0.5,
        base_oi=1000,
        bias_fn=bias_uniform_put_heavy,
        oi_noise_range=(0.85, 1.15),
        description="Uniform put-heavy OI -> NEGATIVE modeled regime, no crossing.",
    ),
    "TSLA_TRANSITION": dict(
        spot=176.55,
        strike_step=2.5,
        n_strikes_each_side=12,
        dtes=[15, 29],
        base_iv=0.48,
        iv_skew_slope=-0.5,
        base_oi=1000,
        bias_fn=bias_balanced,
        oi_noise_range=(0.95, 1.05),
        description="Balanced call/put OI -> near-zero net GEX -> TRANSITION regime.",
    ),
    "TSLA_NO_CROSSING": dict(
        spot=176.55,
        strike_step=2.5,
        n_strikes_each_side=12,
        dtes=[15, 29],
        base_iv=0.48,
        iv_skew_slope=-0.5,
        base_oi=1000,
        bias_fn=bias_uniform_put_heavy,
        oi_noise_range=(0.85, 1.15),
        description="Uniform bias across the whole grid -> primary_gamma_flip must be null.",
    ),
}


def _make_expirations(as_of: datetime, dtes: List[int]) -> List[datetime]:
    """Expirations are anchored to market close (21:00 UTC ~ 4pm ET) on the
    target date, not to the literal as_of time-of-day. This avoids treating
    a legitimate 0DTE contract (expiring later today) as already expired
    when as_of is earlier in the trading day.
    """
    market_close = as_of.replace(hour=21, minute=0, second=0, microsecond=0)
    if market_close <= as_of:
        market_close = as_of + timedelta(minutes=5)
    return [market_close + timedelta(days=d) for d in dtes]


def generate_synthetic_chain(
    underlying_symbol: str,
    spot: float,
    as_of: datetime,
    strike_step: float,
    n_strikes_each_side: int,
    dtes: List[int],
    base_iv: float,
    iv_skew_slope: float,
    base_oi: int,
    seed: int,
    bias_fn: BiasFn = bias_balanced,
    oi_noise_range: Tuple[float, float] = (0.4, 1.6),
) -> List[RawOptionContract]:
    rng = np.random.default_rng(seed)

    strikes = [
        round(spot + i * strike_step, 2) for i in range(-n_strikes_each_side, n_strikes_each_side + 1)
    ]
    expirations = _make_expirations(as_of, dtes)

    contracts: List[RawOptionContract] = []
    for expiration in expirations:
        dte_days = max((expiration - as_of).total_seconds() / 86400.0, 0.0001)
        expiry_oi_scale = max(1.0, 3.0 - 0.05 * dte_days)

        for strike in strikes:
            moneyness = strike / spot
            skew = iv_skew_slope * (moneyness - 1.0)
            term_decay = 0.02 * np.sqrt(dte_days / 30.0)
            call_bias, put_bias = bias_fn(strike, spot)

            for option_type in (OptionType.CALL, OptionType.PUT):
                iv = max(0.03, base_iv + skew + term_decay + rng.normal(0, 0.01))

                distance_factor = np.exp(-((moneyness - 1.0) ** 2) / (2 * 0.03 ** 2))
                type_bias = call_bias if option_type == OptionType.CALL else put_bias
                oi = max(
                    0,
                    int(base_oi * expiry_oi_scale * distance_factor * type_bias * rng.uniform(*oi_noise_range)),
                )
                volume = max(0, int(oi * rng.uniform(0.05, 0.6)))

                intrinsic = (
                    max(spot - strike, 0.0) if option_type == OptionType.CALL else max(strike - spot, 0.0)
                )
                time_value = spot * iv * np.sqrt(max(dte_days, 0.25) / 365.0) * 0.4
                mid = max(0.01, intrinsic + time_value)
                spread = max(0.01, mid * 0.02)
                bid = round(max(0.0, mid - spread / 2), 2)
                ask = round(mid + spread / 2, 2)

                contracts.append(
                    RawOptionContract(
                        underlying_symbol=underlying_symbol,
                        option_symbol=(
                            f"{underlying_symbol}_{expiration.strftime('%y%m%d')}"
                            f"{'C' if option_type == OptionType.CALL else 'P'}{int(strike * 1000):08d}"
                        ),
                        option_type=option_type,
                        strike=strike,
                        expiration=expiration,
                        quote_timestamp=as_of,
                        underlying_spot=spot,
                        bid=bid,
                        ask=ask,
                        last_price=round((bid + ask) / 2, 2),
                        volume=float(volume),
                        open_interest=float(oi),
                        implied_volatility=round(float(iv), 4),
                        vendor_delta=None,
                        vendor_gamma=None,
                        vendor_theta=None,
                        vendor_vega=None,
                        risk_free_rate=0.045,
                        dividend_yield=0.013 if underlying_symbol == "SPX" else 0.0,
                        data_source="mock_synthetic",
                    )
                )
    return contracts


def generate_chain_for_scenario(
    underlying_symbol: str, scenario_name: str, as_of: datetime | None = None
) -> List[RawOptionContract]:
    """Generates a deterministic chain for a named scenario. The seed is
    derived purely from (underlying_symbol, scenario_name, SCENARIO_VERSION)
    via SHA-256, so the resulting chain structure is identical across
    processes, machines, and restarts. `as_of` only affects expiration
    anchoring/timestamps, never the OI/IV/strike structure itself, since
    the RNG seed does not depend on wall-clock time.
    """
    registry = SPX_SCENARIOS if underlying_symbol.upper() == "SPX" else TSLA_SCENARIOS
    if scenario_name not in registry:
        raise KeyError(
            f"Unknown scenario '{scenario_name}' for symbol '{underlying_symbol}'. "
            f"Available: {sorted(registry.keys())}"
        )
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    params = registry[scenario_name]
    seed = stable_seed(underlying_symbol.upper(), scenario_name, SCENARIO_VERSION)

    return generate_synthetic_chain(
        underlying_symbol=underlying_symbol.upper(),
        spot=params["spot"],
        as_of=as_of,
        strike_step=params["strike_step"],
        n_strikes_each_side=params["n_strikes_each_side"],
        dtes=params["dtes"],
        base_iv=params["base_iv"],
        iv_skew_slope=params["iv_skew_slope"],
        base_oi=params["base_oi"],
        seed=seed,
        bias_fn=params["bias_fn"],
        oi_noise_range=params["oi_noise_range"],
    )


def generate_spx_sample(as_of: datetime | None = None) -> List[RawOptionContract]:
    """Backwards-compatible entry point (used by SAMPLE_GENERATORS and
    scripts/generate_sample_data.py). Now maps to the default demo
    scenario instead of an unversioned generic random chain."""
    return generate_chain_for_scenario("SPX", "SPX_DEFAULT_DEMO", as_of)


def generate_tsla_sample(as_of: datetime | None = None) -> List[RawOptionContract]:
    """Backwards-compatible entry point. Now maps to the default demo
    scenario, which is engineered to contain a genuine gamma-flip
    crossing so the default MTS-V30 demonstration never shows a null
    flip (section 5 of the v0.1.1 hardening spec)."""
    return generate_chain_for_scenario("TSLA", "TSLA_DEFAULT_DEMO", as_of)


SAMPLE_GENERATORS = {
    "SPX": generate_spx_sample,
    "TSLA": generate_tsla_sample,
}
