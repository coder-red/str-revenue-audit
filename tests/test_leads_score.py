"""Synthetic-data tests for the custom lead score — no network, no files."""

from __future__ import annotations

import pandas as pd

from str_leads.score import (
    MAX_SCORE,
    WEIGHT_LOW_REVENUE,
    WEIGHT_PRICE_BELOW_NBHD,
    WEIGHT_STALE_REVIEWS,
    WEIGHT_SWEET_SPOT,
    WEIGHT_THIN_DESCRIPTION,
    WEIGHT_TWO_PLUS,
    agency_reason,
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
    assert any("eligible on weak-listing evidence" in r for r in reasons)


def test_two_plus_and_sweet_spot_weights():
    score2, _ = score_host(_row(n_listings=2))
    assert score2 == WEIGHT_TWO_PLUS
    score4, reasons4 = score_host(_row(n_listings=4))
    assert score4 == WEIGHT_TWO_PLUS + WEIGHT_SWEET_SPOT
    assert any("sweet spot" in r for r in reasons4)
    # >=5 listings: portfolio points capped at WEIGHT_TWO_PLUS, no sweet-spot bonus
    score6, _ = score_host(_row(n_listings=6))
    assert score6 == WEIGHT_TWO_PLUS


def test_full_stack_reasons_and_cap():
    score, reasons = score_host(_row(
        n_listings=4, frac_below_nbhd=0.5, any_stale=True, any_thin_desc=True,
        n_low_revenue=2, host_is_superhost=False, host_response_rate=0.4,
        host_tenure_months=6.0,
    ))
    assert score == MAX_SCORE
    assert len(reasons) == 9


def test_weak_listing_signals_outweigh_portfolio():
    """A weak single-listing host must outscore a clean 4-listing one."""
    weak_single = score_host(_row(n_listings=1, frac_below_nbhd=0.2, any_stale=True,
                                  any_thin_desc=True, n_low_revenue=1))[0]
    clean_four = score_host(_row(n_listings=4))[0]
    assert weak_single > clean_four


def test_unknown_superhost_not_penalised():
    score, _ = score_host(_row(host_is_superhost=None))
    assert score == 0


def test_price_and_stale_weights():
    score, _ = score_host(_row(frac_below_nbhd=0.25, any_stale=True))
    assert score == WEIGHT_PRICE_BELOW_NBHD + WEIGHT_STALE_REVIEWS


def test_thin_description_weight():
    score, _ = score_host(_row(any_thin_desc=True))
    assert score == WEIGHT_THIN_DESCRIPTION


def test_low_revenue_weight():
    score, _ = score_host(_row(n_low_revenue=2))
    assert score == WEIGHT_LOW_REVENUE


def test_agencies_excluded_by_default_and_restorable():
    df = pd.DataFrame([
        _row(n_listings=6, calculated_host_listings_count=6.0).to_dict() | {"host_id": 1},
        _row(n_listings=2, host_is_superhost=False,
             calculated_host_listings_count=2.0).to_dict() | {"host_id": 2},
    ])
    out = score_hosts(df, exclude_agencies=True)  # default cutoff 5
    assert bool(out.loc[out["host_id"] == 1, "excluded_agency"].iloc[0]) is True
    assert out.loc[out["host_id"] == 1, "agency_reason"].iloc[0]
    assert bool(out.loc[out["host_id"] == 2, "excluded_agency"].iloc[0]) is False

    out2 = score_hosts(df, exclude_agencies=False)
    assert not out2["excluded_agency"].any()


def test_agency_cutoff_is_configurable():
    row = _row(n_listings=8, calculated_host_listings_count=8.0, host_name="PlainName")
    assert agency_reason(row, cutoff=5) is not None      # excluded at 5
    assert agency_reason(row, cutoff=15) is None         # kept at 15
    df = pd.DataFrame([row.to_dict() | {"host_id": 1}])
    out = score_hosts(df, agency_cutoff=15)
    assert bool(out.iloc[0]["excluded_agency"]) is False


def test_company_name_token_excluded_even_with_few_listings():
    reason = agency_reason(_row(host_name="Harbor Light Stays",
                                n_listings=3, calculated_host_listings_count=3.0))
    assert reason and "stay" in reason


def test_ranking_prefers_score_then_portfolio_then_revenue():
    # All clean except portfolio size differences: score desc, then more doors, then lowest bleed.
    df = pd.DataFrame([
        _row(n_listings=2, min_modelled_revenue=1.0).to_dict() | {"host_id": 1},   # score 2
        _row(n_listings=4, min_modelled_revenue=9e9).to_dict() | {"host_id": 2},   # score 3
        _row(n_listings=6, min_modelled_revenue=1.0).to_dict() | {"host_id": 3},   # score 2, portfolio no bonus
    ])
    out = score_hosts(df, agency_cutoff=99)
    assert list(out["host_id"]) == [2, 3, 1]  # 3-pt sweet-spot host first; then more doors; then bleed
