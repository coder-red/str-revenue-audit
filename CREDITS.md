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

- `str_audit/` — Inside Airbnb field normalisation, comp-matching rules, (Phase 2)
  audit signals: weak photos/description, review recency, price vs neighbourhood median,
  revenue-gap estimate, and the audit-summary prompt. MIT.
