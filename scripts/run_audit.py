# Copyright (c) 2026 Chudi Nnorukam. All rights reserved.
# Licensed under the AVR Source-Available License v1.0. See LICENSE file.
# https://citability.dev

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

    Returns:
        Path to the generated report
    """
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
    ai_results = run_ai_readiness(url)
    print(f"  Section verdict: {ai_results['section_verdict']}")

    ai_path = os.path.join(output_dir, f"{report_name}_ai.json")
    with open(ai_path, "w") as f:
        json.dump(ai_results, f, indent=2)
    print(f"  Saved: {ai_path}")

    # Section 3: Citation + Visibility (live or checklist)
    citation_results = None
    visibility_results = None

    if live_test:
        from citation_auto import run_citation_test
        from visibility_auto import run_visibility_test

        # Section 3: Live Citation Test
        print(f"\n[3/{step_count}] Running live citation test...")
        citation_results = run_citation_test(url, topics, output_dir)

        # Section 4: Live Visibility Test
        print(f"\n[4/{step_count}] Running live visibility test...")
        brand_name = brand or domain.split(".")[0].capitalize()
        visibility_results = run_visibility_test(
            url, brand_name, owner, topics, products, concepts, output_dir,
        )

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
    )

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
        print(f"  AI Visibility:     {visibility_results.get('verdict', 'N/A')} ({visibility_results.get('visibility_rate_pct', 0)}%)")
    if not live_test:
        print(f"  Citations:         (add --live-test for automated testing)")
        print(f"  AI Visibility:     (add --live-test for automated testing)")
    print(f"{'='*60}")
    print(f"\nFull report: {report_path}")

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

    args = parser.parse_args()

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
    )


if __name__ == "__main__":
    main()
