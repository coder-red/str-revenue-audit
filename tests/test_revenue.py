"""Revenue-gap estimate tests — synthetic comps, no dataset, no network."""

from __future__ import annotations

import pandas as pd

from str_audit.revenue import MAX_COMP_PRICE_CV, MIN_COMPS, estimate_gap


def _comps(prices, occ_l365d=73.0, revs=40_000):
    rows = []
    for i, p in enumerate(prices):
        rows.append({"price": float(p),
                     "estimated_occupancy_l365d": occ_l365d,
                     "availability_365": 100,
                     "estimated_revenue_l365d": float(revs[i]) if isinstance(revs, list) else float(revs)})
    return pd.DataFrame(rows)


def _target(price=180.0, rev=10_000):
    return pd.Series({"price": price, "estimated_revenue_l365d": rev})


def test_range_is_min_max_of_the_two_gaps():
    comps = _comps([200.0] * 12)
    out = estimate_gap(_target(), comps)
    nums = out["numbers"]
    a, b = nums["est_annual_price_gap"], nums["est_annual_ia_revenue_gap"]
    assert nums["insufficient_data"] is False
    assert nums["est_gap_low"] == min(a, b) and nums["est_gap_high"] == max(a, b)
    assert any("conservative range" in line for line in out["method"])


def test_range_sorted_when_a_above_b():
    comps = _comps([200.0] * 12, revs=[36_000] * 12)     # target rev 35,000 -> B = 1,000
    out = estimate_gap(_target(price=50.0, rev=35_000), comps)  # A huge
    nums = out["numbers"]
    assert nums["est_gap_low"] <= nums["est_gap_high"]
    assert nums["est_gap_low"] == nums["est_annual_ia_revenue_gap"]      # B is the floor here
    assert nums["est_gap_high"] == nums["est_annual_price_gap"]


def test_insufficient_when_too_few_comps():
    comps = _comps([200.0] * (MIN_COMPS - 1))
    nums = estimate_gap(_target(), comps)["numbers"]
    assert nums["insufficient_data"] is True
    assert nums["est_gap_low"] is None and nums["est_gap_high"] is None
    assert "need" in nums["insufficient_reason"]


def test_insufficient_when_comps_too_dissimilar():
    comps = _comps([100.0] * 9 + [1_600.0, 1_600.0, 1_600.0])  # stdev/median far above threshold
    nums = estimate_gap(_target(), comps)["numbers"]
    assert nums["insufficient_data"] is True
    assert nums["comp_price_cv"] > MAX_COMP_PRICE_CV
    assert "dissimilar" in nums["insufficient_reason"]


def test_no_occupancy_and_no_revenue_quotes_no_figure():
    prices = [200.0] * 12
    rows = [{"price": p, "estimated_occupancy_l365d": None, "availability_365": None,
              "estimated_revenue_l365d": None} for p in prices]
    comps = pd.DataFrame(rows)
    target = pd.Series({"price": 180.0, "estimated_revenue_l365d": None})
    out = estimate_gap(target, comps)
    nums = out["numbers"]
    assert nums["insufficient_data"] is False          # set is fine, just no signal
    assert nums["est_gap_low"] is None
    assert any("occupancy" in line.lower() or "unavailable" in line.lower() for line in out["method"])


def test_old_audit_dicts_still_render_a_range():
    # build_view computes the range from A and B when the dict predates the range fields
    from str_audit.report import build_view
    audit = {
        "target": {"id": 1, "name": "Old Audit", "room_type": "Entire home/apt",
                   "bedrooms": 2.0, "beds": 2.0, "baths": 1.0, "price": 180.0,
                   "neighbourhood_cleansed": "78704", "number_of_reviews": 5,
                   "last_review": "2026-01-01", "availability_365": 100},
        "comps": {"n": 12, "pool": "neighbourhood", "median_price": 200.0, "table": []},
        "signals": [],
        "top_fixes": [],
        "estimate": {"numbers": {"comp_median_price": 200.0, "comp_avg_occupancy": 0.5,
                                "target_price": 180.0, "est_annual_price_gap": 3_000,
                                "target_estimated_revenue_l365d": 10_000,
                                "comp_median_estimated_revenue_l365d": 25_000,
                                "est_annual_ia_revenue_gap": 15_000},
                     "method": ["old"], "caveats": []},
        "llm_summary": "old", "llm_provider_used": "test",
    }
    view = build_view(audit, chart_b64=None)
    assert view["insufficient_data"] is False
    assert view["gap_range"] == "+$3,000 → +$15,000"
