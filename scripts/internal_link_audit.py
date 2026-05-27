#!/usr/bin/env python3
"""
Internal Link Graph Audit

Crawls a site's internal links from its sitemap (or seed URL), builds an
adjacency graph, and reports: orphan pages, depth distribution, authority
concentration, anchor text patterns, and dead links.

Part of AVR v2.0 / /audit-converge L3 layer.
Cost: $0 (HTTP GET only).
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = "citability.dev/internal-link-audit/1.0"
TIMEOUT = 10

GENERIC_ANCHORS = {
    "click here", "here", "read more", "learn more", "this post", "this article",
    "this page", "link", "source", "more", "continue reading", "see more",
    "check it out", "go", "visit", "read", "details", "info",
}


def fetch(url: str) -> tuple[int, str]:
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA}, allow_redirects=True)
        return resp.status_code, resp.text if resp.ok else ""
    except Exception:
        return 0, ""


def get_sitemap_urls(origin: str) -> list[str]:
    status, body = fetch(f"{origin}/sitemap.xml")
    if status != 200 or not body:
        return []
    try:
        root = ET.fromstring(body)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [loc.text for loc in root.findall(".//sm:loc", ns) if loc.text]
        return [u for u in urls if urlparse(u).netloc == urlparse(origin).netloc]
    except ET.ParseError:
        return []


def extract_internal_links(html: str, page_url: str, origin: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            continue
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc != urlparse(origin).netloc:
            continue
        target = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if target.endswith("/") and len(target) > len(origin) + 1:
            target = target.rstrip("/")
        anchor_text = a.get_text(strip=True)[:100]
        rel = a.get("rel", [])
        nofollow = "nofollow" in rel if isinstance(rel, list) else "nofollow" in str(rel)
        links.append({"target": target, "anchor": anchor_text, "nofollow": nofollow})
    return links


def run_internal_link_audit(url: str, max_depth: int = 3, max_pages: int = 100) -> dict[str, Any]:
    parsed = urlparse(url if url.startswith("http") else f"https://{url}")
    origin = f"{parsed.scheme}://{parsed.netloc}"

    sitemap_urls = get_sitemap_urls(origin)
    seed_urls = sitemap_urls[:max_pages] if sitemap_urls else [origin]

    graph: dict[str, list[dict]] = defaultdict(list)
    inbound_count: dict[str, int] = defaultdict(int)
    page_data: dict[str, dict] = {}
    visited: set[str] = set()
    dead_links: list[dict] = []
    nofollow_internal: list[dict] = []
    crawl_queue: list[tuple[str, int]] = [(u, 0 if u == origin else 1) for u in seed_urls]

    while crawl_queue and len(visited) < max_pages:
        page_url, depth = crawl_queue.pop(0)
        normalized = page_url.rstrip("/") if page_url != origin + "/" else origin
        if normalized in visited or depth > max_depth:
            continue

        visited.add(normalized)
        status, html = fetch(page_url)

        if status == 0 or status >= 400:
            if normalized != origin:
                dead_links.append({"url": normalized, "status": status})
            continue

        links = extract_internal_links(html, page_url, origin)
        graph[normalized] = links

        soup = BeautifulSoup(html, "lxml")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        h1 = soup.find("h1")
        h1_text = h1.get_text(strip=True)[:100] if h1 else ""
        word_count = len(soup.get_text().split())

        page_data[normalized] = {
            "title": title, "h1": h1_text, "word_count": word_count,
            "depth": depth, "outbound_count": len(links),
        }

        for link in links:
            target = link["target"].rstrip("/")
            inbound_count[target] += 1
            if link["nofollow"]:
                nofollow_internal.append({"source": normalized, "target": target, "anchor": link["anchor"]})
            if target not in visited and depth + 1 <= max_depth:
                crawl_queue.append((target, depth + 1))

    all_known = set(page_data.keys())
    sitemap_set = set(u.rstrip("/") for u in sitemap_urls)
    orphans = [p for p in (sitemap_set | all_known) if inbound_count.get(p, 0) == 0 and p != origin]

    for p in page_data:
        page_data[p]["inbound_count"] = inbound_count.get(p, 0)

    total_links = sum(len(l) for l in graph.values())
    avg_links = total_links / max(1, len(graph))
    depths = [d["depth"] for d in page_data.values()]
    avg_depth = sum(depths) / max(1, len(depths))
    within_3 = sum(1 for d in depths if d <= 3) / max(1, len(depths)) * 100

    sorted_by_inbound = sorted(page_data.items(), key=lambda x: x[1].get("inbound_count", 0), reverse=True)
    total_inbound = sum(inbound_count.values())
    top5_inbound = sum(v["inbound_count"] for _, v in sorted_by_inbound[:5])
    authority_conc = top5_inbound / max(1, total_inbound) * 100

    anchor_div: dict[str, set] = defaultdict(set)
    for links in graph.values():
        for link in links:
            if link["anchor"]:
                anchor_div[link["target"].rstrip("/")].add(link["anchor"].lower())

    low_div = [{"page": t, "anchors": list(a), "inbound": inbound_count[t]}
               for t, a in anchor_div.items() if len(a) <= 1 and inbound_count.get(t, 0) >= 3]

    generic_anchor_pages = []
    for target, anchors in anchor_div.items():
        generic_count = sum(1 for a in anchors if a.lower().strip() in GENERIC_ANCHORS)
        total = len(anchors)
        if total > 0 and generic_count / total > 0.5:
            generic_anchor_pages.append({
                "page": target,
                "generic_anchors": [a for a in anchors if a.lower().strip() in GENERIC_ANCHORS],
                "good_anchors": [a for a in anchors if a.lower().strip() not in GENERIC_ANCHORS],
                "inbound": inbound_count.get(target, 0),
                "generic_ratio": round(generic_count / total, 2),
            })

    findings = {"critical": [], "high": [], "medium": [], "low": [], "info": []}
    for o in orphans[:20]:
        findings["critical"].append({"type": "ORPHAN", "page": o, "detail": "0 inbound internal links"})
    for p, d in page_data.items():
        if d["depth"] > 3:
            findings["high"].append({"type": "DEPTH", "page": p, "detail": f"depth {d['depth']}"})
    for dl in dead_links:
        findings["high"].append({"type": "DEAD-LINK", "page": dl["url"], "detail": f"HTTP {dl['status']}"})
    if authority_conc > 50:
        findings["medium"].append({"type": "AUTHORITY-CONCENTRATION", "detail": f"Top 5 = {authority_conc:.0f}%"})
    for item in low_div:
        findings["low"].append({"type": "ANCHOR-DIVERSITY", "page": item["page"],
                                "detail": f"All {item['inbound']} links use: {item['anchors'][0] if item['anchors'] else '(empty)'}"})
    for nf in nofollow_internal[:10]:
        findings["low"].append({"type": "NOFOLLOW-INTERNAL", "source": nf["source"],
                                "target": nf["target"], "detail": "rel=nofollow on internal link"})
    for item in generic_anchor_pages[:10]:
        findings["medium"].append({
            "type": "GENERIC-ANCHOR",
            "page": item["page"],
            "detail": f"{item['generic_ratio']*100:.0f}% generic anchors ({', '.join(item['generic_anchors'][:3])})"
        })

    checks_pass = sum([not orphans, within_3 >= 95, authority_conc <= 50, not dead_links, not nofollow_internal, not generic_anchor_pages])
    verdict = "LINKING-HEALTHY" if checks_pass >= 4 else "LINKING-PARTIAL" if checks_pass >= 2 else "LINKING-POOR"

    return {
        "section_id": "L3.1", "section_name": "Internal Linking Audit",
        "section_verdict": verdict, "pass_count": checks_pass, "total_checks": 6,
        "stats": {
            "pages_crawled": len(visited), "pages_in_sitemap": len(sitemap_urls),
            "total_internal_links": total_links, "avg_links_per_page": round(avg_links, 1),
            "avg_depth": round(avg_depth, 1), "pct_within_3_clicks": round(within_3, 1),
            "orphan_count": len(orphans), "dead_link_count": len(dead_links),
            "nofollow_internal_count": len(nofollow_internal),
            "authority_concentration_pct": round(authority_conc, 1),
        },
        "orphan_pages": orphans[:20], "dead_links": dead_links[:20],
        "top_pages_by_inbound": [{"url": u, "inbound": d["inbound_count"], "title": d.get("title", "")}
                                  for u, d in sorted_by_inbound[:10]],
        "low_anchor_diversity": low_div[:10], "nofollow_internal": nofollow_internal[:10],
        "generic_anchor_pages": generic_anchor_pages[:10],
        "findings": findings, "url_audited": url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Internal Link Graph Audit")
    parser.add_argument("url", help="Site root URL to audit")
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_internal_link_audit(args.url, max_depth=args.depth, max_pages=args.max_pages)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    s = result["stats"]
    f = result["findings"]
    print(f"\n{'='*55}")
    print(f"  INTERNAL LINKING AUDIT: {args.url}")
    print(f"{'='*55}")
    print(f"\n  Verdict: {result['section_verdict']} ({result['pass_count']}/{result['total_checks']})")
    print(f"  Pages crawled: {s['pages_crawled']} | Sitemap: {s['pages_in_sitemap']}")
    print(f"  Total links: {s['total_internal_links']} | Avg/page: {s['avg_links_per_page']}")
    print(f"  Avg depth: {s['avg_depth']} | Within 3 clicks: {s['pct_within_3_clicks']}%")
    print(f"  Orphans: {s['orphan_count']} | Dead: {s['dead_link_count']} | Authority top5: {s['authority_concentration_pct']}%")

    for sev in ["critical", "high", "medium", "low"]:
        if f[sev]:
            print(f"\n  {sev.upper()}:")
            for item in f[sev][:10]:
                print(f"    [{item['type']}] {item.get('page', '')} {item.get('detail', '')}")

    if result["top_pages_by_inbound"]:
        print(f"\n  TOP BY INBOUND:")
        for p in result["top_pages_by_inbound"][:5]:
            print(f"    {p['inbound']:3d} -> {p['url']}")


if __name__ == "__main__":
    main()
