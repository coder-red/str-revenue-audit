"""Phase 2 orchestrator: listing -> comps -> signals -> revenue estimate -> summary.

Usage:
    python -m str_audit.audit --listing-id 5094445
    python -m str_audit.audit --demo

Outputs: prints a readable report and writes outputs/audit_<id>.json.
(Phase 3 will render the same dict to the one-page PDF.)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from str_audit.comps import DEFAULT_DATA, PROJECT_ROOT, build_comps
from str_audit.data import load_listings
from str_audit.llm import summarize_audit
from str_audit.revenue import estimate_gap
from str_audit.signals import run_signals, top_fixes

DEFAULT_OUT_DIR = PROJECT_ROOT / "outputs"


def _jsonable(v):
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat() if not pd.isna(v) else None
    if pd.isna(v):
        return None
    return v


def _sanitize(obj):
    """Recursively convert pandas/numpy values into strict-JSON types."""
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return None if pd.isna(obj) else obj.isoformat()
    if obj is pd.NA or obj is pd.NaT:
        return None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return None if math.isnan(obj) else float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def run_audit(df: pd.DataFrame, listing_id: int, k: int = 12, radius_km: float = 3.0,
              k_min: int = 8, photo_count: int | None = None,
              provider: str | None = None) -> dict:
    comps, pool_how = build_comps(df, listing_id, k=k, radius_km=radius_km, k_min=k_min)
    target = df.loc[df["id"] == listing_id].iloc[0]

    signals = run_signals(target, comps_median_price=comps["price"].median(),
                          photo_count=photo_count)
    estimate = estimate_gap(target, comps)

    target_bits = {k_: _jsonable(target[k_]) for k_ in [
        "id", "name", "neighbourhood_cleansed", "room_type", "property_type",
        "bedrooms", "beds", "baths", "price", "minimum_nights", "availability_365",
        "number_of_reviews", "number_of_reviews_ltm", "last_review",
        "reviews_per_month", "review_scores_rating",
        "estimated_occupancy_l365d", "estimated_revenue_l365d",
        "picture_url", "description",
    ]}

    audit = {
        "listing_id": int(listing_id),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_source": "Inside Airbnb — Austin, TX, snapshot 2026-09-17 (CC BY 4.0)",
        "target": target_bits,
        "comps": {
            "n": int(len(comps)),
            "pool": pool_how,
            "median_price": _jsonable(comps["price"].median()),
            "table": comps.drop(columns=["name"]).to_dict(orient="records"),
        },
        "signals": signals,
        "top_fixes": top_fixes(signals),
        "estimate": estimate,
    }

    summary, provider_used = summarize_audit(audit, provider=provider)
    audit["llm_summary"] = summary
    audit["llm_provider_used"] = provider_used
    return audit


def _print_report(audit: dict) -> None:
    t = audit["target"]
    n = audit["estimate"]["numbers"]
    print("=" * 72)
    print(f"STR LISTING REVENUE AUDIT — listing {audit['listing_id']}")
    print(audit["data_source"])
    print("=" * 72)
    print(f"\n{t['name']}")
    print(f"{t['room_type']} · {t['bedrooms']}BR · {t['baths']} bath · ${t['price']:.0f}/night · "
          f"{t['neighbourhood_cleansed']} · {t['number_of_reviews']} reviews")
    print("\n-- SIGNALS ---------------------------------------------------------------")
    for s in audit["signals"]:
        print(f"  [{s['status'].upper():7s}] {s['summary']}")
    print("\n-- ESTIMATED REVENUE GAP (all ESTIMATES, not booked revenue) -------------")
    if n["est_annual_price_gap"] is not None:
        print(f"  Price positioning gap:        ${n['est_annual_price_gap']:+,.0f} / yr")
    if n["est_annual_ia_revenue_gap"] is not None:
        print(f"  vs comp-median Inside Airbnb model revenue: ${n['est_annual_ia_revenue_gap']:+,.0f} / yr")
    if n["target_estimated_revenue_l365d"] is not None:
        print(f"  Inside Airbnb model estimate for this listing: ${n['target_estimated_revenue_l365d']:,.0f} / yr")
    print(f"  (comp median price ${n['comp_median_price']}, comp avg occupancy {n['comp_avg_occupancy']})")
    print("\n  How we calculated it:")
    for line in audit["estimate"]["method"]:
        print(f"   - {line}")
    print("\n-- TOP FIXES ---------------------------------------------------------------")
    for i, fix in enumerate(audit["top_fixes"], 1):
        print(f"  {i}. {fix}")
    print(f"\n-- AUDIT SUMMARY ({audit['llm_provider_used']}) ----------------------------------")
    print(audit["llm_summary"])
    print()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--listing-id", type=int, default=None)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--radius-km", type=float, default=3.0)
    ap.add_argument("--k-min", type=int, default=8)
    ap.add_argument("--photo-count", type=int, default=None,
                    help="user-entered photo count (public data has none)")
    ap.add_argument("--provider", choices=["gemini", "groq", "none"], default=None)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = ap.parse_args()

    df = load_listings(args.data)
    listing_id = args.listing_id
    if args.demo or listing_id is None:
        listing_id = int(df["id"].iloc[0])
        print(f"demo mode: using listing id {listing_id}")

    provider = None if args.provider in (None, "none") else args.provider
    audit = run_audit(df, listing_id, k=args.k, radius_km=args.radius_km,
                      k_min=args.k_min, photo_count=args.photo_count,
                      provider=provider)
    _print_report(audit)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"audit_{listing_id}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(_sanitize(audit), fh, indent=2, allow_nan=False)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
