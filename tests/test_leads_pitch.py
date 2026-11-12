"""Pitch assembly tests — synthetic audit/lead dicts, no network."""

from __future__ import annotations

import pytest

from str_leads import pitch

_AUDIT = {
    "listing_id": 5094445,
    "target": {
        "id": 5094445, "name": "Sweet SoCo 2BR", "room_type": "Entire home/apt",
        "bedrooms": 2.0, "beds": 2.0, "price": 180.0,
        "neighbourhood_cleansed": "78704",
        "number_of_reviews": 30, "last_review": "2026-09-01",
    },
    "estimate": {
        "numbers": {
            "est_annual_price_gap": 15_000,
            "est_annual_ia_revenue_gap": 20_000,
            "target_estimated_revenue_l365d": 30_000,
            "comp_median_estimated_revenue_l365d": 50_000,
            "comp_median_price": 200.0,
        },
        "method": ["ESTIMATE A ..."],
    },
    "comps": {"n": 10, "pool": "neighbourhood", "median_price": 200.0},
    "signals": [{"key": "review_recency", "status": "warn", "summary": "stale"}],
    "top_fixes": ["Reprice toward the comp median.", "Rewrite the description."],
}

_LEAD = {"host_id": 7363313, "host_name": "Macy Ray", "n_listings": 12,
         "reasons": ["+3 — 12 listings"], "weakest_listing_id": 1013186812093487861}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ("SENDER_NAME", "SENDER_BUSINESS", "SENDER_POSTAL_ADDRESS", "OPT_OUT_TEXT"):
        monkeypatch.delenv(key, raising=False)
    yield


def test_fallback_body_uses_only_audit_figures():
    body = pitch.fallback_pitch(_LEAD, _AUDIT)
    assert "20,000" in body            # the one estimate we surface
    assert "estimate" in body.lower()
    assert "5094445" not in body       # ids are not talking points
    assert "15,000" not in body        # we do not leak the other figure
    assert "20-minute" in body


def test_can_spam_fails_without_sender_identity():
    subject = pitch.build_subject(_LEAD)
    ok, problems = pitch.can_spam_ok(subject, pitch.fallback_pitch(_LEAD, _AUDIT))
    assert not ok
    joined = " ".join(problems)
    assert "SENDER_NAME" in joined and "SENDER_BUSINESS" in joined and "POSTAL" in joined


def test_generate_pitch_with_sender_identity_passes(monkeypatch):
    monkeypatch.setenv("SENDER_NAME", "Casey Manager")
    monkeypatch.setenv("SENDER_BUSINESS", "ATX Stays Co")
    monkeypatch.setenv("SENDER_POSTAL_ADDRESS", "123 Congress Ave, Austin, TX 78701")
    result = pitch.generate_pitch(_LEAD, _AUDIT, provider="none")
    assert result["subject"]
    assert "fallback" in result["provider_used"] or result["provider_used"] == "none"
    assert "Casey Manager" in result["body"]
    assert "123 Congress Ave" in result["body"]
    assert "stop" in result["body"].lower()          # default opt-out text present
    assert result["can_spam_ok"], result["can_spam_problems"]


def test_missing_opt_out_detected(monkeypatch):
    monkeypatch.setenv("SENDER_NAME", "Casey Manager")
    monkeypatch.setenv("SENDER_BUSINESS", "ATX Stays Co")
    monkeypatch.setenv("SENDER_POSTAL_ADDRESS", "123 Congress Ave, Austin, TX 78701")
    body = "Hi Macy — quick note.\n\n— Casey Manager, ATX Stays Co\n123 Congress Ave, Austin, TX 78701"
    ok, problems = pitch.can_spam_ok("s", body)
    assert not ok
    assert any("opt-out" in p for p in problems)


def test_placeholder_body_detected(monkeypatch):
    monkeypatch.setenv("SENDER_NAME", "Casey Manager")
    monkeypatch.setenv("SENDER_BUSINESS", "ATX Stays Co")
    monkeypatch.setenv("SENDER_POSTAL_ADDRESS", "123 Congress Ave, Austin, TX 78701")
    body = pitch.fallback_pitch(_LEAD, _AUDIT) + "\n\n— [SENDER_NAME — set in .env before sending]\n" + "123 Congress Ave, Austin, TX 78701\nReply \"stop\" and I will not email you again."
    ok, problems = pitch.can_spam_ok("s", body)
    assert not ok
    assert any("placeholder" in p for p in problems)


def test_first_name_and_subject_deterministic():
    assert pitch.first_name("Macy Ray") == "Macy"
    assert pitch.first_name(None) == "there"
    assert pitch.first_name("  ") == "there"
    subj = pitch.build_subject(_LEAD)
    assert "12" in subj and "Macy" in subj
