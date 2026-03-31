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


def _build_top_actions(seo_results: dict, ai_results: dict, overall: str) -> list[str]:
    """Extract the top 3 prioritized actions from check results."""
    actions = []

    if overall == "AI-READY":
        actions.append("Run the 20-query citation test (Section 3) to establish your baseline citation rate.")
        actions.append("Build backlinks from high-DA sources to increase domain authority.")
        actions.append("Publish content monthly and re-run this audit quarterly to track progress.")
        return actions[:3]

    # Priority 1: SEO failures
    for check in seo_results.get("checks", []):
        if check.get("verdict") == "FAIL":
            name = check["check"].split("_", 1)[1].replace("_", " ").title() if "_" in check["check"] else check["check"]
            if "indexability" in check["check"]:
                actions.append(f"Fix content indexability: ensure server-side rendering and remove noindex tags.")
            elif "crawlability" in check["check"]:
                actions.append(f"Fix technical crawlability: add robots.txt, sitemap.xml, and enforce HTTPS.")
            elif "schema" in check["check"]:
                actions.append(f"Add structured data (JSON-LD) with appropriate @type for your content.")
            elif "web_vitals" in check["check"] or "page_speed" in check["check"]:
                actions.append(f"Improve page performance: target LCP < 2.5s, CLS < 0.1.")
            else:
                actions.append(f"Fix: {name}")

    # Priority 2: AI infra failures
    for check in ai_results.get("checks", []):
        if check.get("verdict") == "FAIL":
            if "llms_txt" in check["check"]:
                actions.append("Create /llms.txt describing your site for AI crawlers.")
            elif "crawler_access" in check["check"]:
                actions.append("Update robots.txt to allow GPTBot, ClaudeBot, and PerplexityBot.")
            elif "structured_data" in check["check"]:
                actions.append("Add schema markup to more pages (target >80% coverage).")
            elif "content_structure" in check["check"]:
                actions.append("Improve heading hierarchy: single H1, logical H2/H3 sections.")
            elif "semantic" in check["check"]:
                actions.append("Use semantic HTML (<article>, <main>, <nav>) instead of generic <div>.")
            elif "content_ratio" in check["check"]:
                actions.append("Increase text-to-HTML ratio: reduce framework overhead or add more content.")

    # Priority 3: AI infra partials
    for check in ai_results.get("checks", []):
        if check.get("verdict") == "PARTIAL" and len(actions) < 3:
            name = check["check"].split("_", 1)[1].replace("_", " ").title() if "_" in check["check"] else check["check"]
            actions.append(f"Improve: {name} (currently partial)")

    return actions[:3]


def generate_report(
    seo_results: dict,
    ai_results: dict,
    citation_results: dict | None = None,
    visibility_results: dict | None = None,
    url: str = "",
    client_name: str | None = None,
    consultant_name: str = "Chudi Nnorukam",
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

    lines.extend([
        "",
        "## Executive Summary",
        "",
        f"**Overall Status: {overall}**",
        "",
        f"This audit ran {total_count} automated checks across two categories: SEO Foundation "
        f"(traditional search readiness) and AI Infrastructure (AI search readiness). "
        f"**{pass_count} of {total_count} checks passed.**",
        "",
    ])

    # Status explanation
    status_explanations = {
        "AI-READY": "Your site has removed all measurable barriers to AI citation. "
                     "The remaining factors (domain authority, content depth, backlinks) "
                     "are built over time through publishing and link acquisition.",
        "FOUNDATION-READY": "Your traditional SEO foundation is solid, but AI-specific "
                           "infrastructure needs attention. AI crawlers may not be able to "
                           "find or parse your content optimally.",
        "INFRASTRUCTURE-READY": "Your AI infrastructure is in place, but traditional SEO "
                               "foundations are broken. Since AI search systems rely on web "
                               "search results as their source, fixing SEO is the priority.",
        "NOT-READY": "Both SEO foundations and AI infrastructure need work. Start with SEO "
                    "fundamentals. AI visibility cannot exist without search visibility.",
    }
    lines.append(status_explanations.get(overall, ""))

    lines.extend([
        "",
        "| Section | Verdict |",
        "|---------|---------|",
        f"| SEO Foundation | {verdict_emoji(seo_results.get('section_verdict', 'FAIL'))} |",
        f"| AI Infrastructure | {verdict_emoji(ai_results.get('section_verdict', 'FAIL'))} |",
    ])

    if visibility_results:
        lines.append(f"| AI Visibility | {visibility_results.get('verdict', 'N/A')} ({visibility_results.get('visibility_rate_pct', 0)}%) |")
    if citation_results:
        lines.append(f"| AI Citations | {verdict_emoji(citation_results.get('verdict', 'NOT_CITED'))} ({citation_results.get('citation_rate_pct', 0)}%) |")

    # Top 3 actions
    lines.extend([
        "",
        "### Top 3 Actions (in priority order)",
        "",
    ])
    for i, action in enumerate(top_actions, 1):
        lines.append(f"{i}. {action}")

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

    # Section 3 (if available)
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
            f"**Verdict:** {visibility_results.get('verdict', 'N/A')}",
            f"**Confidence:** {visibility_results.get('confidence_label', 'LOW')}",
            "",
            f"- Visibility rate: {visibility_results.get('visibility_rate_pct', 0)}%",
            f"- Brand recognized: {visibility_results.get('known_count', 0)} times",
            f"- Recommended by AI: {visibility_results.get('recommended_count', 0)} times",
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
                "This is common for new sites with some web presence but limited topical authority. ",
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

    # Recommendations
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
        lines.append("AI visibility depends on traditional search visibility. Fix Section 1 failures first.")
        lines.append("")
        for check in seo_results.get("checks", []):
            if check.get("verdict") == "FAIL":
                lines.append(f"- **{check['check']}**: Needs attention")
        lines.append("")

    if ai_verdict != "PASS":
        lines.append("### Priority 2: Improve AI Infrastructure")
        lines.append("These checks ensure AI systems can find and parse your content.")
        lines.append("")
        for check in ai_results.get("checks", []):
            if check.get("verdict") in ("FAIL", "PARTIAL"):
                lines.append(f"- **{check['check']}**: {check['verdict']}")
        lines.append("")

    if overall == "AI-READY":
        lines.append("### Next Steps")
        lines.append("Your infrastructure is ready. Focus on:")
        lines.append("- Content quality and topical authority")
        lines.append("- Building backlinks from high-DA sources")
        lines.append("- Monthly citation monitoring to track trends")
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


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python report_generator.py <seo_results.json> <ai_results.json> [citation_results.json]")
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
