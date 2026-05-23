#!/usr/bin/env python3
"""
AVR §2.9 Markdown Content Negotiation Audit

Tests whether a site serves markdown when an AI agent sends
Accept: text/markdown. Cloudflare Radar (May 2026): <0.1% of content
returned to AI bots is markdown, yet markdown reduces payload to 7%
of HTML size (93% reduction).

Two checks:
  M1: Content-type negotiation support (does the server respond to
      Accept: text/markdown with actual markdown?)
  M2: Payload size comparison (markdown vs HTML response size delta)

Verdict bands:
  MARKDOWN-READY     = M1 pass (server returns markdown content)
  MARKDOWN-PARTIAL   = server returns non-HTML reduced content (e.g. plain text)
  MARKDOWN-NOT-READY = server ignores Accept header, returns HTML regardless

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
    "(Section-MarkdownNegotiation audit; https://citability.dev; "
    "contact: chudi@chudi.dev)"
)

REQUEST_TIMEOUT_SEC = 10


def _site_root(url: str) -> str:
    if not url.startswith("http"):
        url = f"https://{url}"
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _fetch_with_accept(url: str, accept: str) -> tuple[int | None, str, int, str]:
    """Fetch URL with a specific Accept header. Returns (status, content_type, body_length, body_preview)."""
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC, allow_redirects=True)
        ct = resp.headers.get("Content-Type", "")
        body = resp.text
        return resp.status_code, ct, len(resp.content), body[:500]
    except requests.RequestException as e:
        return None, f"error:{type(e).__name__}", 0, ""


def check_content_negotiation(url: str) -> dict[str, Any]:
    """Check M1: Does the server honor Accept: text/markdown?"""
    result: dict[str, Any] = {
        "id": "markdown-content-negotiation",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 7,
    }

    status, ct, size, preview = _fetch_with_accept(url, "text/markdown")
    if status is None:
        result["evidence"].append({"error": ct, "url": url})
        return result

    ct_lower = ct.lower()
    is_markdown = "text/markdown" in ct_lower or "text/x-markdown" in ct_lower
    is_plain = "text/plain" in ct_lower and not "text/html" in ct_lower

    looks_like_markdown = False
    if preview:
        md_signals = sum([
            preview.startswith("#"),
            "\n## " in preview,
            "\n- " in preview,
            "\n* " in preview,
            "```" in preview,
            "\n> " in preview,
        ])
        looks_like_markdown = md_signals >= 2

    result["passed"] = is_markdown or (is_plain and looks_like_markdown)
    result["evidence"].append({
        "accept_sent": "text/markdown",
        "status_code": status,
        "content_type_received": ct[:100],
        "response_size_bytes": size,
        "is_markdown_content_type": is_markdown,
        "is_plain_text": is_plain,
        "body_looks_like_markdown": looks_like_markdown,
        "body_preview": preview[:200],
    })
    return result


def check_payload_size_delta(url: str) -> dict[str, Any]:
    """Check M2: Compare markdown vs HTML response sizes."""
    result: dict[str, Any] = {
        "id": "markdown-payload-delta",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 6,
        "optional_signal": True,
    }

    _, _, html_size, _ = _fetch_with_accept(url, "text/html")
    _, md_ct, md_size, _ = _fetch_with_accept(url, "text/markdown")

    if html_size == 0:
        result["evidence"].append({"error": "html_fetch_failed", "url": url})
        return result

    md_ct_lower = md_ct.lower()
    server_returned_different = (
        "text/markdown" in md_ct_lower
        or "text/plain" in md_ct_lower
    ) and "text/html" not in md_ct_lower

    if server_returned_different and md_size > 0:
        ratio = md_size / html_size if html_size > 0 else 1.0
        savings_pct = round((1 - ratio) * 100, 1)
        result["passed"] = savings_pct > 20
        result["evidence"].append({
            "html_size_bytes": html_size,
            "markdown_size_bytes": md_size,
            "size_ratio": round(ratio, 3),
            "savings_pct": savings_pct,
            "cloudflare_benchmark": "Cloudflare reports median 93% reduction (to 7% of HTML size)",
        })
    else:
        result["evidence"].append({
            "html_size_bytes": html_size,
            "markdown_response_content_type": md_ct[:100],
            "note": "Server returned same content type for both Accept headers; no negotiation detected",
            "savings_pct": 0,
        })

    return result


def run_section_markdown_negotiation(url: str) -> dict[str, Any]:
    """Run the full §2.9 Markdown Negotiation section."""
    if not url.startswith("http"):
        url = f"https://{url}"

    m1 = check_content_negotiation(url)
    m2 = check_payload_size_delta(url)

    checks = [m1, m2]
    pass_count = sum(1 for c in checks if c["passed"])

    if m1["passed"]:
        verdict = "MARKDOWN-READY"
    elif m2.get("evidence") and m2["evidence"][0].get("savings_pct", 0) > 0:
        verdict = "MARKDOWN-PARTIAL"
    else:
        verdict = "MARKDOWN-NOT-READY"

    recommendations = []
    if not m1["passed"]:
        recommendations.append({
            "id": "rec-implement-markdown-negotiation",
            "priority": 1,
            "action": (
                "Implement content-type negotiation to serve markdown when AI agents "
                "send Accept: text/markdown. This reduces payload to ~7% of HTML size "
                "(93% reduction, Cloudflare Radar May 2026). Only 5.3% of top domains "
                "support this; adoption is <0.1% of actual responses."
            ),
        })

    return {
        "section_id": "section_markdown_negotiation",
        "section_name": "Markdown Content Negotiation",
        "url_audited": url,
        "checks": checks,
        "section_verdict": verdict,
        "pass_count": pass_count,
        "total_checks": len(checks),
        "recommendations": recommendations,
        "spec_version": "AVR v1.1.0 §2.9 (Cloudflare Radar markdown savings data, May 2026)",
        "cost_usd": 0.0,
        "label": "VERIFIABLE",
        "cloudflare_baseline": {
            "data_window": "May 17-23, 2026",
            "markdown_adoption": "5.3% capability, <0.1% actual responses",
            "median_savings": "93% payload reduction (to 7% of HTML)",
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="AVR §2.9 Markdown Content Negotiation Audit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Cost: $0 (HTTP GET only).",
    )
    parser.add_argument("url", help="URL to audit")
    parser.add_argument("-o", "--output", help="Write JSON result to file")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.quiet:
        print(f"[section-markdown] auditing {args.url} ...", file=sys.stderr)
    result = run_section_markdown_negotiation(args.url)
    if not args.quiet:
        print(f"[section-markdown] verdict: {result['section_verdict']}", file=sys.stderr)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
    else:
        print(json.dumps(result, indent=2))

    code_map = {"MARKDOWN-READY": 0, "MARKDOWN-PARTIAL": 1, "MARKDOWN-NOT-READY": 2}
    sys.exit(code_map.get(result["section_verdict"], 2))


if __name__ == "__main__":
    main()
