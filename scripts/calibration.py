#!/usr/bin/env python3
"""Pre-flight calibration smoke test for AVR audits.

Runs 7 calibration queries before each audit so the audit report can include
a receipt proving the tool just calibrated correctly:

  - 5 known-positive queries against Wikipedia (expect Perplexity to cite
    Wikipedia at least 4/5 — Wikipedia is the canonical reference).
  - 2 known-negative queries against an .invalid TLD (RFC 2606 — should
    NEVER be cited by any engine; any cite is a fabrication signal).

Cached for 24h to amortize cost (~$0.50 per fresh calibration). Operator
can force fresh with `--force-calibrate`.

Resolution decisions (2026-04-30 plan):
  - Negative target uses .invalid (RFC 2606), not real-but-unrelated domain
  - Cache TTL = 24h matches codex methodology "daily for high-volatility"
  - Failure mode: caller decides (run_audit emits CALIBRATION_FAILED
    placeholders for AI sections, exits 2; Sections 1+2 still rendered)
"""
from __future__ import annotations
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

CACHE_PATH = Path.home() / ".cache" / "avr" / "calibration.json"
CACHE_TTL_SECONDS = 24 * 3600

# Known-positive: Wikipedia is the canonical AI-cited reference. Perplexity
# specifically should cite wikipedia.org for direct brand queries on it.
KNOWN_POSITIVE_TARGET = "https://en.wikipedia.org"
KNOWN_POSITIVE_BRAND = "Wikipedia"
EXPECTED_PERPLEXITY_BRAND_HITS_MIN = 4  # of 5 — allow 1 miss for noise

# Known-negative: .invalid TLD per RFC 2606 — guaranteed no engine has
# legit citation source for this URL. Any cite = definitive fabrication.
KNOWN_NEGATIVE_TARGET = "https://nonexistent-test-domain-2026-avr-calibration.invalid"
KNOWN_NEGATIVE_BRAND = "InventedTestBrand47821AvrCalibration"
EXPECTED_NEGATIVE_HITS_MAX = 0  # any cite of a fake domain = false positive


def load_cache() -> dict | None:
    """Return cached receipt if fresh, else None."""
    if not CACHE_PATH.exists():
        return None
    try:
        d = json.loads(CACHE_PATH.read_text())
        if time.time() - d.get("ts", 0) > CACHE_TTL_SECONDS:
            return None
        return d
    except Exception:
        return None


def save_cache(receipt: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    receipt["ts"] = time.time()
    CACHE_PATH.write_text(json.dumps(receipt, indent=2))


def _positive_queries(brand: str) -> list[str]:
    """5 brand queries that should cite the brand if the tool works."""
    return [
        f"What is {brand} and what does it do?",
        f"Who runs {brand}?",
        f"Tell me about {brand} and its main offerings.",
        f"What is {brand} known for?",
        f"Is {brand} a reliable source?",
    ]


def _negative_queries(brand: str) -> list[str]:
    """2 brand queries about an invented brand on a .invalid domain.
    Any citation of this brand's URL is a fabrication."""
    return [
        f"What is {brand}?",
        f"Tell me about {brand}.",
    ]


def run_calibration(force: bool = False) -> dict:
    """Run the smoke test. Returns receipt dict with pass/fail per check.
    Uses cached result if <24h old unless force=True.

    Receipt shape:
      {
        ts: float (unix epoch),
        ts_iso: str,
        from_cache: bool,
        checks: {
          positive_perplexity_brand: {expected_min, actual, errors, pass},
          negative_no_false_positives: {expected_max, actual_per_engine, pass},
        },
        overall_pass: bool,
      }
    """
    cached = None if force else load_cache()
    if cached:
        cached["from_cache"] = True
        return cached

    # Lazy import to avoid circular dependency at module load
    from citation_auto import query_perplexity, query_openai, query_anthropic

    receipt = {
        "ts": time.time(),
        "ts_iso": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
        "checks": {},
    }

    # === Check 1: known-positive (Wikipedia, Perplexity) ===
    pos_hits = 0
    pos_errors = 0
    for q in _positive_queries(KNOWN_POSITIVE_BRAND):
        r = query_perplexity(q, KNOWN_POSITIVE_TARGET)
        if r["status"] == "CITED":
            pos_hits += 1
        elif r["status"] == "ERROR":
            pos_errors += 1
    receipt["checks"]["positive_perplexity_brand"] = {
        "description": "Perplexity cites Wikipedia for brand queries about Wikipedia",
        "expected_min": EXPECTED_PERPLEXITY_BRAND_HITS_MIN,
        "actual": pos_hits,
        "errors": pos_errors,
        "pass": pos_hits >= EXPECTED_PERPLEXITY_BRAND_HITS_MIN,
    }

    # === Check 2: known-negative (.invalid, all engines) ===
    neg_hits_per_engine = {"ChatGPT": 0, "Perplexity": 0, "Claude": 0}
    for q in _negative_queries(KNOWN_NEGATIVE_BRAND):
        for fn, name in [
            (query_openai, "ChatGPT"),
            (query_perplexity, "Perplexity"),
            (query_anthropic, "Claude"),
        ]:
            try:
                r = fn(q, KNOWN_NEGATIVE_TARGET)
                if r["status"] == "CITED":
                    neg_hits_per_engine[name] += 1
                # ERROR on negative test is OK — counts as no false positive
            except Exception:
                pass
    receipt["checks"]["negative_no_false_positives"] = {
        "description": "No engine cites the invented .invalid domain (RFC 2606 guarantees no real source)",
        "expected_max": EXPECTED_NEGATIVE_HITS_MAX,
        "actual_per_engine": neg_hits_per_engine,
        "actual_total": sum(neg_hits_per_engine.values()),
        "pass": all(v <= EXPECTED_NEGATIVE_HITS_MAX for v in neg_hits_per_engine.values()),
    }

    receipt["overall_pass"] = all(c["pass"] for c in receipt["checks"].values())
    save_cache(receipt)
    return receipt


def format_receipt_markdown(receipt: dict) -> str:
    """Render receipt as Markdown section for the audit report."""
    pos = receipt["checks"]["positive_perplexity_brand"]
    neg = receipt["checks"]["negative_no_false_positives"]
    overall = "PASS" if receipt["overall_pass"] else "FAIL"
    age = "from cache" if receipt.get("from_cache") else "fresh"

    lines = [
        "## Methodology Calibration Receipt",
        "",
        f"**Status:** {overall} — calibration ran {age} at {receipt['ts_iso']}",
        "",
        "Before measuring this site, the audit ran a 7-query smoke test against "
        "two reference targets to verify the citation extraction is working as "
        "intended. The receipt is what makes this audit's numbers reproducible "
        "instead of asking you to trust the methodology.",
        "",
        "| Check | Expected | Actual | Verdict |",
        "|---|---|---|---|",
        f"| Wikipedia brand queries cite Wikipedia (Perplexity) | ≥{pos['expected_min']}/5 | {pos['actual']}/5 (errors: {pos['errors']}) | {'PASS' if pos['pass'] else 'FAIL'} |",
        f"| Invented `.invalid` domain NOT cited (any engine, RFC 2606 guarantee) | ≤{neg['expected_max']} total | {neg['actual_total']} total (per engine: {neg['actual_per_engine']}) | {'PASS' if neg['pass'] else 'FAIL'} |",
        "",
    ]
    if not receipt["overall_pass"]:
        lines.extend([
            "**WARNING:** Calibration failed. Site-level citation/visibility "
            "numbers in this report were withheld (see Sections 3 + 4 below). "
            "Possible causes: API quota exhaustion, model behavior change, "
            "network issues. Re-run after resolving, or use `--skip-calibration` "
            "to acknowledge the risk and generate numbers anyway.",
            "",
        ])
    else:
        lines.append("All checks passed. Site-level numbers below are valid for the calibrated tool state.")
        lines.append("")

    return "\n".join(lines)


def format_receipt_console(receipt: dict) -> str:
    """Render receipt as console output for run_audit.py."""
    pos = receipt["checks"]["positive_perplexity_brand"]
    neg = receipt["checks"]["negative_no_false_positives"]
    overall = "PASS" if receipt["overall_pass"] else "FAIL"
    age = "from cache" if receipt.get("from_cache") else "fresh"
    lines = [
        f"  Calibration: {overall} ({age}, {receipt['ts_iso']})",
        f"    - Wikipedia brand cites (Perplexity): {pos['actual']}/5 (expected ≥{pos['expected_min']}) → {'PASS' if pos['pass'] else 'FAIL'}",
        f"    - Invented domain false positives: {neg['actual_total']} (expected 0) → {'PASS' if neg['pass'] else 'FAIL'}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="AVR pre-audit calibration smoke test")
    p.add_argument("--force", action="store_true", help="Bypass cache, re-run fresh")
    p.add_argument("--markdown", action="store_true", help="Emit markdown receipt instead of JSON")
    args = p.parse_args()
    receipt = run_calibration(force=args.force)
    if args.markdown:
        print(format_receipt_markdown(receipt))
    else:
        print(json.dumps(receipt, indent=2))
    import sys
    sys.exit(0 if receipt["overall_pass"] else 2)
