#!/usr/bin/env python3
"""
AVR Section 1: SEO Foundation Checks
Runs Lighthouse, checks robots.txt, sitemap, HTTPS, content indexability.
"""

import json
import re
import subprocess
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


def check_core_web_vitals(url: str) -> dict:
    """Check 1.1: Core Web Vitals via Lighthouse CLI."""
    result = {
        "check": "1.1_core_web_vitals",
        "tier": "VERIFIABLE",
        "metrics": {},
        "verdict": "FAIL",
    }

    try:
        proc = subprocess.run(
            [
                "lighthouse", url,
                "--output", "json",
                "--only-categories=performance",
                "--chrome-flags=--headless --no-sandbox",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if proc.returncode != 0:
            result["error"] = f"Lighthouse exited with code {proc.returncode}"
            return result

        data = json.loads(proc.stdout)
        audits = data.get("audits", {})

        lcp = audits.get("largest-contentful-paint", {}).get("numericValue", 0) / 1000
        cls_val = audits.get("cumulative-layout-shift", {}).get("numericValue", 0)
        perf_score = data.get("categories", {}).get("performance", {}).get("score", 0)

        # INP is not directly in Lighthouse lab data, use TBT as proxy
        tbt = audits.get("total-blocking-time", {}).get("numericValue", 0)

        result["metrics"] = {
            "lcp_seconds": round(lcp, 2),
            "cls": round(cls_val, 3),
            "tbt_ms": round(tbt, 0),
            "performance_score": round(perf_score * 100, 0),
        }

        lcp_ok = lcp <= 2.5
        cls_ok = cls_val <= 0.1
        tbt_ok = tbt <= 200

        if lcp_ok and cls_ok and tbt_ok:
            result["verdict"] = "PASS"
        elif lcp <= 4.0 and cls_val <= 0.25 and tbt <= 600:
            result["verdict"] = "PARTIAL"
        else:
            result["verdict"] = "FAIL"

    except subprocess.TimeoutExpired:
        result["error"] = "Lighthouse timed out after 120s"
    except FileNotFoundError:
        result["error"] = "Lighthouse CLI not installed"
    except (json.JSONDecodeError, KeyError) as e:
        result["error"] = f"Failed to parse Lighthouse output: {e}"

    return result


def check_technical_crawlability(url: str) -> dict:
    """Check 1.2: Technical Crawlability."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    result = {
        "check": "1.2_technical_crawlability",
        "tier": "VERIFIABLE",
        "checks": {},
        "verdict": "FAIL",
    }

    # Check robots.txt
    try:
        resp = requests.get(f"{base}/robots.txt", timeout=10)
        result["checks"]["robots_txt"] = {
            "status": resp.status_code,
            "exists": resp.status_code == 200,
            "size_bytes": len(resp.content),
        }
    except requests.RequestException as e:
        result["checks"]["robots_txt"] = {"exists": False, "error": str(e)}

    # Check sitemap
    try:
        resp = requests.get(f"{base}/sitemap.xml", timeout=10)
        result["checks"]["sitemap"] = {
            "status": resp.status_code,
            "exists": resp.status_code == 200,
            "size_bytes": len(resp.content) if resp.status_code == 200 else 0,
        }
    except requests.RequestException as e:
        result["checks"]["sitemap"] = {"exists": False, "error": str(e)}

    # Check HTTPS
    if parsed.scheme == "https":
        result["checks"]["https"] = {"enforced": True}
        # Check if HTTP redirects to HTTPS
        try:
            http_url = f"http://{parsed.netloc}"
            resp = requests.get(http_url, timeout=10, allow_redirects=False)
            redirects_to_https = (
                resp.status_code in (301, 302, 307, 308)
                and "https" in resp.headers.get("Location", "")
            )
            result["checks"]["https"]["http_redirects"] = redirects_to_https
        except requests.RequestException:
            result["checks"]["https"]["http_redirects"] = "unknown"
    else:
        result["checks"]["https"] = {"enforced": False}

    # Check if important pages are blocked
    robots_ok = result["checks"].get("robots_txt", {}).get("exists", False)
    sitemap_ok = result["checks"].get("sitemap", {}).get("exists", False)
    https_ok = result["checks"].get("https", {}).get("enforced", False)

    passes = sum([robots_ok, sitemap_ok, https_ok])
    if passes >= 3:
        result["verdict"] = "PASS"
    elif https_ok and passes >= 2:
        result["verdict"] = "PARTIAL"
    else:
        result["verdict"] = "FAIL"

    return result


def check_schema_markup(url: str) -> dict:
    """Check 1.3: Schema Markup Validation."""
    result = {
        "check": "1.3_schema_markup",
        "tier": "VERIFIABLE",
        "schemas": [],
        "verdict": "FAIL",
    }

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "AVR-Auditor/1.0"})
        soup = BeautifulSoup(resp.text, "lxml")
        ld_scripts = soup.find_all("script", type="application/ld+json")

        for script in ld_scripts:
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    for item in data:
                        schema_type = item.get("@type", "Unknown")
                        result["schemas"].append({
                            "type": schema_type,
                            "valid_json": True,
                            "has_name": "name" in item,
                            "has_description": "description" in item,
                        })
                else:
                    schema_type = data.get("@type", "Unknown")
                    result["schemas"].append({
                        "type": schema_type,
                        "valid_json": True,
                        "has_name": "name" in data,
                        "has_description": "description" in data,
                    })
            except json.JSONDecodeError:
                result["schemas"].append({"valid_json": False, "raw": script.string[:100] if script.string else ""})

        valid_schemas = [s for s in result["schemas"] if s.get("valid_json")]
        if len(valid_schemas) >= 1 and all(s.get("has_name") for s in valid_schemas):
            result["verdict"] = "PASS"
        elif len(valid_schemas) >= 1:
            result["verdict"] = "PARTIAL"
        else:
            result["verdict"] = "FAIL"

    except requests.RequestException as e:
        result["error"] = str(e)

    return result


def check_page_speed(url: str) -> dict:
    """Check 1.5: Page Speed and Resource Efficiency (uses data from Lighthouse)."""
    result = {
        "check": "1.5_page_speed",
        "tier": "VERIFIABLE",
        "metrics": {},
        "verdict": "FAIL",
    }

    try:
        proc = subprocess.run(
            [
                "lighthouse", url,
                "--output", "json",
                "--only-categories=performance",
                "--chrome-flags=--headless --no-sandbox",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if proc.returncode != 0:
            result["error"] = f"Lighthouse exited with code {proc.returncode}"
            return result

        data = json.loads(proc.stdout)
        audits = data.get("audits", {})
        perf_score = data.get("categories", {}).get("performance", {}).get("score", 0) * 100

        tti = audits.get("interactive", {}).get("numericValue", 0) / 1000
        total_weight = audits.get("total-byte-weight", {}).get("numericValue", 0)
        request_count = audits.get("network-requests", {}).get("details", {}).get("items", [])

        result["metrics"] = {
            "performance_score": round(perf_score, 0),
            "time_to_interactive_s": round(tti, 2),
            "total_weight_kb": round(total_weight / 1024, 0),
            "request_count": len(request_count),
        }

        if perf_score >= 90:
            result["verdict"] = "PASS"
        elif perf_score >= 50:
            result["verdict"] = "PARTIAL"
        else:
            result["verdict"] = "FAIL"

    except subprocess.TimeoutExpired:
        result["error"] = "Lighthouse timed out"
    except FileNotFoundError:
        result["error"] = "Lighthouse CLI not installed"
    except (json.JSONDecodeError, KeyError) as e:
        result["error"] = f"Parse error: {e}"

    return result


def check_content_indexability(url: str) -> dict:
    """Check 1.6: Content Indexability."""
    result = {
        "check": "1.6_content_indexability",
        "tier": "VERIFIABLE",
        "checks": {},
        "verdict": "FAIL",
    }

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "AVR-Auditor/1.0"})
        html = resp.text
        soup = BeautifulSoup(html, "lxml")

        # Visible text content
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text_len = len(text)

        # Meta robots
        meta_robots = soup.find("meta", attrs={"name": re.compile(r"robots", re.I)})
        robots_content = meta_robots.get("content", "").lower() if meta_robots else ""
        has_noindex = "noindex" in robots_content

        # Canonical
        canonical = soup.find("link", rel="canonical")
        canonical_href = canonical.get("href", "") if canonical else ""

        # Paragraph count
        paragraphs = soup.find_all("p")
        p_count = len(paragraphs)

        result["checks"] = {
            "text_length_chars": text_len,
            "has_substantial_content": text_len > 500,
            "paragraph_count": p_count,
            "has_noindex": has_noindex,
            "canonical_present": bool(canonical_href),
            "canonical_href": canonical_href,
        }

        if text_len > 500 and not has_noindex and canonical_href:
            result["verdict"] = "PASS"
        elif has_noindex:
            result["verdict"] = "FAIL"
        elif text_len > 500:
            result["verdict"] = "PARTIAL"
        else:
            result["verdict"] = "FAIL"

    except requests.RequestException as e:
        result["error"] = str(e)

    return result


def run_seo_foundation(url: str, skip_lighthouse: bool = False) -> dict:
    """Run all SEO Foundation checks for a URL."""
    results = {
        "section": "1_seo_foundation",
        "url": url,
        "checks": [],
        "section_verdict": "FAIL",
    }

    if skip_lighthouse:
        results["checks"].append({
            "check": "1.1_core_web_vitals",
            "tier": "VERIFIABLE",
            "verdict": "SKIPPED",
            "note": "Lighthouse skipped (--skip-lighthouse flag)",
        })
        results["checks"].append({
            "check": "1.5_page_speed",
            "tier": "VERIFIABLE",
            "verdict": "SKIPPED",
            "note": "Lighthouse skipped (--skip-lighthouse flag)",
        })
    else:
        results["checks"].append(check_core_web_vitals(url))
        # Skip separate page_speed check since CWV already runs Lighthouse
        # Merge page speed into CWV results to avoid double Lighthouse run
        results["checks"].append({
            "check": "1.5_page_speed",
            "tier": "VERIFIABLE",
            "verdict": results["checks"][0].get("verdict", "FAIL"),
            "note": "Derived from Check 1.1 Lighthouse run",
            "metrics": results["checks"][0].get("metrics", {}),
        })

    results["checks"].append(check_technical_crawlability(url))
    results["checks"].append(check_schema_markup(url))
    results["checks"].append(check_content_indexability(url))

    # Compute section verdict
    verdicts = [c["verdict"] for c in results["checks"] if c["verdict"] != "SKIPPED"]
    if all(v == "PASS" for v in verdicts):
        results["section_verdict"] = "PASS"
    elif any(v == "FAIL" for v in verdicts):
        results["section_verdict"] = "FAIL"
    else:
        results["section_verdict"] = "PARTIAL"

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python seo_foundation.py <URL> [--skip-lighthouse]")
        sys.exit(1)

    target_url = sys.argv[1]
    skip_lh = "--skip-lighthouse" in sys.argv

    if not target_url.startswith("http"):
        target_url = f"https://{target_url}"

    output = run_seo_foundation(target_url, skip_lighthouse=skip_lh)
    print(json.dumps(output, indent=2))
