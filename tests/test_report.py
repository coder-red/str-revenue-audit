"""PDF/HTML rendering tests — synthetic audit dict, no network, no dataset.

Run: python -m pytest tests/ -v
"""

import pytest

from str_audit.report import build_view, render_html, render_pdf


def _audit():
    return {
        "listing_id": 9999,
        "generated_at": "2026-11-11T10:30:00",
        "data_source": "test",
        "target": {
            "id": 9999, "name": "Sweet SoCo 2BR <script>", "room_type": "Entire home/apt",
            "bedrooms": 2.0, "beds": 2.0, "baths": 1.0, "price": 180.0,
            "neighbourhood_cleansed": "78704", "number_of_reviews": 42,
            "last_review": "2026-09-01", "availability_365": 150,
        },
        "comps": {
            "n": 8, "pool": "neighbourhood", "median_price": 200.0,
            "table": [
                {"rank": i + 1, "id": i + 1, "neighbourhood_cleansed": "78704",
                 "room_type": "Entire home/apt", "bedrooms": 2.0, "beds": 2.0, "baths": 1.0,
                 "price": 195.0 + i, "availability_365": 200, "number_of_reviews": 30,
                 "estimated_revenue_l365d": 44000, "last_review": "2026-09-01"}
                for i in range(8)
            ],
        },
        "signals": [
            {"key": "photos", "status": "warn", "value": 4,
             "summary": "Only 4 photos", "detail": ""},
            {"key": "description", "status": "pass", "value": 80,
             "summary": "Description OK", "detail": ""},
        ],
        "top_fixes": ["Shoot or swap in at least 8 professional-looking photos."],
        "estimate": {
            "numbers": {
                "comp_median_price": 200.0, "comp_avg_occupancy": 0.6,
                "target_price": 180.0, "price_gap_per_night": 20.0,
                "est_annual_price_gap": 4380,
                "target_estimated_revenue_l365d": 30000,
                "comp_median_estimated_revenue_l365d": 48500,
                "est_annual_ia_revenue_gap": 18500,
            },
            "method": ["ESTIMATE A ... = $4,380/yr", "ESTIMATE B ... = $18,500/yr"],
            "caveats": ["Both are estimates."],
        },
        "llm_summary": "Line one.\nLine two.",
        "llm_provider_used": "fallback (test)",
    }


def test_sample_banner_renders_when_requested():
    html = render_html(_audit(), chart_b64=None, sample=True)
    assert "SAMPLE — BASED ON PUBLIC INSIDE AIRBNB DATA — ESTIMATES ONLY" in html
    html2 = render_html(_audit(), chart_b64=None)   # default: no banner
    assert "SAMPLE — BASED ON PUBLIC INSIDE AIRBNB DATA" not in html2


def test_render_html_contains_estimates_and_escapes():
    html = render_html(_audit(), chart_b64=None)
    assert "ESTIMATE" in html
    assert "+$4,380 → +$18,500" in html          # headline is now the conservative range
    assert "&lt;script&gt;" in html          # name is escaped
    assert "<script>" not in html
    assert "Line one.<br>Line two." in html  # summary newlines → <br>


def test_insufficient_data_when_too_few_comps():
    audit = _audit()
    audit["comps"] = {**audit["comps"], "n": 3, "table": audit["comps"]["table"][:3]}
    audit["estimate"]["numbers"] = {**audit["estimate"]["numbers"],
                                    "insufficient_data": True,
                                    "insufficient_reason": "only 3 comparable listings (need ≥ 8)"}
    html = render_html(audit, chart_b64=None)
    assert "INSUFFICIENT DATA" in html
    assert "+$4,380 → +$18,500" not in html


def test_render_pdf_bytes():
    pdf = render_pdf(_audit(), chart_b64=None)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 3000


def test_build_view_sign_handling():
    view = build_view(_audit(), chart_b64=None)
    assert view["est_a"] == "+$4,380"
    assert view["est_b"] == "+$18,500"
    assert view["est_b_negative"] is False
    assert view["insufficient_data"] is False
    assert view["gap_range"] == "+$4,380 → +$18,500"
