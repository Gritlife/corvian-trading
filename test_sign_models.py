import pandas as pd

from app.core.enums import SignModel
from app.quant.sign_models import compute_dealer_sign


def _df():
    return pd.DataFrame(
        [
            {"underlying_symbol": "TEST", "option_type": "CALL", "strike": 100.0, "underlying_spot": 100.0,
             "volume": 50.0, "open_interest": 100.0, "expiration": pd.Timestamp("2026-08-01", tz="UTC")},
            {"underlying_symbol": "TEST", "option_type": "PUT", "strike": 100.0, "underlying_spot": 100.0,
             "volume": 50.0, "open_interest": 100.0, "expiration": pd.Timestamp("2026-08-01", tz="UTC")},
        ]
    )


def test_naive_convention_signs_calls_positive_puts_negative():
    df = _df()
    sign, confidence, reasons = compute_dealer_sign(df, SignModel.NAIVE_CONVENTION)
    assert sign.iloc[0] == 1.0
    assert sign.iloc[1] == -1.0
    assert "HEURISTIC_SIGN_MODEL" in reasons


def test_unsigned_gamma_has_no_direction():
    df = _df()
    sign, confidence, reasons = compute_dealer_sign(df, SignModel.UNSIGNED_GAMMA)
    assert (sign == 1.0).all()
    assert confidence.iloc[0] == 1.0


def test_custom_positioning_uses_provided_coefficients_and_defaults_to_zero():
    df = _df()
    key = ("TEST", "CALL", 100.0, pd.Timestamp("2026-08-01", tz="UTC").isoformat())
    coefficients = {key: 0.7}
    sign, confidence, reasons = compute_dealer_sign(df, SignModel.CUSTOM_POSITIONING, coefficients)
    assert sign.iloc[0] == 0.7
    assert sign.iloc[1] == 0.0  # no coefficient provided for the put


def test_heuristic_positioning_never_returns_full_confidence():
    df = _df()
    sign, confidence, reasons = compute_dealer_sign(df, SignModel.HEURISTIC_POSITIONING)
    assert (confidence <= 0.75).all()
    assert (confidence >= 0.1).all()
