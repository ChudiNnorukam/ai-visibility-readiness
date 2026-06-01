#!/usr/bin/env python3
"""
Marston Weekly Update Template Adapter

Reads audit output JSONs (seo, ai, citations summary, visibility summary)
and emits the fields needed to fill marston-weekly-update-template-v1.md.

Computed fields are populated from the audit data. The analysis paragraph
and next-step recommendations are auto-drafted from the deltas between the
current and prior audit by calling Claude Haiku. Use --no-auto-draft to
fall back to operator-filled {{placeholders}}.

Usage:
  # Point at a specific audit base name; prior audit auto-discovered
  python format_marston_template.py --audit-base audit_marstonorthodontics.com_20260518_210713 --audit-dir ../sample-audits --week 2

  # Or auto-pick the newest audit_*_ai.json in a dir
  python format_marston_template.py --audit-dir ../sample-audits --week 2

  # Fall back to placeholders (no API call)
  python format_marston_template.py --audit-dir ../sample-audits --no-auto-draft

Output: paste-ready markdown to stdout. Save by redirecting to a file:
  python format_marston_template.py --audit-dir ../sample-audits --week 2 > week2-draft.md

The output mirrors marston-weekly-update-template-v1.md verbatim where the
template has free-text or operator-judgment fields. Numbers come from the
loaded JSONs and never get fabricated; missing data shows as "(pending)".
The auto-draft uses ONLY the verbatim numbers passed to it; the model is
instructed to never invent metrics.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple


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


def _date_prefix_from_base(audit_base: str) -> str | None:
    """Extract the 8-digit YYYYMMDD date prefix from an audit base name.

    Example: 'audit_marstonorthodontics.com_20260518_210713' -> '20260518'.
    Returns None if no 8-digit run is present.
    """
    m = re.search(r"(\d{8})_\d{6}", audit_base)
    return m.group(1) if m else None


def _domain_from_base(audit_base: str) -> str | None:
    """Extract the domain from an audit base name.

    Example: 'audit_marstonorthodontics.com_20260518_210713' -> 'marstonorthodontics.com'.
    Returns None if the base name does not match the expected
    audit_<domain>_YYYYMMDD_HHMMSS shape. Domain extraction is load-bearing
    when the audit dir mixes multiple clients (which sample-audits/ does).
    """
    m = re.match(r"^audit_(.+)_\d{8}_\d{6}$", audit_base)
    return m.group(1) if m else None


def discover_audit_files(audit_dir: str, audit_base: str | None) -> dict:
    """Locate the four audit JSONs.

    If audit_base is provided, looks for exact-base matches on seo/ai, and
    date-prefix-scoped matches on citations/visibility (same YYYYMMDD as the
    audit_base). Otherwise picks the newest of each kind. Returns dict with
    keys seo, ai, citations, visibility (any may be None).
    """
    audit_dir = os.path.abspath(audit_dir)

    if audit_base:
        seo_path = os.path.join(audit_dir, f"{audit_base}_seo.json")
        ai_path = os.path.join(audit_dir, f"{audit_base}_ai.json")
        date_prefix = _date_prefix_from_base(audit_base)
        domain = _domain_from_base(audit_base)
        if date_prefix and domain:
            citations_path = _newest_match(audit_dir, f"citations_{domain}_{date_prefix}_*_summary.json")
            visibility_path = _newest_match(audit_dir, f"visibility_{domain}_{date_prefix}_*_summary.json")
        elif date_prefix:
            citations_path = _newest_match(audit_dir, f"citations_*_{date_prefix}_*_summary.json")
            visibility_path = _newest_match(audit_dir, f"visibility_*_{date_prefix}_*_summary.json")
        else:
            citations_path = _newest_match(audit_dir, "citations_*_summary.json")
            visibility_path = _newest_match(audit_dir, "visibility_*_summary.json")
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


def discover_prior_audit_base(audit_dir: str, curr_audit_base: str) -> str | None:
    """Return the audit_base of the most-recent audit older than curr_audit_base.

    Walks audit_*_seo.json files for the SAME DOMAIN as curr_audit_base,
    sorted by mtime descending, skips the current base, and returns the
    next-most-recent stem (without '_seo.json'). Returns None if no prior
    audit exists for that domain. Cross-domain mixing is a real-world hazard
    when sample-audits/ holds many clients' runs side-by-side.
    """
    domain = _domain_from_base(curr_audit_base)
    if not domain:
        return None
    audit_dir = os.path.abspath(audit_dir)
    matches = glob.glob(os.path.join(audit_dir, f"audit_{domain}_*_seo.json"))
    if not matches:
        return None
    matches.sort(key=os.path.getmtime, reverse=True)
    curr_seo = os.path.join(audit_dir, f"{curr_audit_base}_seo.json")
    for path in matches:
        if os.path.abspath(path) == os.path.abspath(curr_seo):
            continue
        fname = os.path.basename(path)
        if fname.endswith("_seo.json"):
            return fname[: -len("_seo.json")]
    return None


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


# ---------- Delta computation ----------


def _round_pp(curr: float | None, prev: float | None) -> str:
    """Format the delta between two percentages as a signed Npp string."""
    if curr is None or prev is None:
        return "(pending)"
    diff = round(curr - prev, 1)
    sign = "+" if diff > 0 else ("" if diff == 0 else "")
    return f"{sign}{diff}pp"


def _cat_rate(audit_block: dict | None, by_category_key: str, sub_key: str) -> float | None:
    """Pull a per-category rate_pct from a visibility-summary by_category block."""
    if not audit_block:
        return None
    by_cat = audit_block.get("by_category") or {}
    sub = by_cat.get(by_category_key) or {}
    val = sub.get(sub_key)
    return val if isinstance(val, (int, float)) else None


def compute_deltas(curr: dict, prev: dict | None) -> dict:
    """Compute current vs prior deltas + methodology caveats.

    `curr` and `prev` are the loaded-audit dicts from discover_audit_files
    (each carries keys: seo, ai, citations, visibility). `prev` may be None
    when no prior audit exists.

    Returns a dict the auto-draft prompt builder consumes verbatim. All numeric
    fields preserve None when unavailable; the prompt renders those as
    "(pending)" so the model never has to fabricate.
    """
    curr_citations = (curr or {}).get("citations") or {}
    curr_visibility = (curr or {}).get("visibility") or {}
    curr_seo = (curr or {}).get("seo") or {}
    curr_ai = (curr or {}).get("ai") or {}

    prev_citations = (prev or {}).get("citations") or {}
    prev_visibility = (prev or {}).get("visibility") or {}

    curr_citation_rate = curr_citations.get("citation_rate_pct")
    prev_citation_rate = prev_citations.get("citation_rate_pct")

    curr_brand = _cat_rate(curr_visibility, "brand_recognition", "rate_pct")
    prev_brand = _cat_rate(prev_visibility, "brand_recognition", "rate_pct")
    curr_topic = _cat_rate(curr_visibility, "concept_attribution", "rate_pct")
    prev_topic = _cat_rate(prev_visibility, "concept_attribution", "rate_pct")
    curr_recommend = _cat_rate(curr_visibility, "recommendation", "rate_pct")
    prev_recommend = _cat_rate(prev_visibility, "recommendation", "rate_pct")

    curr_total = curr_citations.get("total_tests")
    prev_total = prev_citations.get("total_tests")
    curr_testable = curr_citations.get("testable")
    prev_testable = prev_citations.get("testable")

    curr_platforms = set((p or "").lower() for p in (curr_citations.get("platforms_tested") or []))
    prev_platforms = set((p or "").lower() for p in (prev_citations.get("platforms_tested") or []))
    new_platforms = sorted(curr_platforms - prev_platforms)
    removed_platforms = sorted(prev_platforms - curr_platforms)

    panel_grew = (
        curr_total is not None and prev_total is not None and curr_total > prev_total
    )

    curr_seo_verdict = curr_seo.get("section_verdict")
    curr_ai_verdict = curr_ai.get("section_verdict")
    # The audit JSONs use a 'verdict' field per check (FAIL / PARTIAL / PASS /
    # SKIPPED). FAIL is hard failure, PARTIAL is partial coverage. Both feed
    # the recommendation prompt; PASS / SKIPPED are excluded.
    curr_seo_failed = [
        c.get("check") for c in (curr_seo.get("checks") or [])
        if c.get("verdict") in ("FAIL", "PARTIAL") and c.get("check")
    ]
    curr_ai_failed = [
        c.get("check") for c in (curr_ai.get("checks") or [])
        if c.get("verdict") in ("FAIL", "PARTIAL") and c.get("check")
    ]
    # Surface specific crawlability blockers when present. The 2026-05-18 hand-
    # written paragraph cited "robots.txt + sitemap returning 403" verbatim;
    # the recommendation needs this detail to land specifically rather than
    # generically. Walks the 1.2_technical_crawlability check for the actual
    # HTTP status codes.
    crawl_notes: list[str] = []
    for c in (curr_seo.get("checks") or []):
        if c.get("check") == "1.2_technical_crawlability":
            sub = c.get("checks") or {}
            for sub_name in ("robots_txt", "sitemap"):
                sub_val = sub.get(sub_name) or {}
                status = sub_val.get("status")
                exists = sub_val.get("exists")
                if status and status >= 400:
                    crawl_notes.append(f"{sub_name} HTTP {status}")
                elif exists is False:
                    crawl_notes.append(f"{sub_name} missing")
            break

    return {
        "curr_date": curr_citations.get("test_date") or curr_visibility.get("test_date"),
        "prev_date": prev_citations.get("test_date") or prev_visibility.get("test_date"),
        # Confidence (load-bearing for the LOW hard rule)
        "curr_confidence": curr_citations.get("confidence_label") or curr_visibility.get("confidence_label"),
        "prev_confidence": prev_citations.get("confidence_label") or prev_visibility.get("confidence_label"),
        # Citation rate
        "curr_citation_rate_pct": curr_citation_rate,
        "prev_citation_rate_pct": prev_citation_rate,
        "citation_rate_delta_pp": _round_pp(curr_citation_rate, prev_citation_rate),
        # Visibility sub-metrics
        "curr_brand_recog_pct": curr_brand,
        "prev_brand_recog_pct": prev_brand,
        "brand_recog_delta_pp": _round_pp(curr_brand, prev_brand),
        "curr_topic_assoc_pct": curr_topic,
        "prev_topic_assoc_pct": prev_topic,
        "topic_assoc_delta_pp": _round_pp(curr_topic, prev_topic),
        "curr_recommend_pct": curr_recommend,
        "prev_recommend_pct": prev_recommend,
        "recommend_delta_pp": _round_pp(curr_recommend, prev_recommend),
        # Methodology caveats
        "curr_total_tests": curr_total,
        "prev_total_tests": prev_total,
        "curr_testable": curr_testable,
        "prev_testable": prev_testable,
        "panel_grew": panel_grew,
        "new_platforms": new_platforms,
        "removed_platforms": removed_platforms,
        "curr_platforms_label": sorted(curr_platforms),
        "prev_platforms_label": sorted(prev_platforms),
        # Infrastructure failures (input for the recommendations bullet)
        "curr_seo_verdict": curr_seo_verdict,
        "curr_ai_verdict": curr_ai_verdict,
        "curr_seo_failed_checks": curr_seo_failed[:5],
        "curr_ai_failed_checks": curr_ai_failed[:5],
        "curr_crawl_blockers": crawl_notes,
    }


# ---------- Auto-draft (Claude API) ----------

# The Marston Slack channel post receives an auto-drafted analysis paragraph
# and 1-3 recommendations each Monday. The draft is generated by Claude Haiku
# from the verbatim audit deltas. The model is instructed to never invent
# metrics; if a number is missing the prompt shows "(pending)" and the model
# uses that literal rather than guessing.

_AUTO_DRAFT_SYSTEM_PROMPT = """You are the Customer Success Lead for the Found for GEO agency, drafting the weekly Slack update for one client (Marston Orthodontics). The update posts to the client's dedicated Slack channel every Monday morning. Voice and rules below are NON-NEGOTIABLE.

VOICE (per the codex node slack-channel-posting-flow.md):

- Verbatim metrics with the literal "+/-Npp" delta format. Example phrasing: "Citation rate dropped 15pp" or "60.0% to 45.0% (-15.0pp)".
- Negative deltas surfaced openly. Never euphemize. "Citation rate dropped 15pp" is correct; "citations softened" is wrong.
- No apology preamble. Do NOT open with "sorry it's been slow", "we know this is rough", "thanks for your patience", or anything in that family.
- No marketing voice. Do NOT use "excited to share", "thrilled to report", "leveraged synergies", "moving the needle", "best-in-class".
- No emoji-stuffing. The renderer sets the header emoji; you write plain text.
- No em-dashes (the long horizontal stroke, U+2014). Use commas, periods, colons, or hyphens instead.
- Cap the analysis at four sentences. Cap recommendations at three bullets total.

HARD RULES (violation invalidates the draft):

1. NEVER fabricate metrics. Use ONLY the verbatim numbers in the user message. If a value is "(pending)", say "(pending)" in your output rather than guessing.
2. If the current confidence_label is LOW, the analysis paragraph MUST mention this explicitly. Example phrasings: "Audit confidence label: LOW on both runs." or "Audit confidence: LOW this run." This is a hard requirement, not a soft hint.
3. If the input flags that the citation panel grew between runs, the analysis paragraph MUST flag that part of the delta is methodology, not signal. Cite the actual test counts ("60 to 80 tests").
4. If new platforms were added between runs, the analysis paragraph MUST name them and flag the methodology effect.
5. Recommendations must be concrete and tied to a verbatim signal in the input (a failed check, a verdict, a negative delta). Do not propose abstract goals.

OUTPUT FORMAT:

Return exactly two sections separated by a single line containing only "---REC---" (literal).

Section 1: the analysis paragraph. No header. No bullets. Plain prose.
Section 2: 1 to 3 recommendation lines. Each line begins with "- " (hyphen space). Most actionable goes first. No header.

REFERENCE EXAMPLE (this is what good looks like, drawn from the 2026-05-18 run):

Analysis:
"The brand-recognition lift is real but the query panel grew (60 to 80 tests) and Claude was added this run, so part of the % delta is methodology, not signal. Audit confidence label: LOW on both runs. Citation rate dropped 15pp. AIs are mentioning the practice more often but linking back less."

Recommendation:
"- SEO foundation (robots.txt + sitemap returning 403) is still the blocker. Fixing those is the highest-leverage move before next week's measurement."

Hold to these voice rules + hard rules even if the user prompt drifts.
"""


def _maybe_load_dotenv(dotenv_path: str = "~/.thrulead/.env") -> None:
    """Load .env keys into os.environ if not already present. Never overrides
    pre-set vars; silently no-ops on file/permission errors. Used to find
    ANTHROPIC_API_KEY in the operator's standard credential file when the
    renderer is invoked outside the SKILL.md webhook block."""
    path = os.path.expanduser(dotenv_path)
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k and v and k not in os.environ:
                    os.environ[k] = v
    except (FileNotFoundError, PermissionError, OSError):
        pass


def _fmt_pct(v: float | int | None) -> str:
    """Verbatim percent for the auto-draft prompt. None becomes "(pending)"."""
    if v is None:
        return "(pending)"
    return f"{v}%"


def _fmt_int(v: int | None) -> str:
    if v is None:
        return "(pending)"
    return str(v)


def _build_user_message(deltas: dict) -> str:
    """Render the per-run input block the model consumes. Verbatim numbers
    only; the model is instructed to use "(pending)" literally for missing
    fields."""

    new_platforms_line = (
        ", ".join(deltas["new_platforms"]) if deltas["new_platforms"] else "(none)"
    )
    removed_platforms_line = (
        ", ".join(deltas["removed_platforms"]) if deltas["removed_platforms"] else "(none)"
    )
    panel_grew_line = "yes" if deltas["panel_grew"] else "no"

    seo_failed = ", ".join(deltas["curr_seo_failed_checks"]) or "(none surfaced)"
    ai_failed = ", ".join(deltas["curr_ai_failed_checks"]) or "(none surfaced)"
    crawl_blockers = ", ".join(deltas.get("curr_crawl_blockers") or []) or "(none detected)"

    return f"""INPUT METRICS (use ONLY these verbatim values; "(pending)" means missing, render it literally)

Current run ({deltas.get('curr_date') or '(pending)'}):
- Audit confidence label: {deltas.get('curr_confidence') or '(pending)'}
- Citation rate: {_fmt_pct(deltas['curr_citation_rate_pct'])}
- Brand recognition: {_fmt_pct(deltas['curr_brand_recog_pct'])}
- Topic association: {_fmt_pct(deltas['curr_topic_assoc_pct'])}
- Active recommendation: {_fmt_pct(deltas['curr_recommend_pct'])}
- Citation panel: {_fmt_int(deltas['curr_total_tests'])} total tests ({_fmt_int(deltas['curr_testable'])} testable)
- Platforms tested: {', '.join(deltas['curr_platforms_label']) or '(pending)'}

Prior run ({deltas.get('prev_date') or '(pending)'}):
- Audit confidence label: {deltas.get('prev_confidence') or '(pending)'}
- Citation rate: {_fmt_pct(deltas['prev_citation_rate_pct'])}
- Brand recognition: {_fmt_pct(deltas['prev_brand_recog_pct'])}
- Topic association: {_fmt_pct(deltas['prev_topic_assoc_pct'])}
- Active recommendation: {_fmt_pct(deltas['prev_recommend_pct'])}
- Citation panel: {_fmt_int(deltas['prev_total_tests'])} total tests ({_fmt_int(deltas['prev_testable'])} testable)
- Platforms tested: {', '.join(deltas['prev_platforms_label']) or '(pending)'}

DELTAS (computed verbatim, format is +/-Npp):
- Citation rate: {deltas['citation_rate_delta_pp']}
- Brand recognition: {deltas['brand_recog_delta_pp']}
- Topic association: {deltas['topic_assoc_delta_pp']}
- Active recommendation: {deltas['recommend_delta_pp']}

METHODOLOGY CAVEATS (cite these in the analysis paragraph when they apply):
- Citation panel grew between runs: {panel_grew_line}
- New platforms in current run: {new_platforms_line}
- Removed platforms in current run: {removed_platforms_line}
- Confidence labels: current={deltas.get('curr_confidence') or '(pending)'}, prior={deltas.get('prev_confidence') or '(pending)'}

INFRASTRUCTURE SIGNALS (input for the recommendation bullets):
- SEO Foundation verdict: {deltas.get('curr_seo_verdict') or '(pending)'}
- AI Infrastructure verdict: {deltas.get('curr_ai_verdict') or '(pending)'}
- SEO checks failing or partial: {seo_failed}
- AI checks failing or partial: {ai_failed}
- Crawlability blockers (specific HTTP statuses): {crawl_blockers}

Draft the analysis paragraph and 1-3 recommendations now. Return the two sections separated by the literal line "---REC---". Hold the voice + hard rules.
"""


def _parse_response(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Split the model output into (analysis_paragraph, recommendations_block).

    The model is instructed to emit a literal "---REC---" line as separator.
    If the separator is missing or the output is empty, returns (None, None)
    so the caller falls back to placeholders.
    """
    if not text or not text.strip():
        return None, None
    parts = re.split(r"^\s*-{2,}\s*REC\s*-{2,}\s*$", text.strip(), maxsplit=1, flags=re.MULTILINE)
    if len(parts) != 2:
        return None, None
    analysis = parts[0].strip()
    recs = parts[1].strip()
    if not analysis or not recs:
        return None, None
    # Sanity: em-dash leak check (voice rule). If the model leaked one, replace
    # with a comma so the post does not violate chudi-frame typographic
    # discipline. Cheap one-line guardrail; not a substitute for the prompt rule.
    analysis = analysis.replace("—", ", ")
    recs = recs.replace("—", ", ")
    return analysis, recs


def draft_analysis_and_recommendations(
    curr_audit: dict,
    prev_audit: dict | None,
    *,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 800,
) -> Tuple[Optional[str], Optional[str]]:
    """Auto-draft the analysis paragraph and recommendations from audit deltas.

    Returns (analysis_paragraph, recommendations_block) on success, or
    (None, None) on any failure (no API key, network error, malformed
    response, etc.). The caller falls back to the operator-fill {{placeholders}}
    when this returns None.

    Arguments:
      curr_audit: dict from discover_audit_files for the current week.
      prev_audit: dict from discover_audit_files for the prior week. May be None.
      model: Claude model ID. Defaults to Haiku 4.5 (low-latency for tight
             structured output).
      max_tokens: cap on model output length. 800 is generous for one
                  paragraph + 3 bullets; tightens guardrails on runaway output.
    """
    _maybe_load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.stderr.write("[auto-draft] ANTHROPIC_API_KEY not set, skipping (falling back to placeholders)\n")
        return None, None

    try:
        import anthropic  # type: ignore
    except ImportError:
        sys.stderr.write("[auto-draft] anthropic SDK not installed, skipping (pip install anthropic)\n")
        return None, None

    deltas = compute_deltas(curr_audit, prev_audit or {})
    user_msg = _build_user_message(deltas)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": _AUTO_DRAFT_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral", "ttl": "5m"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception as e:
        sys.stderr.write(f"[auto-draft] API call failed: {type(e).__name__}: {e}\n")
        return None, None

    # Extract text content from the response. Haiku returns a list of content
    # blocks; concatenate the text blocks (typically just one).
    try:
        text = "".join(
            getattr(b, "text", "") for b in (resp.content or [])
            if getattr(b, "type", "") == "text"
        )
    except Exception as e:
        sys.stderr.write(f"[auto-draft] response parse failed: {type(e).__name__}: {e}\n")
        return None, None

    analysis, recs = _parse_response(text)
    if analysis is None or recs is None:
        sys.stderr.write("[auto-draft] response did not contain the ---REC--- separator; falling back\n")
        return None, None

    # Surface cache usage to stderr for the operator to verify caching works.
    try:
        usage = getattr(resp, "usage", None)
        if usage is not None:
            cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cr = getattr(usage, "cache_read_input_tokens", 0) or 0
            it = getattr(usage, "input_tokens", 0) or 0
            ot = getattr(usage, "output_tokens", 0) or 0
            sys.stderr.write(
                f"[auto-draft] tokens: in={it} out={ot} cache_write={cw} cache_read={cr}\n"
            )
    except Exception:
        pass

    return analysis, recs


# ---------- Template rendering ----------


def render_template(
    fields: dict,
    week: int,
    iso_date: str,
    status_emoji: str,
    *,
    analysis_paragraph: Optional[str] = None,
    recommendations_block: Optional[str] = None,
    auto_drafted: bool = False,
) -> str:
    """Render the marston-weekly-update-template-v1.md filled-in form.

    Manual fields default to {{placeholders}} so the operator can fill them
    in the saved draft before posting. When `analysis_paragraph` is provided,
    a new "Analysis" section is inserted between Site infrastructure and Top
    5 competitors. When `recommendations_block` is provided, it replaces the
    "What we'll do next week" placeholders. The `auto_drafted` flag adds a
    review-trail footer note so the operator can see at a glance that an
    auto-draft was used (the cron-unattended path needs this audit trail).
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

    # @-mention Dr. Marston at the top so the Monday morning post triggers
    # a Slack notification on his end. BLAKE_USER_ID lives in ~/.thrulead/.env.
    # If unset, the renderer gracefully degrades to plain-text "@blakemarston"
    # which does NOT trigger a notification but still names him in the post.
    import os as _os
    _blake_id = _os.environ.get("BLAKE_USER_ID", "").strip()
    if _blake_id:
        mention_line = f"<@{_blake_id}> "
    else:
        mention_line = "@blakemarston "

    # Auto-drafted analysis section. Inserted between Site infrastructure and
    # Top 5 competitors so the synthesis follows the metrics block. Empty when
    # the API call failed or --no-auto-draft was set.
    if analysis_paragraph:
        analysis_section = f"\n*▸ Analysis*\n{analysis_paragraph}\n"
    else:
        analysis_section = ""

    # Recommendations block: substituted into "What we'll do next week". When
    # the auto-draft failed, the original two-line placeholder pair is kept so
    # the operator can fill manually before posting.
    if recommendations_block:
        next_week_block = recommendations_block
    else:
        next_week_block = (
            "{{Manual: specific actions 1-3}}\n"
            "{{Manual: target — specific measurable goal}}"
        )

    # Audit-trail footer: only present when auto-draft ran. The cron-unattended
    # path needs this so the operator can see post-hoc that the analysis was
    # generated, not hand-written.
    if auto_drafted:
        auto_draft_footer = (
            "\n_Analysis + recommendations auto-drafted from audit deltas "
            "(Claude Haiku). Operator review recommended before next-week "
            "ratification._\n"
        )
    else:
        auto_draft_footer = ""

    out = f"""{mention_line}

*Marston Orthodontics, Found for GEO Weekly, Week {week}*
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
{analysis_section}
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
{next_week_block}

*▸ Asks for Dr. Marston*
{{{{Manual: specific request OR "Nothing this week — we have what we need."}}}}

*▸ Receipts*
- citability.dev audit: {fields['receipt']}
- CrowdReply Brand Report: {{{{paste URL}}}}
- Engagement activity log: {{{{paste URL}}}}
{auto_draft_footer}"""
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
    parser.add_argument("--prev-audit-base",
                        help="Prior-week audit base name for delta auto-draft. Auto-discovers second-newest if omitted.")
    parser.add_argument("--week", type=int, default=1, help="Week number for header (default: 1)")
    parser.add_argument("--date", help="ISO date for header (default: today UTC)")
    parser.add_argument("--status", choices=["on-track", "watch", "blocked"], default="on-track",
                        help="Status emoji for header")
    parser.add_argument("--no-auto-draft", action="store_true",
                        help="Skip the Claude Haiku auto-draft and leave the analysis/next-week fields as operator-fill placeholders.")
    parser.add_argument("--draft-model", default="claude-haiku-4-5-20251001",
                        help="Model ID for the auto-draft call (default: claude-haiku-4-5-20251001).")
    args = parser.parse_args()

    iso_date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status_emoji = {"on-track": "🟢 on-track", "watch": "🟡 watch", "blocked": "🔴 blocked"}[args.status]

    loaded = discover_audit_files(args.audit_dir, args.audit_base)

    # Resolve the current audit_base from the discovered paths when not given.
    # We need it as a stable string to scope the prior-audit lookup so we don't
    # accidentally select the same run as both current AND prior.
    curr_base = args.audit_base
    if not curr_base:
        curr_seo_path = (loaded.get("_paths") or {}).get("seo")
        if curr_seo_path:
            curr_seo_name = os.path.basename(curr_seo_path)
            if curr_seo_name.endswith("_seo.json"):
                curr_base = curr_seo_name[: -len("_seo.json")]

    # Discover the prior audit (skipped when --no-auto-draft or no base).
    prev_loaded: dict | None = None
    prev_base: Optional[str] = args.prev_audit_base
    if not args.no_auto_draft:
        if not prev_base and curr_base:
            prev_base = discover_prior_audit_base(args.audit_dir, curr_base)
        if prev_base:
            prev_loaded = discover_audit_files(args.audit_dir, prev_base)

    # Print which files were found to stderr so the operator sees the discovery.
    paths = loaded.get("_paths", {})
    sys.stderr.write("Audit files discovered (current):\n")
    for k in ("seo", "ai", "citations", "visibility"):
        sys.stderr.write(f"  {k}: {paths.get(k) or '(none)'}\n")
    if prev_loaded:
        prev_paths = prev_loaded.get("_paths", {})
        sys.stderr.write("Audit files discovered (prior):\n")
        for k in ("seo", "ai", "citations", "visibility"):
            sys.stderr.write(f"  {k}: {prev_paths.get(k) or '(none)'}\n")
    else:
        sys.stderr.write("Audit files discovered (prior): (none — auto-draft will run without delta context)\n")
    sys.stderr.write("\n")

    # Auto-draft analysis + recommendations from the deltas (skipped on --no-auto-draft).
    analysis_paragraph: Optional[str] = None
    recommendations_block: Optional[str] = None
    auto_drafted = False
    if not args.no_auto_draft:
        analysis_paragraph, recommendations_block = draft_analysis_and_recommendations(
            loaded, prev_loaded, model=args.draft_model
        )
        auto_drafted = analysis_paragraph is not None and recommendations_block is not None
        if not auto_drafted:
            sys.stderr.write("[auto-draft] falling back to operator-fill placeholders\n")

    fields = extract_fields(loaded)
    output = render_template(
        fields,
        args.week,
        iso_date,
        status_emoji,
        analysis_paragraph=analysis_paragraph,
        recommendations_block=recommendations_block,
        auto_drafted=auto_drafted,
    )
    sys.stdout.write(output)


if __name__ == "__main__":
    main()
