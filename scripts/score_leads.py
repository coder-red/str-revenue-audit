"""STR Owner Lead Finder — pipeline driver.

Phase 1 (default): score every host, print the ranking, upsert into SQLite.
Phase 2 (--audit N): additionally run the Listing Revenue Audit on the weakest
listing of each of the top N hosts and store links in the DB.

Usage:
    python scripts/score_leads.py                      # rank + upsert into data/leads.db
    python scripts/score_leads.py --top-n 15           # print more rows
    python scripts/score_leads.py --audit 10           # audit weakest listing of top 10
    python scripts/score_leads.py --no-store --csv outputs/leads_ranked.csv   # read-only

Never sends anything. Outreach happens manually after human review in leadfinder_app.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from str_leads import pitch as pitch_mod
from str_leads import store
from str_leads import contact_finder
from str_leads.audit_bridge import audit_top_leads
from str_leads.data import build_host_table
from str_leads.score import MAX_SCORE, SCORE_VERSION, score_hosts
from str_audit.cities import city as _city_fn, default_data

DEFAULT_CSV = "outputs/leads_ranked.csv"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=None, help="path to listings.csv.gz (overrides --city default)")
    ap.add_argument("--city", choices=["austin", "dallas", "fort-worth"], default=None,
                    help="metro to score (default: austin, or STR_CITY env if set); downloads via scripts/download_data.py if needed")
    ap.add_argument("--top-n", type=int, default=10, help="rows to print (default 10)")
    ap.add_argument("--csv", default=DEFAULT_CSV, help="where to write the ranked CSV")
    ap.add_argument("--include-agencies", action="store_true",
                    help="do not exclude likely property-management agencies")
    ap.add_argument("--agency-cutoff", type=int, default=None, metavar="N",
                    help="agency threshold: hosts with >=N calculated listings are treated as "
                         "professional operators and excluded (default: 5; try 8 or 15)")
    ap.add_argument("--db", default=str(store.DEFAULT_DB), help="SQLite path (default data/leads.db)")
    ap.add_argument("--no-store", action="store_true", help="do not write to the DB (read-only ranking)")
    ap.add_argument("--audit", type=int, default=0, metavar="N",
                    help="run the audit on the weakest listing of each of the top N hosts")
    ap.add_argument("--provider", choices=["gemini", "groq", "none"], default=None,
                    help="LLM provider (default: LLM_PROVIDER from .env; 'none' = offline fallback)")
    ap.add_argument("--find-contacts", type=int, default=0, metavar="N",
                    help="public-contact discovery for the top N leads only (Brave API; needs BRAVE_API_KEY in .env). NEVER runs by default.")
    ap.add_argument("--force-audit", action="store_true",
                    help="re-audit hosts that already have an audit on file")
    ap.add_argument("--pitch", type=int, default=0, metavar="N",
                    help="draft outreach pitches for the top N hosts (needs an audit on file)")
    ap.add_argument("--force-pitch", action="store_true",
                    help="re-draft pitches for hosts that already have one")
    args = ap.parse_args()

    print("Loading snapshot and building host table…")
    slug = _city_fn(args.city)["slug"] if args.city else _city_fn()["slug"]
    _path = Path(args.data) if args.data else default_data(slug)
    print(f"city data: {_path}")
    table = build_host_table(str(_path))
    ranked_all = score_hosts(table, exclude_agencies=not args.include_agencies,
                             agency_cutoff=args.agency_cutoff)
    ranked = ranked_all if args.include_agencies else ranked_all[~ranked_all["excluded_agency"]]

    agencies = ranked_all[ranked_all["agency_reason"].notna()]
    n_agencies = int(ranked_all["excluded_agency"].sum())
    print(f"hosts: {len(ranked_all)} | likely agencies excluded: {n_agencies} | "
          f"ranked: {len(ranked)} | score version {SCORE_VERSION} (max {MAX_SCORE})")
    if args.include_agencies:
        print(f"(--include-agencies: {len(agencies)} company-like hosts kept in ranking)")
    elif n_agencies:
        for r in agencies.head(5).itertuples(index=False):
            print(f"  excluded: host {r.host_id} '{r.host_name}' — {r.agency_reason}")

    cols = ["host_id", "host_name", "n_listings", "score", "median_price",
            "total_modelled_revenue", "host_tenure_months", "host_response_rate"]
    print(f"\nTop {min(args.top_n, len(ranked))} of ranked hosts:")
    print(ranked[cols].head(args.top_n).to_string(index=False))

    for i, (_, row) in enumerate(ranked.head(args.top_n).iterrows(), 1):
        print(f"\n#{i} host {row.host_id} — {row.host_name} (score {row.score}/{MAX_SCORE}, "
              f"{row.n_listings} listings)")
        for reason in row["reasons"]:
            print(f"    {reason}")

    if not args.no_store:
        counts = store.upsert_scored_leads(ranked, args.db, score_version=SCORE_VERSION)
        print(f"\nDB {args.db}: inserted {counts['inserted']} new leads, "
              f"refreshed {counts['updated']} existing (status/contact/notes untouched)")
        print(f"status counts: {store.status_counts(args.db)}")

    if args.audit > 0:
        audit_ids = [int(x) for x in ranked.head(args.audit)["host_id"]]
        provider = None if args.provider in (None, "none") else args.provider
        print(f"\nAuditing the weakest listing of the top {args.audit} hosts "
              f"(provider: {args.provider or 'env/default'})…")
        results = audit_top_leads(audit_ids, db_path=args.db, provider=provider,
                                  force=args.force_audit)
        for r in results:
            if r.get("ok") and r.get("skipped"):
                print(f"  host {r['host_id']}: already audited (listing {r['audit_listing_id']}), skipped")
            elif r.get("ok"):
                gap = r.get("est_annual_ia_revenue_gap")
                gap_s = f"${gap:+,.0f}/yr" if isinstance(gap, (int, float)) else "n/a"
                print(f"  host {r['host_id']}: weakest listing {r['audit_listing_id']} audited "
                      f"(est. gap vs comp-median: {gap_s})")
            else:
                print(f"  host {r['host_id']}: FAILED — {r.get('error')}")

    if args.find_contacts > 0:
        brave_key = None
        try:
            from dotenv import load_dotenv
            load_dotenv()
            import os as _os
            brave_key = _os.environ.get("BRAVE_API_KEY", "").strip() or None
        except ImportError:
            pass
        if not brave_key:
            print("\n--find-contacts: BRAVE_API_KEY not set in .env — skipping contact search. "
                  "Sign up at https://api-dashboard.search.brave.com/register (free tier, $5/mo included).")
        else:
            from str_audit.cities import label as _city_label
            city = _city_label(slug)
            targets = ranked.head(args.find_contacts).to_dict("records")
            print(f"\nPublic-contact discovery for top {args.find_contacts} hosts ({city}, Brave web)…")
            print("Note: hit rates are low on Inside Airbnb names (display names, no domain). "
                  "Emails are ONLY accepted when name matches the page AND a mailto: exists — never guessed.")
            for r in targets:
                host = r["host_name"]
                hits = contact_finder.find_for_lead(host, city, brave_key, max_results=10)
                if hits:
                    top = hits[0]
                    store.update_lead(int(r["host_id"]), args.db,
                                      contact_email=top.email,
                                      contact_url=top.url,
                                      contact_source=top.source,
                                      contact_found="yes",
                                      contact_found_on=__import__("datetime").date.today().isoformat(),
                                      notes=f"auto: evidence {top.evidence_score} | query: {top.query}")
                    print(f"  host {r['host_id']} ({host!r}): {top.email}  via {top.url[:80]}")
                else:
                    store.update_lead(int(r["host_id"]), args.db,
                                      contact_found="not_found",
                                      contact_found_on=__import__("datetime").date.today().isoformat())
                    print(f"  host {r['host_id']} ({host!r}): no public contact found")

    if args.pitch > 0:
        provider = None if args.provider in (None, "none") else args.provider
        # Candidates = hosts with an audit on file (score desc from list_leads), NOT the
        # current ranking — re-weighting the score must not orphan previously audited hosts.
        audited = [d for d in store.list_leads(args.db) if d.get("audit_json_path")]
        candidate_ids = [int(d["host_id"]) for d in audited[:args.pitch]]
        print(f"\nDrafting pitches for {len(candidate_ids)} hosts that already have an audit on file…")
        done = 0
        for host_id in candidate_ids:
            if done >= args.pitch:
                break
            lead = store.get_lead(host_id, args.db)
            if not lead:
                continue
            path = lead.get("audit_json_path")
            if not path or not Path(path).exists():
                continue  # not audited yet — skip silently, run with --audit first
            if lead.get("pitch_body") and not args.force_pitch:
                print(f"  host {host_id}: pitch already drafted, skipped (--force-pitch to redo)")
                done += 1
                continue
            audit = pitch_mod.load_audit(path)
            result = pitch_mod.generate_pitch(lead, audit, provider=provider)
            store.update_lead(host_id, args.db,
                              pitch_subject=result["subject"],
                              pitch_body=result["body"],
                              pitch_provider=result["provider_used"],
                              can_spam_ok=1 if result["can_spam_ok"] else 0)
            done += 1
            flag = "OK" if result["can_spam_ok"] else f"NOT SENDABLE: {', '.join(result['can_spam_problems'])}"
            print(f"  host {host_id}: pitch drafted ({result['provider_used']}) — {flag}")

    out = ranked.copy()
    out["reasons"] = out["reasons"].apply(lambda rs: " | ".join(rs))
    out = out.drop(columns=["austin_listing_ids", "neighbourhoods", "agency_reason",
                            "excluded_agency"], errors="ignore")
    out.to_csv(args.csv, index=False, encoding="utf-8-sig")
    print(f"\nwrote {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
