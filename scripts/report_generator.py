#!/usr/bin/env python3
"""
AVR Report Generator
Takes JSON outputs from seo_foundation, ai_readiness, and citation_monitor,
generates a formatted Markdown audit report.
"""

import json
import sys
from datetime import datetime, timezone


def determine_overall_status(seo_verdict: str, ai_verdict: str) -> str:
    """Determine overall readiness status from section verdicts."""
    if seo_verdict == "PASS" and ai_verdict == "PASS":
        return "AI-READY"
    elif seo_verdict == "PASS":
        return "FOUNDATION-READY"
    elif ai_verdict == "PASS":
        return "INFRASTRUCTURE-READY"
    else:
        return "NOT-READY"


def verdict_emoji(verdict: str) -> str:
    """Map verdict to a simple text indicator (no emojis per user preference)."""
    return {
        "PASS": "[PASS]",
        "PARTIAL": "[PARTIAL]",
        "FAIL": "[FAIL]",
        "SKIPPED": "[SKIPPED]",
        "CITED": "[CITED]",
        "PARTIALLY_CITED": "[PARTIAL]",
        "NOT_CITED": "[NOT CITED]",
    }.get(verdict, f"[{verdict}]")


# ---------------------------------------------------------------------------
# Buyer-facing content maps (2026-07-06: buyer-first framing applied)
# ---------------------------------------------------------------------------

# Plain-language outcome leads for the executive summary.
# The FIRST sentence is what the buyer FEELS, not a pass-count or status code.
# Technical detail (pass counts, overall status label) follows below.
_BUYER_OUTCOME_LEADS: dict[str, str] = {
    "AI-READY": (
        "Your site has removed all measurable infrastructure barriers to AI citation. "
        "AI assistants like ChatGPT and Perplexity can find, read, and cite your content. "
        "The remaining work is building topical authority over time -- that happens through "
        "consistent publishing and link acquisition, not infrastructure fixes."
    ),
    "FOUNDATION-READY": (
        "AI assistants may not find or recommend you, even for searches where you should appear. "
        "Your traditional search foundation is solid, but AI-specific signals are missing or incomplete. "
        "Fixing the items in this report unlocks AI citation and recommendation."
    ),
    "INFRASTRUCTURE-READY": (
        "AI-specific signals are in place, but your underlying search foundation has critical gaps. "
        "AI assistants source their answers from the web -- if search engines cannot index you, "
        "AI cannot cite you. Start with the SEO fixes below, then re-run."
    ),
    "NOT-READY": (
        "AI assistants cannot reliably find or recommend you. "
        "Both the search foundation and the AI-specific signals need attention. "
        "This affects how potential customers discover you through tools like ChatGPT, Perplexity, "
        "and Google AI Overviews. The fix order below is sequenced from highest-leverage to lowest."
    ),
}

# Per-check buyer-facing info, keyed by keyword substring that appears in the check name.
# Lookup: iterate and check if keyword is contained in check["check"].
# Format per entry: (plain_label, who_does_it, rough_effort, expected_result)
# HONESTY GUARD: expected_result is always qualitative -- no fabricated percentages or counts.
_CHECK_BUYER_INFO: list[tuple[str, tuple[str, str, str, str]]] = [
    ("core_web_vitals", (
        "Core Web Vitals",
        "Your dev team",
        "~4-8 hours (varies by site stack)",
        "Better user experience scores improve eligibility for Google enhanced search features "
        "that feed AI overviews.",
    )),
    ("technical_crawlability", (
        "Technical crawl access",
        "Your dev team, or a citability engagement",
        "~1-2 hours",
        "Crawlers can access your robots.txt, sitemap, and pages without HTTP errors. "
        "This is a prerequisite for any search or AI citation to function.",
    )),
    ("schema_markup", (
        "Structured data (schema.org)",
        "Your dev team, or a citability engagement",
        "~3 hours",
        "AI systems can extract structured facts about your business (name, hours, services, category). "
        "This typically improves how accurately AI answers describe you.",
    )),
    ("page_speed", (
        "Page speed",
        "Your dev team",
        "~4-8 hours (varies by site stack)",
        "Faster load times reduce bounce rate from AI-referred visitors "
        "and improve performance-based ranking signals that feed AI overviews.",
    )),
    ("content_indexability", (
        "Content indexing",
        "Your dev team, or a citability engagement",
        "~2 hours",
        "Search engines and AI crawlers can index your pages. "
        "You become eligible to appear in AI-generated answers for your topics.",
    )),
    ("ai_crawler_access", (
        "AI crawler permissions",
        "Your dev team, or a citability engagement",
        "~30 minutes",
        "AI crawlers (GPTBot, ClaudeBot, PerplexityBot) can index your content "
        "for their retrieval systems.",
    )),
    ("llms_txt", (
        "LLMs.txt (AI sitemap)",
        "Your dev team, or a citability engagement",
        "~1 hour",
        "AI agents have a machine-readable map of your content and services. "
        "This improves how thoroughly AI tools can represent and reference you.",
    )),
    ("structured_data_depth", (
        "Structured data depth",
        "Your dev team, or a citability engagement",
        "~3 hours",
        "Richer schema coverage gives AI engines more structured facts to cite. "
        "Wider schema on key pages typically improves citation accuracy over time.",
    )),
    ("content_structure", (
        "Content heading structure",
        "Your content team",
        "~2 hours",
        "AI engines extract your key claims cleanly and attribute them to you accurately.",
    )),
    ("content_ratio", (
        "Content-to-code ratio",
        "Your dev team",
        "~2 hours",
        "More of your actual content is visible to AI; less framework boilerplate noise.",
    )),
    ("semantic_html", (
        "Semantic HTML",
        "Your dev team",
        "~2 hours",
        "AI parsers understand your page layout without guessing, "
        "which reduces misattribution and improves extraction accuracy.",
    )),
]

# Unlock hints for SKIPPED individual checks (keyed by keyword substring in check name)
_SKIPPED_UNLOCK_HINTS: list[tuple[str, str]] = [
    ("core_web_vitals", (
        "Re-run the audit without `--skip-lighthouse`. "
        "Requires Lighthouse (`npm install -g lighthouse`)."
    )),
    ("page_speed", (
        "Re-run the audit without `--skip-lighthouse`. "
        "Requires Lighthouse (`npm install -g lighthouse`)."
    )),
]
_SKIPPED_DEFAULT_HINT = (
    "Re-run the audit with full options enabled, "
    "or contact your citability consultant to unlock this check."
)


def _lookup_buyer_info(check_name: str) -> tuple[str, str, str, str] | None:
    """Find buyer-facing info for a check by keyword substring match."""
    for keyword, info in _CHECK_BUYER_INFO:
        if keyword in check_name:
            return info
    return None


def _unlock_hint_for_skipped_check(check: dict) -> str:
    """Return a buyer-facing 'To unlock this check' hint for a SKIPPED check."""
    check_name = check.get("check", "")
    for keyword, hint in _SKIPPED_UNLOCK_HINTS:
        if keyword in check_name:
            return hint
    return _SKIPPED_DEFAULT_HINT


def _format_check_as_recommendation(check: dict, verdict: str) -> list[str]:
    """Format a failing/partial check as a buyer-facing recommendation block.

    Returns a list of markdown lines. Uses plain-language labels, not internal
    check codes. Adds who does it, rough effort, and an honest expected result.
    HONESTY GUARD: never fabricate a precise number or guaranteed outcome.
    """
    check_name = check.get("check", "")
    info = _lookup_buyer_info(check_name)
    if info:
        label, who, effort, expected = info
        return [
            f"**{label}** {verdict_emoji(verdict)}",
            f"- Who does it: {who}",
            f"- Rough effort: {effort}",
            f"- Expected result: {expected}",
            "",
        ]
    else:
        # Fallback for unmapped checks: cleaned-up label, no fabricated number
        display_name = (
            check_name.split("_", 1)[1].replace("_", " ").title()
            if "_" in check_name
            else check_name
        )
        return [
            f"**{display_name}** {verdict_emoji(verdict)}",
            f"- Expected result: Closes an infrastructure gap that may be limiting AI citation.",
            "",
        ]


def _build_top_actions(
    seo_results: dict, ai_results: dict, overall: str
) -> list[tuple[str, str]]:
    """Extract top 3 prioritized actions with buyer-facing expected results.

    Returns list of (action_text, expected_result_text) tuples.
    HONESTY GUARD: expected_result_text is always qualitative -- never a fabricated number.
    """
    actions: list[tuple[str, str]] = []

    if overall == "AI-READY":
        actions.append((
            "Run the citation test (Section 3) to establish your baseline citation rate.",
            "A data-backed citation rate you can track month over month. "
            "You will know which AI platforms cite you and for which topics.",
        ))
        actions.append((
            "Build backlinks from high-DA sources to increase domain authority.",
            "Higher domain authority correlates with more frequent AI citations over time. "
            "Results appear gradually, typically over weeks to months.",
        ))
        actions.append((
            "Publish consistently on your core topics and re-run this audit quarterly.",
            "AI systems build topical associations from web content. "
            "Consistent publishing strengthens the citation signal over time.",
        ))
        return actions[:3]

    # Priority 1: SEO failures
    for check in seo_results.get("checks", []):
        if check.get("verdict") == "FAIL":
            check_id = check["check"]
            if "indexability" in check_id:
                actions.append((
                    "Fix content indexability: ensure server-side rendering and remove noindex tags.",
                    "Search engines and AI crawlers can index your pages. "
                    "You become eligible to appear in AI-generated answers.",
                ))
            elif "crawlability" in check_id:
                actions.append((
                    "Fix technical crawlability: add robots.txt, sitemap.xml, and enforce HTTPS.",
                    "Crawlers can access your site reliably. "
                    "This is a prerequisite for any search or AI citation.",
                ))
            elif "schema" in check_id:
                actions.append((
                    "Add structured data (JSON-LD) with appropriate @type for your content.",
                    "AI systems can extract structured facts about your business. "
                    "This typically improves how accurately AI answers describe you.",
                ))
            elif "web_vitals" in check_id or "page_speed" in check_id:
                actions.append((
                    "Improve page performance: target LCP < 2.5s, CLS < 0.1.",
                    "Faster pages reduce bounce rate from AI-referred visitors "
                    "and improve performance ranking signals.",
                ))
            else:
                name = (
                    check_id.split("_", 1)[1].replace("_", " ").title()
                    if "_" in check_id
                    else check_id
                )
                actions.append((
                    f"Fix: {name}",
                    "Closes an SEO infrastructure gap that is blocking AI citation.",
                ))

    # Priority 2: AI infra failures
    for check in ai_results.get("checks", []):
        if check.get("verdict") == "FAIL":
            check_id = check["check"]
            if "crawler_access" in check_id:
                actions.append((
                    "Update robots.txt to allow GPTBot, ClaudeBot, and PerplexityBot.",
                    "AI crawlers can index your content for their retrieval systems.",
                ))
            elif "structured_data" in check_id:
                actions.append((
                    "Add schema markup to more pages (target >80% coverage).",
                    "Richer schema coverage gives AI engines more structured facts to cite.",
                ))
            elif "content_structure" in check_id:
                actions.append((
                    "Improve heading hierarchy: single H1, logical H2/H3 sections.",
                    "AI engines extract your key points cleanly and attribute them accurately.",
                ))
            elif "semantic" in check_id:
                actions.append((
                    "Use semantic HTML (<article>, <main>, <nav>) instead of generic <div>.",
                    "AI parsers understand your page structure, reducing misattribution.",
                ))
            elif "content_ratio" in check_id:
                actions.append((
                    "Increase text-to-HTML ratio: reduce framework overhead or add more content.",
                    "More of your real content is visible to AI; less framework noise.",
                ))

    # Priority 3: AI infra partials (fill to 3 if needed)
    for check in ai_results.get("checks", []):
        if check.get("verdict") == "PARTIAL" and len(actions) < 3:
            check_id = check["check"]
            name = (
                check_id.split("_", 1)[1].replace("_", " ").title()
                if "_" in check_id
                else check_id
            )
            actions.append((
                f"Improve: {name} (currently partial)",
                "Closes a partial infrastructure gap that is limiting AI citation precision.",
            ))

    return actions[:3]


def generate_report(
    seo_results: dict,
    ai_results: dict,
    citation_results: dict | None = None,
    visibility_results: dict | None = None,
    url: str = "",
    client_name: str | None = None,
    consultant_name: str = "Chudi Nnorukam",
    calibration_receipt: dict | None = None,
) -> str:
    """Generate a formatted Markdown audit report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    date_short = datetime.now(timezone.utc).strftime("%B %d, %Y")

    overall = determine_overall_status(
        seo_results.get("section_verdict", "FAIL"),
        ai_results.get("section_verdict", "FAIL"),
    )

    # Count passes and failures
    all_checks = seo_results.get("checks", []) + ai_results.get("checks", [])
    active_checks = [c for c in all_checks if c.get("verdict") != "SKIPPED"]
    pass_count = sum(1 for c in active_checks if c["verdict"] == "PASS")
    total_count = len(active_checks)

    top_actions = _build_top_actions(seo_results, ai_results, overall)

    lines = [
        f"# AI Visibility Readiness Audit",
    ]

    # Consulting header (when --client is provided)
    if client_name:
        lines.extend([
            "",
            f"**Prepared for:** {client_name}",
            f"**Prepared by:** {consultant_name}",
            f"**Date:** {date_short}",
            f"**URL audited:** {url or seo_results.get('url', 'N/A')}",
            f"**Framework:** AVR v1.0.0",
            "",
            "---",
        ])
    else:
        lines.extend([
            "",
            f"**URL:** {url or seo_results.get('url', 'N/A')}",
            f"**Date:** {now}",
            f"**Framework:** AVR v1.0.0",
            "",
            "---",
        ])

    # Executive summary -- leads with buyer-felt outcome, NOT a pass-count or status code.
    # Plain-language business consequence first; technical detail (status, counts) follows.
    buyer_outcome = _BUYER_OUTCOME_LEADS.get(overall, "")
    lines.extend([
        "",
        "## Executive Summary",
        "",
        buyer_outcome,
        "",
        f"**Technical status: {overall}** -- {pass_count} of {total_count} infrastructure "
        f"checks passed (SEO Foundation + AI Infrastructure combined).",
        "",
    ])

    lines.extend([
        "| Section | Verdict |",
        "|---------|---------|",
        f"| SEO Foundation | {verdict_emoji(seo_results.get('section_verdict', 'FAIL'))} |",
        f"| AI Infrastructure | {verdict_emoji(ai_results.get('section_verdict', 'FAIL'))} |",
    ])

    if visibility_results:
        # Headline = brand_recognition rate (the cleanest signal). The aggregate
        # visibility_rate_pct averages incompatible signals across a query mix
        # biased toward tools/resources, which understates reference-shaped sites.
        by_cat = visibility_results.get("by_category", {}) or {}
        brand_rate = by_cat.get("brand_recognition", {}).get("rate_pct", 0)
        brand_n = by_cat.get("brand_recognition", {}).get("visible", 0)
        brand_t = by_cat.get("brand_recognition", {}).get("total", 0)
        if brand_t:
            lines.append(f"| AI Visibility (Brand Recognition) | {visibility_results.get('verdict', 'N/A')}, {brand_rate}% ({brand_n}/{brand_t}) |")
        else:
            lines.append(f"| AI Visibility | {visibility_results.get('verdict', 'N/A')} |")
    if citation_results:
        lines.append(f"| AI Citations | {verdict_emoji(citation_results.get('verdict', 'NOT_CITED'))} ({citation_results.get('citation_rate_pct', 0)}%) |")

    # Top actions -- each with a buyer-facing expected result (qualitative, never fabricated).
    if top_actions:
        n = len(top_actions)
        header = f"### Top {n} Action{'s' if n > 1 else ''} (in priority order)"
        lines.extend(["", header, ""])
        for i, (action, expected_result) in enumerate(top_actions, 1):
            lines.append(f"{i}. {action}")
            if expected_result:
                lines.append(f"   - **Expected result:** {expected_result}")

    # Calibration receipt (only present for --live-test runs that didn't --skip-calibration)
    if calibration_receipt:
        from calibration import format_receipt_markdown
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(format_receipt_markdown(calibration_receipt))

    lines.extend([
        "",
        "---",
        "",
        "## Section 1: SEO Foundation",
        "",
        f"**Section Verdict:** {verdict_emoji(seo_results.get('section_verdict', 'FAIL'))}",
        "",
    ])

    # Detail each check
    for check in seo_results.get("checks", []):
        check_name = check.get("check", "Unknown").replace("_", " ").title()
        lines.append(f"### {check_name}")
        lines.append(f"**Tier:** {check.get('tier', 'N/A')} | **Verdict:** {verdict_emoji(check.get('verdict', 'FAIL'))}")
        lines.append("")

        if "error" in check:
            lines.append(f"**Error:** {check['error']}")
            lines.append("")
            continue

        if "metrics" in check and check["metrics"]:
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            for k, v in check["metrics"].items():
                label = k.replace("_", " ").title()
                lines.append(f"| {label} | {v} |")
            lines.append("")

        if "checks" in check and isinstance(check["checks"], dict):
            for sub_name, sub_val in check["checks"].items():
                if isinstance(sub_val, dict):
                    summary = ", ".join(f"{sk}: {sv}" for sk, sv in sub_val.items())
                    lines.append(f"- **{sub_name}:** {summary}")
                else:
                    lines.append(f"- **{sub_name}:** {sub_val}")
            lines.append("")

        if "schemas" in check:
            if check["schemas"]:
                types = [s.get("type", "?") for s in check["schemas"] if s.get("valid_json")]
                lines.append(f"Schema types found: {', '.join(types) if types else 'None'}")
            else:
                lines.append("No structured data found.")
            lines.append("")

        if "note" in check:
            lines.append(f"*{check['note']}*")
            lines.append("")

        # Unlock roadmap for skipped checks -- reads as a next step, not a shrug.
        if check.get("verdict") == "SKIPPED":
            lines.append(f"*To unlock this check: {_unlock_hint_for_skipped_check(check)}*")
            lines.append("")

    # Section 2
    lines.extend([
        "---",
        "",
        "## Section 2: AI Infrastructure Readiness",
        "",
        f"**Section Verdict:** {verdict_emoji(ai_results.get('section_verdict', 'FAIL'))}",
        "",
    ])

    for check in ai_results.get("checks", []):
        check_name = check.get("check", "Unknown").replace("_", " ").title()
        lines.append(f"### {check_name}")
        lines.append(f"**Tier:** {check.get('tier', 'N/A')} | **Verdict:** {verdict_emoji(check.get('verdict', 'FAIL'))}")
        lines.append("")

        if "error" in check:
            lines.append(f"**Error:** {check['error']}")
            lines.append("")
            continue

        details = check.get("details", {})
        if details:
            if "crawlers" in check:
                lines.append("| Crawler | Status | Operator |")
                lines.append("|---------|--------|----------|")
                for name, info in check["crawlers"].items():
                    lines.append(f"| {name} | {info['status']} | {info['operator']} |")
                lines.append("")
            else:
                for k, v in details.items():
                    if k == "first_lines":
                        lines.append(f"- **Preview:** `{' | '.join(str(l) for l in v[:3])}`")
                    elif k == "schema_types":
                        lines.append(f"- **Schema types:** {', '.join(v) if v else 'None'}")
                    elif k == "headings_sample":
                        for h in v[:5]:
                            lines.append(f"  - H{h['level']}: {h['text']}")
                    elif k == "semantic_elements":
                        for el, count in v.items():
                            if count > 0:
                                lines.append(f"  - `<{el}>`: {count}")
                    elif not isinstance(v, (dict, list)):
                        label = k.replace("_", " ").title()
                        lines.append(f"- **{label}:** {v}")
                lines.append("")

        if "note" in check:
            lines.append(f"*{check['note']}*")
            lines.append("")

        # Unlock roadmap for skipped checks
        if check.get("verdict") == "SKIPPED":
            lines.append(f"*To unlock this check: {_unlock_hint_for_skipped_check(check)}*")
            lines.append("")

    # Section 3, when calibration failed and AI tests were withheld, render
    # CALIBRATION_FAILED placeholder with an unlock roadmap -- not a shrug.
    calibration_failed = (
        calibration_receipt is not None
        and not calibration_receipt.get("overall_pass", True)
        and citation_results is None
    )
    if calibration_failed:
        lines.extend([
            "---",
            "",
            "## Section 3: Citation Monitoring",
            "",
            "**Status:** CALIBRATION_FAILED -- site-level numbers withheld.",
            "",
            "The methodology calibration that validates this section's numbers failed "
            "(see Calibration Receipt above). Site-level numbers are withheld because "
            "they cannot be distinguished from calibration noise.",
            "",
            "**To unlock this section:** Resolve the calibration failure shown in the "
            "Calibration Receipt above. The receipt identifies exactly which smoke-test "
            "query failed and what a passing response looks like. Calibration issues "
            "typically resolve within hours (model outages, rate limits). Once resolved, "
            "re-run with `--live-test` to generate verified citation numbers. "
            "Alternatively, pass `--skip-calibration` to acknowledge the risk and generate "
            "numbers anyway (clearly labeled as unvalidated).",
            "",
            "---",
            "",
            "## Section 4: AI Visibility [BEST-EFFORT]",
            "",
            "**Status:** CALIBRATION_FAILED -- site-level numbers withheld.",
            "",
            "Same reason as Section 3 above.",
            "",
            "**To unlock this section:** Same steps as Section 3 (resolve the calibration "
            "failure, then re-run with `--live-test`).",
            "",
        ])

    # Section 3 (normal path, when citation_results present)
    if citation_results:
        lines.extend([
            "---",
            "",
            "## Section 3: Citation Monitoring",
            "",
            f"**Verdict:** {verdict_emoji(citation_results.get('verdict', 'NOT_CITED'))}",
            f"**Confidence:** {citation_results.get('confidence_label', 'LOW')}",
            "",
            f"- Citation rate: {citation_results.get('citation_rate_pct', 0)}%",
            f"- Cited: {citation_results.get('cited_count', 0)} / {citation_results.get('testable', 0)} testable queries",
        ])

        ci = citation_results.get("confidence_interval_95", {})
        if ci:
            lines.append(f"- 95% CI: [{ci.get('low_pct', 0)}%, {ci.get('high_pct', 0)}%]")

        lines.append("")

        by_platform = citation_results.get("by_platform", {})
        if by_platform:
            lines.append("| Platform | Cited | Citation Rate |")
            lines.append("|----------|-------|---------------|")
            for platform, pdata in by_platform.items():
                lines.append(f"| {platform} | {pdata['cited']}/{pdata['total']} | {pdata.get('citation_rate_pct', 0)}% |")
            lines.append("")

        # Fan-out coverage (Section 3b) -- present only when the citation test ran
        # in --fan-out-mode.
        fan = citation_results.get("fan_out_coverage")
        if fan:
            gaps = fan.get("gap_sub_queries", [])
            covered = fan.get("covered_sub_queries", [])
            lines.extend([
                "### Fan-Out Coverage [BEST-EFFORT]",
                "",
                f"**Seed topic:** {fan.get('seed_topic', '')} ({fan.get('query_type', 'unknown')} query)",
                f"**Coverage:** {fan.get('coverage_rate_pct', 0)}% of {fan.get('sub_queries_generated', 0)} "
                f"sub-queries cited (confidence: {fan.get('confidence_label', 'LOW')})",
                "",
                "When an AI engine answers this topic, it fans out into several sub-queries. "
                "Each gap below is a sub-query where the engine answered without citing your site, "
                "a concrete place to win a citation.",
                "",
            ])
            if gaps:
                lines.append(f"**Top fan-out gaps ({min(len(gaps), 5)} of {len(gaps)}):**")
                lines.append("")
                for g in gaps[:5]:
                    lines.append(f"- {g}")
                lines.append("")
            if covered:
                lines.append(f"**Already cited in {len(covered)} sub-quer{'y' if len(covered) == 1 else 'ies'}:** "
                             + ", ".join(covered[:3]) + ("..." if len(covered) > 3 else ""))
                lines.append("")
            lines.append(f"> {fan.get('disclaimer', '')}")
            lines.append("")

    # Section 4: AI Visibility (if available)
    if visibility_results:
        lines.extend([
            "---",
            "",
            "## Section 4: AI Visibility [BEST-EFFORT]",
            "",
            "Visibility measures whether AI systems KNOW about you, even without linking to your URL.",
            "This is different from citation (Section 3). You can be visible but not cited, or cited but not visible.",
            "",
            "**Per-signal scores (the load-bearing numbers, see methodology note):**",
            "",
        ])

        by_cat_pre = visibility_results.get("by_category", {}) or {}
        sig_descriptions = {
            "brand_recognition": "Brand recognition (does the model know you exist when asked directly)",
            "concept_attribution": "Topic association (does the model link you to your topics, paraphrase-tolerant)",
            "recommendation": "Active recommendation (does the model recommend you to users)",
        }
        for cat in ("brand_recognition", "concept_attribution", "recommendation"):
            if cat in by_cat_pre:
                cd = by_cat_pre[cat]
                desc = sig_descriptions.get(cat, cat)
                lines.append(f"- **{desc}:** {cd['visible']}/{cd['total']} = {cd['rate_pct']}%")
        lines.append("")

        agg_pct = visibility_results.get("visibility_rate_pct", 0)
        agg_visible = visibility_results.get("visible_count", 0)
        agg_testable = visibility_results.get("testable", 0)
        agg_total = visibility_results.get("total_tests", 0)
        agg_unknown = agg_total - agg_testable if (agg_total and agg_testable) else 0
        agg_line = (
            f"- Aggregate visibility: {agg_pct}% "
            f"({agg_visible}/{agg_testable} testable; "
            f"{agg_unknown}/{agg_total} queries excluded as UNKNOWN)"
        )
        lines.extend([
            f"**Verdict:** {visibility_results.get('verdict', 'N/A')}",
            f"**Confidence:** {visibility_results.get('confidence_label', 'LOW')}",
            "",
            "*Aggregate (denominator excludes UNKNOWN responses; per-signal rates above use full denominators, so they will not match):*",
            agg_line,
            f"- Brand recognized in {visibility_results.get('known_count', 0)} responses",
            f"- Active recommendations in {visibility_results.get('recommended_count', 0)} responses",
            "",
        ])

        by_cat = visibility_results.get("by_category", {})
        if by_cat:
            lines.append("| Signal | Visible | Rate |")
            lines.append("|--------|---------|------|")
            cat_labels = {
                "brand_recognition": "Brand Recognition",
                "concept_attribution": "Concept Attribution",
                "recommendation": "Recommendation",
            }
            for cat, cdata in by_cat.items():
                label = cat_labels.get(cat, cat.replace("_", " ").title())
                lines.append(f"| {label} | {cdata['visible']}/{cdata['total']} | {cdata['rate_pct']}% |")
            lines.append("")

        by_plat = visibility_results.get("by_platform", {})
        if by_plat:
            lines.append("| Platform | Visible | Rate |")
            lines.append("|----------|---------|------|")
            for pname, pdata in by_plat.items():
                lines.append(f"| {pname} | {pdata['visible']}/{pdata['total']} | {pdata['rate_pct']}% |")
            lines.append("")

        # Interpretation
        vis_rate = visibility_results.get("visibility_rate_pct", 0)
        known = visibility_results.get("known_count", 0)
        rec = visibility_results.get("recommended_count", 0)

        if known > 0 and rec == 0 and vis_rate < 50:
            lines.extend([
                "**Interpretation:** AI systems recognize your brand but do not associate you with your topics yet. ",
                "This is common for newer sites with some web presence but limited topical authority. ",
                "Guest posts, backlinks, and consistent publishing on your core topics will bridge this gap.",
                "",
            ])
        elif vis_rate > 80:
            lines.extend([
                "**Interpretation:** AI systems are highly aware of your brand and associate you with your topics. ",
                "Focus on converting this visibility into citations by ensuring your content is crawlable and structured.",
                "",
            ])
        elif vis_rate == 0:
            lines.extend([
                "**Interpretation:** AI systems show no awareness of your brand. ",
                "Build web presence first: publish content, get backlinks, establish domain authority.",
                "",
            ])

    # Recommendations -- buyer-facing, with expected results and effort estimates.
    # Internal check codes (1.3_schema_markup, etc.) are replaced with plain-language
    # labels. Who does it, rough effort, and expected result are explicit per item.
    # HONESTY GUARD: expected results are qualitative -- no fabricated numbers.
    lines.extend([
        "---",
        "",
        "## Recommendations",
        "",
    ])

    seo_verdict = seo_results.get("section_verdict", "FAIL")
    ai_verdict = ai_results.get("section_verdict", "FAIL")

    if seo_verdict == "FAIL":
        lines.append("### Priority 1: Fix SEO Foundation")
        lines.append(
            "Your site has critical search foundation issues that block AI citation. "
            "Fix these first -- AI systems source their answers from the web, so they "
            "cannot cite you if search crawlers cannot find you."
        )
        lines.append("")
        for check in seo_results.get("checks", []):
            if check.get("verdict") == "FAIL":
                lines.extend(_format_check_as_recommendation(check, "FAIL"))

    if ai_verdict != "PASS":
        lines.append("### Priority 2: Improve AI Infrastructure")
        lines.append(
            "These gaps prevent AI crawlers from finding, parsing, or citing your content accurately."
        )
        lines.append("")
        for check in ai_results.get("checks", []):
            if check.get("verdict") in ("FAIL", "PARTIAL"):
                lines.extend(_format_check_as_recommendation(check, check.get("verdict", "FAIL")))

    if overall == "AI-READY":
        lines.append("### Next Steps")
        lines.append("Your infrastructure is ready. Focus on:")
        lines.append("- Content quality and topical authority (publish consistently on your core topics)")
        lines.append("- Building backlinks from high-DA sources (results appear over weeks to months)")
        lines.append("- Monthly citation monitoring to track trends over time")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")

    if client_name:
        lines.extend([
            f"*Prepared by {consultant_name} using the AI Visibility Readiness Framework v1.0.0*",
            "",
            "**Methodology:** Every check in this report is labeled [VERIFIABLE] (reproducible, backed by "
            "free tools) or [BEST-EFFORT] (point-in-time sample, confidence-labeled). We do not combine "
            "these tiers into a single score. Full methodology available on request.",
            "",
            "**Disclaimer:** Section 3 (Citation Monitoring), if included, contains point-in-time observations "
            "with explicitly labeled confidence. AI citation behavior varies by session, location, and "
            "platform updates. Re-run monthly to track trends.",
        ])
    else:
        lines.extend([
            "*Generated by AI Visibility Readiness Framework v1.0.0*",
            f"*Methodology: [FRAMEWORK.md](../FRAMEWORK.md)*",
            "",
            "**Disclaimer:** Section 3 (Citation Monitoring) results are point-in-time observations with LOW confidence.",
            "AI citation behavior varies by session, location, and platform updates.",
            "Do not make investment decisions based on a single citation test round.",
        ])

    return "\n".join(lines)


def _self_check() -> bool:
    """Minimal self-check: verify the 3 buyer-framing invariants against fixture data.

    Tests:
    1. Executive summary leads with buyer-felt outcome, not a pass-count.
    2. A recommendation row includes 'Expected result:'.
    3. A SKIPPED check includes 'To unlock this check:'.

    Returns True on pass, False on failure. No test framework dependency.
    Run via: python report_generator.py --self-check
    """
    seo_fixture = {
        "section_verdict": "FAIL",
        "checks": [
            {"check": "1.3_schema_markup", "tier": "VERIFIABLE", "verdict": "FAIL"},
            {
                "check": "1.1_core_web_vitals",
                "tier": "VERIFIABLE",
                "verdict": "SKIPPED",
                "note": "Lighthouse skipped (--skip-lighthouse flag)",
            },
        ],
    }
    ai_fixture = {
        "section_verdict": "FAIL",
        "checks": [
            {
                "check": "2.2_structured_data_depth",
                "tier": "VERIFIABLE",
                "verdict": "FAIL",
                "details": {"pages_checked": 5, "pages_with_schema": 0},
            },
        ],
    }
    report = generate_report(seo_fixture, ai_fixture, client_name="TestCo Inc")

    failures = []

    # 1. Executive summary leads with buyer-felt outcome, not a pass-count.
    exec_start = report.find("## Executive Summary")
    if exec_start == -1:
        failures.append("Executive Summary section not found in output")
    else:
        exec_section = report[exec_start + len("## Executive Summary"):exec_start + 400]
        # The first non-blank content should be the buyer outcome, not "This audit ran..."
        first_content_line = ""
        for line in exec_section.split("\n"):
            stripped = line.strip()
            if stripped:
                first_content_line = stripped
                break
        if first_content_line.startswith("This audit ran"):
            failures.append(
                "Executive summary opens with pass-count language ('This audit ran...') "
                "instead of buyer outcome"
            )
        if "AI assistants" not in exec_section[:300]:
            failures.append(
                "Executive summary does not lead with buyer-felt outcome "
                "(expected 'AI assistants...' in first 300 chars after header)"
            )

    # 2. At least one recommendation row includes 'Expected result:'.
    if "Expected result:" not in report:
        failures.append(
            "No 'Expected result:' found anywhere in report "
            "(buyer-facing expected outcome missing from recommendations)"
        )

    # 3. A SKIPPED check includes 'To unlock this check:'.
    if "To unlock this check:" not in report:
        failures.append(
            "No 'To unlock this check:' found in report "
            "(unlock roadmap missing for SKIPPED check)"
        )

    if failures:
        for f in failures:
            print(f"  SELF-CHECK FAIL: {f}", file=sys.stderr)
        return False

    print(
        "[report_generator self-check] PASS: all 3 buyer-framing invariants verified.",
        file=sys.stderr,
    )
    return True


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        ok = _self_check()
        sys.exit(0 if ok else 1)

    if len(sys.argv) < 3:
        print("Usage: python report_generator.py <seo_results.json> <ai_results.json> [citation_results.json]")
        print("       python report_generator.py --self-check   # verify buyer-framing invariants")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        seo = json.load(f)
    with open(sys.argv[2]) as f:
        ai = json.load(f)

    citation = None
    if len(sys.argv) > 3:
        with open(sys.argv[3]) as f:
            citation = json.load(f)

    report = generate_report(seo, ai, citation)
    print(report)
