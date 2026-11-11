"""Download the Inside Airbnb Austin 2026-09-17 snapshot into data/.

Why this file exists (rule 7): data acquisition is *our* glue code — but it's
thin and boring on purpose: a URL list, an idempotent downloader, stdlib only.
No scraping of Airbnb; we only fetch the files Inside Airbnb publishes.

Usage:
    python scripts/download_data.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

SNAPSHOT_DATE = "2026-09-17"
BASE = f"https://data.insideairbnb.com/united-states/tx/austin/{SNAPSHOT_DATE}/data"
FILES = ["listings.csv.gz", "calendar.csv.gz", "reviews.csv.gz"]

DEST_DIR = Path(__file__).resolve().parent.parent / "data" / f"austin-{SNAPSHOT_DATE}"


def main() -> int:
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        dest = DEST_DIR / name
        url = f"{BASE}/{name}"
        if dest.exists():
            print(f"skip (exists): {dest}  [{dest.stat().st_size / 1e6:.1f} MB]")
            continue
        print(f"downloading: {url}")
        urllib.request.urlretrieve(url, dest)
        print(f"  -> {dest}  [{dest.stat().st_size / 1e6:.1f} MB]")
    print("Done. Attribution: Inside Airbnb, Austin TX snapshot", SNAPSHOT_DATE, "(CC BY 4.0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
