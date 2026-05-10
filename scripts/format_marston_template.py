#!/usr/bin/env python3
"""
Marston Weekly Update Template Adapter

Reads audit output JSONs (seo, ai, citations summary, visibility summary)
and emits the fields needed to fill marston-weekly-update-template-v1.md.

Computed fields are populated from the audit data. Manual fields (what we
did, what we'll do, asks for Marston) remain as {{placeholders}} so the
operator can complete them before posting.

Usage:
  # Point at a specific audit base name
  python format_marston_template.py --audit-base audit_marstonorthodontics.com_20260507_181500 --audit-dir ../sample-audits --week 1

  # Or auto-pick the newest audit_*_ai.json in a dir
  python format_marston_template.py --audit-dir ../sample-audits --week 1

Output: paste-ready markdown to stdout. Save by redirecting to a file:
  python format_marston_template.py --audit-dir ../sample-audits --week 1 > week1-draft.md

The output mirrors marston-weekly-update-template-v1.md verbatim where the
template has free-text or operator-judgment fields. Numbers come from the
loaded JSONs and never get fabricated; missing data shows as "(pending)".
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------- File loading ----------


def _load_json(path: str) -> dict | None:
    """Load JSON from path, return None on any failure."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _newest_match(audit_dir: str, pattern: str) -> str | None:
    """Return the most-recently-modified file matching pattern in audit_dir."""
    matches = glob.glob(os.path.join(audit_dir, pattern))
    if not matches:
        return None
    matches.sort(key=os.path.getmtime, reverse=True)
    return matches[0]


def discover_audit_files(audit_dir: str, audit_base: str | None) -> dict:
    """Locate the four audit JSONs.

    If audit_base is provided, looks for exact-base matches. Otherwise
    picks the newest of each kind in audit_dir. Returns dict with keys:
    seo, ai, citations, visibility (any may be None).
    """
    audit_dir = os.path.abspath(audit_dir)

    if audit_base:
        seo_path = os.path.join(audit_dir, f"{audit_base}_seo.json")
        ai_path = os.path.join(audit_dir, f"{audit_base}_ai.json")
    else:
        seo_path = _newest_match(audit_dir, "audit_*_seo.json")
        ai_path = _newest_match(audit_dir, "audit_*_ai.json")

    citations_path = _newest_match(audit_dir, "citations_*_summary.json")
    visibility_path = _newest_match(audit_dir, "visibility_*_summary.json")

    return {
        "seo": _load_json(seo_path) if seo_path else None,
        "ai": _load_json(ai_path) if ai_path else None,
        "citations": _load_json(citations_path) if citations_path else None,
        "visibility": _load_json(visibility_path) if visibility_path else None,
        "_paths": {
            "seo": seo_path,
            "ai": ai_path,
            "citations": citations_path,
            "visibility": visibility_path,
        },
    }


# ---------- Field extraction ----------


def _pct(numerator: float | int | None, denominator: float | int | None) -> str:
    """Format a percentage from numerator/denominator. Returns '(pending)' when None."""
    if numerator is None or denominator is None or denominator == 0:
        return "(pending)"
    return f"{round(100.0 * numerator / denominator, 1)}%"


def _safe_get(d: dict | None, *keys, default=None):
    """Walk nested dict keys, return default if any step is missing."""
    if d is None:
        return default
    cur: object = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def extract_fields(loaded: dict) -> dict:
    """Map raw audit JSONs to template field names.

    Field names mirror the {{placeholder}} tokens in
    marston-weekly-update-template-v1.md. Where the audit cannot supply a
    number (citations test not run, etc), the field is "(pending)".
    """
    citations = loaded.get("citations") or {}
    visibility = loaded.get("visibility") or {}
    seo = loaded.get("seo") or {}
    ai = loaded.get("ai") or {}

    # Visibility score: prefer visibility_summary's overall verdict + numbers
    # citability.dev reports per-category visibility (brand, concept, recommendation).
    # The template's "Visibility Score" maps most cleanly to overall visibility_rate_pct.
    vis_pct = _safe_get(visibility, "visibility_rate_pct")
    vis_verdict = _safe_get(visibility, "verdict")
    by_cat = _safe_get(visibility, "by_category", default={}) or {}

    # Engines tested = unique platforms across either visibility or citation runs.
    # Dedupe case-insensitively because platforms_tested uses lowercase keys
    # ("openai") while by_platform uses display names ("ChatGPT"). Map both
    # to display names for the user-facing list.
    _key_to_display = {
        "openai": "ChatGPT",
        "perplexity": "Perplexity",
        "anthropic": "Claude",
        "gemini": "Gemini",
    }
    engines_set: set[str] = set()
    for run_key in ("citations", "visibility"):
        run = loaded.get(run_key) or {}
        for p in (_safe_get(run, "platforms_tested", default=[]) or []):
            engines_set.add(_key_to_display.get(p.lower(), p))
        for p in (_safe_get(run, "by_platform", default={}) or {}).keys():
            engines_set.add(_key_to_display.get(p.lower(), p))
    engines_tested_n = len(engines_set)
    engines_label = ", ".join(sorted(engines_set)) if engines_set else "(pending)"

    # Citation count (testable = total - errors; this is the right denominator
    # for a citation rate, not total_tests which includes errored queries)
    citation_count = _safe_get(citations, "cited_count")
    total_citation_queries = _safe_get(citations, "testable") or _safe_get(citations, "total_tests")
    citation_rate_pct = _safe_get(citations, "citation_rate_pct")
    citation_verdict = _safe_get(citations, "verdict")
    citation_ci = _safe_get(citations, "confidence_interval_95", default={}) or {}
    citation_confidence = _safe_get(citations, "confidence_label", default="LOW")
    citation_errors = _safe_get(citations, "errors", default=0)

    # Receipt: prefer explicit report_id, fall back to test_date or audit_base
    receipt = (
        _safe_get(citations, "report_id")
        or _safe_get(citations, "run_id")
        or _safe_get(visibility, "report_id")
        or _safe_get(citations, "test_date")
        or "(pending)"
    )

    # Brand mention rate (from visibility's by_category if available)
    brand_recog = by_cat.get("brand_recognition") or {}
    brand_visible = brand_recog.get("visible")
    brand_total = brand_recog.get("total")

    # AI infrastructure verdict + verticals checks
    ai_verdict = _safe_get(ai, "section_verdict")
    rich_types_matched = []
    rich_types_expected = []
    for check in (ai.get("checks") or []):
        if check.get("check") == "2.2_structured_data_depth":
            details = check.get("details") or {}
            rich_types_matched = details.get("rich_types_matched", []) or []
            rich_types_expected = details.get("rich_types_expected", []) or []
            break

    return {
        # Visibility (above the fold)
        "visibility_pct": f"{vis_pct}%" if vis_pct is not None else "(pending)",
        "visibility_verdict": vis_verdict or "(pending)",
        "engines_tested_n": engines_tested_n if engines_tested_n else "(pending)",
        "engines_label": engines_label,
        "receipt": receipt,
        # Where Marston shows up
        "brand_visible": f"{brand_visible}/{brand_total}" if brand_visible is not None and brand_total else "(pending)",
        "citation_count": citation_count if citation_count is not None else "(pending)",
        "citation_total": total_citation_queries if total_citation_queries is not None else "(pending)",
        "citation_rate_pct": f"{citation_rate_pct}%" if citation_rate_pct is not None else _pct(citation_count, total_citation_queries),
        "citation_verdict": citation_verdict or "(pending)",
        "citation_ci_low": citation_ci.get("low_pct"),
        "citation_ci_high": citation_ci.get("high_pct"),
        "citation_confidence": citation_confidence,
        "citation_errors": citation_errors,
        # AI infrastructure
        "ai_verdict": ai_verdict or "(pending)",
        "rich_types_matched": rich_types_matched,
        "rich_types_expected": rich_types_expected,
        # SEO
        "seo_verdict": _safe_get(seo, "section_verdict") or "(pending)",
        # Per-category visibility for finer-grained rendering
        "by_category": by_cat,
        # Per-category citation breakdown (different from visibility by_category)
        "citations_by_category": _safe_get(citations, "by_category", default={}) or {},
    }


# ---------- Template rendering ----------


def render_template(fields: dict, week: int, iso_date: str, status_emoji: str) -> str:
    """Render the marston-weekly-update-template-v1.md filled-in form.

    Manual fields (what we did, what we'll do, asks) stay as {{placeholders}}
    so the operator can fill them in the saved draft before posting.
    """
    by_cat = fields.get("by_category", {}) or {}
    brand_recog = by_cat.get("brand_recognition") or {}
    concept_attr = by_cat.get("concept_attribution") or {}
    recommendation = by_cat.get("recommendation") or {}

    rich_matched = fields.get("rich_types_matched") or []
    rich_expected = fields.get("rich_types_expected") or []
    rich_missing = [t for t in rich_expected if t not in rich_matched] if rich_expected else []

    # Format the schema-coverage line
    if rich_matched:
        schema_line = f"Found: {', '.join(rich_matched)}"
    else:
        schema_line = "Found: none of the expected vertical-rich types"
    if rich_missing:
        schema_line += f" · Missing: {', '.join(rich_missing[:6])}"
        if len(rich_missing) > 6:
            schema_line += f" (+{len(rich_missing) - 6} more)"

    # Confidence interval line (chudi-frame trust-artifact discipline:
    # numbers without uncertainty are misleading)
    ci_line = ""
    if fields.get("citation_ci_low") is not None and fields.get("citation_ci_high") is not None:
        ci_line = f" · 95% CI: [{fields['citation_ci_low']}%, {fields['citation_ci_high']}%]"
    confidence = fields.get("citation_confidence", "LOW")
    errors_note = ""
    if fields.get("citation_errors", 0) > 0:
        errors_note = f" · errors: {fields['citation_errors']} (engine outages, not real misses)"

    # Per-category citation breakdown (the load-bearing detail)
    cat = fields.get("citations_by_category", {}) or {}
    cat_brand = cat.get("brand", {}) or {}
    cat_topic = cat.get("topic_authority", {}) or {}
    cat_long = cat.get("long_tail", {}) or {}
    cat_comp = cat.get("competitor", {}) or {}

    out = f"""*Marston Orthodontics, Found for GEO Weekly, Week {week}*
{iso_date} · status: {status_emoji}

*▸ Citations this week (does AI cite marstonorthodontics.com?)*
{fields['citation_rate_pct']} · verdict: {fields['citation_verdict']} · confidence: {confidence}{ci_line}
{fields['citation_count']} cited / {fields['citation_total']} testable queries{errors_note}
By query type:
- Brand-name queries: {cat_brand.get('cited', '?')}/{cat_brand.get('total', '?')} cited ({cat_brand.get('citation_rate_pct', '?')}%)
- Topic-authority queries: {cat_topic.get('cited', '?')}/{cat_topic.get('total', '?')} cited ({cat_topic.get('citation_rate_pct', '?')}%)
- Long-tail queries: {cat_long.get('cited', '?')}/{cat_long.get('total', '?')} cited ({cat_long.get('citation_rate_pct', '?')}%)
- Competitor-comparison queries: {cat_comp.get('cited', '?')}/{cat_comp.get('total', '?')} cited ({cat_comp.get('citation_rate_pct', '?')}%)
_AI engines tested: {fields['engines_tested_n']} ({fields['engines_label']}) · receipt: {fields['receipt']}_

*▸ Visibility this week (does AI know who Marston is?)*
{fields['visibility_pct']} aggregate · verdict: {fields['visibility_verdict']}
- Brand recognition: {brand_recog.get('visible', '(pending)')}/{brand_recog.get('total', '(pending)')} = {brand_recog.get('rate_pct', '(pending)')}%
- Topic association: {concept_attr.get('visible', '(pending)')}/{concept_attr.get('total', '(pending)')} = {concept_attr.get('rate_pct', '(pending)')}%
- Active recommendation: {recommendation.get('visible', '(pending)')}/{recommendation.get('total', '(pending)')} = {recommendation.get('rate_pct', '(pending)')}%

*▸ Site infrastructure (audit Section 2)*
- AI Infrastructure verdict: {fields['ai_verdict']}
- SEO Foundation verdict: {fields['seo_verdict']}
- Vertical-rich schema check: {schema_line}

*▸ Top 5 competitors AI keeps recommending*
{{{{Pull from CrowdReply Brand Report 'How you compare' table — Top 5 with delta vs last week}}}}
_Note: at baseline, expect DTC aligners (Invisalign, Candid, ALIGNERCO, Smileie, Byte). The opportunity is to make AI surface Marston as the local-practice option for queries with local intent._

*▸ Website tweaks for Dr. Marston (or website guy)*
{{{{Pull failing AI Infrastructure checks + missing vertical schema types — actionable list}}}}
{f"Specifically: add JSON-LD for {', '.join(rich_missing[:3])} schema types." if rich_missing else "All expected vertical schema types present (or audit not yet run)."}

*▸ What we did this week*
{{{{Manual: comments posted, threads engaged, upvotes earned}}}}
{{{{Manual: threads worth flagging with outcome}}}}

*▸ What we'll do next week*
{{{{Manual: specific actions 1-3}}}}
{{{{Manual: target — specific measurable goal}}}}

*▸ Asks for Dr. Marston*
{{{{Manual: specific request OR "Nothing this week — we have what we need."}}}}

*▸ Receipts*
- citability.dev audit: {fields['receipt']}
- CrowdReply Brand Report: {{{{paste URL}}}}
- Engagement activity log: {{{{paste URL}}}}
"""
    return out


# ---------- CLI ----------


def main():
    parser = argparse.ArgumentParser(
        description="Format audit JSONs into the marston-weekly-update-template-v1 fields",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--audit-dir", default=".",
                        help="Directory holding the audit_*.json + citations_*.json + visibility_*.json files")
    parser.add_argument("--audit-base",
                        help="Audit base name (e.g. audit_marstonorthodontics.com_20260507_181500). Auto-pick newest if omitted.")
    parser.add_argument("--week", type=int, default=1, help="Week number for header (default: 1)")
    parser.add_argument("--date", help="ISO date for header (default: today UTC)")
    parser.add_argument("--status", choices=["on-track", "watch", "blocked"], default="on-track",
                        help="Status emoji for header")
    args = parser.parse_args()

    iso_date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status_emoji = {"on-track": "🟢 on-track", "watch": "🟡 watch", "blocked": "🔴 blocked"}[args.status]

    loaded = discover_audit_files(args.audit_dir, args.audit_base)

    # Print which files were found to stderr so the operator sees the discovery
    paths = loaded.get("_paths", {})
    sys.stderr.write("Audit files discovered:\n")
    for k in ("seo", "ai", "citations", "visibility"):
        sys.stderr.write(f"  {k}: {paths.get(k) or '(none)'}\n")
    sys.stderr.write("\n")

    fields = extract_fields(loaded)
    output = render_template(fields, args.week, iso_date, status_emoji)
    sys.stdout.write(output)


if __name__ == "__main__":
    main()
