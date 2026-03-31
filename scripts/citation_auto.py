# Copyright (c) 2026 Chudi Nnorukam. All rights reserved.
# Licensed under the AVR Source-Available License v1.0. See LICENSE file.
# https://citability.dev

#!/usr/bin/env python3
"""
AVR Automated Citation Testing

Queries AI search platforms (OpenAI, Perplexity, Anthropic) with real search
queries and checks whether a target domain appears in their cited sources.

This replaces the manual Section 3 process. Results are still labeled
[BEST-EFFORT] because AI responses vary by session, but the data is real
citation data, not speculation.

Setup:
  1. Copy .env.example to .env and add your API keys
  2. pip install openai anthropic requests
  3. python citation_auto.py test https://chudi.dev --topics "Claude Code hooks" "AI visibility"

Cost per audit (~60 queries):
  OpenAI (gpt-4o-mini + web search): ~$0.60
  Perplexity (sonar):                ~$0.30
  Anthropic (haiku + web search):    ~$0.30
  Total:                             ~$1.20
"""

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            if value and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip()


def _check_keys() -> dict:
    """Check which API keys are available."""
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


def query_openai(query: str, target_domain: str) -> dict:
    """Query OpenAI with web search and check for target domain citations.

    Uses the Responses API with web_search tool.
    Returns: {platform, query, status, cited_urls, response_snippet}
    """
    try:
        from openai import OpenAI
        client = OpenAI()

        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search_preview"}],
            input=query,
        )

        # Extract cited URLs from the response
        cited_urls = []
        response_text = ""

        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        response_text = content.text
                        # Extract URLs from annotations
                        if hasattr(content, "annotations"):
                            for ann in content.annotations:
                                if hasattr(ann, "url"):
                                    cited_urls.append(ann.url)

        # Check if target domain appears in citations
        domain_clean = target_domain.replace("https://", "").replace("http://", "").rstrip("/")
        cited = any(domain_clean in url for url in cited_urls)

        return {
            "platform": "ChatGPT",
            "query": query,
            "status": "CITED" if cited else "NOT_CITED",
            "cited_urls": cited_urls[:10],
            "response_snippet": response_text[:200],
        }

    except Exception as e:
        return {
            "platform": "ChatGPT",
            "query": query,
            "status": "ERROR",
            "error": str(e),
        }


def query_perplexity(query: str, target_domain: str) -> dict:
    """Query Perplexity search API and check for target domain citations.

    Uses the sonar model which includes web search with citations.
    Returns: {platform, query, status, cited_urls, response_snippet}
    """
    try:
        import requests as req

        api_key = os.environ.get("PERPLEXITY_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "sonar",
            "messages": [
                {"role": "user", "content": query}
            ],
        }

        resp = req.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract citations from response
        cited_urls = data.get("citations", [])
        response_text = ""
        if data.get("choices"):
            response_text = data["choices"][0].get("message", {}).get("content", "")

        domain_clean = target_domain.replace("https://", "").replace("http://", "").rstrip("/")
        cited = any(domain_clean in url for url in cited_urls)

        return {
            "platform": "Perplexity",
            "query": query,
            "status": "CITED" if cited else "NOT_CITED",
            "cited_urls": cited_urls[:10],
            "response_snippet": response_text[:200],
        }

    except Exception as e:
        return {
            "platform": "Perplexity",
            "query": query,
            "status": "ERROR",
            "error": str(e),
        }


def query_anthropic(query: str, target_domain: str) -> dict:
    """Query Anthropic Claude with web search and check for target domain citations.

    Uses the Messages API with web_search tool.
    Returns: {platform, query, status, cited_urls, response_snippet}
    """
    try:
        from anthropic import Anthropic
        client = Anthropic()

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": query}],
        )

        # Extract cited URLs from web search result blocks
        cited_urls = []
        response_text = ""

        for block in response.content:
            if block.type == "text":
                response_text += block.text
            elif block.type == "web_search_tool_result":
                for result in getattr(block, "content", []):
                    if hasattr(result, "url"):
                        cited_urls.append(result.url)

        domain_clean = target_domain.replace("https://", "").replace("http://", "").rstrip("/")
        cited = any(domain_clean in url for url in cited_urls)

        return {
            "platform": "Claude",
            "query": query,
            "status": "CITED" if cited else "NOT_CITED",
            "cited_urls": cited_urls[:10],
            "response_snippet": response_text[:200],
        }

    except Exception as e:
        return {
            "platform": "Claude",
            "query": query,
            "status": "ERROR",
            "error": str(e),
        }


PLATFORM_FUNCTIONS = {
    "openai": query_openai,
    "perplexity": query_perplexity,
    "anthropic": query_anthropic,
}

PLATFORM_NAMES = {
    "openai": "ChatGPT",
    "perplexity": "Perplexity",
    "anthropic": "Claude",
}


def generate_queries(domain: str, topics: list[str] | None = None) -> list[dict]:
    """Generate 20 test queries for citation testing."""
    brand = domain.replace(".dev", "").replace(".com", "").replace(".io", "")
    queries = []

    # 5 brand queries
    queries.extend([
        {"id": 1, "category": "brand", "query": f"what is {domain}"},
        {"id": 2, "category": "brand", "query": f"who is {brand}"},
        {"id": 3, "category": "brand", "query": f"{domain} blog"},
        {"id": 4, "category": "brand", "query": f"{brand} developer tools"},
        {"id": 5, "category": "brand", "query": f"tell me about {domain}"},
    ])

    if topics:
        for i, topic in enumerate(topics[:5]):
            queries.append({"id": 6 + i, "category": "topic_authority", "query": f"how to {topic}"})
        for i, topic in enumerate(topics[:5]):
            queries.append({"id": 11 + i, "category": "long_tail", "query": f"best way to {topic} in 2026"})
        for i, topic in enumerate(topics[:5]):
            queries.append({"id": 16 + i, "category": "competitor", "query": f"{topic} tutorial guide"})
    else:
        for i in range(15):
            queries.append({"id": 6 + i, "category": "placeholder", "query": f"[topic query {i+1} - provide --topics]"})

    return queries


def compute_results(results: list[dict]) -> dict:
    """Compute citation rate and confidence from test results."""
    total = len(results)
    errors = sum(1 for r in results if r["status"] == "ERROR")
    testable = total - errors
    cited = sum(1 for r in results if r["status"] == "CITED")

    rate = cited / testable if testable > 0 else 0

    # Wilson score 95% CI
    if testable > 0:
        z = 1.96
        p = rate
        n = testable
        denom = 1 + z**2 / n
        center = (p + z**2 / (2 * n)) / denom
        spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
        ci_low = max(0, center - spread)
        ci_high = min(1, center + spread)
    else:
        ci_low = ci_high = 0

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
        p = r["platform"]
        if p not in platforms:
            platforms[p] = {"cited": 0, "not_cited": 0, "error": 0, "total": 0}
        platforms[p]["total"] += 1
        if r["status"] == "CITED":
            platforms[p]["cited"] += 1
        elif r["status"] == "NOT_CITED":
            platforms[p]["not_cited"] += 1
        elif r["status"] == "ERROR":
            platforms[p]["error"] += 1

    for pdata in platforms.values():
        testable_p = pdata["total"] - pdata["error"]
        pdata["citation_rate_pct"] = round(pdata["cited"] / testable_p * 100, 1) if testable_p > 0 else 0

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
        "errors": errors,
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


def run_citation_test(
    target_url: str,
    topics: list[str] | None = None,
    output_dir: str = ".",
    platforms: list[str] | None = None,
) -> dict:
    """Run automated citation testing across available AI platforms.

    Args:
        target_url: The domain to check citations for
        topics: Topics the site covers (for query generation)
        output_dir: Where to save results
        platforms: Which platforms to test (default: all with valid keys)

    Returns:
        Citation results dict compatible with report_generator
    """
    if not target_url.startswith("http"):
        target_url = f"https://{target_url}"

    domain = target_url.replace("https://", "").replace("http://", "").split("/")[0]
    available = _check_keys()

    # Determine which platforms to use
    if platforms:
        active = {p: available[p] for p in platforms if p in available}
    else:
        active = {p: v for p, v in available.items() if v}

    if not active:
        print("ERROR: No API keys configured. Add keys to .env file:")
        print("  OPENAI_API_KEY=sk-...")
        print("  PERPLEXITY_API_KEY=pplx-...")
        print("  ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    active_names = [PLATFORM_NAMES[p] for p in active]
    print(f"\n{'='*60}")
    print(f"  AVR Automated Citation Test")
    print(f"  Target: {target_url}")
    print(f"  Platforms: {', '.join(active_names)}")
    print(f"  Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    # Generate queries
    queries = generate_queries(domain, topics)
    total_queries = len(queries) * len(active)
    print(f"Running {len(queries)} queries x {len(active)} platforms = {total_queries} tests\n")

    # Run tests
    all_results = []
    for i, q in enumerate(queries, 1):
        for platform_key in active:
            func = PLATFORM_FUNCTIONS[platform_key]
            platform_name = PLATFORM_NAMES[platform_key]

            print(f"  [{i * len(active)}/{total_queries}] {platform_name}: {q['query'][:50]}...", end=" ", flush=True)
            result = func(q["query"], target_url)
            result["query_id"] = q["id"]
            result["category"] = q["category"]
            all_results.append(result)

            status_display = result["status"]
            if status_display == "CITED":
                status_display = "CITED <<"
            print(status_display)

            # Rate limiting: small delay between API calls
            time.sleep(0.5)

    # Compute summary
    summary = compute_results(all_results)
    summary["target_url"] = target_url
    summary["test_date"] = datetime.now(timezone.utc).isoformat()
    summary["platforms_tested"] = list(active.keys())

    # Save raw results
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    raw_path = os.path.join(output_dir, f"citations_{domain}_{timestamp}_raw.json")
    with open(raw_path, "w") as f:
        json.dump(all_results, f, indent=2)

    summary_path = os.path.join(output_dir, f"citations_{domain}_{timestamp}_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  CITATION TEST RESULTS")
    print(f"  Verdict: {summary['verdict']} (confidence: {summary['confidence_label']})")
    print(f"  Citation rate: {summary['citation_rate_pct']}% ({summary['cited_count']}/{summary['testable']})")
    ci = summary["confidence_interval_95"]
    print(f"  95% CI: [{ci['low_pct']}%, {ci['high_pct']}%]")
    print(f"")
    print(f"  Per platform:")
    for pname, pdata in summary["by_platform"].items():
        print(f"    {pname}: {pdata['cited']}/{pdata['total']} cited ({pdata['citation_rate_pct']}%)")
    print(f"")
    print(f"  Raw results: {raw_path}")
    print(f"  Summary: {summary_path}")
    print(f"{'='*60}")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="AVR Automated Citation Testing",
        epilog="""
Examples:
  python citation_auto.py test chudi.dev --topics "Claude Code hooks" "AI visibility"
  python citation_auto.py test example.com --platforms openai perplexity
  python citation_auto.py status                    # Check which API keys are configured
  python citation_auto.py test example.com -o reports/

Platforms:
  openai      ChatGPT with web search (gpt-4o-mini, ~$0.01/query)
  perplexity  Perplexity sonar search (~$0.005/query)
  anthropic   Claude with web search (haiku, ~$0.005/query)

Cost: ~$1.20 per full audit (20 queries x 3 platforms)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # status command
    sub.add_parser("status", help="Check which API keys are configured")

    # test command
    test_p = sub.add_parser("test", help="Run citation test on a URL")
    test_p.add_argument("url", help="Target URL to test citations for")
    test_p.add_argument("--topics", nargs="*", help="Topics the site covers")
    test_p.add_argument("--platforms", nargs="*", choices=["openai", "perplexity", "anthropic"], help="Which platforms to test (default: all with keys)")
    test_p.add_argument("-o", "--output", default=".", help="Output directory")

    args = parser.parse_args()

    if args.command == "status":
        keys = _check_keys()
        print("AVR Citation Testing - API Key Status\n")
        for platform, has_key in keys.items():
            status = "CONFIGURED" if has_key else "MISSING"
            name = PLATFORM_NAMES[platform]
            print(f"  {name:12s} [{status}]")
        print()
        missing = [PLATFORM_NAMES[p] for p, v in keys.items() if not v]
        if missing:
            print(f"  Missing: {', '.join(missing)}")
            print(f"  Add keys to: {env_path}")
        else:
            print("  All platforms ready.")

    elif args.command == "test":
        run_citation_test(args.url, args.topics, args.output, args.platforms)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
