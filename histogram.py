"""
Strike-level histogram normalization for the MTS-V30 TV left-side display
(section 16 of the v0.1.1 hardening spec).

Bars are normalized to [-1.0, +1.0] relative to the maximum absolute
net_gex across all strikes in the current dataset, centered on
mathematical zero. Raw GEX values are preserved alongside the normalized
bar so no information is lost in the visual representation.

STRIKE ORDER: output is sorted ASCENDING by strike (lowest strike first).
This is a deliberate, documented convention — the TV rendering layer is
responsible for any display-order flip (e.g. top-to-bottom vs
bottom-to-top) rather than the engine silently choosing one.
"""
from __future__ import annotations

from typing import Dict, List

EPSILON = 1e-9


def build_histogram(strike_records: List[dict], spot: float) -> List[dict]:
    if not strike_records:
        return []

    max_abs_gex = max(abs(r["net_gex"]) for r in strike_records)
    max_abs_gex = max(max_abs_gex, EPSILON)

    ranked = sorted(strike_records, key=lambda r: abs(r["net_gex"]), reverse=True)
    rank_by_strike: Dict[float, int] = {r["strike"]: i + 1 for i, r in enumerate(ranked)}

    histogram = []
    for r in sorted(strike_records, key=lambda x: x["strike"]):  # ascending strike order
        net_gex = r["net_gex"]
        absolute_gex = r.get("absolute_gex", abs(net_gex))
        normalized_bar = max(-1.0, min(1.0, net_gex / max_abs_gex))
        distance = r["strike"] - spot
        distance_pct = (distance / spot) if spot else 0.0
        histogram.append(
            {
                "strike": r["strike"],
                "net_gex_usd_per_1pct_move": net_gex,
                "absolute_gex_usd_per_1pct_move": absolute_gex,
                "normalized_bar": round(normalized_bar, 6),
                "side": "POSITIVE" if net_gex > 0 else ("NEGATIVE" if net_gex < 0 else "NEUTRAL"),
                "distance_from_spot": distance,
                "distance_from_spot_pct": distance_pct,
                "rank_by_absolute_gex": rank_by_strike[r["strike"]],
            }
        )
    return histogram
