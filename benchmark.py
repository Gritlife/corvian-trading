"""
Benchmark: full gamma analysis on a large synthetic SPX-like chain.

Run with:
    python scripts/benchmark.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.enums import SignModel
from app.providers.sample_data import generate_synthetic_chain, stable_seed, bias_single_crossing
from app.services.gamma_analysis import run_gamma_analysis
from app.providers.base import OptionsDataProvider
from app.models.contract import RawOptionContract


class _StaticProvider(OptionsDataProvider):
    name = "benchmark_static"

    def __init__(self, contracts):
        self._contracts = contracts

    def get_underlying_quote(self, symbol):
        return {"symbol": symbol, "spot": self._contracts[0].underlying_spot, "timestamp": datetime.now(timezone.utc)}

    def get_expirations(self, symbol):
        return sorted({c.expiration for c in self._contracts})

    def get_option_chain(self, symbol):
        return self._contracts

    def get_contract_snapshot(self, option_symbol):
        for c in self._contracts:
            if c.option_symbol == option_symbol:
                return c
        raise KeyError(option_symbol)

    def get_market_clock(self):
        from app.providers.base import MarketClock

        return MarketClock(is_open=True, session="REGULAR", as_of=datetime.now(timezone.utc))


def main():
    as_of = datetime.now(timezone.utc)
    print("Generating large synthetic SPX-like chain (thousands of contracts)...")
    contracts = generate_synthetic_chain(
        underlying_symbol="SPX",
        spot=5425.35,
        as_of=as_of,
        strike_step=5.0,
        n_strikes_each_side=150,   # 301 strikes
        dtes=[0, 1, 2, 5, 9, 16, 23, 30, 44, 58, 65, 79, 93],  # 13 expirations
        base_iv=0.13,
        iv_skew_slope=-0.35,
        base_oi=4500,
        seed=stable_seed("BENCHMARK", "SPX", "v1"),
        bias_fn=bias_single_crossing,
        oi_noise_range=(0.8, 1.2),
    )
    n_contracts = len(contracts)
    print(f"Generated {n_contracts:,} contracts.")

    t0 = time.perf_counter()
    provider = _StaticProvider(contracts)
    result = run_gamma_analysis(provider, "SPX", sign_model=SignModel.NAIVE_CONVENTION, as_of=as_of)
    elapsed = time.perf_counter() - t0

    print(f"Full gamma analysis (normalize -> gamma -> GEX -> aggregate -> spot-shock -> flip -> gauge -> confidence)")
    print(f"completed in {elapsed:.3f} seconds for {n_contracts:,} contracts.")
    print(f"Strikes aggregated: {len(result.strike_df_records)}")
    print(f"Expirations aggregated: {len(result.expiration_df_records)}")
    print(f"Spot-shock grid points: {len(result.spot_shock_profile)}")
    print(f"Gamma flip: {result.gamma_flip}")
    print(f"Gamma gauge: {round(result.gamma_gauge, 2)} ({result.gauge_interpretation})")
    print(f"Confidence score: {result.confidence_score}")

    print()
    print("--- Cached vs uncached TV payload response time (section 28) ---")
    from app.services.cache import analysis_cache, tv_payload_cache
    from app.services.snapshot_service import get_spx_tv_payload_cached

    analysis_cache.clear()
    tv_payload_cache.clear()

    t0 = time.perf_counter()
    payload1 = get_spx_tv_payload_cached(provider)
    uncached_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    payload2 = get_spx_tv_payload_cached(provider)
    cached_time = time.perf_counter() - t0

    print(f"Uncached TV payload response time: {uncached_time*1000:.2f} ms (refresh_status={payload1['refresh_status']})")
    print(f"Cached TV payload response time:   {cached_time*1000:.2f} ms (refresh_status={payload2['refresh_status']})")
    print(f"Speedup: {uncached_time/max(cached_time,1e-6):.0f}x")


if __name__ == "__main__":
    main()
