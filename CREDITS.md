# CREDITS — third-party code, data & what we took

Rule: only MIT / Apache-2.0 / BSD-licensed material is reused. Anything GPL,
LGPL, unlicensed, or "license unclear" was **not** reused — see the bottom section.
Last updated: 2026-11-11 (Phases 1–3).

## Reused / depended on (code)

| Project | License | What we took / use it for | Notes |
|---|---|---|---|
| **pandas** 3.0.3 | BSD-3-Clause | DataFrames; all table manipulation | Core dependency |
| **DuckDB** 2.0.0 | MIT | Zero-copy SQL over `.csv.gz`; column selection on load | Core dependency |
| **scikit-learn** 1.9.0 | BSD-3-Clause | `NearestNeighbors` for comp selection; `StandardScaler` | Core dependency |
| **Streamlit** (Phase 3) | Apache-2.0 | App shell: listings input, comps view, PDF download | Approved in Phase 0 |
| **WeasyPrint** (Phase 3) | BSD-3-Clause | HTML+CSS → one-page PDF | Approved in Phase 0 |
| **Jinja2** (Phase 3) | BSD-3-Clause | The report HTML template | Approved in Phase 0 |
| **plotly** + **kaleido** (Phase 3) | MIT / MIT | Comp chart rendered to PNG for the PDF | Approved in Phase 0 |
| **geopy** (if used) | MIT | Distance/geo utilities | Optional |
| **python-dotenv** (Phase 2) | BSD-family | Load `.env` secrets | Approved in Phase 0 |
| **google-genai** (Phase 2) | Apache-2.0 | Gemini free tier for audit summary | Approved in Phase 0 |
| **groq** (Phase 2) | Apache-2.0 | Groq free tier for audit summary | Approved in Phase 0 |

## Reused (pattern, not code)

| Project | License | What we took |
|---|---|---|
| **streamlit/example-app-pdf-report** | Apache-2.0 | The pattern: Streamlit app → generate PDF → `st.download_button`. No code copied; rewritten for this product. |

## Data

| Source | License | What we used |
|---|---|---|
| **Inside Airbnb** — Austin, TX, 2026-09-17 snapshot | CC BY 4.0 | `listings.csv.gz`, `calendar.csv.gz`, `reviews.csv.gz`. Attribution shown in README and on the PDF footer. |

## Reviewed but NOT reused (flagged)

| Project | Problem | Decision |
|---|---|---|
| `Kozea/WeasyPrint` | none — fine, see above | Reused (Phase 3) |
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

- `str_audit/` — Inside Airbnb field normalisation, comp-matching rules, (Phase 2)
  audit signals: weak photos/description, review recency, price vs neighbourhood median,
  revenue-gap estimate, and the audit-summary prompt. MIT.
