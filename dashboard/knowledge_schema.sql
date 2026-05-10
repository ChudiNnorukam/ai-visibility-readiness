-- ============================================================
-- Knowledge Base Extension - Self-Learning AVR System
-- Phase 1: SQL-based retrieval (no embeddings)
-- ============================================================

PRAGMA foreign_keys = ON;

-- ============================================================
-- KNOWLEDGE TABLES
-- ============================================================

-- Learnable patterns extracted from scans
-- Each row is one observation: "in {industry}, {check_name} was {verdict} because {root_cause}"
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id             INTEGER REFERENCES scans (id) ON DELETE SET NULL,
    domain_id           INTEGER REFERENCES domains (id) ON DELETE SET NULL,
    industry            TEXT NOT NULL,
    check_name          TEXT NOT NULL,
    section             TEXT NOT NULL CHECK (section IN ('seo', 'ai', 'citation', 'visibility')),
    verdict             TEXT NOT NULL,
    root_cause          TEXT,
    pattern_description TEXT NOT NULL,
    fix_recommended     TEXT,
    severity            TEXT CHECK (severity IN ('critical', 'high', 'medium', 'low')) DEFAULT 'medium',
    avr_version         TEXT NOT NULL DEFAULT 'v1.0.0',
    is_validated        INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_ke_industry ON knowledge_entries (industry);
CREATE INDEX IF NOT EXISTS idx_ke_check ON knowledge_entries (check_name);
CREATE INDEX IF NOT EXISTS idx_ke_section ON knowledge_entries (section);
CREATE INDEX IF NOT EXISTS idx_ke_verdict ON knowledge_entries (verdict);

-- Per-scan recommendations with trackable outcomes
CREATE TABLE IF NOT EXISTS recommendations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id             INTEGER NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    domain_id           INTEGER NOT NULL REFERENCES domains (id) ON DELETE CASCADE,
    priority            INTEGER NOT NULL DEFAULT 2,
    category            TEXT NOT NULL,
    check_name          TEXT,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    expected_impact     TEXT,
    effort_estimate     TEXT CHECK (effort_estimate IN ('hours', 'days', 'weeks', 'quarter')),
    status              TEXT NOT NULL
        CHECK (status IN ('proposed', 'accepted', 'in_progress', 'done', 'skipped', 'wont_fix'))
        DEFAULT 'proposed',
    source              TEXT CHECK (source IN ('rule_based', 'knowledge_informed', 'manual'))
        DEFAULT 'rule_based',
    similar_entry_ids   TEXT DEFAULT '[]',
    resolved_at         TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_rec_scan ON recommendations (scan_id);
CREATE INDEX IF NOT EXISTS idx_rec_domain ON recommendations (domain_id);
CREATE INDEX IF NOT EXISTS idx_rec_status ON recommendations (status);
CREATE INDEX IF NOT EXISTS idx_rec_category ON recommendations (category);

-- Feedback loop: did the fix work?
-- Populated when a domain is re-scanned after implementing a recommendation
CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id   INTEGER NOT NULL REFERENCES recommendations (id) ON DELETE CASCADE,
    before_scan_id      INTEGER NOT NULL REFERENCES scans (id),
    after_scan_id       INTEGER NOT NULL REFERENCES scans (id),
    metric_name         TEXT NOT NULL,
    before_value        REAL,
    after_value         REAL,
    delta               REAL,
    delta_pct           REAL,
    outcome             TEXT CHECK (outcome IN ('improved', 'no_change', 'degraded', 'inconclusive'))
        DEFAULT 'inconclusive',
    notes               TEXT,
    measured_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_ro_rec ON recommendation_outcomes (recommendation_id);
CREATE INDEX IF NOT EXISTS idx_ro_outcome ON recommendation_outcomes (outcome);

-- ============================================================
-- VIEWS for knowledge retrieval
-- ============================================================

-- Industry benchmarks: aggregated metrics per industry
CREATE VIEW IF NOT EXISTS v_industry_benchmarks AS
SELECT
    d.industry,
    COUNT(DISTINCT d.id) AS domain_count,
    COUNT(s.id) AS scan_count,
    ROUND(AVG(s.citation_rate_pct), 1) AS avg_citation_rate,
    ROUND(AVG(s.visibility_rate_pct), 1) AS avg_visibility_rate,
    ROUND(100.0 * SUM(CASE WHEN s.overall_verdict = 'AI-READY' THEN 1 ELSE 0 END) / COUNT(s.id), 1) AS pct_ai_ready,
    ROUND(100.0 * SUM(CASE WHEN s.seo_verdict = 'PASS' THEN 1 ELSE 0 END) / COUNT(s.id), 1) AS pct_seo_pass,
    ROUND(100.0 * SUM(CASE WHEN s.ai_verdict = 'PASS' THEN 1 ELSE 0 END) / COUNT(s.id), 1) AS pct_ai_pass,
    ROUND(AVG(s.checks_passed * 1.0 / NULLIF(s.checks_total, 0) * 100), 1) AS avg_check_pass_rate
FROM domains d
JOIN scans s ON s.domain_id = d.id
WHERE d.industry IS NOT NULL
GROUP BY d.industry;

-- Check pass rates across all scans (which checks fail most?)
CREATE VIEW IF NOT EXISTS v_check_failure_rates AS
SELECT
    sc.section,
    sc.check_name,
    COUNT(*) AS total_scans,
    SUM(CASE WHEN sc.verdict = 'PASS' THEN 1 ELSE 0 END) AS pass_count,
    SUM(CASE WHEN sc.verdict = 'FAIL' THEN 1 ELSE 0 END) AS fail_count,
    SUM(CASE WHEN sc.verdict = 'PARTIAL' THEN 1 ELSE 0 END) AS partial_count,
    ROUND(100.0 * SUM(CASE WHEN sc.verdict = 'FAIL' THEN 1 ELSE 0 END) / COUNT(*), 1) AS failure_rate_pct
FROM scan_checks sc
GROUP BY sc.section, sc.check_name
ORDER BY failure_rate_pct DESC;

-- Recommendation effectiveness: which fixes actually work?
CREATE VIEW IF NOT EXISTS v_recommendation_effectiveness AS
SELECT
    r.category,
    r.check_name,
    COUNT(*) AS total_recs,
    SUM(CASE WHEN r.status = 'done' THEN 1 ELSE 0 END) AS implemented,
    SUM(CASE WHEN ro.outcome = 'improved' THEN 1 ELSE 0 END) AS improved,
    SUM(CASE WHEN ro.outcome = 'no_change' THEN 1 ELSE 0 END) AS no_change,
    SUM(CASE WHEN ro.outcome = 'degraded' THEN 1 ELSE 0 END) AS degraded,
    ROUND(100.0 * SUM(CASE WHEN ro.outcome = 'improved' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN ro.outcome IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS success_rate_pct
FROM recommendations r
LEFT JOIN recommendation_outcomes ro ON ro.recommendation_id = r.id
GROUP BY r.category, r.check_name
HAVING total_recs > 0;
