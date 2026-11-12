"""Phase 1 — build the host-level lead table for Austin and print the ranking.

Usage:
    python scripts/score_leads.py                  # rank all hosts, write outputs/leads_ranked.csv
    python scripts/score_leads.py --top-n 25       # print more rows
    python scripts/score_leads.py --include-agencies   # keep likely PM agencies in the ranking

Nothing is sent, nothing is stored — this is read-only over the Inside Airbnb snapshot.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from str_leads.data import build_host_table
from str_leads.score import MAX_SCORE, SCORE_VERSION, score_hosts

DEFAULT_CSV = "outputs/leads_ranked.csv"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=None, help="path to listings.csv.gz (default: Austin snapshot)")
    ap.add_argument("--top-n", type=int, default=20, help="rows to print (default 20)")
    ap.add_argument("--csv", default=DEFAULT_CSV, help="where to write the ranked CSV")
    ap.add_argument("--include-agencies", action="store_true",
                    help="do not exclude likely property-management agencies (>=25 listings)")
    args = ap.parse_args()

    print("Loading snapshot and building host table…")
    table = build_host_table(args.data) if args.data else build_host_table()
    scored = score_hosts(table, exclude_agencies=not args.include_agencies)

    ranked = scored[~scored["excluded_agency"]] if not args.include_agencies else scored
    agencies = scored[scored["agency_reason"].notna()]
    n_agencies = int(scored["excluded_agency"].sum())
    print(f"hosts: {len(scored)} | likely agencies excluded: {n_agencies} | "
          f"ranked: {len(ranked)} | score version {SCORE_VERSION} (max {MAX_SCORE})")
    if args.include_agencies:
        print(f"(--include-agencies: {len(agencies)} company-like hosts kept in ranking)")
    else:
        for r in agencies.head(5).itertuples(index=False):
            print(f"  excluded: host {r.host_id} '{r.host_name}' — {r.agency_reason}")

    cols = ["host_id", "host_name", "n_listings", "score", "median_price",
            "total_modelled_revenue", "host_tenure_months", "host_response_rate"]
    print(f"\nTop {min(args.top_n, len(ranked))} of ranked hosts:")
    print(ranked[cols].head(args.top_n).to_string(index=False))

    for i, (_, row) in enumerate(ranked.head(args.top_n).iterrows(), 1):
        print(f"\n#{i} host {row.host_id} — {row.host_name} (score {row.score}/{MAX_SCORE}, "
              f"{row.n_listings} listings)")
        for reason in row["reasons"]:
            print(f"    {reason}")

    out = ranked.copy()
    out["reasons"] = out["reasons"].apply(lambda rs: " | ".join(rs))
    out = out.drop(columns=["austin_listing_ids", "neighbourhoods"])
    out.to_csv(args.csv, index=False, encoding="utf-8-sig")
    print(f"\nwrote {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
