#!/usr/bin/env python3
"""
Import AVR scan JSON outputs into the SQLite dashboard database.

Usage:
    python3 import_scans.py ../prospect-scans/
    python3 import_scans.py ../prospect-scans/ --db dashboard.db
    python3 import_scans.py ../prospect-scans/audit_fireblocks.com_*.md  # single scan
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(__file__).parent / "dashboard.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Domain metadata for the 5 initial prospects
DOMAIN_META = {
    "fireblocks.com": {
        "brand_name": "Fireblocks",
        "industry": "fintech",
        "icp_fit": "HIGH",
        "topics": ["crypto custody", "digital asset security", "institutional crypto"],
        "products": ["Fireblocks Wallet", "MPC Custody"],
    },
    "partnerize.com": {
        "brand_name": "Partnerize",
        "industry": "martech",
        "icp_fit": "HIGH",
        "topics": ["partner marketing", "affiliate management", "partnership automation"],
        "products": ["Partnerize Platform", "Partner Discovery"],
    },
    "justcall.io": {
        "brand_name": "JustCall",
        "industry": "saas",
        "icp_fit": "HIGH",
        "topics": ["cloud phone system", "business VoIP", "sales dialer"],
        "products": ["JustCall Dialer", "JustCall AI"],
    },
    "productive.io": {
        "brand_name": "Productive",
        "industry": "saas",
        "icp_fit": "MEDIUM",
        "topics": ["project management", "agency management", "resource planning"],
        "products": ["Productive.io"],
    },
    "nextinsurance.com": {
        "brand_name": "Next Insurance",
        "industry": "insurtech",
        "icp_fit": "MEDIUM",
        "topics": ["small business insurance", "commercial insurance", "business liability"],
        "products": ["NEXT Insurance", "Commercial Coverage"],
    },
    # Tier 2 prospects (added Apr 15 2026)
    "algolia.com": {
        "brand_name": "Algolia",
        "industry": "devtools",
        "icp_fit": "HIGH",
        "topics": ["search API", "site search", "search as a service"],
        "products": ["Algolia Search", "Algolia Recommend"],
    },
    "mixpanel.com": {
        "brand_name": "Mixpanel",
        "industry": "analytics",
        "icp_fit": "HIGH",
        "topics": ["product analytics", "user analytics", "behavioral analytics"],
        "products": ["Mixpanel Analytics", "Mixpanel Reports"],
    },
    "drift.com": {
        "brand_name": "Drift",
        "industry": "saas",
        "icp_fit": "HIGH",
        "topics": ["conversational marketing", "live chat", "sales chatbot"],
        "products": ["Drift Chat", "Drift Engage"],
    },
    "lattice.com": {
        "brand_name": "Lattice",
        "industry": "hrtech",
        "icp_fit": "HIGH",
        "topics": ["people management", "performance reviews", "employee engagement"],
        "products": ["Lattice Performance", "Lattice Engagement"],
    },
    "gorgias.com": {
        "brand_name": "Gorgias",
        "industry": "ecommerce",
        "icp_fit": "HIGH",
        "topics": ["ecommerce support", "helpdesk for shopify", "customer service automation"],
        "products": ["Gorgias Helpdesk", "Gorgias Automation"],
    },
    "calendly.com": {
        "brand_name": "Calendly",
        "industry": "saas",
        "icp_fit": "HIGH",
        "topics": ["scheduling tool", "meeting scheduler", "appointment booking"],
        "products": ["Calendly Scheduling", "Calendly Teams"],
    },
    "notion.so": {
        "brand_name": "Notion",
        "industry": "saas",
        "icp_fit": "MEDIUM",
        "topics": ["workspace tool", "project management", "team wiki"],
        "products": ["Notion Workspace", "Notion AI"],
    },
    "loom.com": {
        "brand_name": "Loom",
        "industry": "saas",
        "icp_fit": "HIGH",
        "topics": ["screen recorder", "video messaging", "async video"],
        "products": ["Loom Video", "Loom AI"],
    },
    "braze.com": {
        "brand_name": "Braze",
        "industry": "martech",
        "icp_fit": "HIGH",
        "topics": ["customer engagement", "marketing automation", "push notifications"],
        "products": ["Braze Platform", "Braze Canvas"],
    },
    "contentful.com": {
        "brand_name": "Contentful",
        "industry": "cms",
        "icp_fit": "HIGH",
        "topics": ["headless CMS", "content platform", "API-first CMS"],
        "products": ["Contentful Platform", "Contentful Studio"],
    },
    # Own domains
    "citability.dev": {
        "brand_name": "Citability",
        "industry": "consulting",
        "icp_fit": "HIGH",
        "topics": ["AI visibility", "AI citability", "AI SEO"],
        "products": ["Free Scan", "Quick Report", "Full Audit", "Implementation Sprint"],
    },
    "chudi.dev": {
        "brand_name": "Chudi Nnorukam",
        "industry": "consulting",
        "icp_fit": "HIGH",
        "topics": ["AI visibility", "web architecture", "technical SEO"],
        "products": ["chudi.dev blog", "citability.dev"],
    },
}

PLATFORM_MAP = {"openai": "ChatGPT", "perplexity": "Perplexity", "anthropic": "Claude"}


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the database with schema if needed."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    with open(SCHEMA_PATH) as f:
        schema_sql = f.read()

    # Split and execute each statement (skip PRAGMA lines already set)
    for stmt in schema_sql.split(";"):
        stmt = stmt.strip()
        if stmt and not stmt.startswith("PRAGMA"):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # table/index already exists

    conn.commit()
    return conn


def ensure_domain(conn: sqlite3.Connection, domain: str) -> int:
    """Get or create a domain record. Returns domain_id."""
    row = conn.execute("SELECT id FROM domains WHERE domain = ?", (domain,)).fetchone()
    if row:
        return row[0]

    meta = DOMAIN_META.get(domain, {})
    conn.execute(
        """INSERT INTO domains (domain, brand_name, industry, icp_fit, topics_json, products_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            domain,
            meta.get("brand_name", domain.split(".")[0].capitalize()),
            meta.get("industry"),
            meta.get("icp_fit", "UNKNOWN"),
            json.dumps(meta.get("topics", [])),
            json.dumps(meta.get("products", [])),
        ),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def find_scan_files(scan_dir: Path, domain: str, timestamp: str) -> dict:
    """Find all related files for a scan by domain and timestamp."""
    files = {}
    prefix = f"audit_{domain}_{timestamp}"

    for f in scan_dir.iterdir():
        name = f.name
        if domain in name:
            if name.endswith("_seo.json") and name.startswith(prefix):
                files["seo"] = f
            elif name.endswith("_ai.json") and name.startswith(prefix):
                files["ai"] = f
            elif "citations" in name and "summary" in name and timestamp[:8] in name:
                files["citation_summary"] = f
            elif "citations" in name and "raw" in name and timestamp[:8] in name:
                files["citation_raw"] = f
            elif "visibility" in name and "summary" in name and timestamp[:8] in name:
                files["visibility_summary"] = f
            elif "visibility" in name and "raw" in name and timestamp[:8] in name:
                files["visibility_raw"] = f

    return files


def import_scan(conn: sqlite3.Connection, scan_dir: Path, report_path: Path) -> int | None:
    """Import a single scan from its report file path. Returns scan_id or None."""
    # Parse domain and timestamp from filename: audit_<domain>_<timestamp>.md
    match = re.match(r"audit_(.+?)_(\d{8}_\d{6})\.md", report_path.name)
    if not match:
        print(f"  Skipping {report_path.name}: doesn't match audit pattern")
        return None

    domain = match.group(1)
    timestamp = match.group(2)

    # Check if already imported
    domain_id = ensure_domain(conn, domain)
    scanned_at = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").replace(
        tzinfo=timezone.utc
    ).isoformat()

    existing = conn.execute(
        "SELECT id FROM scans WHERE domain_id = ? AND scanned_at = ?",
        (domain_id, scanned_at),
    ).fetchone()
    if existing:
        print(f"  Already imported: {domain} @ {timestamp}")
        return existing[0]

    # Find related files
    files = find_scan_files(scan_dir, domain, timestamp)
    if "seo" not in files or "ai" not in files:
        print(f"  Missing SEO or AI JSON for {domain} @ {timestamp}")
        return None

    # Load JSON data
    with open(files["seo"]) as f:
        seo_data = json.load(f)
    with open(files["ai"]) as f:
        ai_data = json.load(f)

    citation_summary = None
    if "citation_summary" in files:
        with open(files["citation_summary"]) as f:
            citation_summary = json.load(f)

    visibility_summary = None
    if "visibility_summary" in files:
        with open(files["visibility_summary"]) as f:
            visibility_summary = json.load(f)

    citation_raw = None
    if "citation_raw" in files:
        with open(files["citation_raw"]) as f:
            citation_raw = json.load(f)

    visibility_raw = None
    if "visibility_raw" in files:
        with open(files["visibility_raw"]) as f:
            visibility_raw = json.load(f)

    # Determine verdicts
    seo_verdict = seo_data.get("section_verdict", "FAIL")
    ai_verdict = ai_data.get("section_verdict", "FAIL")

    from report_generator_stub import determine_overall_status
    overall_verdict = determine_overall_status(seo_verdict, ai_verdict)

    # Count checks
    all_checks = seo_data.get("checks", []) + ai_data.get("checks", [])
    checks_total = len(all_checks)
    checks_passed = sum(1 for c in all_checks if c.get("verdict") == "PASS")

    # Insert scan
    conn.execute(
        """INSERT INTO scans (
            domain_id, scanned_at, overall_verdict, seo_verdict, ai_verdict,
            citation_verdict, citation_rate_pct, citation_total, citation_tested, citation_cited,
            citation_ci_low, citation_ci_high, citation_confidence,
            visibility_verdict, visibility_rate_pct, visibility_total, visibility_tested,
            visibility_visible, visibility_known, visibility_recommended,
            checks_passed, checks_total,
            seo_json_path, ai_json_path, citation_raw_path, citation_summary_path,
            visibility_raw_path, visibility_summary_path
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            domain_id, scanned_at, overall_verdict, seo_verdict, ai_verdict,
            citation_summary.get("verdict") if citation_summary else None,
            citation_summary.get("citation_rate_pct") if citation_summary else None,
            citation_summary.get("total_tests") if citation_summary else None,
            citation_summary.get("testable") if citation_summary else None,
            citation_summary.get("cited_count") if citation_summary else None,
            citation_summary.get("confidence_interval_95", {}).get("low_pct") if citation_summary else None,
            citation_summary.get("confidence_interval_95", {}).get("high_pct") if citation_summary else None,
            citation_summary.get("confidence_label") if citation_summary else None,
            visibility_summary.get("verdict") if visibility_summary else None,
            visibility_summary.get("visibility_rate_pct") if visibility_summary else None,
            visibility_summary.get("total_tests") if visibility_summary else None,
            visibility_summary.get("testable") if visibility_summary else None,
            visibility_summary.get("visible_count") if visibility_summary else None,
            visibility_summary.get("known_count") if visibility_summary else None,
            visibility_summary.get("recommended_count") if visibility_summary else None,
            checks_passed, checks_total,
            str(files.get("seo", "")),
            str(files.get("ai", "")),
            str(files.get("citation_raw", "")),
            str(files.get("citation_summary", "")),
            str(files.get("visibility_raw", "")),
            str(files.get("visibility_summary", "")),
        ),
    )
    scan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Import individual checks
    for check in seo_data.get("checks", []):
        conn.execute(
            """INSERT INTO scan_checks (scan_id, section, check_name, tier, verdict, details_json, summary)
               VALUES (?, 'seo', ?, ?, ?, ?, ?)""",
            (
                scan_id,
                check.get("check", "unknown"),
                check.get("tier"),
                check.get("verdict", "ERROR"),
                json.dumps({k: v for k, v in check.items() if k not in ("check", "tier", "verdict")}),
                check.get("note"),
            ),
        )

    for check in ai_data.get("checks", []):
        conn.execute(
            """INSERT INTO scan_checks (scan_id, section, check_name, tier, verdict, details_json, summary)
               VALUES (?, 'ai', ?, ?, ?, ?, ?)""",
            (
                scan_id,
                check.get("check", "unknown"),
                check.get("tier"),
                check.get("verdict", "ERROR"),
                json.dumps({k: v for k, v in check.items() if k not in ("check", "tier", "verdict")}),
                None,
            ),
        )

    # Import citation raw queries
    if citation_raw:
        for q in citation_raw:
            platform = PLATFORM_MAP.get(q.get("platform", "").lower(), q.get("platform", "ChatGPT"))
            conn.execute(
                """INSERT INTO platform_queries (scan_id, platform, query_id, category, query_text,
                   status, cited_urls_json, response_snippet, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scan_id,
                    platform,
                    q.get("query_id"),
                    q.get("category"),
                    q.get("query", ""),
                    q.get("status", "ERROR"),
                    json.dumps(q.get("cited_urls", [])),
                    q.get("response_snippet", "")[:500],
                    q.get("error"),
                ),
            )

    # Import visibility raw queries
    if visibility_raw:
        for q in visibility_raw:
            platform = PLATFORM_MAP.get(q.get("platform", "").lower(), q.get("platform", "ChatGPT"))
            br = q.get("brand_recognition", {})
            rec = q.get("recommendation", {})
            conn.execute(
                """INSERT INTO visibility_queries (scan_id, platform, query_id, category, signal,
                   query_text, is_visible, brand_recognition_level, brand_domain_mentioned,
                   brand_name_mentioned, brand_owner_mentioned, concept_ratio, concepts_found_json,
                   is_recommended, recommended_as_json, response_snippet, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scan_id,
                    platform,
                    q.get("query_id"),
                    q.get("category", "unknown"),
                    q.get("signal"),
                    q.get("query", ""),
                    1 if q.get("visible") else 0,
                    br.get("level"),
                    1 if br.get("domain_mentioned") else 0,
                    1 if br.get("name_mentioned") else 0,
                    1 if br.get("owner_mentioned") else 0,
                    q.get("concept_attribution", {}).get("ratio"),
                    json.dumps(q.get("concept_attribution", {}).get("concepts_found", [])),
                    1 if rec.get("recommended") else 0,
                    json.dumps(rec.get("matched_patterns", [])),
                    q.get("response", "")[:500] if q.get("response") else None,
                    q.get("error"),
                ),
            )

    conn.commit()
    print(f"  Imported: {domain} @ {scanned_at} (scan_id={scan_id})")
    return scan_id


def determine_overall_status(seo_verdict: str, ai_verdict: str) -> str:
    """Determine overall readiness status from section verdicts."""
    if seo_verdict == "PASS" and ai_verdict == "PASS":
        return "AI-READY"
    elif seo_verdict == "PASS":
        return "FOUNDATION-READY"
    elif ai_verdict == "PASS":
        return "INFRASTRUCTURE-READY"
    else:
        return "NOT-READY"


def main():
    parser = argparse.ArgumentParser(description="Import AVR scans into dashboard DB")
    parser.add_argument("scan_dir", help="Directory containing scan output files")
    parser.add_argument("--db", default=str(DB_PATH), help="Database path")
    args = parser.parse_args()

    scan_dir = Path(args.scan_dir)
    if not scan_dir.exists():
        print(f"Error: {scan_dir} does not exist")
        sys.exit(1)

    db_path = Path(args.db)
    conn = init_db(db_path)
    print(f"Database: {db_path}")

    # Find all audit report .md files
    reports = sorted(scan_dir.glob("audit_*.md"))
    if not reports:
        print(f"No audit reports found in {scan_dir}")
        sys.exit(1)

    print(f"Found {len(reports)} audit report(s)")
    imported = 0
    for report in reports:
        scan_id = import_scan(conn, scan_dir, report)
        if scan_id:
            imported += 1

    conn.close()
    print(f"\nDone: {imported}/{len(reports)} scans imported")


if __name__ == "__main__":
    # Inline the overall status function to avoid importing from scripts/
    # (report_generator_stub is defined in this file)
    import types
    report_generator_stub = types.ModuleType("report_generator_stub")
    report_generator_stub.determine_overall_status = determine_overall_status
    sys.modules["report_generator_stub"] = report_generator_stub

    main()
