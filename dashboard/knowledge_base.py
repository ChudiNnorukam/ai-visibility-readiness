#!/usr/bin/env python3
"""
SQL-based knowledge retrieval for the AVR self-learning system.
Phase 1: No embeddings, no frameworks. Plain SQL queries.

Usage:
    from knowledge_base import KnowledgeBase
    kb = KnowledgeBase("dashboard.db")
    similar = kb.get_similar_findings("fintech", "seo_crawlability")
    benchmarks = kb.get_industry_benchmarks("saas")
    fixes = kb.get_effective_fixes("ai", "crawler_access")
"""

import json
import sqlite3
from pathlib import Path


class KnowledgeBase:
    """SQL-based retrieval over accumulated AVR scan data."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self):
        """Apply knowledge schema if not already present."""
        schema_path = Path(__file__).parent / "knowledge_schema.sql"
        if not schema_path.exists():
            return
        conn = self._conn()
        with open(schema_path) as f:
            sql = f.read()
        # Strip SQL comments before splitting
        import re
        sql = re.sub(r"--[^\n]*", "", sql)
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.upper().startswith("PRAGMA"):
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass  # already exists
        conn.commit()
        conn.close()

    # ================================================================
    # RETRIEVAL FUNCTIONS
    # ================================================================

    def get_similar_findings(
        self, industry: str, check_name: str | None = None, limit: int = 10
    ) -> list[dict]:
        """Find similar past findings by industry and check name.

        At n<50, this is a simple SQL WHERE clause.
        At n>50, replace with vector similarity search.
        """
        conn = self._conn()
        if check_name:
            rows = conn.execute(
                """SELECT ke.*, d.domain, d.brand_name
                FROM knowledge_entries ke
                LEFT JOIN domains d ON d.id = ke.domain_id
                WHERE ke.industry = ? AND ke.check_name LIKE ?
                ORDER BY ke.created_at DESC
                LIMIT ?""",
                (industry, f"%{check_name}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT ke.*, d.domain, d.brand_name
                FROM knowledge_entries ke
                LEFT JOIN domains d ON d.id = ke.domain_id
                WHERE ke.industry = ?
                ORDER BY ke.created_at DESC
                LIMIT ?""",
                (industry, limit),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_industry_benchmarks(self, industry: str | None = None) -> list[dict]:
        """Get aggregated metrics per industry."""
        conn = self._conn()
        if industry:
            rows = conn.execute(
                "SELECT * FROM v_industry_benchmarks WHERE industry = ?",
                (industry,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM v_industry_benchmarks ORDER BY scan_count DESC"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_check_failure_rates(self, section: str | None = None) -> list[dict]:
        """Get failure rates per check (which checks fail most?)."""
        conn = self._conn()
        if section:
            rows = conn.execute(
                "SELECT * FROM v_check_failure_rates WHERE section = ?",
                (section,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM v_check_failure_rates").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_effective_fixes(
        self, section: str | None = None, check_name: str | None = None
    ) -> list[dict]:
        """Get recommendation effectiveness data (which fixes actually work?)."""
        conn = self._conn()
        query = "SELECT * FROM v_recommendation_effectiveness WHERE 1=1"
        params: list = []
        if section:
            query += " AND category = ?"
            params.append(section)
        if check_name:
            query += " AND check_name LIKE ?"
            params.append(f"%{check_name}%")
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_domain_history(self, domain: str) -> list[dict]:
        """Get all scans for a domain (for re-scan comparison)."""
        conn = self._conn()
        rows = conn.execute(
            """SELECT s.*, d.domain, d.brand_name, d.industry
            FROM scans s
            JOIN domains d ON d.id = s.domain_id
            WHERE d.domain = ?
            ORDER BY s.scanned_at DESC""",
            (domain,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_scan_details(self, scan_id: int) -> dict:
        """Get full scan details including checks, citations, visibility."""
        conn = self._conn()
        scan = conn.execute(
            """SELECT s.*, d.domain, d.brand_name, d.industry, d.topics_json, d.products_json
            FROM scans s JOIN domains d ON d.id = s.domain_id
            WHERE s.id = ?""",
            (scan_id,),
        ).fetchone()
        if not scan:
            conn.close()
            return {}

        checks = conn.execute(
            "SELECT * FROM scan_checks WHERE scan_id = ? ORDER BY section, check_name",
            (scan_id,),
        ).fetchall()

        citations = conn.execute(
            "SELECT * FROM platform_queries WHERE scan_id = ?",
            (scan_id,),
        ).fetchall()

        visibility = conn.execute(
            "SELECT * FROM visibility_queries WHERE scan_id = ?",
            (scan_id,),
        ).fetchall()

        recommendations = conn.execute(
            "SELECT * FROM recommendations WHERE scan_id = ? ORDER BY priority",
            (scan_id,),
        ).fetchall()

        conn.close()
        return {
            "scan": dict(scan),
            "checks": [dict(c) for c in checks],
            "citations": [dict(c) for c in citations],
            "visibility": [dict(v) for v in visibility],
            "recommendations": [dict(r) for r in recommendations],
        }

    def get_latest_scans(self, limit: int = 20) -> list[dict]:
        """Get latest scan summaries across all domains."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM v_latest_scans ORDER BY scanned_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_citation_by_platform(self) -> list[dict]:
        """Get citation rates broken down by platform."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM v_latest_citation_by_platform"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ================================================================
    # INGESTION FUNCTIONS
    # ================================================================

    def ingest_knowledge_from_scan(self, scan_id: int) -> int:
        """Extract learnable patterns from a completed scan and store them.

        Returns count of knowledge entries created.
        """
        conn = self._conn()
        scan = conn.execute(
            """SELECT s.*, d.domain, d.industry
            FROM scans s JOIN domains d ON d.id = s.domain_id
            WHERE s.id = ?""",
            (scan_id,),
        ).fetchone()
        if not scan:
            conn.close()
            return 0

        industry = scan["industry"] or "unknown"
        domain_id = scan["domain_id"]
        count = 0

        # Extract patterns from individual checks
        checks = conn.execute(
            "SELECT * FROM scan_checks WHERE scan_id = ?", (scan_id,)
        ).fetchall()

        for check in checks:
            details = json.loads(check["details_json"]) if check["details_json"] else {}
            pattern = _describe_pattern(check["section"], check["check_name"], check["verdict"], details)

            if pattern:
                conn.execute(
                    """INSERT OR IGNORE INTO knowledge_entries
                    (scan_id, domain_id, industry, check_name, section, verdict,
                     pattern_description, fix_recommended, severity, avr_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        scan_id, domain_id, industry,
                        check["check_name"], check["section"], check["verdict"],
                        pattern["description"], pattern.get("fix"),
                        pattern.get("severity", "medium"),
                        scan["avr_version"],
                    ),
                )
                count += 1

        # Extract citation pattern
        citation_rate = scan["citation_rate_pct"]
        if citation_rate is not None:
            level = "high" if citation_rate > 40 else "medium" if citation_rate > 20 else "low"
            conn.execute(
                """INSERT OR IGNORE INTO knowledge_entries
                (scan_id, domain_id, industry, check_name, section, verdict,
                 pattern_description, severity, avr_version)
                VALUES (?, ?, ?, 'citation_rate', 'citation', ?, ?, ?, ?)""",
                (
                    scan_id, domain_id, industry,
                    scan["citation_verdict"] or "NOT_CITED",
                    f"{industry} company with {scan['seo_verdict']} SEO and {scan['ai_verdict']} AI infra "
                    f"achieved {citation_rate}% citation rate",
                    level,
                    scan["avr_version"],
                ),
            )
            count += 1

        # Extract visibility pattern
        vis_rate = scan["visibility_rate_pct"]
        if vis_rate is not None:
            conn.execute(
                """INSERT OR IGNORE INTO knowledge_entries
                (scan_id, domain_id, industry, check_name, section, verdict,
                 pattern_description, severity, avr_version)
                VALUES (?, ?, ?, 'visibility_rate', 'visibility', ?, ?, 'medium', ?)""",
                (
                    scan_id, domain_id, industry,
                    scan["visibility_verdict"] or "INVISIBLE",
                    f"{industry} company visibility: {vis_rate}% "
                    f"(known={scan['visibility_known']}, recommended={scan['visibility_recommended']})",
                    scan["avr_version"],
                ),
            )
            count += 1

        conn.commit()
        conn.close()
        return count

    def generate_recommendations(self, scan_id: int) -> list[dict]:
        """Generate recommendations for a scan, informed by past knowledge.

        This is the core learning loop: recommendations improve as the
        knowledge base grows.
        """
        details = self.get_scan_details(scan_id)
        if not details:
            return []

        scan = details["scan"]
        industry = scan.get("industry", "unknown")
        conn = self._conn()
        recs = []

        for check in details["checks"]:
            if check["verdict"] in ("FAIL", "PARTIAL"):
                # Look for similar past findings
                similar = conn.execute(
                    """SELECT ke.fix_recommended, ke.pattern_description,
                              COUNT(*) as occurrences
                    FROM knowledge_entries ke
                    WHERE ke.check_name = ? AND ke.verdict IN ('FAIL', 'PARTIAL')
                    AND ke.fix_recommended IS NOT NULL
                    GROUP BY ke.fix_recommended
                    ORDER BY occurrences DESC
                    LIMIT 3""",
                    (check["check_name"],),
                ).fetchall()

                # Build recommendation
                source = "knowledge_informed" if similar else "rule_based"
                fix_text = similar[0]["fix_recommended"] if similar else _default_fix(check["check_name"])
                similar_ids = [s["fix_recommended"] for s in similar] if similar else []

                priority = 1 if check["verdict"] == "FAIL" else 2
                title = f"Fix: {check['check_name'].replace('_', ' ').title()}"

                conn.execute(
                    """INSERT INTO recommendations
                    (scan_id, domain_id, priority, category, check_name, title,
                     description, source, similar_entry_ids, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed')""",
                    (
                        scan_id, scan["domain_id"], priority,
                        check["section"], check["check_name"], title,
                        fix_text, source, json.dumps(similar_ids),
                    ),
                )
                recs.append({
                    "title": title,
                    "description": fix_text,
                    "priority": priority,
                    "source": source,
                    "similar_count": len(similar),
                })

        # Add industry-specific insight if we have benchmark data
        benchmarks = self.get_industry_benchmarks(industry)
        if benchmarks:
            b = benchmarks[0]
            if b["scan_count"] > 1:
                citation_rate = scan.get("citation_rate_pct")
                if citation_rate is not None and b["avg_citation_rate"] is not None:
                    if citation_rate < b["avg_citation_rate"]:
                        conn.execute(
                            """INSERT INTO recommendations
                            (scan_id, domain_id, priority, category, check_name, title,
                             description, source, status)
                            VALUES (?, ?, 2, 'benchmark', 'industry_comparison', ?,
                                    ?, 'knowledge_informed', 'proposed')""",
                            (
                                scan_id, scan["domain_id"],
                                f"Below {industry} average citation rate",
                                f"Your citation rate ({citation_rate}%) is below the "
                                f"{industry} average ({b['avg_citation_rate']}% across "
                                f"{b['domain_count']} companies). Focus on structured data "
                                f"and content structure to close the gap.",
                            ),
                        )

        conn.commit()
        conn.close()
        return recs


def _describe_pattern(section: str, check_name: str, verdict: str, details: dict) -> dict | None:
    """Convert a check result into a learnable pattern description."""
    if verdict == "PASS":
        return None  # Only learn from failures and partials

    severity = "critical" if verdict == "FAIL" else "medium"

    patterns = {
        # Map both legacy keys (seo_*, ai_*) and actual scan check names (1.x_*, 2.x_*)
        "seo_crawlability": {
            "description": f"Crawlability {verdict}: site may have missing robots.txt, sitemap, or HTTPS issues",
            "fix": "Ensure robots.txt is accessible (200 status), sitemap.xml exists and is linked from robots.txt, and HTTPS is enforced with proper redirects.",
            "severity": "critical",
        },
        "seo_indexability": {
            "description": f"Indexability {verdict}: content may not be rendered server-side or has noindex directives",
            "fix": "Enable server-side rendering (SSR/SSG). Remove noindex meta tags from important pages. Ensure canonical URLs are set correctly.",
            "severity": "critical",
        },
        "seo_schema_markup": {
            "description": f"Schema markup {verdict}: structured data missing or incomplete",
            "fix": "Add JSON-LD structured data with Organization, WebPage, and domain-specific schemas (FAQ, Product, HowTo). Target >80% page coverage.",
            "severity": "high",
        },
        "seo_page_speed": {
            "description": f"Page speed {verdict}: Core Web Vitals may not meet thresholds",
            "fix": "Target LCP < 2.5s, CLS < 0.1, INP < 200ms. Common fixes: image optimization, font preloading, reducing JavaScript bundle size.",
            "severity": "medium",
        },
        "seo_content_quality": {
            "description": f"Content quality {verdict}: text-to-HTML ratio or content depth issues",
            "fix": "Increase substantive content on key pages. Aim for >500 words on landing pages. Add FAQ sections with structured data.",
            "severity": "medium",
        },
        "ai_crawler_access": {
            "description": f"AI crawler access {verdict}: AI bots may be blocked by robots.txt",
            "fix": "Allow GPTBot, ClaudeBot, PerplexityBot, and Google-Extended in robots.txt. Do not blanket-block all bots.",
            "severity": "critical",
        },
        "ai_structured_data_depth": {
            "description": f"Structured data depth {verdict}: schema coverage insufficient for AI extraction",
            "fix": "Add FAQ schema to top 20 pages. Add HowTo schema to tutorial/guide content. Ensure every page has at least WebPage schema.",
            "severity": "high",
        },
        "ai_content_structure": {
            "description": f"Content structure {verdict}: heading hierarchy or semantic HTML issues",
            "fix": "Use single H1 per page, logical H2/H3 hierarchy. Use semantic HTML (article, main, nav, section) instead of generic divs.",
            "severity": "medium",
        },
        "ai_semantic_html": {
            "description": f"Semantic HTML {verdict}: missing semantic elements that AI uses for content parsing",
            "fix": "Wrap main content in <article> or <main>. Use <nav> for navigation. Use <section> with headings for content blocks.",
            "severity": "medium",
        },
        "ai_content_ratio": {
            "description": f"Content ratio {verdict}: low text-to-HTML ratio makes AI extraction harder",
            "fix": "Reduce framework boilerplate. Increase substantive text content. Move scripts to external files.",
            "severity": "low",
        },
    }

    # Map actual AVR scan check names to pattern keys
    check_name_map = {
        "1.1_core_web_vitals": "seo_page_speed",
        "1.2_technical_crawlability": "seo_crawlability",
        "1.3_schema_markup": "seo_schema_markup",
        "1.5_page_speed": "seo_page_speed",
        "1.6_content_indexability": "seo_indexability",
        "2.1_ai_crawler_access": "ai_crawler_access",
        "2.2_structured_data_depth": "ai_structured_data_depth",
        "2.3_content_structure": "ai_content_structure",
        "2.4_content_ratio": "ai_content_ratio",
        "2.5_semantic_html": "ai_semantic_html",
    }

    # Try direct match first, then mapped name
    mapped_name = check_name_map.get(check_name, check_name)
    pattern = patterns.get(check_name) or patterns.get(mapped_name)
    if pattern:
        pattern["severity"] = pattern.get("severity", severity)
        return pattern

    # Generic fallback
    return {
        "description": f"{check_name} {verdict}",
        "fix": None,
        "severity": severity,
    }


def _default_fix(check_name: str) -> str:
    """Default fix recommendation when no knowledge base entries exist."""
    pattern = _describe_pattern("unknown", check_name, "FAIL", {})
    if pattern and pattern.get("fix"):
        return pattern["fix"]
    return f"Review and fix: {check_name.replace('_', ' ')}"
