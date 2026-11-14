"""Synthetic-data tests for the SQLite lead store — tmp DBs, no network."""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from str_leads import store


def _scored_df():
    return pd.DataFrame([
        dict(host_id=101, host_name="Alice", n_listings=4, score=12,
             reasons=["+3 — 4 listings", "+2 — stale reviews"],
             total_modelled_revenue=120_000.0, min_modelled_revenue=5_000.0,
             median_price=180.0, calculated_host_listings_count=4.0,
             weakest_listing_id=9001, neighbourhoods=("78704", "78767"),
             host_url="https://www.airbnb.com/users/show/101",
             host_profile_url=None, host_about="Austin hosts"),
        dict(host_id=202, host_name="Bob", n_listings=2, score=9,
             reasons=["+3 — 2 listings"],
             total_modelled_revenue=40_000.0, min_modelled_revenue=9_000.0,
             median_price=150.0, calculated_host_listings_count=2.0,
             weakest_listing_id=9002, neighbourhoods=("78745",),
             host_url=None, host_profile_url="https://www.airbnb.com/hosts/202",
             host_about=None),
    ])


def test_upsert_insert_then_update_preserves_status(tmp_path):
    db = tmp_path / "leads.db"
    r1 = store.upsert_scored_leads(_scored_df(), db)
    assert r1 == {"inserted": 2, "updated": 0}

    store.update_lead(101, db, status="approved", notes="looks good")
    df2 = _scored_df()
    df2.loc[df2["host_id"] == 101, "score"] = 11
    r2 = store.upsert_scored_leads(df2, db)
    assert r2 == {"inserted": 0, "updated": 2}

    lead = store.get_lead(101, db)
    assert lead["status"] == "approved"          # not reset to 'new'
    assert lead["score"] == 11                   # scoring fields refreshed
    assert lead["notes"] == "looks good"
    assert lead["reasons"] == ["+3 — 4 listings", "+2 — stale reviews"]


def test_transition_timestamps_stamped_once(tmp_path):
    db = tmp_path / "leads.db"
    store.upsert_scored_leads(_scored_df(), db)
    a1 = store.update_lead(101, db, status="approved")
    approved_at = a1["approved_at"]
    assert approved_at
    a2 = store.update_lead(101, db, status="approved", notes="again")
    assert a2["approved_at"] == approved_at      # not re-stamped
    s1 = store.update_lead(101, db, status="sent")
    assert s1["sent_at"]


def test_invalid_status_rejected(tmp_path):
    db = tmp_path / "leads.db"
    store.upsert_scored_leads(_scored_df(), db)
    with pytest.raises(ValueError):
        store.update_lead(101, db, status="emailed")


def test_update_rejects_unknown_fields_and_missing_lead(tmp_path):
    db = tmp_path / "leads.db"
    store.upsert_scored_leads(_scored_df(), db)
    out = store.update_lead(101, db, admin_override="x", notes="ok")
    assert out["notes"] == "ok"
    assert "admin_override" not in out
    with pytest.raises(KeyError):
        store.update_lead(999, db, notes="nope")


def test_list_and_status_counts_and_export(tmp_path):
    db = tmp_path / "leads.db"
    store.upsert_scored_leads(_scored_df(), db)
    store.update_lead(101, db, status="approved")
    order = [d["host_id"] for d in store.list_leads(db)]
    assert order[0] == 101  # higher score first
    counts = store.status_counts(db)
    assert counts["approved"] == 1 and counts["new"] == 1

    csv_text = store.export_csv(db, statuses=["approved"])
    assert csv_text.startswith("\ufeff")
    assert "Alice" in csv_text and "Bob" not in csv_text
    assert "+3 — 4 listings | +2 — stale reviews" in csv_text

    csv_all = store.export_csv(db)
    assert "Alice" in csv_all and "Bob" in csv_all


# The pre-2026-11-12 schema, verbatim — migration must upgrade it in place.
_OLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    host_id INTEGER PRIMARY KEY,
    host_name TEXT,
    n_listings INTEGER,
    score INTEGER NOT NULL,
    score_version TEXT NOT NULL,
    reasons TEXT NOT NULL,
    total_modelled_revenue REAL,
    min_modelled_revenue REAL,
    median_price REAL,
    calculated_host_listings_count REAL,
    weakest_listing_id INTEGER,
    neighbourhoods TEXT,
    host_url TEXT,
    host_profile_url TEXT,
    host_about TEXT,
    contact_email TEXT,
    contact_url TEXT,
    contact_source TEXT,
    contact_found_on TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    audit_listing_id INTEGER,
    audit_listing_url TEXT,
    audit_json_path TEXT,
    audit_provider TEXT,
    pitch_subject TEXT,
    pitch_body TEXT,
    pitch_provider TEXT,
    can_spam_ok INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT,
    sent_at TEXT,
    replied_at TEXT,
    meeting_at TEXT
);
"""


def test_migration_adds_research_columns_to_old_db(tmp_path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(_OLD_SCHEMA)
    store.upsert_scored_leads(_scored_df(), db)
    with store.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(leads)")}
    assert {"website_url", "contact_found"} <= cols
    lead = store.get_lead(101, db)
    assert lead["contact_found"] is None and lead["website_url"] is None


def test_contact_found_counts_and_clearing(tmp_path):
    db = tmp_path / "leads.db"
    store.upsert_scored_leads(_scored_df(), db)
    assert store.contact_found_counts(db)["found_rate"] is None

    store.update_lead(101, db, contact_found="yes", contact_email="alice@example.com")
    store.update_lead(202, db, contact_found="not_found")
    counts = store.contact_found_counts(db)
    assert counts["yes"] == 1 and counts["not_found"] == 1 and counts["researched"] == 2
    assert counts["found_rate"] == 0.5

    store.update_lead(101, db, contact_found="")  # clear back to unresearched
    assert store.get_lead(101, db)["contact_found"] is None
    with pytest.raises(ValueError):
        store.update_lead(101, db, contact_found="maybe")


def test_redact_name_initials():
    assert store.redact_name("Heather & Tony") == "H. & T."
    assert store.redact_name("Alexandra Kaleialoha") == "A. K."
    assert store.redact_name("Macy") == "M."
    assert store.redact_name("  ") is None
    assert store.redact_name(None) is None


def test_exports_redact_names_on_request(tmp_path):
    db = tmp_path / "leads.db"
    store.upsert_scored_leads(_scored_df(), db)   # Alice (101), Bob (202)

    csv_redacted = store.export_csv(db, redact_names=True)
    assert "Alice" not in csv_redacted and "A." in csv_redacted
    assert "Bob" not in csv_redacted and "B." in csv_redacted

    need_redacted = store.export_needing_research_csv(db, redact_names=True)
    assert "Alice" not in need_redacted and "Bob" not in need_redacted
    assert "A." in need_redacted and "B." in need_redacted


def test_export_needing_research_filters_and_excludes_closed(tmp_path):
    db = tmp_path / "leads.db"
    store.upsert_scored_leads(_scored_df(), db)

    csv_text = store.export_needing_research_csv(db)
    assert "Alice" in csv_text and "Bob" in csv_text

    store.update_lead(101, db, contact_found="yes", contact_email="alice@example.com")
    csv_text = store.export_needing_research_csv(db)
    assert "Alice" not in csv_text and "Bob" in csv_text

    store.update_lead(202, db, contact_found="not_found", status="no_contact")
    csv_text = store.export_needing_research_csv(db)
    assert "Alice" not in csv_text and "Bob" not in csv_text and csv_text.startswith("\ufeff")
