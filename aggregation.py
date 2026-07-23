"""
Strike-level and expiration-level gamma aggregation (DERIVED, under a
MODELED sign convention).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd


def dte_from_expiration(expiration: pd.Timestamp, as_of: datetime) -> float:
    delta = expiration.to_pydatetime() - as_of
    return delta.total_seconds() / 86400.0


def aggregate_by_strike(signed_df: pd.DataFrame) -> pd.DataFrame:
    """signed_df must include: strike, option_type, open_interest, volume,
    gex_usd_per_1pct_move (unsigned magnitude), signed_gex_usd_per_1pct_move,
    expiration, sign_confidence.
    """
    if signed_df.empty:
        return pd.DataFrame(
            columns=[
                "strike",
                "call_oi",
                "put_oi",
                "total_oi",
                "call_volume",
                "put_volume",
                "call_gex",
                "put_gex",
                "net_gex",
                "absolute_gex",
                "positive_gex",
                "negative_gex",
                "expiration_count",
                "nearest_expiration",
                "dominant_expiration",
                "confidence_score",
            ]
        )

    df = signed_df.copy()
    df["is_call"] = df["option_type"] == "CALL"

    records = []
    for strike, g in df.groupby("strike"):
        call_g = g[g["is_call"]]
        put_g = g[~g["is_call"]]

        call_gex = float(call_g["signed_gex_usd_per_1pct_move"].sum())
        put_gex = float(put_g["signed_gex_usd_per_1pct_move"].sum())
        net_gex = call_gex + put_gex
        absolute_gex = float(g["gex_usd_per_1pct_move"].abs().sum())
        positive_gex = float(g.loc[g["signed_gex_usd_per_1pct_move"] > 0, "signed_gex_usd_per_1pct_move"].sum())
        negative_gex = float(g.loc[g["signed_gex_usd_per_1pct_move"] < 0, "signed_gex_usd_per_1pct_move"].sum())

        exp_group = g.groupby("expiration")["gex_usd_per_1pct_move"].sum().abs()
        dominant_expiration = exp_group.idxmax() if not exp_group.empty else None

        records.append(
            {
                "strike": float(strike),
                "call_oi": float(call_g["open_interest"].sum()),
                "put_oi": float(put_g["open_interest"].sum()),
                "total_oi": float(g["open_interest"].sum()),
                "call_volume": float(call_g["volume"].sum()),
                "put_volume": float(put_g["volume"].sum()),
                "call_gex": call_gex,
                "put_gex": put_gex,
                "net_gex": net_gex,
                "absolute_gex": absolute_gex,
                "positive_gex": positive_gex,
                "negative_gex": negative_gex,
                "expiration_count": int(g["expiration"].nunique()),
                "nearest_expiration": g["expiration"].min(),
                "dominant_expiration": dominant_expiration,
                "confidence_score": float(g["sign_confidence"].mean()),
            }
        )

    out = pd.DataFrame(records).sort_values("strike").reset_index(drop=True)
    return out


def aggregate_by_expiration(signed_df: pd.DataFrame, as_of: Optional[datetime] = None) -> pd.DataFrame:
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    if signed_df.empty:
        return pd.DataFrame(
            columns=[
                "expiration",
                "dte",
                "call_gex",
                "put_gex",
                "net_gex",
                "absolute_gex",
                "percent_of_total_absolute_gex",
                "is_0dte",
                "is_weekly",
                "is_monthly",
            ]
        )

    df = signed_df.copy()
    df["is_call"] = df["option_type"] == "CALL"
    total_absolute = float(df["gex_usd_per_1pct_move"].abs().sum()) or 1.0

    records = []
    for expiration, g in df.groupby("expiration"):
        call_g = g[g["is_call"]]
        put_g = g[~g["is_call"]]
        call_gex = float(call_g["signed_gex_usd_per_1pct_move"].sum())
        put_gex = float(put_g["signed_gex_usd_per_1pct_move"].sum())
        net_gex = call_gex + put_gex
        absolute_gex = float(g["gex_usd_per_1pct_move"].abs().sum())
        dte = dte_from_expiration(pd.Timestamp(expiration), as_of)

        # Weekly: Friday expiration that is not the 3rd Friday of the month
        # (rough heuristic for "monthly"). Not authoritative — determinable
        # only from calendar structure, not from OCC symbology here.
        exp_dt = pd.Timestamp(expiration)
        is_friday = exp_dt.weekday() == 4
        third_friday = _third_friday(exp_dt.year, exp_dt.month)
        is_monthly = is_friday and exp_dt.date() == third_friday
        is_weekly = is_friday and not is_monthly

        records.append(
            {
                "expiration": expiration,
                "dte": dte,
                "call_gex": call_gex,
                "put_gex": put_gex,
                "net_gex": net_gex,
                "absolute_gex": absolute_gex,
                "percent_of_total_absolute_gex": absolute_gex / total_absolute,
                "is_0dte": dte <= 1.0,
                "is_weekly": bool(is_weekly),
                "is_monthly": bool(is_monthly),
            }
        )

    out = pd.DataFrame(records).sort_values("expiration").reset_index(drop=True)
    return out


def _third_friday(year: int, month: int):
    import calendar

    c = calendar.Calendar()
    fridays = [d for d in c.itermonthdates(year, month) if d.month == month and d.weekday() == 4]
    return fridays[2] if len(fridays) >= 3 else (fridays[-1] if fridays else None)


def bucket_expirations(expiration_records: list) -> dict:
    """Buckets expiration-level records into standard DTE buckets for TV
    display (section 15's `expiration_buckets` field). Input is a list of
    dicts as produced by aggregate_by_expiration().to_dict(orient='records')
    (or the equivalent JSON-safe records used by GammaAnalysisResult).
    """
    buckets = {
        "0DTE": {"count": 0, "net_gex": 0.0, "absolute_gex": 0.0},
        "1_7_DTE": {"count": 0, "net_gex": 0.0, "absolute_gex": 0.0},
        "8_30_DTE": {"count": 0, "net_gex": 0.0, "absolute_gex": 0.0},
        "OVER_30_DTE": {"count": 0, "net_gex": 0.0, "absolute_gex": 0.0},
    }
    for r in expiration_records:
        dte = r["dte"]
        if dte <= 1.0:
            key = "0DTE"
        elif dte <= 7.0:
            key = "1_7_DTE"
        elif dte <= 30.0:
            key = "8_30_DTE"
        else:
            key = "OVER_30_DTE"
        buckets[key]["count"] += 1
        buckets[key]["net_gex"] += r["net_gex"]
        buckets[key]["absolute_gex"] += r["absolute_gex"]
    return buckets


def filter_by_dte(df: pd.DataFrame, min_dte: Optional[float], max_dte: Optional[float]) -> pd.DataFrame:
    out = df
    if min_dte is not None:
        out = out[out["dte"] >= min_dte]
    if max_dte is not None:
        out = out[out["dte"] <= max_dte]
    return out
