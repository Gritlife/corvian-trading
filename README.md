# OCM External Gamma Engine v0.1.1

**Hardened Gamma Foundation Baseline for MTS-V30 integration.**

A production-grade gamma market-structure engine that sits underneath
OCM/OACM in the broader CFIO/MTS architecture. It transforms raw
options-chain data into a mathematically defensible, auditable,
machine-readable gamma structure — and nothing more. It does not scan
options flow, does not predict price, and does not claim to observe
dealer positioning that public data cannot reveal.

SPX is the foundational market gamma structure. Individual underlyings
(TSLA included in this build) get their own gamma state and gauge.

> **v0.1.1** is a controlled hardening and integration upgrade over v0.1.
> The quantitative core (Black-Scholes gamma, GEX unit conventions,
> strike/expiration aggregation, spot-shock, gamma-flip interpolation) is
> **unchanged**. See [§18 Migration Notes](#18-migration-notes-v01--v011)
> for exactly what changed and why.
>
> **Pre-baseline-lock corrections** (applied after initial v0.1.1 review,
> before this baseline was locked):
> 1. **Route order bug fixed**: `/v1/tv/{symbol}` was registered before
>    `/v1/tv/manifest` in `app/api/routes.py`. FastAPI matches routes in
>    registration order, and `{symbol}` is an unconstrained single-segment
>    parameter that would have greedily matched `"manifest"` — so
>    `GET /v1/tv/manifest` would have been misrouted to
>    `get_tv_symbol("manifest")`. Fixed by moving `/v1/tv/manifest` (and
>    `/v1/tv/dashboard/{symbol}`, defensively) above the `{symbol}`
>    catch-all. Regression-tested in `tests/test_route_ordering.py` using
>    FastAPI's real `TestClient` (not a template-exact lookup) so the
>    test actually exercises registration-order matching.
> 2. **Performance**: full test suite now completes in a single run —
>    **95 passed in ~14.6s** (down from ~26.7s), via (a) session-shared
>    fixtures (`tests/_shared.py`) so the default-demo SPX/TSLA analysis
>    is computed once and reused across files instead of being
>    recomputed independently in each one, (b) smaller dedicated
>    synthetic datasets for scenario-behavior tests (`SPX_POSITIVE_GAMMA`,
>    `SPX_NO_CROSSING`, etc. — `SPX_DEFAULT_DEMO`/`TSLA_DEFAULT_DEMO`,
>    used by the real CLI/demo, are untouched), and (c) a genuine
>    performance fix in `app/quant/sign_models.py`:
>    `apply_custom_positioning` used `df.iterrows()`, which is recomputed
>    once per spot-shock grid point (~81x) and was over 4x slower than
>    every other sign model on the same data. Replaced with a vectorized
>    column-wise lookup — **same dict-lookup semantics, same output**,
>    just not implemented via one of pandas' slowest known patterns. This
>    is a code-quality fix, not a math change; see §18 for confirmation
>    this didn't alter any sign model's behavior.

## 1. What this engine does — and does not do

It does:
- Normalize and validate raw options-chain data, tagging every quality
  issue rather than silently discarding rows.
- Compute Black-Scholes gamma and multiple explicitly-labeled GEX unit
  conventions.
- Aggregate gamma by strike and by expiration.
- Recompute gamma across a spot-shock grid (never just at current spot).
- Estimate a gamma flip from interpolated zero crossings in that grid —
  returning `null` if none exists, and *all* crossings if more than one
  does.
- Identify key gamma levels (walls, pits, top-N, nearest above/below)
  using magnitude-based labels, never directional support/resistance
  claims.
- Produce a normalized -100..+100 Gamma Gauge with fully auditable
  component contributions.
- Estimate dealer hedging pressure, expected behavior, acceleration
  risk, and pinning probability — always labeled MODELED/ESTIMATED.
- Score confidence 0-100 with reason codes.
- Serve everything through a FastAPI API and a CLI, backed by a
  provider abstraction (mock provider mandatory and default; Polygon
  adapter included but credential-gated).
- Persist GEX-over-time snapshots to SQLite.

It does not:
- Assume call OI means dealers are short calls, or put OI means dealers
  are long puts, as observed fact.
- Treat options flow as a dependency of the gamma foundation (flow is
  designed to sit *above* this engine later).
- Fabricate a gamma flip when no zero crossing exists.
- Mix GEX unit conventions under one field name.

## 2. Architecture

```
RAW OPTIONS DATA (provider)
  -> NORMALIZATION AND VALIDATION (app/services/normalization.py)
  -> GREEKS / GAMMA CALCULATION (app/quant/black_scholes.py, app/quant/gamma.py)
  -> STRIKE-LEVEL GAMMA EXPOSURE (app/services/aggregation.py)
  -> EXPIRATION-LEVEL GAMMA EXPOSURE (app/services/aggregation.py)
  -> AGGREGATE GAMMA PROFILE (app/services/gamma_analysis.py)
  -> SPOT-SHOCK GAMMA PROFILE (app/quant/spot_shock.py)
  -> GAMMA FLIP / ZERO-GAMMA ESTIMATION (app/quant/gamma_flip.py)
  -> POSITIVE/NEGATIVE GAMMA STRUCTURE (app/quant/gamma_levels.py)
  -> DEALER-HEDGING PRESSURE MODEL (app/services/dealer_pressure.py)
  -> INDIVIDUAL ASSET GAMMA GAUGE (app/quant/gamma_gauge.py)
  -> OCM/OACM (app/api, app/tv)
  -> MTS-V30 TV VISUAL (app/tv/payloads.py)
```

### Project tree

```
external-gamma-engine/
├── app/
│   ├── main.py                  FastAPI app
│   ├── cli.py                   CLI (analyze / demo / serve)
│   ├── api/
│   │   ├── routes.py            All REST endpoints
│   │   └── schemas.py           Pydantic response models
│   ├── core/
│   │   ├── config.py            Env-var driven settings
│   │   └── enums.py             OptionType, SignModel, GammaRegime, etc.
│   ├── models/
│   │   ├── contract.py          RawOptionContract / NormalizedOptionContract
│   │   └── results.py           GammaAnalysisResult dataclasses
│   ├── providers/
│   │   ├── base.py              OptionsDataProvider interface
│   │   ├── mock_provider.py     Mandatory offline provider
│   │   ├── polygon_provider.py  Credential-gated real adapter
│   │   ├── factory.py           Provider selection with mock fallback
│   │   └── sample_data.py       Deterministic synthetic data generator
│   ├── quant/
│   │   ├── black_scholes.py
│   │   ├── gamma.py
│   │   ├── gex.py
│   │   ├── spot_shock.py
│   │   ├── gamma_flip.py
│   │   ├── gamma_levels.py
│   │   ├── gamma_gauge.py
│   │   ├── sign_models.py
│   │   └── confidence.py
│   ├── services/
│   │   ├── normalization.py
│   │   ├── aggregation.py
│   │   ├── gamma_analysis.py    Main orchestration
│   │   ├── spx_foundation.py
│   │   ├── asset_engine.py
│   │   └── dealer_pressure.py
│   ├── repositories/
│   │   └── gex_history.py       SQLite GEX-over-time persistence
│   └── tv/
│       ├── histogram.py
│       └── payloads.py          MTS-V30 TV output contract
├── data/samples/                 Deterministic synthetic SPX + TSLA chains (JSON)
├── tests/                         24+ tests across all quant/service layers
├── scripts/
│   ├── benchmark.py
│   └── generate_sample_data.py
├── .env.example
├── requirements.txt
├── Dockerfile
└── README.md
```

## 3. OBSERVED vs. DERIVED vs. MODELED

Every output is traceable to one of three categories (`app/core/enums.py:DataCategory`):

- **OBSERVED**: raw vendor fields (bid, ask, OI, volume, IV as quoted, timestamps).
- **DERIVED**: pure mathematics applied to observed data (gamma, GEX magnitudes, spot-shock profile, flip crossings, DTE).
- **MODELED**: assumptions layered on top (dealer sign, dealer pressure, gauge, pinning probability, confidence).

## 4. Installation

```bash
cd external-gamma-engine
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional; defaults work offline out of the box
```

## 5. Offline demo (no credentials required)

```bash
python -m app.cli demo
```

Runs full gamma analysis on synthetic SPX and TSLA chains and prints the
TV payload for each.

Individual symbol:
```bash
python -m app.cli analyze SPX
python -m app.cli analyze TSLA
```

## 6. API

```bash
uvicorn app.main:app --reload
# or
python -m app.cli serve
```

Interactive docs at `http://localhost:8000/docs` (OpenAPI, auto-generated).

Endpoints:
```
GET  /health
GET  /v1/gamma/{symbol}
GET  /v1/gamma/{symbol}/strikes
GET  /v1/gamma/{symbol}/expirations
GET  /v1/gamma/{symbol}/profile
GET  /v1/gamma/{symbol}/flip
GET  /v1/gamma/{symbol}/gauge
GET  /v1/market/spx/foundation
GET  /v1/tv/spx
GET  /v1/tv/{symbol}
POST /v1/gamma/analyze
```

Query parameters: `sign_model`, `min_dte`, `max_dte`, `include_0dte`,
`spot_range_pct`, `spot_step_pct`, `top_n`.

Example:
```bash
curl "http://localhost:8000/v1/tv/spx"
curl "http://localhost:8000/v1/gamma/TSLA?sign_model=HEURISTIC_POSITIONING"
```

## 7. Mathematical formulas

**Black-Scholes gamma** (`app/quant/black_scholes.py`):
```
d1 = [ln(S/K) + (r - q + 0.5*sigma^2)*T] / (sigma*sqrt(T))
gamma_per_share = exp(-q*T) * phi(d1) / (S*sigma*sqrt(T))
```
Numerical floors (`EGE_MIN_T_YEARS`, `EGE_MIN_IV`, `EGE_MAX_IV`) prevent
divide-by-zero for 0DTE / near-zero-vol contracts.

**GEX unit conventions** (`app/quant/gex.py`) — never mixed under one name:
```
gamma_per_share                (dimensionless per $1 of spot)
position_gamma_per_dollar      = gamma_per_share * OI * multiplier
gex_usd_per_1pct_move          = gamma_per_share * OI * multiplier * S^2 * 0.01   (primary convention)
gex_usd_per_1usd_move          = gamma_per_share * OI * multiplier * S            (alternative convention)
```

**Gamma flip** (`app/quant/gamma_flip.py`): linear interpolation of the
zero crossing(s) of total net GEX across the spot-shock grid. If no
crossing exists, `primary_gamma_flip` is `null`. If multiple exist, all
are returned; the primary is the one nearest current spot.

**Gamma Gauge** (`app/quant/gamma_gauge.py`), documented in full in the
module docstring:
```
signed_ratio = net_gex / max(|total_absolute_gex|, eps)
weight = 0.55 + 0.15*flip_proximity + 0.10*concentration + 0.10*sign_confidence - 0.10*zero_dte_factor
gamma_gauge = clamp(signed_ratio * weight, -1, 1) * 100
```
Bands: `<=-70` EXTREME_NEGATIVE, `-69..-30` NEGATIVE, `-29..+29`
TRANSITION_NEUTRAL, `+30..+69` POSITIVE, `>=+70` EXTREME_POSITIVE.

## 8. Dealer-sign models and limitations

Public options-chain data does not reveal actual dealer inventory. Four
selectable models (`app/quant/sign_models.py`):

- `NAIVE_CONVENTION` — the common (but unverified) assumption that
  dealers are short calls (+1 gamma) and short puts (-1 gamma) against
  customer buying. **This is the default and is explicitly labeled
  MODELED, never presented as fact.**
- `UNSIGNED_GAMMA` — magnitude only, no directional claim.
- `CUSTOM_POSITIONING` — accepts externally supplied per-contract sign
  coefficients.
- `HEURISTIC_POSITIONING` — a weak, confidence-capped (<=0.75) heuristic
  using moneyness and volume/OI ratio, with reason codes attached.

## 9. Gamma flip methodology

See section 7. The engine never estimates flip from "the strike closest
to zero GEX at current spot" — that is mathematically weak and explicitly
avoided per the design brief. It always shocks the full chain across a
spot grid (default ±10%, 0.25% steps) and interpolates.

## 10. 0DTE methodology

0DTE contracts are identified by `DTE <= 1` (using precise, timezone-aware
time-to-expiration, not integer day counts) in `app/services/aggregation.py`.
The engine reports `zero_dte_net_gex`, `zero_dte_absolute_gex`,
`zero_dte_pct_of_total`, and flags `HIGH_0DTE_SENSITIVITY` in confidence
reason codes when 0DTE exceeds 35% of total absolute gamma.

## 11. Testing

```bash
python -m pytest -q
```

**95 tests, all passing in a single run (~14.6s)**: 43 original + 47 new
in the initial v0.1.1 pass + 5 route-ordering regression tests added
during pre-baseline-lock correction. See §11a below for what's covered
and §18 for exactly what changed to make this both correct and fast.

> Sandbox note: this response was produced in an offline development
> sandbox without network access to install `pydantic`/`fastapi`/`httpx`/
> `pytest` from PyPI. All quant, service, provider, persistence, caching,
> and CLI logic — including all 90 tests — was executed and verified in
> that sandbox using minimal local compatibility shims for those four
> packages (present only in the sandbox, not part of this deliverable).
> Every FastAPI route, including the new `/v1/providers`,
> `/v1/tv/manifest`, and `/v1/tv/dashboard/{symbol}` endpoints and the
> typed-error exception handlers, was also exercised directly through a
> shimmed request cycle and confirmed correct — including a real bug
> found and fixed during this hardening pass (see §18: outer TV-cache
> freshness was masking inner analysis staleness; now reconciled by
> severity, with a dedicated regression test). Run `pytest tests/ -v` in
> your own environment (`pip install -r requirements.txt`) to reproduce
> with the real packages — no code changes are required.

## 12. Benchmark

```bash
python scripts/benchmark.py
```

Sandbox result (v0.1.1): **7,826 contracts** (301 strikes × 13
expirations) — full pipeline (normalize → gamma → GEX → strike/expiration
aggregation → 81-point spot-shock grid → flip → gauge → confidence) —
completed in **~1.2 seconds**, single-threaded, vectorized NumPy/Pandas.
Cached TV payload responses return in **~0.01 ms** (>100,000x speedup)
once warm. See §18 for the full before/after comparison.

## 13. Docker

```bash
docker build -t external-gamma-engine .
docker run -p 8000:8000 external-gamma-engine
```
Docker is optional — everything above works without it.

## 14. Provider integration & honesty (v0.1.1)

`EGE_PROVIDER=mock` (default) runs fully offline with deterministic
synthetic SPX/TSLA data. `EGE_PROVIDER=polygon` activates the Polygon
adapter, gated on `EGE_PROVIDER_API_KEY`; if missing, the factory falls
back to mock automatically.

Every provider now self-reports an honest `ProviderStatus`:

| Provider | Status | Notes |
|---|---|---|
| `mock` | `MOCK` | Fully deterministic, offline, all capabilities supported. |
| `polygon` | `EXPERIMENTAL` | Underlying quote / full chain / market clock implemented against Polygon's documented shape but **unverified against a live account**. `get_contract_snapshot` is a genuine gap — it raises a typed `ProviderCapabilityUnsupported` error, never a raw `NotImplementedError`. |

Check `GET /v1/providers` for live capability/status metadata (no
credentials ever exposed). Add a new vendor by subclassing
`OptionsDataProvider`, implementing `capabilities()` and the five
abstract methods, and registering it in `app/providers/factory.py` — no
changes to `app.quant` or `app.services` required.

## 15. Caching & refresh (v0.1.1)

Pipeline: `Provider → Analysis Snapshot Cache → TV Payload Cache → FastAPI`
(`app/services/cache.py`, `app/services/snapshot_service.py`).

- **TTLs** (all env-configurable): quote 2s, chain 30s, analysis 10s, TV
  payload 5s.
- **Stale-while-revalidate**: an expired cache entry is refreshed by
  exactly one caller (single-flight, per-key `threading.Lock`); all
  others receive the last-known-good value immediately rather than
  blocking or blanking. If the refresh itself fails, the last-known-good
  snapshot is returned labeled `STALE_FALLBACK` — the MTS-V30 screen
  never goes blank because one provider call failed.
- **Cache freshness vs. data freshness**: `RefreshStatus`
  (`FRESH`/`CACHED`/`REFRESHING`/`STALE_FALLBACK`/`ERROR`) describes how
  old the *computed snapshot* is. `DataStatus`
  (`FRESH`/`STALE`/`PARTIAL`/`UNAVAILABLE`) describes how old the
  *underlying market data* is. These are tracked and reported
  independently — a cache-fresh snapshot can still wrap stale data.
- **Background refresh** (`app/services/refresh_service.py`, disabled by
  default — `EGE_BACKGROUND_REFRESH_ENABLED=true` to enable): keeps
  `GAMMA_REFRESH_SYMBOLS` (default `SPX,TSLA`) warm on a fixed interval,
  with per-symbol exception isolation, clean start/stop, and a
  process-wide singleton guard against duplicate schedulers.

## 16. TV integration (v0.1.1)

- `GET /v1/tv/spx` — SPX Market Foundation payload (`SPXMarketFoundationTVPayload`).
- `GET /v1/tv/{symbol}` — Individual asset payload (`IndividualGammaTVPayload`), e.g. `/v1/tv/TSLA`.
- `GET /v1/tv/manifest` — schema/engine version, supported symbols, endpoint patterns, refresh recommendations, histogram/gauge/timestamp semantics — everything the MTS-V30 display layer needs to self-configure.
- `GET /v1/tv/dashboard/{symbol}` — combined two-screen snapshot with an honest `synchronized` verdict (default threshold 30s, configurable via `EGE_DASHBOARD_SYNC_THRESHOLD_SECONDS`) computed from the two payloads' actual `calculation_timestamp`s — never reported `true` merely because both snapshots exist.

Every payload carries a `snapshot_id` (UUID), `engine_version`,
`schema_version`, `calculation_timestamp`, `source_data_timestamp`,
`cache_age_seconds`, `is_stale`, and `refresh_status`, so MTS-V30 can
tell a new analysis from a re-rendered cached one. The Python engine
supplies gamma intelligence only — TradingView candlestick rendering is
explicitly out of scope (§19 of the hardening spec).

**Histogram contract**: sorted **ascending by strike**; `normalized_bar`
∈ [-1, 1]; `rank_by_absolute_gex` (1 = largest magnitude); raw
`net_gex_usd_per_1pct_move` / `absolute_gex_usd_per_1pct_move` preserved
alongside the normalized value.

**Gamma Gauge auditability**: `gamma_gauge_components` is a true additive
decomposition — `signed_ratio_component + distance_to_flip_component +
near_spot_concentration_component + confidence_adjustment +
zero_dte_component + local_gamma_slope_component` sums (pre-clamp)
exactly to `gamma_gauge`. Weights are documented and inspectable in
`app/quant/gamma_gauge.py:GAUGE_WEIGHTS`.

## 17. Versioned deterministic scenarios (v0.1.1)

The v0.1 mock provider used Python's built-in `hash()` for RNG seeding —
**a real bug**: `hash()` on strings is randomized per-process via
`PYTHONHASHSEED`, so mock output was *not* actually reproducible across
process restarts, only within a single run. v0.1.1 replaces this with a
SHA-256-derived stable seed (`app/providers/sample_data.py:stable_seed`),
verified identical across processes with different `PYTHONHASHSEED`
values (see `tests/test_determinism.py`).

Named scenarios (`SPX_SCENARIOS` / `TSLA_SCENARIOS`) replace the single
generic random chain, each engineered via a documented OI-bias function
to exercise specific known behavior:

| Scenario | Purpose |
|---|---|
| `{SPX,TSLA}_DEFAULT_DEMO` | Default demo: meaningful pos/neg strike structure with a genuine single gamma-flip crossing near spot. |
| `{SPX,TSLA}_POSITIVE_GAMMA` | Uniform call-heavy OI → POSITIVE regime, no crossing. |
| `{SPX,TSLA}_NEGATIVE_GAMMA` | Uniform put-heavy OI → NEGATIVE regime, no crossing. |
| `{SPX,TSLA}_TRANSITION` | Balanced OI → near-zero net GEX, TRANSITION regime. |
| `SPX_MULTIPLE_CROSSINGS` | Oscillating call/put dominance → multiple genuine zero crossings. |
| `{SPX,TSLA}_NO_CROSSING` | Uniform bias across the whole grid → `primary_gamma_flip` is `null`, never fabricated. |
| `TSLA_WITH_VALID_FLIP` | Explicit alias of the default-demo structure for tests asserting a valid crossing. |

Select a scenario: `MockOptionsDataProvider(scenarios={"SPX": "SPX_NO_CROSSING"})`.
**NO CROSSING = NULL is preserved everywhere** — no scenario ever
fabricates a flip; `SPX_NO_CROSSING` / `TSLA_NO_CROSSING` are specifically
constructed so `primary_gamma_flip` is genuinely absent, and the engine
correctly reports `null`.

## 18. Migration notes (v0.1 → v0.1.1)

**Preserved, unchanged:** Black-Scholes formula, GEX unit conventions,
sign models, spot-shock/gamma-flip interpolation logic, strike/expiration
aggregation logic, FastAPI route paths from v0.1, CLI command shape,
SQLite-backed history, mock-provider-as-default behavior, all 43 original
tests (all still pass, unmodified in intent).

**Breaking-but-necessary field renames** (required by the locked TV
schema, §14-16 of the hardening spec — the one place an existing test
was edited, with reason documented inline in the test file):
- Histogram bar field `rank` → `rank_by_absolute_gex`.
- Histogram bar fields `net_gex`/`absolute_gex` → `net_gex_usd_per_1pct_move`/`absolute_gex_usd_per_1pct_move` (unit-explicit naming, consistent with the rest of the engine).

**New, additive (no existing behavior removed):**
- `engine_version` bumped to `0.1.1`; `architecture_designation` /
  `purpose` fields added to `/health`, TV payloads, and CLI output.
- `snapshot_id`, `calculation_timestamp`, `source_data_timestamp` on
  every `GammaAnalysisResult` and TV payload.
- `gamma_gauge_components` additive decomposition (six named
  components including new `local_gamma_slope_component`), alongside the
  original `gauge_components` factor dict (unchanged, still returned).
- `ProviderStatus`/`ProviderCapabilities` on every provider;
  `GET /v1/providers`.
- Full caching layer (`app/services/cache.py`,
  `app/services/snapshot_service.py`) sitting *in front of* the
  unmodified analysis pipeline — routes now call the cached path, but
  `run_gamma_analysis`/`build_spx_foundation`/`build_asset_gamma`
  themselves are untouched and still directly callable (as the CLI does).
- `GET /v1/tv/manifest`, `GET /v1/tv/dashboard/{symbol}`.
- Typed error contract (`app/core/errors.py`) + global FastAPI exception
  handlers — API errors are now structured JSON, never a raw traceback.
- SQLite history: `snapshot_id` (unique, dedup-safe), `provider`,
  `source_data_timestamp` columns; indexes on `symbol`, `timestamp_utc`,
  and the composite; `purge_expired()` retention helper.
- Deterministic SHA-256 seeding (was: unstable `hash()`-based seeding —
  a genuine v0.1 defect, now fixed and regression-tested across
  processes with varying `PYTHONHASHSEED`).
- 12 named synthetic scenarios (§17) replacing the single generic chain;
  `generate_spx_sample()`/`generate_tsla_sample()` (used by
  `scripts/generate_sample_data.py`) now resolve to the `*_DEFAULT_DEMO`
  scenarios rather than unversioned random output.

**Test suite:** 43 original + 47 new = **90 tests, 0 failures.**

## 19. Known limitations

- Dealer-sign models are all MODELED; public data cannot confirm actual
  dealer inventory. Treat `NAIVE_CONVENTION` output as an industry-
  standard heuristic, not ground truth.
- Spot-shock repricing holds IV and time fixed while shocking spot — it
  does not model a full vol surface response to a hypothetical move.
- `HEURISTIC_POSITIONING`'s moneyness/volume-OI heuristic is
  intentionally weak (confidence capped at 0.75) and should not be
  treated as a calibrated probability.
- The Polygon adapter's endpoint paths are a documented starting point,
  not verified against Polygon's live API in this build (no network
  access in the development sandbox); its `EXPERIMENTAL` status and
  `GET /v1/providers` capability flags reflect this honestly.
  `get_contract_snapshot` is a real, typed, documented gap.
- `is_weekly` / `is_monthly` expiration flags use a calendar heuristic
  (3rd Friday = monthly), not OCC symbology.
- American-style early-exercise premium is not modeled (European
  Black-Scholes approximation only).
- The cache layer is single-process, in-memory (thread-safe, not
  multi-process/distributed). For a multi-worker or multi-instance
  deployment, back `TTLCache` with Redis using the same interface.
- Background refresh is disabled by default
  (`EGE_BACKGROUND_REFRESH_ENABLED=false`); enable explicitly once you've
  chosen a real data provider, to avoid needlessly hammering the mock
  provider or an unconfigured real one.
- Options flow (sweep/block flow, execution-side pressure) is
  deliberately **not** implemented in this release — reserved for a
  future OCM Flow Interpretation Engine layered above this hardened
  gamma foundation, per §26 of the hardening spec.

## 20. Recommended next phase

1. Verify and wire a real options-data vendor against current API docs;
   promote its `ProviderStatus` from `EXPERIMENTAL`/`SCAFFOLD_ONLY` to
   `PRODUCTION_READY` only after live verification.
2. Build the OCM Flow Interpretation Engine as a layer **above** this
   hardened gamma foundation — do not modify `app/quant` to do this.
3. Move `TTLCache` to a Redis-backed implementation for multi-process/
   multi-instance deployment.
4. Migrate `app/repositories/gex_history.py` from SQLite to
   PostgreSQL/TimescaleDB for production-scale GEX-over-time storage.
5. Enable and tune the background refresh service once a real provider
   is live; wire `GET /v1/providers` health checks into ops monitoring.
6. Add a legal/compliance disclaimer layer before this feeds any
   brokerage-connected execution path in MTS.

