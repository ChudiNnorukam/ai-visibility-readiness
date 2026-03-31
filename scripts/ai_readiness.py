# Copyright (c) 2026 Chudi Nnorukam. All rights reserved.
# Licensed under the AVR Source-Available License v1.0. See LICENSE file.
# https://citability.dev

#!/usr/bin/env python3
"""
AVR Section 2: AI Infrastructure Readiness Checks
Checks llms.txt, AI crawler access, structured data depth, content structure, semantic HTML.
"""

import json
import re
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


AI_CRAWLERS = {
    "GPTBot": "OpenAI (ChatGPT training + web browsing)",
    "ChatGPT-User": "OpenAI (ChatGPT real-time browsing)",
    "ClaudeBot": "Anthropic (Claude web search)",
    "PerplexityBot": "Perplexity (search index)",
    "Google-Extended": "Google (Gemini/AI Overviews training)",
    "CCBot": "Common Crawl (open dataset used by many AI systems)",
}


def check_llms_txt(url: str) -> dict:
    """Check 2.1: llms.txt Presence and Validity."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    result = {
        "check": "2.1_llms_txt",
        "tier": "VERIFIABLE",
        "details": {},
        "verdict": "FAIL",
    }

    try:
        resp = requests.get(f"{base}/llms.txt", timeout=10, headers={"User-Agent": "AVR-Auditor/1.0"})
        result["details"]["status_code"] = resp.status_code
        result["details"]["content_type"] = resp.headers.get("Content-Type", "")

        if resp.status_code == 200:
            content = resp.text.strip()
            lines = content.split("\n")
            result["details"]["line_count"] = len(lines)
            result["details"]["char_count"] = len(content)
            result["details"]["first_lines"] = lines[:5]

            has_content = len(content) > 50
            has_structure = len(lines) > 3

            if has_content and has_structure:
                result["verdict"] = "PASS"
            elif has_content:
                result["verdict"] = "PARTIAL"
            else:
                result["verdict"] = "FAIL"
        else:
            result["verdict"] = "FAIL"
            result["details"]["note"] = f"HTTP {resp.status_code}"

    except requests.RequestException as e:
        result["details"]["error"] = str(e)

    return result


def check_ai_crawler_access(url: str) -> dict:
    """Check 2.2: AI Crawler Access Directives."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    result = {
        "check": "2.2_ai_crawler_access",
        "tier": "VERIFIABLE",
        "crawlers": {},
        "verdict": "FAIL",
    }

    try:
        resp = requests.get(f"{base}/robots.txt", timeout=10)
        if resp.status_code != 200:
            result["details"] = {"error": f"robots.txt returned {resp.status_code}"}
            # No robots.txt means all crawlers allowed by default
            for crawler in AI_CRAWLERS:
                result["crawlers"][crawler] = {
                    "status": "allowed_by_default",
                    "operator": AI_CRAWLERS[crawler],
                }
            result["verdict"] = "PASS"
            return result

        robots_content = resp.text.lower()

        for crawler, operator in AI_CRAWLERS.items():
            crawler_lower = crawler.lower()
            wildcard_blocked = False
            specific_blocked = False
            explicitly_allowed = False

            # Check for explicit allow first
            for line in resp.text.split("\n"):
                stripped = line.strip().lower()
                if crawler_lower in stripped and "allow" in stripped and "disallow" not in stripped:
                    explicitly_allowed = True

            # Check for disallow (specific crawler or wildcard)
            in_block = False
            for line in resp.text.split("\n"):
                stripped = line.strip().lower()
                if stripped.startswith("user-agent:"):
                    agent = stripped.split(":", 1)[1].strip()
                    in_block = agent == crawler_lower or agent == "*"
                elif in_block and stripped.startswith("disallow:"):
                    path = stripped.split(":", 1)[1].strip()
                    if path == "/" or path == "/*":
                        if agent == crawler_lower:
                            specific_blocked = True
                        elif agent == "*":
                            wildcard_blocked = True

            # Specific block always wins. Wildcard block only if no explicit allow.
            if specific_blocked:
                status = "blocked"
            elif explicitly_allowed:
                status = "explicitly_allowed"
            elif wildcard_blocked:
                status = "blocked"
            else:
                status = "allowed_by_default"

            result["crawlers"][crawler] = {
                "status": status,
                "operator": operator,
            }

        allowed_count = sum(1 for c in result["crawlers"].values() if c["status"] != "blocked")
        total = len(result["crawlers"])

        if allowed_count == total:
            result["verdict"] = "PASS"
        elif allowed_count >= total / 2:
            result["verdict"] = "PARTIAL"
        else:
            result["verdict"] = "FAIL"

    except requests.RequestException as e:
        result["details"] = {"error": str(e)}

    return result


def check_structured_data_depth(url: str) -> dict:
    """Check 2.3: Structured Data Depth."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    result = {
        "check": "2.3_structured_data_depth",
        "tier": "VERIFIABLE",
        "details": {},
        "verdict": "FAIL",
    }

    # Get sitemap pages
    pages = []
    try:
        sitemap_resp = requests.get(f"{base}/sitemap.xml", timeout=10)
        if sitemap_resp.status_code == 200:
            page_urls = re.findall(r"<loc>(.*?)</loc>", sitemap_resp.text)
            pages = page_urls[:20]  # Sample up to 20 pages
    except requests.RequestException:
        pass

    if not pages:
        pages = [url]  # At minimum, check the provided URL

    schema_types_found = set()
    pages_with_schema = 0
    pages_checked = 0

    for page_url in pages:
        try:
            resp = requests.get(page_url, timeout=10, headers={"User-Agent": "AVR-Auditor/1.0"})
            pages_checked += 1
            soup = BeautifulSoup(resp.text, "lxml")
            ld_scripts = soup.find_all("script", type="application/ld+json")

            if ld_scripts:
                pages_with_schema += 1
                for script in ld_scripts:
                    try:
                        data = json.loads(script.string or "")
                        if isinstance(data, list):
                            for item in data:
                                if "@type" in item:
                                    schema_types_found.add(item["@type"])
                        elif isinstance(data, dict):
                            if "@type" in data:
                                schema_types_found.add(data["@type"])
                            # Check @graph
                            for item in data.get("@graph", []):
                                if "@type" in item:
                                    schema_types_found.add(item["@type"])
                    except (json.JSONDecodeError, AttributeError):
                        pass
        except requests.RequestException:
            pass

    coverage = pages_with_schema / pages_checked if pages_checked > 0 else 0
    rich_types = {"FAQPage", "HowTo", "Article", "BlogPosting", "Recipe", "Product", "Review"}
    has_rich_types = bool(schema_types_found & rich_types)

    result["details"] = {
        "pages_checked": pages_checked,
        "pages_with_schema": pages_with_schema,
        "coverage_pct": round(coverage * 100, 1),
        "schema_types": sorted(schema_types_found),
        "unique_type_count": len(schema_types_found),
        "has_rich_result_types": has_rich_types,
    }

    if coverage > 0.8 and len(schema_types_found) >= 3:
        result["verdict"] = "PASS"
    elif coverage > 0.5 or len(schema_types_found) >= 1:
        result["verdict"] = "PARTIAL"
    else:
        result["verdict"] = "FAIL"

    return result


def check_content_structure(url: str) -> dict:
    """Check 2.4: Content Structure Quality."""
    result = {
        "check": "2.4_content_structure",
        "tier": "VERIFIABLE",
        "details": {},
        "verdict": "FAIL",
    }

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "AVR-Auditor/1.0"})
        soup = BeautifulSoup(resp.text, "lxml")

        # Heading analysis
        headings = []
        for level in range(1, 7):
            for tag in soup.find_all(f"h{level}"):
                text = tag.get_text(strip=True)
                if text:
                    headings.append({"level": level, "text": text[:80]})

        h1_count = sum(1 for h in headings if h["level"] == 1)
        levels_used = sorted(set(h["level"] for h in headings))

        # Check hierarchy (no skipping)
        hierarchy_ok = True
        for i in range(len(levels_used) - 1):
            if levels_used[i + 1] - levels_used[i] > 1:
                hierarchy_ok = False
                break

        # Paragraph analysis
        paragraphs = soup.find_all("p")
        p_word_counts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text:
                p_word_counts.append(len(text.split()))

        avg_p_words = sum(p_word_counts) / len(p_word_counts) if p_word_counts else 0

        # FAQ detection
        has_faq = bool(soup.find_all("details")) or bool(
            re.search(r'<script[^>]*type="application/ld\+json"[^>]*>.*?"FAQPage"', resp.text, re.DOTALL)
        )

        result["details"] = {
            "h1_count": h1_count,
            "total_headings": len(headings),
            "heading_levels_used": levels_used,
            "hierarchy_clean": hierarchy_ok,
            "section_count": max(len(headings) - 1, 0),
            "paragraph_count": len(p_word_counts),
            "avg_paragraph_words": round(avg_p_words, 0),
            "has_faq_pattern": has_faq,
            "headings_sample": headings[:10],
        }

        single_h1 = h1_count == 1
        good_sections = len(headings) >= 4
        readable_paragraphs = avg_p_words < 150

        if single_h1 and hierarchy_ok and good_sections and readable_paragraphs:
            result["verdict"] = "PASS"
        elif good_sections:
            result["verdict"] = "PARTIAL"
        else:
            result["verdict"] = "FAIL"

    except requests.RequestException as e:
        result["error"] = str(e)

    return result


def check_content_ratio(url: str) -> dict:
    """Check 2.5: Machine-Readable Content Ratio."""
    result = {
        "check": "2.5_content_ratio",
        "tier": "VERIFIABLE",
        "details": {},
        "verdict": "FAIL",
    }

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "AVR-Auditor/1.0"})
        html = resp.text
        total_bytes = len(html)

        # Strip scripts, styles, tags
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        content_bytes = len(text)

        ratio = content_bytes / total_bytes if total_bytes > 0 else 0

        # Content-sufficient override: if raw text is large enough, low ratio
        # just means framework overhead (SSR hydration, CSS-in-JS), not thin content
        content_sufficient = content_bytes > 3000

        result["details"] = {
            "total_html_bytes": total_bytes,
            "text_content_bytes": content_bytes,
            "content_ratio_pct": round(ratio * 100, 1),
            "content_sufficient_override": content_sufficient,
        }

        if ratio > 0.25 and content_bytes > 1000:
            result["verdict"] = "PASS"
        elif content_sufficient:
            result["verdict"] = "PASS"
            result["details"]["note"] = "Low ratio due to framework overhead, but content volume is sufficient"
        elif ratio > 0.10 and content_bytes > 500:
            result["verdict"] = "PARTIAL"
        else:
            result["verdict"] = "FAIL"

    except requests.RequestException as e:
        result["error"] = str(e)

    return result


def check_semantic_html(url: str) -> dict:
    """Check 2.6: Semantic HTML and Accessibility."""
    result = {
        "check": "2.6_semantic_html",
        "tier": "VERIFIABLE",
        "details": {},
        "verdict": "FAIL",
    }

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "AVR-Auditor/1.0"})
        soup = BeautifulSoup(resp.text, "lxml")

        elements = {
            "article": len(soup.find_all("article")),
            "main": len(soup.find_all("main")),
            "nav": len(soup.find_all("nav")),
            "section": len(soup.find_all("section")),
            "aside": len(soup.find_all("aside")),
            "figure": len(soup.find_all("figure")),
            "time": len(soup.find_all("time")),
        }

        imgs = soup.find_all("img")
        imgs_with_alt = sum(1 for img in imgs if img.get("alt", "").strip())
        total_imgs = len(imgs)
        alt_coverage = imgs_with_alt / total_imgs if total_imgs > 0 else 1.0

        result["details"] = {
            "semantic_elements": elements,
            "images_total": total_imgs,
            "images_with_alt": imgs_with_alt,
            "alt_text_coverage_pct": round(alt_coverage * 100, 1),
        }

        has_content_element = elements["article"] > 0 or elements["main"] > 0
        has_nav = elements["nav"] > 0
        good_alt_coverage = alt_coverage >= 0.8

        if has_content_element and has_nav and good_alt_coverage:
            result["verdict"] = "PASS"
        elif has_content_element or good_alt_coverage:
            result["verdict"] = "PARTIAL"
        else:
            result["verdict"] = "FAIL"

    except requests.RequestException as e:
        result["error"] = str(e)

    return result


def run_ai_readiness(url: str) -> dict:
    """Run all AI Infrastructure Readiness checks for a URL."""
    results = {
        "section": "2_ai_infrastructure_readiness",
        "url": url,
        "checks": [],
        "section_verdict": "FAIL",
    }

    results["checks"].append(check_llms_txt(url))
    results["checks"].append(check_ai_crawler_access(url))
    results["checks"].append(check_structured_data_depth(url))
    results["checks"].append(check_content_structure(url))
    results["checks"].append(check_content_ratio(url))
    results["checks"].append(check_semantic_html(url))

    verdicts = [c["verdict"] for c in results["checks"]]
    if all(v == "PASS" for v in verdicts):
        results["section_verdict"] = "PASS"
    elif any(v == "FAIL" for v in verdicts):
        results["section_verdict"] = "FAIL" if verdicts.count("FAIL") > len(verdicts) / 2 else "PARTIAL"
    else:
        results["section_verdict"] = "PARTIAL"

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ai_readiness.py <URL>")
        sys.exit(1)

    target_url = sys.argv[1]
    if not target_url.startswith("http"):
        target_url = f"https://{target_url}"

    output = run_ai_readiness(target_url)
    print(json.dumps(output, indent=2))
