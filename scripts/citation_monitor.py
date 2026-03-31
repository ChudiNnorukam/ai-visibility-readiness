# Copyright (c) 2026 Chudi Nnorukam. All rights reserved.
# Licensed under the AVR Source-Available License v1.0. See LICENSE file.
# https://citability.dev

#!/usr/bin/env python3
"""
AVR Section 3: Citation Monitoring
Generates query checklists, records manual citation test results, computes citation rates.
"""

import json
import math
import sys
from datetime import datetime, timezone


def generate_query_checklist(domain: str, topics: list[str] | None = None) -> dict:
    """Generate a 20-query citation test checklist.

    Args:
        domain: The website domain (e.g., "chudi.dev")
        topics: Optional list of topics the site covers. If not provided,
                generates brand-only queries.
    """
    queries = []

    # 5 brand queries
    brand = domain.replace(".dev", "").replace(".com", "").replace(".io", "")
    queries.extend([
        {"id": 1, "category": "brand", "query": f"what is {domain}", "rationale": "Direct brand recognition"},
        {"id": 2, "category": "brand", "query": f"{brand} blog", "rationale": "Brand + content discovery"},
        {"id": 3, "category": "brand", "query": f"who is {brand}", "rationale": "Personal brand recognition"},
        {"id": 4, "category": "brand", "query": f"{domain} reviews", "rationale": "Social proof / reputation"},
        {"id": 5, "category": "brand", "query": f"{brand} developer", "rationale": "Professional identity"},
    ])

    if topics:
        # 5 topic authority queries
        for i, topic in enumerate(topics[:5]):
            queries.append({
                "id": 6 + i,
                "category": "topic_authority",
                "query": f"how to {topic}",
                "rationale": f"Topic authority for: {topic}",
            })

        # 5 long-tail queries
        for i, topic in enumerate(topics[:5]):
            queries.append({
                "id": 11 + i,
                "category": "long_tail",
                "query": f"best way to {topic} in 2026",
                "rationale": f"Long-tail variant for: {topic}",
            })

        # 5 competitor-adjacent queries
        for i, topic in enumerate(topics[:5]):
            queries.append({
                "id": 16 + i,
                "category": "competitor_adjacent",
                "query": f"{topic} tutorial guide",
                "rationale": f"Competitive query for: {topic}",
            })
    else:
        # Generic placeholder queries when no topics provided
        for i in range(15):
            queries.append({
                "id": 6 + i,
                "category": "placeholder",
                "query": f"[REPLACE with topic query #{i + 1}]",
                "rationale": "Provide topics to generate specific queries",
            })

    checklist = {
        "domain": domain,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_queries": len(queries),
        "platforms": ["ChatGPT", "Perplexity", "Google_AIO"],
        "total_possible_citations": len(queries) * 3,
        "queries": queries,
        "instructions": {
            "step_1": "For each query, search on all 3 platforms",
            "step_2": "Record whether your domain appears in the response",
            "step_3": "Use statuses: CITED (link/mention), NOT_CITED, NO_AIO (for Google when no AI Overview appears)",
            "step_4": "Run this test monthly for trend tracking",
        },
    }

    return checklist


def compute_citation_rate(results: list[dict]) -> dict:
    """Compute citation rate and confidence from test results.

    Args:
        results: List of dicts with keys: query_id, platform, status
                 status is one of: CITED, NOT_CITED, NO_AIO
    """
    total = len(results)
    cited = sum(1 for r in results if r.get("status") == "CITED")
    not_cited = sum(1 for r in results if r.get("status") == "NOT_CITED")
    no_aio = sum(1 for r in results if r.get("status") == "NO_AIO")
    testable = total - no_aio

    rate = cited / testable if testable > 0 else 0

    # Confidence interval (Wilson score interval)
    if testable > 0:
        z = 1.96  # 95% confidence
        p = rate
        n = testable
        denominator = 1 + z**2 / n
        center = (p + z**2 / (2 * n)) / denominator
        spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denominator
        ci_low = max(0, center - spread)
        ci_high = min(1, center + spread)
    else:
        ci_low = 0
        ci_high = 0

    # Confidence label
    if testable >= 600:
        confidence = "HIGH"
    elif testable >= 180:
        confidence = "MODERATE"
    else:
        confidence = "LOW"

    # Per-platform breakdown
    platforms = {}
    for r in results:
        p = r.get("platform", "unknown")
        if p not in platforms:
            platforms[p] = {"cited": 0, "not_cited": 0, "no_aio": 0, "total": 0}
        platforms[p]["total"] += 1
        if r["status"] == "CITED":
            platforms[p]["cited"] += 1
        elif r["status"] == "NOT_CITED":
            platforms[p]["not_cited"] += 1
        elif r["status"] == "NO_AIO":
            platforms[p]["no_aio"] += 1

    for p_data in platforms.values():
        testable_p = p_data["total"] - p_data["no_aio"]
        p_data["citation_rate_pct"] = round(p_data["cited"] / testable_p * 100, 1) if testable_p > 0 else 0

    # Verdict
    if rate > 0.15:
        verdict = "CITED"
    elif rate > 0.01:
        verdict = "PARTIALLY_CITED"
    else:
        verdict = "NOT_CITED"

    return {
        "total_tests": total,
        "testable": testable,
        "cited_count": cited,
        "citation_rate_pct": round(rate * 100, 1),
        "confidence_interval_95": {
            "low_pct": round(ci_low * 100, 1),
            "high_pct": round(ci_high * 100, 1),
        },
        "confidence_label": confidence,
        "by_platform": platforms,
        "verdict": verdict,
    }


def create_recording_template(checklist: dict) -> str:
    """Generate a markdown template for recording citation test results."""
    lines = [
        f"# Citation Test Results: {checklist['domain']}",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        f"**Tester:** [your name]",
        "",
        "## Instructions",
        "For each query below, test on ChatGPT (web browsing), Perplexity, and Google.",
        "Record: CITED (link or mention), NOT_CITED, NO_AIO (Google only, when no AI Overview appears)",
        "",
        "## Results",
        "",
        "| # | Category | Query | ChatGPT | Perplexity | Google AIO | Notes |",
        "|---|----------|-------|---------|------------|------------|-------|",
    ]

    for q in checklist["queries"]:
        lines.append(
            f"| {q['id']} | {q['category']} | {q['query']} | | | | |"
        )

    lines.extend([
        "",
        "## Summary (auto-computed after filling in results)",
        "- Total citations: ___ / ___",
        "- Citation rate: ___%",
        "- Confidence: LOW (single test round)",
        "",
    ])

    return "\n".join(lines)


def parse_results_json(results_file: str) -> dict:
    """Load results from a JSON file and compute citation rate."""
    with open(results_file) as f:
        results = json.load(f)
    return compute_citation_rate(results)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python citation_monitor.py checklist <domain> [topic1] [topic2] ...")
        print("  python citation_monitor.py template <domain> [topic1] [topic2] ...")
        print("  python citation_monitor.py compute <results.json>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "checklist":
        domain = sys.argv[2] if len(sys.argv) > 2 else "example.com"
        topics = sys.argv[3:] if len(sys.argv) > 3 else None
        checklist = generate_query_checklist(domain, topics)
        print(json.dumps(checklist, indent=2))

    elif command == "template":
        domain = sys.argv[2] if len(sys.argv) > 2 else "example.com"
        topics = sys.argv[3:] if len(sys.argv) > 3 else None
        checklist = generate_query_checklist(domain, topics)
        print(create_recording_template(checklist))

    elif command == "compute":
        results_file = sys.argv[2]
        rate = parse_results_json(results_file)
        print(json.dumps(rate, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
