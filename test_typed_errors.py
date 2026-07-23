from app.core.enums import ErrorCode
from app.core.errors import (
    AnalysisFailed,
    NoChainData,
    NoValidIV,
    ProviderCapabilityUnsupported,
    ProviderUnavailable,
    StaleDataRejected,
    SymbolUnsupported,
)


def test_symbol_unsupported_has_correct_code_and_status():
    err = SymbolUnsupported("bad symbol", details={"symbol": "AAPL"})
    resp = err.to_response()
    assert resp["error"]["code"] == ErrorCode.SYMBOL_UNSUPPORTED.value
    assert err.http_status == 404
    assert resp["error"]["details"]["symbol"] == "AAPL"


def test_provider_capability_unsupported_status_and_code():
    err = ProviderCapabilityUnsupported("no snapshot support")
    assert err.code == ErrorCode.PROVIDER_CAPABILITY_UNSUPPORTED
    assert err.http_status == 501


def test_all_typed_errors_produce_structured_json_without_traceback():
    errors = [
        ProviderUnavailable("x"),
        ProviderCapabilityUnsupported("x"),
        SymbolUnsupported("x"),
        NoChainData("x"),
        StaleDataRejected("x"),
        AnalysisFailed("x"),
        NoValidIV("x"),
    ]
    for err in errors:
        resp = err.to_response()
        assert "error" in resp
        assert "code" in resp["error"]
        assert "message" in resp["error"]
        assert "Traceback" not in str(resp)
        assert "File \"" not in str(resp)
