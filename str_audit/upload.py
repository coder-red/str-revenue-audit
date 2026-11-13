"""Forgiving CSV/JSON upload parsing. Pure functions — no Streamlit imports.

Real-world listing exports never match our template exactly, so we:
  1. normalize every column name (lowercase, punctuation -> _),
  2. map known aliases to canonical fields,
  3. derive baths from bathrooms_text when baths is missing,
  4. report the mapping so the user can see what we understood.
"""

from __future__ import annotations

import re

ALIASES = {
    "name": ["name", "title", "listing_name", "listing_title", "headline"],
    "price": ["price", "nightly_price", "night_price", "rate", "price_per_night",
              "nightly_rate", "base_price", "nightly_price_usd"],
    "room_type": ["room_type", "roomtype", "type", "listing_type", "room"],
    "neighbourhood": ["neighbourhood", "neighborhood", "neighbourhood_cleansed",
                      "zip", "zipcode", "zip_code", "postal_code", "postal", "area"],
    "bedrooms": ["bedrooms", "bedrooms_count", "bed_rooms", "num_bedrooms"],
    "beds": ["beds", "beds_count", "number_of_beds", "num_beds"],
    "baths": ["baths", "bathrooms", "number_of_bathrooms", "num_bathrooms"],
    "bathrooms_text": ["bathrooms_text", "baths_text"],
    "availability_365": ["availability_365", "availability", "available_nights",
                         "nights_available", "available_year"],
    "number_of_reviews": ["number_of_reviews", "reviews", "review_count",
                          "num_reviews", "no_of_reviews", "reviews_count"],
    "reviews_per_month": ["reviews_per_month", "rpm", "reviews_monthly", "reviews_per_mo",
                          "reviews_mo", "review_count_per_month"],
    "last_review": ["last_review", "last_review_date", "last_review_at"],
    "description": ["description", "desc", "listing_description", "summary"],
    "photo_count": ["photo_count", "photos", "number_of_photos", "photos_count",
                    "num_photos"],
    "estimated_revenue_l365d": ["estimated_revenue_l365d", "est_revenue",
                                "estimated_revenue", "revenue_estimate"],
    "estimated_occupancy_l365d": ["estimated_occupancy_l365d", "occupancy", "est_occupancy"],
}


def _norm_col(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _norm_room_type(value: object) -> str:
    s = str(value or "").lower()
    if "shared" in s:
        return "Shared room"
    if "private" in s:
        return "Private room"
    return "Entire home/apt"   # "entire", "whole", house, condo, or unknown


def _to_number(value: object):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[$,\s]", "", str(value))
    try:
        return float(s)
    except ValueError:
        return None


def _to_baths(baths_value: object, bathrooms_text: object):
    n = _to_number(baths_value)
    if n is not None:
        return n
    m = re.search(r"\d+(?:\.\d+)?", str(bathrooms_text or ""))
    return float(m.group()) if m else None


def map_uploaded_row(row: dict) -> dict:
    """One raw row (any column names) -> our target, plus the mapping we inferred."""
    normed = {_norm_col(k): v for k, v in row.items()}

    mapping: dict[str, str] = {}
    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            if alias in normed:
                mapping[canonical] = alias
                break

    def raw(canonical: str):
        src = mapping.get(canonical)
        return normed.get(src) if src else None

    target = {
        "name": str(raw("name") or "Uploaded listing"),
        "price": _to_number(raw("price")),
        "room_type": _norm_room_type(raw("room_type")),
        "neighbourhood": str(raw("neighbourhood")) if raw("neighbourhood") not in (None, "") else "78704",
        "bedrooms": _to_number(raw("bedrooms")),
        "beds": _to_number(raw("beds")),
        "baths": _to_baths(raw("baths"), raw("bathrooms_text")),
        "availability_365": _to_number(raw("availability_365")),
        "number_of_reviews": _to_number(raw("number_of_reviews")),
        "reviews_per_month": _to_number(raw("reviews_per_month")),
        "last_review": raw("last_review"),
        "description": raw("description"),
        "estimated_revenue_l365d": _to_number(raw("estimated_revenue_l365d")),
        "estimated_occupancy_l365d": _to_number(raw("estimated_occupancy_l365d")),
    }
    photo_count = _to_number(raw("photo_count"))
    return {
        "target": target,
        "photo_count": int(photo_count) if photo_count is not None else None,
        "mapping": mapping,
        "missing": [k for k in ("price",) if target[k] is None],
        "columns": [str(k) for k in row.keys()],
    }
