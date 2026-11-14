"""Build the committed public demo seed: data/lead_seed.parquet.

Contains the FULL Redact-mode lead table (score v2.0, cutoff 5) with host names
replaced by initials — no real owner is identifiable from the committed file.
The hosted portfolio instance reads this on first boot instead of recomputing
the 60–90 s pipeline. Kept deterministic: regenerate when the score changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json

import pandas as pd  # noqa: E402

from str_leads.data import build_host_table
from str_leads.score import SCORE_VERSION, score_hosts
from str_leads.store import redact_name
from str_audit.comps import DEFAULT_DATA

OUT = Path(__file__).resolve().parent.parent / "data" / "lead_seed.parquet"


def main() -> int:
    print("building host table from", DEFAULT_DATA)
    table = build_host_table()
    ranked = score_hosts(table, agency_cutoff=5)
    ranked = ranked[~ranked["excluded_agency"]].reset_index(drop=True)
    ranked["host_name"] = ranked["host_name"].map(redact_name)
    ranked["score_version"] = SCORE_VERSION
    ranked["reasons"] = ranked["reasons"].map(lambda rs: json.dumps(list(rs), ensure_ascii=False))
    ranked["neighbourhoods"] = ranked["neighbourhoods"].map(
        lambda ns: json.dumps(list(ns), ensure_ascii=False))
    keep = ["host_id", "host_name", "n_listings", "score", "score_version", "reasons",
            "total_modelled_revenue", "min_modelled_revenue", "median_price",
            "calculated_host_listings_count", "weakest_listing_id", "neighbourhoods"]
    ranked[keep].to_parquet(OUT, index=False)
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1024:.0f} KB, {len(ranked)} rows, names redacted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
