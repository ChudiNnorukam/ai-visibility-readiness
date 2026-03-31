# Copyright (c) 2026 Chudi Nnorukam. All rights reserved.
# Licensed under the AVR Source-Available License v1.0. See LICENSE file.
# https://citability.dev

#!/usr/bin/env python3
"""
AVR Automated AI Visibility Testing

Different from citation testing. Citation checks if the AI links to your URL.
Visibility checks if the AI KNOWS about you: mentions your brand, references
your concepts, or recommends your product, even without a direct link.

Three visibility signals:
1. BRAND RECOGNITION: Does the AI know who you are when asked directly?
2. CONCEPT ATTRIBUTION: Does the AI use your ideas/terminology in topic queries?
3. RECOMMENDATION: Does the AI recommend you when asked for tools/resources?

Setup:
  Same .env as citation_auto.py (OPENAI_API_KEY, PERPLEXITY_API_KEY, ANTHROPIC_API_KEY)

Cost per audit (~30 queries):
  Similar to citation testing, ~$0.60-$1.00 depending on platforms available.
"""

import argparse
import json
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
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


PLATFORM_NAMES = {
    "openai": "ChatGPT",
    "perplexity": "Perplexity",
    "anthropic": "Claude",
}


def _query_openai(query: str) -> str:
    """Query OpenAI and return the full response text."""
    from openai import OpenAI
    client = OpenAI()
    response = client.responses.create(
        model="gpt-4o-mini",
        tools=[{"type": "web_search_preview"}],
        input=query,
    )
    text = ""
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    text += content.text
    return text


def _query_perplexity(query: str) -> str:
    """Query Perplexity and return the full response text."""
    import requests as req
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    resp = req.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "sonar", "messages": [{"role": "user", "content": query}]},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("choices"):
        return data["choices"][0].get("message", {}).get("content", "")
    return ""


def _query_anthropic(query: str) -> str:
    """Query Anthropic and return the full response text."""
    from anthropic import Anthropic
    client = Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": query}],
    )
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text
    return text


QUERY_FUNCTIONS = {
    "openai": _query_openai,
    "perplexity": _query_perplexity,
    "anthropic": _query_anthropic,
}


def check_brand_recognition(
    response_text: str,
    domain: str,
    brand_name: str,
    owner_name: str | None = None,
) -> dict:
    """Check if the response shows brand recognition."""
    text_lower = response_text.lower()
    domain_clean = domain.replace("https://", "").replace("http://", "").rstrip("/").lower()

    signals = {
        "domain_mentioned": domain_clean in text_lower,
        "brand_mentioned": brand_name.lower() in text_lower,
        "owner_mentioned": owner_name.lower() in text_lower if owner_name else False,
        "described_accurately": False,  # requires manual review
    }

    mention_count = sum([signals["domain_mentioned"], signals["brand_mentioned"], signals["owner_mentioned"]])

    if mention_count >= 2:
        level = "KNOWN"
    elif mention_count == 1:
        level = "PARTIALLY_KNOWN"
    else:
        level = "UNKNOWN"

    return {"signals": signals, "level": level, "mention_count": mention_count}


def check_concept_attribution(
    response_text: str,
    key_concepts: list[str],
) -> dict:
    """Check if the AI uses concepts/terminology associated with the brand."""
    text_lower = response_text.lower()
    found = []
    for concept in key_concepts:
        if concept.lower() in text_lower:
            found.append(concept)

    ratio = len(found) / len(key_concepts) if key_concepts else 0
    return {
        "concepts_checked": key_concepts,
        "concepts_found": found,
        "concept_ratio": round(ratio, 2),
    }


def check_recommendation(
    response_text: str,
    domain: str,
    brand_name: str,
    product_names: list[str] | None = None,
) -> dict:
    """Check if the AI recommends the brand/product."""
    text_lower = response_text.lower()
    domain_clean = domain.replace("https://", "").replace("http://", "").rstrip("/").lower()

    recommended = False
    recommended_as = []

    # Check for direct recommendations
    rec_patterns = [
        f"recommend {brand_name.lower()}",
        f"try {brand_name.lower()}",
        f"check out {brand_name.lower()}",
        f"use {brand_name.lower()}",
        f"visit {domain_clean}",
        f"{brand_name.lower()} is a",
        f"{brand_name.lower()} offers",
        f"{brand_name.lower()} provides",
    ]

    for pattern in rec_patterns:
        if pattern in text_lower:
            recommended = True
            recommended_as.append(pattern)

    # Check product names
    if product_names:
        for product in product_names:
            if product.lower() in text_lower:
                recommended = True
                recommended_as.append(f"product: {product}")

    return {
        "recommended": recommended,
        "recommended_as": recommended_as,
    }


def generate_visibility_queries(
    domain: str,
    brand_name: str,
    owner_name: str | None = None,
    topics: list[str] | None = None,
    products: list[str] | None = None,
) -> list[dict]:
    """Generate queries for visibility testing across 3 signal categories."""
    queries = []

    # Category 1: Brand Recognition (10 queries)
    queries.extend([
        {"id": 1, "category": "brand_recognition", "query": f"What is {domain}?", "signal": "direct_ask"},
        {"id": 2, "category": "brand_recognition", "query": f"Tell me about {brand_name}", "signal": "direct_ask"},
        {"id": 3, "category": "brand_recognition", "query": f"What does {brand_name} do?", "signal": "direct_ask"},
    ])
    if owner_name:
        queries.extend([
            {"id": 4, "category": "brand_recognition", "query": f"Who is {owner_name}?", "signal": "owner_recognition"},
            {"id": 5, "category": "brand_recognition", "query": f"What has {owner_name} built?", "signal": "owner_recognition"},
        ])
    else:
        queries.extend([
            {"id": 4, "category": "brand_recognition", "query": f"Who created {domain}?", "signal": "owner_recognition"},
            {"id": 5, "category": "brand_recognition", "query": f"Who runs {brand_name}?", "signal": "owner_recognition"},
        ])

    # Category 2: Concept Attribution (10 queries using topics)
    if topics:
        for i, topic in enumerate(topics[:5]):
            queries.append({
                "id": 10 + i,
                "category": "concept_attribution",
                "query": f"What are the best approaches for {topic}?",
                "signal": "topic_expertise",
            })
        for i, topic in enumerate(topics[:5]):
            queries.append({
                "id": 15 + i,
                "category": "concept_attribution",
                "query": f"Who writes about {topic}?",
                "signal": "author_association",
            })

    # Category 3: Recommendation (10 queries)
    if topics:
        for i, topic in enumerate(topics[:5]):
            queries.append({
                "id": 20 + i,
                "category": "recommendation",
                "query": f"What tools or blogs should I follow for {topic}?",
                "signal": "recommendation",
            })
        for i, topic in enumerate(topics[:3]):
            queries.append({
                "id": 25 + i,
                "category": "recommendation",
                "query": f"Best resources for learning {topic} in 2026",
                "signal": "recommendation",
            })
    if products:
        for i, product in enumerate(products[:2]):
            queries.append({
                "id": 28 + i,
                "category": "recommendation",
                "query": f"Is {product} worth using?",
                "signal": "product_recommendation",
            })

    return queries


def run_visibility_test(
    target_url: str,
    brand_name: str,
    owner_name: str | None = None,
    topics: list[str] | None = None,
    products: list[str] | None = None,
    key_concepts: list[str] | None = None,
    output_dir: str = ".",
    platforms: list[str] | None = None,
) -> dict:
    """Run AI visibility test across available platforms.

    Args:
        target_url: Domain to test visibility for
        brand_name: Brand name to search for
        owner_name: Owner/author name
        topics: Topics the site covers
        products: Product names to check
        key_concepts: Unique concepts/terminology from the brand
        output_dir: Where to save results
        platforms: Which platforms to test

    Returns:
        Visibility results dict
    """
    if not target_url.startswith("http"):
        target_url = f"https://{target_url}"

    domain = target_url.replace("https://", "").replace("http://", "").split("/")[0]
    available = _check_keys()

    if platforms:
        active = {p: available[p] for p in platforms if available.get(p)}
    else:
        active = {p: v for p, v in available.items() if v}

    if not active:
        print("ERROR: No API keys configured.")
        sys.exit(1)

    active_names = [PLATFORM_NAMES[p] for p in active]
    print(f"\n{'='*60}")
    print(f"  AVR AI Visibility Test")
    print(f"  Target: {target_url} ({brand_name})")
    print(f"  Platforms: {', '.join(active_names)}")
    print(f"  Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    queries = generate_visibility_queries(domain, brand_name, owner_name, topics, products)
    total_tests = len(queries) * len(active)
    print(f"Running {len(queries)} queries x {len(active)} platforms = {total_tests} tests\n")

    all_results = []
    test_num = 0

    for q in queries:
        for platform_key in active:
            test_num += 1
            func = QUERY_FUNCTIONS[platform_key]
            platform_name = PLATFORM_NAMES[platform_key]

            print(f"  [{test_num}/{total_tests}] {platform_name}: {q['query'][:50]}...", end=" ", flush=True)

            try:
                response_text = func(q["query"])

                # Run all three checks on every response
                brand_check = check_brand_recognition(response_text, target_url, brand_name, owner_name)
                concept_check = check_concept_attribution(response_text, key_concepts or [])
                rec_check = check_recommendation(response_text, target_url, brand_name, products)

                # Determine visibility level for this query
                visible = brand_check["level"] != "UNKNOWN" or rec_check["recommended"] or concept_check["concept_ratio"] > 0.3

                result = {
                    "query_id": q["id"],
                    "category": q["category"],
                    "signal": q["signal"],
                    "platform": platform_name,
                    "query": q["query"],
                    "visible": visible,
                    "brand_recognition": brand_check,
                    "concept_attribution": concept_check,
                    "recommendation": rec_check,
                    "response_snippet": response_text[:300],
                }

                status = "VISIBLE" if visible else "NOT_VISIBLE"
                if brand_check["level"] == "KNOWN":
                    status = "KNOWN"
                elif rec_check["recommended"]:
                    status = "RECOMMENDED"

                print(status)

            except Exception as e:
                result = {
                    "query_id": q["id"],
                    "category": q["category"],
                    "platform": platform_name,
                    "query": q["query"],
                    "visible": False,
                    "error": str(e),
                }
                print("ERROR")

            all_results.append(result)
            time.sleep(0.5)

    # Compute summary
    total = len(all_results)
    errors = sum(1 for r in all_results if "error" in r)
    testable = total - errors
    visible_count = sum(1 for r in all_results if r.get("visible"))
    known_count = sum(1 for r in all_results if r.get("brand_recognition", {}).get("level") == "KNOWN")
    recommended_count = sum(1 for r in all_results if r.get("recommendation", {}).get("recommended"))

    visibility_rate = visible_count / testable if testable > 0 else 0

    # Per-category breakdown
    categories = {}
    for r in all_results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"visible": 0, "total": 0}
        categories[cat]["total"] += 1
        if r.get("visible"):
            categories[cat]["visible"] += 1

    for cdata in categories.values():
        cdata["rate_pct"] = round(cdata["visible"] / cdata["total"] * 100, 1) if cdata["total"] > 0 else 0

    # Per-platform breakdown
    platforms_summary = {}
    for r in all_results:
        p = r.get("platform", "unknown")
        if p not in platforms_summary:
            platforms_summary[p] = {"visible": 0, "total": 0}
        platforms_summary[p]["total"] += 1
        if r.get("visible"):
            platforms_summary[p]["visible"] += 1

    for pdata in platforms_summary.values():
        pdata["rate_pct"] = round(pdata["visible"] / pdata["total"] * 100, 1) if pdata["total"] > 0 else 0

    # Verdict
    if visibility_rate > 0.5:
        verdict = "HIGHLY_VISIBLE"
    elif visibility_rate > 0.2:
        verdict = "PARTIALLY_VISIBLE"
    elif visibility_rate > 0.05:
        verdict = "BARELY_VISIBLE"
    else:
        verdict = "INVISIBLE"

    summary = {
        "target_url": target_url,
        "brand_name": brand_name,
        "test_date": datetime.now(timezone.utc).isoformat(),
        "total_tests": total,
        "testable": testable,
        "visible_count": visible_count,
        "known_count": known_count,
        "recommended_count": recommended_count,
        "visibility_rate_pct": round(visibility_rate * 100, 1),
        "confidence_label": "LOW",  # single round is always LOW
        "by_category": categories,
        "by_platform": platforms_summary,
        "verdict": verdict,
    }

    # Save results
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    raw_path = os.path.join(output_dir, f"visibility_{domain}_{timestamp}_raw.json")
    with open(raw_path, "w") as f:
        json.dump(all_results, f, indent=2)

    summary_path = os.path.join(output_dir, f"visibility_{domain}_{timestamp}_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  AI VISIBILITY TEST RESULTS")
    print(f"  Verdict: {verdict} (confidence: LOW)")
    print(f"  Visibility rate: {summary['visibility_rate_pct']}% ({visible_count}/{testable})")
    print(f"  Brand recognized: {known_count} times")
    print(f"  Recommended: {recommended_count} times")
    print(f"")
    print(f"  By signal category:")
    for cat, cdata in categories.items():
        print(f"    {cat}: {cdata['visible']}/{cdata['total']} visible ({cdata['rate_pct']}%)")
    print(f"")
    print(f"  By platform:")
    for pname, pdata in platforms_summary.items():
        print(f"    {pname}: {pdata['visible']}/{pdata['total']} visible ({pdata['rate_pct']}%)")
    print(f"")
    print(f"  Raw results: {raw_path}")
    print(f"  Summary: {summary_path}")
    print(f"{'='*60}")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="AVR AI Visibility Testing (brand awareness, not just citation links)",
        epilog="""
Examples:
  python visibility_auto.py test chudi.dev --brand "Chudi" --owner "Chudi Nnorukam" \\
    --topics "Claude Code hooks" "AI visibility" --concepts "hooks as middleware" "AVR framework"

  python visibility_auto.py test ahrefs.com --brand "Ahrefs" \\
    --topics "backlink analysis" "keyword research" --products "Site Explorer" "Keywords Explorer"

Visibility Signals (different from citations):
  KNOWN          AI recognizes the brand and describes it accurately
  RECOMMENDED    AI recommends the brand/product when asked for resources
  VISIBLE        AI mentions brand/concepts without direct recommendation
  NOT_VISIBLE    AI shows no awareness of the brand

Cost: ~$0.60-$1.00 per audit depending on platforms
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    test_p = sub.add_parser("test", help="Run visibility test")
    test_p.add_argument("url", help="Target URL")
    test_p.add_argument("--brand", required=True, help="Brand name to check for")
    test_p.add_argument("--owner", help="Owner/author name")
    test_p.add_argument("--topics", nargs="*", help="Topics the site covers")
    test_p.add_argument("--products", nargs="*", help="Product names")
    test_p.add_argument("--concepts", nargs="*", help="Unique concepts/terminology from the brand")
    test_p.add_argument("--platforms", nargs="*", choices=["openai", "perplexity", "anthropic"])
    test_p.add_argument("-o", "--output", default=".", help="Output directory")

    args = parser.parse_args()

    if args.command == "test":
        run_visibility_test(
            args.url, args.brand, args.owner, args.topics,
            args.products, args.concepts, args.output, args.platforms,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
