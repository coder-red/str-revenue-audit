# Phase 0 — Research & reuse plan: STR Owner Lead Finder

Status: **awaiting approval. No code has been written.**
Date: 2026-11-12 · Repo: `str-revenue-audit` · Data: Inside Airbnb Austin TX, snapshot 2026-09-17 (CC BY 4.0)

Rule 1 compliance: everything below was researched from public sources. Rule 2: only MIT / Apache-2.0 / BSD-family material is proposed for reuse; everything else is flagged at the bottom. Rule 3: no Airbnb scraping, no paid data (AirDNA etc.). Rule 5: Python, pandas/DuckDB, SQLite (default) or Supabase free tier, Streamlit, Gemini/Groq free tier. Rule 6: no auto-send — approval queue + CSV export only. Rule 7: custom code is limited to the lead score, the pitch-drafting prompt, and dedupe/status tracking; the Listing Revenue Audit is imported and reused, not rewritten.

## 1. What the data supports (measured, not guessed)

Inside Airbnb Austin 2026-09-17 `listings.csv.gz`:

| Metric | Value |
|---|---|
| Listings (rows) | 11,111 |
| Distinct hosts | 5,507 |
| Hosts with ≥ 2 listings | 1,416 |
| Hosts with ≥ 3 listings | 730 |

Host-level fields present (not loaded by `str_audit/data.py` today, but available):
`host_id`, `host_name`, `host_since`, `host_location`, `host_about`, `host_url`, `host_profile_url`,
`host_response_rate`, `host_acceptance_rate`, `host_is_superhost`, `host_identity_verified`,
`host_listings_count`, `host_total_listings_count`, `calculated_host_listings_count`,
`calculated_host_listings_count_entire_homes/private_rooms/shared_rooms`.

Per-listing signals (already normalised in `str_audit/data.py` + `signals.py`):
review recency (`last_review`), `number_of_reviews`, `reviews_per_month`, `price` vs neighbourhood/comp
median, thin `description`, `estimated_revenue_l365d`, `availability_365`, `instant_bookable`,
`review_scores_rating`.

Fit: strong. A transparent, rule-based host-level lead score is very buildable from this alone.

## 2. Options per category (2–3 each, with license / last-updated / fit)

### (a) Lead scoring / ranking

| # | Option | License | Last updated | Fit |
|---|---|---|---|---|
| 1 | **Rule-based weighted score in pandas/DuckDB — custom code (recommended)** | Our code (MIT) | n/a | Perfect fit for rule 7, which reserves the score for custom code. Transparent, explainable to non-technical property managers, works on 11k rows instantly. Weights live in named constants next to thresholds (same pattern as `str_audit/signals.py`). |
| 2 | **scikit-learn — already a dependency** (BSD-3-Clause) | BSD-3-Clause | 1.9.x, active | Useable for percentile-ranking features (e.g. min-max normalise) and, later, a calibrated model **if** conversion labels are ever collected. Not a scorer out of the box; overkill as a "library solution". |
| 3 | **PyCaret 3.3.2** (MIT, released 2024-04-28, low activity since) | MIT | 2024-04-28 | Rejected. Needs labelled conversion data (we have none), pulls a large dependency tree, and turns an explainable heuristic into a black box. Not recommended. |

Rejected/flagged: upstream "lead-scoring" repos found on GitHub (`olivierzach/tricentis-lead-scoring` — case-study notebook, unlicensed; `Astoriel/LeadGenius` — no license API entry, flagged; `buildingopen/opengtm` — MIT, last push 2026-04, but it is a heavy B2B-SaaS Clay-competitor targeting ICP scoring, wrong domain and unnecessary). **Conclusion: no maintained, permissively licensed, off-the-shelf scorer fits; the score is custom by design.** Ranking output = sorted table with per-signal subscores + reasons.

### (b) Review-and-approve UI in Streamlit (data editor / approval queue)

| # | Option | License | Last updated | Fit |
|---|---|---|---|---|
| 1 | **Streamlit built-ins: `st.data_editor` + `st.session_state` + `st.form` (recommended)** | Apache-2.0 (Streamlit) | 1.67+, active (repo pushed 2026-11-12) | Zero new dependencies, exactly the pattern in Streamlit docs, consistent with `app.py` in this repo. Statuses as a column; approve/edit/reject buttons; CSV export via `st.download_button` (same pattern as the PDF download). |
| 2 | **`streamlit-aggrid` 1.2.1.post2** (wraps ag-grid Community Edition, MIT) | MIT | Release 2025-12-29; active | Optional upgrade if the queue outgrows `st.data_editor`: checkbox selection, paging, row detail pane. One extra dependency; only adopted if needed. ag-grid Community is MIT. |
| 3 | **Pattern-only reuse from `streamlit/example-app-pdf-report`** | Apache-2.0 | n/a (pattern already credited) | Same pattern Project 1 credited: app → generate → `st.download_button`. We borrow the pattern, copy no code. The standalone approval-queue POC repos found (`lat35n-hrt/streamlit_approval_workflow_poc`, `kajarenc/human-in-the-loop-streamlit`) have **no license** → reference only, never copied. |

### (c) Email draft templating

| # | Option | License | Last updated | Fit |
|---|---|---|---|---|
| 1 | **Jinja2 + stdlib `email.message.EmailMessage` (recommended)** | BSD-3-Clause / PSF-stdlib | 3.1.6, released 2025-03-05, active | Already in this repo (renders the PDF template). Strict variable allow-list from the audit dict; plain-text-first drafts (simplest CAN-SPAM compliance) with optional minimal HTML alternative. Best fit for rule 8's "draft only from provided data". |
| 2 | **MJML via npm (`mjmlio/mjml`)** | MIT | Pushed 2026-11-10; npm 5.4.1, 2026-10 | Great responsive HTML emails, but requires a Node toolchain and the **Python** wrapper (`mjml-python` 1.4.2) has no license → flagged. Rejected for this Windows/Python stack. |
| 3 | **React Email (`resend/react-email`)** | MIT | Pushed 2026-11-11; ~20k stars | Rejected: Node/TypeScript UI library, wrong stack. (Mautic — the obvious "full email platform" — is GPL/NOASSERTION → excluded by rule 2. `premailer` — PSF license, unmaintained since 2021 → flagged, skipped.) |

LLM role: the model only fills a fixed allow-list of slots (host name, N listings, audit-quoted estimate labelled ESTIMATE, top fix, sender details, opt-out). Deterministic fallback text when no LLM key, mirroring `str_audit/llm.py`. **No invented numbers — enforced by construction (variables) + prompt + human review.**

### (d) Free contact-discovery methods — what realistically exists, and the limits

No library exists for "find the owner's email" that is both free and license/ToS-clean. What exists is a small set of *manual public-record lookups*. Honest limits stated up front:

| Method | Cost | What it yields | Limits |
|---|---|---|---|
| Inside Airbnb fields already in the dataset: `host_url`, `host_profile_url` (manual page view), `host_about`, `host_location`, `host_verifications` | Free; CC BY 4.0 | Public profile facts for personalisation (joined year, reply rate, listings, "verified"). No contact details are exposed by Airbnb. | **No email/phone.** Airbnb ToS forbids scraping/automation — pages are opened **manually by a human**, never fetched in code. Do not message hosts through Airbnb (spam/ToS); outreach happens off-platform by email. |
| Host's own website / business name found by manual search (`host_name` + "Austin" + "STR"/"property management") | Free | Domain → contact page email, or a business listing (Google Business Profile, BBB). | First-name-only hosts rarely resolve; search engines' ToS forbid automated scraping, so this is **manual** work per lead. Realistic yield: low-to-moderate. |
| OpenCorporates (free tier w/ attribution), Texas Comptroller & Travis County Appraisal District public owner/LLC lookup | Free | Entity or property-owner name behind an LLC; confirms "this host is a real business". | Names only — **no emails**; entity ↔ person mapping is manual and error-prone; generous rate limits on free tier. |
| WHOIS on a discovered domain (e.g. whois.com) | Free | Registrant contact, often redacted | GDPR-style redaction is now the norm; thin yield. |
| LinkedIn public profile (manual view) | Free (account) | Possibly a public contact; human DM is an option | ToS forbids automation/scraping; conversion from cold DM is low; not automatable. |

**Not viable / excluded:** guessed or permutated emails (rule 4 — banned), phone-list datasets and lookup APIs with free trials (purchased data — rule 4), Airbnb message scraping (rules 3 & 4), Hunter/Snov-style "free credits" (still paid-data class, and unreliable attribution). Rule 2 note: no third-party lookup tool clears our license bar anyway.

**Realistic expectation:** perhaps **10–30% of shortlisted leads** get a public contact after manual digging. The rest are marked **`no contact`** and skipped for outreach (still useful as audit demos). Every stored contact records `source_url` + `found_on` date so a reviewer can verify before anything is sent.

**CAN-SPAM note for the drafts (rule 6 + legal minimum):** truthful sender identity, a **physical postal address** in the email, a functioning opt-out line, and opt-out honoured within 10 business days. Drafts must contain all three; the review queue blocks export of a draft missing them.

## 3. Proposed architecture (post-approval)

New sibling package in this repo, reusing `str_audit` untouched:

```
str_leads/
  __init__.py        package marker
  data.py            SELECT host-level + listing columns via DuckDB (reuses normalisation ideas, not code)
  score.py           CUSTOM lead score — weighted, explainable, thresholds as named constants
  audit_bridge.py    runs str_audit.audit.run_audit() per top-N lead; stores audit JSON
  pitch.py           CUSTOM prompt + Jinja2 template for the outreach draft (allow-listed slots only)
  store.py           CUSTOM dedupe/status tracking — SQLite (default) via stdlib sqlite3
  export.py          CSV export builder (approval-queue → CSV)
leadfinder_app.py    Streamlit review queue (approve/edit/reject, status filter, CSV export)
scripts/score_leads.py   CLI: load → host table → score → top-N audits → drafts → SQLite
tests/test_leads_*.py    pytest smoke tests, synthetic data, no network
```

- **Reuse:** `str_audit.comps/signals/revenue/audit/llm/report` imported as-is (Phase 2 of Project 1). No forks, no copies. CREDITS.md updated for Streamlit as-is (already Apache-2.0) plus any new dependency.
- **Storage:** SQLite default (zero-config, zero accounts, git-ignorable). Supabase free tier remains a drop-in alternative behind `str_leads/store.py` if you want hosted/multi-user later.
- **LLM:** `str_audit.llm` wrapper + `LLM_PROVIDER=gemini|groq` from `.env`; deterministic offline fallback. New pitch prompt lives in `str_leads/pitch.py` (rule 7).
- **Statuses:** `new → approved / rejected → sent → replied → meeting` (+ `no contact`, `do_not_contact`). CSV export only; no send path anywhere (rule 6).
- **Lead score sketch (weights to be tuned after you see the first ranking):**
  listings per host ≥ 2 (multi-property owner, +3), price ≥ 10% below named neighbourhood comp median (+2), any listing stale > 180 days (+2), thin description < 60 words (+1), `estimated_revenue_l365d` in bottom tercile vs comp median (+2), not superhost (+1), response rate < 90% (+1), host_since < 24m (+1), availability_365 > 180 (+1). Max ~12; ranking = sorted desc with reasons printed per row.

## 4. Phase plan & stop points

| Phase | Deliverable | Stop? |
|---|---|---|
| 1 | Host-level table + score CLI; printed ranking incl. reasons | report results to you |
| 2 | Audit top-N (default N=10) → SQLite; ESTIMATE labels everywhere | report |
| 3 | LLM pitch drafts (Gemini/Groq or offline fallback) from audit dict only | you review sample drafts |
| 4 | Streamlit queue: approve/edit/reject, status tracking, CSV export | done — you drive it |

Separate Streamlit file (`leadfinder_app.py`), not edits to `app.py`; sidebar cross-links the two tools.

## 5. License flags (excluded / not reusing)

- **Mautic** — GPL/NOASSERTION → excluded (rule 2).
- `Astoriel/LeadGenius` — **no license** → excluded (rule 2). `lat35n-hrt/streamlit_approval_workflow_poc`, `kajarenc/human-in-the-loop-streamlit` — **no license** → pattern reference only, never copied.
- `olivierzach/tricentis-lead-scoring` and various "lead scoring" notebooks — unlicensed/case-study → not reused.
- `mjml-python` — no license → excluded; MJML itself only via npm (not used — wrong stack).
- `premailer` — PSF license (outside MIT/Apache/BSD), unmaintained since 2021 → flagged, not used.
- `email-validator` — Unlicense → excluded (trivial regex used instead).
- `PyCaret` — MIT, would pass rule 2, but wrong fit (no labels) → not used.

## 6. Decisions needed from you

1. Approve the (a)/(b)/(c)/(d) selections above as written?
2. Storage: **SQLite (recommended)** or Supabase free tier?
3. City stays **Austin** (snapshot 2026-09-17)? (Inside Airbnb also offers Dallas/Denver etc.)
4. Top-N for Phase 2 audits: **10**?
5. Sender identity for CAN-SPAM lines in drafts (name, business, postal address) — provide before Phase 3; `.env` keys for the drafts sender details (or placeholders for manual fill).
6. Any deal-breakers on the proposed file map?
