"""Build a comps table for a single listing.

Phase 1 scope (rule 7 — this is our own logic, kept small on purpose):

  1. Candidates = same room_type, beds within +/- 1, same neighbourhood.
  2. If fewer than `k_min` candidates, widen to a `radius_km` radius (haversine).
  3. If still too few, widen to metro-wide (same room_type only).
  4. Rank the remaining candidates by k-nearest distance over the scaled
     feature vector [price, bedrooms, beds, baths] (missing values median-imputed).

Usage:
    python -m str_audit.comps --listing-id 12345678 --k 12
    python -m str_audit.comps --demo            # deterministic example listing
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from str_audit.data import load_listings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = PROJECT_ROOT / "data" / "austin-2026-09-17" / "listings.csv.gz"
DEFAULT_OUT = PROJECT_ROOT / "outputs" / "comps.csv"

FEATURES = ["price", "bedrooms", "beds", "baths"]


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Works on scalars or aligned Series (vectorised)."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), np.radians(np.asarray(lat2, dtype=float))
    dphi = np.radians(np.asarray(lat2, dtype=float) - lat1)
    dlmb = np.radians(np.asarray(lon2, dtype=float) - lon1)
    a = (np.sin(dphi / 2) ** 2
         + math.cos(p1) * np.cos(np.radians(np.asarray(lat2, dtype=float)))
         * np.sin(dlmb / 2) ** 2)
    return 2 * r * np.arcsin(np.sqrt(a))


def _candidate_pool(df: pd.DataFrame, target: pd.Series, radius_km: float, k_min: int):
    """Stage 1: same room type + bed band + neighbourhood (or radius fallback)."""
    pool = df[df["room_type"] == target["room_type"]].copy()
    if pd.notna(target["beds"]):
        beds = target["beds"]
        band = pool[(pool["beds"] >= beds - 1) & (pool["beds"] <= beds + 1)]
        pool = band if len(band) >= k_min else pool

    same_hood = pool[pool["neighbourhood_cleansed"] == target["neighbourhood_cleansed"]]
    if len(same_hood) >= k_min:
        return same_hood, "neighbourhood"

    if pd.notna(target["latitude"]) and pd.notna(target["longitude"]):
        dist = haversine_km(target["latitude"], target["longitude"],
                            pool["latitude"], pool["longitude"])
        within = pool[np.asarray(dist) <= radius_km]
        if len(within) >= k_min:
            return within, f"radius {radius_km:.1f} km"
        expanded = pd.concat([same_hood, within]).drop_duplicates(subset=["id"])
        if len(expanded) >= k_min:
            return expanded, f"neighbourhood + {radius_km:.1f} km radius"

    return pool, "metro-wide (sparse comps)"


def build_comps(df: pd.DataFrame, listing_id: int, k: int = 12,
                radius_km: float = 3.0, k_min: int = 8) -> tuple[pd.DataFrame, str]:
    """Return (comps table, note on how the pool was built) for one listing."""
    match = df.index[df["id"] == listing_id]
    if len(match) == 0:
        sample_ids = df["id"].head(5).tolist()
        raise KeyError(f"listing {listing_id} not found. e.g. {sample_ids}")
    target = df.loc[match[0]]

    pool, how = _candidate_pool(df, target, radius_km, k_min)
    pool = pool[pool["id"] != target["id"]]
    if len(pool) == 0:
        raise ValueError("no comp candidates found — dataset too sparse")

    n = min(k, len(pool))
    X_target = target[FEATURES].to_frame().T.astype(float)
    X_pool = pool[FEATURES].astype(float)

    imputer = SimpleImputer(strategy="median")
    X_all = imputer.fit_transform(pd.concat([X_pool, X_target], ignore_index=True))
    X_pool_i, X_target_i = X_all[:-1], X_all[-1:]

    scaler = StandardScaler()
    X_pool_s = scaler.fit_transform(X_pool_i)
    X_target_s = scaler.transform(X_target_i)

    nn = NearestNeighbors(n_neighbors=n)
    dist, idx = nn.fit(X_pool_s).kneighbors(X_target_s)

    comps = pool.iloc[idx[0]].copy()
    comps.insert(0, "distance", np.round(dist[0], 3))
    comps.insert(0, "rank", range(1, n + 1))
    out_cols = ["rank", "distance", "id", "name", "neighbourhood_cleansed",
                "room_type", "bedrooms", "beds", "baths", "price",
                "availability_365", "number_of_reviews", "reviews_per_month",
                "last_review", "estimated_revenue_l365d"]
    return comps[out_cols].reset_index(drop=True), how


def _print_summary(target: pd.Series, comps: pd.DataFrame, how: str) -> None:
    med = comps["price"].median()
    print(f"\nTarget {int(target['id'])} — {target['name']!r}")
    print(f"  room_type={target['room_type']}  beds={target['beds']}  "
          f"price=${target['price']:.0f}  neighbourhood={target['neighbourhood_cleansed']}")
    print(f"  comp pool: {how}   n={len(comps)}   median comp price=${med:.0f}   "
          f"target vs median: {target['price'] - med:+.0f}")
    print("  Note: `estimated_revenue_l365d` is Inside Airbnb's own model, an ESTIMATE, "
          "not booked revenue.\n")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--listing-id", type=int, default=None)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--radius-km", type=float, default=3.0)
    ap.add_argument("--k-min", type=int, default=8)
    ap.add_argument("--demo", action="store_true",
                    help="use the first listing id (deterministic smoke run)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    df = load_listings(args.data)
    listing_id = args.listing_id
    if args.demo or listing_id is None:
        listing_id = int(df["id"].iloc[0])
        print(f"demo mode: using listing id {listing_id}")

    comps, how = build_comps(df, listing_id, k=args.k,
                             radius_km=args.radius_km, k_min=args.k_min)
    target = df.loc[df["id"] == listing_id].iloc[0]
    _print_summary(target, comps, how)
    print(comps.drop(columns="name").to_string(index=False))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    comps.to_csv(out, index=False)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
