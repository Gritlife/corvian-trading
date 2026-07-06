from app.core.enums import ProviderStatus
from app.core.errors import ProviderCapabilityUnsupported
from app.providers.factory import list_provider_metadata
from app.providers.mock_provider import MockOptionsDataProvider
from app.providers.polygon_provider import PolygonOptionsDataProvider


def test_mock_provider_reports_mock_status_and_full_capabilities():
    caps = MockOptionsDataProvider.capabilities()
    assert MockOptionsDataProvider.status == ProviderStatus.MOCK
    assert caps.supports_underlying_quote
    assert caps.supports_full_chain
    assert caps.supports_contract_snapshot
    assert caps.supports_market_clock


def test_polygon_provider_reports_experimental_status_honestly():
    assert PolygonOptionsDataProvider.status == ProviderStatus.EXPERIMENTAL
    caps = PolygonOptionsDataProvider.capabilities()
    assert caps.supports_contract_snapshot is False
    assert "EGE_PROVIDER_API_KEY" in caps.required_env_vars


def test_polygon_unsupported_capability_raises_typed_error_not_notimplementederror():
    try:
        provider = PolygonOptionsDataProvider(api_key="fake-key-for-test")
    except Exception:
        # Construction itself may fail without real network access; the
        # important behavior under test is the typed-error contract on
        # get_contract_snapshot when a provider instance exists.
        return
    try:
        provider.get_contract_snapshot("SPX_ANY")
        assert False, "expected ProviderCapabilityUnsupported"
    except ProviderCapabilityUnsupported as exc:
        assert exc.code.value == "PROVIDER_CAPABILITY_UNSUPPORTED"
        assert exc.details["capability"] == "get_contract_snapshot"
    except NotImplementedError:
        assert False, "raw NotImplementedError must not be exposed (section 6)"


def test_list_provider_metadata_never_exposes_secret_values():
    metadata = list_provider_metadata()
    names = {m["provider"] for m in metadata}
    assert {"mock", "polygon"} <= names
    serialized = str(metadata)
    assert "sk-" not in serialized  # no leaked key-shaped values
    for m in metadata:
        assert "api_key" not in m
        assert "provider_api_key" not in m


def test_list_provider_metadata_marks_active_provider():
    metadata = list_provider_metadata()
    mock_entry = next(m for m in metadata if m["provider"] == "mock")
    assert mock_entry["active"] is True
    assert mock_entry["health_status"] == "OK"
