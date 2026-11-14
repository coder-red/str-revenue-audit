"""Best-effort PUBLIC-contact finder for leads — opt-in, rate-limited, never guessed.

Rules (carried over from the project): public web info only; no email permutations;
every candidate carries its source URL; nothing is written to the DB without the
caller (CLI) deciding to persist. Hit rates will be low — most Inside Airbnb
host names are first-name-only and not uniquely identifying.

Provider: Brave Search API (free tier, monthly composite $5 in credits included).
Requires BRAVE_API_KEY env (in .env or job env). Sign up at
  https://api-dashboard.search.brave.com/register
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Optional

import requests

BRAVE_WEB = "https://api.search.brave.com/res/v1/web/search"
_EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}")
_MAILTO_RX = re.compile(r'mailto:([^"?\']+)', re.IGNORECASE)
_BLOCKLIST = {
    "example.com", "sentry.io", "wix.com", "squarespace.com", "godaddy.com",
    "airbnb.com", "tripadvisor.com", "wordpress.com", "sites.google.com",
}
_RESERVED = {"hello", "info", "contact", "support", "noreply", "no-reply"}


@dataclass
class Candidate:
    email: Optional[str]
    url: str
    source: str
    evidence_score: int         # higher = better; minimum bar before we hand it back
    name_match: bool
    query: str


def _emails_in_html(text: str) -> list[str]:
    """Harvest emails from raw HTML via mailto: links and visible text."""
    found = set()
    for m in _MAILTO_RX.finditer(text):
        addr = html.unescape(m.group(1)).strip().split("?")[0].lower()
        if _EMAIL_RX.fullmatch(addr):
            found.add(addr)
    for m in _EMAIL_RX.finditer(html.unescape(text)):
        found.add(m.group(0).lower())
    # filter known junk / placeholders
    out = []
    for addr in found:
        domain = addr.split("@", 1)[1].lower()
        if domain in _BLOCKLIST:
            continue
        local = addr.split("@", 1)[0].lower()
        if local in _RESERVED:
            continue
        out.append(addr)
    return out


def _first_name(host_name: str | None) -> str:
    if not host_name or not isinstance(host_name, str):
        return ""
    parts = host_name.strip().split()
    return parts[0].strip(".,;:!?") if parts else ""


def _name_match(host: str | None, text: str) -> bool:
    first = _first_name(host)
    if not first or len(first) < 3:
        return False
    # case-insensitive substring, whole-word; protect "Anna" vs "Vanessa"
    return re.search(rf"\b{re.escape(first)}\b", text, re.IGNORECASE) is not None


def search_brave(query: str, key: str, count: int = 10) -> list[dict]:
    if not key:
        return []
    headers = {"Accept": "application/json", "X-Subscription-Token": key}
    params = {"q": query, "count": str(count)}
    try:
        r = requests.get(BRAVE_WEB, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    web = ((data or {}).get("web") or {}).get("results") or []
    return [
        {"url": x.get("url", ""), "title": x.get("title", ""),
         "description": x.get("description", "")}
        for x in web
    ]


def find_for_lead(host_name: str | None, city: str, key: str,
                  max_results: int = 10,
                  min_evidence: int = 2) -> list[Candidate]:
    """Search public web for host_name's public contact info. Never guesses."""
    query = f'"{host_name}" {city} vacation rental OR Airbnb owner contact'
    out: list[Candidate] = []
    for row in search_brave(query, key, count=max_results):
        try:
            page = requests.get(row["url"], timeout=15,
                                headers={"User-Agent": "Mozilla/5.0 (compatible; lead-finder/0.1)"})
            page.raise_for_status()
            body = page.text
        except Exception:
            continue
        emails = _emails_in_html(body)
        name_ok = _name_match(host_name, body) or _name_match(host_name, row["title"] + " " + row["description"])
        for addr in emails:
            score = 0
            if name_ok:
                score += 2
            else:
                continue  # no name match → reject outright
            if any(tok in body.lower() for tok in ("vacation", "airbnb", "short-term", "str")):
                score += 1
            if score >= min_evidence:
                out.append(Candidate(email=addr, url=row["url"], source="brave_search",
                                     evidence_score=score, name_match=name_ok, query=query))
    # de-dupe by email, keep best-scoring
    by_email: dict[str, Candidate] = {}
    for c in out:
        if c.email not in by_email or by_email[c.email].evidence_score < c.evidence_score:
            by_email[c.email] = c
    return sorted(by_email.values(), key=lambda c: c.evidence_score, reverse=True)
