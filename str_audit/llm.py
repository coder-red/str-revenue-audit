"""LLM summary — thin wrapper over Gemini (free tier) and Groq (free tier).

Reads keys from .env (gitignored). If no key is configured, or the API call
fails, returns a deterministic plain-text fallback built from the same audit
dict — the tool must work offline and must never emit invented numbers.

Env:
    LLM_PROVIDER=gemini|groq     (default: gemini)
    GEMINI_API_KEY, GEMINI_MODEL (default gemini-2.5-flash)
    GROQ_API_KEY,   GROQ_MODEL   (default llama-3.3-70b-versatile)
"""

from __future__ import annotations

import os

from str_audit.audit_prompt import SYSTEM, build_summary_prompt

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv optional; env vars still win if exported
    pass


def _fallback_summary(audit: dict) -> str:
    t = audit["target"]
    n = audit["estimate"]["numbers"]
    fixes = audit["top_fixes"]

    def money(v):
        return f"${v:,.0f}" if isinstance(v, (int, float)) and v is not None else "n/a"

    gap = n.get("est_annual_price_gap")
    sig = {s["key"]: s for s in audit.get("signals", [])}
    rec = sig.get("review_recency", {})
    price_sig = sig.get("price_vs_comps", {})

    if rec.get("status") == "fail":
        lead = "The listing's review momentum is dead — no fresh social proof, and bookings follow reviews."
    elif rec.get("status") == "warn":
        lead = "Booking velocity has gone quiet — reviews have dried up and the listing needs a nudge."
    elif isinstance(gap, (int, float)) and gap > 0 and price_sig.get("status") != "pass":
        lead = f"Priced below the comp set — likely leaving an estimated ${gap:,.0f} per year on the table."
    elif isinstance(gap, (int, float)) and gap < 0 and price_sig.get("status") != "pass":
        lead = f"Priced above the comp set by an estimated ${abs(gap):,.0f} per year of occupancy risk."
    else:
        lead = "Price is in line with the comp set."

    bullet_fixes = "\n".join(f"- {f}" for f in fixes[:4]) or "- No fixes flagged."
    upside = n.get("est_annual_ia_revenue_gap")
    if not isinstance(upside, (int, float)):
        tail = "Estimated upside vs the comp median is unavailable for this listing."
    elif upside >= 0:
        tail = f"Estimated annual upside vs the comp median: {money(upside)} (an estimate, not a guarantee)."
    else:
        tail = f"This listing outperforms the comp median by an estimated {money(abs(upside))} per year (an estimate, not a guarantee)."
    return f"{lead}\n{bullet_fixes}\n{tail}"


def _gemini(prompt: str, system: str = SYSTEM) -> str:
    from google import genai  # lazy import — keeps Phase 1 usable without the SDK
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    resp = client.models.generate_content(
        model=model,
        contents=f"{system}\n\n{prompt}" if system else prompt,
    )
    text = getattr(resp, "text", None)
    if not text:
        raise RuntimeError("empty response from Gemini")
    return text.strip()


def _groq(prompt: str, system: str = SYSTEM) -> str:
    from groq import Groq  # lazy import
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")
    client = Groq(api_key=api_key)
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}],
        temperature=0.4,
        # Reasoning models (e.g. gpt-oss-*) spend most of the budget on hidden
        # reasoning tokens — 400 yields finish_reason=length with empty content.
        max_tokens=2500,
    )
    text = resp.choices[0].message.content
    if not text:
        raise RuntimeError("empty response from Groq")
    return text.strip()


def generate_text(prompt: str, system: str | None = None,
                  provider: str | None = None) -> tuple[str, str]:
    """Call the configured provider. Raises on any failure — callers own their fallbacks.

    Returns (text, provider_used). Added for str_leads.pitch; summarize_audit keeps
    its historical never-raise behaviour by wrapping this.
    """
    provider = (provider or os.environ.get("LLM_PROVIDER", "gemini")).lower().strip()
    system = system if system is not None else SYSTEM
    fn = {"gemini": _gemini, "groq": _groq}.get(provider)
    if fn is None:
        raise RuntimeError(f"unknown LLM_PROVIDER={provider!r}")
    return fn(prompt, system), provider


def summarize_audit(audit: dict, provider: str | None = None) -> tuple[str, str]:
    """Return (summary_text, provider_used). Never raises — falls back deterministically."""
    prompt = build_summary_prompt(audit)
    try:
        return generate_text(prompt, SYSTEM, provider)
    except Exception as exc:  # noqa: BLE001 — we want any failure to degrade, not crash
        resolved = (provider or os.environ.get("LLM_PROVIDER", "gemini")).lower().strip()
        if resolved in ("gemini", "groq"):
            return _fallback_summary(audit), f"fallback ({resolved} unavailable: {exc.__class__.__name__})"
        return _fallback_summary(audit), f"fallback (unknown LLM_PROVIDER={resolved!r})"
