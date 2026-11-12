"""The lead score — custom, transparent, explainable (rule 7).

One row per host -> integer score + human-readable reasons. No ML model: with
no conversion labels, an explainable heuristic is the honest tool, and it is the
artifact a non-technical property manager can be shown and challenge.

Weights and thresholds are named constants so they can be defended and tuned in
one place (same pattern as str_audit/signals.py). Versioned so scores in the DB
can be interpreted later.

Snapshot limitation (Austin 2026-09-17): Inside Airbnb publishes host_since and
host_response_rate as 100% NULL in this file — those two points never fire. The
code still checks them, so future snapshots that carry the fields work as built.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

SCORE_VERSION = "1.0"

# --- tunable weights -----------------------------------------------------------
WEIGHT_MULTI_LISTING = 3      # host runs >= 2 listings in this metro
WEIGHT_TRIPLE_PLUS = 1        # ... plus one more point at >= 3 listings
WEIGHT_PRICE_BELOW_NBHD = 2   # any listing >= 10% below its neighbourhood median price
WEIGHT_STALE_REVIEWS = 2      # any listing with zero reviews or reviews stale > 180 days
WEIGHT_THIN_DESCRIPTION = 1   # any listing with a thin/missing description (< 60 words)
WEIGHT_LOW_REVENUE = 2        # any listing in the metro's bottom modelled-revenue tercile
WEIGHT_NOT_SUPERHOST = 1      # host is not a superhost (unlikely to have a PM)
WEIGHT_SLOW_RESPONSE = 1      # host reply rate < 90% (owner is under-responsive)
WEIGHT_NEW_HOST = 1           # host tenure < 24 months (overwhelmed by self-management)

PRICE_BELOW_NBHD_PCT = 10.0
SLOW_RESPONSE_BELOW = 0.90
NEW_HOST_MONTHS = 24.0
THREE_PLUS_LISTINGS = 3

# Hosts at/above this calculated metro-wide listing count are almost certainly
# professional operators, not owners who underestimate the work. Also excluded
# when the host name matches a company-like keyword (see below). Both checks are
# transparent and reported via `agency_reason`; the CLI has --include-agencies.
AGENCY_LISTINGS_CUTOFF = 15

# Company-like name tokens. Deliberately conservative: only tokens that almost
# never appear in an individual host's display name.
AGENCY_NAME_PATTERN = re.compile(
    r"\b(hotels?|motels?|resorts?|hospitality|managements?|mgmt|realty|propert(y|ies)|"
    r"groups?|cribs|stays?|hostings?|llc|inc|ltd|co|company)\b",
    re.IGNORECASE,
)

MAX_SCORE = (WEIGHT_MULTI_LISTING + WEIGHT_TRIPLE_PLUS + WEIGHT_PRICE_BELOW_NBHD
             + WEIGHT_STALE_REVIEWS + WEIGHT_THIN_DESCRIPTION + WEIGHT_LOW_REVENUE
             + WEIGHT_NOT_SUPERHOST + WEIGHT_SLOW_RESPONSE + WEIGHT_NEW_HOST)


def agency_reason(row: pd.Series) -> Optional[str]:
    """Return why this host looks like a property-management agency, or None."""
    calc = row.get("calculated_host_listings_count")
    n_local = row.get("n_listings")
    effective = calc if pd.notna(calc) else n_local
    if pd.notna(effective) and float(effective) >= AGENCY_LISTINGS_CUTOFF:
        return f"calculated metro-wide listings ≥ {AGENCY_LISTINGS_CUTOFF} ({int(effective)})"
    name = row.get("host_name")
    if isinstance(name, str):
        m = AGENCY_NAME_PATTERN.search(name)
        if m:
            return f"name matches company-like token '{m.group(0).lower()}'"
    return None


def score_host(row: pd.Series) -> tuple[int, list[str]]:
    """Score one host row from build_host_table(). Returns (score, reasons)."""
    score = 0
    reasons: list[str] = []

    n = row.get("n_listings")
    n = int(n) if pd.notna(n) else 0
    if n >= 2:
        score += WEIGHT_MULTI_LISTING
        reasons.append(f"+{WEIGHT_MULTI_LISTING} — {n} listings in Austin (multi-property owner)")
        if n >= THREE_PLUS_LISTINGS:
            score += WEIGHT_TRIPLE_PLUS
            reasons.append(f"+{WEIGHT_TRIPLE_PLUS} — portfolio of {n} (deeper pain, more upside)")

    frac_below = row.get("frac_below_nbhd")
    if pd.notna(frac_below) and float(frac_below) > 0:
        score += WEIGHT_PRICE_BELOW_NBHD
        reasons.append(f"+{WEIGHT_PRICE_BELOW_NBHD} — listing priced ≥{(PRICE_BELOW_NBHD_PCT):.0f}% below "
                       f"neighbourhood median (money left on the table)")

    if bool(row.get("any_stale")):
        score += WEIGHT_STALE_REVIEWS
        reasons.append(f"+{WEIGHT_STALE_REVIEWS} — at least one listing with stale/missing reviews "
                       f"(momentum is dead)")

    if bool(row.get("any_thin_desc")):
        score += WEIGHT_THIN_DESCRIPTION
        reasons.append(f"+{WEIGHT_THIN_DESCRIPTION} — thin listing copy (under 60 words)")

    n_low = row.get("n_low_revenue")
    if pd.notna(n_low) and int(n_low) > 0:
        score += WEIGHT_LOW_REVENUE
        reasons.append(f"+{WEIGHT_LOW_REVENUE} — {int(n_low)} listing(s) in the metro's bottom "
                       f"modelled-revenue tercile")

    superhost = row.get("host_is_superhost")
    if superhost is False or (pd.notna(superhost) and not bool(superhost)):
        score += WEIGHT_NOT_SUPERHOST
        reasons.append(f"+{WEIGHT_NOT_SUPERHOST} — not a superhost (less likely to have a PM)")

    rr = row.get("host_response_rate")
    if pd.notna(rr) and float(rr) < SLOW_RESPONSE_BELOW:
        score += WEIGHT_SLOW_RESPONSE
        reasons.append(f"+{WEIGHT_SLOW_RESPONSE} — reply rate {float(rr):.0%} (<90%: guests go "
                       f"unanswered, bookings die)")

    tenure = row.get("host_tenure_months")
    if pd.notna(tenure) and float(tenure) < NEW_HOST_MONTHS:
        score += WEIGHT_NEW_HOST
        reasons.append(f"+{WEIGHT_NEW_HOST} — hosting for {float(tenure):.0f} months (<24: "
                       f"likely doing everything themself)")

    return score, reasons


def score_hosts(df: pd.DataFrame, exclude_agencies: bool = True) -> pd.DataFrame:
    """Score every host; add score, reasons, excluded_agency. Sorted best-first.

    Ranking: score desc, then n_listings desc, then min modelled revenue asc (the
    host bleeding the most gets the first call).
    """
    out = df.copy()
    results = [score_host(out.iloc[i]) for i in range(len(out))]
    out["score"] = [s for s, _ in results]
    out["reasons"] = [r for _, r in results]
    out["agency_reason"] = [agency_reason(out.iloc[i]) for i in range(len(out))]
    out["excluded_agency"] = out["agency_reason"].notna() if exclude_agencies else False
    return out.sort_values(
        by=["score", "n_listings", "min_modelled_revenue"],
        ascending=[False, False, True],
        na_position="last",
        ignore_index=True,
    )
