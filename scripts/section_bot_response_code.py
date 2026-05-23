#!/usr/bin/env python3
"""
AVR §2.8 Bot Response Code Audit

Tests live HTTP response codes per major AI bot user-agent. Detects sites
accidentally blocking AI crawlers via 403/429 responses.

Grounded in Cloudflare Radar data (May 2026): 8.7% of AI bot requests get
403 Forbidden. This check catches operators in that 8.7%.

Four checks:
  B1: ClaudeBot response code (Anthropic, 9.3% of AI bot traffic)
  B2: GPTBot response code (OpenAI, 10.5%)
  B3: Bingbot response code (Microsoft, Bing AI)
  B4: PerplexityBot response code (Perplexity)

Verdict bands:
  ACCESS-OPEN    = all 4 bots get 200 OK
  ACCESS-PARTIAL = 1-3 bots blocked (403/429/5xx)
  ACCESS-BLOCKED = majority (3+) blocked

Cost: $0 (HTTP GET only).
"""

import argparse
import json
import sys
from typing import Any
from urllib.parse import urlparse

import requests


USER_AGENT_BASE = (
    "AVR-citability/1.1 "
    "(Section-BotResponseCode audit; https://citability.dev; "
    "contact: chudi@chudi.dev)"
)

REQUEST_TIMEOUT_SEC = 8

BOT_AGENTS = [
    {
        "id": "claudebot-response",
        "bot_name": "ClaudeBot",
        "user_agent": "ClaudeBot/1.0 (https://anthropic.com; bot)",
        "traffic_share": "9.3%",
        "rank": 10,
    },
    {
        "id": "gptbot-response",
        "bot_name": "GPTBot",
        "user_agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
        "traffic_share": "10.5%",
        "rank": 10,
    },
    {
        "id": "bingbot-response",
        "bot_name": "Bingbot",
        "user_agent": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
        "traffic_share": "N/A (Bing AI)",
        "rank": 9,
    },
    {
        "id": "perplexitybot-response",
        "bot_name": "PerplexityBot",
        "user_agent": "PerplexityBot/1.0 (+https://perplexity.ai/perplexitybot)",
        "traffic_share": "N/A",
        "rank": 8,
    },
]


def _site_root(url: str) -> str:
    if not url.startswith("http"):
        url = f"https://{url}"
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _test_bot_response(url: str, bot: dict) -> dict[str, Any]:
    """Send a GET request with a specific bot user-agent and record the response."""
    result: dict[str, Any] = {
        "id": bot["id"],
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": bot["rank"],
    }

    headers = {"User-Agent": bot["user_agent"], "Accept": "text/html"}
    try:
        resp = requests.get(
            url, headers=headers, timeout=REQUEST_TIMEOUT_SEC,
            allow_redirects=True, stream=True,
        )
        status = resp.status_code
        content_type = resp.headers.get("Content-Type", "")
        server = resp.headers.get("Server", "")

        is_blocked = status in (403, 429, 451)
        is_error = status >= 500
        result["passed"] = not is_blocked and not is_error

        result["evidence"].append({
            "bot_name": bot["bot_name"],
            "user_agent_sent": bot["user_agent"],
            "status_code": status,
            "content_type": content_type[:100],
            "server": server[:50],
            "blocked": is_blocked,
            "cloudflare_context": f"{bot['bot_name']} represents {bot['traffic_share']} of AI bot traffic (Cloudflare Radar, May 2026)",
        })
        resp.close()
    except requests.RequestException as e:
        result["evidence"].append({
            "bot_name": bot["bot_name"],
            "error": f"{type(e).__name__}: {str(e)[:100]}",
            "blocked": False,
        })

    return result


def run_section_bot_response_code(url: str) -> dict[str, Any]:
    """Run the full §2.8 Bot Response Code section."""
    if not url.startswith("http"):
        url = f"https://{url}"

    checks = []
    blocked_count = 0

    for bot in BOT_AGENTS:
        check = _test_bot_response(url, bot)
        checks.append(check)
        if not check["passed"]:
            blocked_count += 1

    total = len(checks)
    pass_count = total - blocked_count

    if blocked_count == 0:
        verdict = "ACCESS-OPEN"
    elif blocked_count >= 3:
        verdict = "ACCESS-BLOCKED"
    else:
        verdict = "ACCESS-PARTIAL"

    recommendations = []
    for check in checks:
        if not check["passed"]:
            ev = check["evidence"][0] if check["evidence"] else {}
            bot_name = ev.get("bot_name", "unknown")
            status = ev.get("status_code", "N/A")
            recommendations.append({
                "id": f"rec-unblock-{bot_name.lower()}",
                "priority": 1 if status == 403 else 2,
                "action": (
                    f"{bot_name} received HTTP {status}. "
                    f"Check your CDN/WAF rules, robots.txt, and server configuration "
                    f"to ensure {bot_name} is not accidentally blocked. "
                    f"8.7% of all AI bot requests get 403 Forbidden (Cloudflare Radar, May 2026)."
                ),
            })

    return {
        "section_id": "section_bot_response_code",
        "section_name": "Bot Response Code Audit",
        "url_audited": url,
        "checks": checks,
        "section_verdict": verdict,
        "pass_count": pass_count,
        "total_checks": total,
        "recommendations": recommendations,
        "spec_version": "AVR v1.1.0 §2.8 (Cloudflare Radar AI bot response data, May 2026)",
        "cost_usd": 0.0,
        "label": "VERIFIABLE",
        "cloudflare_baseline": {
            "data_window": "May 17-23, 2026",
            "global_403_rate": "8.7%",
            "global_200_rate": "71.2%",
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="AVR §2.8 Bot Response Code Audit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Cost: $0 (HTTP GET only).",
    )
    parser.add_argument("url", help="URL to audit")
    parser.add_argument("-o", "--output", help="Write JSON result to file")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.quiet:
        print(f"[section-bot-response] auditing {args.url} ...", file=sys.stderr)
    result = run_section_bot_response_code(args.url)
    if not args.quiet:
        print(
            f"[section-bot-response] verdict: {result['section_verdict']} "
            f"({result['pass_count']}/{result['total_checks']} bots get 200)",
            file=sys.stderr,
        )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
    else:
        print(json.dumps(result, indent=2))

    code_map = {"ACCESS-OPEN": 0, "ACCESS-PARTIAL": 1, "ACCESS-BLOCKED": 2}
    sys.exit(code_map.get(result["section_verdict"], 2))


if __name__ == "__main__":
    main()
