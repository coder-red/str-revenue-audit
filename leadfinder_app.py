"""STR Owner Lead Finder — Streamlit review queue.

Outreach NEVER happens from here (rule 6). This app is: review ranked leads →
read the audit → edit the drafted pitch → approve/reject → export a CSV you
send from your own mailbox. Sender identity (CAN-SPAM) is read from .env.

Run:  streamlit run leadfinder_app.py
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from str_leads import pitch as pitch_mod
from str_leads import store
from str_audit.cities import city as _city

_CITY = _city()
DOT = {"pass": "🟢", "warn": "🟠", "fail": "🔴", "unknown": "⚪"}
CONTACT_SOURCES = ["host's own website", "business listing (BBB / Google Business Profile)",
                    "OpenCorporates / county property records", "host_about or host profile text",
                    "other (describe in notes)"]
DB = str(store.DEFAULT_DB)

# Hosted portfolio demos set LEADFINDER_REDACT_NAMES=1: host names render as
# initials everywhere (queue, tables, exports) so no real owner is public.
REDACT = os.environ.get("LEADFINDER_REDACT_NAMES", "").lower() in ("1", "true", "yes")


def _disp_name(d: dict) -> str:
    if REDACT:
        return store.redact_name(d.get("host_name")) or f"Host {d.get('host_id')}"
    return d.get("host_name") or "(unnamed host)"


def _seed_demo_if_empty():
    """Hosted demos start with no DB; seed from the committed redacted parquet on first boot."""
    try:
        total = sum(store.status_counts(DB).values())
    except Exception:
        total = 0
    if total:
        return
    seed = Path(__file__).resolve().parent / "data" / "lead_seed.parquet"
    if seed.exists():
        with st.spinner("Loading public demo rankings…"):
            import pandas as pd
            ranked = pd.read_parquet(seed)
            store.upsert_scored_leads(ranked, DB, score_version=str(ranked["score_version"].iloc[0]))
        return
    with st.spinner("Building demo rankings from Inside Airbnb's public Austin snapshot "
                    "(one-time, ~60-90 s)…"):
        from str_leads.data import build_host_table
        from str_leads.score import SCORE_VERSION, score_hosts
        table = build_host_table()
        ranked = score_hosts(table, agency_cutoff=5)
        store.upsert_scored_leads(ranked, DB, score_version=SCORE_VERSION)


def sender_status() -> tuple[bool, list[str]]:
    s = pitch_mod.sender_identity()
    missing = [k for k, v in (("SENDER_NAME", s["name"]), ("SENDER_BUSINESS", s["business"]),
                              ("SENDER_POSTAL_ADDRESS", s["postal"])) if not v]
    return (not missing), missing


def sidebar():
    with st.sidebar:
        st.markdown("### 🎯 STR Owner Lead Finder")
        st.caption(f"{_CITY['name']}, {_CITY['state']} · Inside Airbnb snapshot {_CITY['snapshot']} "
                   f"(CC BY 4.0). Every revenue figure is an ESTIMATE. "
                   f"Hosts ranked by a transparent, explainable score.")
        st.divider()

        ok, missing = sender_status()
        st.markdown("**Sender identity (CAN-SPAM)**")
        if ok:
            st.success("Sender name, business and postal address found in `.env` — drafts can be exportable.")
        else:
            st.error(f"Missing in `.env`: {', '.join(missing)}. Drafts will be flagged "
                     f"**not sendable** until you set these and re-draft.")
            st.caption("CAN-SPAM requires real sender identity + a physical postal address. "
                       "Edit `.env`, then use “Re-draft from audit” per lead.")

        st.divider()
        if REDACT:
            st.caption("Portfolio demo — host names redacted to initials. "
                       "No real owner is identifiable from this deployment.")
        st.markdown("**Queue contents**")
        counts = store.status_counts(DB)
        cols = st.columns(4)
        for i, (k, v) in enumerate(counts.items()):
            cols[i % 4].metric(k.replace("_", " "), v)
        st.divider()
        st.markdown("**Contact research (manual)**")
        cf = store.contact_found_counts(DB)
        if cf["researched"]:
            st.metric("Contact found rate", f"{cf['found_rate']:.0%}",
                      f"{cf['yes']} found of {cf['researched']} researched")
        else:
            st.caption("No contact research recorded yet — mark leads in the queue to build the rate.")

        provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
        key_present = bool(os.environ.get("GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY"))
        st.divider()
        st.markdown("**Pitch writer**")
        if key_present:
            st.success(f"LLM: {provider} (key found in .env)")
        else:
            st.info(f"LLM: {provider} — no key in .env, drafts use the deterministic offline fallback.")

        with st.expander("How outreach works (read this)"):
            st.markdown(
                "1. Review a lead — read the audit and the draft.\n"
                "2. Find the host's **public** contact info (host website, business listing, "
                "county records). Paste it in — every contact records its source URL. "
                "No public contact? Mark **no contact** and move on.\n"
                "3. Approve a strong draft (or edit it).\n"
                "4. Export CSV and **send it yourself, manually**. This tool cannot send.\n"
                "5. Honor opt-outs within 10 business days."
            )
        st.caption("No Airbnb scraping · no purchased lists · no guessing emails. "
                   "Data: Inside Airbnb (CC BY 4.0).")


def _lead_label(d: dict) -> str:
    name = _disp_name(d)
    return f"{d['score']}/16 · {name} · {d.get('n_listings', 0)} listings · {d['status']}"


def _audit_brief(d: dict) -> dict | None:
    path = d.get("audit_json_path")
    if not path or not Path(path).exists():
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _draft_editor(d: dict):
    st.markdown("#### Draft")
    subject = st.text_input("Subject", value=d.get("pitch_subject") or "", key=f"subject_{d['host_id']}")
    body = st.text_area("Body (you are the sender — read every word before approving)",
                        value=d.get("pitch_body") or "", height=340,
                        key=f"body_{d['host_id']}")
    ok, problems = pitch_mod.can_spam_ok(subject, body)
    words = len(body.split())
    c1, c2 = st.columns([1, 3])
    c1.metric("Words", words)
    if ok:
        c2.success("CAN-SPAM check passes — sender identity, postal address and opt-out are present.")
    else:
        c2.error("**NOT SENDABLE:** " + "; ".join(problems))
    return subject, body, ok


def review_queue():
    st.subheader("📥 Review queue")
    status_filter = st.multiselect("Show statuses", options=list(store.STATUSES),
                                   default=["new", "approved"])
    leads = [d for d in store.list_leads(DB) if d["status"] in status_filter]
    if not leads:
        st.info("Nothing in the queue for those statuses. Run `python scripts/score_leads.py --audit 10 --pitch 10` "
                "to create/refresh leads and drafts.")
        return

    ids = [d["host_id"] for d in leads]
    labels = {d["host_id"]: _lead_label(d) for d in leads}
    host_id = st.selectbox("Pick a lead", options=ids, format_func=lambda i: labels[i])
    d = next(x for x in leads if x["host_id"] == host_id)

    # -- header metrics ------------------------------------------------------
    m = st.columns(3)
    m[0].metric("Lead score", f"{d['score']}/16")
    m[1].metric("Listings", d.get("n_listings") or 0)
    m[2].metric("Median price", f"${d['median_price']:.0f}" if d.get("median_price") else "n/a")
    tr = d.get("total_modelled_revenue")
    tr_s = f"${tr:,.0f}" if tr else "n/a"
    st.markdown(f"**Status:** `{d['status']}` · **Modelled revenue across their listings (Σ):** "
                f"{tr_s} — *Inside Airbnb model, an estimate, not booked revenue*")
    st.caption("Score reasons: " + " · ".join(d.get("reasons") or []))
    links = []
    for col, label in (("host_url", "Host profile"), ("host_profile_url", "Host profile (alt)"),
                       ("audit_listing_url", "Audited listing")):
        if d.get(col):
            links.append(f"[{label}]({d[col]})")
    if links:
        st.markdown(" · ".join(links))
    nbhd = ", ".join(d.get("neighbourhoods") or [])
    if nbhd:
        st.caption(f"Neighbourhoods: {nbhd}")

    left, right = st.columns([1, 1], gap="large")

    # -- left: the audit evidence ---------------------------------------------
    with left:
        st.markdown("#### What the audit found")
        audit = _audit_brief(d)
        if audit is None:
            st.warning("No audit on file for this host yet. Run: "
                       f"`python scripts/score_leads.py --audit {len(leads)}` from the repo root.")
        else:
            t = audit.get("target", {})
            n = audit.get("estimate", {}).get("numbers", {})
            st.markdown(f"**{t.get('name')}** — {t.get('room_type')} · {t.get('bedrooms')}BR · "
                        f"${t.get('price')}/night · {t.get('neighbourhood_cleansed')}")
            a = st.columns(3)
            def _m(v):
                return f"${v:,.0f}" if isinstance(v, (int, float)) else "n/a"
            a[0].metric("Est. gap vs comp median /yr", _m(n.get("est_annual_ia_revenue_gap")),
                        help="ESTIMATE — Inside Airbnb model vs comp-median, active comps only.")
            a[1].metric("Est. price-positioning gap /yr", _m(n.get("est_annual_price_gap")),
                        help="ESTIMATE — (comp median price − target) × comp occupancy × 365.")
            a[2].metric("Their modelled rev /yr", _m(n.get("target_estimated_revenue_l365d")),
                        help="ESTIMATE — Inside Airbnb model for this listing.")
            for s in audit.get("signals", []):
                st.markdown(f"{DOT.get(s.get('status'), '⚪')} {s.get('summary')}")
            if audit.get("top_fixes"):
                st.markdown("**Top fixes**")
                for i, fix in enumerate(audit["top_fixes"], 1):
                    st.markdown(f"{i}. {fix}")
            with st.expander("Audit summary (LLM or offline fallback)"):
                st.text(audit.get("llm_summary", ""))
                st.caption(f"Writer: {audit.get('llm_provider_used')}")
        if d.get("pitch_subject") is None and not d.get("pitch_body"):
            if audit is not None:
                if st.button("✍️ Draft pitch from audit", key=f"gen_{d['host_id']}"):
                    with st.spinner("Drafting from the audit…"):
                        result = pitch_mod.generate_pitch(d, audit)
                    store.update_lead(d["host_id"], DB,
                                      pitch_subject=result["subject"],
                                      pitch_body=result["body"],
                                      pitch_provider=result["provider_used"],
                                      can_spam_ok=1 if result["can_spam_ok"] else 0)
                    st.rerun()

    # -- right: contact research capture + the draft ---------------------------
    with right:
        st.markdown("#### Contact research (manual — no lookup services, no guessing)")
        website_url = st.text_input("Host's public website / business listing",
                                    value=d.get("website_url") or "", key=f"web_{d['host_id']}",
                                    placeholder="their site, BBB / Google Business Profile, county property record…")
        e1, e2 = st.columns([2, 3])
        email = e1.text_input("Contact email (if public)", value=d.get("contact_email") or "",
                              key=f"email_{d['host_id']}", placeholder="found on their site / listing")
        found_on = e2.date_input("Looked on", value=date.today(), key=f"found_on_{d['host_id']}")
        source = st.selectbox("Source", options=CONTACT_SOURCES,
                              index=CONTACT_SOURCES.index(d["contact_source"]) if d.get("contact_source") in CONTACT_SOURCES else 0,
                              key=f"source_{d['host_id']}")
        contact_url = st.text_input("Source URL (re-verify before sending)",
                                    value=d.get("contact_url") or "", key=f"curl_{d['host_id']}")
        found_options = ["unresearched", "yes", "no", "not_found"]
        current_found = d.get("contact_found") if d.get("contact_found") in ("yes", "no", "not_found") else "unresearched"
        found = st.selectbox("Contact found?", options=found_options,
                             index=found_options.index(current_found),
                             key=f"found_{d['host_id']}",
                             help="yes = a public contact exists (email required) · no = searched, none found · "
                                  "not_found = confirmed nothing public after a proper look")
        notes = st.text_area("Research notes (visible to you, anyone with the DB file)",
                             value=d.get("notes") or "", key=f"notes_{d['host_id']}", height=70)
        csave, cno_contact = st.columns(2)
        if csave.button("💾 Save contact research", key=f"savec_{d['host_id']}", width='stretch'):
            problems = []
            if found == "yes" and not email.strip():
                problems.append("marked 'yes' but no email set — a yes must point at a real, public address")
            if email.strip() and not contact_url.strip():
                problems.append("contact email set without a source URL — record where it was found")
            store.update_lead(d["host_id"], DB,
                              website_url=website_url.strip() or None,
                              contact_email=email.strip() or None,
                              contact_url=contact_url.strip() or None,
                              contact_source=source,
                              contact_found_on=found_on.isoformat(),
                              contact_found=None if found == "unresearched" else found,
                              notes=notes)
            if problems:
                st.warning("Saved — but: " + "; ".join(problems) + ".")
            else:
                st.success("Contact research saved.")
            st.rerun()
        if cno_contact.button("🚫 No public contact exists", key=f"nc_{d['host_id']}",
                              width='stretch',
                              help="Marks research 'not_found' + lead 'no contact'. Never guess an address."):
            store.update_lead(d["host_id"], DB, contact_found="not_found",
                              contact_found_on=date.today().isoformat(), status="no_contact")
            st.info("Marked not_found + no contact. Moving on — the expected outcome for most hosts.")
            st.rerun()

        subject, body, ok = _draft_editor(d)
        if st.button("🔁 Re-check CAN-SPAM / save edits", key=f"save_{d['host_id']}"):
            store.update_lead(d["host_id"], DB, pitch_subject=subject, pitch_body=body,
                              can_spam_ok=1 if ok else 0)
            st.success("Draft saved." + ("" if ok else " Still flagged — see above."))
            st.rerun()
        st.caption(f"Draft writer: {d.get('pitch_provider') or 'not drafted yet'}")

        st.divider()
        st.markdown("#### Approve & track")
        a1, a2, a3 = st.columns(3)
        if a1.button("✅ Approve draft", key=f"ap_{d['host_id']}", width='stretch'):
            store.update_lead(d["host_id"], DB, status="approved",
                              pitch_subject=subject, pitch_body=body,
                              can_spam_ok=1 if ok else 0)
            st.success("Approved. Export it in the Export tab — then send it yourself."
                       + ("" if ok else " ⚠️ Draft is flagged NOT SENDABLE — fix sender identity first."))
            st.rerun()
        if a2.button("❌ Reject lead", key=f"rj_{d['host_id']}", width='stretch'):
            store.update_lead(d["host_id"], DB, status="rejected")
            st.rerun()
        if a3.button("🛑 Do not contact", key=f"dnc_{d['host_id']}", width='stretch',
                     help="Permanently exclude this host — use for opt-outs / complaints."):
            store.update_lead(d["host_id"], DB, status="do_not_contact")
            st.rerun()
        b1, b2, b3 = st.columns(3)
        for col, label, status, key in (
                (b1, "📤 Mark sent", "sent", "st_"),
                (b2, "💬 Mark replied", "replied", "rp_"),
                (b3, "🤝 Mark meeting", "meeting", "mt_")):
            if col.button(label, key=f"{key}{d['host_id']}", width='stretch',
                          disabled=d["status"] not in ("approved", "sent", "replied", "meeting")):
                store.update_lead(d["host_id"], DB, status=status)
                st.rerun()


def all_leads_tab():
    st.subheader("📋 All leads")
    leads = store.list_leads(DB)
    if not leads:
        st.info("No leads yet — run `python scripts/score_leads.py`.")
        return
    rows = []
    for i, d in enumerate(leads):
        rows.append({
            ("#" if REDACT else "host_id"): i + 1 if REDACT else d["host_id"], "host_name": _disp_name(d),
            "score": d["score"], "n_listings": d.get("n_listings"),
            "median_price": d.get("median_price"),
            "status": d["status"], "contact": d.get("contact_email"),
            "found": d.get("contact_found") or "—",
            "source": d.get("contact_source"),
            "draft ok (CAN-SPAM)": bool(d.get("can_spam_ok")),
            "reasons": " | ".join(d.get("reasons") or []),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, width='stretch', hide_index=True)
    st.caption(f"{len(df)} leads · sorted by score · DB: {DB}")


def export_tab():
    st.subheader("⬇️ Export")
    statuses = st.multiselect("Statuses to include", options=list(store.STATUSES),
                              default=["approved"])
    if not statuses:
        st.info("Pick at least one status.")
        return
    leads = [d for d in store.list_leads(DB) if d["status"] in statuses]
    if not leads:
        st.info("No leads in those statuses.")
        return
    flagged = [d for d in leads if not d.get("can_spam_ok")]
    st.write(f"**{len(leads)}** lead(s) will be exported; **{len(flagged)}** flagged as not sendable "
             f"(missing sender identity or opt-out).")
    if flagged:
        st.error("Flagged leads in this export: " + ", ".join(str(d["host_id"]) for d in flagged) +
                 ". Fix sender identity in `.env` and re-draft, or verify/edit each draft before sending. "
                 "Exporting anyway is allowed — sending them is your responsibility.")
        acknowledged = st.checkbox("I understand these drafts are not sendable as-is, and I will verify "
                                   "sender identity, postal address and opt-out before sending.")
    else:
        acknowledged = True
    csv_bytes = store.export_csv(DB, statuses, redact_names=REDACT).encode("utf-8")
    st.download_button("Download leads_export.csv", data=csv_bytes,
                       file_name="leads_export.csv", mime="text/csv",
                       disabled=not acknowledged)
    st.caption("Columns include the draft subject/body, contact + source URL, audit link, status "
               "timeline and reasons. Send manually from your own mailbox; honor opt-outs within "
               "10 business days; never mark anyone sent before they actually were.")
    st.divider()
    st.markdown("**Needs contact research (unresearched leads)**")
    needing = store.needing_research(DB)
    st.write(f"**{len(needing)}** lead(s) have not been researched yet (contact found = unresearched, "
             f"status not closed). Work these in the queue, or hand the CSV to whoever does the manual dig.")
    st.download_button("Download leads_needing_contact_research.csv",
                       data=store.export_needing_research_csv(DB, redact_names=REDACT).encode("utf-8"),
                       file_name="leads_needing_contact_research.csv", mime="text/csv")


def render():
    if REDACT:
        _seed_demo_if_empty()
    sidebar()
    tab1, tab2, tab3 = st.tabs(["📥 Review queue", "📋 All leads", "⬇️ Export"])
    with tab1:
        review_queue()
    with tab2:
        all_leads_tab()
    with tab3:
        export_tab()


if __name__ == "__main__":
    import streamlit as st
    st.set_page_config(page_title="STR Owner Lead Finder", page_icon="🎯", layout="wide")
    render()
