from app.quant.confidence import compute_confidence


def test_confidence_score_bounded_0_100():
    result = compute_confidence(
        quote_freshness=1.0,
        iv_completeness=1.0,
        oi_completeness=1.0,
        chain_completeness=1.0,
        spread_quality=1.0,
        provider_quality=1.0,
        sign_model_certainty=1.0,
        expiration_coverage=1.0,
    )
    assert result.confidence_score == 100.0
    assert result.reason_codes == []


def test_confidence_flags_stale_quotes():
    result = compute_confidence(
        quote_freshness=0.1,
        iv_completeness=1.0,
        oi_completeness=1.0,
        chain_completeness=1.0,
        spread_quality=1.0,
        provider_quality=1.0,
        sign_model_certainty=1.0,
        expiration_coverage=1.0,
    )
    assert "STALE_QUOTES" in result.reason_codes
    assert result.confidence_score < 100.0


def test_confidence_flags_missing_iv_and_low_oi():
    result = compute_confidence(
        quote_freshness=1.0,
        iv_completeness=0.2,
        oi_completeness=0.1,
        chain_completeness=1.0,
        spread_quality=1.0,
        provider_quality=1.0,
        sign_model_certainty=1.0,
        expiration_coverage=1.0,
    )
    assert "MISSING_IV" in result.reason_codes
    assert "LOW_OI_COVERAGE" in result.reason_codes
