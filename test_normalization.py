from datetime import datetime, timedelta, timezone

from app.core.enums import DataQualityFlag, OptionType
from app.models.contract import RawOptionContract
from app.services.normalization import normalize_chain, normalize_contract


def _base_contract(**overrides):
    now = datetime.now(timezone.utc)
    defaults = dict(
        underlying_symbol="TEST",
        option_symbol="TEST_1",
        option_type=OptionType.CALL,
        strike=100.0,
        expiration=now + timedelta(days=30),
        quote_timestamp=now,
        underlying_spot=100.0,
        bid=1.0,
        ask=1.2,
        last_price=1.1,
        volume=10.0,
        open_interest=100.0,
        implied_volatility=0.2,
        data_source="test",
    )
    defaults.update(overrides)
    return RawOptionContract(**defaults)


def test_negative_open_interest_is_rejected():
    raw = _base_contract(open_interest=-5.0)
    normalized = normalize_contract(raw)
    assert normalized.is_rejected
    assert DataQualityFlag.NEGATIVE_OI in normalized.data_quality_flags


def test_missing_iv_is_flagged_and_floored():
    raw = _base_contract(implied_volatility=None)
    normalized = normalize_contract(raw)
    assert DataQualityFlag.MISSING_IV in normalized.data_quality_flags
    assert normalized.implied_volatility_effective > 0
    assert not normalized.is_rejected


def test_expired_contract_is_rejected():
    now = datetime.now(timezone.utc)
    raw = _base_contract(expiration=now - timedelta(days=1))
    normalized = normalize_contract(raw, as_of=now)
    assert normalized.is_rejected
    assert DataQualityFlag.EXPIRED_CONTRACT in normalized.data_quality_flags


def test_crossed_market_is_flagged():
    raw = _base_contract(bid=2.0, ask=1.0)
    normalized = normalize_contract(raw)
    assert DataQualityFlag.CROSSED_MARKET in normalized.data_quality_flags


def test_duplicate_contract_detection():
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(days=30)
    raw1 = _base_contract(quote_timestamp=now, expiration=expiration)
    raw2 = _base_contract(quote_timestamp=now, expiration=expiration)
    normalized, stats = normalize_chain([raw1, raw2], as_of=now)
    assert stats["duplicates"] == 1
    assert len(normalized) == 1
    assert DataQualityFlag.DUPLICATE_CONTRACT in normalized[0].data_quality_flags


def test_missing_spot_is_rejected():
    raw = _base_contract(underlying_spot=None)
    normalized = normalize_contract(raw)
    assert normalized.is_rejected
    assert DataQualityFlag.MISSING_SPOT in normalized.data_quality_flags


def test_zero_time_to_expiration_uses_floor_not_zero():
    now = datetime.now(timezone.utc)
    raw = _base_contract(expiration=now, quote_timestamp=now)
    normalized = normalize_contract(raw, as_of=now)
    assert normalized.time_to_expiration_years > 0
