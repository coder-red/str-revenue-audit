# STR Listing Revenue Audit

Take one short-term rental listing in a metro, compare it to local listings from
[Inside Airbnb](https://insideairbnb.com/) (free, public, CC BY 4.0), and produce
a one-page PDF showing the estimated revenue gap and the top fixes.
Audience: non-technical property managers. **The PDF is the product.**

Every revenue number in the report is labelled **ESTIMATE** with the calculation shown.

## Status

- [x] Phase 0 — Research & reuse plan (approved 2026-11-11)
- [x] Phase 1 — Pipeline: load one metro, build a comps table for a single listing
- [ ] Phase 2 — Audit signals + revenue-gap estimate + LLM summary (Gemini/Groq free tier)
- [ ] Phase 3 — One-page PDF (WeasyPrint) + Streamlit upload/enter page

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

## File map (every file, and why it exists)

| File | Why it exists |
|---|---|
| `README.md` | This file: what/why/how, data attribution, commands. |
| `CREDITS.md` | Rule 2 compliance: every reused repo/lib, its license, what we took. |
| `.gitignore` | Keeps `.env` secrets, `data/`, and `outputs/` out of git. |
| `.env.example` | Template for Phase 2 LLM keys (Gemini/Groq). Real values live in `.env`, never committed. |
| `requirements.txt` | Minimal pinned-ish deps. Phase 1: pandas, duckdb, scikit-learn. |
| `scripts/download_data.py` | Fetches the Austin 2026-09-17 Inside Airbnb files into `data/` (idempotent, stdlib only). |
| `str_audit/__init__.py` | Package marker + version. |
| `str_audit/data.py` | Loads `listings.csv.gz`, normalises the messy fields (`$1,234` → float, `bathrooms_text` → number, t/f → bool). All Inside Airbnb weirdness is handled here, once. |
| `str_audit/comps.py` | Builds the comps table for one listing: same room type, bed-band, neighbourhood (falls back to radius), then k-nearest on scaled [price, beds, bedrooms, baths]. |
| `tests/test_comps.py` | Smoke tests on a tiny synthetic DataFrame — no network needed. |
| `outputs/` | Generated artefacts (gitignored). |

## License

This project's own code: MIT (see `CREDITS.md` for third-party licenses).
Data: Inside Airbnb, CC BY 4.0.
