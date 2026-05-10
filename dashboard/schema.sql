-- ============================================================
-- AI Citability Dashboard - SQLite Schema
-- AVR Framework v1.0.0
-- ============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ============================================================
-- CORE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS domains (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    domain              TEXT NOT NULL UNIQUE,
    brand_name          TEXT NOT NULL,
    owner_name          TEXT,
    industry            TEXT,
    icp_fit             TEXT CHECK (icp_fit IN ('HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'))
                        DEFAULT 'UNKNOWN',
    topics_json         TEXT DEFAULT '[]',
    concepts_json       TEXT DEFAULT '[]',
    products_json       TEXT DEFAULT '[]',
    tier                TEXT CHECK (tier IN ('free_scan', 'quick_report', 'full_audit', 'sprint'))
                        DEFAULT 'free_scan',
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_domains_domain    ON domains (domain);
CREATE INDEX IF NOT EXISTS idx_domains_industry  ON domains (industry);
CREATE INDEX IF NOT EXISTS idx_domains_icp_fit   ON domains (icp_fit);


CREATE TABLE IF NOT EXISTS scans (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id           INTEGER NOT NULL REFERENCES domains (id) ON DELETE CASCADE,
    scanned_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    avr_version         TEXT NOT NULL DEFAULT 'v1.0.0',

    overall_verdict     TEXT NOT NULL
                        CHECK (overall_verdict IN ('AI-READY','FOUNDATION-READY','INFRASTRUCTURE-READY','NOT-READY')),
    seo_verdict         TEXT NOT NULL CHECK (seo_verdict IN ('PASS','PARTIAL','FAIL')),
    ai_verdict          TEXT NOT NULL CHECK (ai_verdict IN ('PASS','PARTIAL','FAIL')),

    citation_verdict    TEXT CHECK (citation_verdict IN ('CITED','PARTIALLY_CITED','NOT_CITED','ERROR')),
    citation_rate_pct   REAL,
    citation_total      INTEGER,
    citation_tested     INTEGER,
    citation_cited      INTEGER,
    citation_ci_low     REAL,
    citation_ci_high    REAL,
    citation_confidence TEXT CHECK (citation_confidence IN ('HIGH','MODERATE','LOW')),

    visibility_verdict  TEXT CHECK (visibility_verdict IN ('HIGHLY_VISIBLE','PARTIALLY_VISIBLE','BARELY_VISIBLE','INVISIBLE')),
    visibility_rate_pct REAL,
    visibility_total    INTEGER,
    visibility_tested   INTEGER,
    visibility_visible  INTEGER,
    visibility_known    INTEGER,
    visibility_recommended INTEGER,

    checks_passed       INTEGER DEFAULT 0,
    checks_total        INTEGER DEFAULT 0,

    seo_json_path       TEXT,
    ai_json_path        TEXT,
    citation_raw_path   TEXT,
    citation_summary_path TEXT,
    visibility_raw_path TEXT,
    visibility_summary_path TEXT,

    notes               TEXT
);

CREATE INDEX IF NOT EXISTS idx_scans_domain_id   ON scans (domain_id);
CREATE INDEX IF NOT EXISTS idx_scans_scanned_at  ON scans (scanned_at);
CREATE INDEX IF NOT EXISTS idx_scans_overall     ON scans (overall_verdict);


CREATE TABLE IF NOT EXISTS scan_checks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id             INTEGER NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    section             TEXT NOT NULL CHECK (section IN ('seo','ai')),
    check_name          TEXT NOT NULL,
    tier                TEXT,
    verdict             TEXT NOT NULL CHECK (verdict IN ('PASS','PARTIAL','FAIL','SKIPPED','ERROR')),
    details_json        TEXT DEFAULT '{}',
    summary             TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_scan_checks_scan_id    ON scan_checks (scan_id);
CREATE INDEX IF NOT EXISTS idx_scan_checks_check_name ON scan_checks (check_name);
CREATE INDEX IF NOT EXISTS idx_scan_checks_verdict    ON scan_checks (verdict);


CREATE TABLE IF NOT EXISTS platform_queries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id             INTEGER NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    platform            TEXT NOT NULL CHECK (platform IN ('ChatGPT','Perplexity','Claude')),
    query_id            INTEGER,
    category            TEXT,
    query_text          TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('CITED','NOT_CITED','ERROR')),
    cited_urls_json     TEXT DEFAULT '[]',
    response_snippet    TEXT,
    error_message       TEXT,
    queried_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_pq_scan_id    ON platform_queries (scan_id);
CREATE INDEX IF NOT EXISTS idx_pq_platform   ON platform_queries (platform);
CREATE INDEX IF NOT EXISTS idx_pq_status     ON platform_queries (status);
CREATE INDEX IF NOT EXISTS idx_pq_category   ON platform_queries (category);


CREATE TABLE IF NOT EXISTS visibility_queries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id             INTEGER NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    platform            TEXT NOT NULL CHECK (platform IN ('ChatGPT','Perplexity','Claude')),
    query_id            INTEGER,
    category            TEXT NOT NULL,
    signal              TEXT,
    query_text          TEXT NOT NULL,
    is_visible          INTEGER NOT NULL DEFAULT 0,

    brand_recognition_level TEXT
        CHECK (brand_recognition_level IN ('KNOWN','PARTIALLY_KNOWN','UNKNOWN')),
    brand_domain_mentioned  INTEGER DEFAULT 0,
    brand_name_mentioned    INTEGER DEFAULT 0,
    brand_owner_mentioned   INTEGER DEFAULT 0,

    concept_ratio       REAL,
    concepts_found_json TEXT DEFAULT '[]',

    is_recommended      INTEGER DEFAULT 0,
    recommended_as_json TEXT DEFAULT '[]',

    response_snippet    TEXT,
    error_message       TEXT,
    queried_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_vq_scan_id   ON visibility_queries (scan_id);
CREATE INDEX IF NOT EXISTS idx_vq_platform  ON visibility_queries (platform);
CREATE INDEX IF NOT EXISTS idx_vq_category  ON visibility_queries (category);
CREATE INDEX IF NOT EXISTS idx_vq_visible   ON visibility_queries (is_visible);


CREATE TABLE IF NOT EXISTS fixes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id             INTEGER NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    domain_id           INTEGER NOT NULL REFERENCES domains (id) ON DELETE CASCADE,
    priority            INTEGER NOT NULL DEFAULT 2,
    category            TEXT NOT NULL,
    check_name          TEXT,
    description         TEXT NOT NULL,
    status              TEXT NOT NULL
        CHECK (status IN ('open','in_progress','done','wont_fix'))
        DEFAULT 'open',
    resolved_at         TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_fixes_domain_id  ON fixes (domain_id);
CREATE INDEX IF NOT EXISTS idx_fixes_scan_id    ON fixes (scan_id);
CREATE INDEX IF NOT EXISTS idx_fixes_status     ON fixes (status);
CREATE INDEX IF NOT EXISTS idx_fixes_priority   ON fixes (priority);


CREATE TABLE IF NOT EXISTS outreach (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id           INTEGER NOT NULL REFERENCES domains (id) ON DELETE CASCADE,
    contact_email       TEXT,
    contact_name        TEXT,
    contact_title       TEXT,
    sequence_step       INTEGER NOT NULL DEFAULT 1,
    email_sent_at       TEXT,
    opened              INTEGER DEFAULT 0,
    opened_at           TEXT,
    replied             INTEGER DEFAULT 0,
    replied_at          TEXT,
    meeting_booked      INTEGER DEFAULT 0,
    meeting_booked_at   TEXT,
    deal_stage          TEXT
        CHECK (deal_stage IN ('cold','warm','demo_scheduled','proposal_sent','closed_won','closed_lost','nurture'))
        DEFAULT 'cold',
    deal_value          REAL,
    email_subject       TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_outreach_domain_id   ON outreach (domain_id);
CREATE INDEX IF NOT EXISTS idx_outreach_deal_stage  ON outreach (deal_stage);
CREATE INDEX IF NOT EXISTS idx_outreach_email_sent  ON outreach (email_sent_at);


-- ============================================================
-- VIEWS
-- ============================================================

CREATE VIEW IF NOT EXISTS v_latest_scans AS
SELECT
    d.id              AS domain_id,
    d.domain,
    d.brand_name,
    d.industry,
    d.icp_fit,
    s.id              AS scan_id,
    s.scanned_at,
    s.overall_verdict,
    s.seo_verdict,
    s.ai_verdict,
    s.citation_verdict,
    s.citation_rate_pct,
    s.visibility_verdict,
    s.visibility_rate_pct,
    s.checks_passed,
    s.checks_total
FROM domains d
LEFT JOIN scans s ON s.id = (
    SELECT id FROM scans
    WHERE domain_id = d.id
    ORDER BY scanned_at DESC
    LIMIT 1
);

CREATE VIEW IF NOT EXISTS v_latest_citation_by_platform AS
SELECT
    d.domain,
    d.brand_name,
    pq.scan_id,
    s.scanned_at,
    pq.platform,
    COUNT(*)                                              AS total_queries,
    SUM(CASE WHEN pq.status = 'CITED' THEN 1 ELSE 0 END) AS cited_count,
    ROUND(
        100.0 * SUM(CASE WHEN pq.status = 'CITED' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN pq.status != 'ERROR' THEN 1 ELSE 0 END), 0),
        1
    ) AS citation_rate_pct
FROM platform_queries pq
JOIN scans s ON s.id = pq.scan_id
JOIN domains d ON d.id = s.domain_id
WHERE s.id = (
    SELECT id FROM scans WHERE domain_id = s.domain_id ORDER BY scanned_at DESC LIMIT 1
)
GROUP BY d.domain, pq.platform;
