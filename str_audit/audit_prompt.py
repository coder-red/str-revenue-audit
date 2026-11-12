"""The audit-summary prompt — ours (rule 5).

One prompt, shared by both providers (Gemini/Groq). Hard rules baked in:
non-technical tone, no invented numbers, ESTIMATE language, short output.
"""

SYSTEM = (
    "You are a revenue analyst writing for a non-technical short-term-rental "
    "property manager. Write in plain English. Use only the numbers you are given; "
    "never invent, round up, or re-derive them. Always call revenue figures "
    "'estimates'. No jargon (no 'RevPAR', 'ADR', 'comp set' without explanation). "
    "No markdown tables. Output plain text, under 180 words."
)


def build_summary_prompt(audit: dict) -> str:
    t = audit["target"]
    c = audit["comps"]
    n = audit["estimate"]["numbers"]
    signals = audit["signals"]
    fixes = audit["top_fixes"]

    signal_lines = "\n".join(f"- [{s['status'].upper()}] {s['summary']}" for s in signals)
    fix_lines = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(fixes)) or "1. None — listing is healthy."

    def money(v):
        return f"${v:,.0f}" if isinstance(v, (int, float)) and v is not None else "n/a"

    lo, hi = n.get("est_gap_low"), n.get("est_gap_high")
    if n.get("insufficient_data"):
        gap_range = f"INSUFFICIENT DATA — {n.get('insufficient_reason') or 'too few similar comps'}. Do not quote any figure."
    elif lo is not None and hi is not None:
        gap_range = f"{money(lo)} to {money(hi)} per year (ESTIMATE from public data)"
    else:
        gap_range = "unavailable — occupancy or revenue signal missing"

    return f"""Write the audit summary for this listing.

LISTING
- Name: {t.get('name')}
- Room type: {t.get('room_type')} | Beds: {t.get('beds')} | Neighbourhood: {t.get('neighbourhood_cleansed')}
- Price: {money(t.get('price'))} per night | Availability (365d): {t.get('availability_365')} nights
- Reviews: {t.get('number_of_reviews')} total, last review: {t.get('last_review')}

COMP SET (n={c.get('n')}, pool: {c.get('pool')})
- Median comp price: {money(c.get('median_price'))} per night
- Comp median est. annual revenue (Inside Airbnb model): {money(n.get('comp_median_estimated_revenue_l365d'))}

REVENUE GAP (all figures are ESTIMATES, method printed on the PDF)
- Conservative range for the annual upside (A → B): {gap_range}
- Estimated annual gap from price positioning: {money(n.get('est_annual_price_gap'))}
- Estimated annual gap vs comp median revenue (Inside Airbnb model): {money(n.get('est_annual_ia_revenue_gap'))}
- Inside Airbnb's estimate of this listing's annual revenue: {money(n.get('target_estimated_revenue_l365d'))}

SIGNALS
{signal_lines}

TOP FIXES (in order)
{fix_lines}

INSTRUCTIONS
- Open with one sentence: the single biggest problem in plain English.
- Then 2-4 short bullets: the fixes, each tied to what it means for bookings or rate.
- Close with one sentence naming the conservative range of estimated annual upside (the “A → B” range) exactly as given, and state clearly that it is an estimate from public data, not a guarantee. If no range is available (insufficient data), say the public data was too thin to quote a figure and do not quote one. Do not substitute a single figure for the range.
- Do not add any other numbers. Do not use markdown headers."""
