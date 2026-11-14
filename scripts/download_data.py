"""Download an Inside Airbnb snapshot into data/ — city configurable.

Usage:
    python scripts/download_data.py                 # Austin (default); listings + calendar + reviews
    python scripts/download_data.py --city dallas    # Dallas snapshot; listings only
    python scripts/download_data.py --city fort-worth --full   # all three files
    python scripts/download_data.py --all-listings   # listings.csv.gz for every registered city

City registry lives in str_audit/cities.py (snapshot dates, URL paths).
Default downloads listings.csv.gz only (the scoring/audit pipeline never reads the others);
pass --full to also grab calendar.csv.gz and reviews.csv.gz (~70 MB).
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from str_audit import cities

FILES_FULL = ["listings.csv.gz", "calendar.csv.gz", "reviews.csv.gz"]


def fetch(slug: str, files: list[str]) -> None:
    dest_dir = cities.data_dir(slug)
    dest_dir.mkdir(parents=True, exist_ok=True)
    label = cities.label(slug)
    for name in files:
        dest = dest_dir / name
        if dest.exists():
            print(f"skip (exists): {dest}  [{dest.stat().st_size / 1e6:.1f} MB]")
            continue
        url = cities.snapshot_url(slug, name)
        print(f"downloading {label}: {url}")
        urllib.request.urlretrieve(url, dest)
        print(f"  -> {dest}  [{dest.stat().st_size / 1e6:.1f} MB]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--city", choices=list(cities.CITIES), default=None,
                    help="which metro to fetch (default: austin, or STR_CITY env if set)")
    ap.add_argument("--full", action="store_true",
                    help="also fetch calendar.csv.gz and reviews.csv.gz (~70 MB)")
    ap.add_argument("--all-listings", action="store_true",
                    help="fetch listings.csv.gz for EVERY registered city")
    args = ap.parse_args()

    slugs = list(cities.CITIES) if args.all_listings else [args.city or cities.city()["slug"]]
    files = FILES_FULL if (args.full and not args.all_listings) else ["listings.csv.gz"]
    for slug in slugs:
        fetch(slug, files)
    print("Done. Attribution: Inside Airbnb (CC BY 4.0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
