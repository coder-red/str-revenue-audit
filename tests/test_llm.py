"""LLM wrapper tests — no network calls.

Run: python -m pytest tests/ -v
"""

from str_audit.llm import _fallback_summary, summarize_audit

_AUDIT = {
    "target": {
        "name": "Sweet SoCo 2BR", "room_type": "Entire home/apt", "beds": 2,
        "neighbourhood_cleansed": "78704", "price": 180.0,
        "availability_365": 182, "number_of_reviews": 30,
        "last_review": "2026-09-01",
    },
    "comps": {"n": 10, "pool": "neighbourhood", "median_price": 200.0},
    "estimate": {
        "numbers": {
            "est_annual_price_gap": 15_000,
            "est_annual_ia_revenue_gap": 20_000,
            "target_estimated_revenue_l365d": 30_000,
            "comp_median_estimated_revenue_l365d": 50_000,
        },
        "method": ["ESTIMATE A ...", "ESTIMATE B ..."],
        "caveats": ["All figures are estimates."],
    },
    "signals": [
        {"key": "price_vs_comps", "status": "warn", "summary": "-10.0% below comp median"},
        {"key": "review_recency", "status": "pass", "summary": "fresh"},
    ],
    "top_fixes": ["Reprice toward the comp median."],
}


def test_fallback_summary_is_plain_and_mentions_estimate():
    text = _fallback_summary(_AUDIT)
    assert "estimate" in text.lower()
    assert "Reprice" in text
    assert "15,000" in text or "15000" in text.replace(",", "")


def test_unknown_provider_falls_back():
    summary, used = summarize_audit(_AUDIT, provider="not-a-provider")
    assert "fallback" in used
    assert "Reprice" in summary


def test_missing_keys_fall_back_without_raising(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    for provider in ("gemini", "groq"):
        summary, used = summarize_audit(_AUDIT, provider=provider)
        assert "fallback" in used
        assert isinstance(summary, str) and summary
