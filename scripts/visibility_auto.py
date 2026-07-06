#!/usr/bin/env python3
from __future__ import annotations
"""
AVR Automated AI Visibility Testing

Different from citation testing. Citation checks if the AI links to your URL.
Visibility checks if the AI KNOWS about you: mentions your brand, references
your concepts, or recommends your product, even without a direct link.

Three visibility signals:
1. BRAND RECOGNITION: Does the AI know who you are when asked directly?
2. CONCEPT ATTRIBUTION: Does the AI use your ideas/terminology in topic queries?
3. RECOMMENDATION: Does the AI recommend you when asked for tools/resources?

Setup:
  Same .env as citation_auto.py (OPENAI_API_KEY, PERPLEXITY_API_KEY, ANTHROPIC_API_KEY)

Cost per audit (~30 queries):
  Live API queries, varies by platform.
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Semaphore

# Live calls run concurrently ACROSS platforms with a per-platform cap that
# protects each provider's rate limit. This is metric-invariant: each
# (query, platform) result is computed purely from that call's response text,
# and the summary is order-independent. Set AVR_PER_PLATFORM_CONCURRENCY=1 to
# force fully-serial behavior. (Was fully serial; 160 sequential calls took
# ~30 min and blew the 900s audit timeout. Parallelized 2026-06-08.)
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
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
    }


PLATFORM_NAMES = {
    "openai": "ChatGPT",
    "perplexity": "Perplexity",
    "anthropic": "Claude",
    "gemini": "Gemini",
}


def _query_openai(query: str) -> str:
    """Query OpenAI and return the full response text.

    DESIGN NOTE: visibility tests TRAINING-DATA brand knowledge — does the
    model know about this brand without looking it up? Forcing web_search
    would corrupt the measurement (the model would summarize the brand's
    homepage instead of revealing what it actually knows). The web_search
    tool is OFFERED but not forced; the model uses it if it's uncertain.
    """
    from openai import OpenAI
    # 90s per-call timeout — without it, OpenAI's web_search backend can
    # hang indefinitely (witnessed during overnight test). Surfaces as
    # exception so the retry wrapper can catch it.
    client = OpenAI(timeout=90.0)
    response = client.responses.create(
        model="gpt-4.1",
        temperature=0,
        tools=[{"type": "web_search_preview"}],
        input=query,
    )
    text = ""
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    text += content.text
    return text


def _query_perplexity(query: str) -> str:
    """Query Perplexity and return the full response text.

    Perplexity always searches by definition (sonar model). For visibility,
    this is acceptable — Perplexity's "what does the web currently say" is
    a reasonable proxy for visibility on engines designed around web search.
    """
    import requests as req
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    resp = req.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "sonar", "temperature": 0, "messages": [{"role": "user", "content": query}]},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("choices"):
        return data["choices"][0].get("message", {}).get("content", "")
    return ""


def _query_anthropic(query: str) -> str:
    """Query Anthropic and return the full response text.

    Same design note as _query_openai: web_search OFFERED but not forced
    — visibility tests training knowledge. Claude is conservative about
    invoking web_search, so most responses come from training data.
    """
    from anthropic import Anthropic
    client = Anthropic(timeout=90.0)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        temperature=0,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": query}],
    )
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text
    return text


def _query_gemini(query: str) -> str:
    """Query Google Gemini and return the full response text.

    Same design note as _query_openai: visibility tests TRAINING-DATA brand
    knowledge. Gemini's google_search grounding tool is NOT enabled here so
    the response reflects what the model knows, not what the search index
    currently says. Citation tests in citation_auto.py do enable grounding.

    60s per-call timeout (added 2026-05-21): without it, a hung Gemini
    connection stalls the whole visibility test indefinitely. The other 3
    platforms (OpenAI 90s, Perplexity 30s, Anthropic 90s) all carry timeouts;
    Gemini was the lone unbounded path. Repro: chudi.dev visibility runs
    2026-05-21 both hung at 0% CPU for 25+ min on a single Gemini call.
    _query_with_retry already retries up to 2x on exception, so the
    effective max wait is ~3 minutes per query.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(http_options=types.HttpOptions(timeout=60_000))
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=query,
        config=types.GenerateContentConfig(temperature=0),
    )
    return response.text or ""


QUERY_FUNCTIONS = {
    "openai": _query_openai,
    "perplexity": _query_perplexity,
    "anthropic": _query_anthropic,
    "gemini": _query_gemini,
}


def _query_with_retry(func, query: str, max_retries: int = 2) -> tuple[str, str | None]:
    """Call a query function with retry-on-exception.

    Returns (response_text, error_message). On all-attempts-failed,
    response_text is "" and error_message is the last exception's str.

    Rate-limit handling (added 2026-05-10): if the exception message contains
    a 429 / RESOURCE_EXHAUSTED / quota / rate signal, back off 60s instead of
    the default short exponential. The 60s window resets Gemini 2.5-flash's
    free-tier 15 RPM quota. Without this, 20 sequential Gemini visibility
    queries exhaust the quota after ~5 successes; the short retry (max 4.5s)
    doesn't clear the rate window, so 16/20 queries return empty + ERROR.
    """
    import time as _t
    last_err = None
    rate_limit_signals = ("429", "RESOURCE_EXHAUSTED", "quota", "rate limit", "rate_limit", "Too Many Requests")
    for attempt in range(max_retries + 1):
        try:
            return func(query), None
        except Exception as e:
            last_err = str(e)
            if attempt < max_retries:
                # Detect rate-limit error and back off long enough to clear the window
                if any(sig.lower() in last_err.lower() for sig in rate_limit_signals):
                    _t.sleep(60)
                else:
                    _t.sleep(1.5 * (2 ** attempt))
    return "", last_err


def _brand_mentioned(text: str, brand_name: str) -> bool:
    """Detect brand-name mention in text, tolerant of spacing/case variants.

    'freeCodeCamp' should match 'free code camp', 'Free Code Camp', and the
    canonical 'freecodecamp'. Strips non-alphanumeric chars and compares.
    """
    if not brand_name:
        return False
    canonical = "".join(c for c in brand_name.lower() if c.isalnum())
    text_canonical = "".join(c for c in text.lower() if c.isalnum())
    if canonical and canonical in text_canonical:
        return True
    # Also match the literal lowercased brand name (preserves word boundaries)
    return brand_name.lower() in text.lower()


def check_brand_recognition(
    response_text: str,
    domain: str,
    brand_name: str,
    owner_name: str | None = None,
) -> dict:
    """Check if the response shows brand recognition.

    Three signals: domain mention, brand mention (space-tolerant), owner mention.
    Levels: KNOWN (2+ signals) / PARTIALLY_KNOWN (1) / UNKNOWN (0).
    """
    text_lower = response_text.lower()
    domain_clean = domain.replace("https://", "").replace("http://", "").rstrip("/").lower()

    signals = {
        "domain_mentioned": domain_clean in text_lower,
        "brand_mentioned": _brand_mentioned(response_text, brand_name),
        "owner_mentioned": _brand_mentioned(response_text, owner_name) if owner_name else False,
        "described_accurately": False,  # requires manual review
    }

    mention_count = sum([signals["domain_mentioned"], signals["brand_mentioned"], signals["owner_mentioned"]])

    if mention_count >= 2:
        level = "KNOWN"
    elif mention_count == 1:
        level = "PARTIALLY_KNOWN"
    else:
        level = "UNKNOWN"

    return {"signals": signals, "level": level, "mention_count": mention_count}


_CONCEPT_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at",
    "with", "is", "are", "was", "were", "be", "by", "as", "this", "that",
    "from", "but", "not",
}


def _concept_match(response_text: str, concept: str, overlap_threshold: float = 0.5) -> bool:
    """Match a concept phrase against response text via token overlap.

    Literal substring match misses paraphrases — e.g., concept 'interactive
    coding curriculum' wouldn't match a response that says 'interactive
    courses for coding'. This token-stemmed approach checks how many of the
    concept's content words (after dropping stopwords + simple stem) appear
    anywhere in the response. If 50%+ of content words present, count it.

    Deterministic + no LLM call (preserves reproducibility per
    ai-citation-measurement-methodology codex node §Step 4).
    """
    if not concept:
        return False
    text_lower = response_text.lower()
    # Direct substring match wins (preserves prior behavior for exact hits)
    if concept.lower() in text_lower:
        return True

    def tokenize(s: str) -> list[str]:
        # Split on non-alphanumeric, lowercase, drop empties + stopwords + single chars
        out = []
        cur = []
        for ch in s.lower():
            if ch.isalnum():
                cur.append(ch)
            elif cur:
                out.append("".join(cur))
                cur = []
        if cur:
            out.append("".join(cur))
        return [t for t in out if t and t not in _CONCEPT_STOPWORDS and len(t) > 2]

    def stem(tok: str) -> str:
        # Crude suffix stemmer covering common English noun/verb endings.
        # Good enough for "courses" → "cours", "tutorial" → "tutori", etc.
        for suffix in ("ationally", "ization", "ational", "iveness", "ements",
                       "ations", "isation", "ization", "ingly", "fully",
                       "ities", "ously", "ation", "ement", "ished",
                       "tions", "sions", "ments", "able", "ible", "less",
                       "ness", "ment", "tion", "sion", "ings", "ings",
                       "ies", "ied", "ing", "ers", "est", "ity",
                       "ly", "es", "ed", "er", "or", "al"):
            if tok.endswith(suffix) and len(tok) > len(suffix) + 2:
                return tok[:-len(suffix)]
        if tok.endswith("s") and len(tok) > 3:
            return tok[:-1]
        return tok

    concept_tokens = [stem(t) for t in tokenize(concept)]
    if not concept_tokens:
        return False
    text_stems = {stem(t) for t in tokenize(response_text)}

    matches = sum(1 for ct in concept_tokens if ct in text_stems)
    return matches / len(concept_tokens) >= overlap_threshold


def check_concept_attribution(
    response_text: str,
    key_concepts: list[str],
) -> dict:
    """Check if the AI uses concepts/terminology associated with the brand.

    Per-concept match uses _concept_match (token-stem overlap, 50% threshold)
    so paraphrases count: 'interactive coding curriculum' matches 'interactive
    courses for coding' — both share {interactiv, cod} stems above threshold.
    """
    found = [c for c in key_concepts if _concept_match(response_text, c)]
    ratio = len(found) / len(key_concepts) if key_concepts else 0
    return {
        "concepts_checked": key_concepts,
        "concepts_found": found,
        "concept_ratio": round(ratio, 2),
    }


def check_recommendation(
    response_text: str,
    domain: str,
    brand_name: str,
    product_names: list[str] | None = None,
) -> dict:
    """Check if the AI recommends the brand/product.

    "Recommendation" means the model is suggesting the brand to the user,
    not just describing it. Patterns like 'X is a' / 'X provides' are
    DESCRIPTIVE (already counted by brand_recognition); they're excluded here
    to avoid double-counting and to keep this signal meaningfully different.
    """
    text_lower = response_text.lower()
    brand_lower = brand_name.lower()
    domain_clean = domain.replace("https://", "").replace("http://", "").rstrip("/").lower()

    recommended = False
    recommended_as = []

    # Imperative recommendation patterns ("the model is suggesting the user use the brand")
    rec_patterns = [
        f"recommend {brand_lower}",
        f"i recommend {brand_lower}",
        f"i'd recommend {brand_lower}",
        f"i would recommend {brand_lower}",
        f"i suggest {brand_lower}",
        f"i'd suggest {brand_lower}",
        f"try {brand_lower}",
        f"check out {brand_lower}",
        f"check {brand_lower} out",
        f"use {brand_lower}",
        f"start with {brand_lower}",
        f"go with {brand_lower}",
        f"consider {brand_lower}",
        f"visit {domain_clean}",
        f"head to {domain_clean}",
        # Listicle inclusion patterns — the model put the brand in a list of recommendations
        f"- {brand_lower}",
        f"* {brand_lower}",
        f"1. {brand_lower}",
        f"2. {brand_lower}",
        f"3. {brand_lower}",
        f"**{brand_lower}**",
    ]

    for pattern in rec_patterns:
        if pattern in text_lower:
            recommended = True
            recommended_as.append(pattern)

    # Check product names — product mention typically IS a recommendation in context
    if product_names:
        for product in product_names:
            if product.lower() in text_lower:
                recommended = True
                recommended_as.append(f"product: {product}")

    # Dedupe
    recommended_as = list(dict.fromkeys(recommended_as))

    return {
        "recommended": recommended,
        "recommended_as": recommended_as,
    }


def generate_visibility_queries(
    domain: str,
    brand_name: str,
    owner_name: str | None = None,
    topics: list[str] | None = None,
    products: list[str] | None = None,
) -> list[dict]:
    """Generate queries for visibility testing across 3 signal categories."""
    queries = []

    # Category 1: Brand Recognition (10 queries)
    queries.extend([
        {"id": 1, "category": "brand_recognition", "query": f"What is {domain}?", "signal": "direct_ask"},
        {"id": 2, "category": "brand_recognition", "query": f"Tell me about {brand_name}", "signal": "direct_ask"},
        {"id": 3, "category": "brand_recognition", "query": f"What does {brand_name} do?", "signal": "direct_ask"},
    ])
    if owner_name:
        queries.extend([
            {"id": 4, "category": "brand_recognition", "query": f"Who is {owner_name}?", "signal": "owner_recognition"},
            {"id": 5, "category": "brand_recognition", "query": f"What has {owner_name} built?", "signal": "owner_recognition"},
        ])
    else:
        queries.extend([
            {"id": 4, "category": "brand_recognition", "query": f"Who created {domain}?", "signal": "owner_recognition"},
            {"id": 5, "category": "brand_recognition", "query": f"Who runs {brand_name}?", "signal": "owner_recognition"},
        ])

    # Category 2: Concept Attribution (10 queries using topics)
    if topics:
        for i, topic in enumerate(topics[:5]):
            queries.append({
                "id": 10 + i,
                "category": "concept_attribution",
                "query": f"What are the best approaches for {topic}?",
                "signal": "topic_expertise",
            })
        for i, topic in enumerate(topics[:5]):
            queries.append({
                "id": 15 + i,
                "category": "concept_attribution",
                "query": f"Who writes about {topic}?",
                "signal": "author_association",
            })

    # Category 3: Recommendation (10 queries)
    if topics:
        for i, topic in enumerate(topics[:5]):
            queries.append({
                "id": 20 + i,
                "category": "recommendation",
                "query": f"What tools or blogs should I follow for {topic}?",
                "signal": "recommendation",
            })
        for i, topic in enumerate(topics[:3]):
            queries.append({
                "id": 25 + i,
                "category": "recommendation",
                "query": f"Best resources for learning {topic} in 2026",
                "signal": "recommendation",
            })
    if products:
        for i, product in enumerate(products[:2]):
            queries.append({
                "id": 28 + i,
                "category": "recommendation",
                "query": f"Is {product} worth using?",
                "signal": "product_recommendation",
            })

    return queries


def run_visibility_test(
    target_url: str,
    brand_name: str,
    owner_name: str | None = None,
    topics: list[str] | None = None,
    products: list[str] | None = None,
    key_concepts: list[str] | None = None,
    output_dir: str = ".",
    platforms: list[str] | None = None,
) -> dict:
    """Run AI visibility test across available platforms.

    Args:
        target_url: Domain to test visibility for
        brand_name: Brand name to search for
        owner_name: Owner/author name
        topics: Topics the site covers
        products: Product names to check
        key_concepts: Unique concepts/terminology from the brand
        output_dir: Where to save results
        platforms: Which platforms to test

    Returns:
        Visibility results dict
    """
    if not target_url.startswith("http"):
        target_url = f"https://{target_url}"

    domain = target_url.replace("https://", "").replace("http://", "").split("/")[0]

    # Argument fallback: when --concepts or --products are not provided,
    # fall back to --topics so concept_attribution and recommendation
    # checks have something to match against. Without this, those checks
    # silently return 0/N across all queries even when responses are well-
    # formed. See citability-skill-evolution-2026-05-20-case-study.
    effective_concepts = key_concepts if key_concepts else (topics or [])
    effective_products = products if products else (topics or [])
    if not key_concepts and effective_concepts:
        print(f"NOTE: --concepts not provided; using --topics as fallback for "
              f"concept_attribution checks: {effective_concepts}")
    if not products and effective_products:
        print(f"NOTE: --products not provided; using --topics as fallback for "
              f"recommendation checks: {effective_products}")
    if not effective_concepts:
        print("WARN: no --concepts or --topics; concept_attribution signal "
              "will return 0/N (no match list). Pass --topics or --concepts.")
    if not effective_products:
        print("WARN: no --products or --topics; recommendation signal will "
              "rely on brand-name patterns only. Pass --topics or --products.")

    available = _check_keys()

    if platforms:
        active = {p: available[p] for p in platforms if available.get(p)}
    else:
        active = {p: v for p, v in available.items() if v}

    if not active:
        print("ERROR: No API keys configured.")
        sys.exit(1)

    active_names = [PLATFORM_NAMES[p] for p in active]
    print(f"\n{'='*60}")
    print(f"  AVR AI Visibility Test")
    print(f"  Target: {target_url} ({brand_name})")
    print(f"  Platforms: {', '.join(active_names)}")
    print(f"  Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    queries = generate_visibility_queries(domain, brand_name, owner_name, topics, products)
    total_tests = len(queries) * len(active)
    print(f"Running {len(queries)} queries x {len(active)} platforms = {total_tests} tests\n")

    # Build the task list in q-major, platform-minor order so the assembled
    # all_results is byte-identical to the prior serial ordering.
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
        func = QUERY_FUNCTIONS[platform_key]
        platform_name = PLATFORM_NAMES[platform_key]

        # Per-platform semaphore caps concurrency to one provider's rate budget;
        # calls to DIFFERENT providers still overlap. The 0.5s politeness delay
        # stays inside the slot so it throttles per-platform, not globally.
        with per_platform[platform_key]:
            response_text, err = _query_with_retry(func, q["query"])
            time.sleep(0.5)

        if err and not response_text:
            result = {
                "query_id": q["id"],
                "category": q["category"],
                "signal": q["signal"],
                "platform": platform_name,
                "query": q["query"],
                "visible": False,
                "error": err,
            }
            status = "ERROR"
        else:
            # Run all three checks on every response. Each is a pure function of
            # the response text + this query's params, so concurrency cannot
            # change any individual result (metric invariance).
            brand_check = check_brand_recognition(response_text, target_url, brand_name, owner_name)
            concept_check = check_concept_attribution(response_text, effective_concepts)
            rec_check = check_recommendation(response_text, target_url, brand_name, effective_products)

            visible = brand_check["level"] != "UNKNOWN" or rec_check["recommended"] or concept_check["concept_ratio"] > 0.3

            result = {
                "query_id": q["id"],
                "category": q["category"],
                "signal": q["signal"],
                "platform": platform_name,
                "query": q["query"],
                "visible": visible,
                "brand_recognition": brand_check,
                "concept_attribution": concept_check,
                "recommendation": rec_check,
                "response_snippet": response_text[:300],
            }

            status = "VISIBLE" if visible else "NOT_VISIBLE"
            if brand_check["level"] == "KNOWN":
                status = "KNOWN"
            elif rec_check["recommended"]:
                status = "RECOMMENDED"

        with progress_lock:
            progress["done"] += 1
            print(f"  [{progress['done']}/{total_tests}] {platform_name}: {q['query'][:50]}... {status}", flush=True)

        return tidx, result

    max_workers = max(1, len(active) * PER_PLATFORM_CONCURRENCY)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for tidx, result in ex.map(_run_task, tasks):
            results_by_idx[tidx] = result

    all_results = results_by_idx

    # Compute summary
    total = len(all_results)
    errors = sum(1 for r in all_results if "error" in r)
    testable = total - errors
    visible_count = sum(1 for r in all_results if r.get("visible"))
    known_count = sum(1 for r in all_results if r.get("brand_recognition", {}).get("level") == "KNOWN")
    recommended_count = sum(1 for r in all_results if r.get("recommendation", {}).get("recommended"))

    visibility_rate = visible_count / testable if testable > 0 else 0

    # Per-category breakdown
    categories = {}
    for r in all_results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"visible": 0, "total": 0}
        categories[cat]["total"] += 1
        if r.get("visible"):
            categories[cat]["visible"] += 1

    for cdata in categories.values():
        cdata["rate_pct"] = round(cdata["visible"] / cdata["total"] * 100, 1) if cdata["total"] > 0 else 0

    # Per-platform breakdown
    platforms_summary = {}
    for r in all_results:
        p = r.get("platform", "unknown")
        if p not in platforms_summary:
            platforms_summary[p] = {"visible": 0, "total": 0, "errored": 0}
        platforms_summary[p]["total"] += 1
        if "error" in r:
            platforms_summary[p]["errored"] += 1
        if r.get("visible"):
            platforms_summary[p]["visible"] += 1

    for pdata in platforms_summary.values():
        # rate_pct kept (visible / total) for backward compat with historical
        # scans + the dashboard. testable_rate_pct (visible / testable) excludes
        # errored queries from the denominator so an all-errored platform reads
        # as "0/0 untestable", not a misleading "0% invisible". Added 2026-05-28
        # after the chudi.dev run where 19/19 Claude queries errored on a depleted
        # API credit balance and showed as "0%", indistinguishable from regression.
        pdata["testable"] = pdata["total"] - pdata["errored"]
        pdata["rate_pct"] = round(pdata["visible"] / pdata["total"] * 100, 1) if pdata["total"] > 0 else 0
        pdata["testable_rate_pct"] = round(pdata["visible"] / pdata["testable"] * 100, 1) if pdata["testable"] > 0 else None

    # Verdict — keyed off brand_recognition rate (the cleanest signal). The
    # aggregate visibility_rate averages incompatible signals across a query
    # mix biased toward tools/resources, which can declare reference sites
    # INVISIBLE incorrectly. The brand_recognition rate is what the headline
    # claim "AI knows about you" actually measures.
    brand_rate = (categories.get("brand_recognition", {}).get("rate_pct", 0) or 0) / 100.0
    if brand_rate > 0.7:
        verdict = "HIGHLY_VISIBLE"
    elif brand_rate > 0.4:
        verdict = "PARTIALLY_VISIBLE"
    elif brand_rate > 0.1:
        verdict = "BARELY_VISIBLE"
    else:
        verdict = "INVISIBLE"

    # Per-platform error surfacing (added 2026-05-28). A platform that errors on
    # every query (depleted credit balance, rate-limit, 503s) otherwise hides as
    # "0% visible". Surface count + categorized sample so the failure self-identifies.
    def _categorize_error(msg: str) -> str:
        m = (msg or "").lower()
        if "credit balance" in m or "plans & billing" in m or "purchase credits" in m:
            return "credit_balance_too_low"
        if any(x in m for x in ("429", "rate limit", "rate_limit", "too many requests", "resource_exhausted", "quota")):
            return "rate_limited"
        if "503" in m or "unavailable" in m or "high demand" in m or "overloaded" in m:
            return "service_unavailable"
        if "timeout" in m or "timed out" in m:
            return "timeout"
        if "authentication" in m or "401" in m or "invalid x-api-key" in m:
            return "auth_error"
        return "other"

    errors_by_platform = {}
    for r in all_results:
        if "error" in r:
            p = r.get("platform", "unknown")
            if p not in errors_by_platform:
                errors_by_platform[p] = {"count": 0, "category": None, "sample": None}
            errors_by_platform[p]["count"] += 1
            if errors_by_platform[p]["category"] is None:
                errors_by_platform[p]["category"] = _categorize_error(r["error"])
                errors_by_platform[p]["sample"] = r["error"][:200]

    summary = {
        "target_url": target_url,
        "brand_name": brand_name,
        "test_date": datetime.now(timezone.utc).isoformat(),
        "total_tests": total,
        "testable": testable,
        "visible_count": visible_count,
        "known_count": known_count,
        "recommended_count": recommended_count,
        "visibility_rate_pct": round(visibility_rate * 100, 1),
        "confidence_label": "LOW",  # single round is always LOW
        "by_category": categories,
        "by_platform": platforms_summary,
        "errors_by_platform": errors_by_platform,
        "verdict": verdict,
    }

    # Save results
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    raw_path = os.path.join(output_dir, f"visibility_{domain}_{timestamp}_raw.json")
    with open(raw_path, "w") as f:
        json.dump(all_results, f, indent=2)

    summary_path = os.path.join(output_dir, f"visibility_{domain}_{timestamp}_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary — lead with PER-CATEGORY since the overall rate averages
    # signals that mean different things (brand-knows-you, topic-association,
    # active-recommendation). The per-category breakdown is the honest metric.
    print(f"\n{'='*60}")
    print(f"  AI VISIBILITY TEST RESULTS")
    print(f"  Verdict: {verdict} (confidence: LOW)")
    print(f"")
    print(f"  PER-CATEGORY SCORES (the load-bearing numbers):")
    cat_labels = {
        "brand_recognition": "Brand recognition (does the model know you exist)",
        "concept_attribution": "Topic association (paraphrase-tolerant — does the model link you to your topics)",
        "recommendation": "Active recommendation (does the model recommend you to users)",
    }
    for cat in ["brand_recognition", "concept_attribution", "recommendation"]:
        if cat in categories:
            cdata = categories[cat]
            label = cat_labels.get(cat, cat)
            print(f"    {label}")
            print(f"      → {cdata['visible']}/{cdata['total']} = {cdata['rate_pct']}%")
    # Show any other categories that weren't in the canonical set
    for cat, cdata in categories.items():
        if cat not in cat_labels:
            print(f"    {cat}: {cdata['visible']}/{cdata['total']} ({cdata['rate_pct']}%)")
    print(f"")
    print(f"  By platform:")
    for pname, pdata in platforms_summary.items():
        print(f"    {pname}: {pdata['visible']}/{pdata['total']} = {pdata['rate_pct']}%")
    print(f"")
    print(f"  Aggregate (averages incompatible signals — interpret per-category instead):")
    print(f"    {summary['visibility_rate_pct']}% overall ({visible_count}/{testable})")
    print(f"    Brand recognized {known_count} times, recommended {recommended_count} times")
    print(f"")
    print(f"  Raw results: {raw_path}")
    print(f"  Summary: {summary_path}")
    print(f"{'='*60}")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="AVR AI Visibility Testing (brand awareness, not just citation links)",
        epilog="""
Examples:
  python visibility_auto.py test chudi.dev --brand "Chudi" --owner "Chudi Nnorukam" \\
    --topics "Claude Code hooks" "AI visibility" --concepts "hooks as middleware" "AVR framework"

  python visibility_auto.py test ahrefs.com --brand "Ahrefs" \\
    --topics "backlink analysis" "keyword research" --products "Site Explorer" "Keywords Explorer"

Visibility Signals (different from citations):
  KNOWN          AI recognizes the brand and describes it accurately
  RECOMMENDED    AI recommends the brand/product when asked for resources
  VISIBLE        AI mentions brand/concepts without direct recommendation
  NOT_VISIBLE    AI shows no awareness of the brand

Coverage: live API queries, varies by platform
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    test_p = sub.add_parser("test", help="Run visibility test")
    test_p.add_argument("url", help="Target URL")
    test_p.add_argument("--brand", required=True, help="Brand name to check for")
    test_p.add_argument("--owner", help="Owner/author name")
    test_p.add_argument("--topics", nargs="*", help="Topics the site covers")
    test_p.add_argument("--products", nargs="*", help="Product names")
    test_p.add_argument("--concepts", nargs="*", help="Unique concepts/terminology from the brand")
    test_p.add_argument("--platforms", nargs="*", choices=["openai", "perplexity", "anthropic", "gemini"])
    test_p.add_argument("-o", "--output", default=".", help="Output directory")
    test_p.add_argument("--emit-queries", action="store_true",
                        help="Print the query set as JSON and exit 0; no API call, no key required")

    args = parser.parse_args()

    if args.command == "test":
        if args.emit_queries:
            url = args.url if args.url.startswith("http") else f"https://{args.url}"
            domain = url.replace("https://", "").replace("http://", "").split("/")[0]
            effective_products = args.products if args.products else (args.topics or [])
            queries = generate_visibility_queries(domain, args.brand, args.owner, args.topics, effective_products)
            print(json.dumps({
                "mode": "visibility",
                "url": url,
                "queries": [
                    {"id": q["id"], "category": q["category"], "platform": "all", "prompt": q["query"]}
                    for q in queries
                ],
            }, indent=2))
            sys.exit(0)
        run_visibility_test(
            args.url, args.brand, args.owner, args.topics,
            args.products, args.concepts, args.output, args.platforms,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
