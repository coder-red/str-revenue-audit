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
"""

from __future__ import annotations

import numpy as np
import pandas as pd


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
