#!/usr/bin/env python3.11
"""
exec_pdf.py — Render a CEO-ready PDF from an AVR audit run.

Input:  path to an audit markdown file (audit_<DOMAIN>_<DATE>_<TS>.md)
        Auto-discovers sibling JSON artifacts (seo, ai, citations summary,
        visibility summary) in the same directory.

Output: audit_<DOMAIN>_<DATE>_<TS>_exec.pdf next to the input MD.

Pipeline:
  1. Load all artifacts
  2. Build a single HTML string with inline CSS + inline SVG charts
  3. Write HTML to a tempfile
  4. Shell out to Chrome --headless --print-to-pdf

No pip deps. Chrome must exist at /Applications/Google Chrome.app.

Usage:
    python3.11 exec_pdf.py <path-to-audit-md>
"""

from __future__ import annotations
import json
import re
import subprocess
import sys
import tempfile
import html
from datetime import datetime
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# ---------------------------------------------------------------------------
# Check labels & CEO-facing rationale
# ---------------------------------------------------------------------------
CHECK_META = {
    "1.1_core_web_vitals":        ("Page loading speed",        "Fast pages rank better in both search and AI answers."),
    "1.5_page_speed":             ("Page speed score",          "Lighthouse score — a speed proxy for ranking."),
    "1.2_technical_crawlability": ("Search engine access",      "Search engines and AI bots must be able to reach your pages."),
    "1.3_schema_markup":          ("Structured data (schema)",  "Schema tells AI what your business IS, not just what's on the page."),
    "1.6_content_indexability":   ("Indexability",              "Pages must be index-eligible (no noindex, canonical set)."),
    "2.1_ai_crawler_access":      ("AI bot access",             "GPTBot, ClaudeBot, PerplexityBot must be allowed in robots.txt."),
    "2.2_structured_data_depth":  ("Schema coverage (site-wide)", "≥80% of pages should carry structured data — not just the home page."),
    "2.3_content_structure":      ("Headings & content shape",  "Clean H1→H2→H3 hierarchy + short paragraphs = AI-retrievable passages."),
    "2.4_content_ratio":          ("Text-to-code ratio",        "Too much HTML code vs. actual text hides your content from AI."),
    "2.5_semantic_html":          ("Semantic HTML tags",        "<article>, <main>, <nav> tags help AI identify your real content."),
}

VERDICT_CLASS = {"PASS": "pass", "PARTIAL": "partial", "FAIL": "fail", "SKIPPED": "skipped"}
VERDICT_LABEL = {"PASS": "Passing", "PARTIAL": "Partial", "FAIL": "Failing", "SKIPPED": "Not tested"}

OVERALL_STATUS_CLASS = {
    "NOT-READY": "not-ready",
    "FOUNDATION-READY": "foundation",
    "INFRASTRUCTURE-READY": "infra",
    "AI-READY": "ready",
}


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def discover_siblings(md_path: Path) -> dict:
    base = md_path.stem  # audit_<DOMAIN>_<DATE>_<TS>
    m = re.match(r"^audit_(.+)_(\d{8})_(\d{6})$", base)
    if not m:
        raise ValueError(f"MD filename doesn't match expected shape: {md_path.name}")
    domain, date, ts = m.group(1), m.group(2), m.group(3)
    d = md_path.parent

    seo = d / f"audit_{domain}_{date}_{ts}_seo.json"
    ai  = d / f"audit_{domain}_{date}_{ts}_ai.json"

    # citations + visibility have their OWN timestamps (later than the scan)
    cit_matches = sorted(d.glob(f"citations_{domain}_{date}_*_summary.json"))
    vis_matches = sorted(d.glob(f"visibility_{domain}_{date}_*_summary.json"))

    return {
        "seo": seo if seo.exists() else None,
        "ai":  ai  if ai.exists()  else None,
        "citations":  cit_matches[-1] if cit_matches else None,
        "visibility": vis_matches[-1] if vis_matches else None,
        "domain": domain,
        "date": date,
        "ts": ts,
    }


def load_json(p: Path | None):
    if p is None or not p.exists():
        return None
    return json.loads(p.read_text())


def extract_md_header(md_path: Path) -> dict:
    """Pull client name, URL, date, and top-actions list from MD."""
    text = md_path.read_text()
    out = {"client": "Client", "url": "", "date": "", "overall": "NOT-READY", "actions": []}

    m = re.search(r"\*\*Prepared for:\*\* (.+)", text)
    if m: out["client"] = m.group(1).strip()
    m = re.search(r"\*\*URL audited:\*\* (.+)", text)
    if m: out["url"] = m.group(1).strip()
    m = re.search(r"\*\*Date:\*\* (.+)", text)
    if m: out["date"] = m.group(1).strip()
    m = re.search(r"\*\*Overall Status:\s*([A-Z\-]+)\*\*", text)
    if m: out["overall"] = m.group(1).strip()

    # Actions: lines after "### Top 3 Actions" until next "---"
    m = re.search(r"### Top \d+ Actions.*?\n\n(.+?)(?=\n---|\n##)", text, re.DOTALL)
    if m:
        lines = m.group(1).strip().split("\n")
        for line in lines:
            line = line.strip()
            m2 = re.match(r"^\d+\.\s+(.+)", line)
            if m2:
                out["actions"].append(m2.group(1).strip())
    return out


# ---------------------------------------------------------------------------
# SVG chart builders (pure, no deps)
# ---------------------------------------------------------------------------
def svg_gauge(label: str, pct: float, ci_low: float | None = None, ci_high: float | None = None,
              width: int = 240, height: int = 140) -> str:
    """Semicircle gauge from 0 (left) to 100 (right) with optional 95% CI band."""
    cx, cy, r = width / 2, height - 20, (width / 2) - 20
    pct = max(0, min(100, pct))

    def polar(p):
        import math
        theta = math.pi * (1 - p / 100)
        return cx + r * math.cos(theta), cy - r * math.sin(theta)

    # Arc path helper
    def arc_path(p0, p1, radius):
        import math
        x0, y0 = polar(p0)
        x1, y1 = polar(p1)
        large = 0
        return f"M {x0:.1f} {y0:.1f} A {radius} {radius} 0 {large} 1 {x1:.1f} {y1:.1f}"

    # Color by rate
    color = rate_color(pct)

    # Confidence-interval band (lighter)
    ci_band = ""
    if ci_low is not None and ci_high is not None:
        ci_band = f'<path d="{arc_path(ci_low, ci_high, r)}" stroke="{color}" stroke-width="12" fill="none" opacity="0.25" stroke-linecap="round" />'

    # Primary arc (0 → pct)
    arc = f'<path d="{arc_path(0, pct, r)}" stroke="{color}" stroke-width="12" fill="none" stroke-linecap="round" />'
    # Background track
    track = f'<path d="{arc_path(0, 100, r)}" stroke="#e5e7eb" stroke-width="12" fill="none" />'

    # Labels
    ci_text = ""
    if ci_low is not None and ci_high is not None:
        ci_text = f'<text x="{cx}" y="{cy+24}" text-anchor="middle" font-size="9" fill="#6b7280">95% CI: {ci_low:.0f}% – {ci_high:.0f}%</text>'

    return f"""
    <svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{width}px">
      {track}
      {ci_band}
      {arc}
      <text x="{cx}" y="{cy-6}" text-anchor="middle" font-size="28" font-weight="700" fill="#111827">{pct:.0f}%</text>
      <text x="{cx}" y="{cy+10}" text-anchor="middle" font-size="10" fill="#6b7280">{html.escape(label)}</text>
      {ci_text}
    </svg>
    """


def rate_color(pct: float) -> str:
    if pct >= 80: return "#10b981"
    if pct >= 50: return "#f59e0b"
    if pct >= 20: return "#f97316"
    return "#ef4444"


def svg_hbar(rows: list[tuple[str, float, str | None]], width: int = 500, bar_h: int = 28) -> str:
    """Horizontal bar chart. rows = [(label, pct, optional color), ...]."""
    row_gap = 10
    total_h = (bar_h + row_gap) * len(rows)
    label_w = 160
    value_w = 60
    track_w = width - label_w - value_w - 20

    svg_rows = []
    for i, row in enumerate(rows):
        label, pct, color = (row + (None,))[:3]
        pct = max(0, min(100, pct))
        c = color or rate_color(pct)
        y = i * (bar_h + row_gap)
        svg_rows.append(f"""
          <text x="0" y="{y + bar_h/2 + 4}" font-size="11" fill="#111827">{html.escape(label)}</text>
          <rect x="{label_w}" y="{y}" width="{track_w}" height="{bar_h}" fill="#f3f4f6" rx="4" />
          <rect x="{label_w}" y="{y}" width="{track_w * pct / 100:.1f}" height="{bar_h}" fill="{c}" rx="4" />
          <text x="{label_w + track_w + 8}" y="{y + bar_h/2 + 4}" font-size="12" font-weight="600" fill="#111827">{pct:.0f}%</text>
        """)
    return f"""
    <svg viewBox="0 0 {width} {total_h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{width}px">
      {''.join(svg_rows)}
    </svg>
    """


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
CSS = """
@page { size: letter; margin: 0.55in; }
@media print { .page-break { page-break-before: always; } }

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Inter', system-ui, sans-serif;
  color: #111827; font-size: 10.5pt; line-height: 1.5;
}
h1 { font-size: 26pt; margin: 0; font-weight: 700; letter-spacing: -0.02em; line-height: 1.15; }
h2 { font-size: 15pt; margin: 20pt 0 10pt 0; font-weight: 700; border-bottom: 1.5pt solid #e5e7eb; padding-bottom: 5pt; letter-spacing: -0.01em; }
h3 { font-size: 11.5pt; margin: 10pt 0 4pt 0; font-weight: 600; }
p { margin: 6pt 0; }
.muted { color: #6b7280; }
.small { font-size: 9pt; }

.brand {
  font-size: 9pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em;
  color: #0ea5e9; margin-bottom: 12pt;
}
.cover-meta {
  display: flex; flex-wrap: wrap; gap: 18pt; margin: 14pt 0 20pt 0;
  font-size: 10pt; color: #374151;
}
.cover-meta b { font-weight: 600; color: #111827; }

/* Overall-status banner */
.hero {
  display: flex; align-items: center; justify-content: space-between; gap: 20pt;
  padding: 18pt 22pt; border-radius: 10pt; margin: 16pt 0;
}
.hero-label { font-size: 10pt; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; opacity: 0.75; }
.hero-value { font-size: 26pt; font-weight: 800; letter-spacing: -0.02em; margin-top: 3pt; }
.hero-summary { flex: 1; font-size: 10.5pt; line-height: 1.5; }
.hero.not-ready { background: #fef2f2; color: #7f1d1d; border: 1pt solid #fecaca; }
.hero.foundation { background: #fffbeb; color: #78350f; border: 1pt solid #fde68a; }
.hero.infra { background: #f0f9ff; color: #075985; border: 1pt solid #bae6fd; }
.hero.ready { background: #f0fdf4; color: #14532d; border: 1pt solid #bbf7d0; }

/* Score cards grid */
.grid-4 {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10pt; margin: 12pt 0;
}
.card {
  border: 1pt solid #e5e7eb; border-radius: 8pt; padding: 12pt 14pt; background: white;
  break-inside: avoid;
}
.card .label { font-size: 9pt; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }
.card .metric { font-size: 20pt; font-weight: 700; margin-top: 2pt; line-height: 1.1; letter-spacing: -0.02em; }
.card .sub { font-size: 9pt; color: #6b7280; margin-top: 3pt; }
.card .status-chip { display: inline-block; font-size: 9pt; padding: 2pt 8pt; border-radius: 99pt; font-weight: 600; margin-top: 5pt; }
.status-chip.pass    { background: #d1fae5; color: #065f46; }
.status-chip.partial { background: #fef3c7; color: #78350f; }
.status-chip.fail    { background: #fee2e2; color: #7f1d1d; }
.status-chip.skipped { background: #f3f4f6; color: #374151; }

.chart-block { padding: 14pt; border: 1pt solid #e5e7eb; border-radius: 8pt; margin: 10pt 0; background: white; break-inside: avoid; }
.chart-block .chart-title { font-size: 11.5pt; font-weight: 600; margin-bottom: 3pt; }
.chart-block .chart-sub { font-size: 9pt; color: #6b7280; margin-bottom: 10pt; }
.chart-block .interpretation { font-size: 10pt; color: #374151; margin-top: 10pt; line-height: 1.5; padding: 10pt; background: #f9fafb; border-radius: 6pt; border-left: 3pt solid #0ea5e9; }

/* Checks table */
table.checks { width: 100%; border-collapse: collapse; font-size: 10pt; }
table.checks th, table.checks td { text-align: left; padding: 8pt 10pt; border-bottom: 1pt solid #f3f4f6; vertical-align: top; }
table.checks th { background: #f9fafb; font-size: 8.5pt; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; border-bottom: 1.5pt solid #e5e7eb; }
table.checks td .check-name { font-weight: 600; }
table.checks td .check-why { font-size: 9pt; color: #6b7280; margin-top: 2pt; }

/* Action cards */
.action-list { display: flex; flex-direction: column; gap: 8pt; }
.action-card {
  display: flex; gap: 12pt; align-items: flex-start;
  border: 1pt solid #e5e7eb; border-left: 3.5pt solid #0ea5e9;
  padding: 12pt 14pt; border-radius: 6pt; background: white;
  break-inside: avoid;
}
.action-num {
  width: 24pt; height: 24pt; border-radius: 50%;
  background: #0ea5e9; color: white; font-weight: 700; font-size: 11pt;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1pt;
}
.action-body { flex: 1; font-size: 10.5pt; line-height: 1.5; }
.action-body .title { font-weight: 600; margin-bottom: 2pt; }
.action-body .why { font-size: 9pt; color: #6b7280; }

.footer {
  margin-top: 18pt; padding-top: 10pt; border-top: 1pt solid #e5e7eb;
  font-size: 8.5pt; color: #6b7280; line-height: 1.5;
}
.footer b { color: #374151; }
"""


def classify_overall(overall: str) -> str:
    return OVERALL_STATUS_CLASS.get(overall, "not-ready")


def section_verdict(checks: list[dict]) -> str:
    """Given a list of check dicts, return overall section verdict."""
    vs = [c.get("verdict", "SKIPPED") for c in checks]
    if "FAIL" in vs:
        return "FAIL"
    if "PARTIAL" in vs:
        return "PARTIAL"
    non_skip = [v for v in vs if v != "SKIPPED"]
    if not non_skip:
        return "SKIPPED"
    if all(v == "PASS" for v in non_skip):
        return "PASS"
    return "PARTIAL"


def exec_summary_text(overall: str, seo_v: str, ai_v: str, cit_pct: float, vis_pct: float) -> str:
    """Plain-English verdict for the hero banner."""
    if overall == "NOT-READY":
        if seo_v == "PASS" and ai_v in ("FAIL", "PARTIAL"):
            return "Search foundations are solid, but the AI-readiness layer needs work before AI systems will cite you reliably."
        if ai_v == "FAIL":
            return "AI systems currently can't extract clean content from your site. Fix the technical layer first — content investment before that is wasted."
        if seo_v in ("FAIL", "PARTIAL") and ai_v in ("FAIL", "PARTIAL"):
            return "Both the SEO foundation and the AI-readiness layer need work. Start with SEO — AI visibility can't exist without search visibility."
    if overall == "FOUNDATION-READY":
        return "Search foundations are solid. Next priority: build the structured-data + semantic-HTML layer that AI systems read."
    if overall == "INFRASTRUCTURE-READY":
        return "Technically AI-ready. Next priority: topical-cluster content + entity-authority work so AI doesn't just find you — it recommends you."
    if overall == "AI-READY":
        return "You're in the minority. Now it's a game of ongoing content freshness, entity authority, and citation monitoring."
    return "See section-by-section detail for the specific fixes."


def render_check_row(chk: dict) -> str:
    cid = chk.get("check", "")
    verdict = chk.get("verdict", "SKIPPED")
    label, why = CHECK_META.get(cid, (cid.replace("_", " ").title(), ""))
    cls = VERDICT_CLASS.get(verdict, "skipped")
    return f"""
      <tr>
        <td>
          <div class="check-name">{html.escape(label)}</div>
          <div class="check-why">{html.escape(why)}</div>
        </td>
        <td><span class="status-chip {cls}">{html.escape(VERDICT_LABEL.get(verdict, verdict))}</span></td>
      </tr>
    """


def humanize_action(raw: str) -> tuple[str, str]:
    """Map raw recommendation to (title, why)."""
    r = raw.lower()
    if "schema markup" in r or "structured data" in r or "schema" in r and "coverage" in r:
        return ("Add structured data (schema) to more pages",
                "Aim for ≥80% site-wide coverage. Schema tells AI what your services ARE — essential for recommendation-type queries.")
    if "text-to-html" in r or "text-to-code" in r or "content ratio" in r:
        return ("Increase the text-to-code ratio on key pages",
                "Framework overhead is hiding your actual content from AI extractors. Add more substantive text or trim unused markup.")
    if "semantic html" in r or "<article>" in r:
        return ("Use semantic HTML tags (<article>, <main>, <nav>, <section>)",
                "Generic <div> soup forces AI to guess at structure. Semantic tags make retrieval precise.")
    if "alt text" in r or "image alt" in r:
        return ("Add descriptive alt text to all images",
                "Alt text is indexable content. Low coverage is easy points left on the table.")
    if "faq" in r:
        return ("Add an FAQ section with FAQPage schema",
                "FAQ-shaped content matches how LLMs re-query the web (3-10 paraphrases per user question).")
    if "improve" in r:
        return (raw.strip().rstrip("."),
                "See technical details in the full breakdown.")
    return (raw.strip().rstrip("."), "")


def render_html(md_info: dict, siblings: dict, seo: dict, ai: dict, citations: dict, visibility: dict) -> str:
    client = md_info["client"]
    url = md_info["url"]
    date_str = md_info["date"]
    overall = md_info["overall"]
    overall_class = classify_overall(overall)

    seo_checks = seo.get("checks", []) if seo else []
    ai_checks = ai.get("checks", []) if ai else []

    seo_v = section_verdict(seo_checks)
    ai_v = section_verdict(ai_checks)

    cit_pct = citations.get("citation_rate_pct", 0.0) if citations else 0.0
    cit_cited = citations.get("cited_count", 0) if citations else 0
    cit_total = citations.get("testable", 0) if citations else 0
    cit_ci = citations.get("confidence_interval_95", {}) if citations else {}
    cit_verdict = citations.get("verdict", "UNKNOWN") if citations else "UNKNOWN"
    cit_conf = citations.get("confidence_label", "LOW") if citations else "LOW"

    vis_pct = visibility.get("visibility_rate_pct", 0.0) if visibility else 0.0
    vis_cats = visibility.get("by_category", {}) if visibility else {}
    vis_verdict = visibility.get("verdict", "UNKNOWN") if visibility else "UNKNOWN"

    exec_blurb = exec_summary_text(overall, seo_v, ai_v, cit_pct, vis_pct)

    # 4-card scorecard
    scorecards = [
        ("SEO Foundation", VERDICT_LABEL.get(seo_v, seo_v), VERDICT_CLASS.get(seo_v, "skipped"),
         f"{sum(1 for c in seo_checks if c.get('verdict')=='PASS')}/{sum(1 for c in seo_checks if c.get('verdict') in ('PASS','PARTIAL','FAIL'))} checks passing"),
        ("AI Infrastructure", VERDICT_LABEL.get(ai_v, ai_v), VERDICT_CLASS.get(ai_v, "skipped"),
         f"{sum(1 for c in ai_checks if c.get('verdict')=='PASS')}/{sum(1 for c in ai_checks if c.get('verdict') in ('PASS','PARTIAL','FAIL'))} checks passing"),
        ("AI Citations", f"{cit_pct:.0f}% cited", f"cited-{cit_conf.lower()}",
         f"{cit_cited} of {cit_total} queries cited you as source"),
        ("AI Visibility", f"{vis_pct:.0f}% visible", f"cited-{cit_conf.lower()}",
         f"{visibility.get('visible_count', 0) if visibility else 0} of {visibility.get('total_tests', 0) if visibility else 0} queries knew about you"),
    ]

    score_cards_html = ""
    for label, value, cls_raw, sub in scorecards:
        # map status classes for chips
        chip_cls = cls_raw if cls_raw in ("pass", "partial", "fail", "skipped") else ""
        if not chip_cls:
            # for citation/visibility percentages, derive from raw value
            pct_match = re.search(r"(\d+)%", value)
            if pct_match:
                p = int(pct_match.group(1))
                chip_cls = "pass" if p >= 80 else "partial" if p >= 40 else "fail"
        score_cards_html += f"""
          <div class="card">
            <div class="label">{html.escape(label)}</div>
            <div class="metric">{html.escape(value)}</div>
            <div class="sub">{html.escape(sub)}</div>
            <span class="status-chip {chip_cls}">&nbsp;</span>
          </div>
        """

    # Citation gauge
    ci_low = cit_ci.get("low_pct")
    ci_high = cit_ci.get("high_pct")
    citation_gauge = svg_gauge("Citation rate", cit_pct, ci_low, ci_high, width=260, height=160)

    # Visibility breakdown chart
    def cat_rate(k): return vis_cats.get(k, {}).get("rate_pct", 0.0)
    visibility_chart = svg_hbar([
        ("Brand recognition",   cat_rate("brand_recognition"),   None),
        ("Concept attribution", cat_rate("concept_attribution"), None),
        ("Being recommended",   cat_rate("recommendation"),      None),
    ], width=500, bar_h=26)

    # Check rows
    all_checks = seo_checks + ai_checks
    # order: fail → partial → pass → skipped
    order = {"FAIL": 0, "PARTIAL": 1, "PASS": 2, "SKIPPED": 3}
    all_checks_sorted = sorted(all_checks, key=lambda c: order.get(c.get("verdict", "SKIPPED"), 99))
    checks_table_rows = "\n".join(render_check_row(c) for c in all_checks_sorted)

    # Actions
    actions_html = ""
    for i, raw in enumerate(md_info["actions"][:5], start=1):
        title, why = humanize_action(raw)
        actions_html += f"""
          <div class="action-card">
            <div class="action-num">{i}</div>
            <div class="action-body">
              <div class="title">{html.escape(title)}</div>
              {"<div class='why'>" + html.escape(why) + "</div>" if why else ""}
            </div>
          </div>
        """
    if not actions_html:
        actions_html = "<p class='muted'>All automated checks passed. Focus next on entity authority (Wikipedia/Wikidata) and topical-cluster content.</p>"

    # Interpretation text
    cit_interp = cit_interpretation(cit_pct, cit_verdict, ci_low, ci_high)
    vis_interp = vis_interpretation(vis_cats, vis_verdict)

    # ---- assemble ----
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AVR Report — {html.escape(client)}</title>
  <style>{CSS}</style>
</head>
<body>

  <!-- ======================================================= PAGE 1 -->
  <div class="brand">AI Visibility Readiness Audit — AVR v1.0.0</div>
  <h1>{html.escape(client)}</h1>
  <div class="cover-meta">
    <div><b>URL audited:</b> {html.escape(url)}</div>
    <div><b>Date:</b> {html.escape(date_str)}</div>
    <div><b>Prepared by:</b> Chudi Nnorukam</div>
  </div>

  <div class="hero {overall_class}">
    <div>
      <div class="hero-label">Overall status</div>
      <div class="hero-value">{html.escape(overall.replace('-', ' '))}</div>
    </div>
    <div class="hero-summary">{html.escape(exec_blurb)}</div>
  </div>

  <h2>Executive scorecard</h2>
  <div class="grid-4">
    {score_cards_html}
  </div>

  <p class="muted small" style="margin-top:16pt">
    This audit tests two layers: <b>SEO Foundation</b> (can search engines and AI bots reach your pages?)
    and <b>AI Infrastructure</b> (can AI systems extract and understand your content?).
    Then it measures two outcomes: <b>AI Citations</b> (do answers link to you?) and <b>AI Visibility</b> (do AI systems KNOW about you?).
  </p>

  <!-- ======================================================= PAGE 2 -->
  <div class="page-break"></div>
  <h2>How AI sees you today</h2>

  <div class="chart-block">
    <div class="chart-title">AI Citation Rate — {cit_pct:.0f}%</div>
    <div class="chart-sub">
      How often ChatGPT linked to your URL when asked {cit_total} real questions about your domain and services.
    </div>
    <div style="display:flex; gap:20pt; align-items:center;">
      <div style="flex:0 0 260px;">{citation_gauge}</div>
      <div class="interpretation" style="flex:1; margin-top:0;">{cit_interp}</div>
    </div>
  </div>

  <div class="chart-block">
    <div class="chart-title">Visibility by signal type</div>
    <div class="chart-sub">
      Brand recognition is the easy signal — ChatGPT confirms your business exists. The other two are the ones that drive referrals.
    </div>
    {visibility_chart}
    <div class="interpretation">{vis_interp}</div>
  </div>

  <!-- ======================================================= PAGE 3 -->
  <div class="page-break"></div>
  <h2>Technical checks</h2>
  <p class="muted small" style="margin-top:0">
    {len([c for c in all_checks if c.get('verdict') == 'PASS'])} passing,
    {len([c for c in all_checks if c.get('verdict') == 'PARTIAL'])} partial,
    {len([c for c in all_checks if c.get('verdict') == 'FAIL'])} failing,
    {len([c for c in all_checks if c.get('verdict') == 'SKIPPED'])} not tested.
    Every check is VERIFIABLE — reproducible from raw HTML/HTTP, no judgment call involved.
  </p>
  <table class="checks">
    <thead><tr><th>Check</th><th style="width:110pt">Status</th></tr></thead>
    <tbody>
      {checks_table_rows}
    </tbody>
  </table>

  <!-- ======================================================= PAGE 4 -->
  <div class="page-break"></div>
  <h2>Priority actions</h2>
  <p class="muted small" style="margin-top:0">
    These are the highest-leverage fixes, in order. Addressing all of them moves the site from <b>{html.escape(overall.replace('-', ' '))}</b> toward FOUNDATION-READY or better.
  </p>
  <div class="action-list">
    {actions_html}
  </div>

  <h3 style="margin-top:20pt">Beyond the checklist</h3>
  <p>
    Passing all technical checks gets you to <b>retrievable</b>. To go from retrievable to
    <b>recommended</b> requires two parallel investments:
  </p>
  <ul>
    <li><b>Topical depth</b> — 8–15 posts per pillar topic (not one-off articles) so you compound as a topical authority.</li>
    <li><b>Entity authority</b> — Wikipedia, Wikidata, local health/business directories, press mentions. This is what teaches AI that you're a legitimate entity to recommend in "best X" queries.</li>
  </ul>

  <div class="footer">
    <div><b>Methodology.</b> Every check is labeled [VERIFIABLE] or [BEST-EFFORT]. We do not combine these tiers into a single composite score — that would hide which tier is failing. Citation and visibility measurements are point-in-time samples with explicit 95% confidence intervals. Re-run monthly to track trends.</div>
    <div style="margin-top:6pt">Framework: AVR v1.0.0 · Generated {datetime.now().strftime('%B %d, %Y')} · Prepared by Chudi Nnorukam</div>
  </div>

</body>
</html>
"""


def cit_interpretation(pct: float, verdict: str, ci_low, ci_high) -> str:
    if pct >= 60:
        return ("ChatGPT cites you in the majority of relevant queries — a strong signal. Focus now shifts to "
                "WHICH queries cite you and WHICH don't, so you can close specific content gaps.")
    if pct >= 20:
        return (f"ChatGPT cites you sometimes, but inconsistently. The {ci_low:.0f}–{ci_high:.0f}% confidence range is wide, "
                "which typically means citation fires on brand-named queries but not on the topic-based queries buyers actually ask. "
                "The fix is topical-cluster content matching how real questions get phrased.")
    return ("ChatGPT rarely links back to your site. This is almost always a combined structured-data + topical-authority gap. "
            "Start with the technical fixes on the previous page, then layer in cluster content.")


def vis_interpretation(vis_cats: dict, verdict: str) -> str:
    br = vis_cats.get("brand_recognition", {}).get("rate_pct", 0.0)
    ca = vis_cats.get("concept_attribution", {}).get("rate_pct", 0.0)
    rec = vis_cats.get("recommendation", {}).get("rate_pct", 0.0)
    if br >= 80 and ca < 30 and rec < 30:
        return ("Classic 'brand known, topical authority zero' pattern. ChatGPT confirms you exist when asked directly, "
                "but won't recommend you when someone asks 'best [your category] in [your city]'. "
                "That's the pattern this framework is designed to fix: entity authority + topical depth work in parallel.")
    if ca >= 40 or rec >= 40:
        return ("You've crossed from brand-recognition-only into genuine topical authority. Keep building — the next "
                "threshold (recommendation >60%) is where 'AI-as-channel' becomes a real acquisition channel.")
    return ("Mixed signals. See the per-query detail in the raw data for which prompts fired and which didn't.")


# ---------------------------------------------------------------------------
# Chrome headless → PDF
# ---------------------------------------------------------------------------
def render_pdf(html_str: str, out_path: Path) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
        fh.write(html_str)
        html_path = fh.name
    try:
        cmd = [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=5000",
            "--no-pdf-header-footer",
            f"--print-to-pdf={out_path}",
            f"file://{html_path}",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            print("Chrome stderr:", r.stderr, file=sys.stderr)
            print("Chrome stdout:", r.stdout, file=sys.stderr)
            raise RuntimeError(f"Chrome exit {r.returncode}")
    finally:
        Path(html_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) != 2:
        print("Usage: python3.11 exec_pdf.py <path-to-audit-md>", file=sys.stderr)
        sys.exit(2)

    md_path = Path(sys.argv[1]).resolve()
    if not md_path.exists():
        print(f"Not found: {md_path}", file=sys.stderr)
        sys.exit(1)

    siblings = discover_siblings(md_path)
    md_info = extract_md_header(md_path)
    seo = load_json(siblings["seo"]) or {}
    ai = load_json(siblings["ai"]) or {}
    citations = load_json(siblings["citations"]) or {}
    visibility = load_json(siblings["visibility"]) or {}

    html_str = render_html(md_info, siblings, seo, ai, citations, visibility)

    out_pdf = md_path.with_name(md_path.stem + "_exec.pdf")
    # Optionally also persist the HTML for debug:
    out_html = md_path.with_name(md_path.stem + "_exec.html")
    out_html.write_text(html_str)

    render_pdf(html_str, out_pdf)
    print(f"OK  HTML: {out_html}")
    print(f"OK  PDF:  {out_pdf}")


if __name__ == "__main__":
    main()
