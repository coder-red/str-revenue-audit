"""STR Revenue Audit — audit UI, imported by app.py (the unified dispatcher).
   Find   — paste an Airbnb link or listing id
   Enter  — type the listing details (unlocks the photo-count signal)
   Upload — one-row CSV/JSON; columns are matched forgivingly
"""

from __future__ import annotations

import io
import json

from dotenv import load_dotenv
import pandas as pd
import streamlit as st

load_dotenv()

from str_audit.audit import run_audit, run_audit_custom
from str_audit.cities import city, default_data, label, metro_line
from str_audit.data import load_listings
from str_audit.parse import parse_listing_id
from str_audit.report import _money, render_pdf
from str_audit.upload import map_uploaded_row



def render():
    _CITY = city()                     # STR_CITY env var switches metros; default Austin
    _SLUG, _METRO = _CITY["slug"], metro_line()

    CURATED = {
        "A dead listing (great before/after)": 21004527,
        "A healthy listing (strong performer)": 5094445,
    } if _SLUG == "austin" else {}


    @st.cache_resource(show_spinner=f"Loading {label()} snapshot…")
    def get_df():
        return load_listings(default_data())


    DOT = {"pass": "🟢", "warn": "🟠", "fail": "🔴", "unknown": "⚪"}


    def show_audit(audit: dict):
        t, n = audit["target"], audit["estimate"]["numbers"]
        st.subheader(t.get("name") or "Your listing")
        st.caption(f"{t.get('room_type')} · {t.get('bedrooms')}BR · {t.get('baths')} bath · "
                   f"${t.get('price')}/night · {t.get('neighbourhood_cleansed')} · "
                   f"{t.get('number_of_reviews')} reviews · {audit['comps']['pool']} comps (n={audit['comps']['n']})")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Price gap (A)/yr", _money(n.get("est_annual_price_gap"), signed=True))
        c2.metric("vs comps (B)/yr", _money(n.get("est_annual_ia_revenue_gap"), signed=True))
        c3.metric("Comp median price", _money(n.get("comp_median_price")))
        occ = n.get("comp_avg_occupancy")
        c4.metric("Comp occupancy", f"{occ:.0%}" if occ is not None else "n/a")

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
            st.markdown("#### What's wrong")
            for s in audit["signals"]:
                st.markdown(f"{DOT.get(s['status'], '⚪')} **{s['key'].replace('_', ' ').title()}** — {s['summary']}")
            st.markdown("#### Top fixes")
            for i, fix in enumerate(audit["top_fixes"], 1):
                st.markdown(f"**{i}.** {fix}")
        with right:
            st.markdown("#### The short version")
            st.info(audit["llm_summary"])

        with st.expander("Comps"):
            comps_df = pd.DataFrame(audit["comps"]["table"])[
                ["rank", "neighbourhood_cleansed", "room_type", "bedrooms", "baths",
                 "price", "availability_365", "number_of_reviews", "estimated_revenue_l365d"]]
            comps_df.columns = ["#", "Neighbourhood", "Room type", "Beds", "Baths",
                                 "Price", "Avail 365d", "Reviews", "Est. rev (ESTIMATE)"]
            st.dataframe(comps_df, width="stretch", hide_index=True)

        with st.expander("How we calculated it"):
            for line in audit["estimate"]["method"]:
                st.markdown(f"- {line}")
            for cav in audit["estimate"]["caveats"]:
                st.caption(f"⚠ {cav}")

        pdf = render_pdf(audit)
        lid = audit["listing_id"] if audit["listing_id"] is not None else "custom"
        st.download_button("⬇ Download the one-page PDF", data=pdf,
                           file_name=f"audit_{lid}.pdf", mime="application/pdf",
                           type="primary")
        st.caption(f"Inside Airbnb · {label()} · {_CITY['snapshot']} · CC BY 4.0")


    def _provider_choice():
        return st.selectbox("Summary", ["auto", "gemini", "groq", "offline"], index=0)


    def _provider_arg(choice: str):
        return None if choice in ("auto", "offline") else choice


    st.markdown("<h1 style='font-family:Georgia,serif;color:#10483c;margin-bottom:0'>STR Revenue Audit</h1>",
                unsafe_allow_html=True)
    st.caption(f"{_METRO} · every revenue figure an ESTIMATE")

    tab1, tab2, tab3 = st.tabs(["🔍 Find", "✍️ Enter", "📄 Upload"])

    with tab1:
        choice = st.selectbox("Example", ["Paste your own link or ID"] + list(CURATED),
                              label_visibility="collapsed")
        raw = st.text_input("Paste an Airbnb link or listing ID",
                            value=str(CURATED[choice]) if choice in CURATED else "",
                            placeholder="https://www.airbnb.com/rooms/21004527  — or just the number",
                            key=f"lid_{choice}",
                            label_visibility="collapsed")
        col1, col2, col3 = st.columns(3)
        k = col1.slider("Comps", 8, 20, 12, label_visibility="collapsed")
        photo_count = col2.number_input("Photos (optional)", min_value=0, max_value=120, value=0,
                                        label_visibility="collapsed")
        provider = _provider_choice()
        if st.button("Run audit", type="primary", key="run_tab1"):
            listing_id = parse_listing_id(raw)
            if listing_id is None:
                st.error("Couldn't find a listing ID in that. Paste an Airbnb link like "
                         "airbnb.com/rooms/21004527 — or just the number.")
                st.stop()
            df = get_df()
            with st.spinner("Building comps and audit…"):
                try:
                    audit = run_audit(df, int(listing_id), k=int(k),
                                      photo_count=int(photo_count) or None,
                                      provider=_provider_arg(provider))
                except KeyError as exc:
                    st.error(f"{exc} — this deployment covers {label()} only.")
                    st.stop()
            show_audit(audit)

    with tab2:
        with st.form("manual"):
            name = st.text_input("Name", "My SoCo 2BR")
            c1, c2, c3 = st.columns(3)
            price = c1.number_input("Price ($)", min_value=10.0, value=150.0, step=5.0)
            room_type = c2.selectbox("Room type", ["Entire home/apt", "Private room", "Shared room"])
            hood = c3.text_input("ZIP", "78704")
            c4, c5, c6 = st.columns(3)
            bedrooms = c4.number_input("Bedrooms", min_value=0.0, max_value=10.0, value=1.0, step=0.5)
            beds = c5.number_input("Beds", min_value=0.0, max_value=20.0, value=1.0, step=0.5)
            baths = c6.number_input("Baths", min_value=0.0, max_value=10.0, value=1.0, step=0.5)
            c7, c8, c9 = st.columns(3)
            availability = c7.slider("Avail/365", 0, 365, 120)
            reviews = c8.number_input("Reviews", min_value=0, value=12)
            rpm = c9.number_input("Reviews/mo", min_value=0.0, value=0.4, step=0.1)
            last_review = st.date_input("Last review", value=pd.Timestamp("2026-08-01").date())
            photo_count2 = st.number_input("Photos", min_value=0, max_value=120, value=6)
            description = st.text_area("Description", "Cozy 1BR near SoCo…", height=80)
            est_rev = st.number_input("Est. annual revenue (optional)", min_value=0.0, value=0.0, step=1000.0)
            submitted = st.form_submit_button("Run audit", type="primary")
        if submitted:
            df = get_df()
            provider = st.selectbox("Summary", ["auto", "gemini", "groq", "offline"], index=0, key="prov_manual")
            target = dict(name=name, price=price, room_type=room_type,
                          neighbourhood=hood, bedrooms=bedrooms, beds=beds, baths=baths,
                          availability_365=availability, number_of_reviews=int(reviews),
                          reviews_per_month=rpm, last_review=str(last_review),
                          description=description,
                          estimated_revenue_l365d=est_rev or None,
                          property_type="", minimum_nights=None)
            with st.spinner("Building comps and audit…"):
                audit = run_audit_custom(df, target,
                                         photo_count=int(photo_count2) or None,
                                         provider=_provider_arg(provider))
            show_audit(audit)

    SAMPLE_CSV = ('name,price,room_type,neighbourhood,bedrooms,beds,baths,'
                  'availability_365,number_of_reviews,reviews_per_month,last_review,description,photo_count\n'
                  '"My SoCo 2BR",150,"Entire home/apt",78704,1,1,1,280,12,0.4,2026-08-01,"Short cozy description",5\n')


    @st.cache_data(show_spinner=False)
    def _cached_custom_audit(target_json: str, photo_count: int | None, provider: str | None):
        target = json.loads(target_json)
        return run_audit_custom(get_df(), target, photo_count=photo_count, provider=provider)


    with tab3:
        st.download_button("⬇ Sample CSV", data=SAMPLE_CSV, file_name="listing_sample.csv", mime="text/csv")
        uploaded = st.file_uploader("One listing — CSV or JSON (columns auto-matched)",
                                    type=["csv", "json"], label_visibility="collapsed")
        if uploaded is not None:
            try:
                raw_bytes = uploaded.read()
                if uploaded.name.lower().endswith(".json"):
                    data = json.loads(raw_bytes)
                    row = data[0] if isinstance(data, list) else data
                    if not isinstance(row, dict):
                        raise ValueError("JSON must be one object (or a list containing one)")
                else:
                    row = pd.read_csv(io.BytesIO(raw_bytes)).iloc[0].to_dict()
            except Exception as exc:
                st.error(f"Couldn't read that file: {exc}")
                st.stop()

            parsed = map_uploaded_row(row)
            target, photos = parsed["target"], parsed["photo_count"]
            if parsed["mapping"]:
                st.caption("Matched: " + ", ".join(f"{c} ← {src}" for c, src in parsed["mapping"].items()))

            if parsed["missing"]:
                cols = ", ".join(parsed["columns"]) or "(none)"
                st.error(f"No price column found. Your columns: {cols}. Rename one of them "
                         f"`price` (or `nightly_price` / `rate`) and re-upload.")
                st.stop()

            photo_count3 = st.number_input("Photos", min_value=0, max_value=120,
                                           value=photos or 0, key="photos_upload")
            provider = st.selectbox("Summary", ["auto", "gemini", "groq", "offline"],
                                    index=0, key="prov_upload")
            with st.spinner("Building comps and audit…"):
                audit = _cached_custom_audit(json.dumps(target, default=str),
                                             int(photo_count3) or None,
                                             _provider_arg(provider))
            show_audit(audit)
