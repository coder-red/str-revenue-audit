"""Revenue-gap estimate — every figure labelled ESTIMATE with its formula.

Our own logic (rule 5). We compute two complementary, honest numbers:

  A. Price-positioning gap (transparent, from public fields):
       est_annual_price_gap = (comp_median_price - target_price)
                              * comp_avg_occupancy * 365
     where comp_avg_occupancy = mean(comp estimated_occupancy_l365d) / 365
     (fallback: mean((365 - availability_365) / 365), clipped to [0, 1]).
     Positive => target is underpriced (money left on the table).

  B. Inside Airbnb model gap (black-box, disclosed):
       est_annual_ia_gap = median(comp estimated_revenue_l365d)
                           - target estimated_revenue_l365d
     Both sides are Inside Airbnb's own model output, not booked revenue.

We do NOT invent per-signal dollar impacts — no public dataset supports that.
Signals drive the fixes; the two numbers above are the only revenue figures.

Since 2026-11-12 the headline is a CONSERVATIVE RANGE (min→max of the two gaps),
not a single figure — single numbers from noisy public data over-promise. If the
comp set is too thin or too dissimilar, we say INSUFFICIENT DATA instead of
quoting a figure at all:
  * n comps < MIN_COMPS (8)      -> insufficient
  * comp price coefficient of variation (stdev / median) > MAX_COMP_PRICE_CV -> insufficient
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_COMPS = 8                # below this the comp set is anecdote, not evidence
MAX_COMP_PRICE_CV = 0.6      # stdev(price) / median(price) above this = comps too dissimilar


def price_cv(prices) -> float | None:
    """stdev(price) / median(price). None when there's nothing to compute on."""
    import statistics
    vals = [float(p) for p in prices if p is not None]
    if len(vals) < 2:
        return None
    med = statistics.median(vals)
    return statistics.stdev(vals) / med if med else None


def _comp_occupancy(comps: pd.DataFrame) -> tuple[float | None, str]:
    occ = comps["estimated_occupancy_l365d"].dropna()
    if len(occ) >= 3 and occ.sum() > 0:
        return float(min(max(occ.mean() / 365.0, 0.0), 1.0)), "Inside Airbnb estimated_occupancy_l365d (mean of comps) / 365"
    avail = comps["availability_365"].dropna()
    if len(avail) >= 3:
        proxy = ((365 - avail) / 365.0).clip(0, 1).mean()
        return float(proxy), "availability proxy: mean((365 - availability_365) / 365) — blocked nights may overstate occupancy"
    return None, "no occupancy signal available"


def estimate_gap(target: pd.Series, comps: pd.DataFrame) -> dict:
    comp_median_price = float(comps["price"].median()) if len(comps) else None
    occ, occ_source = _comp_occupancy(comps)
    target_price = float(target["price"])

    price_gap = None
    if comp_median_price and occ is not None:
        price_gap = (comp_median_price - target_price) * occ * 365.0

    comp_revs = comps["estimated_revenue_l365d"].dropna()
    active_revs = comp_revs[comp_revs > 0]  # exclude dormant/blocked listings (rev = 0)
    comp_median_rev = float(active_revs.median()) if len(active_revs) >= 3 else None
    comp_rev_n = int(len(active_revs))
    target_rev = target.get("estimated_revenue_l365d")
    target_ia_rev = float(target_rev) if pd.notna(target_rev) else None
    ia_gap = None
    if comp_median_rev is not None and target_ia_rev is not None:
        ia_gap = comp_median_rev - target_ia_rev

    # --- conservative-range / insufficient-data decision (2026-11-12) ------------
    prices = comps["price"].dropna()
    cv = price_cv(prices) or 0.0
    insufficient_reason = None
    if len(comps) < MIN_COMPS:
        insufficient_reason = f"only {len(comps)} comparable listings (need ≥ {MIN_COMPS})"
    elif cv > MAX_COMP_PRICE_CV:
        insufficient_reason = (f"comp prices too dissimilar (stdev/median = {cv:.2f} "
                               f"> {MAX_COMP_PRICE_CV})")
    gap_values = [g for g in (price_gap, ia_gap) if g is not None]
    gap_low = gap_high = None
    if insufficient_reason is None and gap_values:
        gap_low, gap_high = min(gap_values), max(gap_values)
    insufficient_data = insufficient_reason is not None

    numbers = {
        "comp_median_price": round(comp_median_price, 2) if comp_median_price else None,
        "comp_avg_occupancy": round(occ, 3) if occ is not None else None,
        "target_price": round(target_price, 2),
        "price_gap_per_night": round(comp_median_price - target_price, 2) if comp_median_price else None,
        # ESTIMATE A — see method
        "est_annual_price_gap": round(price_gap) if price_gap is not None else None,
        # ESTIMATE B — see method
        "target_estimated_revenue_l365d": round(target_ia_rev) if target_ia_rev is not None else None,
        "comp_median_estimated_revenue_l365d": round(comp_median_rev) if comp_median_rev is not None else None,
        "est_annual_ia_revenue_gap": round(ia_gap) if ia_gap is not None else None,
        # 2026-11-12: headline is the range (min→max of the two gaps), not a single figure.
        "est_gap_low": round(gap_low) if gap_low is not None else None,
        "est_gap_high": round(gap_high) if gap_high is not None else None,
        "insufficient_data": bool(insufficient_data),
        "insufficient_reason": insufficient_reason,
        "comp_price_cv": round(cv, 3),
    }

    method = [
        "comp set: same room type, beds ±1, same neighbourhood (fallback: 3 km radius, then metro-wide), "
        f"n = {len(comps)}, k-nearest by scaled [price, bedrooms, beds, baths].",
        f"comp_avg_occupancy from {occ_source}.",
        "ESTIMATE A (price positioning): (comp_median_price − target_price) × comp_avg_occupancy × 365 "
        f"= ({comp_median_price or 0:.2f} − {target_price:.2f}) × {(occ or 0):.3f} × 365"
        + (f" = ${price_gap:,.0f}/yr" if price_gap is not None else ""),
        f"ESTIMATE B (Inside Airbnb model): median(estimated_revenue_l365d) over active comps "
        f"(> $0 est. annual revenue; n = {comp_rev_n}) − target estimated_revenue_l365d"
        + (f" = {comp_median_rev:,.0f} − {target_ia_rev:,.0f} = ${ia_gap:,.0f}/yr"
           if ia_gap is not None else " (unavailable: fewer than 3 active comps with est. revenue)"),
        (f"INSUFFICIENT DATA — {insufficient_reason}. No figure is quoted." if insufficient_reason else
         (f"conservative range: ${gap_low:,.0f} – ${gap_high:,.0f} per year (A → B). ESTIMATE from public data."
          if gap_low is not None else
          "Neither gap could be computed — occupancy or revenue signal unavailable. No figure is quoted.")),
        "Both are ESTIMATES, not booked revenue. Actuals depend on seasonality, blocked nights, "
        "fees, and listing quality. Use as directional sizing, not as an invoice.",
    ]

    return {
        "numbers": numbers,
        "method": method,
        "caveats": [
            "Inside Airbnb revenue fields are model estimates, not recorded bookings.",
            "Occupancy from availability_365 blends booked and blocked nights.",
            "Comp median is robust to outliers; mean is not. We use medians throughout.",
            "Fixes from weak photos/description/reviews are directional — no per-signal "
            "dollar attribution exists in public data, so we deliberately don't invent one.",
        ],
    }
