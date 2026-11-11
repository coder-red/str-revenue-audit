"""Render the audit dict to the one-page PDF (xhtml2pdf — no system deps).

Phase 3. WeasyPrint was the approved pick but needs GTK/Pango system
libraries that don't exist on this Windows machine; xhtml2pdf (Apache-2.0)
was the pre-approved fallback and ships pure-Python. Fonts (DejaVu, see
assets/fonts/README.txt) let the PDF embed a real typeface with full
Latin coverage.

Usage:
    python -m str_audit.report --listing-id 21004527
"""

from __future__ import annotations

import argparse
import base64
import html as _html
import sys
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = PROJECT_ROOT / "templates"
ASSETS_FONTS = PROJECT_ROOT / "assets" / "fonts"
DEFAULT_OUT_DIR = PROJECT_ROOT / "outputs"


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
    """Tiny horizontal bar: this listing vs comp median (ESTIMATE B inputs)."""
    n = audit["estimate"]["numbers"]
    target = n.get("target_estimated_revenue_l365d") or 0
    comp = n.get("comp_median_estimated_revenue_l365d") or 0
    if not (target or comp):
        return None
    try:
        import plotly.graph_objects as go

        fig = go.Figure(go.Bar(
            x=[target, comp],
            y=["This listing", "Comp median"],
            orientation="h",
            marker_color=["#10483c", "#c8c4b8"],
            text=[f"${target:,.0f}", f"${comp:,.0f}"],
            textposition="outside",
            hoverinfo="skip",
        ))
        fig.update_layout(
            margin=dict(l=4, r=10, t=2, b=2), height=110, width=720,
            xaxis=dict(visible=False, range=[0, max(target, comp) * 1.18 or 1]),
            yaxis=dict(autorange="reversed", showgrid=False, tickfont=dict(size=12)),
            font=dict(family="DejaVu Sans", size=11, color="#232323"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        return base64.b64encode(fig.to_image(format="png", scale=2)).decode()
    except Exception:
        return None  # chart is decoration; the PDF must render without it


def build_view(audit: dict, chart_b64: str | None = None) -> dict:
    t = audit["target"]
    c = audit["comps"]
    n = audit["estimate"]["numbers"]
    gap_a, gap_b = n.get("est_annual_price_gap"), n.get("est_annual_ia_revenue_gap")

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
        "listing_name": t.get("name") or "Untitled listing",
        "listing_meta": meta,
        "metro_line": "AUSTIN, TX · INSIDE AIRBNB 2026-09-17",
        "generated_at": (audit.get("generated_at") or "")[:10],
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
        "signals": signals,
        "fixes": fixes or ["No fixes flagged — the listing is healthy."],
        "summary_plain": summary_plain,
        "summary_html": summary_html,
        "comps_rows": comps_rows,
        "method": audit["estimate"]["method"],
        "chart_b64": chart_b64,
    }


def render_html(audit: dict, chart_b64: str | None = "auto") -> str:
    if chart_b64 == "auto":
        chart_b64 = make_chart_b64(audit)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("audit_report.html")
    view = build_view(audit, chart_b64=chart_b64)
    # file:/// prefix — xhtml2pdf wants a URL; forward slashes everywhere
    view["assets"] = ASSETS_FONTS.as_posix()
    return template.render(view=view, assets=view["assets"])


def render_pdf(audit: dict, chart_b64: str | None = "auto") -> bytes:
    from xhtml2pdf import pisa

    html = render_html(audit, chart_b64=chart_b64)
    buf = BytesIO()
    result = pisa.CreatePDF(StringIO(html), dest=buf)
    if result.err:
        raise RuntimeError(f"xhtml2pdf reported {result.err} error(s)")
    return buf.getvalue()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=str(PROJECT_ROOT / "data" / "austin-2026-09-17" / "listings.csv.gz"))
    ap.add_argument("--listing-id", type=int, required=True)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--photo-count", type=int, default=None)
    ap.add_argument("--provider", choices=["gemini", "groq", "none"], default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from str_audit.audit import run_audit
    from str_audit.data import load_listings

    df = load_listings(args.data)
    provider = None if args.provider in (None, "none") else args.provider
    audit = run_audit(df, args.listing_id, k=args.k,
                      photo_count=args.photo_count, provider=provider)
    pdf = render_pdf(audit)

    out = Path(args.out) if args.out else DEFAULT_OUT_DIR / f"audit_{args.listing_id}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf)
    print(f"wrote {out}  ({len(pdf) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
