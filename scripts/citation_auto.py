#!/usr/bin/env python3
from __future__ import annotations
"""
AVR Automated Citation Testing

Queries AI search platforms (OpenAI, Perplexity, Anthropic, Google Gemini)
with real search queries and checks whether a target domain appears in their
cited sources.

This replaces the manual Section 3 process. Results are still labeled
[BEST-EFFORT] because AI responses vary by session, but the data is real
citation data, not speculation.

Setup:
  1. Copy .env.example to .env and add your API keys
  2. pip install openai anthropic google-genai requests
  3. python citation_auto.py test https://chudi.dev --topics "Claude Code hooks" "AI visibility"

Cost per audit (~80 queries with Gemini added):
  OpenAI (gpt-4.1 + web search)
  Perplexity (sonar)
  Anthropic (haiku + web search)
  Gemini (2.5-flash + grounding)
"""

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Semaphore

# Live calls run concurrently ACROSS platforms with a per-platform cap that
# protects each provider's rate limit. Metric-invariant: each (query, platform)
# citation result is computed purely from that call, and compute_results sums
# are order-independent. Set AVR_PER_PLATFORM_CONCURRENCY=1 to force serial.
# (Was fully serial; parallelized 2026-06-08 to fit the audit timeout budget.)
PER_PLATFORM_CONCURRENCY = max(1, int(os.environ.get("AVR_PER_PLATFORM_CONCURRENCY", "4")))

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            if value and not os.environ.get(key.strip()):
                os.environ[key.strip()] = value.strip()


def _check_keys() -> dict:
    """Check which API keys are available."""
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
    }


def _domain_match(target_domain: str, url: str | None) -> bool:
    """Match target_domain against url's hostname, tolerating www. variants.

    Compares HOSTNAMES only — substring-matching the raw URL produces false
    positives like 'https://ipaddress.com/website/en.wikipedia.org' matching
    'en.wikipedia.org' via the path. Hostname-only match avoids that.
    """
    if not url:
        return False
    from urllib.parse import urlparse
    target = target_domain.replace("https://", "").replace("http://", "").rstrip("/").lower()
    # Strip any path component if the operator passed a full URL as target
    target_host = target.split("/", 1)[0]
    target_no_www = target_host[4:] if target_host.startswith("www.") else target_host

    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        url_host = (parsed.hostname or "").lower()
    except Exception:
        return False
    if not url_host:
        return False
    url_host_no_www = url_host[4:] if url_host.startswith("www.") else url_host

    # Match if hostnames are equal (with/without www) or one is a subdomain of the other's apex
    if url_host == target_host or url_host_no_www == target_no_www:
        return True
    # Subdomain match: news.freecodecamp.org should match freecodecamp.org if target is the apex
    if url_host_no_www.endswith("." + target_no_www) or target_no_www.endswith("." + url_host_no_www):
        return True
    return False


def query_openai(query: str, target_domain: str) -> dict:
    """Query OpenAI with FORCED web_search and check for target domain citations.

    Uses the Responses API with web_search_preview tool, gpt-4.1 (mini variants
    do not reliably emit url_citation annotations even when search runs).
    Forces tool invocation via tool_choice — without it the model answers from
    training data and emits zero citations regardless of query.
    Returns: {platform, query, status, cited_urls, response_snippet}
    """
    try:
        from openai import OpenAI
        # 90s per-call timeout — without it, OpenAI's web_search backend can
        # hang indefinitely (witnessed: 2.5h hang on a single call before
        # this fix). Caught hangs surface as exceptions → trigger retry.
        client = OpenAI(timeout=90.0)

        # Without the system instruction, gpt-4.1 emits ~1 annotation per query
        # even with forced web_search; WITH the instruction, it emits 10-13.
        # Verified via diagnostic on 2026-04-29 — see docs note in this file's history.
        # temperature=0 per ai-citation-measurement-methodology codex §Step 4
        # (reproducibility requirement).
        response = client.responses.create(
            model="gpt-4.1",
            temperature=0,
            tools=[{"type": "web_search_preview"}],
            tool_choice={"type": "web_search_preview"},
            input=[
                {"role": "system", "content": "When answering, search the web and cite multiple authoritative sources inline. Always include url_citation annotations for any specific claim drawn from a search result."},
                {"role": "user", "content": query},
            ],
        )

        cited_urls: list[str] = []
        response_text = ""

        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        response_text = content.text
                        for ann in (getattr(content, "annotations", None) or []):
                            ann_d = ann.model_dump() if hasattr(ann, "model_dump") else dict(ann)
                            url = ann_d.get("url") or (ann_d.get("url_citation") or {}).get("url")
                            if url:
                                cited_urls.append(url)

        # Dedupe while preserving order
        seen = set()
        cited_urls = [u for u in cited_urls if not (u in seen or seen.add(u))]

        cited = any(_domain_match(target_domain, u) for u in cited_urls)

        return {
            "platform": "ChatGPT",
            "query": query,
            "status": "CITED" if cited else "NOT_CITED",
            "cited_urls": cited_urls[:10],
            "response_snippet": response_text[:300],
        }

    except Exception as e:
        return {
            "platform": "ChatGPT",
            "query": query,
            "status": "ERROR",
            "error": str(e),
        }


def query_perplexity(query: str, target_domain: str) -> dict:
    """Query Perplexity search API and check for target domain citations.

    Uses the sonar model which includes web search with citations.
    Returns: {platform, query, status, cited_urls, response_snippet}
    """
    try:
        import requests as req

        api_key = os.environ.get("PERPLEXITY_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "sonar",
            "temperature": 0,
            "messages": [
                {"role": "user", "content": query}
            ],
        }

        resp = req.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract citations: prefer the newer 'search_results' (each has url+title),
        # fall back to legacy 'citations' (list of URL strings)
        cited_urls: list[str] = []
        for sr in (data.get("search_results") or []):
            if isinstance(sr, dict) and sr.get("url"):
                cited_urls.append(sr["url"])
        if not cited_urls:
            cited_urls = data.get("citations", []) or []

        response_text = ""
        if data.get("choices"):
            response_text = data["choices"][0].get("message", {}).get("content", "")

        cited = any(_domain_match(target_domain, u) for u in cited_urls)

        return {
            "platform": "Perplexity",
            "query": query,
            "status": "CITED" if cited else "NOT_CITED",
            "cited_urls": cited_urls[:10],
            "response_snippet": response_text[:300],
        }

    except Exception as e:
        return {
            "platform": "Perplexity",
            "query": query,
            "status": "ERROR",
            "error": str(e),
        }


def query_anthropic(query: str, target_domain: str) -> dict:
    """Query Anthropic Claude with FORCED web_search and check for citations.

    Uses Messages API with web_search_20250305 tool, forced via tool_choice
    (without forcing, Claude rarely invokes the tool for general-knowledge
    queries and emits zero citations).

    Extracts URLs from TWO surfaces:
      1. text-block .citations[] arrays — what the model ACTUALLY cited inline
         (the URLs a user would see as clickable footnotes)
      2. web_search_tool_result blocks — what the model SAW from search
         (broader; includes URLs the model considered but didn't cite)
    A target appearing in either qualifies as CITED. The two are emitted
    separately in the result so downstream analysis can distinguish.
    """
    try:
        from anthropic import Anthropic
        client = Anthropic(timeout=90.0)

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            temperature=0,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            tool_choice={"type": "tool", "name": "web_search"},
            messages=[{"role": "user", "content": query}],
        )

        text_cited_urls: list[str] = []      # URLs the model explicitly cited inline
        search_result_urls: list[str] = []   # URLs from search results (saw but may not have cited)
        response_text = ""

        for block in response.content:
            if block.type == "text":
                response_text += block.text
                for cit in (getattr(block, "citations", None) or []):
                    cit_d = cit.model_dump() if hasattr(cit, "model_dump") else dict(cit)
                    url = cit_d.get("url")
                    if url:
                        text_cited_urls.append(url)
            elif block.type == "web_search_tool_result":
                for result in (getattr(block, "content", None) or []):
                    res_d = result.model_dump() if hasattr(result, "model_dump") else dict(result)
                    url = res_d.get("url") or getattr(result, "url", None)
                    if url:
                        search_result_urls.append(url)

        # Dedupe each
        def _dedupe(lst):
            seen = set()
            return [u for u in lst if not (u in seen or seen.add(u))]
        text_cited_urls = _dedupe(text_cited_urls)
        search_result_urls = _dedupe(search_result_urls)

        # All cited URLs (union, dedup, text-cited first)
        cited_urls = _dedupe(text_cited_urls + search_result_urls)

        cited_inline = any(_domain_match(target_domain, u) for u in text_cited_urls)
        cited_in_search = any(_domain_match(target_domain, u) for u in search_result_urls)
        cited = cited_inline or cited_in_search

        return {
            "platform": "Claude",
            "query": query,
            "status": "CITED" if cited else "NOT_CITED",
            "cited_urls": cited_urls[:10],
            "cited_inline": cited_inline,           # in text-block citations (sharper signal)
            "cited_in_search": cited_in_search,     # appeared in search results
            "response_snippet": response_text[:300],
        }

    except Exception as e:
        return {
            "platform": "Claude",
            "query": query,
            "status": "ERROR",
            "error": str(e),
        }


def query_gemini(query: str, target_domain: str) -> dict:
    """Query Google Gemini with Google Search grounding and check for citations.

    Uses gemini-2.5-flash with the google_search built-in tool. Citations come
    back via response.candidates[0].grounding_metadata.grounding_chunks, each
    chunk's .web.uri is a source URL the model grounded on.

    SDK reads GEMINI_API_KEY (or GOOGLE_API_KEY) from env automatically.
    Returns: {platform, query, status, cited_urls, response_snippet}
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client()

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=query,
            config=types.GenerateContentConfig(
                temperature=0,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        cited_urls: list[str] = []
        response_text = response.text or ""

        candidates = getattr(response, "candidates", None) or []
        if candidates:
            metadata = getattr(candidates[0], "grounding_metadata", None)
            if metadata:
                chunks = getattr(metadata, "grounding_chunks", None) or []
                for chunk in chunks:
                    web = getattr(chunk, "web", None)
                    if web and getattr(web, "uri", None):
                        cited_urls.append(web.uri)

        # Dedupe while preserving order
        seen = set()
        cited_urls = [u for u in cited_urls if not (u in seen or seen.add(u))]

        cited = any(_domain_match(target_domain, u) for u in cited_urls)

        return {
            "platform": "Gemini",
            "query": query,
            "status": "CITED" if cited else "NOT_CITED",
            "cited_urls": cited_urls[:10],
            "response_snippet": response_text[:300],
        }

    except Exception as e:
        return {
            "platform": "Gemini",
            "query": query,
            "status": "ERROR",
            "error": str(e),
        }


PLATFORM_FUNCTIONS = {
    "openai": query_openai,
    "perplexity": query_perplexity,
    "anthropic": query_anthropic,
    "gemini": query_gemini,
}

PLATFORM_NAMES = {
    "openai": "ChatGPT",
    "perplexity": "Perplexity",
    "anthropic": "Claude",
    "gemini": "Gemini",
}


def _derive_brand_from_domain(domain: str) -> str:
    """Strip TLD + leading 'www.' to get a brand-name approximation.

    Used only when the operator does NOT pass --brand. Naive but covers the
    common cases (example.com → 'example', news.foo.io → 'news.foo').
    """
    host = domain.replace("www.", "", 1) if domain.startswith("www.") else domain
    # Drop the rightmost label (TLD)
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[:-1])
    return host


def generate_queries(
    domain: str,
    topics: list[str] | None = None,
    brand: str | None = None,
    vertical: str | None = None,
    vertical_ctx: dict | None = None,
) -> list[dict]:
    """Generate 20 test queries for citation testing.

    If `vertical` is set (e.g., "local-healthcare", "saas-tool", "personal-brand"),
    delegates to verticals.py:get_vertical(vertical).query_template_builder(ctx)
    for vertical-aware templates instead of the generic ones below.

    Generic brand templates ask about the BRAND BY NAME, not by domain — querying
    'what is example.com' triggers domain-lookup search results (ipaddress.com,
    scamminder.com, etc.) instead of citations to the actual brand. Verified
    via 2026-04-29 calibration on Wikipedia.

    Topic templates use natural-English phrasings so engines treat them as
    real user queries rather than generated test queries.
    """
    brand_name = brand or _derive_brand_from_domain(domain)

    # Vertical-aware path
    if vertical:
        try:
            from verticals import get_vertical
            v = get_vertical(vertical)
            ctx = dict(vertical_ctx or {})
            ctx.setdefault("brand", brand_name)
            queries = v.query_template_builder(ctx)
            if queries:
                return queries
            # Fall through to generic if vertical's builder returned empty
            # (tech-publisher uses generic templates by design)
        except Exception as e:
            print(f"  [warn] vertical '{vertical}' failed ({e}); using generic templates")

    queries = []

    # 5 brand queries — ask about the brand by NAME, not by domain
    queries.extend([
        {"id": 1, "category": "brand", "query": f"What is {brand_name} and what does it do?"},
        {"id": 2, "category": "brand", "query": f"Who runs {brand_name}?"},
        {"id": 3, "category": "brand", "query": f"Tell me about {brand_name} and its main offerings."},
        {"id": 4, "category": "brand", "query": f"What is {brand_name} known for?"},
        {"id": 5, "category": "brand", "query": f"Is {brand_name} a reliable source?"},
    ])

    if topics:
        for i, topic in enumerate(topics[:5]):
            queries.append({"id": 6 + i, "category": "topic_authority", "query": f"What are the most authoritative sources for {topic}?"})
        for i, topic in enumerate(topics[:5]):
            queries.append({"id": 11 + i, "category": "long_tail", "query": f"How do I get started learning {topic} in 2026?"})
        # Competitor category: head-to-head comparison query (NOT "best resources" —
        # that's a tutorial-shape query that lives in long_tail. Renamed semantically
        # to actually test competitor positioning per 2026-04-30 plan stream A4.)
        for i, topic in enumerate(topics[:5]):
            queries.append({
                "id": 16 + i,
                "category": "competitor",
                "query": f"How does {brand_name} compare to other resources for {topic}?",
            })
    else:
        for i in range(15):
            queries.append({"id": 6 + i, "category": "placeholder", "query": f"[topic query {i+1} - provide --topics]"})

    return queries


def compute_results(results: list[dict]) -> dict:
    """Compute citation rate and confidence from test results."""
    total = len(results)
    errors = sum(1 for r in results if r["status"] == "ERROR")
    testable = total - errors
    cited = sum(1 for r in results if r["status"] == "CITED")

    rate = cited / testable if testable > 0 else 0

    # Wilson score 95% CI
    if testable > 0:
        z = 1.96
        p = rate
        n = testable
        denom = 1 + z**2 / n
        center = (p + z**2 / (2 * n)) / denom
        spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
        ci_low = max(0, center - spread)
        ci_high = min(1, center + spread)
    else:
        ci_low = ci_high = 0

    # Confidence label
    if testable >= 600:
        confidence = "HIGH"
    elif testable >= 180:
        confidence = "MODERATE"
    else:
        confidence = "LOW"

    # Per-platform breakdown
    platforms = {}
    for r in results:
        p = r["platform"]
        if p not in platforms:
            platforms[p] = {"cited": 0, "not_cited": 0, "error": 0, "total": 0}
        platforms[p]["total"] += 1
        if r["status"] == "CITED":
            platforms[p]["cited"] += 1
        elif r["status"] == "NOT_CITED":
            platforms[p]["not_cited"] += 1
        elif r["status"] == "ERROR":
            platforms[p]["error"] += 1

    for pdata in platforms.values():
        testable_p = pdata["total"] - pdata["error"]
        pdata["citation_rate_pct"] = round(pdata["cited"] / testable_p * 100, 1) if testable_p > 0 else 0

    # Per-category breakdown — load-bearing because the overall rate averages
    # incompatible query types (brand vs competitor vs tutorial-shape). Per-category
    # is the honest metric to compare across sites of different shape (e.g.,
    # Wikipedia loses tutorial-shape queries; freeCodeCamp loses comparison-shape).
    categories = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"cited": 0, "not_cited": 0, "error": 0, "total": 0}
        categories[cat]["total"] += 1
        if r["status"] == "CITED":
            categories[cat]["cited"] += 1
        elif r["status"] == "NOT_CITED":
            categories[cat]["not_cited"] += 1
        elif r["status"] == "ERROR":
            categories[cat]["error"] += 1
    for cdata in categories.values():
        testable_c = cdata["total"] - cdata["error"]
        cdata["citation_rate_pct"] = round(cdata["cited"] / testable_c * 100, 1) if testable_c > 0 else 0

    # Verdict — keyed off brand+topic_authority categories, not the overall rate.
    # The overall rate averages competitor and long_tail queries that are tutorial-
    # shape and not the right test for a citation-attribution claim.
    brand_topic_results = [r for r in results if r.get("category") in ("brand", "topic_authority")]
    bt_testable = sum(1 for r in brand_topic_results if r["status"] != "ERROR")
    bt_cited = sum(1 for r in brand_topic_results if r["status"] == "CITED")
    bt_rate = bt_cited / bt_testable if bt_testable > 0 else 0
    if bt_rate > 0.4:
        verdict = "CITED"
    elif bt_rate > 0.05:
        verdict = "PARTIALLY_CITED"
    else:
        verdict = "NOT_CITED"

    return {
        "total_tests": total,
        "testable": testable,
        "errors": errors,
        "cited_count": cited,
        "citation_rate_pct": round(rate * 100, 1),
        "brand_topic_rate_pct": round(bt_rate * 100, 1),
        "brand_topic_cited": bt_cited,
        "brand_topic_testable": bt_testable,
        "confidence_interval_95": {
            "low_pct": round(ci_low * 100, 1),
            "high_pct": round(ci_high * 100, 1),
        },
        "confidence_label": confidence,
        "by_platform": platforms,
        "by_category": categories,
        "verdict": verdict,
    }


def _call_with_retry(fn, query, target_url, max_retries: int = 2):
    """Call an engine query function, retrying transient ERROR results.

    Engine functions catch their own exceptions and return {status: ERROR};
    we retry with exponential backoff on those. Non-error results pass through.

    Rate-limit handling (added 2026-05-10): if the error message contains a
    429 / RESOURCE_EXHAUSTED / quota signal, back off 60s instead of the
    default short exponential. The 60s window resets Gemini 2.5-flash's
    free-tier 15 RPM quota. Without this, sequential bursts of >5 Gemini
    queries exhaust the quota and the short retry (max 4.5s) doesn't clear it.
    """
    import time as _t
    last_result = None
    rate_limit_signals = ("429", "RESOURCE_EXHAUSTED", "quota", "rate limit", "rate_limit", "Too Many Requests")
    for attempt in range(max_retries + 1):
        result = fn(query, target_url)
        if result.get("status") != "ERROR":
            return result
        last_result = result
        if attempt < max_retries:
            err_msg = str(result.get("error") or result.get("response_snippet") or "").lower()
            if any(sig.lower() in err_msg for sig in rate_limit_signals):
                _t.sleep(60)
            else:
                _t.sleep(1.5 * (2 ** attempt))  # 1.5s, 3s
    return last_result


def run_citation_test(
    target_url: str,
    topics: list[str] | None = None,
    output_dir: str = ".",
    platforms: list[str] | None = None,
    brand: str | None = None,
    vertical: str | None = None,
    vertical_ctx: dict | None = None,
) -> dict:
    """Run automated citation testing across available AI platforms.

    Args:
        target_url: The domain to check citations for
        topics: Topics the site covers (for query generation)
        output_dir: Where to save results
        platforms: Which platforms to test (default: all with valid keys)

    Returns:
        Citation results dict compatible with report_generator
    """
    if not target_url.startswith("http"):
        target_url = f"https://{target_url}"

    domain = target_url.replace("https://", "").replace("http://", "").split("/")[0]
    available = _check_keys()

    # Determine which platforms to use
    if platforms:
        active = {p: available[p] for p in platforms if p in available}
    else:
        active = {p: v for p, v in available.items() if v}

    if not active:
        print("ERROR: No API keys configured. Add keys to .env file:")
        print("  OPENAI_API_KEY=sk-...")
        print("  PERPLEXITY_API_KEY=pplx-...")
        print("  ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    active_names = [PLATFORM_NAMES[p] for p in active]
    print(f"\n{'='*60}")
    print(f"  AVR Automated Citation Test")
    print(f"  Target: {target_url}")
    print(f"  Platforms: {', '.join(active_names)}")
    print(f"  Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    # Generate queries
    queries = generate_queries(domain, topics, brand=brand, vertical=vertical, vertical_ctx=vertical_ctx)
    total_queries = len(queries) * len(active)
    print(f"Running {len(queries)} queries x {len(active)} platforms = {total_queries} tests\n")

    # Build tasks in q-major, platform-minor order so assembled all_results is
    # identical to the prior serial ordering.
    tasks = []  # (idx, q, platform_key)
    for q in queries:
        for platform_key in active:
            tasks.append((len(tasks), q, platform_key))

    results_by_idx = [None] * len(tasks)
    per_platform = {p: Semaphore(PER_PLATFORM_CONCURRENCY) for p in active}
    progress = {"done": 0}
    progress_lock = Lock()

    def _run_task(task):
        tidx, q, platform_key = task
        func = PLATFORM_FUNCTIONS[platform_key]
        platform_name = PLATFORM_NAMES[platform_key]

        # Per-platform semaphore caps each provider's concurrency; cross-provider
        # calls overlap. 0.5s politeness stays inside the slot (per-platform).
        with per_platform[platform_key]:
            result = _call_with_retry(func, q["query"], target_url)
            time.sleep(0.5)
        result["query_id"] = q["id"]
        result["category"] = q["category"]

        with progress_lock:
            progress["done"] += 1
            status_display = result["status"]
            if status_display == "CITED":
                status_display = "CITED <<"
            print(f"  [{progress['done']}/{total_queries}] {platform_name}: {q['query'][:50]}... {status_display}", flush=True)

        return tidx, result

    max_workers = max(1, len(active) * PER_PLATFORM_CONCURRENCY)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for tidx, result in ex.map(_run_task, tasks):
            results_by_idx[tidx] = result

    all_results = results_by_idx

    # Compute summary
    summary = compute_results(all_results)
    summary["target_url"] = target_url
    summary["test_date"] = datetime.now(timezone.utc).isoformat()
    summary["platforms_tested"] = list(active.keys())

    # Save raw results
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    raw_path = os.path.join(output_dir, f"citations_{domain}_{timestamp}_raw.json")
    with open(raw_path, "w") as f:
        json.dump(all_results, f, indent=2)

    summary_path = os.path.join(output_dir, f"citations_{domain}_{timestamp}_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary — lead with per-category (the load-bearing numbers); the
    # overall rate averages incompatible query types and is shown last as
    # context, not as the headline.
    print(f"\n{'='*60}")
    print(f"  CITATION TEST RESULTS")
    print(f"  Verdict: {summary['verdict']} (confidence: {summary['confidence_label']})")
    print(f"")
    print(f"  HEADLINE: brand + topic_authority cited rate (the load-bearing number):")
    print(f"    {summary['brand_topic_cited']}/{summary['brand_topic_testable']} = {summary['brand_topic_rate_pct']}%")
    print(f"")
    cat_labels = {
        "brand": "Brand queries (does the engine cite you when asked about your brand)",
        "topic_authority": "Topic authority (does it cite you for authoritative-source queries)",
        "long_tail": "Tutorial-shape queries (how-to, getting-started)",
        "competitor": "Comparison queries (how does brand compare to alternatives)",
    }
    print(f"  PER-CATEGORY SCORES:")
    for cat in ("brand", "topic_authority", "long_tail", "competitor"):
        if cat in summary["by_category"]:
            cd = summary["by_category"][cat]
            label = cat_labels.get(cat, cat)
            print(f"    {label}")
            print(f"      → {cd['cited']}/{cd['total']} = {cd['citation_rate_pct']}%")
    print(f"")
    print(f"  Per platform:")
    for pname, pdata in summary["by_platform"].items():
        print(f"    {pname}: {pdata['cited']}/{pdata['total']} cited ({pdata['citation_rate_pct']}%)")
    print(f"")
    print(f"  Aggregate (averages incompatible categories — interpret per-category above):")
    print(f"    {summary['citation_rate_pct']}% overall ({summary['cited_count']}/{summary['testable']})")
    ci = summary["confidence_interval_95"]
    print(f"    95% CI: [{ci['low_pct']}%, {ci['high_pct']}%]")
    print(f"")
    print(f"  Raw results: {raw_path}")
    print(f"  Summary: {summary_path}")
    print(f"{'='*60}")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="AVR Automated Citation Testing",
        epilog="""
Examples:
  python citation_auto.py test chudi.dev --topics "Claude Code hooks" "AI visibility"
  python citation_auto.py test example.com --platforms openai perplexity
  python citation_auto.py status                    # Check which API keys are configured
  python citation_auto.py test example.com -o reports/

Platforms:
  openai      ChatGPT with web search (gpt-4.1)
  perplexity  Perplexity sonar search
  anthropic   Claude with web search (haiku)
  gemini      Google Gemini with Search grounding (2.5-flash)

Coverage: 20 queries x 4 platforms
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # status command
    sub.add_parser("status", help="Check which API keys are configured")

    # test command
    test_p = sub.add_parser("test", help="Run citation test on a URL")
    test_p.add_argument("url", help="Target URL to test citations for")
    test_p.add_argument("--brand", help="Brand name to use in queries (e.g., 'Wikipedia', 'freeCodeCamp'). Defaults to derived-from-domain.")
    test_p.add_argument("--topics", nargs="*", help="Topics the site covers")
    test_p.add_argument("--vertical", choices=["local-healthcare", "saas-tool", "personal-brand", "tech-publisher"],
                        help="Vertical profile for query templates (geo-aware for local-healthcare, etc.)")
    test_p.add_argument("--platforms", nargs="*", choices=["openai", "perplexity", "anthropic", "gemini"], help="Which platforms to test (default: all with keys)")
    test_p.add_argument("-o", "--output", default=".", help="Output directory")

    args = parser.parse_args()

    if args.command == "status":
        keys = _check_keys()
        print("AVR Citation Testing - API Key Status\n")
        for platform, has_key in keys.items():
            status = "CONFIGURED" if has_key else "MISSING"
            name = PLATFORM_NAMES[platform]
            print(f"  {name:12s} [{status}]")
        print()
        missing = [PLATFORM_NAMES[p] for p, v in keys.items() if not v]
        if missing:
            print(f"  Missing: {', '.join(missing)}")
            print(f"  Add keys to: {env_path}")
        else:
            print("  All platforms ready.")

    elif args.command == "test":
        # Build vertical context from CLI args. Each vertical's template builder
        # has its own required keys; we pass everything we have and let the
        # builder pick what it needs.
        vertical_ctx = {
            "brand": args.brand,
            "topics": args.topics or [],
            "use_cases": args.topics or [],   # SaaS uses use_cases
            "expertise": args.topics or [],   # Personal-brand uses expertise
        }
        run_citation_test(
            args.url, args.topics, args.output, args.platforms,
            brand=args.brand, vertical=args.vertical, vertical_ctx=vertical_ctx,
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
