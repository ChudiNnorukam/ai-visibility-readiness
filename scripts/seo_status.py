#!/usr/bin/env python3
"""
SEO + GEO Status Roll-Up
========================
One screen of truth for the SEO / AI-SEO automation surface. Aggregates the
report artifacts produced by the (otherwise scattered) cron jobs into a single
view so you never have to open five files to know where things stand:

  - Last activity      : freshness per source; flags any source >7 days stale
                         (a stale source means that cron silently stopped firing)
  - Open failures      : ranking P0/P1/P2 findings + entity-audit pass/fail + CTR gaps
  - Rank / traffic      : GSC checkpoint week-over-week deltas (impressions/clicks/pages)
  - AI-citation         : GEO tracker (OpenAI / Perplexity) + Bing AI citations (if present)

Read-only. Safe to run anytime. Invoked by seo_orchestrator.sh at the end of
each cron cadence, and runnable standalone for a quick status check.

Usage:
  python3 seo_status.py            # one-screen text status (default)
  python3 seo_status.py --json     # machine-readable JSON (for logs / dashboards)
  python3 seo_status.py --stale-days 14   # change the staleness threshold
"""

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()

# ---------------------------------------------------------------------------
# Source paths (absolute; each loaded defensively so a missing file is "n/a")
# ---------------------------------------------------------------------------
BLOG = HOME / "Projects" / "active" / "chudi-blog"
AIVR = HOME / "Projects" / "business" / "ai-visibility-readiness"

SRC = {
    "entity": BLOG / "content" / "entity-audit.json",
    "ranking": BLOG / "content" / "ranking-agent-report.json",
    "geo": BLOG / "content" / "geo-citations.json",
    "gsc_checkpoint": HOME / ".claude" / "cron" / "gsc-checkpoint-log.json",
    "ctr_glob": str(AIVR / "reports" / "gsc-ctr-gaps-*.md"),
    # Optional: written by gsc-ctr-pr-agent.py when the Bing pull is enabled.
    "bing": AIVR / "reports" / "bing-query-stats-latest.json",
}

DEFAULT_STALE_DAYS = 7


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def load_json(path: Path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as exc:  # malformed / unreadable
        return {"__error__": str(exc)}


def parse_ts(s):
    """Parse an ISO timestamp or YYYY-MM-DD date into a tz-aware UTC datetime."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s[:10])  # date-only fallback
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def age_days(ts):
    if ts is None:
        return None
    return (datetime.now(timezone.utc) - ts).days


def freshness(ts, stale_days):
    """Return (age_days, label) where label is e.g. '2d' or '20d STALE'."""
    a = age_days(ts)
    if a is None:
        return None, "n/a"
    flag = " STALE" if a > stale_days else ""
    return a, f"{a}d{flag}"


# ---------------------------------------------------------------------------
# Per-source extractors -> normalized dicts
# ---------------------------------------------------------------------------

def read_ranking():
    d = load_json(SRC["ranking"])
    if not isinstance(d, dict) or "__error__" in (d or {}):
        return {"ok": False, "ts": None, "p0": None, "p1": None, "p2": None, "total": None}
    return {
        "ok": True,
        "ts": parse_ts(d.get("generatedAt")),
        "p0": d.get("p0Count", 0),
        "p1": d.get("p1Count", 0),
        "p2": d.get("p2Count", 0),
        "total": d.get("totalFindings", 0),
    }


def read_entity():
    d = load_json(SRC["entity"])
    if not isinstance(d, dict) or "__error__" in (d or {}):
        return {"ok": False, "ts": None, "pass": None, "blocks": None}
    return {
        "ok": True,
        "ts": parse_ts(d.get("generatedAt")),
        "pass": d.get("pass"),
        "blocks": d.get("blocksFound"),
    }


def read_geo():
    d = load_json(SRC["geo"])
    if not isinstance(d, dict) or not isinstance(d.get("citations"), list) or not d["citations"]:
        return {"ok": False, "ts": None, "questions": None, "openai_cited": None,
                "perplexity_cited": None, "status": None}
    last = d["citations"][-1]
    r = last.get("results", {}) if isinstance(last, dict) else {}
    inner = r.get("results", []) if isinstance(r, dict) else []
    questions = len(inner) if isinstance(inner, list) else None
    return {
        "ok": True,
        "ts": parse_ts(r.get("generatedAt") or last.get("date")),
        "questions": questions,
        "openai_cited": r.get("openaiCitedCount"),
        "perplexity_cited": r.get("perplexityCitedCount"),
        "perplexity_available": r.get("perplexityAvailable"),
        "status": r.get("status"),
    }


def read_gsc_checkpoint():
    d = load_json(SRC["gsc_checkpoint"])
    if not isinstance(d, list) or not d:
        return {"ok": False, "ts": None, "runs": 0, "sites": {}}
    last = d[-1]
    return {
        "ok": True,
        "ts": parse_ts(last.get("generatedAt") or last.get("date")),
        "runs": len(d),
        "sites": last.get("sites", {}) if isinstance(last, dict) else {},
    }


def read_ctr():
    """Latest gsc-ctr-gaps report: parse the gap count + property + date from the markdown head."""
    reps = sorted(glob.glob(SRC["ctr_glob"]))
    if not reps:
        return {"ok": False, "ts": None, "gaps": None, "path": None}
    path = Path(reps[-1])
    gaps, prop, gen = None, None, None
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[:20]:
            low = line.lower()
            if "page-query pairs" in low and "found" in low:
                # e.g. "Found **9 page-query pairs** with significant CTR gaps."
                for tok in line.replace("**", " ").split():
                    if tok.isdigit():
                        gaps = int(tok)
                        break
            elif line.startswith("**Generated:**"):
                gen = line.split("**", 2)[-1].strip()
            elif line.startswith("**Property:**"):
                prop = line.split("**", 2)[-1].strip()
    except Exception:
        pass
    # Prefer the in-report generated timestamp; fall back to the date in the filename.
    ts = parse_ts(gen) or parse_ts(path.stem.replace("gsc-ctr-gaps-", ""))
    return {"ok": True, "ts": ts, "gaps": gaps, "path": str(path), "property": prop}


def read_bing():
    """Optional Bing AI-citation / query-stats snapshot (written by the CTR agent's BWT pull)."""
    d = load_json(SRC["bing"])
    if not isinstance(d, dict) or "__error__" in (d or {}):
        return {"ok": False, "ts": None, "ai_citations": None, "queries": None}
    return {
        "ok": True,
        "ts": parse_ts(d.get("generatedAt")),
        "ai_citations": d.get("aiCitations"),
        "queries": d.get("queryCount"),
        "property": d.get("property"),
    }


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def collect(stale_days):
    return {
        "ranking": read_ranking(),
        "entity": read_entity(),
        "geo": read_geo(),
        "gsc": read_gsc_checkpoint(),
        "ctr": read_ctr(),
        "bing": read_bing(),
        "_meta": {"stale_days": stale_days,
                  "generated": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    }


def _pct(num, den):
    if num is None or not den:
        return None
    return round(100.0 * num / den, 1)


# ---------------------------------------------------------------------------
# Text renderer
# ---------------------------------------------------------------------------

def render_text(s, stale_days):
    L = []
    bar = "=" * 64
    L.append(bar)
    L.append("  SEO + GEO STATUS ROLL-UP   (chudi.dev)")
    L.append(f"  generated {s['_meta']['generated']}   stale threshold {stale_days}d")
    L.append(bar)

    # --- Last activity (freshness per source) ---------------------------
    L.append("")
    L.append("LAST ACTIVITY (per source)")
    rows = [
        ("ranking-agent", s["ranking"]["ts"]),
        ("entity-audit", s["entity"]["ts"]),
        ("geo-citations", s["geo"]["ts"]),
        ("gsc-checkpoint", s["gsc"]["ts"]),
        ("ctr-report", s["ctr"]["ts"]),
    ]
    if s["bing"]["ok"]:
        rows.append(("bing-query-stats", s["bing"]["ts"]))
    stale_sources = []
    for name, ts in rows:
        a, label = freshness(ts, stale_days)
        when = ts.date().isoformat() if ts else "n/a"
        mark = "!" if (a is not None and a > stale_days) else " "
        L.append(f"  {mark} {name:<18} {when:<12} ({label})")
        if a is not None and a > stale_days:
            stale_sources.append(name)

    # --- Open failures --------------------------------------------------
    L.append("")
    L.append("OPEN FAILURES")
    rk = s["ranking"]
    if rk["ok"]:
        L.append(f"  ranking findings  P0={rk['p0']}  P1={rk['p1']}  P2={rk['p2']}  (total {rk['total']})")
    else:
        L.append("  ranking findings  n/a")
    en = s["entity"]
    if en["ok"]:
        verdict = "PASS" if en["pass"] else "FAIL"
        L.append(f"  entity audit      {verdict}  (schema blocks found: {en['blocks']})")
    else:
        L.append("  entity audit      n/a")
    ct = s["ctr"]
    if ct["ok"]:
        L.append(f"  CTR gaps          {ct['gaps']} page-query pairs below expected CTR")
    else:
        L.append("  CTR gaps          n/a")

    # --- Rank / traffic deltas ------------------------------------------
    L.append("")
    L.append("RANK / TRAFFIC (GSC checkpoint, week-over-week)")
    gsc = s["gsc"]
    if gsc["ok"] and gsc["sites"]:
        if gsc["runs"] < 2:
            L.append(f"  baseline only ({gsc['runs']} run) - deltas available after the next checkpoint")
        for site, m in gsc["sites"].items():
            di, dc, dp = m.get("deltaImpressions"), m.get("deltaClicks"), m.get("deltaPages")
            def d(x):
                return "+%d" % x if isinstance(x, (int, float)) and x >= 0 else (str(x) if x is not None else "--")
            L.append(f"  {site:<16} impr={m.get('impressions')} ({d(di)})  "
                     f"clicks={m.get('clicks')} ({d(dc)})  pages={m.get('pages')} ({d(dp)})")
    else:
        L.append("  n/a")

    # --- AI citation ----------------------------------------------------
    L.append("")
    L.append("AI-CITATION RATE")
    geo = s["geo"]
    if geo["ok"]:
        rate = _pct(geo["openai_cited"], geo["questions"])
        rate_s = f"{rate}%" if rate is not None else "n/a"
        L.append(f"  OpenAI (GEO probe) {geo['openai_cited']}/{geo['questions']} cited = {rate_s}   [{geo['status']}]")
        if geo.get("perplexity_available"):
            prate = _pct(geo["perplexity_cited"], geo["questions"])
            L.append(f"  Perplexity         {geo['perplexity_cited']}/{geo['questions']} cited = {prate}%")
        else:
            L.append("  Perplexity         unavailable this run")
    else:
        L.append("  GEO probe          n/a")
    bg = s["bing"]
    if bg["ok"]:
        L.append(f"  Bing/Copilot       {bg['ai_citations']} AI citations across {bg['queries']} queries")
    else:
        L.append("  Bing/Copilot       not pulled (enable BWT in gsc-ctr-pr-agent)")

    # --- Headline -------------------------------------------------------
    L.append("")
    L.append("-" * 64)
    alerts = []
    if stale_sources:
        alerts.append(f"{len(stale_sources)} stale source(s): {', '.join(stale_sources)}")
    if rk["ok"] and (rk["p0"] or 0) > 0:
        alerts.append(f"{rk['p0']} P0 ranking finding(s)")
    if en["ok"] and en["pass"] is False:
        alerts.append("entity audit FAILING")
    if ct["ok"] and ct["gaps"]:
        alerts.append(f"{ct['gaps']} CTR gap(s)")
    if alerts:
        L.append("ATTENTION: " + "; ".join(alerts))
    else:
        L.append("ATTENTION: none - all sources fresh and clean")
    L.append("-" * 64)
    return "\n".join(L)


# ---------------------------------------------------------------------------
# JSON renderer (datetimes -> iso strings)
# ---------------------------------------------------------------------------

def jsonify(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: jsonify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [jsonify(v) for v in obj]
    return obj


def main():
    ap = argparse.ArgumentParser(description="One-screen SEO + GEO status roll-up.")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS,
                    help=f"flag a source stale after this many days (default {DEFAULT_STALE_DAYS})")
    args = ap.parse_args()

    s = collect(args.stale_days)
    if args.json:
        print(json.dumps(jsonify(s), indent=2))
    else:
        print(render_text(s, args.stale_days))


if __name__ == "__main__":
    main()
