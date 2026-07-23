from datetime import datetime, timedelta, timezone

import pandas as pd

from app.core.enums import SignModel
from app.quant.gamma import apply_sign_and_signed_gex, compute_contract_gamma
from app.quant.spot_shock import build_spot_grid, compute_spot_shock_profile
from app.services.aggregation import aggregate_by_expiration, aggregate_by_strike


def _sample_df():
    now = datetime.now(timezone.utc)
    rows = []
    for strike in [95.0, 100.0, 105.0]:
        for option_type in ["CALL", "PUT"]:
            rows.append(
                {
                    "underlying_symbol": "TEST",
                    "option_symbol": f"T{strike}{option_type}",
                    "option_type": option_type,
                    "strike": strike,
                    "expiration": pd.Timestamp(now + timedelta(days=10)),
                    "quote_timestamp": pd.Timestamp(now),
                    "underlying_spot": 100.0,
                    "open_interest": 500.0,
                    "volume": 50.0,
                    "implied_volatility_effective": 0.2,
                    "implied_volatility_observed": 0.2,
                    "risk_free_rate": 0.03,
                    "dividend_yield": 0.0,
                    "time_to_expiration_years": 10 / 365.0,
                    "is_rejected": False,
                    "data_source": "test",
                }
            )
    return pd.DataFrame(rows)


def test_strike_aggregation_sums_correctly():
    df = _sample_df()
    priced = compute_contract_gamma(df)
    signed, _ = apply_sign_and_signed_gex(priced, SignModel.NAIVE_CONVENTION)
    strike_df = aggregate_by_strike(signed)
    assert len(strike_df) == 3
    assert set(strike_df["strike"]) == {95.0, 100.0, 105.0}
    assert (strike_df["total_oi"] == 1000.0).all()


def test_expiration_aggregation_percentages_sum_to_one():
    df = _sample_df()
    priced = compute_contract_gamma(df)
    signed, _ = apply_sign_and_signed_gex(priced, SignModel.NAIVE_CONVENTION)
    exp_df = aggregate_by_expiration(signed)
    assert abs(exp_df["percent_of_total_absolute_gex"].sum() - 1.0) < 1e-9


def test_spot_shock_grid_includes_current_spot():
    grid = build_spot_grid(100.0, range_pct=0.1, step_pct=0.05)
    assert 100.0 in grid
    assert grid.min() <= 90.0
    assert grid.max() >= 110.0


def test_spot_shock_recalculates_gamma_at_each_level():
    df = _sample_df()
    # Break the call/put OI symmetry of the base fixture: under
    # NAIVE_CONVENTION, identical call/put OI at every strike makes
    # signed net GEX cancel exactly (gamma is option-type-independent in
    # Black-Scholes), which would trivially pass this test for the wrong
    # reason. Asymmetric OI ensures we are actually exercising
    # spot-dependent recalculation.
    df.loc[df["option_type"] == "CALL", "open_interest"] = [300.0, 500.0, 700.0]
    df.loc[df["option_type"] == "PUT", "open_interest"] = [700.0, 500.0, 300.0]

    profile = compute_spot_shock_profile(
        contracts_df=df,
        current_spot=100.0,
        sign_model=SignModel.NAIVE_CONVENTION,
        range_pct=0.05,
        step_pct=0.05,
        contract_multiplier=100,
    )
    # Different hypothetical spots should generally produce different total gex.
    values = {round(p.total_net_gex, 6) for p in profile}
    assert len(values) > 1


def test_0dte_bucket_flag():
    now = datetime.now(timezone.utc)
    df = _sample_df()
    df["expiration"] = pd.Timestamp(now + timedelta(hours=2))
    priced = compute_contract_gamma(df)
    signed, _ = apply_sign_and_signed_gex(priced, SignModel.NAIVE_CONVENTION)
    exp_df = aggregate_by_expiration(signed, as_of=now)
    assert exp_df["is_0dte"].iloc[0] == True  # noqa: E712
