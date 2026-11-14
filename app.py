"""STR Revenue Audit + Owner Lead Finder — one app, two modes.

Run:  streamlit run app.py            # defaults to the Revenue Audit (LANDING_MODE=audit)
      LANDING_MODE=leads streamlit run app.py

Mode switch: the slim brand bar has two plain links — the same code, same DB, two lanes.
"""

from __future__ import annotations

import os

import streamlit as st

# One page-config call, at the top of the unified app.
st.set_page_config(page_title="STR Revenue Audit", page_icon="🏠", layout="wide")

_LANDING = os.environ.get("LANDING_MODE", "audit").strip().lower()
_mode = st.query_params.get("mode", _LANDING).strip().lower()
MODE = "leads" if _mode == "leads" else "audit"

_CHROME = """<style>
#MainMenu, footer, header[data-testid="stHeader"],
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSkipLink"],
a[href^="#"]
{ display: none !important; }
.block-container { padding-top: 0.6rem; max-width: 1100px; }
</style>"""
_CHROME_AUDIT = """<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
</style>"""
st.markdown(_CHROME + ("" if MODE == "leads" else _CHROME_AUDIT), unsafe_allow_html=True)

_mode_link = lambda m, label, active: (
    f'<a href="?mode={m}" style="font-family:Arial,sans-serif;font-size:12.5px;font-weight:{"bold" if active else "normal"};'
    f'color:{"#10483c" if active else "#7c7a70"};text-decoration:none;padding:2px 4px;'
    f'border-bottom:2px solid {"#d97706" if active else "transparent"}">{label}</a>')
st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:center;
            padding:2px 2px 6px 2px;border-bottom:1px solid #e3e0d7;margin-bottom:6px">
  <div style="font-family:Georgia,serif;color:#10483c;font-size:15px;letter-spacing:3px;font-weight:bold">
    STR&nbsp;REVENUE&nbsp;AUDIT
  </div>
  <div style="display:flex;gap:10px;align-items:center">
    {_mode_link("audit", "Revenue audit", MODE == "audit")}
    <span style="color:#d8d5cc">|</span>
    {_mode_link("leads", "Owner lead finder", MODE == "leads")}
  </div>
</div>""", unsafe_allow_html=True)

if MODE == "leads":
    from leads_ui import render as _render_leads
    _render_leads()
else:
    from audit_ui import render as _render_audit
    _render_audit()
