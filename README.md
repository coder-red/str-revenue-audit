# STR Listing Revenue Audit

Take one short-term rental listing in a metro, compare it to local listings from
[Inside Airbnb](https://insideairbnb.com/) (free, public, CC BY 4.0), and produce
a one-page PDF showing the estimated revenue gap and the top fixes.
Audience: non-technical property managers. **The PDF is the product.**

Every revenue number in the report is labelled **ESTIMATE** with the calculation shown.

## Status

- [x] Phase 0 — Research & reuse plan (approved 2026-11-11)
- [x] Phase 1 — Pipeline: load one metro, build a comps table for a single listing
- [x] Phase 2 — Audit signals + revenue-gap estimate + LLM summary (Gemini/Groq free tier, offline fallback)
- [x] Phase 3 — One-page PDF (xhtml2pdf) + Streamlit app (look up / enter / upload a listing, download PDF)

## Data source & attribution

Inside Airbnb, "Austin, Texas, United States" snapshot dated **2026-09-17**,
licensed CC BY 4.0. If you use this project's outputs, credit **Inside Airbnb**
as the source (CC BY 4.0 requires it). No Airbnb scraping is performed or permitted here.

We download three files (see `scripts/download_data.py`):

| File | Size | Used for |
|---|---|---|
| `listings.csv.gz` | ~6.8 MB | listing facts: price, room type, beds, reviews, location |
| `calendar.csv.gz` | ~9.5 MB | availability/price over next ~12 months |
| `reviews.csv.gz` | ~61 MB | review recency & volume signals (Phase 2) |

## Setup

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python scripts/download_data.py                    # fetches Austin 2026-09-17 into data/
```

## Phase 1 — comps table for one listing

```bash
# comps for a specific listing id, written to outputs/
python -m str_audit.comps --listing-id 12345678 --k 12

# deterministic demo on a sample listing
python -m str_audit.comps --demo
```

`str_audit.comps` prints the table to stdout and writes `outputs/comps.csv`.

## Phase 2 — audit + revenue gap + summary

```bash
python -m str_audit.audit --listing-id 21004527   # full audit, prints report + writes outputs/audit_<id>.json
```

Signals (all our own logic, thresholds in `str_audit/signals.py`):
weak photos (user-entered count only; public data has none → reported `unknown`),
thin description (<60 words), review recency (stale after 180 days; 0 reviews = fail),
price vs comp median (>10% off = flag).

Revenue numbers — **both are ESTIMATES with formulas printed**:
- **A, price positioning:** `(comp_median_price − target_price) × comp_avg_occupancy × 365`
- **B, Inside Airbnb model:** `median(comp estimated_revenue_l365d, active comps only) − target's`

### LLM summary (optional — works without keys)

The summary runs through Gemini or Groq free tier, selected at runtime:

```bash
cp .env.example .env      # Windows: copy .env.example .env
# edit .env: GEMINI_API_KEY=...  or  GROQ_API_KEY=...  and LLM_PROVIDER=gemini|groq
python -m str_audit.audit --listing-id 21004527 --provider gemini
```

With no keys (or `--provider none`), a deterministic fallback summary is produced
from the audit dict — no invented numbers, works offline. Prompt lives in
`str_audit/audit_prompt.py`; every call is wrapped so any API failure degrades
to the fallback instead of crashing.

## Phase 3 — one-page PDF + Streamlit app

```bash
# generate the PDF from the CLI (no Streamlit needed)
python -m str_audit.report --listing-id 21004527
#   -> outputs/audit_21004527.pdf

# run the app (upload / enter / look up a listing, download the PDF)
streamlit run app.py
```

The app has three entry points: **Inside Airbnb listing** (by id, e.g. the curated
`21004527`), **Enter manually** (feeds the photo-count signal — public data has none),
and **Upload CSV/JSON** (same fields as the manual form; sample template downloadable in-app).

### Branding
The PDF header and app title say **"STR Revenue Audit"** — rename in
`templates/audit_report.html` (`.band-title`), `app.py` (`st.set_page_config`, `st.title`),
and `.streamlit/config.toml`. PDF colours: `#10483c` green, `#d97706` amber, `#f4f1ea` bone.

### PDF engine note
WeasyPrint (Phase 0 pick) needs GTK/Pango system libraries this Windows machine lacks —
no winget/package manager available either. **xhtml2pdf** (pre-approved fallback, Apache-2.0)
is used instead; the Jinja2 template is table-based CSS written to port back to WeasyPrint
on Linux/macOS unchanged. See `CREDITS.md`.

## File map (every file, and why it exists)

| File | Why it exists |
|---|---|
| `README.md` | This file: what/why/how, data attribution, commands. |
| `CREDITS.md` | Rule 2 compliance: every reused repo/lib, its license, what we took. |
| `.gitignore` | Keeps `.env` secrets, `data/`, and `outputs/` out of git. |
| `.env.example` | Template for Phase 2 LLM keys (Gemini/Groq). Real values live in `.env`, never committed. |
| `requirements.txt` | Minimal pinned-ish deps. Phase 1: pandas, duckdb, scikit-learn. |
| `scripts/download_data.py` | Fetches the Austin 2026-09-17 Inside Airbnb files into `data/` (idempotent, stdlib only). |
| `app.py` | Streamlit app — three ways in (look up / enter / upload), audit view, PDF download button. |
| `templates/audit_report.html` | The one-page PDF: Jinja2 + table CSS (xhtml2pdf-safe). All ESTIMATE labels, method and attribution render from data; branding is here (`.band-title`). |
| `str_audit/report.py` | Audit dict → styled HTML → PDF bytes. Owns the Plotly→kaleido chart (PNG base64; silently omitted if kaleido can't run) and the Jinja view model. |
| `assets/fonts/` | DejaVu TTFs embedded in the PDF (Bitstream Vera license — see `assets/fonts/README.txt`). |
| `.streamlit/config.toml` | App theme: deep green primary, warm off-white background, no usage stats. |
| `requirements-dev.txt` | Dev tools only: pytest, pypdf, pypdfium2. |
| `str_audit/__init__.py` | Package marker + version. |
| `str_audit/data.py` | Loads `listings.csv.gz`, normalises the messy fields (`$1,234` → float, `bathrooms_text` → number, t/f → bool). All Inside Airbnb weirdness is handled here, once. |
| `str_audit/comps.py` | Builds the comps table for one listing: same room type, bed-band, neighbourhood (falls back to radius), then k-nearest on scaled [price, beds, bedrooms, baths]. |
| `str_audit/signals.py` | Our audit logic: photo/description/review-recency/price-vs-comps signals with thresholds as named constants; ranks top fixes by severity. |
| `str_audit/revenue.py` | The two ESTIMATE figures (price-positioning gap; Inside Airbnb model gap over active comps) with formulas and caveats returned alongside. |
| `str_audit/audit_prompt.py` | The audit-summary prompt — ours. Non-technical tone, no invented numbers, ESTIMATE language baked in. |
| `str_audit/llm.py` | Thin Gemini/Groq wrapper (free tiers, keys from `.env`). Any failure degrades to a deterministic plain-text fallback built from the same audit dict. |
| `str_audit/audit.py` | Phase 2 orchestrator: listing → comps → signals → estimate → summary; prints the report and writes `outputs/audit_<id>.json`. (Phase 3 renders the same dict to PDF.) |
| `tests/` | pytest smoke tests on synthetic data — no network. `python -m pytest tests/ -v` |
| `outputs/` | Generated artefacts (gitignored). |

## License

This project's own code: MIT (see `CREDITS.md` for third-party licenses).
Data: Inside Airbnb, CC BY 4.0.
