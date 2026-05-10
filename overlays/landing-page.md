# AVR Overlay: Landing Page

Applies the universal AVR framework (`FRAMEWORK.md`) to **single-URL conversion
surfaces**: a page whose purpose is to answer one implicit question ("what does
this do?") in service of one action ("sign up / buy / book"). Landing pages are
the hardest surface to make AI-citable because their value density is high but
their passage structure is low — a hero + three bullets + a CTA button is not
what an AI retriever chunks well.

If a check is not mentioned in an adjustments section below, it applies unchanged
from `FRAMEWORK.md`.

## Scope

A site qualifies for the landing-page overlay when it is **a single URL (or a
very small set of sibling URLs) optimized for one conversion action**. Scope is
narrow on purpose: if the site has docs, blog, or multi-feature pages, use
`overlays/saas.md` instead.

**In scope (positive examples):**
- Single-product micro-SaaS landing pages (one product, one CTA)
- Newsletter signup pages
- Waitlist pages
- Conference / event pages
- One-off campaign pages (e.g., product launch pages)
- Standalone pricing-or-trial pages where the root IS the primary surface

**Out of scope (negative examples):**
- Multi-surface SaaS sites (landing + docs + pricing)
  → use `overlays/saas.md`
- Content blogs where the homepage lists recent posts
  → use `overlays/blog.md`
- E-commerce category or product pages (they are part of a product catalog, not
  a single-intent page)
  → universal framework; no overlay applies cleanly yet

**Single-URL audit.** Unlike the SaaS overlay, a landing-page audit runs only
on the single primary URL. Do not crawl a sitemap; the sitemap may not exist
or may be padded with irrelevant URLs.

## Tier 1 adjustments (SEO Foundation)

| Check | Overlay adjustment |
|-------|-------------------|
| 1.1 Core Web Vitals | **Strict**: landing pages are read once and judged in seconds. `FAIL` if LCP > 2.5s. No PARTIAL tolerance. |
| 1.2 Technical Crawlability | Unchanged, but `sitemap.xml` is optional (single-URL sites). `robots.txt` is still required. |
| 1.3 Schema Markup | Require `Organization` OR `WebSite` OR `SoftwareApplication` OR `Product` schema — the exact type depends on what is being offered. Missing schema on a single-URL site is `FAIL`. |
| 1.4 Mobile Friendliness | **Strict**: landing pages get more mobile traffic than any other page class. Any `PARTIAL` signal (viewport, tap targets, font size) becomes `FAIL`. |
| 1.5 Page Speed | **Strict**: Performance Score ≥ 80 required. Landing pages often have unoptimized hero videos, webfont cascades, third-party analytics — this check catches all of them. |
| 1.6 Content Indexability | **Strict**: CSR-only is `FAIL`. A landing page that renders "only in a browser" is invisible to AI retrievers and to shared-link previews. |

## Tier 2 adjustments (AI Infrastructure)

| Check | Overlay adjustment |
|-------|-------------------|
| 2.1 AI Crawler Access | Unchanged. |
| 2.2 Structured Data Depth | Relaxed: a single URL cannot have "depth across pages." Require at minimum `Organization` + one content-type schema (`Product` / `SoftwareApplication` / `Article`). Two schema types is `PASS`; one is `PARTIAL`; zero is `FAIL`. |
| 2.3 Content Structure Quality | **Tightened answer-first rule (see L1 below).** The value proposition must appear in the first two sentences of visible body text, before any paragraph of context or narrative. |
| 2.4 Machine-Readable Content Ratio | Relaxed: landing pages intentionally use imagery and whitespace. Content ratio > 15% is acceptable (universal is 25%). Below 10% is still `FAIL` (AI crawlers have nothing to extract). |
| 2.5 Semantic HTML | Require `<main>` for the primary content region and `<section>` for each value block. `<div>`-soup landing pages score `PARTIAL`. |

## Tier 3 adjustments (Citation Monitoring)

Landing pages are cited primarily through **category-entry queries** and
**branded-plus-category queries**. Adjust the 20-query landscape:

- **2 brand queries** (brand name, product name — only 2 because new landing
  pages rarely have brand recognition; most citation opportunity is category-
  entry)
- **6 category-entry queries** ("best X for Y", "X tool recommendations",
  "tools like Z where Z is a known-big-competitor")
- **6 direct-intent queries** (the literal question the landing page answers —
  "how do I do X", "do I need Y for Z") — these test whether the page's
  value proposition matches stated user intent
- **4 comparison queries** ("X vs Y", "alternatives to X") — tests whether the
  landing page is retrievable in comparison contexts
- **2 "what is this" queries** — directly tests whether the landing page's
  answer-first structure is reachable ("what is <brand>", "what does <domain>
  do")

Total 20 queries × 3 platforms = 60 pairs per round.

Check 3.2 (Brand Mention Detection) is almost always `UNKNOWN` for new landing
pages — record it, but the result is informative mainly as a waypoint to
revisit after 30–60 days of content and backlink work.

## Type-specific checks

These four checks run **in addition to** the universal 14.

### L1. Value proposition in first two sentences (tightened answer-first)

**What it measures:** Whether a reader can understand *what the product does*
and *who it is for* from the first two visible sentences of body text, without
scrolling.

**How to run:** Fetch the page source. Extract the first 2–3 sentences after
the H1. The value prop must include at minimum: (a) a noun for the product
category, (b) a verb or noun for the user's problem, (c) a named audience or
use-case.

**Pass / fail:**
- `PASS`: first 2 sentences contain all three elements.
- `PARTIAL`: 2 of 3 elements (e.g., category + problem but no audience).
- `FAIL`: first 2 sentences are marketing adjectives with no operational noun
  ("The future of work, reimagined.").

### L2. Category-entry prompt presence

**What it measures:** Whether the literal category phrase AI systems use to
retrieve competitors appears in the page's copy (H1 / H2s / first paragraph).
A page that describes itself in bespoke language never matches category-entry
retrieval.

**How to run:** Run `"best <category>"` on one AI platform. Note the category
phrase it echoes back (e.g., "scheduling tool," "meeting scheduler,"
"calendar assistant"). Grep the landing-page copy for that phrase.

**Pass / fail:**
- `PASS`: exact phrase present in H1, H2, or first 200 words of body.
- `PARTIAL`: phrase present somewhere on the page, but not in prominent copy.
- `FAIL`: phrase absent; page describes itself in brand-invented vocabulary.

### L3. Conversion-signal schema

**What it measures:** Whether the landing page exposes the schema types an AI
system uses to understand what action the page wants a user to take.

**How to run:** Check JSON-LD for at least one of: `Product`,
`SoftwareApplication`, `Service`, `Offer`, `AggregateOffer`, or `Event` (for
event landing pages). Plus `Organization` with a valid `url` and `sameAs`.

**Pass / fail:**
- `PASS`: at least one action/offer schema + `Organization` schema.
- `PARTIAL`: one schema present, other missing.
- `FAIL`: neither present, or only generic `WebPage` schema.

### L4. Single-intent coherence

**What it measures:** Whether the page pursues one intent end-to-end, or
whether it mixes multiple intents that fragment AI retrieval.

**How to run:** Count CTAs. Classify each CTA by intent (sign up / buy /
download / contact / subscribe). Multi-intent pages (e.g., "Sign up" + "Read
our blog" + "Download whitepaper" all prominent) weaken each retrieval path.

**Pass / fail:**
- `PASS`: one primary CTA, repeated consistently; at most one secondary CTA
  subordinated visually.
- `PARTIAL`: two competing CTAs of equal prominence.
- `FAIL`: three or more competing CTAs with no visual hierarchy.

## Status verdict overrides

**One override:** a landing page that fails L1 (value prop in first two
sentences) cannot reach `AI-READY` even if all universal checks pass. Rationale:
answer-first structure is the one load-bearing property of landing-page
citability — a page that hides its value prop behind a narrative lede has no
quotable opening for an AI retriever, and the universal Check 2.3 is not strict
enough to catch this on a short page.

Status when L1 fails while universal checks PASS: `INFRASTRUCTURE-READY`, with
L1 as the primary Actionable Recommendation.

All other type-specific failures (L2, L3, L4) surface as Actionable
Recommendations without changing the status verdict.

## Canonical examples

Landing-page-class audits in `sample-audits/` are limited; the closest
references:

| Site | Verdict | Date | Note |
|------|---------|------|------|
| citability.dev | `INFRASTRUCTURE-READY` | 2026-04-15 | The landing surface of the product that runs AVR audits. SEO PARTIAL (TTFB), AI infra PASS. Meets L1, L3; L2 varies by prompt. Reference case for "landing page of a dev-tool SaaS." |
| chudi.dev/blog | (audited as blog overlay) | 2026-04-15 | NOT a landing page in the overlay sense — blog overlay applies. Noted here to prevent miscategorization. |

[Target] — add 2–3 landing-page-class audits to `sample-audits/` before the next
revision of this overlay, so canonical examples can cover `NOT-READY`,
`FOUNDATION-READY`, and `AI-READY` cases.
