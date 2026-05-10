#!/usr/bin/env python3
"""
Citability AI Visibility Dashboard
Streamlit app reading from dashboard.db with knowledge base integration.

Run: streamlit run dashboard/app.py
"""

import json
import sqlite3
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from knowledge_base import KnowledgeBase

# ================================================================
# CONFIG
# ================================================================

DB_PATH = Path(__file__).parent / "dashboard.db"
APP_TITLE = "Citability - AI Visibility Dashboard"

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="<target>",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_kb() -> KnowledgeBase:
    return KnowledgeBase(str(DB_PATH))


@st.cache_data(ttl=60)
def query_db(sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ================================================================
# SIDEBAR
# ================================================================

st.sidebar.title("Citability Dashboard")
page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Scan Details", "Industry Benchmarks", "Knowledge Base", "Outreach"],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Data Status**")
scan_count = query_db("SELECT COUNT(*) as n FROM scans")[0]["n"]
domain_count = query_db("SELECT COUNT(*) as n FROM domains")[0]["n"]
ke_count = query_db(
    "SELECT COUNT(*) as n FROM knowledge_entries"
    if "knowledge_entries" in [r["name"] for r in query_db("SELECT name FROM sqlite_master WHERE type='table'")]
    else "SELECT 0 as n"
)[0]["n"]

st.sidebar.metric("Domains Scanned", domain_count)
st.sidebar.metric("Total Scans", scan_count)
st.sidebar.metric("Knowledge Entries", ke_count)


# ================================================================
# PAGE: OVERVIEW
# ================================================================

def page_overview():
    st.title("AI Visibility Overview")
    st.markdown("Cross-company scan results at a glance.")

    # Latest scans table
    kb = get_kb()
    scans = kb.get_latest_scans()

    if not scans:
        st.warning("No scans in database. Run AVR scans first.")
        return

    # Verdict distribution
    col1, col2, col3, col4 = st.columns(4)
    verdicts = [s["overall_verdict"] for s in scans if s["overall_verdict"]]
    verdict_counts = {v: verdicts.count(v) for v in set(verdicts)}

    col1.metric("AI-READY", verdict_counts.get("AI-READY", 0))
    col2.metric("FOUNDATION-READY", verdict_counts.get("FOUNDATION-READY", 0))
    col3.metric("INFRA-READY", verdict_counts.get("INFRASTRUCTURE-READY", 0))
    col4.metric("NOT-READY", verdict_counts.get("NOT-READY", 0))

    st.markdown("---")

    # Scan results table
    st.subheader("Latest Scan Results")
    table_data = []
    for s in scans:
        table_data.append({
            "Domain": s.get("domain", ""),
            "Brand": s.get("brand_name", ""),
            "Industry": (s.get("industry") or "").title(),
            "Overall": s.get("overall_verdict", ""),
            "SEO": s.get("seo_verdict", ""),
            "AI Infra": s.get("ai_verdict", ""),
            "Citation %": f"{s['citation_rate_pct']:.1f}%" if s.get("citation_rate_pct") is not None else "N/A",
            "Visibility %": f"{s['visibility_rate_pct']:.1f}%" if s.get("visibility_rate_pct") is not None else "N/A",
            "Checks": f"{s.get('checks_passed', 0)}/{s.get('checks_total', 0)}",
        })
    st.dataframe(table_data, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Charts
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Citation Rates by Domain")
        citation_data = [
            {"Domain": s["brand_name"], "Citation Rate %": s["citation_rate_pct"] or 0}
            for s in scans if s.get("citation_rate_pct") is not None
        ]
        if citation_data:
            fig = px.bar(
                citation_data,
                x="Domain",
                y="Citation Rate %",
                color="Citation Rate %",
                color_continuous_scale=["#ef4444", "#f59e0b", "#22c55e"],
                range_color=[0, 50],
            )
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("Visibility Rates by Domain")
        vis_data = [
            {"Domain": s["brand_name"], "Visibility Rate %": s["visibility_rate_pct"] or 0}
            for s in scans if s.get("visibility_rate_pct") is not None
        ]
        if vis_data:
            fig = px.bar(
                vis_data,
                x="Domain",
                y="Visibility Rate %",
                color="Visibility Rate %",
                color_continuous_scale=["#ef4444", "#f59e0b", "#22c55e"],
                range_color=[0, 60],
            )
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)

    # Key insight callout
    st.markdown("---")
    st.subheader("Key Insights")

    avg_citation = sum(s["citation_rate_pct"] for s in scans if s.get("citation_rate_pct")) / max(1, sum(1 for s in scans if s.get("citation_rate_pct")))
    ai_ready_pct = 100 * verdict_counts.get("AI-READY", 0) / max(1, len(scans))

    insights = [
        f"**{ai_ready_pct:.0f}%** of scanned companies are AI-READY ({verdict_counts.get('AI-READY', 0)}/{len(scans)})",
        f"Average citation rate: **{avg_citation:.1f}%** across {len(scans)} scans",
        f"Best SEO company (JustCall) still only achieves **21.4%** citation rate: SEO != AI Citability",
    ]
    for insight in insights:
        st.markdown(f"- {insight}")


# ================================================================
# PAGE: SCAN DETAILS
# ================================================================

def page_scan_details():
    st.title("Scan Details")

    domains = query_db("SELECT id, domain, brand_name FROM domains ORDER BY brand_name")
    if not domains:
        st.warning("No domains in database.")
        return

    selected = st.selectbox(
        "Select Domain",
        domains,
        format_func=lambda d: f"{d['brand_name']} ({d['domain']})",
    )

    if not selected:
        return

    # Get all scans for this domain
    scans = query_db(
        """SELECT * FROM scans WHERE domain_id = ? ORDER BY scanned_at DESC""",
        (selected["id"],),
    )

    if not scans:
        st.info(f"No scans found for {selected['domain']}")
        return

    # If multiple scans, show comparison
    if len(scans) > 1:
        st.subheader("Re-scan Comparison")
        latest = scans[0]
        previous = scans[1]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Latest** ({latest['scanned_at'][:10]})")
            st.metric("Overall", latest["overall_verdict"])
            st.metric(
                "Citation Rate",
                f"{latest['citation_rate_pct']:.1f}%" if latest.get("citation_rate_pct") is not None else "N/A",
                delta=f"{(latest.get('citation_rate_pct') or 0) - (previous.get('citation_rate_pct') or 0):.1f}pp" if latest.get("citation_rate_pct") is not None and previous.get("citation_rate_pct") is not None else None,
            )
        with col2:
            st.markdown(f"**Previous** ({previous['scanned_at'][:10]})")
            st.metric("Overall", previous["overall_verdict"])
            st.metric("Citation Rate", f"{previous['citation_rate_pct']:.1f}%" if previous.get("citation_rate_pct") is not None else "N/A")

        st.markdown("---")

    # Show latest scan details
    scan = scans[0]
    kb = get_kb()
    details = kb.get_scan_details(scan["id"])

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Overall", scan["overall_verdict"])
    col2.metric("SEO", scan["seo_verdict"])
    col3.metric("AI Infra", scan["ai_verdict"])
    col4.metric("Checks", f"{scan['checks_passed']}/{scan['checks_total']}")

    st.markdown("---")

    # Individual checks
    st.subheader("Check Results")
    tab_seo, tab_ai = st.tabs(["SEO Foundation", "AI Infrastructure"])

    with tab_seo:
        seo_checks = [c for c in details.get("checks", []) if c["section"] == "seo"]
        for check in seo_checks:
            verdict_color = {"PASS": "green", "PARTIAL": "orange", "FAIL": "red"}.get(check["verdict"], "gray")
            st.markdown(f":{verdict_color}[**{check['verdict']}**] {check['check_name'].replace('_', ' ').title()}")
            if check.get("summary"):
                st.caption(check["summary"])

    with tab_ai:
        ai_checks = [c for c in details.get("checks", []) if c["section"] == "ai"]
        for check in ai_checks:
            verdict_color = {"PASS": "green", "PARTIAL": "orange", "FAIL": "red"}.get(check["verdict"], "gray")
            st.markdown(f":{verdict_color}[**{check['verdict']}**] {check['check_name'].replace('_', ' ').title()}")
            if check.get("summary"):
                st.caption(check["summary"])

    # Citation details
    if details.get("citations"):
        st.markdown("---")
        st.subheader("Citation Test Results")
        citation_table = []
        for c in details["citations"]:
            citation_table.append({
                "Platform": c["platform"],
                "Category": c.get("category", ""),
                "Query": c["query_text"][:80],
                "Status": c["status"],
                "Cited URLs": c.get("cited_urls_json", "[]"),
            })
        st.dataframe(citation_table, use_container_width=True, hide_index=True)

    # Visibility details
    if details.get("visibility"):
        st.markdown("---")
        st.subheader("Visibility Test Results")
        vis_table = []
        for v in details["visibility"]:
            vis_table.append({
                "Platform": v["platform"],
                "Category": v.get("category", ""),
                "Query": v["query_text"][:80],
                "Visible": "Yes" if v["is_visible"] else "No",
                "Recognition": v.get("brand_recognition_level", ""),
                "Recommended": "Yes" if v.get("is_recommended") else "No",
            })
        st.dataframe(vis_table, use_container_width=True, hide_index=True)

    # Recommendations
    if details.get("recommendations"):
        st.markdown("---")
        st.subheader("Recommendations")
        for rec in details["recommendations"]:
            icon = {1: "!!!", 2: "!!", 3: "!"}.get(rec["priority"], "")
            badge = " (knowledge-informed)" if rec["source"] == "knowledge_informed" else ""
            st.markdown(f"**P{rec['priority']}** {rec['title']}{badge}")
            st.caption(rec["description"])


# ================================================================
# PAGE: INDUSTRY BENCHMARKS
# ================================================================

def page_benchmarks():
    st.title("Industry Benchmarks")
    st.markdown("Aggregated metrics from all scans, grouped by industry. Grows more accurate with each scan.")

    kb = get_kb()
    benchmarks = kb.get_industry_benchmarks()

    if not benchmarks:
        st.info("Need scan data across industries to show benchmarks.")
        return

    # Benchmarks table
    st.subheader("Metrics by Industry")
    bench_table = []
    for b in benchmarks:
        bench_table.append({
            "Industry": (b["industry"] or "").title(),
            "Domains": b["domain_count"],
            "Scans": b["scan_count"],
            "Avg Citation %": f"{b['avg_citation_rate']:.1f}%" if b.get("avg_citation_rate") is not None else "N/A",
            "Avg Visibility %": f"{b['avg_visibility_rate']:.1f}%" if b.get("avg_visibility_rate") is not None else "N/A",
            "% AI-Ready": f"{b['pct_ai_ready']:.0f}%",
            "% SEO Pass": f"{b['pct_seo_pass']:.0f}%",
            "Avg Check Pass Rate": f"{b['avg_check_pass_rate']:.0f}%",
        })
    st.dataframe(bench_table, use_container_width=True, hide_index=True)

    # Check failure rates
    st.markdown("---")
    st.subheader("Most Common Failures (across all scans)")
    failures = kb.get_check_failure_rates()
    if failures:
        failure_data = [
            {
                "Check": f["check_name"].replace("_", " ").title(),
                "Section": f["section"].upper(),
                "Failure Rate %": f["failure_rate_pct"],
                "Fail": f["fail_count"],
                "Partial": f["partial_count"],
                "Pass": f["pass_count"],
            }
            for f in failures
        ]
        fig = px.bar(
            failure_data,
            x="Check",
            y="Failure Rate %",
            color="Section",
            title="Check Failure Rates",
            color_discrete_map={"SEO": "#3b82f6", "AI": "#8b5cf6"},
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    # Confidence note
    st.markdown("---")
    total_scans = sum(b["scan_count"] for b in benchmarks)
    if total_scans < 20:
        st.warning(
            f"Benchmarks based on **{total_scans} scans**. "
            f"Need 20+ for reliable industry averages. "
            f"Run more Tier 2 scans to improve confidence."
        )
    else:
        st.success(f"Benchmarks based on **{total_scans} scans** across {len(benchmarks)} industries.")


# ================================================================
# PAGE: KNOWLEDGE BASE
# ================================================================

def page_knowledge():
    st.title("Knowledge Base")
    st.markdown("Learnable patterns extracted from scans. The system gets smarter with each audit.")

    kb = get_kb()

    # Knowledge entry count
    entries = query_db(
        "SELECT COUNT(*) as n FROM knowledge_entries"
        if "knowledge_entries" in [r["name"] for r in query_db("SELECT name FROM sqlite_master WHERE type='table'")]
        else "SELECT 0 as n"
    )
    total_entries = entries[0]["n"]

    if total_entries == 0:
        st.info("Knowledge base is empty. Click 'Seed from existing scans' to populate.")
        if st.button("Seed from existing scans"):
            scans = query_db("SELECT id FROM scans")
            count = 0
            for s in scans:
                count += kb.ingest_knowledge_from_scan(s["id"])
            st.success(f"Ingested {count} knowledge entries from {len(scans)} scans.")
            st.rerun()
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Entries", total_entries)

    # Entries by section
    by_section = query_db(
        "SELECT section, COUNT(*) as n FROM knowledge_entries GROUP BY section ORDER BY n DESC"
    )
    col2.metric("Sections Covered", len(by_section))

    # Entries by industry
    by_industry = query_db(
        "SELECT industry, COUNT(*) as n FROM knowledge_entries GROUP BY industry ORDER BY n DESC"
    )
    col3.metric("Industries", len(by_industry))

    st.markdown("---")

    # Browse by industry
    st.subheader("Browse Patterns")
    industry_filter = st.selectbox(
        "Filter by Industry",
        ["All"] + [i["industry"].title() for i in by_industry],
    )

    if industry_filter == "All":
        patterns = query_db(
            "SELECT * FROM knowledge_entries ORDER BY created_at DESC LIMIT 50"
        )
    else:
        patterns = query_db(
            "SELECT * FROM knowledge_entries WHERE industry = ? ORDER BY created_at DESC LIMIT 50",
            (industry_filter.lower(),),
        )

    for p in patterns:
        severity_color = {"critical": "red", "high": "orange", "medium": "blue", "low": "gray"}.get(p["severity"], "gray")
        st.markdown(f":{severity_color}[**{p['severity'].upper()}**] [{p['section'].upper()}] {p['check_name']}")
        st.caption(p["pattern_description"])
        if p.get("fix_recommended"):
            st.markdown(f"> **Fix:** {p['fix_recommended']}")
        st.markdown("")

    # Recommendation effectiveness (empty until re-scans happen)
    st.markdown("---")
    st.subheader("Recommendation Effectiveness")
    effectiveness = kb.get_effective_fixes()
    if effectiveness:
        st.dataframe(effectiveness, use_container_width=True, hide_index=True)
    else:
        st.info("No recommendation outcomes tracked yet. Re-scan a domain after implementing fixes to start the feedback loop.")

    # Ingest new scans
    st.markdown("---")
    if st.button("Re-ingest all scans"):
        scans = query_db("SELECT id FROM scans")
        count = 0
        for s in scans:
            count += kb.ingest_knowledge_from_scan(s["id"])
        st.success(f"Ingested {count} knowledge entries from {len(scans)} scans.")
        st.rerun()


# ================================================================
# PAGE: OUTREACH
# ================================================================

def page_outreach():
    st.title("Outreach Pipeline")
    st.markdown("Cold email campaign tracking. Populated when leads are loaded into MoneyPrinter CRM.")

    # Lead list from domains table
    leads = query_db(
        """SELECT d.domain, d.brand_name, d.industry, d.icp_fit,
                  s.overall_verdict, s.citation_rate_pct, s.visibility_rate_pct
           FROM domains d
           LEFT JOIN v_latest_scans s ON s.domain_id = d.id
           ORDER BY d.icp_fit, d.brand_name"""
    )

    if not leads:
        st.info("No leads in database.")
        return

    # Scanned vs not scanned
    scanned = [l for l in leads if l.get("overall_verdict")]
    not_scanned = [l for l in leads if not l.get("overall_verdict")]

    col1, col2 = st.columns(2)
    col1.metric("Leads with Scan Data", len(scanned))
    col2.metric("Leads Pending Scan", len(not_scanned))

    st.markdown("---")
    st.subheader("Scanned Leads (ready for personalized outreach)")
    if scanned:
        scan_table = [
            {
                "Brand": l["brand_name"],
                "Domain": l["domain"],
                "Industry": (l.get("industry") or "").title(),
                "ICP Fit": l.get("icp_fit", ""),
                "Verdict": l.get("overall_verdict", ""),
                "Citation %": f"{l['citation_rate_pct']:.1f}%" if l.get("citation_rate_pct") is not None else "N/A",
                "Visibility %": f"{l['visibility_rate_pct']:.1f}%" if l.get("visibility_rate_pct") is not None else "N/A",
            }
            for l in scanned
        ]
        st.dataframe(scan_table, use_container_width=True, hide_index=True)

    # Outreach tracking (will populate once CRM data flows in)
    st.markdown("---")
    st.subheader("Campaign Tracking")
    outreach = query_db("SELECT COUNT(*) as n FROM outreach")
    if outreach[0]["n"] == 0:
        st.info("No outreach records yet. Load leads into MoneyPrinter CRM after warmup (~Apr 27).")
    else:
        stages = query_db(
            "SELECT deal_stage, COUNT(*) as n FROM outreach GROUP BY deal_stage"
        )
        st.dataframe([dict(s) for s in stages], use_container_width=True, hide_index=True)


# ================================================================
# ROUTING
# ================================================================

pages = {
    "Overview": page_overview,
    "Scan Details": page_scan_details,
    "Industry Benchmarks": page_benchmarks,
    "Knowledge Base": page_knowledge,
    "Outreach": page_outreach,
}

pages[page]()
