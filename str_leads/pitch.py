"""Pitch drafting — custom prompt (rule 7).

The LLM fills ONLY the email body, from an explicit allow-listed fact sheet built
from (a) the lead row and (b) the audit dict for that host's weakest listing.
It may not invent numbers, claims, or identity. Subject line is deterministic
(not LLM-generated) so it can never fabricate a claim either. The sender block
(name, business, postal address) and the opt-out line are appended by code,
always — CAN-SPAM is not left to the model.

Every figure quoted is an ESTIMATE from the audit, and the prompt says so.
With no LLM key (or on any failure) a deterministic fallback body is produced
from the same audit dict, mirroring str_audit.llm's offline-fallback pattern.

There is NO send capability anywhere in this module (rule 6).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from str_audit.llm import generate_text

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PITCH_SYSTEM = (
    "You are a short-term-rental property manager writing a plain-text cold outreach "
    "email to an Airbnb host you have never met. Hard rules: (1) Use ONLY the facts "
    "and figures in the brief you are given. (2) Never invent, estimate, re-derive, or "
    "round any number; if a figure is not provided, do not mention it. (3) Always call "
    "revenue figures 'estimates'. (4) No claims about the host's business, revenue, "
    "occupancy, or intentions beyond the brief. (5) Plain English, no jargon, no "
    "markdown, no bullet-point spam. Under 150 words. (6) One clear call to action: a "
    "20-minute call this week. (7) Do NOT write a subject line and do NOT sign the "
    "email — the signature is appended separately."
)

DEFAULT_OPT_OUT = 'Reply "stop" (or tell me anytime) and I will not email you again.'


def sender_identity() -> dict:
    """Sender facts from the environment; anything missing comes back None."""
    return {
        "name": _env("SENDER_NAME"),
        "business": _env("SENDER_BUSINESS"),
        "postal": _env("SENDER_POSTAL_ADDRESS"),
        "opt_out": _env("OPT_OUT_TEXT") or DEFAULT_OPT_OUT,
    }


def _env(key: str) -> str | None:
    v = os.environ.get(key, "").strip()
    return v or None


def compose_footer() -> str:
    """The block appended to every draft. Placeholders are loud on purpose so a
    half-filled .env can never masquerade as a sendable email."""
    s = sender_identity()
    name = s["name"] or "[SENDER_NAME — set in .env before sending]"
    business = s["business"] or "[SENDER_BUSINESS — set in .env before sending]"
    postal = s["postal"] or "[SENDER_POSTAL_ADDRESS — set in .env before sending]"
    return f"— {name}, {business}\n{postal}\n{s['opt_out']}"


_PLACEHOLDER_MARKERS = ("[SENDER_", "set in .env", "TODO", "XXX", "<insert", "{SENDER_")


def can_spam_ok(subject: str, body: str) -> tuple[bool, list[str]]:
    """Strict check of the assembled draft. Returns (ok, missing_or_problem_list)."""
    problems: list[str] = []
    s = sender_identity()
    if not (subject or "").strip():
        problems.append("subject is empty")
    if not s["name"]:
        problems.append("SENDER_NAME not set")
    elif s["name"] not in body:
        problems.append("sender name missing from body")
    if not s["business"]:
        problems.append("SENDER_BUSINESS not set")
    elif s["business"] not in body:
        problems.append("sender business missing from body")
    if not s["postal"]:
        problems.append("SENDER_POSTAL_ADDRESS not set")
    elif s["postal"] not in body:
        problems.append("postal address missing from body")
    if s["opt_out"] not in body:
        problems.append("opt-out line missing from body")
    for marker in _PLACEHOLDER_MARKERS:
        if marker in body:
            problems.append(f"placeholder marker {marker!r} in body")
            break
    return (not problems, problems)


_FIRST_NAME_RE = re.compile(r"[A-Za-z][A-Za-z'\-]{0,39}")


def first_name(host_name) -> str:
    if not isinstance(host_name, str):
        return "there"
    m = _FIRST_NAME_RE.search(host_name.split()[0] if host_name.split() else "")
    return m.group(0).capitalize() if m else "there"


def build_subject(lead: dict) -> str:
    """Deterministic on purpose — the subject must never invent a claim."""
    n = lead.get("n_listings") or 1
    return f"Quick thought on your {n} Austin listings — {first_name(lead.get('host_name'))}"


def _money(v) -> str:
    return f"${v:,.0f}" if isinstance(v, (int, float)) and v is not None else "n/a"


def build_pitch_prompt(lead: dict, audit: dict) -> str:
    t = audit.get("target", {})
    n = audit.get("estimate", {}).get("numbers", {})
    fixes = audit.get("top_fixes", [])[:3]
    listing_id = audit.get("listing_id") or t.get("id")
    neighbourhood = t.get("neighbourhood_cleansed") or "Austin"

    fix_lines = "\n".join(f"- {f}" for f in fixes) or "- (no fixes flagged)"
    return f"""Write the outreach email for this host, from the brief below — nothing else.

HOST
- First name: {first_name(lead.get('host_name'))}
- Total listings they run in Austin (per Inside Airbnb public data): {lead.get('n_listings')}
- Listing we audited ({neighbourhood}): {t.get('name')}
- Room type: {t.get('room_type')} | Beds: {t.get('beds')} | Price: {_money(t.get('price'))}/night
- Reviews: {t.get('number_of_reviews')} total, last review: {t.get('last_review')}

WHAT THE AUDIT FOUND (every figure below is an ESTIMATE from the audit — say so)
- Estimated annual gap vs the comp-median revenue (Inside Airbnb model): {_money(n.get('est_annual_ia_revenue_gap'))} per year
- Estimated annual gap from price positioning: {_money(n.get('est_annual_price_gap'))} per year
- Their listing's modelled revenue: {_money(n.get('target_estimated_revenue_l365d'))} per year
- Comp-median modelled revenue: {_money(n.get('comp_median_estimated_revenue_l365d'))} per year
- Comp median price: {_money(n.get('comp_median_price'))}/night

TOP FIXES FROM THE AUDIT (in priority order)
{fix_lines}

INSTRUCTIONS
- Open with one sentence showing you looked at their actual listing (use its name naturally).
- One or two sentences on the estimated gap — always with the word 'estimate'.
- Suggest the single highest-impact fix from the list.
- Close with one sentence asking for a 20-minute call this week to walk through the audit.
- Do not mention Inside Airbnb by name; say 'public listing data' instead.
- No subject line, no signature, no markdown. Plain text, under 150 words."""


def fallback_pitch(lead: dict, audit: dict) -> str:
    """Deterministic body when no LLM is available — audit dict only, no invention."""
    t = audit.get("target", {})
    n = audit.get("estimate", {}).get("numbers", {})
    fixes = audit.get("top_fixes") or []
    fix_one = fixes[0] if fixes else "tighten the basics on the listing"
    name = first_name(lead.get("host_name"))
    listing = t.get("name") or "your listing"
    gap = n.get("est_annual_ia_revenue_gap")
    gap_line = (f"the gap vs the comp-median modelled revenue pencils out at an estimated "
                f"{_money(gap)} per year" if isinstance(gap, (int, float))
                else "there is an estimated revenue gap against the comp set")
    return (
        f"Hi {name} — I found your {t.get('room_type', 'listing').lower()} "
        f"\"{listing}\" in the public listing data and ran the numbers.\n\n"
        f"{gap_line} (an estimate from public data, not a guarantee — the method is attached "
        f"to the audit). The first thing I would fix: {fix_one}\n\n"
        f"If you want, I can walk you through the audit on a quick 20-minute call this week — "
        f"no pitch beyond that. Worst case you keep the findings."
    )


def load_audit(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def generate_pitch(lead: dict, audit: dict, provider: str | None = None) -> dict:
    """Assemble a sendable-by-a-human draft. Returns dict with subject/body/provider/can_spam_ok."""
    prompt = build_pitch_prompt(lead, audit)
    provider_used = "fallback"
    try:
        body, provider_used = generate_text(prompt, PITCH_SYSTEM, provider=provider)
    except Exception as exc:  # noqa: BLE001 — degrade, never crash, never invent
        body = fallback_pitch(lead, audit)
        provider_used = f"fallback ({(provider or os.environ.get('LLM_PROVIDER', 'gemini')).lower()} unavailable: {exc.__class__.__name__})"

    footer = compose_footer()
    full_body = body.rstrip() + "\n\n" + footer
    subject = build_subject(lead)
    ok, problems = can_spam_ok(subject, full_body)
    return {
        "subject": subject,
        "body": full_body,
        "provider_used": provider_used,
        "can_spam_ok": ok,
        "can_spam_problems": problems,
    }
