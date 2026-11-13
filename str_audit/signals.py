"""Audit signals — weak photos / description, review recency, price vs comp median.

Our own logic (rule 5). Each signal returns a dict:
    {key, status, value, summary, detail}
status: "pass" | "warn" | "fail" | "unknown"
Thresholds are module constants so they can be defended and tuned in one place.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

# --- tunable thresholds (defend these in the report footer) -------------------
MIN_DESCRIPTION_WORDS = 60        # below this, guests bounce off the listing copy
MIN_PHOTOS = 8                    # user-entered photo count below this is weak
STALE_REVIEW_DAYS = 180           # no new review in 6+ months = listing feels dead
LOW_REVIEWS_PER_MONTH = 0.5       # under half a review/month, market isn't booking it
PRICE_COMP_BAND_PCT = 10.0        # >10% above comp median = overpriced risk;
                                  # >10% below = likely leaving money on the table


def _word_count(text) -> int | None:
    if not isinstance(text, str) or not text.strip():
        return None
    return len(text.split())


def signal_description(target: pd.Series) -> dict:
    words = _word_count(target.get("description"))
    if words is None:
        return dict(key="description", status="fail", value=0,
                    summary="No description",
                    detail="The listing has no description at all. "
                           "Guests book what they can picture; a missing description is a silent deal-breaker.")
    if words < MIN_DESCRIPTION_WORDS:
        return dict(key="description", status="warn", value=words,
                    summary=f"Thin description ({words} words)",
                    detail=f"{words} words is below the {MIN_DESCRIPTION_WORDS}-word mark. "
                           f"Comp listings with full, amenity-rich copy convert better.")
    return dict(key="description", status="pass", value=words,
                summary=f"Description OK ({words} words)", detail="")


def signal_photos(photo_count: int | None) -> dict:
    """Inside Airbnb publishes no photo count, so for dataset targets this is honestly
    reported as unknown. Phase 3 (user-entered listing) passes the real count."""
    if photo_count is None:
        return dict(key="photos", status="unknown", value=None,
                    summary="Photo count not available in public data",
                    detail="Inside Airbnb does not publish photo counts. Enter the listing's "
                           "photo count in the upload form for a real check (weak below "
                           f"{MIN_PHOTOS} photos).")
    if photo_count < MIN_PHOTOS:
        return dict(key="photos", status="warn", value=photo_count,
                    summary=f"Only {photo_count} photos",
                    detail=f"Below the {MIN_PHOTOS}-photo benchmark. Bright, staged, wide-angle "
                           f"photos of the hero room and bath are the cheapest conversion lever.")
    return dict(key="photos", status="pass", value=photo_count,
                summary=f"Photo count OK ({photo_count})", detail="")


def signal_review_recency(target: pd.Series, today: date | None = None) -> dict:
    today = today or date.today()
    n_reviews = target.get("number_of_reviews")
    last = target.get("last_review")

    if (pd.isna(n_reviews) or int(n_reviews) == 0):
        return dict(key="review_recency", status="fail", value=None,
                    summary="No reviews yet",
                    detail="Zero reviews on record. No social proof = low conversion and low "
                           "search placement. Price to win first bookings, then harvest reviews.")
    if pd.isna(last):
        return dict(key="review_recency", status="unknown", value=None,
                    summary=f"Last-review date missing ({int(n_reviews)} reviews on record)",
                    detail="Review count is known but the last-review date isn't in this file. "
                           "Enter the listing manually with the last review date for a freshness check.")

    days = (today - last.date()).days if hasattr(last, "date") else (today - last).days
    rpm = target.get("reviews_per_month")
    rpm_val = float(rpm) if pd.notna(rpm) else math.nan

    if days > STALE_REVIEW_DAYS:
        return dict(key="review_recency", status="fail" if days > 365 else "warn",
                    value=days,
                    summary=f"Last review {days} days ago",
                    detail=f"No review in {days} days (stale after {STALE_REVIEW_DAYS}). "
                           f"Momentum matters more than rating; recent reviews reset the 'booked recently' signal.")
    if not math.isnan(rpm_val) and rpm_val < LOW_REVIEWS_PER_MONTH:
        return dict(key="review_recency", status="warn",
                    value=rpm_val,
                    summary=f"Low booking velocity ({rpm_val:.2f} reviews/mo)",
                    detail=f"Below {LOW_REVIEWS_PER_MONTH} reviews/month suggests the listing is "
                           f"getting looks but not bookings — check title, cover photo and price.")
    return dict(key="review_recency", status="pass", value=days,
                summary=f"Reviews are fresh (last {days} days ago, "
                        f"{rpm_val:.2f}/mo)" if not math.isnan(rpm_val) else f"Reviews are fresh (last {days} days ago)",
                detail="")


def signal_price_vs_comps(target_price: float, comps_median_price: float) -> dict:
    if comps_median_price is None or pd.isna(comps_median_price) or comps_median_price <= 0:
        return dict(key="price_vs_comps", status="unknown", value=None,
                    summary="No comp median available", detail="Not enough comps to compare.")
    pct = (target_price - comps_median_price) / comps_median_price * 100.0
    if pct > PRICE_COMP_BAND_PCT:
        return dict(key="price_vs_comps", status="warn", value=round(pct, 1),
                    summary=f"{pct:+.1f}% above comp median (${comps_median_price:.0f})",
                    detail="Priced above the comp set. Likely trading occupancy for rate — "
                           "check whether booked nights justify it; if not, trim toward median.")
    if pct < -PRICE_COMP_BAND_PCT:
        return dict(key="price_vs_comps", status="warn", value=round(pct, 1),
                    summary=f"{pct:+.1f}% below comp median (${comps_median_price:.0f})",
                    detail="Priced below the comp set. Demand exists at this quality level — "
                           "you are likely leaving revenue on the table every booked night.")
    return dict(key="price_vs_comps", status="pass", value=round(pct, 1),
                summary=f"Priced in line with comps ({pct:+.1f}%)", detail="")


def run_signals(target: pd.Series, comps_median_price: float,
                photo_count: int | None = None,
                today: date | None = None) -> list[dict]:
    return [
        signal_photos(photo_count),
        signal_description(target),
        signal_review_recency(target, today=today),
        signal_price_vs_comps(target["price"], comps_median_price),
    ]


def top_fixes(signals: list[dict]) -> list[str]:
    """Rank actionable fixes: fail > warn > unknown, stable within severity."""
    order = {"fail": 0, "warn": 1, "unknown": 2, "pass": 3}
    actionable = [(order[s["status"]], i, s) for i, s in enumerate(signals) if s["status"] != "pass"]
    actionable.sort(key=lambda t: (t[0], t[1]))
    fixes = []
    for _, _, s in actionable:
        fix = {
            "description": "Rewrite the listing description to 120+ words covering sleeps, "
                           "amenities, transit and what makes the space memorable.",
            "photos": "Shoot or swap in at least 8 professional-looking photos: hero room, "
                      "bath, kitchen, one detail shot.",
            "review_recency": "Re-engage: price to your first/ next review, make checkout "
                              "frictionless, ask happy guests for honest reviews.",
            "price_vs_comps": "Reprice toward the comp median (see ESTIMATE on page 1) and "
                              "review weekly until occupancy stabilises.",
        }.get(s["key"], s["summary"])
        fixes.append(fix)
    return fixes
