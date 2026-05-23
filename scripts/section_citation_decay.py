#!/usr/bin/env python3
"""
AVR §7 Citation Decay Rate Audit

Implements the Citation Decay Rate, Citation half-life, Decay slope,
Displacement event detection, and Citation Retention Rate signals defined
by AVR v1.1.0 per the codex node
[[avr-framework-v1-1-0-upgrade-citation-decay-rate-the-moat-insight-ratified-2026-05-22-with-two-sub-term-renames]].

Operator-coined keystone metric for citability.dev — first-to-market vs.
Semrush / BrightEdge / Conductor (none of which surface citation duration
as a tracked dimension as of 2026-05-22 fetch).

Five derived metrics, all [VERIFIABLE] (computed from observed Bing AI
Performance CSV data; no API spend; no projection beyond observed window):

  M1: Citation Decay Rate           (per-week aggregate decline pct)
  M2: Citation half-life            (days from peak to 50% decline; null if undecayed)
  M3: Decay slope                   (linear regression slope of post-peak citations/day)
  M4: Displacement event count      (week-over-week drops > 1.5 stdev from mean delta)
  M5: Citation Retention Rate       (oldest-month-citations / current-month-citations)

Source: ~/Downloads/chudi.dev_AIPerformanceOverviewStats_*.csv (per
/citability bing-citations operation spec). Reads daily-granularity Bing AI
Copilot citation data. If no CSV available, returns DATA-INSUFFICIENT verdict
with a recommendation to export from bing.com/webmasters first.

Verdict bands:
  GROWING               = Decay slope > 0 AND week-over-week trend up
  STABLE                = |Decay slope| < threshold AND retention >= 80%
  DECLINING             = Decay slope < 0 AND retention < 80%
  DATA-INSUFFICIENT     = < 30 days of data

Cost: $0 (CSV file read + statistical computation; no API spend).
"""

import argparse
import csv
import glob
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


CSV_GLOB_DEFAULT = str(Path.home() / "Downloads" / "chudi.dev_AIPerformanceOverviewStats_*.csv")
SNAPSHOT_PATH = Path.home() / ".claude" / "state" / "bing-citations-snapshot.json"

DECAY_SLOPE_STABLE_THRESHOLD = 0.05  # citations/day; under this is "flat"
RETENTION_PASS_THRESHOLD = 0.80
MIN_DAYS_FOR_VALID_AUDIT = 30
DISPLACEMENT_STDEV_MULTIPLIER = 1.5


def find_latest_csv(glob_pattern: str | None = None) -> str | None:
    pattern = glob_pattern or CSV_GLOB_DEFAULT
    matches = glob.glob(pattern)
    if not matches:
        return None
    # Sort by mtime descending; newest first.
    matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return matches[0]


def parse_bing_csv(path: str) -> list[dict[str, Any]]:
    """Return [{date: date, citations: int, cited_pages: int}, ...] sorted ascending by date."""
    rows = []
    with open(path, encoding="utf-8-sig") as f:  # utf-8-sig handles BOM
        reader = csv.DictReader(f)
        for r in reader:
            date_str = r.get("Date", "").strip()
            if not date_str:
                continue
            # Date format observed: "M/D/YYYY 12:00:00 AM"
            m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
            if not m:
                continue
            mm, dd, yyyy = m.groups()
            try:
                d = datetime(int(yyyy), int(mm), int(dd)).date()
            except ValueError:
                continue
            try:
                citations = int(r.get("Citations", "0").strip() or 0)
                cited_pages = int(r.get("Cited Pages", "0").strip() or 0)
            except (ValueError, AttributeError):
                citations, cited_pages = 0, 0
            rows.append({"date": d, "citations": citations, "cited_pages": cited_pages})
    rows.sort(key=lambda r: r["date"])
    return rows


def bucket_by_week(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Bucket daily rows by ISO week (Monday-start). Returns {week_iso: {citations_sum, days_in_bucket}}."""
    buckets: dict[str, dict[str, Any]] = {}
    for r in rows:
        # ISO week (year, week) tuple — use Monday-of-week as the bucket key.
        d = r["date"]
        monday = d - timedelta(days=d.weekday())
        key = monday.isoformat()
        if key not in buckets:
            buckets[key] = {"week_start": monday, "citations_sum": 0, "days_in_bucket": 0, "cited_pages_sum": 0}
        buckets[key]["citations_sum"] += r["citations"]
        buckets[key]["days_in_bucket"] += 1
        buckets[key]["cited_pages_sum"] += r["cited_pages"]
    return dict(sorted(buckets.items()))


def compute_decay_slope(rows: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    """Linear regression slope of citations/day over the observation window.

    Returns (slope_citations_per_day, evidence_dict).
    """
    if len(rows) < 2:
        return 0.0, {"reason": "insufficient_data_for_slope"}
    # Use day-index as x, citations as y.
    n = len(rows)
    xs = list(range(n))
    ys = [r["citations"] for r in rows]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    slope = cov / var_x if var_x else 0.0
    return slope, {"n_days": n, "mean_citations_per_day": round(mean_y, 2), "slope_citations_per_day": round(slope, 4)}


def detect_displacement_events(weekly: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Identify week-over-week drops exceeding 1.5 * stdev of weekly deltas."""
    if len(weekly) < 4:
        return []
    keys = list(weekly.keys())
    weekly_totals = [weekly[k]["citations_sum"] for k in keys]
    deltas = [weekly_totals[i] - weekly_totals[i - 1] for i in range(1, len(weekly_totals))]
    if len(deltas) < 2:
        return []
    try:
        stdev_delta = statistics.stdev(deltas)
    except statistics.StatisticsError:
        return []
    mean_delta = statistics.mean(deltas)
    threshold = mean_delta - (DISPLACEMENT_STDEV_MULTIPLIER * stdev_delta)
    events = []
    for i, d in enumerate(deltas):
        if d < threshold:
            events.append({
                "week_start": keys[i + 1],
                "delta": d,
                "prior_week_citations": weekly_totals[i],
                "this_week_citations": weekly_totals[i + 1],
                "pct_drop": round((1 - weekly_totals[i + 1] / max(weekly_totals[i], 1)) * 100, 1),
            })
    return events


def compute_half_life(rows: list[dict[str, Any]]) -> int | None:
    """Return days from peak-week to the START of a SUSTAINED 4-week below-50% window.

    Calibration update 2026-05-22: require sustained 4-week below-50% before
    declaring half-life crossed. Previous version flagged any single week
    below 50% of peak, which produced false-positive half-life signals on
    overall-growing data (a brief intra-window dip would trigger the metric
    even though the underlying trend was upward). Smoke-test 2026-05-22 on
    chudi.dev Bing CSV showed GROWING + 21d half-life simultaneously —
    internally contradictory; this fix resolves the contradiction.

    Returns None if the data never sustains 4 consecutive weeks below 50%.
    """
    SUSTAINED_WEEKS_BELOW_HALF = 4
    if len(rows) < 14:
        return None
    weekly = bucket_by_week(rows)
    if len(weekly) < SUSTAINED_WEEKS_BELOW_HALF + 2:
        return None
    keys = list(weekly.keys())
    weekly_totals = [(k, weekly[k]["citations_sum"]) for k in keys]
    peak_week_key, peak = max(weekly_totals, key=lambda kv: kv[1])
    if peak == 0:
        return None
    target = peak / 2.0
    peak_idx = next(i for i, (k, _) in enumerate(weekly_totals) if k == peak_week_key)
    # Scan post-peak weeks for the first index where the SUBSEQUENT 4 weeks
    # ALL stay below 50% of peak. That sustained-window start is the
    # half-life crossing event.
    for start in range(peak_idx + 1, len(weekly_totals) - SUSTAINED_WEEKS_BELOW_HALF + 1):
        window = weekly_totals[start:start + SUSTAINED_WEEKS_BELOW_HALF]
        if all(w[1] <= target for w in window):
            half_life_weeks = start - peak_idx
            return half_life_weeks * 7
    return None  # never sustained 4-week below 50%


def compute_retention_rate(rows: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    """Citations from oldest 30-day window / citations from newest 30-day window."""
    if len(rows) < 60:
        return 1.0, {"reason": "insufficient_data_for_retention", "n_days": len(rows)}
    earliest_window = rows[:30]
    latest_window = rows[-30:]
    earliest_sum = sum(r["citations"] for r in earliest_window)
    latest_sum = sum(r["citations"] for r in latest_window)
    if earliest_sum == 0:
        # If we started from zero, retention isn't a meaningful concept; treat as 1.0
        return 1.0, {"earliest_sum": 0, "latest_sum": latest_sum, "interpretation": "zero_baseline"}
    retention = latest_sum / earliest_sum
    return retention, {
        "earliest_30d_sum": earliest_sum,
        "latest_30d_sum": latest_sum,
        "retention_rate": round(retention, 3),
        "earliest_window_start": rows[0]["date"].isoformat(),
        "latest_window_end": rows[-1]["date"].isoformat(),
    }


def section_verdict(slope: float, retention: float, n_days: int) -> str:
    if n_days < MIN_DAYS_FOR_VALID_AUDIT:
        return "DATA-INSUFFICIENT"
    if slope > DECAY_SLOPE_STABLE_THRESHOLD and retention >= RETENTION_PASS_THRESHOLD:
        return "GROWING"
    if abs(slope) < DECAY_SLOPE_STABLE_THRESHOLD and retention >= RETENTION_PASS_THRESHOLD:
        return "STABLE"
    if slope < -DECAY_SLOPE_STABLE_THRESHOLD or retention < RETENTION_PASS_THRESHOLD:
        return "DECLINING"
    return "STABLE"


def confidence_band(n_days: int) -> str:
    if n_days < 14:
        return "LOW"
    if n_days < 60:
        return "MODERATE"
    return "HIGH"


def run_section_citation_decay(csv_path: str | None = None) -> dict[str, Any]:
    actual_csv = csv_path or find_latest_csv()
    if not actual_csv or not os.path.exists(actual_csv):
        return {
            "section_id": "section_citation_decay",
            "section_name": "Citation Decay Rate (the moat metric)",
            "section_verdict": "DATA-INSUFFICIENT",
            "error": "no_bing_csv_found",
            "recommendations": [{
                "id": "rec-export-bing-csv",
                "priority": 1,
                "action": (
                    "Export the Bing AI Performance Report CSV from "
                    "bing.com/webmasters -> AI Performance Report -> Export CSV, save to "
                    f"~/Downloads/chudi.dev_AIPerformanceOverviewStats_*.csv, then re-run this op."
                ),
            }],
            "cost_usd": 0.0,
            "label": "VERIFIABLE",
        }

    rows = parse_bing_csv(actual_csv)
    if len(rows) < MIN_DAYS_FOR_VALID_AUDIT:
        return {
            "section_id": "section_citation_decay",
            "section_name": "Citation Decay Rate (the moat metric)",
            "section_verdict": "DATA-INSUFFICIENT",
            "n_days": len(rows),
            "csv_source": actual_csv,
            "recommendation": (
                f"Need at least {MIN_DAYS_FOR_VALID_AUDIT} days of Bing AI data; "
                f"current export covers {len(rows)} days. Wait for more data or check the export window."
            ),
            "cost_usd": 0.0,
            "label": "VERIFIABLE",
        }

    weekly = bucket_by_week(rows)
    slope, slope_evidence = compute_decay_slope(rows)
    half_life_days = compute_half_life(rows)
    retention, retention_evidence = compute_retention_rate(rows)
    displacement_events = detect_displacement_events(weekly)

    # Citation Decay Rate as a per-week aggregate: (oldest_weeks_avg - newest_weeks_avg) / oldest_weeks_avg
    weekly_keys = list(weekly.keys())
    if len(weekly_keys) >= 4:
        early_avg = statistics.mean(weekly[k]["citations_sum"] for k in weekly_keys[:2])
        late_avg = statistics.mean(weekly[k]["citations_sum"] for k in weekly_keys[-2:])
        decay_rate_pct = round((1 - late_avg / max(early_avg, 1)) * 100, 1) if early_avg > 0 else 0
    else:
        decay_rate_pct = 0
        early_avg = 0
        late_avg = 0

    n_days = len(rows)
    verdict = section_verdict(slope, retention, n_days)
    conf = confidence_band(n_days)

    recommendations = []
    if verdict == "DECLINING":
        recommendations.append({
            "id": "rec-investigate-decline",
            "priority": 1,
            "action": (
                f"Citations declining: slope {slope:.3f}/day, retention {retention:.1%}. "
                f"Found {len(displacement_events)} displacement event(s). Investigate competing "
                "content published around displacement weeks; consider counter-content with stronger "
                "Fact-Block Density (per AVR v1.1.0 §3)."
            ),
        })
    if half_life_days and half_life_days < 30:
        recommendations.append({
            "id": "rec-short-half-life",
            "priority": 2,
            "action": (
                f"Citation half-life is short ({half_life_days} days from peak to 50% drop). "
                "Short half-lives indicate brittle citation foundation; topical authority may be insufficient."
            ),
        })
    if not recommendations and verdict != "GROWING":
        recommendations.append({
            "id": "rec-maintain-stable",
            "priority": 3,
            "action": "Citations stable. Continue current content cadence; re-audit monthly.",
        })

    return {
        "section_id": "section_citation_decay",
        "section_name": "Citation Decay Rate (the moat metric)",
        "csv_source": actual_csv,
        "section_verdict": verdict,
        "confidence": conf,
        "window": {
            "start_date": rows[0]["date"].isoformat(),
            "end_date": rows[-1]["date"].isoformat(),
            "n_days": n_days,
            "weeks": len(weekly),
        },
        "metrics": {
            "citation_decay_rate_pct": decay_rate_pct,
            "citation_half_life_days": half_life_days,
            "decay_slope_citations_per_day": round(slope, 4),
            "displacement_event_count": len(displacement_events),
            "citation_retention_rate": round(retention, 3),
        },
        "evidence": {
            "decay_slope": slope_evidence,
            "retention": retention_evidence,
            "displacement_events": displacement_events[:5],
            "weekly_totals_summary": {
                "weeks_observed": len(weekly),
                "peak_week_citations": max((w["citations_sum"] for w in weekly.values()), default=0),
                "early_2wk_avg": round(early_avg, 1),
                "late_2wk_avg": round(late_avg, 1),
            },
        },
        "recommendations": recommendations,
        "spec_version": "AVR v1.1.0 §7 (Citation Decay Rate keystone moat metric, ratified 2026-05-22)",
        "cost_usd": 0.0,
        "label": "VERIFIABLE",
    }


def main():
    parser = argparse.ArgumentParser(
        description="AVR §7 Citation Decay Rate Audit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--csv", help="Path to Bing AI Performance CSV (default: latest in ~/Downloads/)")
    parser.add_argument("-o", "--output", help="Write JSON result to this path")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress prints")
    args = parser.parse_args()

    if not args.quiet:
        print(f"[section-decay] computing Citation Decay Rate ...", file=sys.stderr)
    result = run_section_citation_decay(args.csv)
    if not args.quiet:
        print(f"[section-decay] verdict: {result['section_verdict']} (confidence: {result.get('confidence', 'N/A')})", file=sys.stderr)
        if "metrics" in result:
            m = result["metrics"]
            print(f"  decay rate: {m['citation_decay_rate_pct']}%/window", file=sys.stderr)
            print(f"  half-life: {m['citation_half_life_days']} days" if m["citation_half_life_days"] else "  half-life: not yet decayed to 50%", file=sys.stderr)
            print(f"  decay slope: {m['decay_slope_citations_per_day']} citations/day", file=sys.stderr)
            print(f"  displacement events: {m['displacement_event_count']}", file=sys.stderr)
            print(f"  retention rate: {m['citation_retention_rate']}", file=sys.stderr)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
