"""SQLite dedupe + status tracking for leads (rule 7 — our code, stdlib only).

One row per host (host_id is the primary key — that IS the dedupe). Re-running
the scorer refreshes score fields only; status, contact info, notes, audit and
pitch drafts are never overwritten.

Statuses: new -> approved | rejected; approved -> sent -> replied -> meeting.
Terminal/other: rejected, no_contact, do_not_contact. There is deliberately NO
"send" path here — status changes are made by the human in the Streamlit queue
(or by hand), and outreach itself happens outside this repo.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "leads.db"

STATUSES = ("new", "approved", "rejected", "sent", "replied", "meeting",
            "no_contact", "do_not_contact")
CONTACT_FOUND_VALUES = ("yes", "no", "not_found")
_STATUS_TS = {"approved": "approved_at", "sent": "sent_at", "replied": "replied_at", "meeting": "meeting_at"}
_UPDATABLE = {
    "status", "contact_email", "contact_url", "contact_source", "contact_found_on",
    "notes", "pitch_subject", "pitch_body", "can_spam_ok", "pitch_provider",
    "audit_listing_id", "audit_listing_url", "audit_json_path", "audit_provider",
    "website_url", "contact_found",
}
# Statuses that mean the outreach question is closed — excluded from "needs research".
_CLOSED_STATUSES = ("rejected", "do_not_contact", "no_contact", "sent", "replied", "meeting")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    host_id INTEGER PRIMARY KEY,
    host_name TEXT,
    n_listings INTEGER,
    score INTEGER NOT NULL,
    score_version TEXT NOT NULL,
    reasons TEXT NOT NULL,                  -- JSON array
    total_modelled_revenue REAL,
    min_modelled_revenue REAL,
    median_price REAL,
    calculated_host_listings_count REAL,
    weakest_listing_id INTEGER,
    neighbourhoods TEXT,                    -- JSON array
    host_url TEXT,
    host_profile_url TEXT,
    host_about TEXT,
    contact_email TEXT,
    contact_url TEXT,
    contact_source TEXT,
    contact_found_on TEXT,
    website_url TEXT,                       -- host's own site / business listing (public)
    contact_found TEXT,                     -- 'yes' | 'no' | 'not_found' | NULL (not researched yet)
    status TEXT NOT NULL DEFAULT 'new',
    audit_listing_id INTEGER,
    audit_listing_url TEXT,
    audit_json_path TEXT,
    audit_provider TEXT,
    pitch_subject TEXT,
    pitch_body TEXT,
    pitch_provider TEXT,
    can_spam_ok INTEGER,                    -- 1 only when sender identity + opt-out are present
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT,
    sent_at TEXT,
    replied_at TEXT,
    meeting_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
"""

# Forward-only, idempotent column additions for DBs created before 2026-11-12.
_MIGRATIONS = [("website_url", "TEXT"), ("contact_found", "TEXT")]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}
    for name, decl in _MIGRATIONS:
        if name not in existing:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {name} {decl}")


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for col in ("reasons", "neighbourhoods"):
        try:
            d[col] = json.loads(d[col]) if d[col] else []
        except (TypeError, json.JSONDecodeError):
            d[col] = []
    return d


def upsert_scored_leads(df: pd.DataFrame, db_path: str | Path = DEFAULT_DB,
                        score_version: str = "1.0") -> dict:
    """Insert new hosts; refresh scoring fields for existing ones. Never touches
    status/contact/notes/pitch/audit. Returns {'inserted': n, 'updated': m}."""
    inserted = updated = 0
    payload_cols = ["host_id", "host_name", "n_listings", "score", "total_modelled_revenue",
                    "min_modelled_revenue", "median_price", "calculated_host_listings_count",
                    "weakest_listing_id", "neighbourhoods", "host_url", "host_profile_url",
                    "host_about", "reasons"]
    with connect(db_path) as conn:
        for rec in df.itertuples(index=False):
            row = rec._asdict()
            missing = [c for c in payload_cols if c not in row]
            if missing:
                raise ValueError(f"scored dataframe is missing columns: {missing}")
            host_id = int(row["host_id"])
            if pd.isna(host_id):
                continue
            reasons = row["reasons"]
            if not isinstance(reasons, str):
                reasons = json.dumps(list(reasons), ensure_ascii=False)
            nbhd = row.get("neighbourhoods")
            neighbourhoods = json.dumps(list(nbhd) if isinstance(nbhd, (list, tuple)) else [],
                                        ensure_ascii=False)
            exists = conn.execute("SELECT 1 FROM leads WHERE host_id = ?", (host_id,)).fetchone()
            now = _now()
            if exists:
                conn.execute(
                    """UPDATE leads SET host_name=?, n_listings=?, score=?, score_version=?,
                       reasons=?, total_modelled_revenue=?, min_modelled_revenue=?, median_price=?,
                       calculated_host_listings_count=?, weakest_listing_id=?, neighbourhoods=?,
                       host_url=?, host_profile_url=?, host_about=?, updated_at=?
                       WHERE host_id=?""",
                    (_clean_str(row["host_name"]), int(row["n_listings"]), int(row["score"]),
                     score_version, reasons, _num(row["total_modelled_revenue"]),
                     _num(row["min_modelled_revenue"]), _num(row["median_price"]),
                     _num(row["calculated_host_listings_count"]), _int_or_none(row["weakest_listing_id"]),
                     neighbourhoods, _clean_str(row["host_url"]), _clean_str(row["host_profile_url"]),
                     _clean_str(row["host_about"]), now, host_id),
                )
                updated += 1
            else:
                conn.execute(
                    """INSERT INTO leads (host_id, host_name, n_listings, score, score_version,
                       reasons, total_modelled_revenue, min_modelled_revenue, median_price,
                       calculated_host_listings_count, weakest_listing_id, neighbourhoods,
                       host_url, host_profile_url, host_about, status, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'new', ?, ?)""",
                    (host_id, _clean_str(row["host_name"]), int(row["n_listings"]), int(row["score"]),
                     score_version, reasons, _num(row["total_modelled_revenue"]),
                     _num(row["min_modelled_revenue"]), _num(row["median_price"]),
                     _num(row["calculated_host_listings_count"]), _int_or_none(row["weakest_listing_id"]),
                     neighbourhoods, _clean_str(row["host_url"]), _clean_str(row["host_profile_url"]),
                     _clean_str(row["host_about"]), now, now),
                )
                inserted += 1
    return {"inserted": inserted, "updated": updated}


def _num(v) -> float | None:
    return None if v is None or pd.isna(v) else float(v)


def _int_or_none(v) -> int | None:
    return None if v is None or pd.isna(v) else int(v)


def _clean_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def get_lead(host_id: int, db_path: str | Path = DEFAULT_DB) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM leads WHERE host_id = ?", (int(host_id),)).fetchone()
    return _row_to_dict(row) if row else None


def list_leads(db_path: str | Path = DEFAULT_DB, status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM leads"
    params: tuple = ()
    if status:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY score DESC, n_listings DESC, min_modelled_revenue ASC"
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def contact_found_counts(db_path: str | Path = DEFAULT_DB) -> dict:
    """Running stat for the UI: researched = any contact_found set; found = 'yes'."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT contact_found, count(*) AS n FROM leads GROUP BY contact_found"
        ).fetchall()
    counts = {"yes": 0, "no": 0, "not_found": 0, "unresearched": 0}
    for r in rows:
        key = r["contact_found"] if r["contact_found"] in CONTACT_FOUND_VALUES else "unresearched"
        counts[key] += r["n"]
    researched = counts["yes"] + counts["no"] + counts["not_found"]
    counts["researched"] = researched
    counts["found_rate"] = (counts["yes"] / researched) if researched else None
    return counts


def needing_research(db_path: str | Path = DEFAULT_DB) -> list[dict]:
    """Leads not yet researched for a public contact (still need the manual dig)."""
    placeholders = ",".join("?" * len(_CLOSED_STATUSES))
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT * FROM leads
                WHERE (contact_found IS NULL OR contact_found = '')
                  AND status NOT IN ({placeholders})
                ORDER BY score DESC, n_listings DESC, min_modelled_revenue ASC""",
            _CLOSED_STATUSES,
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


_NEED_RESEARCH_COLS = [
    "host_id", "host_name", "score", "n_listings", "score_version",
    "weakest_listing_id", "audit_listing_id", "audit_listing_url",
    "host_url", "host_profile_url", "host_about", "neighbourhoods",
    "reasons", "notes", "pitch_subject", "created_at",
]


def export_needing_research_csv(db_path: str | Path = DEFAULT_DB) -> str:
    """CSV of leads still needing manual contact research — for the outreach workflow."""
    leads = needing_research(db_path)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_NEED_RESEARCH_COLS, lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()
    for d in leads:
        row = {c: d.get(c) for c in _NEED_RESEARCH_COLS}
        row["neighbourhoods"] = ", ".join(d.get("neighbourhoods") or [])
        row["reasons"] = " | ".join(d.get("reasons") or [])
        writer.writerow(row)
    return "\ufeff" + buf.getvalue()


def status_counts(db_path: str | Path = DEFAULT_DB) -> dict[str, int]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT status, count(*) AS n FROM leads GROUP BY status").fetchall()
    counts = {s: 0 for s in STATUSES}
    counts.update({r["status"]: r["n"] for r in rows})
    return counts


def update_lead(host_id: int, db_path: str | Path = DEFAULT_DB, **fields) -> dict:
    """Update whitelisted fields; manage transition timestamps. Never sets 'sent' from here
    without the human explicitly choosing it in the UI."""
    fields = {k: v for k, v in fields.items() if k in _UPDATABLE}
    status = fields.get("status")
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    found = fields.get("contact_found")
    if found is not None and found not in CONTACT_FOUND_VALUES and found != "":
        raise ValueError(f"contact_found must be one of {CONTACT_FOUND_VALUES} (or '' to clear)")
    if found == "":
        fields["contact_found"] = None

    now = _now()
    assignments = ["updated_at = ?"]
    params: list = [now]
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        params.append(value)
    if status in _STATUS_TS:  # stamp the transition time once, on entry
        assignments.append(f"{_STATUS_TS[status]} = COALESCE({_STATUS_TS[status]}, ?)")
        params.append(now)

    params.append(int(host_id))
    with connect(db_path) as conn:
        conn.execute(f"UPDATE leads SET {', '.join(assignments)} WHERE host_id = ?", params)
        row = conn.execute("SELECT * FROM leads WHERE host_id = ?", (int(host_id),)).fetchone()
    if row is None:
        raise KeyError(f"lead {host_id} not found")
    return _row_to_dict(row)


_EXPORT_COLS = [
    "host_id", "host_name", "status", "score", "n_listings", "median_price",
    "total_modelled_revenue", "min_modelled_revenue", "weakest_listing_id",
    "host_url", "contact_email", "contact_url", "contact_source", "contact_found_on",
    "website_url", "contact_found",
    "audit_listing_id", "audit_listing_url", "audit_json_path",
    "pitch_subject", "pitch_body", "can_spam_ok", "notes",
    "created_at", "updated_at", "approved_at", "sent_at", "replied_at", "meeting_at",
]


def export_csv(db_path: str | Path = DEFAULT_DB, statuses: list[str] | None = None) -> str:
    """CSV of the leads, reasons flattened — ready for Excel. UTF-8 BOM so Excel opens it cleanly."""
    leads = list_leads(db_path)
    if statuses:
        bad = [s for s in statuses if s not in STATUSES]
        if bad:
            raise ValueError(f"unknown statuses: {bad}")
        leads = [d for d in leads if d["status"] in statuses]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_COLS + ["reasons", "neighbourhoods"],
                            extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for d in leads:
        row = {c: d.get(c) for c in _EXPORT_COLS}
        row["reasons"] = " | ".join(d.get("reasons") or [])
        row["neighbourhoods"] = ", ".join(d.get("neighbourhoods") or [])
        writer.writerow(row)
    return "\ufeff" + buf.getvalue()
