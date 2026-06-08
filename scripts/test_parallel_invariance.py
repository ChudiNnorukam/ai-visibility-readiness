#!/usr/bin/env python3
"""Metric-invariance regression test for the parallelized live phases.

Proves that running the visibility + citation phases CONCURRENTLY
(PER_PLATFORM_CONCURRENCY=4) produces byte-identical summaries and raw results
to running them SERIALLY (=1), given deterministic (stubbed) engine responses.

This is the guard the 2026-06-08 parallelization rests on: parallelism must
never change a paying client's numbers. Engine calls are stubbed so the only
variable is serial-vs-parallel execution; any difference = a concurrency bug
(shared-state race, lost result, reordering). Run: python3 test_parallel_invariance.py
"""
import copy
import hashlib
import json
import tempfile

import visibility_auto as vis
import citation_auto as cit

BRAND = "Marston Orthodontics"
URL = "https://marstonorthodontics.com"
DOMAIN = "marstonorthodontics.com"
PLATFORMS = ["openai", "perplexity", "anthropic", "gemini"]


def _strip_volatile(d):
    """Drop timestamp-ish keys so only the metrics are compared."""
    volatile = {"test_date", "generated_at", "timestamp", "date"}
    if isinstance(d, dict):
        return {k: _strip_volatile(v) for k, v in d.items() if k not in volatile}
    if isinstance(d, list):
        return [_strip_volatile(x) for x in d]
    return d


def _vis_stub(func, query, max_retries=2):
    """Deterministic visibility response: a stable mix of visible/not by query."""
    h = int(hashlib.sha256(query.encode()).hexdigest(), 16) % 3
    if h == 0:
        return (f"{BRAND} at {URL} is excellent. Marston Orthodontics offers braces and Invisalign.", None)
    if h == 1:
        return ("There are many orthodontists in the area; consider local clear-aligner providers.", None)
    return (f"I recommend {BRAND} ({URL}) for Invisalign and clear aligners.", None)


def _cit_stub_factory(pname):
    def fn(query, target_url):
        h = int(hashlib.sha256((pname + query).encode()).hexdigest(), 16) % 2
        status = "CITED" if h == 0 else "NOT_CITED"
        return {
            "status": status,
            "platform": pname,
            "query": query,
            "response_snippet": "stub",
            "cited_url": target_url if status == "CITED" else None,
        }
    return fn


def _run(module, concurrency, runner):
    module.PER_PLATFORM_CONCURRENCY = concurrency
    with tempfile.TemporaryDirectory() as d:
        return _strip_volatile(runner(d))


def test_visibility_invariance():
    vis._check_keys = lambda: {p: True for p in PLATFORMS}
    vis._query_with_retry = _vis_stub

    def runner(d):
        return vis.run_visibility_test(
            target_url=URL, brand_name=BRAND, owner_name="Dr. Blake Marston",
            topics=["orthodontics", "braces", "Invisalign"], output_dir=d, platforms=PLATFORMS,
        )

    serial = _run(vis, 1, runner)
    parallel = _run(vis, 4, runner)
    assert serial == parallel, "VISIBILITY summary differs between serial and parallel"
    print(f"  visibility: serial == parallel  (brand_rate keys: "
          f"{serial.get('by_category', {}).get('brand_recognition', {})})")


def test_citation_invariance():
    cit._check_keys = lambda: {p: True for p in PLATFORMS}
    cit.PLATFORM_FUNCTIONS = {p: _cit_stub_factory(cit.PLATFORM_NAMES[p]) for p in PLATFORMS}

    def runner(d):
        return cit.run_citation_test(
            target_url=URL, topics=["orthodontics", "braces", "Invisalign"],
            output_dir=d, platforms=PLATFORMS, brand=BRAND,
        )

    serial = _run(cit, 1, runner)
    parallel = _run(cit, 4, runner)
    assert serial == parallel, "CITATION summary differs between serial and parallel"
    print(f"  citation:   serial == parallel  (overall: "
          f"{serial.get('cited')}/{serial.get('testable')} cited)")


if __name__ == "__main__":
    test_visibility_invariance()
    test_citation_invariance()
    print("\nPASS: parallel execution is metric-invariant vs serial for both phases.")
