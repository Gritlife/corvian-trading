"""
Dumps deterministic synthetic sample data to data/samples/*.json.

Run with:
    python scripts/generate_sample_data.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.sample_data import generate_spx_sample, generate_tsla_sample

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


def _contract_to_dict(c) -> dict:
    d = c.model_dump()
    d["option_type"] = c.option_type.value
    d["expiration"] = c.expiration.isoformat()
    d["quote_timestamp"] = c.quote_timestamp.isoformat()
    d["_synthetic"] = True
    d["_note"] = "SYNTHETIC SAMPLE DATA. Not real market data."
    return d


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    as_of = datetime(2026, 7, 2, 21, 0, 0, tzinfo=timezone.utc)  # fixed reference timestamp

    spx = generate_spx_sample(as_of=as_of)
    tsla = generate_tsla_sample(as_of=as_of)

    with open(OUT_DIR / "spx_sample_chain.json", "w") as f:
        json.dump([_contract_to_dict(c) for c in spx], f, indent=2)

    with open(OUT_DIR / "tsla_sample_chain.json", "w") as f:
        json.dump([_contract_to_dict(c) for c in tsla], f, indent=2)

    print(f"Wrote {len(spx)} SPX contracts to {OUT_DIR / 'spx_sample_chain.json'}")
    print(f"Wrote {len(tsla)} TSLA contracts to {OUT_DIR / 'tsla_sample_chain.json'}")


if __name__ == "__main__":
    main()
