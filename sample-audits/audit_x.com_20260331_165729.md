# AI Visibility Readiness Audit

**URL:** https://x.com
**Date:** 2026-03-31 16:57 UTC
**Framework:** AVR v1.0.0

---

## Executive Summary

**Overall Status: NOT-READY**

This audit ran 9 automated checks across two categories: SEO Foundation (traditional search readiness) and AI Infrastructure (AI search readiness). **2 of 9 checks passed.**

Both SEO foundations and AI infrastructure need work. Start with SEO fundamentals. AI visibility cannot exist without search visibility.

| Section | Verdict |
|---------|---------|
| SEO Foundation | [FAIL] |
| AI Infrastructure | [FAIL] |

### Top 3 Actions (in priority order)

1. Add structured data (JSON-LD) with appropriate @type for your content.
2. Fix content indexability: ensure server-side rendering and remove noindex tags.
3. Update robots.txt to allow GPTBot, ClaudeBot, and PerplexityBot.

---

## Section 1: SEO Foundation

**Section Verdict:** [FAIL]

### 1.1 Core Web Vitals
**Tier:** VERIFIABLE | **Verdict:** [SKIPPED]

*Lighthouse skipped (--skip-lighthouse flag)*

### 1.5 Page Speed
**Tier:** VERIFIABLE | **Verdict:** [SKIPPED]

*Lighthouse skipped (--skip-lighthouse flag)*

### 1.2 Technical Crawlability
**Tier:** VERIFIABLE | **Verdict:** [PASS]

- **robots_txt:** status: 200, exists: True, size_bytes: 2514
- **sitemap:** status: 200, exists: True, size_bytes: 246554
- **https:** enforced: True, http_redirects: True

### 1.3 Schema Markup
**Tier:** VERIFIABLE | **Verdict:** [FAIL]

No structured data found.

### 1.6 Content Indexability
**Tier:** VERIFIABLE | **Verdict:** [FAIL]

- **text_length_chars:** 493
- **has_substantial_content:** False
- **paragraph_count:** 3
- **has_noindex:** False
- **canonical_present:** False
- **canonical_href:** 

---

## Section 2: AI Infrastructure Readiness

**Section Verdict:** [FAIL]

### 2.1 Llms Txt
**Tier:** VERIFIABLE | **Verdict:** [PASS]

- **Status Code:** 200
- **Content Type:** text/html; charset=utf-8
- **Line Count:** 354
- **Char Count:** 246539
- **Preview:** `<!DOCTYPE html><html dir="ltr" lang="en"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=0,viewport-fit=cover" /><link rel="preconnect" href="//abs.twimg.com" /><link rel="dns-prefetch" href="//abs.twimg.com" /><link rel="preconnect" href="//api.twitter.com" /><link rel="dns-prefetch" href="//api.twitter.com" /><link rel="preconnect" href="//api.x.com" /><link rel="dns-prefetch" href="//api.x.com" /><link rel="preconnect" href="//pbs.twimg.com" /><link rel="dns-prefetch" href="//pbs.twimg.com" /><link rel="preconnect" href="//t.co" /><link rel="dns-prefetch" href="//t.co" /><link rel="preconnect" href="//video.twimg.com" /><link rel="dns-prefetch" href="//video.twimg.com" /><link nonce="N2I4M2ZhMjgtNDI3OS00OTk2LWEyY2ItNTJiMTJjOGI4OWRj" rel="preload" as="script" crossorigin="anonymous" href="https://abs.twimg.com/responsive-web/client-web/vendor.f1dc7e4a.js" /><link nonce="N2I4M2ZhMjgtNDI3OS00OTk2LWEyY2ItNTJiMTJjOGI4OWRj" rel="preload" as="script" crossorigin="anonymous" href="https://abs.twimg.com/responsive-web/client-web/i18n/en.901ee17a.js" /><link nonce="N2I4M2ZhMjgtNDI3OS00OTk2LWEyY2ItNTJiMTJjOGI4OWRj" rel="preload" as="script" crossorigin="anonymous" href="https://abs.twimg.com/responsive-web/client-web/main.f7ac183a.js" /><meta http-equiv="onion-location" content="https://twitter3e4tixl4xyajtrzo62zg5vztmjuricljdp2c5kshju4avyoid.onion/" /><meta property="fb:app_id" content="2231777543" /><meta content="X (formerly Twitter)" property="og:site_name" /><meta name="google-site-verification" content="reUF-TgZq93ZGtzImw42sfYglI2hY0QiGRmfc4jeKbs" /><meta name="facebook-domain-verification" content="x6sdcc8b5ju3bh8nbm59eswogvg6t1" /><link rel="search" type="application/opensearchdescription+xml" href="/os-x.xml" title="X"> | <link rel="search" type="application/opensearchdescription+xml" href="/os-grok.xml" title="Grok"><link rel="apple-touch-icon" sizes="192x192" href="https://abs.twimg.com/responsive-web/client-web/icon-ios.77d25eba.png" /><meta name="twitter-site-verification" content="dbRmuape0udoTZzNr9+9iGrx5sA3hSjdDlChVP08Qh9gdHn4UwtH0jblts7f4tU1" /><link rel="manifest" href="/manifest.json" crossOrigin="use-credentials" /><link rel="search" type="application/opensearchdescription+xml" href="/os-x.xml" title="X"><link rel="search" type="application/opensearchdescription+xml" href="/os-grok.xml" title="Grok"><link rel="mask-icon" sizes="any" href="https://abs.twimg.com/responsive-web/client-web/icon-svg.ea5ff4aa.svg" color="#1D9BF0"><link rel="shortcut icon" href="//abs.twimg.com/favicons/twitter.3.ico"><meta name="theme-color" media="(prefers-color-scheme: light)" content="#FFFFFF" /><meta name="theme-color" media="(prefers-color-scheme: dark)" content="#000000" /><meta http-equiv="origin-trial" content="AlpCmb40F5ZjDi9ZYe+wnr/V8MF+XmY41K4qUhoq+2mbepJTNd3q4CRqlACfnythEPZqcjryfAS1+ExS0FFRcA8AAABmeyJvcmlnaW4iOiJodHRwczovL3R3aXR0ZXIuY29tOjQ0MyIsImZlYXR1cmUiOiJMYXVuY2ggSGFuZGxlciIsImV4cGlyeSI6MTY1NTI1MTE5OSwiaXNTdWJkb21haW4iOnRydWV9" /><style>html,body{height: 100%;}::cue{white-space:normal}</style><style id="react-native-stylesheet">[stylesheet-group="0"]{} | body{margin:0;}`

### 2.2 Ai Crawler Access
**Tier:** VERIFIABLE | **Verdict:** [FAIL]

### 2.3 Structured Data Depth
**Tier:** VERIFIABLE | **Verdict:** [FAIL]

- **Pages Checked:** 1
- **Pages With Schema:** 0
- **Coverage Pct:** 0.0
- **Schema types:** None
- **Unique Type Count:** 0
- **Has Rich Result Types:** False

### 2.4 Content Structure
**Tier:** VERIFIABLE | **Verdict:** [FAIL]

- **H1 Count:** 1
- **Total Headings:** 1
- **Hierarchy Clean:** True
- **Section Count:** 0
- **Paragraph Count:** 3
- **Avg Paragraph Words:** 15.0
- **Has Faq Pattern:** False
  - H1: JavaScript is not available.

### 2.5 Content Ratio
**Tier:** VERIFIABLE | **Verdict:** [FAIL]

- **Total Html Bytes:** 246539
- **Text Content Bytes:** 492
- **Content Ratio Pct:** 0.2
- **Content Sufficient Override:** False

### 2.6 Semantic Html
**Tier:** VERIFIABLE | **Verdict:** [PARTIAL]

- **Images Total:** 1
- **Images With Alt:** 1
- **Alt Text Coverage Pct:** 100.0

---

## Recommendations

### Priority 1: Fix SEO Foundation
AI visibility depends on traditional search visibility. Fix Section 1 failures first.

- **1.3_schema_markup**: Needs attention
- **1.6_content_indexability**: Needs attention

### Priority 2: Improve AI Infrastructure
These checks ensure AI systems can find and parse your content.

- **2.2_ai_crawler_access**: FAIL
- **2.3_structured_data_depth**: FAIL
- **2.4_content_structure**: FAIL
- **2.5_content_ratio**: FAIL
- **2.6_semantic_html**: PARTIAL

---

*Generated by AI Visibility Readiness Framework v1.0.0*
*Methodology: [FRAMEWORK.md](../FRAMEWORK.md)*

**Disclaimer:** Section 3 (Citation Monitoring) results are point-in-time observations with LOW confidence.
AI citation behavior varies by session, location, and platform updates.
Do not make investment decisions based on a single citation test round.