"""
GSC CTR-Optimization PR Agent
==============================

Dependencies (pip install line at bottom of this docstring):
  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2

OAuth Desktop Client Setup (one-time, per GCP project):
  1. Go to https://console.cloud.google.com/
  2. Select or create a project.
  3. APIs and Services -> Library -> search "Google Search Console API" -> Enable.
  4. APIs and Services -> Credentials -> Create Credentials -> OAuth client ID.
  5. Application type: "Desktop app".  Name it anything (e.g. "gsc-ctr-agent").
  6. Download the JSON, save to ~/.config/gsc-agent/client_secret.json
     (or set env GSC_OAUTH_CLIENT_SECRETS to your preferred path).
  7. APIs and Services -> OAuth consent screen -> add your Google account as a
     Test User if the app is in "Testing" mode.

First run opens a browser tab for one-time consent. The token is cached at
~/.config/gsc-agent/token.json and auto-refreshed on subsequent runs.

WARNING: The Search Console API treats URL-prefix properties
("https://example.com/") differently from domain properties
("sc-domain:example.com"). Domain properties are verified via DNS; if your
property is domain-type, some query filters behave differently. This script
warns you and continues - but validate that impressions are non-zero.

PR creation (--apply) opens a REAL review-only PR against the content repo
(default ~/Projects/active/chudi-blog) using a dirty-tree-safe git worktree.

Multi-engine: --engine gsc|bing|both. The Bing pull reads a Bing Webmaster
API key from env BING_WEBMASTER_API_KEY or ~/.config/bing-webmaster/apikey
(never hardcoded, never logged); it is skipped gracefully if the key is absent.
"""

# Requirements:
#   pip install google-api-python-client google-auth-oauthlib google-auth-httplib2

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Google auth + API imports - fail fast with a clear message if missing
# ---------------------------------------------------------------------------
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError as exc:
    print(
        f"[ERROR] Missing dependency: {exc}\n"
        "Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

DEFAULT_CLIENT_SECRETS = Path.home() / ".config" / "gsc-agent" / "client_secret.json"
DEFAULT_TOKEN_PATH = Path.home() / ".config" / "gsc-agent" / "token.json"

# Position -> expected CTR heuristic (based on industry averages; adjust as needed).
# Source: aggregated CTR studies (SISTRIX, Backlinko, Advanced Web Ranking).
POSITION_CTR_TABLE = {
    1: 0.28,
    2: 0.15,
    3: 0.10,
    4: 0.07,
    5: 0.05,
    6: 0.04,
    7: 0.03,
    8: 0.025,
    9: 0.02,
    10: 0.018,
}

# Positions beyond 10 use this fallback expected CTR.
POSITION_BEYOND_10_CTR = 0.01

REPORTS_DIR = Path(__file__).parent.parent / "reports"

# --- Bing Webmaster Tools (BWT) -------------------------------------------
# The API key is read from env or a gitignored key file; never hardcoded,
# never logged. See get_bing_api_key().
DEFAULT_BING_KEY_PATH = Path.home() / ".config" / "bing-webmaster" / "apikey"
BING_API_BASE = "https://ssl.bing.com/webmaster/api.svc/json"

# --- Content repo for --apply PRs -----------------------------------------
DEFAULT_CONTENT_REPO = Path.home() / "Projects" / "active" / "chudi-blog"
REPORT_SUBDIR = "content/seo-reports"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_credentials(client_secrets_path: Path, token_path: Path) -> Credentials:
    """Load cached credentials or run the OAuth InstalledAppFlow (Desktop client)."""
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not client_secrets_path.exists():
                print(
                    f"[ERROR] Client secrets file not found: {client_secrets_path}\n"
                    "Download your Desktop OAuth client JSON from GCP Console and place it there,\n"
                    "or set env GSC_OAUTH_CLIENT_SECRETS to its path.",
                    file=sys.stderr,
                )
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Cache the token for future runs.
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
        print(f"[auth] Token cached to {token_path}")

    return creds


def build_gsc_service(creds: Credentials):
    """Build the Search Console service object (searchconsole v1)."""
    return build("searchconsole", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Property helpers
# ---------------------------------------------------------------------------

def list_properties(service) -> list[dict]:
    """Return all verified GSC properties for the authenticated account."""
    result = service.sites().list().execute()
    return result.get("siteEntry", [])


def check_property_type(site_url: str) -> str:
    """Return 'domain' if sc-domain: prefix, else 'url-prefix'."""
    if site_url.startswith("sc-domain:"):
        return "domain"
    return "url-prefix"


def print_properties(properties: list[dict]) -> None:
    """Print all verified properties with their type."""
    print("\n[properties] Verified GSC properties for this account:")
    for prop in properties:
        url = prop.get("siteUrl", "")
        ptype = check_property_type(url)
        permission = prop.get("permissionLevel", "unknown")
        print(f"  {url}  [{ptype}]  permission={permission}")
    print()


# ---------------------------------------------------------------------------
# GSC query
# ---------------------------------------------------------------------------

def query_search_analytics(
    service,
    property_url: str,
    days: int,
    row_limit: int = 1000,
) -> list[dict]:
    """
    Query searchanalytics for page+query dimensions over the last N days.
    Returns a list of row dicts with keys: page, query, clicks, impressions, ctr, position.
    """
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)

    body = {
        "startDate": str(start_date),
        "endDate": str(end_date),
        "dimensions": ["page", "query"],
        "rowLimit": row_limit,
    }

    try:
        response = (
            service.searchanalytics()
            .query(siteUrl=property_url, body=body)
            .execute()
        )
    except HttpError as exc:
        print(f"[ERROR] GSC API error: {exc}", file=sys.stderr)
        sys.exit(1)

    rows = response.get("rows", [])
    results = []
    for row in rows:
        keys = row.get("keys", [])
        results.append(
            {
                "page": keys[0] if len(keys) > 0 else "",
                "query": keys[1] if len(keys) > 1 else "",
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": row.get("ctr", 0.0),
                "position": row.get("position", 0.0),
                "engine": "google",
            }
        )
    return results


# ---------------------------------------------------------------------------
# CTR-gap detection
# ---------------------------------------------------------------------------

def expected_ctr(position: float) -> float:
    """Return expected CTR for a given (possibly fractional) position."""
    rounded = max(1, round(position))
    return POSITION_CTR_TABLE.get(rounded, POSITION_BEYOND_10_CTR)


def find_ctr_gaps(
    rows: list[dict],
    impression_floor: int,
    gap_threshold: float = 0.5,
) -> list[dict]:
    """
    Return rows where impressions >= impression_floor AND
    actual_ctr < gap_threshold * expected_ctr(position).
    Sorted by impressions descending (biggest opportunity first).
    """
    gaps = []
    for row in rows:
        if row["impressions"] < impression_floor:
            continue
        exp = expected_ctr(row["position"])
        if row["ctr"] < gap_threshold * exp:
            gaps.append(
                {
                    **row,
                    "expected_ctr": exp,
                    "ctr_gap": exp - row["ctr"],
                }
            )
    gaps.sort(key=lambda r: r["impressions"], reverse=True)
    return gaps


# ---------------------------------------------------------------------------
# Suggestion generator (deterministic templates)
# ---------------------------------------------------------------------------

def draft_suggestion(row: dict) -> str:
    """
    Return a templated, deterministic suggestion for improving CTR.
    Clearly marked as a suggestion - not AI-generated copy.
    """
    query = row["query"]
    page = row["page"]
    position = row["position"]
    actual_ctr = row["ctr"]
    expected = row["expected_ctr"]

    lines = []
    engine = row.get("engine", "google")
    lines.append(f"**Page:** {page}")
    lines.append(f"**Top query:** `{query}`  _(engine: {engine})_")
    lines.append(
        f"**Stats:** position={position:.1f}, actual CTR={actual_ctr:.1%}, "
        f"expected CTR~{expected:.1%}"
    )
    lines.append("")
    lines.append("**Suggested improvements (review before applying):**")

    if position <= 3:
        lines.append(
            f'- Title: include "{query}" closer to the start of the title tag if not already present.'
        )
        lines.append(
            "- Meta description: add a specific value-proposition or statistic to increase "
            "click motivation (e.g. number, outcome, or year)."
        )
    elif position <= 7:
        lines.append(
            f'- Title: test a question-format title targeting "{query}" (e.g. "How to ... [{query}]").'
        )
        lines.append(
            "- Meta description: add a call-to-action phrase and match the query intent more explicitly."
        )
    else:
        lines.append(
            f'- Title: this page ranks position {position:.0f}; consider whether the page fully satisfies '
            f'the intent of "{query}" before optimizing CTR alone.'
        )
        lines.append(
            "- Meta description: ensure it is not truncated and contains the query term naturally."
        )

    lines.append(
        "- Schema: if not present, add Article/HowTo/FAQ schema to earn rich-result snippets."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(gaps: list[dict], property_url: str, days: int, date_str: str) -> Path:
    """Write a markdown gap report to the reports directory. Returns the path."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"gsc-ctr-gaps-{date_str}.md"

    lines = [
        f"# GSC CTR Gap Report - {date_str}",
        "",
        f"**Property:** {property_url}",
        f"**Period:** last {days} days",
        f"**Generated:** {datetime.utcnow().isoformat(timespec='seconds')}Z",
        "",
        "---",
        "",
        f"## Summary",
        "",
        f"Found **{len(gaps)} page-query pairs** with significant CTR gaps.",
        "",
        "---",
        "",
        "## Top CTR Gaps (ranked by impressions)",
        "",
    ]

    for i, row in enumerate(gaps[:20], 1):
        lines.append(f"### {i}. {row['page']}")
        lines.append("")
        lines.append(draft_suggestion(row))
        lines.append("")
        lines.append("---")
        lines.append("")

    if len(gaps) > 20:
        lines.append(f"*... and {len(gaps) - 20} more gaps not shown above.*")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# Bing Webmaster Tools (BWT) query stats
# ---------------------------------------------------------------------------

def get_bing_api_key() -> str | None:
    """
    Resolve the Bing Webmaster API key WITHOUT ever hardcoding or logging it.

    Order: env BING_WEBMASTER_API_KEY, then a gitignored key file at
    ~/.config/bing-webmaster/apikey (set perms 0600). Returns None when
    unavailable, in which case the Bing pull is skipped gracefully.

    Get the key at: Bing Webmaster Tools -> Settings (gear) -> API access ->
    API Key -> View API Key. Then:  printf '%s' '<KEY>' > ~/.config/bing-webmaster/apikey
    (or `export BING_WEBMASTER_API_KEY=<KEY>`).
    """
    key = os.environ.get("BING_WEBMASTER_API_KEY")
    if key and key.strip():
        return key.strip()
    if DEFAULT_BING_KEY_PATH.exists():
        try:
            val = DEFAULT_BING_KEY_PATH.read_text(encoding="utf-8").strip()
            return val or None
        except OSError:
            return None
    return None


def query_bing_search_analytics(site_url: str, api_key: str) -> list[dict]:
    """
    Call BWT GetQueryStats and return rows in the SAME shape as the GSC query
    (page, query, clicks, impressions, ctr, position, engine) so they flow
    through find_ctr_gaps unchanged.

    GetQueryStats is query-level (no page dimension) and returns a weekly time
    series per query; we aggregate across the returned window per query and use
    an impression-weighted average position. Docs:
    https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.iwebmasterapi.getquerystats

    API: GET /webmaster/api.svc/json/GetQueryStats?siteUrl=<url>&apikey=<key>
    Resp: {"d":[{"AvgImpressionPosition":17,"Clicks":15,"Impressions":100,
                 "Query":"q","Date":"/Date(ms-offset)/"}, ...]}
    """
    params = urllib.parse.urlencode({"siteUrl": site_url, "apikey": api_key})
    url = f"{BING_API_BASE}/GetQueryStats?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        # Never echo the key (it lives in the URL); report only the method name.
        print(
            f"[bing][WARN] GetQueryStats failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return []

    raw = payload.get("d", []) if isinstance(payload, dict) else []
    agg: dict[str, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        q = item.get("Query", "")
        if not q:
            continue
        impr = item.get("Impressions", 0) or 0
        a = agg.setdefault(q, {"clicks": 0, "impressions": 0, "pos_wsum": 0.0})
        a["clicks"] += item.get("Clicks", 0) or 0
        a["impressions"] += impr
        a["pos_wsum"] += (item.get("AvgImpressionPosition", 0) or 0) * impr

    rows = []
    for q, a in agg.items():
        impr = a["impressions"]
        if impr <= 0:
            continue
        rows.append(
            {
                "page": f"(bing: {site_url})",
                "query": q,
                "clicks": a["clicks"],
                "impressions": impr,
                "ctr": a["clicks"] / impr,
                "position": a["pos_wsum"] / impr,
                "engine": "bing",
            }
        )
    return rows


def write_bing_snapshot(site_url: str, rows: list[dict], date_str: str) -> None:
    """Write a tiny no-secrets snapshot that seo_status.py can read for the roll-up."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    snap = {
        "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "property": site_url,
        "queryCount": len(rows),
        # GetQueryStats has no AI-citation field; the AI Performance counts seen
        # in the BWT UI come from a separate surface. Reserved for a future pull.
        "aiCitations": None,
    }
    (REPORTS_DIR / "bing-query-stats-latest.json").write_text(
        json.dumps(snap, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# PR creation (gated behind --apply) - real, dirty-tree-safe worktree pattern
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def open_pr(report_path: Path, gaps: list[dict], content_repo: Path, date_str: str) -> None:
    """
    Open a REAL PR against the content repo containing the gap report.

    Uses the verified dirty-tree-safe worktree pattern (codex node
    chudi-blog-clean-deploy-worktree): branch off origin/main inside a temp
    worktree so the operator's working tree is never touched; stage ONLY the
    report file (never `git add -A`, which leaks secrets); commit --no-verify
    (husky's pre-commit needs node_modules, absent in a bare worktree); push;
    then `gh pr create`.

    The PR is REVIEW-ONLY by design: it surfaces the ranked suggestions for the
    operator to apply the title/meta edits they agree with, then merge.
    Auto-rewriting frontmatter from heuristic templates is intentionally NOT
    done here (it would ship low-quality copy under the operator's name).
    """
    repo = str(content_repo)
    if not (content_repo / ".git").exists():
        print(f"[apply][ERROR] Not a git repo: {repo}", file=sys.stderr)
        return
    if not shutil.which("gh"):
        print("[apply][ERROR] gh CLI not found; install GitHub CLI to open PRs.", file=sys.stderr)
        return

    branch = f"gsc-ctr-{date_str}"
    wt = tempfile.mkdtemp(prefix="gsc-ctr-wt-")
    pushed = False
    try:
        r = _run(["git", "fetch", "origin"], cwd=repo)
        if r.returncode != 0:
            print(f"[apply][ERROR] git fetch failed: {r.stderr.strip()}", file=sys.stderr)
            return
        r = _run(["git", "worktree", "add", "-b", branch, wt, "origin/main"], cwd=repo)
        if r.returncode != 0:
            print(f"[apply][ERROR] worktree add failed: {r.stderr.strip()}", file=sys.stderr)
            return

        dest_dir = Path(wt) / REPORT_SUBDIR
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / report_path.name).write_text(
            report_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

        rel = str(Path(REPORT_SUBDIR) / report_path.name)
        _run(["git", "add", rel], cwd=wt)  # ONLY the report file, never -A
        msg = f"docs(seo): GSC/BWT CTR gap report {date_str} ({len(gaps)} gaps)"
        r = _run(["git", "commit", "--no-verify", "-m", msg], cwd=wt)
        if r.returncode != 0:
            print(f"[apply][ERROR] commit failed: {(r.stderr or r.stdout).strip()}", file=sys.stderr)
            return
        r = _run(["git", "push", "-u", "origin", branch], cwd=wt)
        if r.returncode != 0:
            print(f"[apply][ERROR] push failed: {r.stderr.strip()}", file=sys.stderr)
            return
        pushed = True

        body = (
            f"Automated CTR gap report for {date_str}.\n\n"
            f"**{len(gaps)} page-query pairs** are below expected CTR for their position.\n\n"
            "Each entry in the report is a REVIEW item: apply the title/meta edits you "
            "agree with, then merge. Suggestions are heuristic, not finished copy.\n\n"
            f"Report file: `{rel}`"
        )
        r = _run(
            ["gh", "pr", "create", "--base", "main", "--head", branch,
             "--title", f"SEO: CTR gaps {date_str}", "--body", body],
            cwd=wt,
        )
        if r.returncode == 0:
            print(f"[apply] PR opened: {r.stdout.strip()}")
        else:
            print(
                f"[apply][ERROR] gh pr create failed: {(r.stderr or r.stdout).strip()}\n"
                f"  Branch '{branch}' was pushed; open the PR manually if needed.",
                file=sys.stderr,
            )
    finally:
        _run(["git", "worktree", "remove", wt, "--force"], cwd=repo)
        # If we never pushed, drop the local branch the worktree created so a
        # retry on the same date doesn't collide.
        if not pushed:
            _run(["git", "branch", "-D", branch], cwd=repo)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GSC CTR-optimization agent: find high-impression/low-CTR pages and draft improvements.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--property",
        default=os.environ.get("GSC_PROPERTY", "https://chudi.dev/"),
        help="GSC property URL (default: env GSC_PROPERTY or https://chudi.dev/)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=28,
        help="Number of days to look back (default: 28)",
    )
    parser.add_argument(
        "--impression-floor",
        type=int,
        default=int(os.environ.get("IMPRESSION_FLOOR", "100")),
        help="Minimum impressions to include a row (default: 100)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Open a PR with the gap report (default: dry-run only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Force dry-run even if --apply is passed. Dry-run is already the default when --apply is absent.",
    )
    parser.add_argument(
        "--date",
        default=datetime.utcnow().strftime("%Y-%m-%d"),
        help="Date string for the report filename (default: today UTC)",
    )
    parser.add_argument(
        "--engine",
        choices=["gsc", "bing", "both"],
        default=os.environ.get("CTR_ENGINE", "gsc"),
        help="Which search engine(s) to pull CTR data from (default: gsc). "
        "'bing'/'both' require a Bing Webmaster API key (env BING_WEBMASTER_API_KEY "
        "or ~/.config/bing-webmaster/apikey).",
    )
    parser.add_argument(
        "--content-repo",
        default=str(DEFAULT_CONTENT_REPO),
        help=f"Content repo to open the --apply PR against (default: {DEFAULT_CONTENT_REPO})",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    apply_mode = args.apply and not args.dry_run

    # Resolve secrets paths from env or defaults.
    client_secrets_path = Path(
        os.environ.get("GSC_OAUTH_CLIENT_SECRETS", str(DEFAULT_CLIENT_SECRETS))
    )
    token_path = DEFAULT_TOKEN_PATH

    print(f"[config] Property:         {args.property}")
    print(f"[config] Engine(s):        {args.engine}")
    print(f"[config] Days:             {args.days}")
    print(f"[config] Impression floor: {args.impression_floor}")
    print(f"[config] Mode:             {'APPLY (PR creation)' if apply_mode else 'DRY-RUN'}")
    print(f"[config] Content repo:     {args.content_repo}")
    print()

    rows: list[dict] = []

    # ------------------------------------------------------------------
    # Google Search Console (engine gsc/both)
    # ------------------------------------------------------------------
    if args.engine in ("gsc", "both"):
        print(f"[gsc] Client secrets: {client_secrets_path}")
        print(f"[gsc] Token cache:    {token_path}")
        creds = get_credentials(client_secrets_path, token_path)
        service = build_gsc_service(creds)
        print("[gsc] Authenticated successfully.")

        properties = list_properties(service)
        print_properties(properties)

        property_urls = [p.get("siteUrl", "") for p in properties]
        if args.property not in property_urls:
            print(
                f"[WARN] Target property '{args.property}' was not found in your verified properties list.\n"
                "       Check spelling, trailing slash, and that you have access.\n"
                "       Continuing anyway - the query may return zero rows.",
                file=sys.stderr,
            )

        ptype = check_property_type(args.property)
        if ptype == "domain":
            print(
                "[WARN] Target property is a domain property (sc-domain: prefix).\n"
                "       Domain properties aggregate all subdomains and protocols.\n"
                "       Some dimension filters behave differently for domain properties;\n"
                "       verify that the returned impression counts are non-zero.\n",
                file=sys.stderr,
            )

        print(f"[gsc] Fetching search analytics for the last {args.days} days...")
        gsc_rows = query_search_analytics(service, args.property, args.days)
        print(f"[gsc] Received {len(gsc_rows)} row(s).")
        rows.extend(gsc_rows)

    # ------------------------------------------------------------------
    # Bing Webmaster Tools (engine bing/both; skipped gracefully w/o key)
    # ------------------------------------------------------------------
    if args.engine in ("bing", "both"):
        bing_key = get_bing_api_key()
        if not bing_key:
            print(
                "[bing][WARN] No Bing Webmaster API key found "
                "(env BING_WEBMASTER_API_KEY or ~/.config/bing-webmaster/apikey).\n"
                "             Skipping the Bing pull. See get_bing_api_key() for setup.",
                file=sys.stderr,
            )
        else:
            print(f"[bing] Fetching GetQueryStats for {args.property} ...")
            bing_rows = query_bing_search_analytics(args.property, bing_key)
            print(f"[bing] Received {len(bing_rows)} aggregated query row(s).")
            write_bing_snapshot(args.property, bing_rows, args.date)
            rows.extend(bing_rows)

    # ------------------------------------------------------------------
    # No-data guard
    # ------------------------------------------------------------------
    if not rows:
        print("[INFO] No rows returned from any engine. Possible causes:")
        print("  - Property not verified or wrong URL format.")
        print("  - Domain-type property returning empty due to filter mismatch.")
        print("  - No data in the selected date range, or Bing key missing.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # CTR-gap detection (across all engines)
    # ------------------------------------------------------------------
    gaps = find_ctr_gaps(rows, impression_floor=args.impression_floor)
    n_google = sum(1 for g in gaps if g.get("engine") == "google")
    n_bing = sum(1 for g in gaps if g.get("engine") == "bing")
    print(
        f"[gaps] Found {len(gaps)} CTR gap(s) above impression floor "
        f"{args.impression_floor}  (google={n_google}, bing={n_bing})."
    )

    if not gaps:
        print("[INFO] No gaps detected. Try lowering --impression-floor.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    report_path = write_report(gaps, args.property, args.days, args.date)
    print(f"[report] Written to: {report_path}")

    # ------------------------------------------------------------------
    # PR creation (gated behind --apply)
    # ------------------------------------------------------------------
    if apply_mode:
        open_pr(report_path, gaps, Path(args.content_repo), args.date)
    else:
        print(
            f"\n[dry-run] Would open a PR against {args.content_repo} with the report at:\n"
            f"          {report_path}\n"
            "          Re-run with --apply (and without --dry-run) to create the PR."
        )


if __name__ == "__main__":
    main()
