"""Best-effort PUBLIC-contact finder for leads — opt-in, rate-limited, never guessed.

Rules (carried over from the project): public web info only; no email permutations;
every candidate carries its source URL; nothing is written to the DB without the
caller (CLI) deciding to persist. Hit rates will be low — most Inside Airbnb
host names are first-name-only and not uniquely identifying.

Providers (all free, key in .env):
  - Tavily (default): 1,000 API credits/mo free, no card required. POST /search.
                      Sign up at https://app.tavily.com/home
                      Honest limits: tops out; covers ~top-200 hosts/month of 4,600.
  - Brave Search API: free monthly $5 credit (~1,000 searches). GET /web/search.
                      https://api-dashboard.search.brave.com/register
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Optional

import requests

BRAVE_WEB = "https://api.search.brave.com/res/v1/web/search"
TAVILY_SEARCH = "https://api.tavily.com/search"
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


def _candidates_from_rows(host_name, city, rows, source, min_evidence):
    out = []
    first = _first_name(host_name)
    for row in rows:
        text = (row.get("title") or "") + " " + (row.get("description") or "") + " " + (row.get("content") or "")
        blob = (row.get("url") or "") + " " + text
        name_ok = _name_match(host_name, blob)
        if not name_ok:
            continue
        emails = _emails_in_text(blob)
        if emails:
            strongest = max((_evidence(x, host_name, blob) for x in emails), default=0)
            if strongest >= min_evidence:
                for addr in emails:
                    score = _evidence(addr, host_name, blob)
                    if score >= min_evidence:
                        out.append(Candidate(email=addr, url=row.get("url", ""), source=source,
                                             evidence_score=score, name_match=True,
                                             query=f'"{host_name}" {city} vacation rental OR Airbnb owner contact'))
        else:
            # no email in snippets but strong hit — surface the page as a lead pointer
            score = 2 if _topic_hit(text) else 1
            if score >= min_evidence:
                out.append(Candidate(email=None, url=row.get("url", ""), source=source,
                                     evidence_score=score, name_match=True,
                                     query=f'"{host_name}" {city} vacation rental OR Airbnb owner contact'))
    return out


def _evidence(addr: str, host: str | None, text: str) -> int:
    score = 2 if _name_match(host, text) else 0
    if any(tok in text.lower() for tok in ("vacation", "airbnb", "short-term", "str")):
        score += 1
    if addr and not addr.split("@", 1)[1].lower().startswith(("yahoo", "gmail", "outlook")):
        score += 1   # branded domains beat freemail for a business contact
    return score


def _topic_hit(text: str) -> bool:
    t = text.lower()
    return any(tok in t for tok in ("vacation rental", "airbnb", "short-term", "str", "vrbo", "owner"))


def _emails_in_text(text: str) -> list[str]:
    found = set()
    for m in _EMAIL_RX.finditer(html.unescape(text)):
        found.add(m.group(0).lower())
    for m in _MAILTO_RX.finditer(text):
        addr = html.unescape(m.group(1)).strip().split("?")[0].lower()
        if _EMAIL_RX.fullmatch(addr):
            found.add(addr)
    out = []
    for addr in found:
        domain = addr.split("@", 1)[1].lower()
        if domain in _BLOCKLIST:
            continue
        if addr.split("@", 1)[0].lower() in _RESERVED:
            continue
        out.append(addr)
    return out


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
         "description": x.get("description", ""), "content": ""}
        for x in web
    ]


def search_tavily(query: str, key: str, max_results: int = 5) -> list[dict]:
    if not key:
        return []
    try:
        r = requests.post(
            TAVILY_SEARCH,
            json={"query": query, "max_results": max_results, "search_depth": "basic",
                  "topic": "general", "include_answer": False},
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    results = data.get("results") or []
    return [
        {"url": x.get("url", ""), "title": x.get("title", ""),
         "description": x.get("content", x.get("raw_content", "")), "content": x.get("content", "")}
        for x in results
    ]


def find_for_lead(host_name: str | None, city: str, key: str,
                  max_results: int = 5,
                  min_evidence: int = 2,
                  provider: str = "tavily") -> list[Candidate]:
    """Search public web for host_name's public contact info. Never guesses.

    provider: "tavily" (default; free 1k credits/mo) or "brave". Pass the matching key.
    """
    query = f'"{host_name}" {city} vacation rental OR Airbnb owner contact email'
    if provider == "brave":
        rows = search_brave(query, key, count=max_results)
        source = "brave_search"
    else:
        rows = search_tavily(query, key, max_results=max_results)
        source = "tavily_search"
    out = _candidates_from_rows(host_name, city, rows, source, min_evidence)
    by_email: dict[str, Candidate] = {}
    by_url: dict[str, Candidate] = {}
    for c in out:
        if c.email:
            cur = by_email.get(c.email)
            if cur is None or cur.evidence_score < c.evidence_score:
                by_email[c.email] = c
        else:
            cur = by_url.get(c.url)
            if cur is None or cur.evidence_score < c.evidence_score:
                by_url[c.url] = c
    merged = list(by_email.values()) + list(by_url.values())
    return sorted(merged, key=lambda c: c.evidence_score, reverse=True)
