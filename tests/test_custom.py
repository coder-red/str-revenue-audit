"""Custom (user-entered) listing path — synthetic comps, no dataset, no network.

Run: python -m pytest tests/ -v
"""

import pandas as pd
import pytest

from str_audit.audit import make_custom_target, run_audit_custom


def _toy_df() -> pd.DataFrame:
    rows = []
    for i in range(14):
        rows.append(dict(
            id=1000 + i, name=f"comp {i}", host_id=5000 + i,
            neighbourhood_cleansed="78704", neighbourhood_group_cleansed=None,
            latitude=30.27 + i * 0.001, longitude=-97.74 + i * 0.001,
            property_type="Entire rental unit", room_type="Entire home/apt",
            bedrooms=2.0, beds=2.0, baths=1.0,
            price=150 + i * 2, minimum_nights=2, has_availability=True,
            availability_365=100, number_of_reviews=10 + i,
            number_of_reviews_ltm=5, last_review=pd.Timestamp("2026-08-01"),
            reviews_per_month=1.0, review_scores_rating=4.8,
            estimated_occupancy_l365d=200, estimated_revenue_l365d=30000 + i * 1000,
            instant_bookable=True, picture_url=None, description="desc",
        ))
    return pd.DataFrame(rows)


def test_make_custom_target_types():
    t = make_custom_target(dict(
        name="My place", price="150", room_type="Entire home/apt",
        neighbourhood="78704", bedrooms="1", beds="1", baths="1",
        availability_365="200", number_of_reviews="7",
        reviews_per_month="0.3", last_review="2026-09-01",
        description="Cozy spot near the patio restaurants",
    ))
    assert t["price"] == 150.0
    assert t["availability_365"] == 200
    assert t["number_of_reviews"] == 7
    assert isinstance(t["last_review"], pd.Timestamp)


def test_run_audit_custom_end_to_end(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    audit = run_audit_custom(
        _toy_df(),
        dict(name="My place", price=150, room_type="Entire home/apt",
             neighbourhood="78704", bedrooms=2.0, beds=2.0, baths=1.0,
             availability_365=300, number_of_reviews=3, reviews_per_month=0.2,
             last_review="2026-06-01", description="Short"),
        k=8, k_min=5, photo_count=4, provider="gemini",
    )
    assert audit["listing_id"] is None
    assert audit["comps"]["n"] == 8
    assert audit["llm_provider_used"].startswith("fallback")
    photos = next(s for s in audit["signals"] if s["key"] == "photos")
    assert photos["status"] == "warn"               # 4 photos < 8
    recency = next(s for s in audit["signals"] if s["key"] == "review_recency")
    assert recency["status"] in ("warn", "fail")    # stale reviews
    assert audit["estimate"]["numbers"]["est_annual_price_gap"] is not None
