# AVR Glossary

Terminology reference for the AI Visibility Readiness (AVR) framework. Every term
here is defined once, with a cross-reference to the section of `FRAMEWORK.md` or an
`overlays/*.md` file where it is operationalized. When a term in the spec or an
overlay does not match a definition here, the glossary is wrong or the document is
wrong — not both. Fix whichever is out of sync.

**Scope note on the "15-check" framing.** AVR v1.0 shipped with 15 checks. AVR v1.1
removed Check 2.1 (`llms.txt`) after evidence that no major AI company confirms
reading it; current AVR is **14 checks across 3 tiers**. Older marketing copy
referencing "15 checks" is stale — this glossary matches the current spec.

---

## Core audit terms

### AI Visibility Audit
A project-based service that measures a site's readiness to be retrieved and cited
by AI-powered search systems (ChatGPT, Perplexity, Google AI Overviews, Claude,
Gemini). Unlike a classical SEO audit, an AVR audit labels every check as
`[VERIFIABLE]` or `[BEST-EFFORT]` and refuses to collapse the result into a single
composite score. → `FRAMEWORK.md` §Philosophy.

### Prompt Landscape
The structured set of queries representing what a real user would ask an AI system
in territory the site intends to own. Not limited to branded queries. For AVR audits
the landscape is fixed at **20 queries × 3 platforms** per round (see Check 3.1); the
*shape* of the 20 varies by site type — blog, SaaS, and landing-page overlays each
define their own prompt mix. → `FRAMEWORK.md` §Check 3.1, `overlays/*.md` §Tier 3
adjustments.

### Prompt Cluster
A thematic grouping of related queries within a prompt landscape, e.g.,
"alternatives-to" queries for SaaS, "how-to" queries for blogs, "category-entry"
queries for landing pages. Clusters are how we avoid cherry-picking: citation
patterns reported per-cluster, not just as a global rate. → `overlays/*.md` §Tier 3
adjustments.

### Discrete Status
The overall verdict of an AVR audit. Exactly one of: `AI-READY`,
`INFRASTRUCTURE-READY`, `FOUNDATION-READY`, `NOT-READY`. Deliberately not a number.
→ `FRAMEWORK.md` §Overall Readiness Assessment.

### Evidence Tier
The label every AVR check carries. `[VERIFIABLE]` = objective, reproducible,
backed by a free API or CLI — anyone gets the same answer. `[BEST-EFFORT]` =
point-in-time observation whose result varies by session, location, and phrasing.
Sections 1 and 2 are fully `[VERIFIABLE]`; Section 3 is fully `[BEST-EFFORT]`.
→ `FRAMEWORK.md` §Philosophy.

---

## Citation and grounding

### Citation
An explicit reference to a source — URL, domain, document title, or inline quote —
in an AI-generated answer. In AVR, citation is tested per query per platform; the
unit of count is the query-platform pair. → `FRAMEWORK.md` §Check 3.1.

### Citation Rate
Actual citations ÷ total query-platform pairs tested. A single round (20 queries ×
3 platforms = 60 pairs) yields a `LOW` confidence estimate; multiple rounds raise
the confidence tier (see **Confidence Tier**). Verdict thresholds: `CITED` > 15%,
`PARTIALLY_CITED` 1–15%, `NOT_CITED` 0%. → `FRAMEWORK.md` §Check 3.1.

### Citation Context
The role a citation plays in the surrounding answer: primary authority, supporting
example, or marginal aside. AVR v1.1 does not require classifying context
automatically — the auditor notes context in the per-query record when it changes
the interpretation (e.g., "cited, but as a negative example"). → `FRAMEWORK.md`
§Check 3.1 (Notes column).

### Citation Quality
The combined assessment of whether a citation is accurate, relevant, and current
relative to the cited page's actual content. Measured by Check 3.3 (Retrieval
Quality Assessment), which only applies when Check 3.1 found at least one
citation. Verdict values: `ACCURATE`, `DISTORTED`, `OUTDATED`. → `FRAMEWORK.md`
§Check 3.3.

### Grounding
The process by which an AI system anchors a generated claim to a verifiable
external source. A grounded claim has an inspectable citation that matches the
claim in both substance and interpretation. Ungrounded claims are paraphrase
without source; fabricated grounding is **Hallucinated Citation**. AVR does not
audit the AI system's grounding pipeline; it audits whether your content is
*groundable* (Section 2 checks). → `FRAMEWORK.md` §Section 2 preamble.

### Hallucinated Citation
A citation that refers to a non-existent, incorrect, or irrelevant source
relative to the claim it is attached to. In the brand-mention check (Check 3.2),
`HALLUCINATED` is a specific verdict signalling potential reputation risk —
the AI is making up facts about the site and attributing them to a source that
does not support them. → `FRAMEWORK.md` §Check 3.2.

### Brand-Mention Verdict
The per-query verdict for Check 3.2 (Brand Mention Detection): `KNOWN`,
`PARTIAL`, `UNKNOWN`, or `HALLUCINATED`. Distinct from citation verdicts —
brand mention tests recognition, not retrieval-and-link. A brand can be `KNOWN`
across three platforms while having a 7% citation rate (see the Calendly case in
`prospect-scans/SCAN_RESULTS_SUMMARY.md`). → `FRAMEWORK.md` §Check 3.2.

### Visibility-Citation Gap
The difference between brand visibility (Check 3.2) and citation rate (Check 3.1).
A wide gap — high visibility, low citation — means AI systems recommend the brand
by name but rarely link to the brand's own pages. Structural cause: the site's
content is not retrievable or quotable, so the AI paraphrases from third-party
sources instead. → `prospect-scans/SCAN_RESULTS_SUMMARY.md` (15-company
benchmark: average gap 36.3pp).

---

## Relevance and retrieval

### Topical Relevance
How closely a page's content matches the semantic intent of a query cluster. Not
a direct AVR check; a prerequisite for citation. A site that passes every AVR
`[VERIFIABLE]` check but has no content addressing the query cluster will still
score `NOT_CITED` on Check 3.1. → `overlays/blog.md` §Tier 3 adjustments.

### Entity Relevance
Whether a page provides substantive information about the entity being queried
(brand, product, person) rather than an incidental mention. Incidental mentions
fragment the AI's entity graph; substantive pages anchor it. Entity relevance is
the implicit target of Check 3.2. → `overlays/saas.md` §Type-specific checks.

### Query Fan-out
The internal rephrasing AI systems perform on a user query before retrieval —
typically 3–10 paraphrase variants. A site whose content only matches the
literal query wording will underperform relative to a site whose content covers
paraphrase space (synonyms in H2s, FAQ blocks that restate the question). Not a
direct AVR check; an input shape to Check 3.1 prompt design. → `overlays/blog.md`
§Type-specific checks.

### Paraphrase Coverage
The proportion of probable query paraphrases a page addresses in its headings or
body copy. Operationalized in the blog overlay as a type-specific check (H2s
covering the fan-out variants of the target query). → `overlays/blog.md`
§Type-specific checks.

### Answer-First Structure
The discipline of placing the direct answer to a page's implicit question within
the first two sentences, before explanation, context, or narrative. Load-bearing
for AI citation because LLM rerankers preferentially select first-paragraph
answers. Enforced universally by Check 2.3 (Content Structure Quality) and tightened
further in the landing-page overlay. → `FRAMEWORK.md` §Check 2.3,
`overlays/landing-page.md` §Tier 2 adjustments.

### Passage Chunking
The property of content being extractable as self-contained passages (256–1024
tokens) that answer a discrete question. AI retrievers fetch passages, not pages;
content that requires three paragraphs of setup before the answer chunks poorly.
Tested implicitly by Check 2.3 (heading hierarchy, paragraph length). Load-bearing
for blog overlays. → `FRAMEWORK.md` §Check 2.3, `overlays/blog.md` §Tier 2
adjustments.

---

## Technical readiness

### AI Crawler
A bot operated by an AI company for the purpose of indexing web content for
retrieval or training. Distinct from classical search crawlers. The six AVR
tracks: `GPTBot` (OpenAI), `ChatGPT-User` (OpenAI), `ClaudeBot` (Anthropic),
`PerplexityBot` (Perplexity), `Google-Extended` (Google Gemini/AIO training),
`CCBot` (Common Crawl, consumed by many AI systems). → `FRAMEWORK.md`
§Check 2.1.

### AI Crawler Access
Whether the six tracked AI crawlers are permitted by `robots.txt` to access the
site. Tested by Check 2.1. Many sites opt out of AI search entirely by blanket-
blocking crawlers via "block all AI" templates; this is a closed door, not a
neutral choice. → `FRAMEWORK.md` §Check 2.1.

### `llms.txt` (deliberately excluded from AVR v1.1)
An emerging convention for exposing a site's summary and preferred entry points
to LLM crawlers. Proposed in 2024; ~10% adoption by 2026; no major AI company
confirms reading it. **AVR v1.1 explicitly does not score for `llms.txt`
presence** to avoid inflating scores on unvalidated signals. Monitored for
adoption; will be added as a check if confirmed crawler support lands from a
major platform. → `FRAMEWORK.md` §Section 2 preamble (Deliberately excluded).

### Semantic HTML
The use of HTML elements that convey structural meaning (`<article>`, `<main>`,
`<nav>`, `<section>`, `<time>`, `<figure>`) rather than generic `<div>`
containers. Helps AI systems identify which region of a page is the primary
content. Tested by Check 2.5. → `FRAMEWORK.md` §Check 2.5.

### Schema Markup
Structured data embedded in pages via JSON-LD, Microdata, or RDFa, conforming to
schema.org vocabulary. Makes entities, relationships, and page types directly
machine-readable. Tested for presence and validity by Check 1.3, and for depth
and type coverage by Check 2.2. → `FRAMEWORK.md` §Check 1.3, §Check 2.2.

### Machine-Readable Content Ratio
The proportion of a page's HTML bytes that are visible text versus scripts,
styles, and layout boilerplate. Higher ratios give AI crawlers more material to
index per byte fetched. Tested by Check 2.4. → `FRAMEWORK.md` §Check 2.4.

### Content Indexability
Whether primary content is present in the HTML source (SSR/SSG) rather than
rendered only after JavaScript execution. Most AI crawlers do not execute JS;
client-side-only content is invisible to them. Tested by Check 1.6.
→ `FRAMEWORK.md` §Check 1.6.

---

## Reporting and methodology

### Status Verdict
The single-value output of an AVR audit. One of:
- **AI-READY** — SEO `PASS`, AI Infrastructure `PASS`, Citations any.
- **INFRASTRUCTURE-READY** — SEO `PARTIAL`, AI Infrastructure `PASS`.
- **FOUNDATION-READY** — SEO `PASS`, AI Infrastructure `PARTIAL` or `FAIL`.
- **NOT-READY** — SEO `FAIL` (overrides everything).

The verdict exposes *which tier is failing*, which a composite score would hide.
→ `FRAMEWORK.md` §Overall Readiness Assessment.

### Section Verdict
The per-section result: `PASS`, `PARTIAL`, or `FAIL` for Sections 1 and 2;
`CITED`, `PARTIALLY_CITED`, or `NOT_CITED` for Section 3. Section verdicts are
never averaged — they roll up to the status verdict via the rule table.
→ `FRAMEWORK.md` §Per-Section Verdicts.

### Confidence Tier
The label attached to every `[BEST-EFFORT]` result indicating sample size and
stability. `LOW` = 60 query-platform pairs (one round of Check 3.1);
`MODERATE` = ~180 pairs (three rounds); `HIGH` = 600+ pairs (ten rounds or a
Wilson 95% CI narrower than ±10pp). See Framework §Check 3.1 and the tightened
confidence-interval math in §Methodology Notes. → `FRAMEWORK.md` §Check 3.1,
§Methodology Notes.

### Actionable Recommendation
A prioritized, specific change that improves one named failing check. AVR
recommendations are derived from real failing checks only — never a generic
best-practice list, never a "do all of these" dump. An overlay's
`Type-specific checks` section can generate type-specific recommendations that
would not appear on a universal audit. → `overlays/*.md` §Type-specific checks.

### Composite Score (deliberately NOT used)
A single 0–100 number summarizing AVR performance. AVR v1 refuses to produce
one. Rationale: a composite mixes `[VERIFIABLE]` and `[BEST-EFFORT]` tiers,
creating false precision; it hides which tier is failing, so a client cannot
act on it; and no vendor has published a ground-truth validation for any
composite in this space. "If a vendor sells you an AEO score, ask them: what is
the ground truth you validated this against?" → `FRAMEWORK.md` §Overall
Readiness Assessment, §What We Explicitly Do NOT Score.
