from app.core.config import settings
from app.tv.payloads import build_spx_tv_payload, build_symbol_tv_payload
from tests._shared import SPX_FOUNDATION, TSLA_ASSET_RESULT


def test_settings_report_0_1_1():
    assert settings.engine_version == "0.1.1"
    assert "0.1.1" in settings.architecture_designation


def test_spx_tv_payload_reports_0_1_1():
    payload = build_spx_tv_payload(SPX_FOUNDATION)
    assert payload["engine_version"] == "0.1.1"
    assert payload["schema_version"] == "1.0"


def test_asset_tv_payload_reports_0_1_1():
    payload = build_symbol_tv_payload(TSLA_ASSET_RESULT)
    assert payload["engine_version"] == "0.1.1"
