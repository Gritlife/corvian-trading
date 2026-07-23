from datetime import datetime, timezone

from app.core.enums import GammaRegime, SignModel
from app.providers.mock_provider import MockOptionsDataProvider
from app.services.gamma_analysis import run_gamma_analysis

AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _analyze(symbol: str, scenario: str):
    provider = MockOptionsDataProvider(as_of=AS_OF, scenarios={symbol: scenario})
    return run_gamma_analysis(provider, symbol, sign_model=SignModel.NAIVE_CONVENTION, as_of=AS_OF)


def test_spx_positive_gamma_scenario_classifies_positive():
    a = _analyze("SPX", "SPX_POSITIVE_GAMMA")
    assert a.gamma_regime == GammaRegime.POSITIVE
    assert a.gamma_flip is None


def test_spx_negative_gamma_scenario_classifies_negative():
    a = _analyze("SPX", "SPX_NEGATIVE_GAMMA")
    assert a.gamma_regime == GammaRegime.NEGATIVE
    assert a.gamma_flip is None


def test_spx_transition_scenario_classifies_transition():
    a = _analyze("SPX", "SPX_TRANSITION")
    assert a.gamma_regime == GammaRegime.TRANSITION


def test_spx_no_crossing_scenario_flip_is_null():
    a = _analyze("SPX", "SPX_NO_CROSSING")
    assert a.gamma_flip is None
    assert a.all_gamma_crossings == []


def test_spx_multiple_crossings_scenario_has_at_least_two_crossings():
    a = _analyze("SPX", "SPX_MULTIPLE_CROSSINGS")
    assert len(a.all_gamma_crossings) >= 2
    assert a.gamma_flip is not None  # primary is still selected (nearest to spot)


def test_tsla_valid_flip_scenario_has_genuine_crossing():
    a = _analyze("TSLA", "TSLA_WITH_VALID_FLIP")
    assert a.gamma_flip is not None
    assert len(a.all_gamma_crossings) >= 1
    # The flip must be a real interpolated point within the spot-shock grid.
    spots = [p["hypothetical_spot"] for p in a.spot_shock_profile]
    assert min(spots) <= a.gamma_flip <= max(spots)


def test_tsla_no_crossing_scenario_flip_is_null():
    a = _analyze("TSLA", "TSLA_NO_CROSSING")
    assert a.gamma_flip is None
    assert a.all_gamma_crossings == []


def test_tsla_positive_and_negative_regime_scenarios():
    pos = _analyze("TSLA", "TSLA_POSITIVE_GAMMA")
    neg = _analyze("TSLA", "TSLA_NEGATIVE_GAMMA")
    assert pos.gamma_regime == GammaRegime.POSITIVE
    assert neg.gamma_regime == GammaRegime.NEGATIVE


def test_default_demo_scenarios_used_when_no_override_given():
    """Confirms the default MockOptionsDataProvider (no scenario override)
    uses the *_DEFAULT_DEMO scenarios, and that the default TSLA demo has
    a genuine, non-fabricated gamma flip (section 5)."""
    provider = MockOptionsDataProvider(as_of=AS_OF)
    assert provider.active_scenario("SPX") == "SPX_DEFAULT_DEMO"
    assert provider.active_scenario("TSLA") == "TSLA_DEFAULT_DEMO"

    tsla_analysis = run_gamma_analysis(provider, "TSLA", sign_model=SignModel.NAIVE_CONVENTION, as_of=AS_OF)
    assert tsla_analysis.gamma_flip is not None, "Default TSLA demo scenario must contain a genuine gamma flip"

    spx_analysis = run_gamma_analysis(provider, "SPX", sign_model=SignModel.NAIVE_CONVENTION, as_of=AS_OF)
    # Meaningful positive AND negative strike structure (section 4).
    positive_strikes = [r for r in spx_analysis.strike_df_records if r["net_gex"] > 0]
    negative_strikes = [r for r in spx_analysis.strike_df_records if r["net_gex"] < 0]
    assert len(positive_strikes) > 0
    assert len(negative_strikes) > 0
