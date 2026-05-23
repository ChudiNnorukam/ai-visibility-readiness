#!/usr/bin/env python3
"""
AVR §2.10 AI Rules in robots.txt Audit

Parses robots.txt for AI-specific user-agent directives. Cloudflare Radar
(May 2026): 79% of top domains have AI-specific rules in robots.txt, but
many get them wrong (inconsistent blocking, missing major crawlers).

Three checks:
  R1: robots.txt exists and is parseable
  R2: AI-specific user-agent rules present (any of ClaudeBot, GPTBot,
      ChatGPT-User, Bingbot, PerplexityBot, anthropic-ai, etc.)
  R3: Rule completeness - are all major AI crawlers explicitly addressed?
      Inconsistent rules (blocking GPTBot but not ClaudeBot) are flagged.

Verdict bands:
  AI-RULES-COMPLETE = R1 + R2 + R3 all pass (robots.txt with complete AI coverage)
  AI-RULES-PARTIAL  = R1 + R2 pass, R3 fails (has rules but inconsistent)
  AI-RULES-MISSING  = R1 or R2 fail (no robots.txt or no AI rules)

Cost: $0 (HTTP GET + local parsing).
"""

import argparse
import json
import re
import sys
from typing import Any
from urllib.parse import urlparse

import requests


USER_AGENT = (
    "AVR-citability/1.1 "
    "(Section-RobotsAIRules audit; https://citability.dev; "
    "contact: chudi@chudi.dev)"
)

REQUEST_TIMEOUT_SEC = 8

AI_USER_AGENTS = [
    "ClaudeBot",
    "anthropic-ai",
    "Claude-Web",
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "Bingbot",
    "PerplexityBot",
    "Bytespider",
    "Google-Extended",
    "Googlebot",
]

MAJOR_AI_CRAWLERS = {"ClaudeBot", "GPTBot", "ChatGPT-User", "PerplexityBot", "Google-Extended"}


def _site_root(url: str) -> str:
    if not url.startswith("http"):
        url = f"https://{url}"
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _fetch_robots_txt(site_root: str) -> tuple[str | None, str | None, int | None]:
    """Fetch robots.txt. Returns (body, error, status_code)."""
    url = f"{site_root}/robots.txt"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC, allow_redirects=True)
        if resp.status_code == 404:
            return None, "not_found", 404
        if resp.status_code >= 400:
            return None, f"http_{resp.status_code}", resp.status_code
        return resp.text, None, resp.status_code
    except requests.RequestException as e:
        return None, f"network_error:{type(e).__name__}", None


def _parse_user_agent_blocks(robots_txt: str) -> dict[str, list[str]]:
    """Parse robots.txt into {user-agent: [directives]} map."""
    blocks: dict[str, list[str]] = {}
    current_agents: list[str] = []

    for line in robots_txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.lower().startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            current_agents.append(agent)
            if agent not in blocks:
                blocks[agent] = []
        elif current_agents:
            for agent in current_agents:
                blocks[agent].append(line)
            if not line.lower().startswith(("allow:", "disallow:", "crawl-delay:", "sitemap:")):
                pass
        else:
            pass

        if line.lower().startswith(("allow:", "disallow:")) and not current_agents:
            current_agents = []

    return blocks


def check_robots_exists(site_root: str) -> tuple[dict[str, Any], str | None]:
    """Check R1: robots.txt exists and is parseable."""
    result: dict[str, Any] = {
        "id": "robots-txt-exists",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 8,
    }

    body, err, status = _fetch_robots_txt(site_root)
    if err:
        result["evidence"].append({
            "error": err,
            "status_code": status,
            "url": f"{site_root}/robots.txt",
        })
        return result, None

    line_count = len(body.splitlines()) if body else 0
    result["passed"] = line_count >= 2
    result["evidence"].append({
        "status_code": status,
        "line_count": line_count,
        "size_bytes": len(body.encode()) if body else 0,
        "url": f"{site_root}/robots.txt",
    })
    return result, body


def check_ai_rules_present(robots_txt: str | None) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Check R2: AI-specific user-agent rules are present."""
    result: dict[str, Any] = {
        "id": "ai-rules-present",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 9,
    }

    if not robots_txt:
        result["evidence"].append({"error": "no_robots_txt"})
        return result, {}

    blocks = _parse_user_agent_blocks(robots_txt)

    found_ai_agents = []
    for agent_name in AI_USER_AGENTS:
        for block_agent in blocks:
            if agent_name.lower() == block_agent.lower():
                directives = blocks[block_agent]
                has_allow = any(d.lower().startswith("allow:") for d in directives)
                has_disallow = any(d.lower().startswith("disallow:") for d in directives)
                found_ai_agents.append({
                    "agent": agent_name,
                    "matched_block": block_agent,
                    "has_allow": has_allow,
                    "has_disallow": has_disallow,
                    "directive_count": len(directives),
                })

    result["passed"] = len(found_ai_agents) >= 1
    result["evidence"].append({
        "ai_agents_found": len(found_ai_agents),
        "agents": found_ai_agents,
        "total_user_agent_blocks": len(blocks),
        "cloudflare_baseline": "79% of top domains have AI-specific rules (Cloudflare Radar, May 2026)",
    })
    return result, blocks


def check_rule_completeness(blocks: dict[str, list[str]]) -> dict[str, Any]:
    """Check R3: Are all major AI crawlers explicitly addressed?"""
    result: dict[str, Any] = {
        "id": "ai-rules-completeness",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 7,
    }

    if not blocks:
        result["evidence"].append({"error": "no_blocks_to_check"})
        return result

    block_agents_lower = {a.lower() for a in blocks}

    covered = []
    missing = []
    for crawler in MAJOR_AI_CRAWLERS:
        if crawler.lower() in block_agents_lower:
            covered.append(crawler)
        else:
            missing.append(crawler)

    coverage_rate = len(covered) / len(MAJOR_AI_CRAWLERS) if MAJOR_AI_CRAWLERS else 0

    has_wildcard = "*" in blocks
    wildcard_has_ai_directives = False
    if has_wildcard:
        wildcard_directives = blocks["*"]
        wildcard_has_ai_directives = any(
            "ai" in d.lower() or "bot" in d.lower() or "crawl" in d.lower()
            for d in wildcard_directives
        )

    inconsistency = []
    blocking_agents = set()
    allowing_agents = set()
    for crawler in MAJOR_AI_CRAWLERS:
        for block_agent, directives in blocks.items():
            if crawler.lower() == block_agent.lower():
                has_disallow_all = any(
                    re.match(r"disallow:\s*/\s*$", d, re.IGNORECASE)
                    for d in directives
                )
                if has_disallow_all:
                    blocking_agents.add(crawler)
                else:
                    allowing_agents.add(crawler)

    if blocking_agents and allowing_agents:
        inconsistency.append({
            "type": "mixed_policy",
            "blocked": sorted(blocking_agents),
            "allowed": sorted(allowing_agents),
            "note": "Inconsistent: some AI crawlers fully blocked while others allowed",
        })

    result["passed"] = len(missing) <= 1 and len(inconsistency) == 0
    result["evidence"].append({
        "major_crawlers_total": len(MAJOR_AI_CRAWLERS),
        "covered": sorted(covered),
        "missing": sorted(missing),
        "coverage_rate": round(coverage_rate, 2),
        "has_wildcard": has_wildcard,
        "inconsistencies": inconsistency,
    })
    if not result["passed"]:
        result["compliance_rate"] = round(coverage_rate, 2)

    return result


def run_section_robots_ai_rules(url: str) -> dict[str, Any]:
    """Run the full §2.10 AI Rules in robots.txt section."""
    site_root = _site_root(url)

    r1, robots_body = check_robots_exists(site_root)
    r2, blocks = check_ai_rules_present(robots_body)
    r3 = check_rule_completeness(blocks)

    checks = [r1, r2, r3]
    pass_count = sum(1 for c in checks if c["passed"])

    if pass_count == 3:
        verdict = "AI-RULES-COMPLETE"
    elif r1["passed"] and r2["passed"]:
        verdict = "AI-RULES-PARTIAL"
    else:
        verdict = "AI-RULES-MISSING"

    recommendations = []
    if not r1["passed"]:
        recommendations.append({
            "id": "rec-create-robots-txt",
            "priority": 1,
            "action": "Create a robots.txt file. 83% of top domains have one (Cloudflare Radar, May 2026).",
        })
    if not r2["passed"] and r1["passed"]:
        recommendations.append({
            "id": "rec-add-ai-rules",
            "priority": 1,
            "action": (
                "Add AI-specific user-agent rules to robots.txt. 79% of top domains "
                "have them. At minimum, add explicit directives for ClaudeBot, GPTBot, "
                "ChatGPT-User, PerplexityBot, and Google-Extended."
            ),
        })
    if not r3["passed"] and r2["passed"]:
        ev = r3["evidence"][0] if r3["evidence"] else {}
        missing = ev.get("missing", [])
        inconsistencies = ev.get("inconsistencies", [])
        if missing:
            recommendations.append({
                "id": "rec-complete-ai-rules",
                "priority": 2,
                "action": f"Add robots.txt rules for missing AI crawlers: {', '.join(missing)}.",
            })
        if inconsistencies:
            recommendations.append({
                "id": "rec-fix-inconsistent-rules",
                "priority": 1,
                "action": (
                    "Fix inconsistent AI bot policy: some crawlers are fully blocked while "
                    "others are allowed. This likely blocks indexing by engines you want to be cited in."
                ),
            })

    return {
        "section_id": "section_robots_ai_rules",
        "section_name": "AI Rules in robots.txt",
        "url_audited": url,
        "checks": checks,
        "section_verdict": verdict,
        "pass_count": pass_count,
        "total_checks": len(checks),
        "recommendations": recommendations,
        "spec_version": "AVR v1.1.0 §2.10 (Cloudflare Radar robots.txt AI rules data, May 2026)",
        "cost_usd": 0.0,
        "label": "VERIFIABLE",
        "cloudflare_baseline": {
            "data_window": "May 17-23, 2026",
            "robots_txt_adoption": "83%",
            "ai_rules_adoption": "79%",
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="AVR §2.10 AI Rules in robots.txt Audit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Cost: $0 (HTTP GET + local parsing).",
    )
    parser.add_argument("url", help="URL to audit")
    parser.add_argument("-o", "--output", help="Write JSON result to file")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.quiet:
        print(f"[section-robots-ai] auditing {args.url} ...", file=sys.stderr)
    result = run_section_robots_ai_rules(args.url)
    if not args.quiet:
        print(f"[section-robots-ai] verdict: {result['section_verdict']}", file=sys.stderr)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
    else:
        print(json.dumps(result, indent=2))

    code_map = {"AI-RULES-COMPLETE": 0, "AI-RULES-PARTIAL": 1, "AI-RULES-MISSING": 2}
    sys.exit(code_map.get(result["section_verdict"], 2))


if __name__ == "__main__":
    main()
