"""Smoke tests for comps — synthetic data, no network, no real listings.

Run: python -m pytest tests/ -v
"""

import pandas as pd
import pytest

from str_audit.comps import build_comps


def _toy_df() -> pd.DataFrame:
    rows = []
    # 14 "Entire home/apt" rows around the target, same neighbourhood + beds
    for i in range(14):
        rows.append(dict(
            id=1000 + i, name=f"comp {i}", host_id=5000 + i,
            neighbourhood_cleansed="78701", neighbourhood_group_cleansed=None,
            latitude=30.27 + i * 0.001, longitude=-97.74 + i * 0.001,
            property_type="Entire rental unit", room_type="Entire home/apt",
            bedrooms=2.0, beds=2.0, baths=1.0,
            price=150 + i, minimum_nights=2, has_availability=True,
            availability_365=100, number_of_reviews=10 + i,
            number_of_reviews_ltm=5, last_review=pd.Timestamp("2026-08-01"),
            reviews_per_month=1.0, review_scores_rating=4.8,
            estimated_occupancy_l365d=200, estimated_revenue_l365d=30000,
            instant_bookable=True, picture_url=None, description="desc",
        ))
    # target listing
    rows.append(dict(
        id=9999, name="target", host_id=7777,
        neighbourhood_cleansed="78701", neighbourhood_group_cleansed=None,
        latitude=30.27, longitude=-97.74,
        property_type="Entire rental unit", room_type="Entire home/apt",
        bedrooms=2.0, beds=2.0, baths=1.0, price=140.0, minimum_nights=2,
        has_availability=True, availability_365=50, number_of_reviews=30,
        number_of_reviews_ltm=8, last_review=pd.Timestamp("2026-09-01"),
        reviews_per_month=2.0, review_scores_rating=4.9,
        estimated_occupancy_l365d=250, estimated_revenue_l365d=35000,
        instant_bookable=True, picture_url=None, description="desc",
    ))
    # noise: different room type, must not appear in comps
    rows.append(dict(
        id=8888, name="private room", host_id=6666,
        neighbourhood_cleansed="78701", neighbourhood_group_cleansed=None,
        latitude=30.27, longitude=-97.74,
        property_type="Private room in rental unit", room_type="Private room",
        bedrooms=1.0, beds=1.0, baths=1.0, price=80.0, minimum_nights=1,
        has_availability=True, availability_365=300, number_of_reviews=5,
        number_of_reviews_ltm=1, last_review=pd.Timestamp("2026-05-01"),
        reviews_per_month=0.5, review_scores_rating=4.0,
        estimated_occupancy_l365d=100, estimated_revenue_l365d=5000,
        instant_bookable=False, picture_url=None, description="desc",
    ))
    return pd.DataFrame(rows)


def test_comps_exclude_target_and_match_room_type():
    df = _toy_df()
    comps, how = build_comps(df, listing_id=9999, k=8, k_min=5)
    assert 9999 not in comps["id"].tolist()
    assert len(comps) == 8
    assert (comps["room_type"] == "Entire home/apt").all()
    assert comps["rank"].tolist() == list(range(1, 9))


def test_unknown_listing_raises():
    df = _toy_df()
    with pytest.raises(KeyError):
        build_comps(df, listing_id=123)


def test_distance_sorted_ascending():
    df = _toy_df()
    comps, _ = build_comps(df, listing_id=9999, k=6, k_min=5)
    assert comps["distance"].is_monotonic_increasing
