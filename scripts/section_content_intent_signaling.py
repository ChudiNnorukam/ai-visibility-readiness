#!/usr/bin/env python3
"""
AVR §1.4 Content Intent Signaling Audit

Parses robots.txt for content intent directives that separate ACCESS permission
(traditional Allow/Disallow) from USAGE permission (what AI systems may do with
the content). Three directive families:

  ai-train:  May this content be used for model training?
  search:    May this content appear in AI search/citation results?
  ai-input:  May this content be used as query context?

The "search" directive is directly tied to citation eligibility and is the
load-bearing signal for AVR's citation measurement thesis.

Reference: IETF draft (emerging), Suganthan Layer 2 protocol stack.

Four checks:
  S1: robots.txt accessible and parseable
  S2: Any content intent directives present (ai-train, search, ai-input)
  S3: "search" directive explicitly allows citation (search: allow or search: yes)
  S4: Directive coverage - are intent signals set for all major AI user-agents?

Verdict bands:
  INTENT-SIGNALED   = S1 + S2 + S3 all pass (site signals citation intent)
  INTENT-PARTIAL    = S1 + S2 pass, S3 fails (has intent directives but not search)
  INTENT-ABSENT     = S1 or S2 fail (no content intent signaling at all)

Cost: $0 (HTTP GET + local parsing).
"""

import argparse
import json
import re
import sys
from typing import Any
from urllib.parse import urlparse

import requests

INTENT_DIRECTIVES = ["ai-train", "search", "ai-input"]

AI_AGENTS = [
    "claudebot", "gptbot", "chatgpt-user", "perplexitybot",
    "google-extended", "anthropic-ai", "applebot-extended",
    "cohere-ai", "ccbot",
]


def parse_robots_intent(robots_text: str) -> dict[str, Any]:
    """Parse robots.txt for content intent directives.

    Returns per-agent and wildcard intent directives found.
    """
    lines = robots_text.lower().split("\n")
    current_agent = None
    intents: dict[str, dict[str, str]] = {}

    for line in lines:
        line = line.strip()
        if line.startswith("#") or not line:
            continue

        if line.startswith("user-agent:"):
            current_agent = line.split(":", 1)[1].strip()
            if current_agent not in intents:
                intents[current_agent] = {}
        elif ":" in line and current_agent is not None:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key in INTENT_DIRECTIVES:
                intents[current_agent][key] = value

    return intents


def run_section_content_intent_signaling(url: str) -> dict[str, Any]:
    """Run the Content Intent Signaling audit."""
    if not url.startswith("http"):
        url = f"https://{url}"

    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = f"{origin}/robots.txt"

    checks: list[dict[str, Any]] = []
    robots_text = ""
    robots_accessible = False

    # S1: robots.txt accessible
    try:
        resp = requests.get(
            robots_url,
            timeout=10,
            headers={"User-Agent": "citability.dev/avr-audit/1.2"},
        )
        robots_accessible = resp.status_code == 200
        if robots_accessible:
            robots_text = resp.text
    except Exception as e:
        robots_text = ""
        robots_accessible = False

    checks.append({
        "check_id": "S1",
        "name": "robots.txt accessible",
        "pass": robots_accessible,
        "detail": (
            f"robots.txt returned HTTP {resp.status_code}"
            if robots_accessible
            else "robots.txt not accessible or returned non-200"
        ),
    })

    # Parse intent directives
    intents = parse_robots_intent(robots_text) if robots_accessible else {}
    all_intent_keys: set[str] = set()
    for agent_intents in intents.values():
        all_intent_keys.update(agent_intents.keys())

    # S2: Any content intent directives present
    has_any_intent = len(all_intent_keys) > 0
    found_directives = sorted(all_intent_keys) if has_any_intent else []
    checks.append({
        "check_id": "S2",
        "name": "Content intent directives present",
        "pass": has_any_intent,
        "detail": (
            f"Found intent directives: {', '.join(found_directives)}"
            if has_any_intent
            else "No ai-train, search, or ai-input directives found in robots.txt"
        ),
    })

    # S3: "search" directive allows citation
    search_values: list[str] = []
    for agent, agent_intents in intents.items():
        if "search" in agent_intents:
            search_values.append(f"{agent}: search={agent_intents['search']}")

    search_allows = any(
        agent_intents.get("search", "").lower() in ("allow", "yes", "true", "all")
        for agent_intents in intents.values()
    )
    checks.append({
        "check_id": "S3",
        "name": "search directive allows citation",
        "pass": search_allows,
        "detail": (
            f"Citation-allowing search directives: {'; '.join(search_values)}"
            if search_allows
            else (
                f"search directive found but does not allow: {'; '.join(search_values)}"
                if search_values
                else "No 'search' directive found. Site does not signal citation intent."
            )
        ),
    })

    # S4: Directive coverage across major AI user-agents
    agents_with_intent = set()
    for agent in intents:
        if any(ai_agent in agent for ai_agent in AI_AGENTS) or agent == "*":
            if intents[agent]:
                agents_with_intent.add(agent)

    coverage_pct = (
        len(agents_with_intent) / max(1, len(AI_AGENTS)) * 100
        if agents_with_intent
        else 0
    )
    has_wildcard_intent = "*" in intents and bool(intents.get("*"))
    good_coverage = has_wildcard_intent or coverage_pct >= 50

    checks.append({
        "check_id": "S4",
        "name": "Intent directive coverage",
        "pass": good_coverage,
        "detail": (
            f"Wildcard (*) has intent directives covering all agents"
            if has_wildcard_intent
            else (
                f"Intent directives cover {len(agents_with_intent)}/{len(AI_AGENTS)} "
                f"major AI agents ({coverage_pct:.0f}%)"
            )
        ),
    })

    # Verdict
    pass_count = sum(1 for c in checks if c["pass"])
    total_checks = len(checks)

    if checks[0]["pass"] and checks[1]["pass"] and checks[2]["pass"]:
        verdict = "INTENT-SIGNALED"
    elif checks[0]["pass"] and checks[1]["pass"]:
        verdict = "INTENT-PARTIAL"
    else:
        verdict = "INTENT-ABSENT"

    return {
        "section_id": "1.4",
        "section_name": "Content Intent Signaling",
        "section_verdict": verdict,
        "pass_count": pass_count,
        "total_checks": total_checks,
        "checks": checks,
        "intent_directives_found": dict(intents) if intents else {},
        "url_audited": url,
        "robots_url": robots_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AVR §1.4 Content Intent Signaling Audit"
    )
    parser.add_argument("url", help="URL to audit")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    result = run_section_content_intent_signaling(args.url)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"\n{'='*50}")
    print(f"  AVR §1.4 Content Intent Signaling")
    print(f"  URL: {args.url}")
    print(f"{'='*50}")
    print(f"\n  Verdict: {result['section_verdict']}")
    print(f"  Checks: {result['pass_count']}/{result['total_checks']} pass\n")
    for check in result["checks"]:
        status = "PASS" if check["pass"] else "FAIL"
        print(f"  [{status}] {check['check_id']}: {check['name']}")
        print(f"         {check['detail']}")

    if result["intent_directives_found"]:
        print(f"\n  Directives found:")
        for agent, directives in result["intent_directives_found"].items():
            for key, value in directives.items():
                print(f"    User-agent: {agent} -> {key}: {value}")


if __name__ == "__main__":
    main()
