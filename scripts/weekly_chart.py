#!/usr/bin/env python3
"""Build a weekly line chart of AI visibility deltas for a single domain.

Discovers all `visibility_<domain>_*_summary.json` and
`citations_<domain>_*_summary.json` files in an audit dir, pairs them by
test_date, and writes a PNG line chart of brand-recognition, topic-association,
active-recommendation, and citation-rate over time.

Replaces /tmp/marston_weekly_chart.py which hard-coded the two May-2026
JSON filenames. This version is parameterized: any domain, any audit dir,
any number of weekly data points.

Usage:
  python3 weekly_chart.py \\
      --audit-dir /Users/chudinnorukam/Projects/business/ai-visibility-readiness/sample-audits \\
      --domain marstonorthodontics.com \\
      --brand "Marston Orthodontics" \\
      --output-dir /Users/chudinnorukam/Projects/business/ai-visibility-readiness/sample-audits \\
      --filename-prefix marston_weekly_trend

Exits non-zero with a clear message if fewer than 2 visibility files are found
(a one-point chart is misleading).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def _load_json(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def discover_pairs(audit_dir: str, domain: str) -> list[tuple[datetime, dict, dict | None]]:
    """Find every visibility summary for the domain, sorted by test_date.

    For each visibility file, find the citations summary closest in time
    (same audit run typically shares a date prefix but timestamps differ).
    Returns a list of (datetime, visibility_dict, citations_dict_or_None).
    """
    vis_pattern = os.path.join(audit_dir, f"visibility_{domain}_*_summary.json")
    cit_pattern = os.path.join(audit_dir, f"citations_{domain}_*_summary.json")

    vis_files = [p for p in glob.glob(vis_pattern) if _load_json(p)]
    cit_files = [p for p in glob.glob(cit_pattern) if _load_json(p)]

    cit_by_date: dict[str, list[tuple[datetime, dict]]] = {}
    for p in cit_files:
        c = _load_json(p)
        if not c or "test_date" not in c:
            continue
        try:
            dt = datetime.fromisoformat(c["test_date"])
        except ValueError:
            continue
        cit_by_date.setdefault(dt.date().isoformat(), []).append((dt, c))

    pairs: list[tuple[datetime, dict, dict | None]] = []
    for p in vis_files:
        v = _load_json(p)
        if not v or "test_date" not in v:
            continue
        try:
            vdt = datetime.fromisoformat(v["test_date"])
        except ValueError:
            continue
        same_day = cit_by_date.get(vdt.date().isoformat(), [])
        nearest = None
        if same_day:
            nearest = min(same_day, key=lambda pair: abs((pair[0] - vdt).total_seconds()))[1]
        pairs.append((vdt, v, nearest))

    pairs.sort(key=lambda t: t[0])
    return pairs


def build_series(pairs: list[tuple[datetime, dict, dict | None]]) -> dict:
    dates: list = []
    brand: list = []
    topic: list = []
    recommend: list = []
    citations: list = []

    for dt, v, c in pairs:
        bc = (v.get("by_category") or {})
        br = (bc.get("brand_recognition") or {}).get("rate_pct")
        tp = (bc.get("concept_attribution") or {}).get("rate_pct")
        rc = (bc.get("recommendation") or {}).get("rate_pct")
        cr = c.get("citation_rate_pct") if c else None

        dates.append(dt.date())
        brand.append(br if br is not None else float("nan"))
        topic.append(tp if tp is not None else float("nan"))
        recommend.append(rc if rc is not None else float("nan"))
        citations.append(cr if cr is not None else float("nan"))

    return {
        "dates": dates,
        "brand": brand,
        "topic": topic,
        "recommend": recommend,
        "citations": citations,
    }


def render_chart(
    series: dict,
    brand_label: str,
    output_path: str,
    confidence_note: str | None,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 6.5))

    plots = [
        ("Brand recognition", series["brand"], "#0b66c2"),
        ("Topic association", series["topic"], "#13a155"),
        ("Active recommendation", series["recommend"], "#d97706"),
        ("Citation rate", series["citations"], "#9333ea"),
    ]
    for label, values, color in plots:
        ax.plot(
            series["dates"],
            values,
            marker="o",
            markersize=9,
            linewidth=2.4,
            color=color,
            label=label,
        )
        for d, v in zip(series["dates"], values):
            if v == v:
                ax.annotate(
                    f"{v:.1f}%",
                    (d, v),
                    textcoords="offset points",
                    xytext=(0, 10),
                    ha="center",
                    fontsize=9,
                    color=color,
                )

    ax.set_ylim(0, 100)
    ax.set_ylabel("Score (%)", fontsize=11)
    ax.set_title(
        f"{brand_label}: weekly AI visibility trend",
        fontsize=14,
        fontweight="bold",
        pad=16,
    )
    ax.set_xlabel("Week", fontsize=11)
    ax.grid(True, alpha=0.25, linestyle=":")
    ax.legend(loc="lower right", framealpha=0.95)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate(rotation=0, ha="center")

    if confidence_note:
        fig.text(
            0.5,
            0.02,
            confidence_note,
            ha="center",
            fontsize=8.5,
            color="#555",
        )

    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(output_path, dpi=160, bbox_inches="tight")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--audit-dir", required=True, help="Directory holding the audit summaries")
    parser.add_argument("--domain", required=True, help="Domain (e.g. marstonorthodontics.com)")
    parser.add_argument("--brand", required=True, help="Brand label for chart title")
    parser.add_argument("--output-dir", help="Where to write the PNG (defaults to --audit-dir)")
    parser.add_argument(
        "--filename-prefix",
        help="PNG filename prefix; defaults to <domain-slug>_weekly_trend",
    )
    parser.add_argument(
        "--allow-single-point",
        action="store_true",
        help="Emit chart even when only 1 visibility data point exists (default: require >=2)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or args.audit_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    pairs = discover_pairs(args.audit_dir, args.domain)
    if not pairs:
        sys.stderr.write(
            f"ERROR: no visibility summaries found in {args.audit_dir} matching domain {args.domain}\n"
        )
        return 1
    if len(pairs) < 2 and not args.allow_single_point:
        sys.stderr.write(
            f"ERROR: only {len(pairs)} visibility data point found; need >=2 for a trend chart "
            f"(pass --allow-single-point to override)\n"
        )
        return 2

    series = build_series(pairs)

    confidence_labels = []
    query_sizes = []
    platforms = set()
    for _, v, c in pairs:
        if "confidence_label" in v:
            confidence_labels.append(v["confidence_label"])
        if "total_tests" in v:
            query_sizes.append(v["total_tests"])
        for p in v.get("by_platform", {}).keys():
            platforms.add(p)
        if c:
            for p in c.get("by_platform", {}).keys():
                platforms.add(p)

    notes_parts = []
    notes_parts.append(f"Data points: {len(pairs)}.")
    if query_sizes and len(set(query_sizes)) > 1:
        notes_parts.append(
            f"Query-set size varied across runs ({min(query_sizes)} to {max(query_sizes)} tests); "
            "deltas mix methodology shift with real movement."
        )
    if confidence_labels and all(c == "LOW" for c in confidence_labels):
        notes_parts.append("Confidence label on all runs: LOW.")
    confidence_note = " ".join(notes_parts) if notes_parts else None

    slug = args.filename_prefix or f"{args.domain.replace('.', '_')}_weekly_trend"
    date_suffix = series["dates"][-1].strftime("%Y%m%d")
    out_png = os.path.join(output_dir, f"{slug}_{date_suffix}.png")

    render_chart(series, args.brand, out_png, confidence_note)
    print(out_png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
