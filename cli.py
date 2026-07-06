"""
CLI entrypoints:

    python -m app.cli analyze SPX
    python -m app.cli analyze TSLA
    python -m app.cli demo
    python -m app.cli serve
"""
from __future__ import annotations

import argparse
import json
import sys

from app.core.config import settings
from app.core.enums import SignModel
from app.providers.factory import get_provider
from app.services.asset_engine import build_asset_gamma
from app.services.spx_foundation import build_spx_foundation
from app.tv.payloads import build_spx_tv_payload, build_symbol_tv_payload


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_analyze(symbol: str, sign_model: str) -> None:
    provider = get_provider()
    model = SignModel(sign_model)

    if symbol.upper() == "SPX":
        foundation = build_spx_foundation(provider, sign_model=model)
        payload = build_spx_tv_payload(foundation)
        a = foundation.analysis
    else:
        asset_result = build_asset_gamma(provider, symbol.upper(), sign_model=model)
        payload = build_symbol_tv_payload(asset_result)
        a = asset_result.analysis

    print(f"{settings.architecture_designation} ({settings.purpose})")
    print(f"=== Gamma Analysis: {a.symbol} ===")
    print(f"Snapshot ID: {a.snapshot_id}")
    print(f"Spot: {a.spot}")
    print(f"Regime: {a.gamma_regime.value}")
    print(f"Gamma Gauge: {round(a.gamma_gauge, 2)} ({a.gauge_interpretation})")
    print(f"Gamma Flip: {a.gamma_flip}")
    print(f"Total Net GEX ($/1% move): {a.total_net_gex:,.0f}")
    print(f"Total Absolute GEX ($/1% move): {a.total_absolute_gex:,.0f}")
    print(f"Confidence Score: {a.confidence_score}")
    print(f"Data Status: {a.data_status.value}")
    print(f"Provider: {a.provider_name} ({a.provider_status})")
    print()
    print("--- TV Payload ---")
    _print_json(payload)


def cmd_demo() -> None:
    print("Running offline demo (synthetic SPX + TSLA, no credentials required)...\n")
    cmd_analyze("SPX", SignModel.NAIVE_CONVENTION.value)
    print("\n" + "=" * 60 + "\n")
    cmd_analyze("TSLA", SignModel.NAIVE_CONVENTION.value)


def cmd_serve(host: str, port: int, reload: bool) -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="External Gamma Engine CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="Run gamma analysis for a symbol using the mock provider")
    p_analyze.add_argument("symbol", type=str)
    p_analyze.add_argument("--sign-model", type=str, default=SignModel.NAIVE_CONVENTION.value)

    sub.add_parser("demo", help="Run the offline SPX + TSLA demo end-to-end")

    p_serve = sub.add_parser("serve", help="Start the FastAPI server")
    p_serve.add_argument("--host", type=str, default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "analyze":
        cmd_analyze(args.symbol, args.sign_model)
    elif args.command == "demo":
        cmd_demo()
    elif args.command == "serve":
        cmd_serve(args.host, args.port, args.reload)

    return 0


if __name__ == "__main__":
    sys.exit(main())
