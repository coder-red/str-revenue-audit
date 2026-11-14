"""Run the existing Listing Revenue Audit on each top lead and store the result.

Reuses str_audit.audit.run_audit untouched — we do not reimplement any audit
logic. The weakest listing per host (lowest modelled revenue, computed once in
str_leads.data) is the one audited: it is the listing most likely to need help.

Each audit JSON is written to outputs/audit_<listing_id>.json (same artefact
Project 1 produces) and linked from the leads table.
"""

from __future__ import annotations

import json
from pathlib import Path

from str_audit.audit import _sanitize, run_audit  # single JSON-safety helper, not duplicated
from str_audit.cities import default_data as _default_data
from str_audit.comps import PROJECT_ROOT
from str_audit.data import load_listings

from str_leads import store

DEFAULT_OUT_DIR = PROJECT_ROOT / "outputs"
AIRBNB_LISTING_URL = "https://www.airbnb.com/rooms/{id}"


def audit_weakest_listing(listing_id: int, df=None, k: int = 12,
                          provider: str | None = None,
                          out_dir: str | Path = DEFAULT_OUT_DIR) -> dict:
    """Run the audit for one listing; write outputs/audit_<id>.json; return the dict."""
    if df is None:
        df = load_listings(_default_data())
    audit = run_audit(df, int(listing_id), k=k, provider=provider)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"audit_{int(listing_id)}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(_sanitize(audit), fh, indent=2, allow_nan=False)
    audit["_audit_json_path"] = str(out_path)
    return audit


def audit_top_leads(host_ids: list[int], db_path: str | Path = store.DEFAULT_DB,
                    k: int = 12, provider: str | None = None,
                    force: bool = False) -> list[dict]:
    """Audit the weakest listing of each host in `host_ids`, storing links in the DB.

    Idempotent: a host that already has audit_listing_id is skipped unless force=True.
    Failures are collected, not raised, so one bad listing never kills the batch.
    """
    df = load_listings(_default_data())
    results: list[dict] = []
    for host_id in host_ids:
        lead = store.get_lead(host_id, db_path)
        if lead is None:
            results.append({"host_id": host_id, "ok": False, "error": "lead not in DB"})
            continue
        listing_id = lead.get("weakest_listing_id")
        if listing_id is None:
            results.append({"host_id": host_id, "ok": False,
                            "error": "no weakest listing on file (all listings missing modelled revenue?)"})
            continue
        if lead.get("audit_listing_id") and not force:
            results.append({"host_id": host_id, "ok": True, "skipped": True,
                            "audit_listing_id": lead["audit_listing_id"]})
            continue
        try:
            audit = audit_weakest_listing(listing_id, df=df, k=k, provider=provider)
            store.update_lead(
                host_id, db_path,
                audit_listing_id=int(listing_id),
                audit_listing_url=AIRBNB_LISTING_URL.format(id=int(listing_id)),
                audit_json_path=audit["_audit_json_path"],
                audit_provider=audit.get("llm_provider_used"),
            )
            gap = audit.get("estimate", {}).get("numbers", {}).get("est_annual_ia_revenue_gap")
            results.append({"host_id": host_id, "ok": True, "audit_listing_id": int(listing_id),
                            "est_annual_ia_revenue_gap": gap})
        except Exception as exc:  # noqa: BLE001 — batch must not die on one listing
            results.append({"host_id": host_id, "ok": False, "error": f"{exc.__class__.__name__}: {exc}"})
    return results
