# AVR Overlay: Blog

Applies the universal AVR framework (`FRAMEWORK.md`) to content-first sites whose
primary value unit is a long-form article, not a product page, not a conversion
funnel, not a docs tree. An overlay **does not replace** any of the 14 core
checks — it reweights them, changes the Tier 3 prompt mix, and adds 3 type-specific
checks that the universal framework does not run.

If a check is not mentioned in an adjustments section below, it applies unchanged
from `FRAMEWORK.md`.

## Scope

A site qualifies for the blog overlay when **a majority of its indexable pages are
articles** — dated posts addressing a specific question or topic, authored by a
person (or a small named editorial team), organized by topic clusters rather than
product funnels.

**In scope (positive examples):**
- Personal technical blogs (chudi.dev, brandontran.dev)
- Single-author editorial sites
- Niche content hubs with topic pillars + cluster pages
- Newsletter archives surfaced as browsable articles

**Out of scope (negative examples):**
- Company "Resources" sections whose real purpose is lead capture
  → use `overlays/saas.md`, treat the blog as a subordinate surface
- Listicle farms with no named author
  → universal framework is sufficient; type-specific checks below will not fit
- Documentation sites (even if blog-styled)
  → use `overlays/saas.md` (docs are a SaaS surface)

**Mixed-surface resolution.** When a site has a blog *inside* a product domain
(e.g., `company.com/blog/*`), audit the blog surface with this overlay and the
product surface with the SaaS overlay. Record both verdicts; report the worse of
the two as the site-level default unless the operator specifies otherwise.

## Tier 1 adjustments (SEO Foundation)

| Check | Overlay adjustment |
|-------|-------------------|
| 1.1 Core Web Vitals | Unchanged. Blogs often fail LCP because of hero images — flag but do not treat as fatal for a blog that otherwise passes Tier 2. |
| 1.2 Technical Crawlability | Unchanged. Blogs *must* expose a sitemap that enumerates every post — blog platforms that paginate without a sitemap score `FAIL` even if the default `sitemap.xml` returns 200. |
| 1.3 Schema Markup | Require `Article`, `BlogPosting`, or `TechArticle` `@type` on post pages; `Person` schema for the author; `WebSite` schema on the homepage. Check `PARTIAL` if only `WebSite` is present. |
| 1.4 Mobile Friendliness | Unchanged. |
| 1.5 Page Speed | Relaxed threshold: Performance Score ≥ 70 is acceptable for a blog post with a large lead image, provided INP ≤ 200ms. Rationale: blogs are read-once, not revisited; the CWV bar is Tier 3 behavior, not Tier 1. |
| 1.6 Content Indexability | **Strict**: blog content rendered client-side-only is a `FAIL`. Articles that are not in the HTML source are invisible to every AI crawler. No partial credit. |

## Tier 2 adjustments (AI Infrastructure)

| Check | Overlay adjustment |
|-------|-------------------|
| 2.1 AI Crawler Access | Unchanged. |
| 2.2 Structured Data Depth | Raise the bar: ≥ 80% of posts must carry `BlogPosting` or equivalent, not just the homepage. Check `PARTIAL` if homepage-only. |
| 2.3 Content Structure Quality | **Load-bearing for blogs.** Strict heading hierarchy, average paragraph < 120 words (tighter than the universal 150), at least one H2 per ~400 words of body copy. |
| 2.4 Machine-Readable Content Ratio | Raise target: content ratio > 40% (universal is 25%). Blogs have less chrome than product pages; a 20% ratio means bloated theme or heavy client-side analytics. |
| 2.5 Semantic HTML | Require `<article>` wrapping post body. `<time datetime>` for published-date. `<main>` for primary column. Missing any of these three is `PARTIAL`. |

## Tier 3 adjustments (Citation Monitoring)

The universal Check 3.1 asks for 20 queries split 5/5/5/5 across brand / topic-
authority / long-tail / competitor-adjacent. For blogs, shift the mix to reward
topical depth:

- **3 brand queries** (author + domain + title of the most-linked post)
- **7 topic-pillar queries** ("how to X", "what is Y", "best way to Z" on the
  site's 2–3 topic pillars — pull from the site's own tag or category tree)
- **7 long-tail query fan-out variants** (for each pillar, 2–3 paraphrases of the
  same underlying intent — tests paraphrase coverage directly)
- **3 competitor-adjacent queries** (where a more established site currently
  owns the topic cluster — tests share-of-voice)

Total still 20 queries × 3 platforms = 60 pairs per round; interpretation per
Check 3.1 and the tightened confidence-interval rules in `FRAMEWORK.md`
§Methodology Notes.

Check 3.2 (Brand Mention Detection) is less informative for small blogs — a
site with DA < 10 will score `UNKNOWN` on every platform by default. Run it, but
do not weight the result in the status rollup unless the brand is the author's
name and the expectation is personal-brand recognition.

## Type-specific checks

These three checks run **in addition to** the universal 14. A blog that passes
the universal checks but fails the type-specific checks still reaches the core
status verdict — the type-specific failures show up as Actionable Recommendations
in the report, not as verdict overrides.

### B1. Pillar / cluster internal-link density

**What it measures:** Whether the site's topic pillars are supported by densely
linked cluster pages, the pattern that signals topical authority to both
classical rankers and AI retrievers.

**How to run:** Crawl up to 50 posts. For each post, count outbound links to
other posts on the same site. Flag when the median is < 2 internal links per
post, or when > 30% of posts have zero internal links.

**Pass / fail:**
- `PASS`: median ≥ 3 internal links per post; every pillar page has ≥ 5 linked
  cluster pages.
- `PARTIAL`: median 1–2 internal links per post.
- `FAIL`: > 30% of posts have zero internal links.

### B2. Author schema and bylines

**What it measures:** Whether the author is established as an entity across the
site in both machine-readable form (`Person` schema with `sameAs`) and
human-readable form (byline on every post).

**How to run:** Grep post pages for `"@type":\s*"Person"` in JSON-LD, and check
that `sameAs` includes at least two external profiles (LinkedIn, GitHub,
Wikipedia, Twitter/X, Mastodon). Visually: every post has a visible byline.

**Pass / fail:**
- `PASS`: Person schema present on every post, `sameAs` ≥ 2 external profiles,
  byline visible.
- `PARTIAL`: schema on some posts but not all, or `sameAs` only lists self-owned
  domains.
- `FAIL`: no Person schema on posts, or no visible byline.

### B3. Long-tail paraphrase coverage in H2s

**What it measures:** Whether the H2 structure of a pillar post covers the
likely query-fan-out variants a user would ask an AI, not just the literal title.

**How to run:** Pick one pillar post. Extract its H2s. Run its target query
through 3 AI systems and note the paraphrases they pose to themselves (often
visible in the response wording, or in Perplexity's "Related" suggestions). The
H2s should address at least 3 of the ~5 typical paraphrases.

**Pass / fail:**
- `PASS`: H2s address ≥ 3 paraphrase variants.
- `PARTIAL`: H2s address 1–2 paraphrase variants.
- `FAIL`: H2s only restate the title or segment by chronology ("Part 1,"
  "Part 2").

## Status verdict overrides

None. Blog-type-specific failures surface as Actionable Recommendations, not as
status-verdict overrides. Rationale: the core framework's verdict rules are
principled (SEO is downstream of visibility; composite scoring hides tiers); an
overlay that changed the verdict rules would mean the overlay is really a
different framework.

## Canonical examples

Drawn from the audits in `sample-audits/` and `prospect-scans/`. Verdicts reflect
the audit on the cited date; re-audit before quoting.

| Site | Verdict | Date | Note |
|------|---------|------|------|
| chudi.dev | `AI-READY` | 2026-04-15 | Single-author technical blog. Tier 1 PASS, Tier 2 PASS; meets B1-B3. Reference case for overlay calibration. |
| brandontran.dev | `NOT-READY` | 2026-03-31 | Personal site with no `sitemap.xml`, no `Article` schema, no AI-crawler directives. Fails B2 (no Person schema). Reference case for "floor of the overlay." |
| ahrefs.com | `FOUNDATION-READY` | 2026-03-31 | High-authority industry blog (and product). Tier 1 PASS, Tier 2 PARTIAL; meets B1, partial on B2. Demonstrates that high DA plus blog content does not automatically reach AI-READY. |

[Target] — add a second mid-range blog (DA 30–50) as a canonical reference once
such an audit is available in `sample-audits/`.
