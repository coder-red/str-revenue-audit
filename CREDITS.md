# CREDITS — third-party code, data & what we took

Rule: only MIT / Apache-2.0 / BSD-licensed material is reused. Anything GPL,
LGPL, unlicensed, or "license unclear" was **not** reused — see the bottom section.
Last updated: 2026-11-12 (Phases 1–4; STR Owner Lead Finder).

## Reused / depended on (code)

| Project | License | What we took / use it for | Notes |
|---|---|---|---|
| **pandas** 3.0.3 | BSD-3-Clause | DataFrames; all table manipulation | Core dependency |
| **DuckDB** 2.0.0 | MIT | Zero-copy SQL over `.csv.gz`; column selection on load | Core dependency |
| **scikit-learn** 1.9.0 | BSD-3-Clause | `NearestNeighbors` for comp selection; `StandardScaler` | Core dependency |
| **Streamlit** 1.x | Apache-2.0 | App shell: sidebar, tabs, `st.download_button` for the PDF | Phase 3 |
| **xhtml2pdf** 0.2.x | Apache-2.0 | HTML+CSS → one-page PDF (**promoted from fallback**) | Phase 3. See note below |
| **Jinja2** 3.x | BSD-3-Clause | The report HTML template | Phase 3 |
| **plotly** + **kaleido** | MIT / MIT | Chart rendered to PNG → base64 → embedded in the PDF | Chart is decoration; PDF renders without it |
| **python-dotenv** | BSD-family | Load `.env` secrets | Phase 2 |
| **google-genai** | Apache-2.0 | Gemini free tier for audit summary | Phase 2 |
| **groq** | Apache-2.0 | Groq free tier for audit summary | Phase 2 |
| **DejaVu fonts** (bundled in `assets/fonts/`) | Bitstream Vera (permissive, notice retained) | Typeface embedded in the PDF | See `assets/fonts/README.txt` |

**PDF engine note:** WeasyPrint (approved in Phase 0) cannot run on this Windows
machine — it needs GTK/Pango system libraries and no package manager here provides
them. We fell back to **xhtml2pdf**, the pre-approved fallback option. The design
(`templates/audit_report.html`) is deliberately table-based CSS so it ports back to
WeasyPrint unchanged on Linux/macOS. Both engines are reused, not copied.

## Reused (pattern, not code)

| Project | License | What we took |
|---|---|---|
| **streamlit/example-app-pdf-report** | Apache-2.0 | The pattern: Streamlit app → generate PDF → `st.download_button`. No code copied; rewritten for this product. |

## STR Owner Lead Finder (Phases 1–4) — what we reused, took, and rejected

Reused unchanged: `str_audit` package (audit, comps, signals, revenue, report, llm),
Jinja2 (BSD-3), Streamlit (Apache-2.0), DuckDB (MIT), scikit-learn (BSD-3), pandas (BSD-3),
`sqlite3` stdlib, `csv`/`json` stdlib. **No new runtime dependencies were added.**
`str_audit/llm.py` gained one public function (`generate_text`) and an optional `system`
parameter; it also now passes the system prompt to Gemini as well (documented in git history).

Round 2 (2026-11-12) added, with **no new dependencies**: score v2.0 (re-weighted toward
small self-managing owners; agency cutoff configurable), conservative-range/INSUFFICIENT-DATA
revenue headline, manual contact-research fields + CSV export + found-rate stat, anonymized
`docs/sample_audit.pdf`, and re-rendered public screenshots (identity removed). Web research
(site/, docs/) reuses nothing beyond the previous phase's assets.

| Option considered | License | Decision |
|---|---|---|
| Streamlit `st.data_editor` (built-in) | Apache-2.0 | Used only via built-ins (`st.tabs`, `st.selectbox`, `st.text_area`, `st.download_button`) |
| `streamlit-aggrid` 1.2.1.post2 (wraps ag-grid Community) | MIT | Evaluated, **not used** — built-ins suffice |
| MJML (`mjmlio/mjml`, npm 5.4.1, pushed 2026-11-10) | MIT | Rejected — Node toolchain; LLM drafts stay plain-text |
| React Email (`resend/react-email`, ~20k stars) | MIT | Rejected — Node/TS, wrong stack |
| Mautic | GPL / NOASSERTION | Excluded by license rule |
| `mjml-python` 1.4.2 | No license | Excluded by license rule |
| `premailer` | PSF license (outside allowed set), stale since 2021 | Excluded |
| `email-validator` | Unlicense | Excluded by license rule |
| `PyCaret` 3.3.2 | MIT | Rejected — no conversion labels; kills explainability |
| Lead-scoring repos found on GitHub (case-study notebooks; `Astoriel/LeadGenius`; `buildingopen/opengtm` — MIT but heavy B2B-SaaS) | MIT / none | None reused; the lead score is custom (rule 7) |
| Streamlit approval-queue POC repos (`lat35n-hrt/streamlit_approval_workflow_poc`, `kajarenc/human-in-the-loop-streamlit`) | **No license** | Reference only; never copied |
| Our own new code: `str_leads/` (score, pitch, store, data, audit_bridge), `leadfinder_app.py`, `scripts/score_leads.py` | MIT | Ours |

## Dev-only tools (not shipped)

`pytest` (tests), `pypdf` + `pypdfium2` (PDF text/raster checks during development),
`matplotlib` (one-off: source of the DejaVu TTFs bundled in `assets/fonts/`).

## Data

| Source | License | What we used |
|---|---|---|
| **Inside Airbnb** — Austin, TX, 2026-09-17 snapshot | CC BY 4.0 | `listings.csv.gz`, `calendar.csv.gz`, `reviews.csv.gz`. Attribution shown in README and on the PDF footer. |

## Reviewed but NOT reused (flagged)

| Project | Problem | Decision |
|---|---|---|
| `Kozea/WeasyPrint` | BSD-3, but requires GTK/Pango **system** libraries absent on this Windows machine | **Not usable here**; xhtml2pdf (pre-approved fallback) used instead. Kept as the future Linux/macOS option — template is written to port cleanly. |
| **fpdf2** | LGPL-3.0-only | **Excluded** by license rule |
| **xhtml2pdf** | OK (Apache-2.0) but weaker CSS | Kept as fallback only, not a dependency yet |
| **python-pdfkit + wkhtmltopdf** | Wrapper MIT, but wkhtmltopdf is LGPL and unmaintained | **Excluded** |
| **reportlab** | BSD-like (ok), but far too low-level for a one-page styled doc | Skipped; WeasyPrint chosen |
| `JuanCampbsi/analytics_engineering_airbnb` | **No license** (all rights reserved) | Ideas only; no code copied |
| `UPGo-McGill/strr` | R package; license field blank in DESCRIPTION | Reference only; no code copied |
| `KalyanM45/End-to-End-Airbnb-Price-Prediction` | **No license** | Feature-engineering ideas only; no code copied |
| `samuelklam/airbnb-pricing-prediction` | **No license** | Not used |
| `MarinaSchluter/Inside-Airbnb_Hawaii` | **No license** | Layout inspiration only; no code copied |
| `Kallistratis/thessaloniki-airbnb-analysis`, `jforward1/InsideAirbnb-Analysis`, and ~all other Inside Airbnb GitHub repos found | **No license** | Not used |

## Our own code (not third-party)

- `str_audit/` — Inside Airbnb field normalisation, comp-matching rules,
  audit signals, revenue-gap estimate, audit-summary prompt.
- `str_leads/` — host-level aggregation, lead score, pitch drafting, SQLite store.
- `app.py`, `audit_ui.py`, `leadfinder_app.py`, `scripts/score_leads.py` — unified app shell, audit UI as a component, review queue + pipeline driver.

All rights reserved — source visible on GitHub for inspection; ask before reuse.
