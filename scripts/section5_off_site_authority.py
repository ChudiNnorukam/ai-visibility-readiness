#!/usr/bin/env python3
"""
AVR Section 5: Off-Site Authority Checks (Phase 1 only)

Implements sub-checks 7, 8, 9 from the citability-off-site-authority-section-spec
(decision_id dc-20260513T180052Z-9409, ratified 2026-05-13):

  Check 7: Wikipedia entry exists      [VERIFIABLE]  rank 10
  Check 8: Wikidata entry exists       [VERIFIABLE]  rank 10
  Check 9: Schema sameAs completeness  [VERIFIABLE]  rank 10

Phase 2 / 3 / 4 sub-checks (mention counts, review platforms, Reddit, YouTube,
listicles, LinkedIn, HARO) are NOT in scope here. They are deferred per the
ratified migration plan.

Output JSON shape: see spec lines 84-106. Section verdict for Phase 1:
  PASS    = 3 of 3 pass
  PARTIAL = 1-2 of 3 pass
  FAIL    = 0 of 3 pass
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

USER_AGENT = (
    "AVR-citability/1.0 "
    "(Section5 off-site authority audit; https://citability.dev; "
    "contact: chudi@chudi.dev)"
)

REQUEST_TIMEOUT_SEC = 4
SPARQL_TIMEOUT_SEC = 6  # SPARQL endpoint is intermittently slow; allow more headroom.

SAMEAS_TARGETS = {
    "linkedin": ["linkedin.com"],
    "github": ["github.com"],
    "wikipedia": ["wikipedia.org"],
    "wikidata": ["wikidata.org"],
    "x_twitter": ["x.com", "twitter.com"],
    "medium": ["medium.com"],
}

SAMEAS_MIN_REQUIRED = 4


def _domain_root(url: str) -> str:
    """Strip scheme + www + path, return bare host (e.g. 'github.com')."""
    if not url.startswith("http"):
        url = f"https://{url}"
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _brand_from_domain(host: str) -> str:
    """Default brand inference: capitalize the second-level label.

    'github.com'    -> 'GitHub' is too aggressive (we don't capitalize sub-words);
                       just title-case the SLD: 'Github'. Wikipedia search is
                       case-insensitive enough that 'Github' still hits 'GitHub'.
    'chudi.dev'     -> 'Chudi'
    'sub.example.com' -> 'Example'
    """
    parts = host.split(".")
    if len(parts) >= 2:
        sld = parts[-2]
    else:
        sld = parts[0]
    return sld[:1].upper() + sld[1:]


def _evidence_url(api: str, params: dict[str, Any]) -> str:
    from urllib.parse import urlencode

    return f"{api}?{urlencode(params)}"


def check_wikipedia(brand: str, owner: str | None = None) -> dict[str, Any]:
    """Check 7: Wikipedia entry exists for brand OR operator name.

    Pass criterion: at least one query returns a non-redirect, non-disambiguation
    page. We accept any matching mainspace article title.
    """
    result: dict[str, Any] = {
        "id": "wikipedia-entry-exists",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 10,
    }

    candidates = [c for c in (brand, owner) if c]
    if not candidates:
        result["evidence"].append({"error": "no brand or owner candidate provided"})
        return result

    headers = {"User-Agent": USER_AGENT}
    for term in candidates:
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": term,
            "srlimit": 1,
            "srprop": "snippet",
        }
        try:
            resp = requests.get(
                WIKIPEDIA_API,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            result["evidence"].append({
                "term": term,
                "error": f"wikipedia api failed: {exc}",
            })
            continue

        hits = data.get("query", {}).get("search", []) or []
        if not hits:
            result["evidence"].append({
                "term": term,
                "found": False,
                "source": _evidence_url(WIKIPEDIA_API, params),
            })
            continue

        top = hits[0]
        title = top.get("title", "")
        snippet = (top.get("snippet") or "")[:240]
        page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        is_disambig = (
            "disambiguation" in title.lower()
            or "may refer to" in snippet.lower()
        )
        result["evidence"].append({
            "term": term,
            "found": True,
            "title": title,
            "url": page_url,
            "snippet": snippet,
            "disambiguation_suspected": is_disambig,
        })
        if not is_disambig:
            result["passed"] = True

    return result


def check_wikidata(brand: str, domain_host: str, owner: str | None = None) -> dict[str, Any]:
    """Check 8: Wikidata Q-number exists AND links to brand domain via P856 or P973.

    Strategy: SPARQL query for items whose P856 (official website) or P973
    (described at URL) contains the brand domain. If any item is returned,
    pass.

    Fallback: if SPARQL fails or returns nothing, try wbsearchentities for
    brand + owner and report Q-numbers found (but do NOT mark passed unless
    the domain link is verified).
    """
    result: dict[str, Any] = {
        "id": "wikidata-entry-exists",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 10,
    }

    headers = {"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"}

    safe_host = re.sub(r"[^a-zA-Z0-9.\-]", "", domain_host)
    if len(safe_host) < 3 or "." not in safe_host:
        result["evidence"].append({
            "method": "sparql",
            "error": f"refusing to query Wikidata with too-broad host filter: '{safe_host}'",
        })
        return result

    sparql = (
        "SELECT ?item ?itemLabel ?prop ?website WHERE {{"
        "  {{ ?item wdt:P856 ?website . BIND('P856' AS ?prop) }}"
        "  UNION"
        "  {{ ?item wdt:P973 ?website . BIND('P973' AS ?prop) }}"
        '  FILTER(CONTAINS(STR(?website), "{host}"))'
        '  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}'
        "}} LIMIT 5"
    ).format(host=safe_host)

    try:
        resp = requests.get(
            WIKIDATA_SPARQL,
            params={"query": sparql, "format": "json"},
            headers=headers,
            timeout=SPARQL_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        data = resp.json()
        bindings = data.get("results", {}).get("bindings", []) or []
        for b in bindings:
            qid_uri = b.get("item", {}).get("value", "")
            qid = qid_uri.rsplit("/", 1)[-1] if qid_uri else ""
            label = b.get("itemLabel", {}).get("value", "")
            website = b.get("website", {}).get("value", "")
            prop = b.get("prop", {}).get("value", "")
            if qid:
                result["evidence"].append({
                    "qid": qid,
                    "label": label,
                    "linked_via": prop,
                    "website": website,
                    "method": "sparql",
                    "url": f"https://www.wikidata.org/wiki/{qid}",
                })
                result["passed"] = True
    except (requests.RequestException, ValueError) as exc:
        result["evidence"].append({
            "method": "sparql",
            "error": f"wikidata sparql failed: {exc}",
        })

    if result["passed"]:
        return result

    # Fallback: search by name, then verify the candidate's P856/P973 via wbgetentities.
    candidates = [c for c in (brand, owner) if c]
    for term in candidates:
        try:
            resp = requests.get(
                WIKIDATA_API,
                params={
                    "action": "wbsearchentities",
                    "format": "json",
                    "search": term,
                    "language": "en",
                    "limit": 3,
                    "type": "item",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            result["evidence"].append({
                "term": term,
                "method": "wbsearchentities",
                "error": str(exc),
            })
            continue

        hits = data.get("search", []) or []
        for hit in hits:
            qid = hit.get("id", "")
            if not qid:
                continue
            verified = _verify_qid_links_domain(qid, domain_host)
            if verified is not None:
                result["evidence"].append({
                    "term": term,
                    "method": "wbsearchentities+wbgetentities",
                    "qid": qid,
                    "label": hit.get("label", ""),
                    "description": hit.get("description", ""),
                    "linked_via": verified["prop"],
                    "website": verified["website"],
                    "url": f"https://www.wikidata.org/wiki/{qid}",
                })
                result["passed"] = True
                return result
            else:
                result["evidence"].append({
                    "term": term,
                    "method": "wbsearchentities",
                    "qid_candidate": qid,
                    "label": hit.get("label", ""),
                    "description": hit.get("description", ""),
                    "note": (
                        f"Q-number found by name match but no P856/P973 link to "
                        f"'{domain_host}' verified; not counted as pass."
                    ),
                })

    return result


def _verify_qid_links_domain(qid: str, domain_host: str) -> dict[str, str] | None:
    """Fetch wbgetentities for QID, check P856 (official website) + P973 (described at URL).

    Returns {'prop': 'P856', 'website': '...'} on first match, else None.
    """
    try:
        resp = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "format": "json",
                "ids": qid,
                "props": "claims",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None

    claims = data.get("entities", {}).get(qid, {}).get("claims", {}) or {}
    for prop in ("P856", "P973"):
        for claim in claims.get(prop, []) or []:
            value = (
                claim.get("mainsnak", {})
                     .get("datavalue", {})
                     .get("value", "")
            )
            if isinstance(value, str) and domain_host.lower() in value.lower():
                return {"prop": prop, "website": value}
    return None


def _extract_jsonld_blocks(html: str) -> list[Any]:
    """Pull every JSON-LD script block. Return list of parsed JSON values."""
    soup = BeautifulSoup(html, "html.parser")
    blocks: list[Any] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        blocks.append(parsed)
    return blocks


_JSONLD_MAX_DEPTH = 50


def _walk_jsonld(node: Any, _depth: int = 0) -> list[dict[str, Any]]:
    """Yield every dict node in a JSON-LD tree (handles @graph, lists, nesting).

    Depth-capped at 50 to defend against pathological inputs.
    """
    if _depth > _JSONLD_MAX_DEPTH:
        return []
    out: list[dict[str, Any]] = []
    if isinstance(node, dict):
        out.append(node)
        for v in node.values():
            out.extend(_walk_jsonld(v, _depth + 1))
    elif isinstance(node, list):
        for item in node:
            out.extend(_walk_jsonld(item, _depth + 1))
    return out


def _matches_type(node: dict[str, Any], target: str) -> bool:
    t = node.get("@type")
    if t is None:
        return False
    if isinstance(t, str):
        return t.lower() == target.lower()
    if isinstance(t, list):
        return any(isinstance(x, str) and x.lower() == target.lower() for x in t)
    return False


def _classify_sameas_url(url: str) -> str | None:
    u = url.lower()
    for label, patterns in SAMEAS_TARGETS.items():
        if any(p in u for p in patterns):
            return label
    return None


def check_schema_sameas(url: str) -> dict[str, Any]:
    """Check 9: JSON-LD Person/Organization sameAs includes >=4 of the target set."""
    result: dict[str, Any] = {
        "id": "schema-sameas-completeness",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 10,
    }

    parsed_initial = urlparse(url)
    if parsed_initial.scheme and parsed_initial.scheme not in ("http", "https"):
        result["evidence"].append({
            "error": f"refusing to fetch non-http(s) URL: scheme '{parsed_initial.scheme}'"
        })
        return result
    if not parsed_initial.scheme:
        url = f"https://{url}"
    parsed = urlparse(url)
    if not parsed.netloc:
        result["evidence"].append({"error": "URL has no host component"})
        return result

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        resp.encoding = resp.encoding or "utf-8"
        html = resp.text
    except requests.RequestException as exc:
        result["evidence"].append({"error": f"homepage fetch failed: {exc}"})
        return result

    blocks = _extract_jsonld_blocks(html)
    if not blocks:
        result["evidence"].append({"error": "no JSON-LD script blocks found on homepage"})
        return result

    matched_categories: dict[str, list[str]] = {}
    matched_node_types: list[str] = []

    for block in blocks:
        for node in _walk_jsonld(block):
            if not (_matches_type(node, "Person") or _matches_type(node, "Organization")):
                continue
            same_as = node.get("sameAs")
            if not same_as:
                continue
            urls = same_as if isinstance(same_as, list) else [same_as]
            urls = [u for u in urls if isinstance(u, str)]
            for u in urls:
                cat = _classify_sameas_url(u)
                if cat:
                    matched_categories.setdefault(cat, []).append(u)
            t = node.get("@type")
            matched_node_types.append(t if isinstance(t, str) else json.dumps(t))

    distinct = list(matched_categories.keys())
    result["evidence"].append({
        "node_types_with_sameas": matched_node_types,
        "matched_categories": distinct,
        "matched_count": len(distinct),
        "min_required": SAMEAS_MIN_REQUIRED,
        "matched_urls": matched_categories,
    })

    if len(distinct) >= SAMEAS_MIN_REQUIRED:
        result["passed"] = True

    return result


def _build_recommendations(checks: list[dict[str, Any]]) -> list[str]:
    """Auto-generate recommendations from failed checks, ordered by hierarchy rank.

    Lower rank number = higher priority (per spec line 108).
    """
    failed = [c for c in checks if not c.get("passed")]
    failed.sort(key=lambda c: c.get("signal_hierarchy_rank", 99))

    msgs = []
    for c in failed:
        cid = c["id"]
        rank = c.get("signal_hierarchy_rank", "?")
        if cid == "wikipedia-entry-exists":
            msgs.append(
                f"Pursue a Wikipedia entry for the brand or operator (check 7 failed; "
                f"rank {rank} signal). Notability requires multiple independent secondary sources."
            )
        elif cid == "wikidata-entry-exists":
            msgs.append(
                f"Create a Wikidata Q-item linked to your domain via P856 (official website) "
                f"or P973 (described at URL) at https://www.wikidata.org/wiki/Special:NewItem "
                f"(check 8 failed; rank {rank} signal)."
            )
        elif cid == "schema-sameas-completeness":
            ev = (c.get("evidence") or [{}])[-1]
            cur = ev.get("matched_count", 0)
            need = ev.get("min_required", SAMEAS_MIN_REQUIRED)
            msgs.append(
                f"Extend Person or Organization JSON-LD sameAs on the homepage to include "
                f"at least {need} of: LinkedIn, GitHub, Wikipedia, Wikidata, X/Twitter, Medium "
                f"(currently {cur}; check 9 failed; rank {rank} signal)."
            )
    return msgs


def _section_verdict(checks: list[dict[str, Any]]) -> str:
    passed = sum(1 for c in checks if c.get("passed"))
    if passed == 3:
        return "PASS"
    if passed >= 1:
        return "PARTIAL"
    return "FAIL"


def run_section5(
    url: str,
    brand: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """Run Phase 1 of Section 5 (checks 7, 8, 9). Parallelized to fit a 10s budget.

    Returns the section_5_off_site_authority sub-object per spec lines 84-106,
    wrapped under that key for direct merge into the audit JSON.
    """
    if not url.startswith("http"):
        url = f"https://{url}"
    host = _domain_root(url)
    inferred_brand = brand or _brand_from_domain(host)

    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=3) as pool:
        f7 = pool.submit(check_wikipedia, inferred_brand, owner)
        f8 = pool.submit(check_wikidata, inferred_brand, host, owner)
        f9 = pool.submit(check_schema_sameas, url)
        # Hard cap each result at 9.5s so total stays under the 10s spec budget
        # even if a worker hangs past its per-request timeout.
        per_check_budget = 9.5
        check7 = f7.result(timeout=per_check_budget)
        check8 = f8.result(timeout=per_check_budget)
        check9 = f9.result(timeout=per_check_budget)

    elapsed_ms = int((time.monotonic() - started) * 1000)

    checks = [check7, check8, check9]
    verdict = _section_verdict(checks)
    score = f"{sum(1 for c in checks if c.get('passed'))}/3"

    payload = {
        "section_5_off_site_authority": {
            "phase": 1,
            "phase_scope_note": (
                "Phase 1 implements sub-checks 7, 8, 9 only "
                "(Wikipedia, Wikidata, Schema sameAs). Phases 2-4 deferred per "
                "decision_id dc-20260513T180052Z-9409."
            ),
            "url_audited": url,
            "brand_used": inferred_brand,
            "owner_used": owner,
            "verdict": verdict,
            "score": score,
            "weighted_score": score,
            "elapsed_ms": elapsed_ms,
            "checks": checks,
            "recommendations": _build_recommendations(checks),
        }
    }
    return payload


def main():
    parser = argparse.ArgumentParser(
        description=(
            "AVR Section 5 (Phase 1): Off-Site Authority audit. "
            "Implements Wikipedia, Wikidata, and Schema sameAs checks only. "
            "Phases 2-4 deferred per ratified spec."
        )
    )
    parser.add_argument("url", help="URL to audit (https:// optional)")
    parser.add_argument("--brand", help="Brand name (default: inferred from domain)")
    parser.add_argument("--owner", help="Owner / operator name (used as fallback for Wikipedia + Wikidata)")
    parser.add_argument("-o", "--output", help="Write the result JSON to this path (otherwise stdout)")
    args = parser.parse_args()

    payload = run_section5(args.url, brand=args.brand, owner=args.owner)
    text = json.dumps(payload, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        print(f"\nSaved: {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
