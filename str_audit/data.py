"""Load and normalise an Inside Airbnb `listings.csv.gz` file.

Why this file exists: all of Inside Airbnb's messy encodings live here, once.
Everything downstream (comps, audit, PDF) sees a clean, typed DataFrame.

Normalisations applied:
  * `price` "$1,234.00"          -> float
  * `bathrooms_text` "1.5 baths" -> float `baths` (first number in the string)
  * `neighbourhood_cleansed`     -> read as string (DuckDB auto-detect guessed BIGINT otherwise)
  * `instant_bookable` / `has_availability`  't'/'f' -> bool
  * `bedrooms` / `beds`                     -> float, missing kept as NaN (studios)
  * rows with missing/zero price or missing id are dropped
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd

# Columns we actually need. Selecting them at read time keeps memory sane.
COLUMNS = [
    "id",
    "name",
    "host_id",
    "neighbourhood_cleansed",
    "neighbourhood_group_cleansed",
    "latitude",
    "longitude",
    "property_type",
    "room_type",
    "bedrooms",
    "beds",
    "bathrooms_text",
    "price",
    "minimum_nights",
    "has_availability",
    "availability_365",
    "number_of_reviews",
    "number_of_reviews_ltm",
    "last_review",
    "reviews_per_month",
    "review_scores_rating",
    "estimated_occupancy_l365d",
    "estimated_revenue_l365d",
    "instant_bookable",
    "picture_url",
    "description",
]

_BOOL = {"t": True, "f": False, "true": True, "false": False}


def _to_bool(series: pd.Series) -> pd.Series:
    return series.str.strip().str.lower().map(_BOOL)


def _to_price(series: pd.Series) -> pd.Series:
    cleaned = series.str.replace(r"[$,\s]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def _to_baths(series: pd.Series) -> pd.Series:
    return series.str.extract(r"(\d+(?:\.\d+)?)", expand=False).pipe(
        pd.to_numeric, errors="coerce"
    )


def load_listings(path: str | Path) -> pd.DataFrame:
    """Read listings.csv.gz into a typed, cleaned DataFrame."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python scripts/download_data.py` first."
        )
    # all_varchar avoids DuckDB mis-guessing types (e.g. neighbourhood_cleansed as BIGINT).
    cols = ", ".join(COLUMNS)
    query = f"SELECT {cols} FROM read_csv_auto('{path.as_posix()}', all_varchar=True)"
    df = duckdb.sql(query).df()

    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
    for col in ("bedrooms", "beds"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["baths"] = _to_baths(df["bathrooms_text"].fillna(""))
    df["price"] = _to_price(df["price"].fillna(""))
    for col in ("latitude", "longitude", "reviews_per_month", "review_scores_rating",
                "minimum_nights"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("availability_365", "number_of_reviews", "number_of_reviews_ltm",
                "estimated_occupancy_l365d", "estimated_revenue_l365d"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    df["last_review"] = pd.to_datetime(df["last_review"], errors="coerce")
    df["instant_bookable"] = _to_bool(df["instant_bookable"].fillna(""))
    df["has_availability"] = _to_bool(df["has_availability"].fillna(""))
    df["neighbourhood_cleansed"] = df["neighbourhood_cleansed"].astype("string")

    df = df.dropna(subset=["id", "price"])
    df = df[df["price"] > 0].reset_index(drop=True)
    return df
