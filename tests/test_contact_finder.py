"""Contact finder smoke tests — mocked HTTP, no network, no real API calls."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from str_leads import contact_finder

TAVILY_HIT = {
    "results": [
        {"url": "https://www.janeaustinvrentals.com/contact",
         "title": "Jane's Austin Vacation Rentals — contact",
         "content": "Reach Jane at jane.host@janeaustinvrentals.com for bookings. Austin vacation rental since 2019."},
    ],
}


def test_emails_in_html_keeps_valid_drops_known_junk():
    text = """<html><body>
    <h1>Jane's Austin Vacation Rental</h1>
    <p>Reach me at jane.host@janeaustinvrentals.com</p>
    <a href="mailto:jane.host@janeaustinvrentals.com">email</a>
    <p>Or info@janeaustinvrentals.com</p>
    </body></html>"""
    emails = contact_finder._emails_in_text(text)
    assert "jane.host@janeaustinvrentals.com" in emails
    assert "info@janeaustinvrentals.com" not in emails   # reserved local-part


def test_name_match_protects_partial_collisions():
    assert contact_finder._name_match("Jane", "jane.host@janeaustinvrentals.com")
    assert not contact_finder._name_match("Ana", "Vanessa hosts vacation rentals")


def test_first_name_handles_messy_input():
    assert contact_finder._first_name("Jane Smith") == "Jane"
    assert contact_finder._first_name(None) == ""
    assert contact_finder._first_name("") == ""


def test_no_key_returns_empty():
    assert contact_finder.search_tavily("x", "") == []
    assert contact_finder.search_brave("x", "") == []
    assert contact_finder.find_for_lead("Jane", "Austin, TX", "", provider="tavily") == []


def test_tavily_end_to_end_mocked():
    def fake_post(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json = lambda: TAVILY_HIT
        m.text = ""
        return m

    with patch("str_leads.contact_finder.requests.post", side_effect=fake_post):
        cands = contact_finder.find_for_lead("Jane", "Austin, TX", "test-key", provider="tavily")

    assert cands, f"got {cands}"
    c = cands[0]
    assert c.email == "jane.host@janeaustinvrentals.com"
    assert c.source == "tavily_search"
    assert c.name_match is True
    assert c.evidence_score >= 2


def test_brave_end_to_end_mocked():
    brave_payload = {
        "web": {"results": [
            {"url": "https://www.janeaustinvrentals.com/contact",
             "title": "Jane's Austin Vacation Rentals — contact",
             "description": "Jane runs Austin vacation rentals; reach her at jane.host@janeaustinvrentals.com"},
        ]},
    }

    def fake_get(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json = lambda: brave_payload
        m.text = ""
        return m

    with patch("str_leads.contact_finder.requests.get", side_effect=fake_get):
        cands = contact_finder.find_for_lead("Jane", "Austin, TX", "test-key", provider="brave")

    assert cands, f"got {cands}"
    assert cands[0].email == "jane.host@janeaustinvrentals.com"
    assert cands[0].source == "brave_search"


def test_no_name_match_filters_everyone_out(monkeypatch=None):
    def fake_post(url, **kwargs):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json = lambda: {
            "results": [
                {"url": "https://unrelated1.com/about",
                 "title": "some Texas rental",
                 "content": "contact anna@example.com for booking"},
            ],
        }
        m.text = ""
        return m

    with patch("str_leads.contact_finder.requests.post", side_effect=fake_post):
        cands = contact_finder.find_for_lead("Zzz_NoName", "Austin, TX", "test-key", provider="tavily")

    assert cands == []
