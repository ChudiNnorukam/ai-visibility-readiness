#!/usr/bin/env python3
"""Weekly citation scoreboard for the SEO/AVR org (wargame 03 MOVE 2).

One row per week: the three numbers the org steers by.
  - live_retrieval_citation_rate: /citability --personal (live-retrieval) cited/total
  - bing_per_day:                 Bing WMT AI Copilot citations/day (operator CSV export)
  - gsc_clicks_7d:                Google Search Console clicks, trailing 7 days

Append-only JSONL so history is never rewritten. Staleness guard: if the newest
row is >9 days old, the run fires a loud alarm (and chiron_notify if present) so a
dead cadence can't masquerade as "still fine".

ponytail: stdlib only, one file, no deps. A cron/loop or a weekly session runs:
  python3 citation_scoreboard.py add --citation-rate 0.636 --gsc-clicks 52 [--bing-per-day 7.13] [--note "..."]
  python3 citation_scoreboard.py show
"""
import argparse, json, os, shutil, subprocess, sys
from datetime import date, datetime

BOARD = os.path.join(os.path.dirname(__file__), "..", "sample-audits", "citation-scoreboard.jsonl")
STALE_DAYS = 9


def _rows():
    if not os.path.exists(BOARD):
        return []
    with open(BOARD) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _staleness_alarm(rows):
    if not rows:
        return
    last = rows[-1]["date"]
    gap = (date.today() - datetime.strptime(last, "%Y-%m-%d").date()).days
    if gap > STALE_DAYS:
        msg = f"[SCOREBOARD STALE] last citation-scoreboard row is {gap}d old ({last}); weekly cadence has lapsed."
        print("!" * 70 + f"\n{msg}\n" + "!" * 70, file=sys.stderr)
        # ponytail: fire chiron_notify only if it's on PATH; loud stderr is the floor.
        if shutil.which("chiron_notify"):
            try:
                subprocess.run(["chiron_notify", msg], timeout=10, check=False)
            except Exception:
                pass


def add(args):
    rows = _rows()
    _staleness_alarm(rows)  # check the PRIOR newest before appending this week's row
    row = {
        "date": args.date or date.today().isoformat(),
        "live_retrieval_citation_rate": args.citation_rate,
        "bing_per_day": args.bing_per_day,
        "gsc_clicks_7d": args.gsc_clicks,
        "note": args.note or "",
    }
    with open(BOARD, "a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"appended: {json.dumps(row)}")
    show(args)


def show(args):
    rows = _rows()
    if not rows:
        print("(scoreboard empty)")
        return
    print(f"{'date':<12}{'cite_rate':>10}{'bing/day':>10}{'gsc_clk7d':>11}  note")
    for r in rows:
        cr = f"{r['live_retrieval_citation_rate']:.1%}" if r.get("live_retrieval_citation_rate") is not None else "-"
        bp = f"{r['bing_per_day']:.2f}" if r.get("bing_per_day") is not None else "-"
        gc = str(r["gsc_clicks_7d"]) if r.get("gsc_clicks_7d") is not None else "-"
        print(f"{r['date']:<12}{cr:>10}{bp:>10}{gc:>11}  {r.get('note','')}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--citation-rate", type=float, default=None, help="cited/total from live-retrieval --personal (0-1)")
    a.add_argument("--bing-per-day", type=float, default=None, help="Bing WMT AI citations/day (from CSV export)")
    a.add_argument("--gsc-clicks", type=int, default=None, help="GSC clicks trailing 7d")
    a.add_argument("--note", default=None)
    a.add_argument("--date", default=None, help="override YYYY-MM-DD (default today)")
    a.set_defaults(func=add)
    s = sub.add_parser("show")
    s.set_defaults(func=show)
    args = p.parse_args()
    args.func(args)
