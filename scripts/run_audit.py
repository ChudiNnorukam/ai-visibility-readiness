#!/usr/bin/env python3
"""
AVR Main Entry Point
Runs all automated checks and generates the final audit report.
Optionally runs live AI citation + visibility tests with --live-test.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from seo_foundation import run_seo_foundation
from ai_readiness import run_ai_readiness
from citation_monitor import generate_query_checklist
from report_generator import generate_report
from section_webmcp_agent_readiness import run_section_webmcp_agent_readiness
from section_fact_block_density import run_section_fact_block_density
from section_citation_decay import run_section_citation_decay
from section_bot_response_code import run_section_bot_response_code
from section_markdown_negotiation import run_section_markdown_negotiation
from section_robots_ai_rules import run_section_robots_ai_rules
from section_agent_readiness_tier import run_section_agent_readiness_tier
from section_crawl_signal import run_section_crawl_signal
from section_content_intent_signaling import run_section_content_intent_signaling


def run_audit(
    url: str,
    output_dir: str = ".",
    skip_lighthouse: bool = False,
    topics: list[str] | None = None,
    client_name: str | None = None,
    consultant_name: str = "Chudi Nnorukam",
    live_test: bool = False,
    brand: str | None = None,
    owner: str | None = None,
    products: list[str] | None = None,
    concepts: list[str] | None = None,
    skip_calibration: bool = False,
    force_calibrate: bool = False,
    vertical: str | None = None,
    vertical_ctx: dict | None = None,
    full_v11: bool = False,
    allow_skip_on_client: bool = False,
) -> str:
    """Run the full AVR audit on a URL.

    Args:
        url: Target URL to audit
        output_dir: Directory to save results
        skip_lighthouse: Skip Lighthouse checks (faster, no CWV data)
        topics: Topics for citation and visibility testing
        client_name: Client name for consulting report header
        consultant_name: Consultant name for report header
        live_test: Run live AI citation + visibility tests (costs ~$2/audit)
        brand: Brand name for visibility testing
        owner: Owner/author name for visibility testing
        products: Product names for visibility testing
        concepts: Key concepts/terminology for visibility testing
        allow_skip_on_client: Override the ship-gate that blocks --skip-lighthouse on client runs

    Returns:
        Path to the generated report
    """
    # Ship-gate: a $497/client run must never ship with a SKIPPED Core Web Vitals check.
    # Lighthouse is free; there is no excuse to skip it on a paid deliverable.
    # The buyer-facing "completing this measurement" copy is a fallback for genuinely-impossible
    # cases (Lighthouse ran but was blocked by the site), not the default.
    if client_name and skip_lighthouse and not allow_skip_on_client:
        print(
            "ERROR: A $497/client audit must include Core Web Vitals; "
            "remove --skip-lighthouse, or pass --allow-skip-on-client to override.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not url.startswith("http"):
        url = f"https://{url}"

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    domain = url.replace("https://", "").replace("http://", "").split("/")[0]
    report_name = f"audit_{domain}_{timestamp}"

    os.makedirs(output_dir, exist_ok=True)

    step_count = 5 if live_test else 3
    print(f"\n{'='*60}")
    print(f"  AI Visibility Readiness Audit")
    print(f"  URL: {url}")
    if live_test:
        print(f"  Mode: FULL (infrastructure + live AI testing)")
    print(f"  Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    # Section 1: SEO Foundation
    print(f"[1/{step_count}] Running SEO Foundation checks...")
    if skip_lighthouse:
        print("  (Lighthouse skipped)")
    seo_results = run_seo_foundation(url, skip_lighthouse=skip_lighthouse)
    print(f"  Section verdict: {seo_results['section_verdict']}")

    seo_path = os.path.join(output_dir, f"{report_name}_seo.json")
    with open(seo_path, "w") as f:
        json.dump(seo_results, f, indent=2)
    print(f"  Saved: {seo_path}")

    # Section 2: AI Infrastructure Readiness
    print(f"\n[2/{step_count}] Running AI Infrastructure Readiness checks...")
    ai_results = run_ai_readiness(url, vertical=vertical)
    print(f"  Section verdict: {ai_results['section_verdict']}")

    ai_path = os.path.join(output_dir, f"{report_name}_ai.json")
    with open(ai_path, "w") as f:
        json.dump(ai_results, f, indent=2)
    print(f"  Saved: {ai_path}")

    # Section 3: Citation + Visibility (live or checklist)
    citation_results = None
    visibility_results = None

    calibration_receipt = None
    calibration_passed = True  # default true for non-live runs

    if live_test:
        from citation_auto import run_citation_test
        from visibility_auto import run_visibility_test

        # Pre-flight calibration smoke test (per 2026-04-30 plan stream C).
        # Cached 24h; --force-calibrate to bypass; --skip-calibration to skip.
        if not skip_calibration:
            from calibration import run_calibration, format_receipt_console
            print(f"\n[calibration] Running pre-flight smoke test...")
            calibration_receipt = run_calibration(force=force_calibrate)
            print(format_receipt_console(calibration_receipt))
            calibration_passed = calibration_receipt["overall_pass"]
            if not calibration_passed:
                print(f"\n  Calibration FAILED — site-level AI numbers will be withheld from")
                print(f"  Sections 3+4. Sections 1+2 (HTTP/HTML checks) will still be written.")
                print(f"  Re-run after resolving, or pass --skip-calibration to override.")
        else:
            print(f"\n[calibration] SKIPPED via --skip-calibration flag")

        # Section 3: Live Citation Test (only if calibration passed OR skipped)
        if calibration_passed:
            print(f"\n[3/{step_count}] Running live citation test...")
            citation_results = run_citation_test(
                url, topics, output_dir, brand=brand,
                vertical=vertical, vertical_ctx=vertical_ctx,
            )

            # Section 4: Live Visibility Test
            print(f"\n[4/{step_count}] Running live visibility test...")
            brand_name = brand or domain.split(".")[0].capitalize()
            visibility_results = run_visibility_test(
                url, brand_name, owner, topics, products, concepts, output_dir,
            )
        else:
            # Calibration failed and not skipped — withhold AI sections
            print(f"\n[3/{step_count}] Citation test SKIPPED (calibration failed)")
            print(f"[4/{step_count}] Visibility test SKIPPED (calibration failed)")

        print(f"\n[5/{step_count}] Generating audit report...")
    else:
        print(f"\n[3/{step_count}] Generating citation test checklist...")
        checklist = generate_query_checklist(domain, topics)
        checklist_path = os.path.join(output_dir, f"{report_name}_citation_checklist.json")
        with open(checklist_path, "w") as f:
            json.dump(checklist, f, indent=2)
        print(f"  Saved: {checklist_path}")
        print(f"  For live testing, re-run with: --live-test --brand \"{domain.split('.')[0]}\"")

    # Generate report
    report = generate_report(
        seo_results, ai_results,
        citation_results=citation_results,
        visibility_results=visibility_results,
        url=url,
        client_name=client_name,
        consultant_name=consultant_name,
        calibration_receipt=calibration_receipt,
    )

    # AVR v1.1.0 sections 6/7/8 — Agent Readiness + Fact-Block Density + Citation Decay Rate.
    # Free ($0); run on every --full-v11 audit regardless of --live-test status.
    webmcp_results = None
    factblock_results = None
    decay_results = None
    if full_v11:
        try:
            print(f"\n[v1.1.0/6] Running Agent Readiness audit (WebMCP + AgentCard)...")
            webmcp_results = run_section_webmcp_agent_readiness(url)
            webmcp_path = os.path.join(output_dir, f"{report_name}_webmcp.json")
            with open(webmcp_path, "w") as f:
                json.dump(webmcp_results, f, indent=2)
            print(f"  Section verdict: {webmcp_results.get('section_verdict', 'N/A')}")
            print(f"  Saved: {webmcp_path}")
        except Exception as e:
            print(f"  WARN: agent-readiness section failed: {type(e).__name__}: {e}")

        try:
            print(f"\n[v1.1.0/7] Running Fact-Block Density audit...")
            factblock_results = run_section_fact_block_density(url)
            fb_path = os.path.join(output_dir, f"{report_name}_factblock.json")
            with open(fb_path, "w") as f:
                json.dump(factblock_results, f, indent=2)
            print(f"  Section verdict: {factblock_results.get('section_verdict', 'N/A')} (score: {factblock_results.get('extractability_score', 0)}/100)")
            print(f"  Saved: {fb_path}")
        except Exception as e:
            print(f"  WARN: fact-block-density section failed: {type(e).__name__}: {e}")

        try:
            print(f"\n[v1.1.0/8] Running Citation Decay Rate audit (Bing CSV)...")
            decay_results = run_section_citation_decay()
            cd_path = os.path.join(output_dir, f"{report_name}_decay.json")
            with open(cd_path, "w") as f:
                json.dump(decay_results, f, indent=2)
            print(f"  Section verdict: {decay_results.get('section_verdict', 'N/A')} (confidence: {decay_results.get('confidence', 'N/A')})")
            print(f"  Saved: {cd_path}")
        except Exception as e:
            print(f"  WARN: citation-decay section failed: {type(e).__name__}: {e}")

        # AVR v1.1.0 sections 9-13: Cloudflare Radar-derived checks (May 2026).
        # All free ($0); HTTP GET probes only.
        try:
            print(f"\n[v1.1.0/9] Running Bot Response Code audit...")
            bot_resp_results = run_section_bot_response_code(url)
            br_path = os.path.join(output_dir, f"{report_name}_botresponse.json")
            with open(br_path, "w") as f:
                json.dump(bot_resp_results, f, indent=2)
            print(f"  Section verdict: {bot_resp_results.get('section_verdict', 'N/A')} ({bot_resp_results.get('pass_count', 0)}/{bot_resp_results.get('total_checks', 0)} bots get 200)")
            print(f"  Saved: {br_path}")
        except Exception as e:
            print(f"  WARN: bot-response-code section failed: {type(e).__name__}: {e}")

        try:
            print(f"\n[v1.1.0/10] Running Markdown Negotiation audit...")
            md_results = run_section_markdown_negotiation(url)
            md_path = os.path.join(output_dir, f"{report_name}_markdown.json")
            with open(md_path, "w") as f:
                json.dump(md_results, f, indent=2)
            print(f"  Section verdict: {md_results.get('section_verdict', 'N/A')}")
            print(f"  Saved: {md_path}")
        except Exception as e:
            print(f"  WARN: markdown-negotiation section failed: {type(e).__name__}: {e}")

        try:
            print(f"\n[v1.1.0/11] Running AI Rules in robots.txt audit...")
            robots_results = run_section_robots_ai_rules(url)
            rob_path = os.path.join(output_dir, f"{report_name}_robotsai.json")
            with open(rob_path, "w") as f:
                json.dump(robots_results, f, indent=2)
            print(f"  Section verdict: {robots_results.get('section_verdict', 'N/A')} ({robots_results.get('pass_count', 0)}/{robots_results.get('total_checks', 0)} checks pass)")
            print(f"  Saved: {rob_path}")
        except Exception as e:
            print(f"  WARN: robots-ai-rules section failed: {type(e).__name__}: {e}")

        try:
            print(f"\n[v1.1.0/12] Running Agent Readiness Tier audit...")
            tier_results = run_section_agent_readiness_tier(url)
            tier_path = os.path.join(output_dir, f"{report_name}_agenttier.json")
            with open(tier_path, "w") as f:
                json.dump(tier_results, f, indent=2)
            print(f"  Section verdict: {tier_results.get('section_verdict', 'N/A')} (score: {tier_results.get('agent_tier_score', 0)}/4)")
            print(f"  Saved: {tier_path}")
        except Exception as e:
            print(f"  WARN: agent-readiness-tier section failed: {type(e).__name__}: {e}")

        try:
            print(f"\n[v1.1.0/13] Running Crawl Signal check...")
            crawl_results = run_section_crawl_signal(url)
            crawl_path = os.path.join(output_dir, f"{report_name}_crawlsignal.json")
            with open(crawl_path, "w") as f:
                json.dump(crawl_results, f, indent=2)
            print(f"  Section verdict: {crawl_results.get('section_verdict', 'N/A')} ({crawl_results.get('pass_count', 0)}/{crawl_results.get('total_checks', 0)} checks pass)")
            print(f"  Saved: {crawl_path}")
        except Exception as e:
            print(f"  WARN: crawl-signal section failed: {type(e).__name__}: {e}")

        # AVR v1.2.0 section 14: Content Intent Signaling (ai-train/search/ai-input).
        try:
            print(f"\n[v1.2.0/14] Running Content Intent Signaling audit...")
            intent_results = run_section_content_intent_signaling(url)
            intent_path = os.path.join(output_dir, f"{report_name}_contentintent.json")
            with open(intent_path, "w") as f:
                json.dump(intent_results, f, indent=2)
            print(f"  Section verdict: {intent_results.get('section_verdict', 'N/A')} ({intent_results.get('pass_count', 0)}/{intent_results.get('total_checks', 0)} checks pass)")
            print(f"  Saved: {intent_path}")
        except Exception as e:
            print(f"  WARN: content-intent-signaling section failed: {type(e).__name__}: {e}")

    report_path = os.path.join(output_dir, f"{report_name}.md")
    with open(report_path, "w") as f:
        f.write(report)
    print(f"  Saved: {report_path}")

    # Summary
    from report_generator import determine_overall_status
    overall = determine_overall_status(
        seo_results.get("section_verdict", "FAIL"),
        ai_results.get("section_verdict", "FAIL"),
    )

    print(f"\n{'='*60}")
    print(f"  OVERALL STATUS: {overall}")
    print(f"  SEO Foundation:    {seo_results['section_verdict']}")
    print(f"  AI Infrastructure: {ai_results['section_verdict']}")
    if citation_results:
        print(f"  Citations:         {citation_results.get('verdict', 'N/A')} ({citation_results.get('citation_rate_pct', 0)}%)")
    if visibility_results:
        # Per-category headlines — the aggregate "visibility_rate_pct" averages
        # incompatible signals (brand-recognition + topic-association + active-recommendation)
        # across a query-set biased toward tools/resources, which produces misleading numbers
        # for reference-shaped sites. Show the load-bearing per-category numbers instead.
        by_cat = visibility_results.get("by_category", {}) or {}
        labels = {
            "brand_recognition": "Brand recognition",
            "concept_attribution": "Topic association",
            "recommendation": "Active recommendation",
        }
        print(f"  AI Visibility:     {visibility_results.get('verdict', 'N/A')}")
        for cat in ("brand_recognition", "concept_attribution", "recommendation"):
            if cat in by_cat:
                cd = by_cat[cat]
                print(f"    - {labels.get(cat, cat):24} {cd['visible']}/{cd['total']} = {cd['rate_pct']}%")
    if not live_test:
        print(f"  Citations:         (add --live-test for automated testing)")
        print(f"  AI Visibility:     (add --live-test for automated testing)")
    print(f"{'='*60}")
    print(f"\nFull report: {report_path}")

    # Exit 2 if calibration failed and operator did not opt out — signals
    # to CI/automation that the AI sections are missing.
    if live_test and not skip_calibration and not calibration_passed:
        import sys
        print(f"\nWARNING: calibration failed; AI sections withheld. Exiting 2.")
        sys.exit(2)

    return report_path


def main():
    parser = argparse.ArgumentParser(
        description="AI Visibility Readiness (AVR) Audit",
        epilog="""
Examples:
  # Quick infrastructure audit (free, no API calls)
  python run_audit.py example.com --skip-lighthouse

  # Full audit with live AI testing (~$2)
  python run_audit.py example.com --live-test --brand "MyBrand" --owner "Jane Doe" \\
    --topics "web dev" "React" --concepts "my unique framework"

  # Consulting report
  python run_audit.py client.com --live-test --brand "ClientCo" \\
    --client "ClientCo Inc" --topics "their niche"

Output (infrastructure only):
  audit_<domain>_<timestamp>.md               - Full report
  audit_<domain>_<timestamp>_seo.json         - SEO check data
  audit_<domain>_<timestamp>_ai.json          - AI readiness data

Output (with --live-test, adds):
  citations_<domain>_<timestamp>_summary.json  - Citation test results
  citations_<domain>_<timestamp>_raw.json      - Raw citation data
  visibility_<domain>_<timestamp>_summary.json - Visibility test results
  visibility_<domain>_<timestamp>_raw.json     - Raw visibility data

Verdicts:
  AI-READY             SEO + AI infrastructure both pass
  FOUNDATION-READY     SEO passes, AI infrastructure needs work
  INFRASTRUCTURE-READY AI infra passes, SEO is broken
  NOT-READY            SEO foundation fails

Live Test Verdicts:
  Citation:   NOT_CITED / PARTIALLY_CITED / CITED
  Visibility: INVISIBLE / BARELY_VISIBLE / PARTIALLY_VISIBLE / HIGHLY_VISIBLE

Cost: Infrastructure audit is free. Live testing costs ~$2 per audit.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="URL to audit (https:// prefix optional)")
    parser.add_argument("-o", "--output", default=".", help="Output directory (default: current dir)")
    parser.add_argument("--skip-lighthouse", action="store_true", help="Skip Lighthouse checks (10x faster)")
    parser.add_argument("--topics", nargs="*", help="Topics the site covers")
    parser.add_argument("--client", help="Client name for consulting report header")
    parser.add_argument("--consultant", default="Chudi Nnorukam", help="Consultant name (default: Chudi Nnorukam)")

    # Live test options
    live = parser.add_argument_group("live AI testing (--live-test)")
    live.add_argument("--live-test", action="store_true", help="Run live citation + visibility tests (~$2/audit)")
    live.add_argument("--brand", help="Brand name for visibility testing")
    live.add_argument("--owner", help="Owner/author name for visibility testing")
    live.add_argument("--products", nargs="*", help="Product names to check")
    live.add_argument("--concepts", nargs="*", help="Unique concepts/terminology from the brand")
    live.add_argument("--force-calibrate", action="store_true",
                      help="Bypass 24h calibration cache, run fresh smoke test")
    live.add_argument("--skip-calibration", action="store_true",
                      help="Skip calibration entirely (operator accepts the risk of un-validated numbers)")

    # Consulting / client run overrides
    client_grp = parser.add_argument_group("consulting run overrides")
    client_grp.add_argument(
        "--allow-skip-on-client",
        action="store_true",
        help=(
            "Override the ship-gate that requires Lighthouse for client/consulting runs. "
            "Use only when Lighthouse is genuinely impossible (auth-walled, blocks probes). "
            "Without this flag, --client + --skip-lighthouse is refused."
        ),
    )

    # AVR v1.1.0 sections (all free, $0 API spend)
    v11 = parser.add_argument_group("AVR v1.1.0 sections (free)")
    v11.add_argument("--full-v11", action="store_true",
                     help="Run AVR v1.1.0 sections 6/7/8: Agent Readiness (WebMCP+AgentCard) + Fact-Block Density + Citation Decay Rate. $0 cost.")

    # Vertical profile options (per verticals.py)
    vert = parser.add_argument_group("vertical profile (per verticals.py)")
    vert.add_argument("--vertical", choices=["local-healthcare", "saas-tool", "personal-brand", "tech-publisher"],
                      help="Vertical profile: biases citation queries, schema-type expectations, and indirect-citation sources")
    # Local-healthcare context
    vert.add_argument("--city", help="City (local-healthcare vertical)")
    vert.add_argument("--neighborhood", help="Neighborhood (local-healthcare vertical, falls back to --city)")
    vert.add_argument("--services", nargs="*", help="Services offered, e.g. braces Invisalign clear-aligners")
    vert.add_argument("--patient-segments", nargs="*", help="Patient segments, e.g. kids teens adults (local-healthcare)")
    vert.add_argument("--practice-type", help="Practice type, e.g. orthodontist dentist physical-therapist")
    # SaaS context
    vert.add_argument("--category", help="Product category (saas-tool vertical)")
    vert.add_argument("--use-cases", nargs="*", help="Use cases (saas-tool vertical)")
    # Personal-brand context
    vert.add_argument("--expertise", nargs="*", help="Areas of expertise (personal-brand vertical)")

    args = parser.parse_args()

    # Build vertical_ctx from CLI args (only the keys this vertical's builder reads)
    vertical_ctx = {}
    if args.vertical:
        if args.brand:
            vertical_ctx["brand"] = args.brand
        if args.city:
            vertical_ctx["city"] = args.city
        if args.neighborhood:
            vertical_ctx["neighborhood"] = args.neighborhood
        if args.services:
            vertical_ctx["services"] = args.services
        if args.patient_segments:
            vertical_ctx["patient_segments"] = args.patient_segments
        if args.practice_type:
            vertical_ctx["practice_type"] = args.practice_type
        if args.category:
            vertical_ctx["category"] = args.category
        if args.use_cases:
            vertical_ctx["use_cases"] = args.use_cases
        if args.expertise:
            vertical_ctx["expertise"] = args.expertise

    run_audit(
        args.url,
        args.output,
        args.skip_lighthouse,
        args.topics,
        client_name=args.client,
        consultant_name=args.consultant,
        live_test=args.live_test,
        brand=args.brand,
        owner=args.owner,
        products=args.products,
        concepts=args.concepts,
        skip_calibration=args.skip_calibration,
        force_calibrate=args.force_calibrate,
        vertical=args.vertical,
        vertical_ctx=vertical_ctx or None,
        full_v11=args.full_v11,
        allow_skip_on_client=args.allow_skip_on_client,
    )


if __name__ == "__main__":
    main()
