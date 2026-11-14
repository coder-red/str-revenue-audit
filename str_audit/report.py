"""Render the audit dict to the one-page PDF (xhtml2pdf — no system deps).

Client-grade design: wordmark header, composite health score, two ESTIMATE
cards, comp percentile chart, formula footer. White-label via CLIENT_BRAND
(e.g. CLIENT_BRAND="Acme Property Group" stamps the client's name on the page).

Usage:
    CLIENT_BRAND="Acme PM" python -m str_audit.report --listing-id 21004527
"""

from __future__ import annotations

import argparse
import base64
import html as _html
import os
import sys
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from str_audit import cities
from str_audit.cities import default_data, metro_line

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = PROJECT_ROOT / "templates"
ASSETS_FONTS = PROJECT_ROOT / "assets" / "fonts"
DEFAULT_OUT_DIR = PROJECT_ROOT / "outputs"

DEFAULT_BRAND = "STR Revenue Audit"


def _money(v, signed: bool = False) -> str:
    if v is None:
        return "n/a"
    try:
        if pd.isna(v):
            return "n/a"
    except (TypeError, ValueError):
        pass
    if signed:
        sign = "+" if v >= 0 else "-"
        return f"{sign}${abs(v):,.0f}"
    return f"${v:,.0f}"


def _int_or_dash(v) -> str:
    try:
        if v is None or pd.isna(v):
            return "–"
        return f"{int(v)}"
    except (TypeError, ValueError):
        return "–"


def make_chart_b64(audit: dict) -> str | None:
    """Nightly price: target vs comp P25 / median / P75 — one glance."""
    prices = [r.get("price") for r in audit.get("comps", {}).get("table", [])
              if isinstance(r.get("price"), (int, float))]
    target = audit["target"].get("price")
    if len(prices) < 3 or target is None:
        return None
    s = pd.Series(prices)
    p25, p50, p75 = (float(s.quantile(q)) for q in (0.25, 0.5, 0.75))
    labels = ["Comp median", "Comp P75", "Comp P25", "This listing"]
    values = [p50, p75, p25, float(target)]
    colors = ["#c8c4b8", "#c8c4b8", "#c8c4b8", "#10483c"]
    try:
        import plotly.graph_objects as go

        fig = go.Figure(go.Bar(
            x=values, y=labels, orientation="h",
            marker_color=colors,
            text=[f"${v:,.0f}" for v in values],
            textposition="outside",
            hoverinfo="skip",
        ))
        fig.update_layout(
            margin=dict(l=4, r=50, t=2, b=2), height=115, width=700,
            xaxis=dict(visible=False, range=[0, max(values) * 1.16 or 1]),
            yaxis=dict(showgrid=False, tickfont=dict(size=11, family="DejaVu Sans")),
            font=dict(family="DejaVu Sans", size=10, color="#232323"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        return base64.b64encode(fig.to_image(format="png", scale=2)).decode()
    except Exception:
        return None


def _verdict_sub(audit: dict) -> str:
    """Supporting line, composed from data — headline itself is the conservative range."""
    fixes = audit.get("top_fixes") or []
    fails = [s for s in audit.get("signals", []) if s.get("status") == "fail"]
    if fails:
        first = fails[0]["key"].replace("_", " ")
        return f"Biggest leak: {first}. " + (fixes[0] if fixes else "")
    if fixes:
        return "Biggest lever: " + fixes[0]
    return "Listing is fundamentally healthy — tactical tuning only."


def build_view(audit: dict, chart_b64: str | None = None, sample: bool = False) -> dict:
    t = audit["target"]
    c = audit["comps"]
    n = audit["estimate"]["numbers"]
    health = audit.get("health") or {"score": None, "label": "n/a", "deductions": [], "formula": ""}
    gap_a, gap_b = n.get("est_annual_price_gap"), n.get("est_annual_ia_revenue_gap")

    # Conservative range (or INSUFFICIENT DATA) — the numbers dict carries the decision
    # when the audit came from the pipeline; derive it for hand-built fixtures.
    lo, hi = n.get("est_gap_low"), n.get("est_gap_high")
    if lo is None:
        gaps = [g for g in (gap_a, gap_b) if isinstance(g, (int, float))]
        lo, hi = (min(gaps), max(gaps)) if gaps else (None, None)
    gap_range = (f"{_money(lo, signed=True)} → {_money(hi, signed=True)}"
                 if lo is not None else None)
    insufficient_data = bool(n.get("insufficient_data"))
    insufficient_reason = n.get("insufficient_reason") or "the comp set is too thin or too dissimilar to quote an upside figure. We do not guess."
    subline = _verdict_sub(audit)

    brand = os.environ.get("CLIENT_BRAND", DEFAULT_BRAND).strip() or DEFAULT_BRAND

    meta_bits = [
        t.get("room_type") or "Listing",
        f"{t.get('bedrooms')}BR" if t.get("bedrooms") is not None else None,
        f"{t.get('baths')} bath" if t.get("baths") is not None else None,
        t.get("neighbourhood_cleansed"),
        f"{t.get('number_of_reviews')} reviews" if t.get("number_of_reviews") is not None else None,
        f"last review {str(t.get('last_review'))[:10]}" if t.get("last_review") else None,
    ]
    meta = " · ".join(str(b) for b in meta_bits if b)

    occ = n.get("comp_avg_occupancy")
    comp_rev_n = None
    for line in audit["estimate"]["method"]:
        if "n = " in line:
            try:
                comp_rev_n = int(line.split("n = ")[-1].split(")")[0])
            except ValueError:
                pass

    fixes = [str(f) for f in audit.get("top_fixes", [])][:3]
    summary_plain = audit.get("llm_summary", "")
    summary_html = _html.escape(summary_plain).replace("\n", "<br>")

    comps_rows = []
    for row in audit.get("comps", {}).get("table", [])[:6]:
        comps_rows.append({
            "rank": row.get("rank"),
            "hood": row.get("neighbourhood_cleansed") or "–",
            "room_type": (row.get("room_type") or "").replace("Entire home/apt", "Entire home"),
            "price": f"{row.get('price'):,.0f}" if row.get("price") else "–",
            "est_rev": _money(row.get("estimated_revenue_l365d")),
            "reviews": _int_or_dash(row.get("number_of_reviews")),
        })

    signals = [{
        "status": s["status"],
        "name": s["key"].replace("_", " "),
        "summary": s["summary"],
    } for s in audit.get("signals", [])]

    return {
        "brand": brand,
        "brand_is_default": brand == DEFAULT_BRAND,
        "listing_name": t.get("name") or "Untitled listing",
        "listing_meta": meta,
        "metro_line": metro_line(),
        "generated_at": (audit.get("generated_at") or "")[:10],
        "gap_range": gap_range,
        "insufficient_data": insufficient_data,
        "insufficient_reason": insufficient_reason,
        "verdict_sub": _html.escape(subline),
        "est_a": _money(gap_a, signed=True),
        "est_b": _money(gap_b, signed=True),
        "est_a_negative": isinstance(gap_a, (int, float)) and gap_a < 0,
        "est_b_negative": isinstance(gap_b, (int, float)) and gap_b < 0,
        "comp_price": f"{n['comp_median_price']:,.0f}" if n.get("comp_median_price") else "n/a",
        "price": f"{n['target_price']:,.0f}" if n.get("target_price") else "n/a",
        "occupancy": f"{occ:.3f}" if occ is not None else "n/a",
        "occupancy_pct": f"{occ * 100:.0f}%" if occ is not None else "n/a",
        "comp_n": c.get("n", 0),
        "pool": c.get("pool", ""),
        "comp_ia_rev": _money(n.get("comp_median_estimated_revenue_l365d")),
        "target_ia_rev": _money(n.get("target_estimated_revenue_l365d")),
        "active_comps_n": comp_rev_n if comp_rev_n is not None else "≥3",
        "health": health,
        "sample_banner": sample,
        "health_deductions": " · ".join(health.get("deductions", [])),
        "signals": signals,
        "fixes": fixes or ["No fixes flagged — the listing is healthy."],
        "summary_html": summary_html,
        "comps_rows": comps_rows,
        "method": audit["estimate"]["method"] + ([f"Health score: {health.get('formula')} "
                    f"Deductions: {', '.join(health.get('deductions', [])) or 'none'}."]
                   if health.get("formula") else []),
        "chart_b64": chart_b64,
    }


def render_html(audit: dict, chart_b64: str | None = "auto", sample: bool = False) -> str:
    if chart_b64 == "auto":
        chart_b64 = make_chart_b64(audit)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("audit_report.html")
    view = build_view(audit, chart_b64=chart_b64, sample=sample)
    view["assets"] = ASSETS_FONTS.as_posix()
    return template.render(view=view, assets=view["assets"])


def render_pdf(audit: dict, chart_b64: str | None = "auto", sample: bool = False) -> bytes:
    from xhtml2pdf import pisa

    html = render_html(audit, chart_b64=chart_b64, sample=sample)
    buf = BytesIO()
    result = pisa.CreatePDF(StringIO(html), dest=buf)
    if result.err:
        raise RuntimeError(f"xhtml2pdf reported {result.err} error(s)")
    return buf.getvalue()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--city", choices=list(cities.CITIES), default=None,
                    help="metro to audit (default: austin, or STR_CITY env if set)")
    ap.add_argument("--data", default=None,
                    help="path to listings.csv.gz (overrides --city/STR_CITY default)")
    ap.add_argument("--listing-id", type=int, required=True)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--photo-count", type=int, default=None)
    ap.add_argument("--provider", choices=["gemini", "groq", "none"], default=None)
    ap.add_argument("--sample", action="store_true",
                    help="render as a public-safe SAMPLE banner (anonymized audit is your responsibility)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.city:
        os.environ["STR_CITY"] = args.city
    elif args.data:
        inferred = cities.infer_slug(args.data)
        if inferred:
            os.environ["STR_CITY"] = inferred
    data_path = args.data or str(default_data())

    from str_audit.audit import run_audit
    from str_audit.data import load_listings

    df = load_listings(data_path)
    provider = None if args.provider in (None, "none") else args.provider
    audit = run_audit(df, args.listing_id, k=args.k,
                      photo_count=args.photo_count, provider=provider)
    pdf = render_pdf(audit, sample=args.sample)

    out = Path(args.out) if args.out else DEFAULT_OUT_DIR / f"audit_{args.listing_id}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf)
    print(f"wrote {out}  ({len(pdf) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
