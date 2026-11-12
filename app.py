"""STR Revenue Audit — Streamlit app.

Three ways in:
  1) Audit a listing from the Inside Airbnb Austin snapshot (by id).
  2) Enter listing details manually (feeds the photo-count signal, which
     public data can't provide).
  3) Upload a one-row CSV/JSON with the same fields.

Renders the audit on screen and offers the one-page PDF for download.
Run:  streamlit run app.py
"""

from __future__ import annotations

import io
import json
import os

from dotenv import load_dotenv
import pandas as pd
import streamlit as st

load_dotenv()  # sidebar reads os.environ for the LLM key status; llm.py loads it lazily otherwise

from str_audit.audit import run_audit, run_audit_custom
from str_audit.comps import DEFAULT_DATA
from str_audit.data import load_listings
from str_audit.report import _money, _int_or_dash, render_pdf

st.set_page_config(page_title="STR Revenue Audit", page_icon="🏠", layout="wide")

CURATED = {
    "Example — a dead listing (great before/after story)": 21004527,
    "Example — a healthy listing (strong performer)": 5094445,
}


@st.cache_resource(show_spinner="Loading Inside Airbnb Austin snapshot…")
def get_df():
    return load_listings(DEFAULT_DATA)


def sidebar():
    with st.sidebar:
        st.markdown("### STR Revenue Audit")
        st.caption("Austin, TX · Inside Airbnb snapshot 2026-09-17 (CC BY 4.0). "
                   "All revenue figures are ESTIMATES — method is printed on the PDF.")
        st.divider()
        provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
        key_present = bool(os.environ.get("GEMINI_API_KEY") if provider == "gemini"
                           else os.environ.get("GROQ_API_KEY"))
        st.markdown("**Audit summary writer**")
        if key_present:
            st.success(f"LLM: {provider} (key found in .env)")
        else:
            st.info(f"LLM: {provider} — no key in `.env`, using offline fallback summary "
                    f"(deterministic, no invented numbers).")
            st.caption("Copy `.env.example` to `.env` and add a free Gemini or Groq API key to enable LLM summaries.")
        st.divider()
        st.caption("Data attribution: Inside Airbnb (CC BY 4.0). Do not scrape Airbnb. "
                   "Photo counts are only available via manual entry/upload.")


DOT = {"pass": "🟢", "warn": "🟠", "fail": "🔴", "unknown": "⚪"}


def show_audit(audit: dict):
    t, n = audit["target"], audit["estimate"]["numbers"]
    st.subheader(t.get("name") or "Your listing")
    st.caption(f"{t.get('room_type')} · {t.get('bedrooms')}BR · {t.get('baths')} bath · "
               f"${t.get('price')}/night · {t.get('neighbourhood_cleansed')} · "
               f"{t.get('number_of_reviews')} reviews · comps: {audit['comps']['pool']} "
               f"(n={audit['comps']['n']})")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price gap/yr (A, ESTIMATE)", _money(n.get("est_annual_price_gap"), signed=True))
    c2.metric("vs comp median/yr (B, ESTIMATE)", _money(n.get("est_annual_ia_revenue_gap"), signed=True))
    c3.metric("Comp median price", _money(n.get("comp_median_price")))
    occ = n.get("comp_avg_occupancy")
    c4.metric("Comp avg occupancy", f"{occ:.0%}" if occ is not None else "n/a")

    # 2026-11-12: conservative range headline, or INSUFFICIENT DATA
    lo, hi = n.get("est_gap_low"), n.get("est_gap_high")
    if lo is None:  # older audits: derive from A and B
        gaps = [g for g in (n.get("est_annual_price_gap"), n.get("est_annual_ia_revenue_gap"))
                if isinstance(g, (int, float))]
        if gaps:
            lo, hi = min(gaps), max(gaps)
    comps_n = audit["comps"].get("n", 0) or 0
    prices = [r.get("price") for r in audit["comps"].get("table", [])
              if isinstance(r.get("price"), (int, float))]
    from str_audit.revenue import MAX_COMP_PRICE_CV, MIN_COMPS, price_cv
    cv = price_cv(prices) if prices else None
    too_thin = bool(n.get("insufficient_data")) or comps_n < MIN_COMPS or (cv is not None and cv > MAX_COMP_PRICE_CV)
    if too_thin:
        st.error("INSUFFICIENT DATA — the comp set is too thin or too dissimilar to quote an upside "
                 "figure. We do not guess.")
    elif lo is not None and hi is not None:
        st.info(f"**Conservative range (ESTIMATE, public data):** {_money(lo, signed=True)} → "
                f"{_money(hi, signed=True)} per year — price repriced only → full comp-median gap. "
                f"An estimate, not a guarantee.")

    left, right = st.columns([1.15, 1])
    with left:
        st.markdown("#### What the listing tells us")
        for s in audit["signals"]:
            st.markdown(f"{DOT.get(s['status'], '⚪')} **{s['key'].replace('_', ' ').title()}** — {s['summary']}")
        st.markdown("#### Top fixes")
        for i, fix in enumerate(audit["top_fixes"], 1):
            st.markdown(f"**{i}.** {fix}")
    with right:
        st.markdown("#### The short version")
        st.info(audit["llm_summary"])
        st.caption(f"Summary by: {audit.get('llm_provider_used', 'fallback')}")

    with st.expander("Comp set (top 12)"):
        comps_df = pd.DataFrame(audit["comps"]["table"])[
            ["rank", "neighbourhood_cleansed", "room_type", "bedrooms", "baths",
             "price", "availability_365", "number_of_reviews", "estimated_revenue_l365d"]]
        comps_df.columns = ["#", "Neighbourhood", "Room type", "Beds", "Baths",
                             "Price", "Avail 365d", "Reviews", "Est. rev (ESTIMATE)"]
        st.dataframe(comps_df, width="stretch", hide_index=True)

    with st.expander("How we calculated it (method & caveats)"):
        for line in audit["estimate"]["method"]:
            st.markdown(f"- {line}")
        for cav in audit["estimate"]["caveats"]:
            st.caption(f"⚠ {cav}")

    pdf = render_pdf(audit)
    lid = audit["listing_id"] if audit["listing_id"] is not None else "custom"
    st.download_button("⬇ Download one-page PDF", data=pdf,
                       file_name=f"audit_{lid}.pdf", mime="application/pdf",
                       type="primary")


def _provider_choice():
    return st.selectbox("Summary provider", ["auto (.env)", "gemini", "groq", "none (offline fallback)"],
                        index=0, help="'auto' reads LLM_PROVIDER from .env")


def _provider_arg(choice: str):
    return None if choice.startswith("auto") else (None if choice.startswith("none") else choice)


sidebar()
st.title("STR Revenue Audit")
st.caption("Compare one listing against its Austin comp pool — see the estimated revenue gap and the top fixes.")

tab1, tab2, tab3 = st.tabs(["🔍 Inside Airbnb listing", "✍️ Enter manually", "📄 Upload CSV/JSON"])

with tab1:
    pick = st.selectbox("Example listing", ["(custom id…)"] + list(CURATED), index=0)
    default_id = CURATED.get(pick, 21004527) if pick != "(custom id…)" else 21004527
    listing_id = st.number_input("Listing id", min_value=1, value=int(default_id), step=1)
    col1, col2, col3 = st.columns(3)
    k = col1.slider("Comps (k)", 8, 20, 12)
    photo_count = col2.number_input("Photo count (optional)", min_value=0, max_value=120, value=0,
                                    help="Public data has no photo count — enter it to unlock the photos signal. 0 = unknown.")
    provider = _provider_choice()
    if st.button("Run audit", type="primary", key="run_tab1"):
        df = get_df()
        with st.spinner("Building comps and audit…"):
            try:
                audit = run_audit(df, int(listing_id), k=int(k),
                                  photo_count=int(photo_count) or None,
                                  provider=_provider_arg(provider))
            except KeyError as exc:
                st.error(str(exc))
                st.stop()
        show_audit(audit)

with tab2:
    with st.form("manual"):
        st.markdown("##### Your listing")
        name = st.text_input("Listing name", "My SoCo 2BR")
        c1, c2, c3 = st.columns(3)
        price = c1.number_input("Nightly price ($)", min_value=10.0, value=150.0, step=5.0)
        room_type = c2.selectbox("Room type", ["Entire home/apt", "Private room", "Shared room"])
        hood = c3.text_input("Neighbourhood (Austin ZIP)", "78704")
        c4, c5, c6 = st.columns(3)
        bedrooms = c4.number_input("Bedrooms", min_value=0.0, max_value=10.0, value=1.0, step=0.5)
        beds = c5.number_input("Beds", min_value=0.0, max_value=20.0, value=1.0, step=0.5)
        baths = c6.number_input("Baths", min_value=0.0, max_value=10.0, value=1.0, step=0.5)
        c7, c8, c9 = st.columns(3)
        availability = c7.slider("Available nights / yr", 0, 365, 120,
                                 help="Nights blocked in your calendar — higher = fewer bookings expected")
        reviews = c8.number_input("Total reviews", min_value=0, value=12)
        rpm = c9.number_input("Reviews per month", min_value=0.0, value=0.4, step=0.1)
        last_review = st.date_input("Date of last review", value=pd.Timestamp("2026-08-01").date())
        photo_count2 = st.number_input("Photo count", min_value=0, max_value=120, value=6)
        description = st.text_area("Listing description", "Cozy 1BR near SoCo…", height=80)
        est_rev = st.number_input("Estimated annual revenue ($, optional — Inside Airbnb model)",
                                  min_value=0.0, value=0.0, step=1000.0,
                                  help="Leave 0 if unknown — ESTIMATE B will just note it's unavailable.")
        submitted = st.form_submit_button("Run audit", type="primary")
    if submitted:
        df = get_df()
        provider = st.selectbox("Summary provider", ["auto (.env)", "gemini", "groq", "none (offline fallback)"],
                                index=0, key="prov_manual")
        target = dict(name=name, price=price, room_type=room_type,
                      neighbourhood=hood, bedrooms=bedrooms, beds=beds, baths=baths,
                      availability_365=availability, number_of_reviews=int(reviews),
                      reviews_per_month=rpm, last_review=str(last_review),
                      description=description,
                      estimated_revenue_l365d=est_rev or None,
                      photo_count=None)
        with st.spinner("Building comps and audit…"):
            audit = run_audit_custom(df, target,
                                     photo_count=int(photo_count2) or None,
                                     provider=_provider_arg(provider))
        show_audit(audit)

with tab3:
    st.markdown("Upload a one-row **CSV** (headers) or **JSON** with keys like:")
    sample_csv = "name,price,room_type,neighbourhood,bedrooms,beds,baths,availability_365,number_of_reviews,reviews_per_month,last_review,description,photo_count\n\"My SoCo 2BR\",150,\"Entire home/apt\",78704,1,1,1,280,12,0.4,2026-08-01,\"Short cozy description here\",5\n"
    st.download_button("⬇ Sample CSV template", data=sample_csv, file_name="listing_sample.csv",
                       mime="text/csv")
    uploaded = st.file_uploader("Listing file", type=["csv", "json"])
    if uploaded is not None:
        try:
            raw = uploaded.read()
            if uploaded.name.lower().endswith(".json"):
                data = json.loads(raw)
                row = data[0] if isinstance(data, list) else data
            else:
                row = pd.read_csv(io.BytesIO(raw)).iloc[0].to_dict()
        except Exception as exc:
            st.error(f"Couldn't parse the file: {exc}")
            st.stop()

        def _get(*names, default=None):
            for nm in names:
                if nm in row and pd.notna(row[nm]):
                    return row[nm]
            return default

        target = dict(
            name=_get("name", default="Uploaded listing"),
            price=_get("price"),
            room_type=_get("room_type", default="Entire home/apt"),
            neighbourhood=_get("neighbourhood", "neighbourhood_cleansed", default="78704"),
            bedrooms=_get("bedrooms"), beds=_get("beds"), baths=_get("baths"),
            availability_365=_get("availability_365"),
            number_of_reviews=_get("number_of_reviews"),
            reviews_per_month=_get("reviews_per_month"),
            last_review=_get("last_review"),
            description=_get("description"),
            estimated_revenue_l365d=_get("estimated_revenue_l365d"),
        )
        photos = _get("photo_count", "photos")
        photo_count3 = st.number_input("Photo count (from your file if present)",
                                       min_value=0, max_value=120,
                                       value=int(float(photos)) if photos is not None else 0)
        provider = st.selectbox("Summary provider", ["auto (.env)", "gemini", "groq", "none (offline fallback)"],
                                index=0, key="prov_upload")
        if st.button("Run audit", type="primary", key="run_tab3"):
            if target["price"] is None:
                st.error("The file must include at least: name, price, room_type, neighbourhood, bedrooms, beds, baths.")
                st.stop()
            df = get_df()
            with st.spinner("Building comps and audit…"):
                audit = run_audit_custom(df, target,
                                         photo_count=int(photo_count3) or None,
                                         provider=_provider_arg(provider))
            show_audit(audit)
