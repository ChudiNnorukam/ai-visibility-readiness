#!/usr/bin/env python3
"""
AVR §2.12 Crawl Signal Check

Verifies that a site is accessible to AI crawlers and responsive enough
for reliable crawling. Acts as a proxy for crawl-signal presence when
CDN log access is unavailable.

Cloudflare Radar context (May 2026): ClaudeBot crawls at 10,600:1
crawl-to-refer ratio (declining 16.9%), GPTBot at 1,000:1 (declining
11.9%). If AI bots can not reach your site, you can not be cited.

Three checks:
  C1: Response time to AI user-agent (is the site responsive enough
      for crawler budget? <3s threshold)
  C2: robots.txt allows at least the major AI crawlers (not fully
      Disallow: / for ClaudeBot, GPTBot, PerplexityBot)
  C3: No aggressive rate-limiting detected (429 on repeated requests
      within 5 seconds)

Verdict bands:
  CRAWL-ACCESSIBLE = all 3 pass (site is reachable and crawler-friendly)
  CRAWL-PARTIAL    = C1 passes but C2 or C3 fails (reachable but restricted)
  CRAWL-BLOCKED    = C1 fails or both C2+C3 fail

Cost: $0 (HTTP GET only, 3-5 requests total).
"""

import argparse
import json
import sys
import time
from typing import Any
from urllib.parse import urlparse

import requests


USER_AGENT = (
    "AVR-citability/1.1 "
    "(Section-CrawlSignal audit; https://citability.dev; "
    "contact: chudi@chudi.dev)"
)

CLAUDE_UA = "ClaudeBot/1.0 (https://anthropic.com; bot)"

REQUEST_TIMEOUT_SEC = 10
RESPONSE_TIME_THRESHOLD_SEC = 3.0


def _site_root(url: str) -> str:
    if not url.startswith("http"):
        url = f"https://{url}"
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def check_response_time(url: str) -> dict[str, Any]:
    """C1: Is the site responsive to AI crawlers? (<3s threshold)"""
    result: dict[str, Any] = {
        "id": "crawl-response-time",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 8,
    }

    headers = {"User-Agent": CLAUDE_UA, "Accept": "text/html"}
    try:
        start = time.monotonic()
        resp = requests.get(
            url, headers=headers, timeout=REQUEST_TIMEOUT_SEC,
            allow_redirects=True, stream=True,
        )
        elapsed = time.monotonic() - start
        status = resp.status_code
        resp.close()

        result["passed"] = elapsed < RESPONSE_TIME_THRESHOLD_SEC and status < 400
        result["evidence"].append({
            "response_time_sec": round(elapsed, 3),
            "threshold_sec": RESPONSE_TIME_THRESHOLD_SEC,
            "status_code": status,
            "user_agent_sent": CLAUDE_UA,
            "within_threshold": elapsed < RESPONSE_TIME_THRESHOLD_SEC,
        })
    except requests.Timeout:
        result["evidence"].append({
            "error": "timeout",
            "threshold_sec": REQUEST_TIMEOUT_SEC,
            "note": "Site did not respond within timeout; crawlers will skip",
        })
    except requests.RequestException as e:
        result["evidence"].append({
            "error": f"{type(e).__name__}: {str(e)[:100]}",
        })

    return result


def check_robots_allows_crawling(site_root: str) -> dict[str, Any]:
    """C2: robots.txt does not fully block major AI crawlers."""
    result: dict[str, Any] = {
        "id": "crawl-robots-allows",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 9,
    }

    url = f"{site_root}/robots.txt"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
        if resp.status_code == 404:
            result["passed"] = True
            result["evidence"].append({
                "note": "No robots.txt found; all crawlers implicitly allowed",
                "url": url,
            })
            return result
        if resp.status_code >= 400:
            result["passed"] = True
            result["evidence"].append({
                "note": f"robots.txt returned {resp.status_code}; treated as no restrictions",
                "url": url,
            })
            return result

        body = resp.text
    except requests.RequestException as e:
        result["evidence"].append({"error": f"{type(e).__name__}", "url": url})
        return result

    major_crawlers = ["ClaudeBot", "GPTBot", "PerplexityBot"]
    fully_blocked = []

    lines = body.splitlines()
    current_agent = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith("user-agent:"):
            current_agent = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("disallow:") and current_agent:
            path = stripped.split(":", 1)[1].strip()
            if path == "/" and current_agent in major_crawlers:
                fully_blocked.append(current_agent)

    result["passed"] = len(fully_blocked) == 0
    result["evidence"].append({
        "major_crawlers_checked": major_crawlers,
        "fully_blocked": fully_blocked,
        "note": f"{len(fully_blocked)} of {len(major_crawlers)} major AI crawlers fully blocked" if fully_blocked else "No major AI crawlers fully blocked",
        "cloudflare_context": {
            "claudebot_crawl_ratio": "10,600:1 (declining 16.9%)",
            "gptbot_crawl_ratio": "1,000:1 (declining 11.9%)",
        },
    })
    return result


def check_rate_limiting(url: str) -> dict[str, Any]:
    """C3: No aggressive rate-limiting on 3 rapid requests."""
    result: dict[str, Any] = {
        "id": "crawl-rate-limit-check",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 6,
    }

    headers = {"User-Agent": CLAUDE_UA, "Accept": "text/html"}
    statuses = []
    got_429 = False

    for i in range(3):
        try:
            resp = requests.head(
                url, headers=headers, timeout=REQUEST_TIMEOUT_SEC,
                allow_redirects=True,
            )
            statuses.append(resp.status_code)
            if resp.status_code == 429:
                got_429 = True
                retry_after = resp.headers.get("Retry-After", "")
                result["evidence"].append({
                    "request_number": i + 1,
                    "status_code": 429,
                    "retry_after": retry_after,
                    "note": "Rate-limited; aggressive throttling detected for AI crawlers",
                })
                break
        except requests.RequestException:
            statuses.append(0)
        if i < 2:
            time.sleep(0.5)

    if not got_429:
        result["passed"] = True
        result["evidence"].append({
            "requests_sent": len(statuses),
            "status_codes": statuses,
            "rate_limited": False,
            "cloudflare_baseline": "0.8% of AI bot requests get 429 (Cloudflare Radar, May 2026)",
        })

    return result


def run_section_crawl_signal(url: str) -> dict[str, Any]:
    """Run the full §2.12 Crawl Signal section."""
    if not url.startswith("http"):
        url = f"https://{url}"
    site_root = _site_root(url)

    c1 = check_response_time(url)
    c2 = check_robots_allows_crawling(site_root)
    c3 = check_rate_limiting(url)

    checks = [c1, c2, c3]
    pass_count = sum(1 for c in checks if c["passed"])

    if pass_count == 3:
        verdict = "CRAWL-ACCESSIBLE"
    elif c1["passed"] and (not c2["passed"] or not c3["passed"]):
        verdict = "CRAWL-PARTIAL"
    else:
        verdict = "CRAWL-BLOCKED"

    recommendations = []
    if not c1["passed"]:
        ev = c1["evidence"][0] if c1["evidence"] else {}
        rt = ev.get("response_time_sec", "N/A")
        recommendations.append({
            "id": "rec-improve-response-time",
            "priority": 1,
            "action": (
                f"Response time ({rt}s) exceeds {RESPONSE_TIME_THRESHOLD_SEC}s threshold. "
                "Slow responses cause crawlers to deprioritize your site. "
                "Check server performance, CDN configuration, and page weight."
            ),
        })
    if not c2["passed"]:
        ev = c2["evidence"][0] if c2["evidence"] else {}
        blocked = ev.get("fully_blocked", [])
        recommendations.append({
            "id": "rec-unblock-crawlers",
            "priority": 1,
            "action": (
                f"robots.txt fully blocks {', '.join(blocked)}. "
                "Remove 'Disallow: /' for these crawlers if you want to be cited by their AI engines."
            ),
        })
    if not c3["passed"]:
        recommendations.append({
            "id": "rec-relax-rate-limits",
            "priority": 2,
            "action": (
                "Aggressive rate-limiting (429) detected for AI crawler user-agents. "
                "Consider whitelisting known AI bot user-agents or raising rate limits."
            ),
        })

    return {
        "section_id": "section_crawl_signal",
        "section_name": "Crawl Signal Check",
        "url_audited": url,
        "checks": checks,
        "section_verdict": verdict,
        "pass_count": pass_count,
        "total_checks": len(checks),
        "recommendations": recommendations,
        "spec_version": "AVR v1.1.0 §2.12 (Cloudflare Radar crawl-to-refer data, May 2026)",
        "cost_usd": 0.0,
        "label": "VERIFIABLE",
        "cloudflare_baseline": {
            "data_window": "May 17-23, 2026",
            "claudebot_crawl_ratio": "10,600:1 (declining 16.9%)",
            "gptbot_crawl_ratio": "1,000:1 (declining 11.9%)",
            "global_429_rate": "0.8%",
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="AVR §2.12 Crawl Signal Check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Cost: $0 (HTTP GET only).",
    )
    parser.add_argument("url", help="URL to audit")
    parser.add_argument("-o", "--output", help="Write JSON result to file")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.quiet:
        print(f"[section-crawl] auditing {args.url} ...", file=sys.stderr)
    result = run_section_crawl_signal(args.url)
    if not args.quiet:
        print(f"[section-crawl] verdict: {result['section_verdict']}", file=sys.stderr)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
    else:
        print(json.dumps(result, indent=2))

    code_map = {"CRAWL-ACCESSIBLE": 0, "CRAWL-PARTIAL": 1, "CRAWL-BLOCKED": 2}
    sys.exit(code_map.get(result["section_verdict"], 2))


if __name__ == "__main__":
    main()
