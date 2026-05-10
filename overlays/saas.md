# AVR Overlay: SaaS

Applies the universal AVR framework (`FRAMEWORK.md`) to multi-surface product
sites: a root landing page plus features / pricing / docs / changelog / (often)
blog surfaces. SaaS sites fail AVR audits in a distinctive way — brand visibility
is usually high, but citation rate is low, because pages are optimized for a
logged-in buyer journey rather than for passage extraction by an AI retriever.
See the 15-company prospect scan (`prospect-scans/SCAN_RESULTS_SUMMARY.md`): 0/15
SaaS companies reached `AI-READY`, and the average visibility-citation gap was
36.3 points.

If a check is not mentioned in an adjustments section below, it applies unchanged
from `FRAMEWORK.md`.

## Scope

A site qualifies for the SaaS overlay when it sells a software product or
service to businesses or developers and has **at least two distinct page
classes** — e.g., landing + docs, landing + pricing, landing + features. Single-
page marketing sites use `overlays/landing-page.md` instead.

**In scope (positive examples):**
- B2B SaaS product sites (Calendly, Notion, Loom, Drift, Algolia, Braze)
- Developer tools with docs (Contentful, Algolia, citability.dev)
- API / platform products (Fireblocks)

**Out of scope (negative examples):**
- Personal portfolios with a "Services" page
  → use `overlays/landing-page.md` if single-intent, otherwise the blog overlay
- Documentation-only sites (no sales surface)
  → audit as a SaaS docs surface, but skip the pricing / features sections below
- Pure marketplace sites
  → universal framework; SaaS-specific checks below will not map cleanly

**Multi-surface audit.** SaaS sites should be audited at **three URL classes**
per round: (1) the root landing page, (2) a representative docs page, (3) the
pricing page (or the first feature page if no pricing is exposed). Report a
per-class verdict plus a site-level roll-up (worst of the three).

## Tier 1 adjustments (SEO Foundation)

| Check | Overlay adjustment |
|-------|-------------------|
| 1.1 Core Web Vitals | Unchanged. |
| 1.2 Technical Crawlability | **Strict**: docs subdomain must be in the primary `sitemap.xml` or expose its own discoverable sitemap. Docs behind a subdomain with no sitemap entry score `FAIL`. |
| 1.3 Schema Markup | Require `Organization` schema on the root, with `sameAs` linking to LinkedIn + GitHub (for dev tools) + Crunchbase. Require `Product` or `SoftwareApplication` schema on product / pricing pages. |
| 1.4 Mobile Friendliness | Unchanged. |
| 1.5 Page Speed | Unchanged, but flag when docs pages load > 3s — docs are read for reference, slow docs correlate with low citation (AI retrievers time out). |
| 1.6 Content Indexability | **Strict**: SaaS marketing pages rendered CSR-only are a `FAIL`. Most frameworks (Next, Nuxt, SvelteKit) support SSR/SSG by default — CSR-only in 2026 is an active choice. |

## Tier 2 adjustments (AI Infrastructure)

| Check | Overlay adjustment |
|-------|-------------------|
| 2.1 AI Crawler Access | **Strict**: blocking any of GPTBot, ClaudeBot, PerplexityBot is `FAIL` for SaaS. The prospect-scan data shows blanket-blocked sites have 0% citation and single-digit visibility. |
| 2.2 Structured Data Depth | Docs pages need `TechArticle` or `HowTo` schema, not `WebPage`. Pricing pages need `Offer` or `AggregateOffer` schema. Homepage alone with `Organization` scores `PARTIAL`. |
| 2.3 Content Structure Quality | **Load-bearing for docs surfaces, relaxed for landing surfaces.** Docs require FAQ-style patterns and H2-per-concept; landing pages are measured instead by Check 2.3 at a relaxed bar (one clear H1 + value-prop paragraph). |
| 2.4 Machine-Readable Content Ratio | Relaxed for landing pages (they have more chrome by design); unchanged for docs. |
| 2.5 Semantic HTML | Require `<main>` on every page class. Docs need `<article>` wrapping content. Pricing pages need `<table>` (not CSS grid of divs) for plan comparison. |

## Tier 3 adjustments (Citation Monitoring)

SaaS products are most often discovered through **intent queries**, not brand
queries. Adjust the 20-query landscape:

- **3 brand queries** (company name, product name, founder/CEO name if
  public-facing)
- **5 category-entry queries** ("best X tool", "X alternatives", "X vs Y" where
  Y is the most-cited competitor — pull competitor names from one round of
  Check 3.1 on the top category query)
- **5 use-case queries** ("how do I X with [category]", "[category] for Y
  use-case", "[job-to-be-done]") — these test whether the product gets
  recommended in *problem* framings, not just *product* framings
- **4 docs-intent queries** ("how to [specific feature]", "[feature] API",
  "[feature] best practices") — these test whether the docs surface is
  retrievable independent of the marketing surface
- **3 pricing / evaluation queries** ("[product] pricing", "is [product] worth
  it", "[product] free tier")

Total 20 queries × 3 platforms = 60 pairs per round.

Check 3.2 (Brand Mention Detection) is **highly informative** for SaaS — the
visibility-citation gap is the characteristic SaaS failure mode. Always run it
and always report the gap explicitly (visibility % minus citation %).

## Type-specific checks

These four checks run **in addition to** the universal 14.

### S1. Intent-per-page coherence

**What it measures:** Whether each of the three audited URL classes (landing /
docs / pricing) addresses a single dominant intent, or whether the site crams
multiple intents onto one page (e.g., docs with embedded pricing upsells).

**How to run:** For each audited page, classify the intent
(informational / commercial / navigational / transactional). Multi-intent pages
score `PARTIAL` regardless of other checks.

**Pass / fail:**
- `PASS`: each URL class has a single clear intent.
- `PARTIAL`: one of the three classes is multi-intent.
- `FAIL`: two or more classes are multi-intent, or the landing page is
  informational-only (no call-to-action).

### S2. Brand + category prompt coverage

**What it measures:** Whether the site explicitly covers the `"[brand] + [category]"`
query pattern AI systems use when a user names the brand and asks for context.

**How to run:** Query `"what is <brand>"` and `"<brand> for <category>"` on all
3 platforms. Check whether the brand's own pages appear as cited sources (not
just third-party summaries).

**Pass / fail:**
- `PASS`: brand's own pages cited on ≥ 2 platforms.
- `PARTIAL`: brand mentioned by name but not cited on any platform (the
  visibility-citation gap).
- `FAIL`: brand not mentioned by name (`UNKNOWN` on Check 3.2).

### S3. Docs freshness signal

**What it measures:** Whether docs pages expose a visible "last updated" date
and whether that date is within the last 6 months for at least 50% of pages.
AI retrievers prefer fresh sources; stale docs get skipped.

**How to run:** Sample 10 docs pages. Look for a "last updated" or "revised"
date in visible text, or a `<time datetime>` element, or a `dateModified` in
JSON-LD.

**Pass / fail:**
- `PASS`: ≥ 70% of sampled docs have a visible date, ≥ 50% within 6 months.
- `PARTIAL`: ≥ 50% have a date, but > 50% are older than 6 months.
- `FAIL`: < 50% of docs have any date signal.

### S4. Feature → use-case page split

**What it measures:** Whether the site has distinct pages for each major
feature *and* a separate set of pages for each major use-case, or whether it
conflates the two. AI retrievers cite use-case pages for problem queries and
feature pages for solution queries — a site with only feature pages will miss
half the retrieval surface.

**How to run:** From the primary navigation, count feature pages (named after
a capability) vs use-case pages (named after a job or problem). Inspect the
sitemap for dedicated use-case URLs.

**Pass / fail:**
- `PASS`: ≥ 3 feature pages and ≥ 3 use-case pages, distinct URLs and copy.
- `PARTIAL`: feature pages only, but with use-case sections inside each feature
  page.
- `FAIL`: one landing page conflates features and use-cases with no dedicated
  URLs.

## Status verdict overrides

None. SaaS-type-specific failures surface as Actionable Recommendations, not as
status-verdict overrides. An overlay-aware audit MAY additionally report a
per-class verdict (landing / docs / pricing), but the site-level status verdict
follows the core framework rules.

## Canonical examples

Verdicts drawn from `prospect-scans/SCAN_RESULTS_SUMMARY.md` (2026-04-14 /
2026-04-15). Re-audit before quoting.

| Site | Verdict | Citation % | Visibility % | Note |
|------|---------|-----------|--------------|------|
| citability.dev | `INFRASTRUCTURE-READY` | — | — | SEO partial (TTFB issues on hosted audit runs), AI infra PASS. The product that runs AVR audits lives one notch below its own top verdict. |
| JustCall | `FOUNDATION-READY` | 21.4% | 36.8% | Tier 1 PASS, Tier 2 PARTIAL. Demonstrates that SEO-clean does not imply AI-ready. |
| Calendly | `NOT-READY` | 7.1% | 88.2% | **Reference case for the visibility-citation gap.** ChatGPT knows Calendly (88% visibility) but almost never links to calendly.com (7% citation) — classic S2 failure. |
| Notion | `NOT-READY` | 7.1% | 58.8% | SEO FAIL. Popular SaaS with blanket CSR rendering; AI crawlers see an empty page. |
| Drift | `NOT-READY` | 21.4% | 52.9% | Tier 1 FAIL (CWV + crawlability), Tier 2 PARTIAL. |
| Algolia | `NOT-READY` | 7.1% | 76.5% | Tier 1 PARTIAL, Tier 2 PARTIAL. High visibility due to strong developer-brand recognition; citation gap from unrendered docs. |

Reference benchmark: in the 15-company prospect scan, **0/15 SaaS companies
reached `AI-READY`**; only 3/15 reached `FOUNDATION-READY`. The universal
baseline is not being met in this category, which is why the SaaS overlay
tightens Tier 1 and Tier 2 thresholds rather than adding more Tier 3 prompts.
