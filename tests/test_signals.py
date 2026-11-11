"""Unit tests for audit signals and the revenue estimate (synthetic, no network).

Run: python -m pytest tests/ -v
"""

import math
from datetime import date

import pandas as pd
import pytest

from str_audit.revenue import estimate_gap
from str_audit.signals import (run_signals, signal_description,
                               signal_price_vs_comps, signal_review_recency)


def _target(**over):
    base = dict(
        description=("Bright and cheerful 2BR near South Congress, walkable to restaurants, "
                     "cafes and South 1st shops. Full kitchen with dishwasher, fast wifi for "
                     "remote work, self check-in with a smart lock, free parking just behind the "
                     "building, coffee maker, fresh linens, towels and extra toiletries provided. "
                     "Sleeps four comfortably: one king bed in the main bedroom, one queen sleeper "
                     "sofa in the living room. Quiet residential street, 10 minutes to downtown "
                     "and The Domain by car, 4 minutes on foot to the bus. Heated pool and grill "
                     "downstairs shared with six units."),
        number_of_reviews=42, last_review=pd.Timestamp("2026-09-01"),
        reviews_per_month=1.5, price=200.0,
    )
    base.update(over)
    return pd.Series(base)


def test_description_word_count_threshold():
    assert signal_description(_target())["status"] == "pass"
    assert signal_description(_target(description="nice place"))["status"] == "warn"
    assert signal_description(_target(description=float("nan")))["status"] == "fail"
    assert signal_description(_target(description=None))["status"] == "fail"


def test_review_recency_stale_and_missing():
    fresh = signal_review_recency(_target(), today=date(2026, 11, 1))
    assert fresh["status"] == "pass"
    stale = signal_review_recency(_target(last_review=pd.Timestamp("2025-01-01")),
                                  today=date(2026, 11, 1))
    assert stale["status"] in ("warn", "fail")
    none = signal_review_recency(_target(number_of_reviews=0, last_review=pd.NaT),
                                 today=date(2026, 11, 1))
    assert none["status"] == "fail"


def test_price_vs_comps_bands():
    assert signal_price_vs_comps(110.0, 100.0)["status"] == "pass"   # within ±10%
    assert signal_price_vs_comps(125.0, 100.0)["status"] == "warn"   # 25% over
    assert signal_price_vs_comps(80.0, 100.0)["status"] == "warn"    # 20% under
    assert signal_price_vs_comps(100.0, None)["status"] == "unknown"


def test_estimate_gap_math():
    target = _target(price=180.0, estimated_revenue_l365d=30000.0)
    comps = pd.DataFrame([
        dict(price=200.0, availability_365=180, estimated_occupancy_l365d=219,   # 0.60 * 365 exactly
             estimated_revenue_l365d=44000),
        dict(price=210.0, availability_365=150, estimated_occupancy_l365d=219,
             estimated_revenue_l365d=53000),
        dict(price=190.0, availability_365=200, estimated_occupancy_l365d=219,
             estimated_revenue_l365d=35000),
    ])
    est = estimate_gap(target, comps)
    n = est["numbers"]
    comp_med = 200.0
    occ = 219 / 365
    expected = (comp_med - 180.0) * occ * 365
    assert n["comp_median_price"] == 200.0
    assert n["est_annual_price_gap"] == round(expected)
    assert n["est_annual_ia_revenue_gap"] == round(44000 - 30000)
    assert any("ESTIMATE A" in line for line in est["method"])
    assert any("ESTIMATE B" in line for line in est["method"])


def test_estimate_gap_handles_missing_airbnb_model():
    target = _target(price=180.0, estimated_revenue_l365d=None)
    comps = pd.DataFrame([
        dict(price=200.0, availability_365=180, estimated_occupancy_l365d=219,
             estimated_revenue_l365d=None),
        dict(price=210.0, availability_365=150, estimated_occupancy_l365d=255,
             estimated_revenue_l365d=None),
        dict(price=190.0, availability_365=200, estimated_occupancy_l365d=182,
             estimated_revenue_l365d=None),
    ])
    est = estimate_gap(target, comps)
    assert est["numbers"]["est_annual_ia_revenue_gap"] is None
    assert est["numbers"]["est_annual_price_gap"] is not None  # ESTIMATE A still works
