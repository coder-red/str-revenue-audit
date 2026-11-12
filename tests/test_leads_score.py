"""Synthetic-data tests for the custom lead score — no network, no files."""

from __future__ import annotations

import pandas as pd

from str_leads.score import (
    MAX_SCORE,
    WEIGHT_MULTI_LISTING,
    WEIGHT_NOT_SUPERHOST,
    WEIGHT_PRICE_BELOW_NBHD,
    WEIGHT_STALE_REVIEWS,
    WEIGHT_THIN_DESCRIPTION,
    WEIGHT_TRIPLE_PLUS,
    score_host,
    score_hosts,
)


def _row(**kw):
    base = dict(
        n_listings=1,
        frac_below_nbhd=0.0,
        any_stale=False,
        any_thin_desc=False,
        n_low_revenue=0,
        host_is_superhost=True,
        host_response_rate=1.0,
        host_tenure_months=60.0,
        min_modelled_revenue=50_000.0,
        calculated_host_listings_count=1.0,
        host_name="SimpleOwner",
    )
    base.update(kw)
    return pd.Series(base)


def test_single_superhost_scores_zero():
    score, reasons = score_host(_row())
    assert score == 0
    assert reasons == []


def test_multi_listing_and_triple_bonus():
    score, reasons = score_host(_row(n_listings=3))
    assert score == WEIGHT_MULTI_LISTING + WEIGHT_TRIPLE_PLUS
    assert any("multi-property" in r for r in reasons)


def test_full_stack_reasons_and_cap():
    score, reasons = score_host(_row(
        n_listings=4, frac_below_nbhd=0.5, any_stale=True, any_thin_desc=True,
        n_low_revenue=2, host_is_superhost=False, host_response_rate=0.4,
        host_tenure_months=6.0,
    ))
    assert score == MAX_SCORE
    assert len(reasons) == 9


def test_unknown_superhost_not_penalised():
    score, _ = score_host(_row(host_is_superhost=None))
    assert score == 0


def test_price_and_stale_weights():
    score, _ = score_host(_row(frac_below_nbhd=0.25, any_stale=True))
    assert score == WEIGHT_PRICE_BELOW_NBHD + WEIGHT_STALE_REVIEWS


def test_thin_description_weight():
    score, _ = score_host(_row(any_thin_desc=True))
    assert score == WEIGHT_THIN_DESCRIPTION


def test_agencies_excluded_by_default_and_restorable():
    df = pd.DataFrame([
        _row(n_listings=30, calculated_host_listings_count=30.0).to_dict() | {"host_id": 1},
        _row(n_listings=2, host_is_superhost=False,
             calculated_host_listings_count=2.0).to_dict() | {"host_id": 2},
    ])
    out = score_hosts(df, exclude_agencies=True)
    assert bool(out.loc[out["host_id"] == 1, "excluded_agency"].iloc[0]) is True
    assert out.loc[out["host_id"] == 1, "agency_reason"].iloc[0]
    assert bool(out.loc[out["host_id"] == 2, "excluded_agency"].iloc[0]) is False

    out2 = score_hosts(df, exclude_agencies=False)
    assert not out2["excluded_agency"].any()


def test_company_name_token_excluded_even_with_few_listings():
    from str_leads.score import agency_reason
    reason = agency_reason(_row(host_name="Wyndham Hotels And Resorts",
                                n_listings=3, calculated_host_listings_count=3.0))
    assert reason and "hotel" in reason


def test_ranking_order_prefers_listings_then_revenue():
    df = pd.DataFrame([
        _row(n_listings=3, host_is_superhost=False, min_modelled_revenue=9e9).to_dict() | {"host_id": 1},
        _row(n_listings=3, host_is_superhost=False, min_modelled_revenue=1.0).to_dict() | {"host_id": 2},
    ])
    out = score_hosts(df)
    assert out.iloc[0]["host_id"] == 2  # same score+listings -> lowest bleeding revenue first
