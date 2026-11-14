"""Contact finder smoke tests — mocked HTTP, no network, no real API calls."""

from __future__ import annotations

import re
from unittest.mock import patch, MagicMock

from str_leads import contact_finder

FAKE_PAGE = """<html><body>
<h1>Jane's Austin Vacation Rental</h1>
<p>Reach me at jane.host@janeaustinvrentals.com for bookings and questions.</p>
<a href="mailto:jane.host@janeaustinvrentals.com">email jane</a>
<p>Also contact: hello@janeaustinvrentals.com</p>
</body></html>"""

FAKE_RESULTS = {
    "web": {
        "results": [
            {"url": "https://www.janeaustinvrentals.com/contact",
             "title": "Jane's Austin Rentals",
             "description": "Austin vacation rental and property management"},
        ],
    },
}


def test_emails_in_html_keeps_valid_drops_known_junk():
    emails = contact_finder._emails_in_html(FAKE_PAGE)
    assert "jane.host@janeaustinvrentals.com" in emails
    # 'hello@' local part is reserved — dropped
    assert "hello@janeaustinvrentals.com" not in emails


def test_name_match_protects_partial_collisions():
    assert contact_finder._name_match("Jane", "jane.host@janeaustinvrentals.com")
    assert not contact_finder._name_match("Ana", "Vanessa hosts vacation rentals")


def test_first_name_handles_messy_input():
    assert contact_finder._first_name("Jane Smith") == "Jane"
    assert contact_finder._first_name(None) == ""
    assert contact_finder._first_name("") == ""


def test_find_for_lead_returns_nothing_when_no_key():
    assert contact_finder.search_brave("x", "") == []


def test_find_for_lead_parses_mock_brave_and_requires_name_match():
    def fake_get(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        if "api.search.brave.com" in url:
            m.json = lambda: FAKE_RESULTS
            m.text = ""
        elif "janeaustinvrentals.com" in url:
            m.text = FAKE_PAGE
            m.json = lambda: {}
        else:
            m.raise_for_status.side_effect = Exception("boom")
        return m

    with patch("str_leads.contact_finder.requests.get", side_effect=fake_get):
        cands = contact_finder.find_for_lead("Jane", "Austin, TX", "test-key")

    emails = [c.email for c in cands]
    assert "jane.host@janeaustinvrentals.com" in emails, f"got {emails}"
    assert all(c.name_match for c in cands)
    assert all(c.source == "brave_search" for c in cands)
    assert all(c.evidence_score >= 2 for c in cands)


def test_no_name_match_filters_everyone_out():
    def fake_get(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        if "api.search.brave.com" in url:
            m.json = lambda: FAKE_RESULTS
            m.text = ""
        else:
            m.text = "<html><body>mail anna@example.com and jane@example.com</body></html>"
            m.json = lambda: {}
        return m

    with patch("str_leads.contact_finder.requests.get", side_effect=fake_get):
        cands = contact_finder.find_for_lead("Zzz_NoName", "Austin, TX", "test-key")

    assert cands == []
