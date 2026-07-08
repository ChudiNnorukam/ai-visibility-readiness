# Why Your AEO Score Is Made Up (And What to Measure Instead)

I spent 106 hours building AI visibility infrastructure for my blog. llms.txt files. Schema markup on every page. Citation tracking scripts. Daily GEO cron jobs. AI-readable content surfaces.

The result after three months: zero AI citations. Zero product sales. Eight organic clicks per month.

The infrastructure was technically correct. Every validator passed. Every structured data test came back green. I had done everything the AEO guides told me to do.

The problem was simpler than any of that. My domain had no authority. Google did not rank my pages. And AI search engines use web search results as their retrieval source. If Google cannot find you, ChatGPT never sees you.

I had built the roof before the foundation existed.

## The $10K Lesson

Here is what I learned the expensive way: AEO is downstream of SEO. Always. No exceptions.

AI Overviews pulls from Google's index. Perplexity crawls the web and weighs domain authority. ChatGPT's web browsing follows search results. Every AI search system starts with traditional search, then applies its own ranking on top.

If you do not rank in web search, AI search never sees you. All the llms.txt files and schema markup in the world cannot fix that.

This is not a controversial claim. It is how these systems work at the infrastructure level. But the AEO industry does not lead with it, because "fix your SEO first" is a harder sell than "optimize for AI with our proprietary score."

I verified this the hard way. My site had valid llms.txt, nine schema.org types across every page, semantic HTML, AI crawler access in robots.txt. A perfect score on every AI readiness check I could think of. And Perplexity had never heard of me. ChatGPT returned nothing. Google AI Overviews did not include a single one of my pages.

The infrastructure was a roof with no walls and no foundation underneath it.

## The Measurement Problem

After I accepted that my AEO infrastructure was useless without SEO foundations, I started looking at how the industry measures AI visibility. What I found was not reassuring.

I tested five AEO tools. Every one had a proprietary "AI Score" or "AEO Index." I asked each of them the same question: what ground truth did you validate this score against? One gave me a vague answer about "correlation with visibility signals." The rest did not respond.

I ran two of the tools on the same site, same day. One scored it 72/100. The other scored it 41/100. Neither could explain the discrepancy. Neither could tell me what a 72 meant in concrete terms. Would I get cited by ChatGPT? How often? For which queries? Nobody could say.

Here is the reality of AEO measurement in 2026:

**What is objectively measurable:**
- Google Search Console data (impressions, clicks, position). Free API. Reproducible.
- Core Web Vitals (LCP, CLS, INP). Lighthouse CLI. Same result every time.
- Schema markup validity. Parseable, testable, binary pass/fail.
- AI crawler access (robots.txt). You either allow GPTBot or you do not.
- llms.txt presence. It exists or it does not.

**What is not measurable at scale:**
- "AI citation rate." No AI platform exposes citation data via API. You can test manually, query by query, but results vary by session and location.
- "AEO Score." Every vendor invents their own. No standard exists. No ground truth.
- "AI ranking." AI platforms do not have rankings the way Google does. There is no position 1.
- "AI authority." This metric does not exist in any standardized form.

The gap between these two lists is where the AEO industry makes its money. They sell dashboards that visualize metrics from the second list, presented with the confidence of the first list.

## What I Built Instead

I needed an audit framework I could trust. One that would tell me what was real and what was speculation. So I built one with a simple rule: label everything.

The AI Visibility Readiness (AVR) framework splits every check into two tiers:

**[VERIFIABLE]:** Objective, reproducible, backed by a free API or CLI tool. Anyone can run this check and get the same result.

**[BEST-EFFORT]:** Measurable in a point-in-time sample, but not reproducible at scale. Results vary by session. We label confidence explicitly: HIGH, MODERATE, or LOW.

We do not combine these tiers into a single score. A composite number would mix facts with estimates, creating false precision. Instead, the framework produces three independent verdicts.

### Section 1: SEO Foundation (6 checks, all VERIFIABLE)

Core Web Vitals. Technical crawlability. Schema markup validation. Mobile friendliness. Page speed. Content indexability.

Every check has a data source (Lighthouse, GSC, HTTP requests), exact commands to run, and binary pass/fail criteria. No interpretation required. No vendor dependency.

If this section fails, stop. Do not invest in AI optimization. Fix your search foundation first.

### Section 2: AI Infrastructure Readiness (6 checks, all VERIFIABLE)

llms.txt presence and validity. AI crawler access directives. Structured data depth across your sitemap. Content structure quality (heading hierarchy, passage-level answers). Machine-readable content ratio. Semantic HTML usage.

These checks measure whether you have removed the barriers to AI citation. They do not predict whether AI systems will cite you. That distinction matters.

A site with PASS on all 12 checks in Sections 1 and 2 is AI-READY. It means: "We have done everything within our control. The rest depends on content quality, domain authority, and time."

### Section 3: Citation Monitoring (3 checks, all BEST-EFFORT)

Query-based citation testing across ChatGPT, Perplexity, and Google AI Overviews. Brand mention detection. Retrieval quality assessment.

Every result in this section is labeled with confidence: LOW for a single test round (20 queries), MODERATE for three rounds, HIGH for ten or more. We compute Wilson score confidence intervals so you know the margin of error.

This section tells you what IS happening with AI citations. Not what SHOULD happen. Not what a vendor predicts WILL happen. What is happening right now, with explicit uncertainty bounds.

## The Overall Verdict

The framework does not produce a number. It produces a status:

- **AI-READY:** SEO passes, AI infrastructure passes. You have done your part.
- **FOUNDATION-READY:** SEO passes, AI infrastructure needs work. Add llms.txt, fix robots.txt.
- **INFRASTRUCTURE-READY:** AI infrastructure passes, but SEO is broken. Fix the foundation.
- **NOT-READY:** SEO foundation fails. Everything else is premature.

Notice what is missing: there is no "78/100" score. No "your AI visibility improved 23% this month." Those numbers require ground truth that does not exist in 2026. Anyone selling them is selling confidence they do not have.

## I Ran It on Three Sites. Here Is What Happened.

I tested the AVR framework on three sites: my own blog (chudi.dev), CSS-Tricks (one of the most established frontend blogs on the web), and a small developer portfolio site.

My site scored FOUNDATION-READY. SEO foundation passed. AI infrastructure was partial, dragged down by a low content-to-HTML ratio (4.3%, typical for JavaScript-heavy SvelteKit apps). Everything else was green: llms.txt, schema markup on 100% of pages, nine schema types, clean heading hierarchy, all AI crawlers allowed.

CSS-Tricks scored NOT-READY. This surprised me. A DA 90 site with millions of readers, and the automated checks flagged issues with content indexability and AI infrastructure. The framework does not care about reputation. It measures what it measures.

The small portfolio site scored NOT-READY across the board. No schema markup. No llms.txt. No sitemap. The basics were missing.

Three sites, three different statuses, and every check was reproducible. No vendor dependency. No proprietary algorithm. Just HTTP requests, HTML parsing, and binary pass/fail criteria.

## Run It Yourself

The framework is open. The scripts are Python, the data sources are free, and the methodology is documented. Every check lists the exact command, the pass/fail threshold, and why it matters.

If you are evaluating AEO tools, ask them three questions:
1. Which of your metrics are verifiable vs. estimated?
2. What ground truth did you validate your AI scores against?
3. Can I reproduce your results independently?

If they cannot answer all three, you are paying for a dashboard, not a measurement.

## The Standard Does Not Exist Yet

AEO in 2026 is where SEO was in 2000. Everyone has a framework. None are standardized. The game is still being defined.

Google Search Console did not launch until 2006. Moz's Domain Authority took years to become an industry benchmark. Core Web Vitals were not standardized until 2020, two decades after the first SEO tools appeared.

AI visibility measurement will follow the same path. Somebody will define the standard. Somebody will build the ground truth. Until then, the honest approach is to measure what you can, label what you cannot, and refuse to combine them into a number that implies more certainty than exists.

## What I Would Tell Past Me

Do not build the AI visibility layer until the search foundation exists. Do not trust any metric without understanding its evidence tier. Do not combine verifiable data with best-effort estimates into a single score.

The 106 hours I spent on AEO infrastructure were not wasted. They taught me what is real and what is marketing in a field that is still being defined. The framework that came out of that failure is more valuable than any "AEO Score" I could buy.

The standard does not exist yet. Someone has to define it with transparency. This is my attempt.

---

*Chudi Nnorukam builds AI-augmented development tools and writes about what works (and what does not) at chudi.dev.*
