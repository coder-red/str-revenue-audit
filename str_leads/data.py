"""Host-level table from the Inside Airbnb listings snapshot.

Why this file exists: `str_audit.data` loads the listing-level columns the audit
needs; the lead finder ALSO needs the host-level columns (host_name, host_since,
response rates, ...) which that loader intentionally drops. Here we read those
with our own DuckDB query and join them onto the per-listing facts that
`load_listings` already normalises. Project 1 files are not edited.

No scraping and no paid data — everything comes from the one CC BY 4.0 snapshot.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from str_audit.comps import DEFAULT_DATA  # single source of truth for the data path
from str_audit.data import load_listings
from str_audit.signals import MIN_DESCRIPTION_WORDS, STALE_REVIEW_DAYS

# Columns read straight from the raw snapshot (all_varchar, same trick as str_audit.data).
HOST_COLUMNS = [
    "host_id",
    "host_name",
    "host_since",
    "host_location",
    "host_about",
    "host_url",
    "host_profile_url",
    "host_response_rate",
    "host_acceptance_rate",
    "host_is_superhost",
    "host_identity_verified",
    "host_listings_count",
    "host_total_listings_count",
    "calculated_host_listings_count",
    "calculated_host_listings_count_entire_homes",
    "first_review",
]

_BOOL = {"t": True, "f": False, "true": True, "false": False}


def _to_rate(series: pd.Series) -> pd.Series:
    """'95%' -> 0.95; empty/NaN stays NaN."""
    cleaned = series.fillna("").str.strip().str.rstrip("%")
    return pd.to_numeric(cleaned, errors="coerce") / 100.0


def _to_bool(series: pd.Series) -> pd.Series:
    return series.fillna("").str.strip().str.lower().map(_BOOL)


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _to_count(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("float")


def load_host_fields(path: str | Path) -> pd.DataFrame:
    """Read + normalise host-level columns; one row per host_id (first non-null wins)."""
    path = Path(path)
    cols = ", ".join(HOST_COLUMNS)
    df = duckdb.sql(
        f"SELECT {cols} FROM read_csv_auto('{path.as_posix()}', all_varchar=True)"
    ).df()

    df["host_id"] = _to_number(df["host_id"]).astype("Int64")
    df = df.dropna(subset=["host_id"]).reset_index(drop=True)

    df["host_since"] = pd.to_datetime(df["host_since"], errors="coerce")
    df["first_review"] = pd.to_datetime(df["first_review"], errors="coerce")
    df["host_response_rate"] = _to_rate(df["host_response_rate"])
    df["host_acceptance_rate"] = _to_rate(df["host_acceptance_rate"])
    df["host_is_superhost"] = _to_bool(df["host_is_superhost"])
    df["host_identity_verified"] = _to_bool(df["host_identity_verified"])
    for col in ("host_listings_count", "host_total_listings_count",
                "calculated_host_listings_count",
                "calculated_host_listings_count_entire_homes"):
        df[col] = _to_count(df[col])
    for col in ("host_name", "host_location", "host_about", "host_url", "host_profile_url"):
        df[col] = df[col].astype("string").str.strip()

    # One row per host: take the first non-null value per column (nat/nan aware).
    df = df.sort_index()

    def _coalesce(s: pd.Series):
        for v in s:
            try:
                if pd.notna(v):
                    return v
            except (TypeError, ValueError):
                return v
        return None

    grouped = df.groupby("host_id", as_index=False).agg(
        {col: _coalesce for col in HOST_COLUMNS if col != "host_id"}
    )

    # _coalesce returns Python/object values; restore types.
    grouped["host_since"] = pd.to_datetime(grouped["host_since"], errors="coerce")
    grouped["first_review"] = pd.to_datetime(grouped["first_review"], errors="coerce")
    for col in ("host_response_rate", "host_acceptance_rate"):
        grouped[col] = pd.to_numeric(grouped[col], errors="coerce")
    for col in ("host_is_superhost", "host_identity_verified"):
        grouped[col] = grouped[col].astype("boolean")
    for col in ("host_listings_count", "host_total_listings_count",
                "calculated_host_listings_count",
                "calculated_host_listings_count_entire_homes"):
        grouped[col] = pd.to_numeric(grouped[col], errors="coerce")
    for col in ("host_name", "host_location", "host_about", "host_url", "host_profile_url"):
        grouped[col] = grouped[col].astype("string")
    return grouped


def _listing_flags(listings: pd.DataFrame, today: date) -> pd.DataFrame:
    """Per-listing boolean flags used by the lead score."""
    df = listings.copy()
    # Project 1's loader leaves host_id as a raw string; coerce for the join with host fields.
    df["host_id"] = pd.to_numeric(df["host_id"], errors="coerce").astype("Int64")

    # Price position vs neighbourhood median (metro median fallback for thin neighbourhoods).
    nbhd_counts = df.groupby("neighbourhood_cleansed")["price"].transform("count")
    nbhd_median = df.groupby("neighbourhood_cleansed")["price"].transform("median")
    if df["price"].median() is not None and pd.notna(df["price"].median()):
        nbhd_median = nbhd_median.where(nbhd_counts >= 10, df["price"].median())
    df["price_pct_below_nbhd"] = (nbhd_median - df["price"]) / nbhd_median * 100.0

    last = pd.to_datetime(df["last_review"], errors="coerce")
    days_since = (pd.Timestamp(today) - last).dt.days
    n_reviews = pd.to_numeric(df["number_of_reviews"], errors="coerce").fillna(0)
    df["stale"] = (n_reviews == 0) | (days_since > STALE_REVIEW_DAYS)

    words = df["description"].fillna("").str.split().str.len()
    df["thin_desc"] = words < MIN_DESCRIPTION_WORDS  # includes missing/empty description

    rev = pd.to_numeric(df["estimated_revenue_l365d"], errors="coerce")
    p33 = rev.quantile(0.33)
    df["low_modelled_revenue"] = rev <= p33 if pd.notna(p33) else False
    return df


def build_host_table(path: str | Path = DEFAULT_DATA,
                     today: date | None = None) -> pd.DataFrame:
    """Aggregate the snapshot to one row per host with lead-score inputs attached."""
    today = today or date.today()
    listings = _listing_flags(load_listings(path), today)
    hosts = load_host_fields(path)

    agg = listings.groupby("host_id", as_index=False).agg(
        n_listings=("id", "count"),
        austin_listing_ids=("id", lambda s: tuple(int(x) for x in s)),
        min_price=("price", "min"),
        median_price=("price", "median"),
        frac_below_nbhd=("price_pct_below_nbhd", lambda s: float((s >= 10.0).mean())),
        any_stale=("stale", "max"),
        any_thin_desc=("thin_desc", "max"),
        n_low_revenue=("low_modelled_revenue", "sum"),
        total_modelled_revenue=("estimated_revenue_l365d", "sum"),
        min_modelled_revenue=("estimated_revenue_l365d", "min"),
        weakest_listing_id=("estimated_revenue_l365d", lambda s: _weakest_id(listings, s)),
        median_last_review=("last_review", "median"),
        neighbourhoods=("neighbourhood_cleansed", lambda s: tuple(sorted(set(s.dropna())))),
    )

    merged = hosts.merge(agg, on="host_id", how="right", validate="1:1")
    tenure_months = (pd.Timestamp(today) - merged["host_since"]).dt.days / 30.44
    merged["host_tenure_months"] = tenure_months.round(1)  # stays NaN when the snapshot has no host_since
    return merged.sort_values(["n_listings"], ascending=False, ignore_index=True)


def _weakest_id(listings: pd.DataFrame, rev_series: pd.Series):
    """Listing id with the lowest modelled revenue (NaN dropped), else stalest, else first."""
    sub = listings.loc[rev_series.index]
    rev = pd.to_numeric(sub["estimated_revenue_l365d"], errors="coerce")
    if rev.notna().any():
        return int(sub.loc[rev.idxmin(), "id"])
    last = pd.to_datetime(sub["last_review"], errors="coerce")
    if last.notna().any():
        return int(sub.loc[last.idxmin(), "id"])
    return int(sub["id"].iloc[0])
