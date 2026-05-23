#!/usr/bin/env python3
"""
AVR §2.11 Agent Readiness Tier Score

Composite score across 4 agent standards adoption signals. Broader than
§2.7 WebMCP (which checks manifest + AgentCard specifically); this section
scores the BREADTH of agent infrastructure adoption.

Cloudflare Radar (May 2026) adoption rates across top 200K domains:
  robots.txt AI rules: 79%
  Sitemap: 68%
  MCP Server Card / .well-known/webmcp: 0.11% / 0%
  Agent Skills / A2A AgentCard: 0.13% / 0.0081%

Four checks:
  T1: robots.txt has AI-specific rules (79% baseline)
  T2: XML sitemap accessible (68% baseline)
  T3: .well-known/webmcp manifest present (0% baseline)
  T4: .well-known/agent.json AgentCard present (0.0081% baseline)

Score: 0-4 (count of passed checks)

Verdict bands:
  AGENT-TIER-HIGH = 3-4 checks pass (ahead of market)
  AGENT-TIER-MID  = 1-2 checks pass (baseline infrastructure)
  AGENT-TIER-LOW  = 0 checks pass (no agent readiness)

Cost: $0 (HTTP GET only).
"""

import argparse
import json
import sys
from typing import Any
from urllib.parse import urlparse

import requests


USER_AGENT = (
    "AVR-citability/1.1 "
    "(Section-AgentReadinessTier audit; https://citability.dev; "
    "contact: chudi@chudi.dev)"
)

REQUEST_TIMEOUT_SEC = 8


def _site_root(url: str) -> str:
    if not url.startswith("http"):
        url = f"https://{url}"
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _head_or_get(url: str, accept: str = "*/*") -> tuple[int | None, str]:
    """Light probe: HEAD first, fall back to GET on 405."""
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    try:
        resp = requests.head(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC, allow_redirects=True)
        if resp.status_code == 405:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC, allow_redirects=True)
        return resp.status_code, resp.headers.get("Content-Type", "")
    except requests.RequestException as e:
        return None, f"error:{type(e).__name__}"


def check_robots_ai_rules(site_root: str) -> dict[str, Any]:
    """T1: robots.txt has AI-specific user-agent rules."""
    result: dict[str, Any] = {
        "id": "tier-robots-ai-rules",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 8,
    }

    url = f"{site_root}/robots.txt"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
        if resp.status_code != 200:
            result["evidence"].append({"error": f"http_{resp.status_code}", "url": url})
            return result

        body = resp.text.lower()
        ai_agents_found = []
        for agent in ["claudebot", "gptbot", "chatgpt-user", "perplexitybot", "google-extended", "anthropic-ai"]:
            if f"user-agent: {agent}" in body:
                ai_agents_found.append(agent)

        result["passed"] = len(ai_agents_found) >= 1
        result["evidence"].append({
            "ai_agents_found": ai_agents_found,
            "count": len(ai_agents_found),
            "adoption_baseline": "79% of top domains (Cloudflare Radar, May 2026)",
        })
    except requests.RequestException as e:
        result["evidence"].append({"error": f"{type(e).__name__}", "url": url})

    return result


def check_sitemap(site_root: str) -> dict[str, Any]:
    """T2: XML sitemap accessible."""
    result: dict[str, Any] = {
        "id": "tier-sitemap-present",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 7,
    }

    sitemap_paths = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"]
    for path in sitemap_paths:
        url = f"{site_root}{path}"
        status, ct = _head_or_get(url, "application/xml")
        if status == 200:
            result["passed"] = True
            result["evidence"].append({
                "sitemap_url": url,
                "status_code": 200,
                "content_type": ct[:100],
                "adoption_baseline": "68% of top domains (Cloudflare Radar, May 2026)",
            })
            return result

    result["evidence"].append({
        "paths_checked": [f"{site_root}{p}" for p in sitemap_paths],
        "note": "No sitemap found at standard paths",
    })
    return result


def check_webmcp_manifest(site_root: str) -> dict[str, Any]:
    """T3: .well-known/webmcp manifest present."""
    result: dict[str, Any] = {
        "id": "tier-webmcp-present",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 10,
    }

    url = f"{site_root}/.well-known/webmcp"
    status, ct = _head_or_get(url, "application/json")
    result["passed"] = status == 200
    result["evidence"].append({
        "url": url,
        "status_code": status,
        "content_type": ct[:100] if status == 200 else "",
        "adoption_baseline": "0% of top 200K domains (Cloudflare Radar, May 2026)",
    })
    return result


def check_agentcard(site_root: str) -> dict[str, Any]:
    """T4: .well-known/agent.json AgentCard present."""
    result: dict[str, Any] = {
        "id": "tier-agentcard-present",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 9,
    }

    url = f"{site_root}/.well-known/agent.json"
    status, ct = _head_or_get(url, "application/json")
    result["passed"] = status == 200
    result["evidence"].append({
        "url": url,
        "status_code": status,
        "content_type": ct[:100] if status == 200 else "",
        "adoption_baseline": "0.0081% of top 200K domains (Cloudflare Radar, May 2026)",
    })
    return result


def run_section_agent_readiness_tier(url: str) -> dict[str, Any]:
    """Run the full §2.11 Agent Readiness Tier section."""
    site_root = _site_root(url)

    t1 = check_robots_ai_rules(site_root)
    t2 = check_sitemap(site_root)
    t3 = check_webmcp_manifest(site_root)
    t4 = check_agentcard(site_root)

    checks = [t1, t2, t3, t4]
    pass_count = sum(1 for c in checks if c["passed"])

    if pass_count >= 3:
        verdict = "AGENT-TIER-HIGH"
    elif pass_count >= 1:
        verdict = "AGENT-TIER-MID"
    else:
        verdict = "AGENT-TIER-LOW"

    recommendations = []
    if not t1["passed"]:
        recommendations.append({
            "id": "rec-add-ai-robots-rules",
            "priority": 1,
            "action": "Add AI-specific user-agent rules to robots.txt. 79% of top domains have them.",
        })
    if not t2["passed"]:
        recommendations.append({
            "id": "rec-add-sitemap",
            "priority": 2,
            "action": "Publish an XML sitemap. 68% of top domains have one.",
        })
    if not t3["passed"]:
        recommendations.append({
            "id": "rec-add-webmcp",
            "priority": 3,
            "action": (
                "Publish a .well-known/webmcp manifest. 0% of top domains have this; "
                "it is the frontier of agent readiness."
            ),
        })
    if not t4["passed"]:
        recommendations.append({
            "id": "rec-add-agentcard",
            "priority": 4,
            "action": "Publish a .well-known/agent.json AgentCard if your site exposes agent skills.",
        })

    return {
        "section_id": "section_agent_readiness_tier",
        "section_name": "Agent Readiness Tier Score",
        "url_audited": url,
        "checks": checks,
        "section_verdict": verdict,
        "pass_count": pass_count,
        "total_checks": len(checks),
        "agent_tier_score": pass_count,
        "recommendations": recommendations,
        "spec_version": "AVR v1.1.0 §2.11 (Cloudflare Radar agent standards adoption, May 2026)",
        "cost_usd": 0.0,
        "label": "VERIFIABLE",
        "cloudflare_baseline": {
            "data_window": "May 17-23, 2026",
            "scanned_domains": 111076,
            "standards_adoption": {
                "robots_txt_ai_rules": "79%",
                "sitemap": "68%",
                "webmcp": "0%",
                "a2a_agent_card": "0.0081%",
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="AVR §2.11 Agent Readiness Tier Score",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Cost: $0 (HTTP GET only).",
    )
    parser.add_argument("url", help="URL to audit")
    parser.add_argument("-o", "--output", help="Write JSON result to file")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.quiet:
        print(f"[section-agent-tier] auditing {args.url} ...", file=sys.stderr)
    result = run_section_agent_readiness_tier(args.url)
    if not args.quiet:
        print(
            f"[section-agent-tier] verdict: {result['section_verdict']} "
            f"(score: {result['agent_tier_score']}/4)",
            file=sys.stderr,
        )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
    else:
        print(json.dumps(result, indent=2))

    code_map = {"AGENT-TIER-HIGH": 0, "AGENT-TIER-MID": 1, "AGENT-TIER-LOW": 2}
    sys.exit(code_map.get(result["section_verdict"], 2))


if __name__ == "__main__":
    main()
