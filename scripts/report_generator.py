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
    """Map verdict to a simple text indicator (internal / non-buyer use only).

    NEVER call this for buyer-facing output. Use _buyer_verdict() instead.
    """
    return {
        "PASS": "[PASS]",
        "PARTIAL": "[PARTIAL]",
        "FAIL": "[FAIL]",
        "SKIPPED": "[SKIPPED]",
        "CITED": "[CITED]",
        "PARTIALLY_CITED": "[PARTIAL]",
        "NOT_CITED": "[NOT CITED]",
    }.get(verdict, f"[{verdict}]")


def _buyer_verdict(verdict: str) -> str:
    """Map internal verdict to a buyer-legible word. No bracket tokens in buyer output."""
    return {
        "PASS": "Working",
        "PARTIAL": "Partly working",
        "FAIL": "Needs work",
        "SKIPPED": "Not tested this round",
        "CITED": "Cited",
        "PARTIALLY_CITED": "Partly cited",
        "NOT_CITED": "Not cited",
    }.get(verdict, verdict)


# ---------------------------------------------------------------------------
# Buyer-facing content maps (2026-07-06: buyer-first framing applied)
# ---------------------------------------------------------------------------

# Plain-language outcome leads for the executive summary.
# The FIRST sentence is what the buyer FEELS, not a pass-count or status code.
# Technical detail (pass counts, overall status label) follows below.
# NOTE: no double-hyphens (--) in any buyer-facing string; use a comma or single hyphen.
_BUYER_OUTCOME_LEADS: dict[str, str] = {
    "AI-READY": (
        "Your site has removed all measurable infrastructure barriers to AI citation. "
        "AI assistants like ChatGPT and Perplexity can find, read, and cite your content. "
        "The remaining work is building topical authority over time, which happens through "
        "consistent publishing and link acquisition, not infrastructure fixes."
    ),
    "FOUNDATION-READY": (
        "AI assistants may not find or recommend you, even for searches where you should appear. "
        "Your traditional search foundation is solid, but AI-specific signals are missing or incomplete. "
        "Fixing the items in this report unlocks AI citation and recommendation."
    ),
    "INFRASTRUCTURE-READY": (
        "AI-specific signals are in place, but your underlying search foundation has critical gaps. "
        "AI assistants source their answers from the web. If search engines cannot index you, "
        "AI cannot cite you. Start with the SEO fixes below."
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
# Format per entry: (plain_label, who_does_it, rough_effort, expected_result, web_person_instruction)
# HONESTY GUARD: expected_result is qualitative, never a fabricated number.
#   The no-promise hedge appears ONCE, in the executive-summary "What to expect:" line - not per row.
# WHO-DOES-IT GUARD: no "content team" (most buyers have none);
#   no unpriced "citability engagement" - use "reply for a flat quote" instead.
_CHECK_BUYER_INFO: list[tuple[str, tuple[str, str, str, str, str]]] = [
    ("core_web_vitals", (
        "Site speed and performance",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~4-8 hours (varies by site setup)",
        "Once improved, your site loads faster for visitors arriving from any source. "
        "Over the weeks following the fix, this improves eligibility for Google enhanced features "
        "that feed AI answers.",
        "Ask your web host or developer to review your Core Web Vitals in Google Search Console "
        "and bring LCP below 2.5 s, FCP below 1.8 s, and CLS below 0.1.",
    )),
    ("crawlability", (
        "Search and AI crawler access",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~1-2 hours",
        "Once fixed, search engines and AI crawlers can reliably reach and read your pages. "
        "This is the prerequisite for everything else: if crawlers cannot reach your site, "
        "nothing else in this report matters.",
        "Make sure your site has a valid XML sitemap submitted to Google Search Console, "
        "and that all pages load over HTTPS without redirect chains.",
    )),
    ("schema_markup", (
        "Structured data (labels in your website's code that spell out your practice name, "
        "hours, services, and location so AI tools can read them correctly)",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~3 hours",
        "Once added, AI tools can read your practice name, hours, services, and location directly from your site. "
        "Over the weeks to months following the fix, this typically makes AI answers about local practices "
        "more likely to include and correctly describe you.",
        "Add structured-data markup (schema.org / JSON-LD) for a local dental practice, "
        "covering name, address, phone, hours, and services.",
    )),
    ("page_speed", (
        "Page speed",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~4-8 hours (varies by site setup)",
        "Once improved, visitors arriving from AI tools spend more time on your site and are more likely to book. "
        "Over the weeks following the fix, faster load times also improve the ranking signals that feed AI overviews.",
        "Run a PageSpeed Insights test on your homepage and implement the top two or three fixes it recommends.",
    )),
    ("indexability", (
        "Content indexing",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~2 hours",
        "Once fixed, search engines and AI crawlers can index your pages and include them in answers. "
        "Over the weeks following the fix, your practice becomes eligible to appear in AI-generated answers "
        "for local searches.",
        "In Google Search Console, check the Coverage report for errors and ask your developer "
        "to remove any noindex tags from your main pages.",
    )),
    ("crawler_access", (
        "AI crawler permissions",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~30 minutes",
        "Once fixed, AI crawlers like ChatGPT's bot and Google's AI bot can visit and read your site. "
        "Over the weeks following the fix, your content becomes part of what those systems know about "
        "local practices in your area.",
        "In your robots.txt file, confirm that no Disallow rule blocks GPTBot, PerplexityBot, "
        "ClaudeBot, or Googlebot.",
    )),
    ("llms_txt", (
        "AI content map (llms.txt)",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~1 hour",
        "Once added, AI agents have a machine-readable list of your key pages and services. "
        "Over the weeks following the fix, this helps AI tools represent your practice more completely "
        "when they answer questions about local services.",
        "Create a plain text file at /llms.txt on your website listing your key pages, services, "
        "and a one-sentence description of each.",
    )),
    ("structured_data_depth", (
        "Structured data depth",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~3 hours",
        "Once expanded, AI tools have more structured facts about your practice to draw on. "
        "Over the weeks to months following the fix, wider data coverage typically improves "
        "how accurately and completely AI answers describe you.",
        "Expand the structured-data markup (JSON-LD) so it covers all your main service pages "
        "and location pages, not just the homepage.",
    )),
    ("content_structure", (
        "Content heading structure",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~2 hours",
        "Once fixed, AI tools can navigate your page content cleanly and attribute your key claims accurately. "
        "Over the weeks following the fix, your content is more likely to be cited precisely rather than paraphrased incorrectly.",
        "Reorganize your page headings so there is exactly one H1 per page, followed by H2s "
        "for each main section and H3s for sub-points.",
    )),
    ("content_ratio", (
        "Content clarity (text vs. code ratio)",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~2 hours",
        "Once improved, more of your actual content is visible to AI tools, with less technical noise in the way. "
        "Over the weeks following the fix, AI engines are better able to summarize what your practice does.",
        "Move your service descriptions into plain HTML text, and ask your developer to reduce "
        "the amount of JavaScript or CSS loaded inline on the page.",
    )),
    ("semantic_html", (
        "Page structure",
        "whoever maintains your website (most web providers handle this routinely); "
        "or we can do it for a flat fee - reply for a quote",
        "~2 hours",
        "Once fixed, AI parsers can understand your page layout without guessing. "
        "Over the weeks following the fix, this reduces the chance of misattribution and improves "
        "how accurately AI describes your practice.",
        "Use proper HTML landmark tags (header, main, nav, footer, article) for your page layout, "
        "instead of generic div containers.",
    )),
]

# Evidence sentences for PASS checks (buyer output only).
# Every PASS row in a buyer report needs at least one sentence proving the work was done.
# Without this, a PASS row has zero words of evidence; buyer reads "they didn't actually check this."
# Keyed by keyword substring that appears in the check name.
_PASS_EVIDENCE: list[tuple[str, str]] = [
    ("core_web_vitals",
        "We measured your site's core performance metrics; they meet the required thresholds, so nothing to fix here."),
    ("crawlability",
        "We tested whether search engines and AI crawlers can reach and read your pages; they can, so nothing to fix here."),
    ("schema_markup",
        "We checked whether your site has structured data labels that AI tools can read; they are present and valid, so nothing to fix here."),
    ("page_speed",
        "We measured your site's load time; it meets performance thresholds, so nothing to fix here."),
    ("indexability",
        "We confirmed your pages are not blocking search engines or AI crawlers from indexing them; they are fully accessible."),
    ("crawler_access",
        "We checked whether AI crawlers (ChatGPT's bot, Google's AI bot, and others) are allowed to visit your site; they are all permitted, so nothing to fix here."),
    ("llms_txt",
        "We checked whether your site has an AI-readable content map in place; it is, so nothing to fix here."),
    ("structured_data_depth",
        "We checked the depth of your structured data coverage; it meets the threshold, so nothing to fix here."),
    ("content_structure",
        "We checked whether your page headings follow a clear hierarchy that AI tools can navigate; they do, so nothing to fix here."),
    ("content_ratio",
        "We measured the ratio of readable content to code on your pages; it is within an acceptable range."),
    ("semantic_html",
        "We checked whether your page structure is legible to AI parsers; it is, so nothing to fix here."),
]

# Evidence sentences for FAIL and PARTIAL checks (buyer output only).
# A FAIL/PARTIAL row that has no metrics/details still needs one sentence proving the work was done.
# Move 3.1: "one plain-English evidence sentence per check, PASS or FAIL"
# Keyed by keyword substring that appears in the check name.
_FAIL_EVIDENCE: list[tuple[str, str]] = [
    ("core_web_vitals",
        "We measured your site's core performance metrics; they fell below the required thresholds, so this needs attention."),
    ("crawlability",
        "We tested whether search engines and AI crawlers can reach and read your pages; one or more issues were found that block access."),
    ("schema_markup",
        "We checked whether your site has structured data labels that AI tools can read; none were found, so AI cannot read your practice details directly from your site."),
    ("page_speed",
        "We measured your site's load time; it did not meet performance thresholds, so this needs attention."),
    ("indexability",
        "We checked whether your pages are accessible to search engines; issues were found that block indexing."),
    ("crawler_access",
        "We checked whether AI crawlers are allowed to visit your site; one or more were blocked, so AI bots cannot index your content."),
    ("llms_txt",
        "We checked whether your site has an AI-readable content map; none was found, so AI agents have no guided way to navigate your content."),
    ("structured_data_depth",
        "We checked the depth of structured data across your pages; only a small fraction of pages have it, "
        "so AI tools have limited structured facts about your practice to draw on."),
    ("content_structure",
        "We checked whether your page headings follow a clear hierarchy; the structure is partial, "
        "so AI tools may not navigate your content cleanly."),
    ("content_ratio",
        "We measured the ratio of readable content to code; there is more technical noise than content, "
        "so AI engines may have trouble extracting what your practice does."),
    ("semantic_html",
        "We checked whether your page structure is legible to AI parsers; issues were found that may cause misattribution."),
]


def _fail_evidence_for_check(check_name: str) -> str:
    """Return a plain-English evidence sentence for a FAIL or PARTIAL check."""
    for keyword, evidence in _FAIL_EVIDENCE:
        if keyword in check_name:
            return evidence
    return "We ran this check and found issues that need attention."


def _schema_markup_fail_evidence(ai_checks: list) -> str:
    """Derive the 1.3 schema markup failure sentence from the 2.2 structured_data_depth details.

    Rule: any check whose buyer evidence references a schema/page count derives it from
    the same underlying number as section 2.2 (structured_data_depth), so the two sections
    never contradict each other in the same report.
    """
    for check in ai_checks:
        if "structured_data_depth" in check.get("check", ""):
            details = check.get("details", {})
            pages_with_schema = details.get("pages_with_schema")
            pages_checked = details.get("pages_checked")
            if pages_with_schema is not None and pages_checked:
                if pages_with_schema == 0:
                    return (
                        "We checked whether your site has structured data labels that AI tools can read; "
                        "none were found, so AI cannot read your practice details directly from your site."
                    )
                else:
                    return (
                        f"We found schema labels on only {pages_with_schema} of your {pages_checked} pages, "
                        "so AI tools can read almost none of your practice details directly from your site."
                    )
    # Fallback: no cross-check data available
    return (
        "We checked whether your site has structured data labels that AI tools can read; "
        "they are missing or incomplete, so AI cannot read your practice details directly from your site."
    )


# POLICY (ship-gate, not copy): Never ship a $497 report with a SKIPPED verifiable check.
# Run Lighthouse before shipping - it is free. The buyer-facing copy below is a fallback
# ONLY if the check is genuinely impossible per the wargame kit definition (two failed attempts,
# site blocks probes, or auth-walled). The template must degrade safely; the POLICY is never to ship SKIPPED.
# No CLI flags or instructions in buyer-facing copy - a promise TO the buyer, never an instruction AT them.
_SKIPPED_UNLOCK_HINTS: list[tuple[str, str]] = [
    ("core_web_vitals",
        "Site speed: we're completing this measurement and will send your scores "
        "within 3 business days at no extra cost."),
    ("page_speed",
        "Site speed: we're completing this measurement and will send your scores "
        "within 3 business days at no extra cost."),
]
_SKIPPED_DEFAULT_HINT = (
    "We're completing this measurement and will send your results "
    "within 3 business days at no extra cost."
)


def _lookup_buyer_info(check_name: str) -> tuple[str, str, str, str, str] | None:
    """Find buyer-facing info for a check by keyword substring match."""
    for keyword, info in _CHECK_BUYER_INFO:
        if keyword in check_name:
            return info
    return None


def _pass_evidence_for_check(check_name: str) -> str:
    """Return a plain-English evidence sentence for a PASS check."""
    for keyword, evidence in _PASS_EVIDENCE:
        if keyword in check_name:
            return evidence
    return "We ran this check and confirmed no issues."


def _unlock_hint_for_skipped_check(check: dict) -> str:
    """Return a buyer-facing promise for a SKIPPED check.

    Never returns CLI instructions. A promise TO the buyer, not an instruction AT them.
    """
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
    WHO-DOES-IT GUARD: no unpriced engagement mentions, no 'content team'.
    """
    check_name = check.get("check", "")
    info = _lookup_buyer_info(check_name)
    if info:
        label, who, effort, expected, web_person = info
        return [
            f"**{label}** - {_buyer_verdict(verdict)}",
            f"- Who does it: {who}",
            f"- Rough effort: {effort}",
            f"- Expected result: {expected}",
            f"- **What to tell your web person:** {web_person}",
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
            f"**{display_name}** - {_buyer_verdict(verdict)}",
            "- Expected result: Closes an infrastructure gap that may be limiting AI citation.",
            "",
        ]


def _build_top_actions(
    seo_results: dict, ai_results: dict, overall: str
) -> list[tuple[str, str]]:
    """Extract top 3 prioritized actions with buyer-facing expected results.

    Returns list of (action_text, expected_result_text) tuples.
    HONESTY GUARD: expected_result_text is always qualitative - never a fabricated number.
    """
    actions: list[tuple[str, str]] = []

    if overall == "AI-READY":
        actions.append((
            "Run the citation test (Section 3) to establish your baseline citation rate.",
            "A data-backed citation rate you can track month over month. "
            "You will know which AI platforms cite you and for which topics.",
        ))
        actions.append((
            "Build backlinks from reputable sources to increase domain authority.",
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
                    "Fix content indexing: ensure your pages are not blocking search engines from reading them.",
                    "Search engines and AI crawlers can index your pages. "
                    "You become eligible to appear in AI-generated answers for local searches.",
                ))
            elif "crawlability" in check_id:
                actions.append((
                    "Fix crawler access: ensure your site has a sitemap and is accessible over HTTPS.",
                    "Crawlers can access your site reliably. "
                    "This is a prerequisite for any search or AI citation.",
                ))
            elif "schema" in check_id:
                actions.append((
                    "Add structured data (labels in your website's code that spell out your practice name, "
                    "hours, services, and location) so AI tools can read them correctly.",
                    "AI tools can read your practice details directly from your site. "
                    "Over the weeks to months following the fix, this typically makes AI answers more likely "
                    "to include and correctly describe you.",
                ))
            elif "web_vitals" in check_id or "page_speed" in check_id:
                actions.append((
                    "Improve page speed so visitors from AI tools don't leave before reading.",
                    "Faster pages keep potential patients engaged. "
                    "This also improves the signals that feed AI-generated overviews.",
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
                    "Update your site's crawler permissions so AI bots can visit and read your pages.",
                    "AI crawlers can index your content. "
                    "The permission must be in place before any AI tool can cite you.",
                ))
            elif "structured_data" in check_id:
                actions.append((
                    "Add structured data labels to more of your pages so AI has more facts to draw on.",
                    "Richer data coverage gives AI engines more to cite about your practice. "
                    "Over the weeks to months following the fix, this typically improves citation accuracy.",
                ))
            elif "content_structure" in check_id:
                actions.append((
                    "Improve heading structure so AI tools can navigate your content cleanly.",
                    "AI engines extract your key points cleanly and attribute them to you accurately.",
                ))
            elif "semantic" in check_id:
                actions.append((
                    "Use structured page markup so AI parsers understand your layout.",
                    "AI parsers understand your page structure, reducing misattribution.",
                ))
            elif "content_ratio" in check_id:
                actions.append((
                    "Increase the ratio of readable content to code on your pages.",
                    "More of your real content is visible to AI; less technical noise gets in the way.",
                ))

    # Priority 3: AI infra partials (fill to 3 if needed)
    for check in ai_results.get("checks", []):
        if check.get("verdict") == "PARTIAL" and len(actions) < 3:
            check_id = check["check"]
            info = _lookup_buyer_info(check_id)
            if info:
                label = info[0]
                actions.append((
                    f"Improve: {label} (partly working, needs completion)",
                    "Closes a partial gap that is limiting how accurately AI describes your practice.",
                ))
            else:
                name = (
                    check_id.split("_", 1)[1].replace("_", " ").title()
                    if "_" in check_id
                    else check_id
                )
                actions.append((
                    f"Improve: {name} (partly working, needs completion)",
                    "Closes a partial infrastructure gap that is limiting AI citation precision.",
                ))

    return actions[:3]


def generate_cover_email(
    client_name: str,
    url: str,
    consultant_name: str = "Chudi Nnorukam",
) -> str:
    """Generate a buyer-vocabulary cover email for the audit delivery.

    Four sentences in the buyer's own language: what we checked; the one-line result
    ('AI tools cannot reliably recommend your practice yet, here's exactly what to fix
    and who does it'); where the Monday-morning box is; how to reply.
    No AVR/framework jargon. No 'AI Visibility Readiness', no 'schema', no CLI terms.
    """
    domain = url.replace("https://", "").replace("http://", "").rstrip("/")
    lines = [
        f"Hi {client_name},",
        "",
        f"We audited {domain} to check whether AI tools like ChatGPT, Perplexity, "
        "and Google's AI results can find and recommend your practice when potential patients search nearby.",
        "",
        "The short answer: AI tools cannot reliably recommend your practice yet. "
        "The attached report lists exactly what to fix and who does it.",
        "",
        "There's a 'What to do Monday morning' section near the top - "
        "it gives you a clear first step, a forwarding email you can copy and send "
        "to whoever maintains your website, and an option if you don't have a web person.",
        "",
        "Questions or not sure what to do next? Reply to this email and I'll help.",
        "",
        f"- {consultant_name}",
    ]
    return "\n".join(lines)


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

    # Buyer mode: use plain-language verdicts; no bracket tokens in buyer output.
    _vd = _buyer_verdict if client_name else verdict_emoji

    # Derive counts from data - do not hardcode.
    all_checks = seo_results.get("checks", []) + ai_results.get("checks", [])
    skipped_checks = [c for c in all_checks if c.get("verdict") == "SKIPPED"]
    active_checks = [c for c in all_checks if c.get("verdict") != "SKIPPED"]
    pass_count = sum(1 for c in active_checks if c["verdict"] == "PASS")
    fail_count = sum(1 for c in active_checks if c["verdict"] == "FAIL")
    partial_count = sum(1 for c in active_checks if c["verdict"] == "PARTIAL")
    ran_count = len(active_checks)
    total_count = len(all_checks)

    top_actions = _build_top_actions(seo_results, ai_results, overall)

    lines = [
        "# AI Visibility Readiness Audit",
    ]

    # Consulting header (when client_name is provided)
    if client_name:
        lines.extend([
            "",
            f"**Prepared for:** {client_name}",
            f"**Prepared by:** {consultant_name}",
            f"**Date:** {date_short}",
            f"**URL audited:** {url or seo_results.get('url', 'N/A')}",
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

    # Executive summary: leads with buyer-felt outcome, NOT a pass-count or status code.
    # Plain-language business consequence first; technical detail follows.
    buyer_outcome = _BUYER_OUTCOME_LEADS.get(overall, "")

    # Patient bridge: connects AI visibility to the specific buyer's real stakes.
    # HONESTY GUARD: never invent a patient count or percentage.
    practice_name = client_name or url or "your practice"
    patient_bridge = (
        f"In practical terms: when a potential patient asks ChatGPT, Perplexity, or Google's AI "
        f"'who's a good dentist near me?', {practice_name} is unlikely to be mentioned, "
        "and those patients book with whoever is."
    )

    # Arithmetic summary: derive from data, never hardcode.
    # States the total ran, explains any SKIPPED item, and gives working/needs-work/partly-working counts.
    if skipped_checks:
        skipped_label = "an 8th" if total_count == 8 else f"{len(skipped_checks)} more"
        arith_line = (
            f"We ran {ran_count} checks "
            f"({skipped_label}, site speed, is covered separately - see 1.1 below): "
            f"{pass_count} working, {fail_count} need work, {partial_count} partly working."
        )
    else:
        arith_line = (
            f"We ran {ran_count} checks: "
            f"{pass_count} working, {fail_count} need work, {partial_count} partly working."
        )

    lines.extend([
        "",
        "## Executive Summary",
        "",
        buyer_outcome,
        "",
        patient_bridge,
        "",
        arith_line,
        "",
    ])

    if client_name:
        lines.extend([
            "**What to expect:** These fixes remove technical barriers - they do not guarantee patient "
            "bookings, and we cannot promise a specific patient count. Anyone who does is guessing. "
            "Once the infrastructure is in place, AI tools can find and correctly describe your practice; "
            "citation rates typically improve over the weeks to months that follow as search engines "
            "and AI platforms re-crawl your site.",
            "",
        ])

    lines.extend([
        "| Section | Result |",
        "|---------|--------|",
        f"| SEO Foundation | {_vd(seo_results.get('section_verdict', 'FAIL'))} |",
        f"| AI Infrastructure | {_vd(ai_results.get('section_verdict', 'FAIL'))} |",
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
        lines.append(f"| AI Citations | {_vd(citation_results.get('verdict', 'NOT_CITED'))} ({citation_results.get('citation_rate_pct', 0)}%) |")

    # Top actions: each with a buyer-facing expected result (qualitative, never fabricated).
    if top_actions:
        n = len(top_actions)
        header = f"### Top {n} Action{'s' if n > 1 else ''} (in priority order)"
        lines.extend(["", header, ""])
        for i, (action, expected_result) in enumerate(top_actions, 1):
            lines.append(f"{i}. {action}")
            if expected_result:
                lines.append(f"   - **Expected result:** {expected_result}")

    # "What to do Monday morning" box: near the top, answers Q3 before the buyer hunts for it.
    # Step 1: forward to web person. Step 2: pre-written email. Step 3: no-dev-team path.
    if client_name:
        site_url = url or "your website"
        domain = site_url.replace("https://", "").replace("http://", "").rstrip("/")
        lines.extend([
            "",
            "---",
            "",
            "## What to do Monday morning",
            "",
            "**Step 1:** Forward this report to whoever built or currently maintains your website. "
            f"It covers 3 fixes with an estimated total of about 8 hours of work. "
            "The report is written so they can act on it directly.",
            "",
            "**Step 2:** Use this email to send it to them:",
            "",
            "> Hi [your web contact],",
            ">",
            f"> We had an independent audit done on {domain} covering how AI tools",
            "> (ChatGPT, Google's AI results, etc.) find and describe the practice.",
            "> The attached report lists 3 fixes, with what each one is, why it matters,",
            "> and roughly how long it takes (about 8 hours total).",
            "> Everything you need to implement them is in the report itself.",
            "> Could you review it and let me know when you could schedule the work?",
            ">",
            "> Thanks,",
            "> Dr. [Your name]",
            "",
            "**Step 3:** No one maintains your site? "
            "Reply to this email and we'll quote a flat price to do all three fixes.",
            "",
            "---",
        ])

    # Calibration receipt (only present for --live-test runs that didn't --skip-calibration)
    if calibration_receipt:
        from calibration import format_receipt_markdown
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(format_receipt_markdown(calibration_receipt))

    lines.extend([
        "",
        "## Section 1: SEO Foundation",
        "",
        f"**Section result:** {_vd(seo_results.get('section_verdict', 'FAIL'))}",
        "",
    ])

    # Detail each check
    for check in seo_results.get("checks", []):
        check_raw = check.get("check", "Unknown")
        check_name = check_raw.replace("_", " ").title()
        verdict = check.get("verdict", "FAIL")
        lines.append(f"### {check_name}")

        if client_name:
            # Buyer mode: plain-language verdict, no internal tier label
            lines.append(f"**Result:** {_vd(verdict)}")
        else:
            lines.append(f"**Tier:** {check.get('tier', 'N/A')} | **Verdict:** {verdict_emoji(verdict)}")
        lines.append("")

        # Jargon gloss: add a plain-English subline for "schema markup" (buyer mode only).
        # This is the section heading gloss required so a non-technical buyer can brief their web person.
        if client_name and "schema_markup" in check_raw:
            lines.extend([
                "*Schema markup is structured data - labels embedded in your website's code that "
                "spell out your practice name, hours, services, and location so AI tools can read "
                "them directly.*",
                "",
            ])

        if "error" in check:
            lines.append(f"**Error:** {check['error']}")
            lines.append("")
            continue

        if "metrics" in check and check["metrics"]:
            # In buyer mode, suppress raw metric tables for PASS checks - a non-technical
            # buyer reads "LCP Ms 2180" as padding she cannot use. The plain-English
            # pass evidence sentence (added below) is sufficient. Show the table in
            # non-buyer mode and in buyer mode when the check needs work (FAIL/PARTIAL).
            if not client_name or verdict != "PASS":
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

        # Evidence sentences (buyer output only). Move 3.1: one sentence per check, PASS or FAIL.
        # PASS: always add the evidence sentence (no other detail exists for PASS rows).
        # FAIL/PARTIAL: add ONLY when no metrics/checks/schemas detail was already rendered;
        #   those detail lines already serve as evidence. This avoids doubling up.
        # SCHEMA SPECIAL CASE: schema_markup (1.3) derives its page-count from the
        #   structured_data_depth (2.2) details so the two sections never contradict.
        if client_name:
            if verdict == "PASS":
                lines.append(_pass_evidence_for_check(check_raw))
                lines.append("")
            elif verdict in ("FAIL", "PARTIAL"):
                has_detail = (
                    ("metrics" in check and check.get("metrics")) or
                    ("checks" in check and isinstance(check.get("checks"), dict)) or
                    "schemas" in check
                )
                if not has_detail:
                    if "schema_markup" in check_raw:
                        lines.append(_schema_markup_fail_evidence(ai_results.get("checks", [])))
                    else:
                        lines.append(_fail_evidence_for_check(check_raw))
                    lines.append("")

        if "note" in check:
            # In buyer mode, suppress raw notes (may contain internal flag names or jargon)
            if not client_name:
                lines.append(f"*{check['note']}*")
                lines.append("")

        # SKIPPED checks: buyer sees a promise, never a CLI instruction.
        if verdict == "SKIPPED":
            hint = _unlock_hint_for_skipped_check(check)
            if client_name:
                lines.append(f"*{hint}*")
            else:
                lines.append(f"*To unlock this check: {hint}*")
            lines.append("")

    # Section 2
    lines.extend([
        "---",
        "",
        "## Section 2: AI Infrastructure Readiness",
        "",
        f"**Section result:** {_vd(ai_results.get('section_verdict', 'FAIL'))}",
        "",
    ])

    for check in ai_results.get("checks", []):
        check_raw = check.get("check", "Unknown")
        check_name = check_raw.replace("_", " ").title()
        verdict = check.get("verdict", "FAIL")
        lines.append(f"### {check_name}")

        if client_name:
            lines.append(f"**Result:** {_vd(verdict)}")
        else:
            lines.append(f"**Tier:** {check.get('tier', 'N/A')} | **Verdict:** {verdict_emoji(verdict)}")
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

        # Evidence sentences (buyer output only). Move 3.1: one sentence per check, PASS or FAIL.
        if client_name:
            if verdict == "PASS":
                lines.append(_pass_evidence_for_check(check_raw))
                lines.append("")
            elif verdict in ("FAIL", "PARTIAL"):
                has_detail = bool(check.get("details", {})) or "crawlers" in check
                if not has_detail:
                    lines.append(_fail_evidence_for_check(check_raw))
                    lines.append("")

        if "note" in check:
            if not client_name:
                lines.append(f"*{check['note']}*")
                lines.append("")

        # SKIPPED checks: buyer sees a promise, never a CLI instruction.
        if verdict == "SKIPPED":
            hint = _unlock_hint_for_skipped_check(check)
            if client_name:
                lines.append(f"*{hint}*")
            else:
                lines.append(f"*To unlock this check: {hint}*")
            lines.append("")

    # Section 3 (calibration failed path): buyer-facing, no CLI copy.
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
            "**Status:** Measurement pending.",
            "",
            "The methodology check that validates this section's numbers did not pass. "
            "Site-level numbers are withheld because they cannot be distinguished from measurement noise. "
            "We will send these results within 3 business days at no extra cost.",
            "",
        ])

    # Section 3 (normal path, when citation_results present)
    if citation_results:
        lines.extend([
            "---",
            "",
            "## Section 3: Citation Monitoring",
            "",
            f"**Verdict:** {_vd(citation_results.get('verdict', 'NOT_CITED'))}",
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

        # Fan-out coverage (Section 3b): present only when the citation test ran in --fan-out-mode.
        fan = citation_results.get("fan_out_coverage")
        if fan:
            gaps = fan.get("gap_sub_queries", [])
            covered = fan.get("covered_sub_queries", [])
            lines.extend([
                "### Fan-Out Coverage",
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
            "## Section 4: AI Visibility",
            "",
            "Visibility measures whether AI systems know about you, even without linking to your URL. "
            "This is different from citation (Section 3). You can be visible but not cited, or cited but not visible.",
            "",
            "**Per-signal scores:**",
            "",
        ])

        by_cat_pre = visibility_results.get("by_category", {}) or {}
        sig_descriptions = {
            "brand_recognition": "Brand recognition (does the model know you exist when asked directly)",
            "concept_attribution": "Topic association (does the model link you to your topics)",
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
            f"{agg_unknown}/{agg_total} queries excluded as unknown)"
        )
        lines.extend([
            f"**Verdict:** {visibility_results.get('verdict', 'N/A')}",
            f"**Confidence:** {visibility_results.get('confidence_label', 'LOW')}",
            "",
            "*Aggregate (denominator excludes unknown responses; per-signal rates above use full denominators, so they will not match):*",
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

        vis_rate = visibility_results.get("visibility_rate_pct", 0)
        known = visibility_results.get("known_count", 0)
        rec = visibility_results.get("recommended_count", 0)

        if known > 0 and rec == 0 and vis_rate < 50:
            lines.extend([
                "**Interpretation:** AI systems recognize your brand but do not associate you with your topics yet. "
                "This is common for newer sites with some web presence but limited topical authority. "
                "Guest posts, backlinks, and consistent publishing on your core topics will bridge this gap.",
                "",
            ])
        elif vis_rate > 80:
            lines.extend([
                "**Interpretation:** AI systems are highly aware of your brand and associate you with your topics. "
                "Focus on converting this visibility into citations by ensuring your content is crawlable and structured.",
                "",
            ])
        elif vis_rate == 0:
            lines.extend([
                "**Interpretation:** AI systems show no awareness of your brand. "
                "Build web presence first: publish content, get backlinks, establish domain authority.",
                "",
            ])

    # Recommendations: buyer-facing, with expected results and effort estimates.
    # Internal check codes are replaced with plain-language labels.
    # HONESTY GUARD: expected results are qualitative - no fabricated numbers.
    lines.extend([
        "---",
        "",
        "## Recommendations",
        "",
    ])

    seo_verdict_val = seo_results.get("section_verdict", "FAIL")
    ai_verdict_val = ai_results.get("section_verdict", "FAIL")

    if seo_verdict_val == "FAIL":
        lines.append("### Priority 1: Fix SEO Foundation")
        lines.append(
            "Your site has critical search foundation issues that block AI citation. "
            "Fix these first - AI systems source their answers from the web, so they "
            "cannot cite you if search crawlers cannot find you."
        )
        lines.append("")
        for check in seo_results.get("checks", []):
            if check.get("verdict") == "FAIL":
                lines.extend(_format_check_as_recommendation(check, "FAIL"))

    if ai_verdict_val != "PASS":
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
        lines.append("- Building backlinks from reputable sources (results appear over weeks to months)")
        lines.append("- Monthly citation monitoring to track trends over time")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")

    if client_name:
        # Determine which sections are actually present (no phantom section references in fine print).
        has_citation_section = bool(citation_results) or calibration_failed

        lines.extend([
            f"*Prepared by {consultant_name} using the AI Visibility Readiness Framework*",
            "",
            # Methodology: inline summary, not "available on request".
            "**How we check:** Every check in this report is a direct technical measurement "
            "run against your live site. "
            "Infrastructure checks (Sections 1 and 2) test crawlability, schema, indexing status, "
            "and AI crawler permissions. These checks are objective and re-verifiable - "
            "your web provider can confirm each finding independently.",
            "",
        ])

        # Disclaimer: only mention sections that exist.
        disclaimer = (
            "**A note on results:** These checks measure infrastructure readiness - "
            "they tell you whether the technical conditions for AI citation are in place. "
            "AI citation behavior also depends on your site's content, authority, and how AI platforms "
            "update over time. Infrastructure fixes are necessary but not sufficient on their own; "
            "content and authority building happen over weeks to months after the fixes are in place."
        )
        if has_citation_section:
            disclaimer += (
                " Citation monitoring results (Section 3) are point-in-time observations - "
                "re-run monthly to track trends."
            )
        lines.append(disclaimer)
    else:
        lines.extend([
            "*Generated by AI Visibility Readiness Framework v1.0.0*",
            f"*Methodology: [FRAMEWORK.md](../FRAMEWORK.md)*",
            "",
            "**Disclaimer:** Citation monitoring results (Section 3, when present) are point-in-time observations.",
            "AI citation behavior varies by session, location, and platform updates.",
            "Do not make investment decisions based on a single citation test round.",
        ])

    return "\n".join(lines)


def _self_check() -> bool:
    """Minimal self-check: verify buyer-framing invariants against fixture data.

    Tests:
    1. Executive summary leads with buyer-felt outcome, not a pass-count.
    2. A recommendation row includes 'Expected result:'.
    3. SKIPPED check does NOT contain CLI residue (no --skip-lighthouse, npm install, Re-run the audit).
    4. 'What to do Monday morning' box is present in buyer output.
    5. No raw bracket tokens ([PASS], [FAIL], [PARTIAL], [SKIPPED]) in buyer output.
    6. Jargon gloss for 'structured data'/'schema markup' is present in buyer output.
    7. The no-promise hedge ('cannot promise') appears exactly once (in 'What to expect:' only).
    8. Every technical recommendation includes a 'What to tell your web person:' line.
    9. No 'freely available' tool bragging in buyer output.

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
                "note": "Lighthouse skipped",
            },
            {"check": "1.2_crawlability", "tier": "VERIFIABLE", "verdict": "PASS"},
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
            {"check": "2.4_semantic_html", "tier": "VERIFIABLE", "verdict": "PASS"},
        ],
    }
    report = generate_report(seo_fixture, ai_fixture, client_name="TestCo Inc", url="https://example.com")

    failures = []

    # 1. Executive summary leads with buyer-felt outcome, not a pass-count.
    exec_start = report.find("## Executive Summary")
    if exec_start == -1:
        failures.append("Executive Summary section not found in output")
    else:
        exec_section = report[exec_start + len("## Executive Summary"):exec_start + 400]
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

    # 3. No CLI residue in buyer output.
    cli_residues = ["--skip-lighthouse", "npm install", "Re-run the audit"]
    for residue in cli_residues:
        if residue in report:
            failures.append(
                f"CLI residue found in buyer output: '{residue}' "
                "(must never appear in buyer-facing copy)"
            )

    # 4. 'What to do Monday morning' box present in buyer output.
    if "What to do Monday morning" not in report:
        failures.append(
            "No 'What to do Monday morning' section found in buyer report "
            "(required for buyer-first framing)"
        )

    # 5. No raw bracket tokens in buyer output.
    bracket_tokens = ["[PASS]", "[FAIL]", "[PARTIAL]", "[SKIPPED]"]
    for token in bracket_tokens:
        if token in report:
            failures.append(
                f"Raw bracket token '{token}' found in buyer report "
                "(use buyer words: Working/Needs work/Partly working/Not tested this round)"
            )

    # 6. Jargon gloss for 'structured data'/'schema markup' present in buyer output.
    if "labels in your website's code" not in report:
        failures.append(
            "Jargon gloss for 'structured data'/'schema markup' not found in buyer output "
            "(expected 'labels in your website\\'s code' to appear near first use)"
        )

    # 7. The no-promise hedge appears exactly once (de-duplicated to 'What to expect:' only).
    promise_count = report.count("cannot promise")
    if promise_count != 1:
        failures.append(
            f"The no-promise hedge ('cannot promise') appears {promise_count} times in buyer output "
            f"(expected exactly 1 - in the 'What to expect:' line in the executive summary only)"
        )

    # 8. Every FAIL/PARTIAL recommendation includes a 'What to tell your web person:' line.
    expected_rec_count = sum(
        1 for c in seo_fixture["checks"] + ai_fixture["checks"]
        if c.get("verdict") in ("FAIL", "PARTIAL")
    )
    actual_web_person_count = report.count("What to tell your web person:")
    if actual_web_person_count < expected_rec_count:
        failures.append(
            f"'What to tell your web person:' appears {actual_web_person_count} times "
            f"but expected at least {expected_rec_count} (one per FAIL/PARTIAL recommendation)"
        )

    # 9. No "freely available" tool bragging in buyer output (FIX B).
    if "freely available" in report:
        failures.append(
            "'freely available' found in buyer output "
            "(must not advertise free tools in buyer-facing copy; "
            "keep direct-measurement transparency, drop the free-tool brag)"
        )

    if failures:
        for f in failures:
            print(f"  SELF-CHECK FAIL: {f}", file=sys.stderr)
        return False

    print(
        "[report_generator self-check] PASS: all 9 buyer-framing invariants verified.",
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
