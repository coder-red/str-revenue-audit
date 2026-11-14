"""City registry for the audit + lead finder — single source of truth.

Set STR_CITY (austin|dallas|fort-worth) in the environment to switch metros;
audits, PDFs, the Streamlit apps, the lead scorer and the seed builder all
resolve their data path and metro labels from here. Default: austin.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CITIES: dict[str, dict] = {
    "austin":     {"slug": "austin", "name": "Austin",      "state": "TX",
                   "snapshot": "2026-09-17", "sub": "tx", "country": "united-states"},
    "dallas":     {"slug": "dallas", "name": "Dallas",      "state": "TX",
                   "snapshot": "2026-09-19", "sub": "tx", "country": "united-states"},
    "fort-worth": {"slug": "fort-worth", "name": "Fort Worth", "state": "TX",
                   "snapshot": "2026-09-17", "sub": "tx", "country": "united-states"},
}


def city(slug: str | None = None) -> dict:
    slug = (slug or os.environ.get("STR_CITY") or "austin").strip().lower()
    if slug not in CITIES:
        raise ValueError(f"unknown STR_CITY={slug!r} — known cities: {', '.join(sorted(CITIES))}")
    return CITIES[slug]


def label(slug: str | None = None) -> str:
    c = city(slug)
    return f"{c['name']}, {c['state']}"


def metro_line(slug: str | None = None) -> str:
    c = city(slug)
    return f"{c['name'].upper()}, {c['state']} · INSIDE AIRBNB {c['snapshot']}"


def data_dir(slug: str | None = None) -> Path:
    c = city(slug)
    return PROJECT_ROOT / "data" / f"{c['slug']}-{c['snapshot']}"


def default_data(slug: str | None = None) -> Path:
    return data_dir(slug) / "listings.csv.gz"


def data_source(slug: str | None = None) -> str:
    c = city(slug)
    return f"Inside Airbnb — {label(slug)}, snapshot {c['snapshot']} (CC BY 4.0)"


def snapshot_url(slug: str, filename: str = "listings.csv.gz") -> str:
    c = CITIES[slug]
    return (f"https://data.insideairbnb.com/{c['country']}/{c['sub']}/{c['slug']}/"
            f"{c['snapshot']}/data/{filename}")


def infer_slug(path) -> str | None:
    """Infer the metro from a --data path like data/fort-worth-2026-09-17/listings.csv.gz."""
    if not path:
        return None
    s = Path(path).as_posix().lower()
    for key in ("fort-worth", "dallas", "austin"):  # longest first
        c = CITIES[key]
        if f"{c['slug']}-{c['snapshot']}" in s:
            return key
    return None
