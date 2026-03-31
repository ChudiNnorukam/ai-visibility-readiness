# AI Visibility Readiness (AVR) Framework v1.0

A transparent, tiered audit methodology for measuring website readiness for both traditional search engines and AI-powered search systems.

**Author:** Chudi Nnorukam (chudi.dev)
**Version:** 1.0.0
**Last Updated:** 2026-03-31

## Philosophy

Every check in this framework is labeled with its evidence tier:

- **[VERIFIABLE]**: Objective, reproducible, backed by a free API or CLI tool. Anyone can run this check and get the same result.
- **[BEST-EFFORT]**: Measurable in a point-in-time sample, but not reproducible at scale. Results vary by session, query phrasing, and platform state. We label confidence explicitly.

We do not invent scores for things we cannot measure. If a metric has no ground truth, we say so.

---

## Section 1: SEO Foundation

These checks measure the baseline that AI search systems depend on. AI search engines use web search results as their retrieval source. If traditional search cannot find you, AI search never sees you.

### Check 1.1: Core Web Vitals [VERIFIABLE]

**What it measures:** Real-user loading experience: Largest Contentful Paint (LCP), Cumulative Layout Shift (CLS), and Interaction to Next Paint (INP).

**Data source:** Lighthouse CLI (lab data) or Chrome UX Report API (field data).

**How to run:**
```bash
lighthouse <URL> --output json --only-categories=performance --chrome-flags="--headless"
```

**Pass/fail criteria:**
| Metric | Good | Needs Improvement | Poor |
|--------|------|-------------------|------|
| LCP | <= 2.5s | <= 4.0s | > 4.0s |
| CLS | <= 0.1 | <= 0.25 | > 0.25 |
| INP | <= 200ms | <= 500ms | > 500ms |

**Verdict:** PASS if all three metrics are "Good." PARTIAL if any metric is "Needs Improvement." FAIL if any metric is "Poor."

**Why it matters for AI visibility:** AI search systems preferentially retrieve from fast, stable pages. Google AI Overviews inherits ranking signals from organic search, where Core Web Vitals are a confirmed ranking factor. Slow pages get crawled less frequently by all bots, including AI crawlers.

---

### Check 1.2: Technical Crawlability [VERIFIABLE]

**What it measures:** Whether search engine and AI crawlers can discover and access your pages.

**Data source:** Direct HTTP requests to robots.txt, sitemap.xml, and page URLs.

**How to run:**
```bash
# Check robots.txt
curl -sI <URL>/robots.txt | head -5

# Check sitemap
curl -sI <URL>/sitemap.xml | head -5

# Check HTTPS redirect
curl -sI http://<domain> | grep -i location
```

**Pass/fail criteria:**
| Check | Pass | Fail |
|-------|------|------|
| robots.txt exists and returns 200 | Yes | 404 or blocks all crawlers |
| sitemap.xml exists and returns 200 | Yes | 404 or empty |
| HTTPS enforced (HTTP redirects to HTTPS) | Yes | No redirect or mixed content |
| No critical pages blocked by robots.txt | Yes | Important paths disallowed |

**Verdict:** PASS if all four checks pass. FAIL if HTTPS is not enforced or robots.txt blocks crawlers. PARTIAL otherwise.

**Why it matters for AI visibility:** AI crawlers (GPTBot, ClaudeBot, PerplexityBot) respect robots.txt. If your robots.txt blocks them or does not exist, these systems cannot index your content. A missing sitemap means crawlers must discover pages through links alone, which is slower and less complete.

---

### Check 1.3: Schema Markup Validation [VERIFIABLE]

**What it measures:** Whether structured data (JSON-LD, Microdata, RDFa) is present, valid, and covers key content types.

**Data source:** HTML parsing of page source for JSON-LD blocks + schema.org validation.

**How to run:**
```bash
# Extract JSON-LD from page
curl -s <URL> | python3 -c "
import sys, json, re
html = sys.stdin.read()
blocks = re.findall(r'<script type=\"application/ld\+json\">(.*?)</script>', html, re.DOTALL)
for b in blocks:
    try:
        print(json.dumps(json.loads(b), indent=2))
    except json.JSONDecodeError:
        print(f'INVALID JSON: {b[:100]}...')
"
```

**Pass/fail criteria:**
| Check | Pass | Fail |
|-------|------|------|
| At least one JSON-LD block present | Yes | No structured data |
| All JSON-LD blocks parse as valid JSON | Yes | Syntax errors |
| @type matches page content (Article, Product, FAQ, etc.) | Yes | Missing or wrong type |
| Required properties present for the @type | Yes | Missing name, description, etc. |

**Verdict:** PASS if valid schema exists with correct type and required properties. PARTIAL if schema exists but has missing properties. FAIL if no structured data or invalid JSON.

**Why it matters for AI visibility:** Structured data is the machine-readable layer that AI systems parse directly. Google AI Overviews, Perplexity, and ChatGPT web search all consume structured data to understand page content. A page with valid Article schema and FAQ schema is more likely to be cited because the AI can extract structured answers without parsing free text.

---

### Check 1.4: Mobile Friendliness [VERIFIABLE]

**What it measures:** Whether the page renders correctly on mobile viewports and is touch-friendly.

**Data source:** Lighthouse CLI mobile audit.

**How to run:**
```bash
lighthouse <URL> --output json --form-factor mobile --only-categories=accessibility,best-practices
```

**Pass/fail criteria:**
| Check | Pass | Fail |
|-------|------|------|
| Viewport meta tag present | Yes | Missing |
| Text readable without zoom (font >= 12px) | Yes | Too small |
| Tap targets adequately sized (>= 48x48px) | Yes | Too small or overlapping |
| No horizontal scroll on 360px viewport | Yes | Content overflows |

**Verdict:** PASS if all checks pass. FAIL if viewport meta is missing. PARTIAL otherwise.

**Why it matters for AI visibility:** Google's index is mobile-first. AI Overviews pulls from the mobile index. If your page breaks on mobile, it ranks lower in the index that AI systems retrieve from.

---

### Check 1.5: Page Speed and Resource Efficiency [VERIFIABLE]

**What it measures:** Total page weight, number of requests, and time to interactive.

**Data source:** Lighthouse performance audit.

**How to run:**
```bash
lighthouse <URL> --output json --only-categories=performance --chrome-flags="--headless"
```

**Pass/fail criteria:**
| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| Performance Score | >= 90 | >= 50 | < 50 |
| Total Page Weight | < 1MB | < 3MB | > 3MB |
| Time to Interactive | < 3.8s | < 7.3s | > 7.3s |
| Total Requests | < 50 | < 100 | > 100 |

**Verdict:** PASS if Performance Score >= 90. PARTIAL if >= 50. FAIL if < 50.

**Why it matters for AI visibility:** AI crawlers have timeout budgets. A page that takes 10 seconds to render may be abandoned before the crawler extracts content. Lighter pages get crawled more completely and more frequently.

---

### Check 1.6: Content Indexability [VERIFIABLE]

**What it measures:** Whether the primary content is in the HTML source (not hidden behind JavaScript rendering) and is indexable.

**Data source:** HTTP response + HTML parsing.

**How to run:**
```bash
# Check if content is in raw HTML (not JS-rendered only)
curl -s <URL> | wc -c  # Should have substantial content
curl -s <URL> | grep -c '<p>'  # Paragraph count in source

# Check meta robots
curl -s <URL> | grep -i 'meta.*robots'

# Check canonical
curl -s <URL> | grep -i 'rel="canonical"'
```

**Pass/fail criteria:**
| Check | Pass | Fail |
|-------|------|------|
| HTML source contains > 500 characters of visible text | Yes | JS-rendered only |
| No noindex in meta robots | Yes | noindex present |
| Canonical tag present and self-referencing | Yes | Missing or pointing elsewhere |
| No duplicate content signals | Yes | Multiple pages with same content |

**Verdict:** PASS if content is in HTML, indexable, and canonical. FAIL if noindex or JS-only rendering. PARTIAL if canonical issues.

**Why it matters for AI visibility:** Most AI crawlers do NOT execute JavaScript. If your content is rendered client-side only (React SPA without SSR), AI crawlers see an empty page. Server-side rendering or static generation is required for AI visibility.

---

## Section 2: AI Infrastructure Readiness

These checks measure whether your site has the specific signals and configurations that AI systems look for, beyond traditional SEO.

### Check 2.1: llms.txt Presence and Validity [VERIFIABLE]

**What it measures:** Whether a llms.txt file exists at the site root and conforms to the emerging specification.

**Data source:** Direct HTTP request + content parsing.

**How to run:**
```bash
curl -sI <URL>/llms.txt | head -5
curl -s <URL>/llms.txt | head -50
```

**Pass/fail criteria:**
| Check | Pass | Fail |
|-------|------|------|
| /llms.txt returns HTTP 200 | Yes | 404 or other error |
| Content-Type is text/plain or text/markdown | Yes | Wrong content type |
| Contains site description / purpose | Yes | Empty or placeholder |
| Lists key pages or content areas | Yes | No navigation structure |
| Updated within last 90 days (if datestamp present) | Yes | Stale content |

**Verdict:** PASS if file exists, parses correctly, and has substantive content. PARTIAL if exists but minimal. FAIL if missing.

**Why it matters for AI visibility:** llms.txt is an emerging standard for telling AI systems what your site is about and where to find key content. It is the AI equivalent of sitemap.xml. Adoption is early but growing. Having one signals to AI crawlers that you've considered their needs.

---

### Check 2.2: AI Crawler Access Directives [VERIFIABLE]

**What it measures:** Whether robots.txt explicitly addresses AI-specific crawlers.

**Data source:** robots.txt parsing.

**How to run:**
```bash
curl -s <URL>/robots.txt | grep -iE 'GPTBot|ClaudeBot|PerplexityBot|ChatGPT-User|anthropic|Google-Extended|CCBot'
```

**AI crawlers to check:**
| Crawler | Operator | Purpose |
|---------|----------|---------|
| GPTBot | OpenAI | ChatGPT web browsing + training |
| ChatGPT-User | OpenAI | ChatGPT real-time browsing |
| ClaudeBot | Anthropic | Claude web search |
| PerplexityBot | Perplexity | Perplexity search index |
| Google-Extended | Google | Gemini/AI Overviews training |
| CCBot | Common Crawl | Open dataset used by many AI systems |

**Pass/fail criteria:**
| Check | Pass | Fail |
|-------|------|------|
| robots.txt does NOT block GPTBot | Allowed or not mentioned | Explicitly disallowed |
| robots.txt does NOT block ClaudeBot | Allowed or not mentioned | Explicitly disallowed |
| robots.txt does NOT block PerplexityBot | Allowed or not mentioned | Explicitly disallowed |
| At least 3 of 6 AI crawlers allowed | Yes | Majority blocked |

**Verdict:** PASS if all major AI crawlers are allowed. PARTIAL if some are blocked. FAIL if majority are blocked.

**Why it matters for AI visibility:** If you block GPTBot, ChatGPT will never cite you. If you block PerplexityBot, Perplexity cannot index your pages. Each blocked crawler is a closed door to that AI platform's users. Many sites block AI crawlers by default (copying "block all AI" robots.txt templates) without realizing they're opting out of AI search entirely.

---

### Check 2.3: Structured Data Depth [VERIFIABLE]

**What it measures:** How many schema.org types are implemented and what percentage of pages have structured data.

**Data source:** Sitemap crawl + HTML parsing of each page.

**How to run:**
```bash
# Get all pages from sitemap
curl -s <URL>/sitemap.xml | grep -oP '<loc>\K[^<]+' | head -50 > /tmp/pages.txt

# Check each for JSON-LD
while read page; do
  types=$(curl -s "$page" | grep -oP '"@type"\s*:\s*"\K[^"]+' | sort -u | tr '\n' ',')
  echo "$page: $types"
done < /tmp/pages.txt
```

**Pass/fail criteria:**
| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| Pages with any schema | > 80% | > 50% | < 50% |
| Unique schema types | >= 3 | >= 1 | 0 |
| Rich result eligible types (FAQ, HowTo, Article) | >= 1 | 0 | 0 |

**Verdict:** PASS if >80% of pages have schema and >=3 types. PARTIAL if >50%. FAIL if <50% or 0 types.

**Why it matters for AI visibility:** Structured data density signals to AI systems that your site is machine-readable by design, not by accident. Sites with diverse schema types (Article + Person + FAQ + HowTo) provide richer context for AI citation selection. A single Article schema on every page is better than nothing, but FAQ and HowTo schemas make content directly extractable as answers.

---

### Check 2.4: Content Structure Quality [VERIFIABLE]

**What it measures:** Whether page content follows a clear heading hierarchy with extractable answer passages.

**Data source:** HTML parsing of page source.

**How to run:**
```bash
curl -s <URL> | python3 -c "
import sys, re
html = sys.stdin.read()
headings = re.findall(r'<(h[1-6])[^>]*>(.*?)</\1>', html, re.DOTALL | re.IGNORECASE)
for tag, text in headings:
    clean = re.sub(r'<[^>]+>', '', text).strip()
    print(f'{tag.upper()}: {clean}')
"
```

**Pass/fail criteria:**
| Check | Pass | Fail |
|-------|------|------|
| Single H1 tag per page | Yes | Multiple or missing |
| H2-H6 follow hierarchy (no skipping levels) | Yes | H1 -> H3 (skipped H2) |
| At least 3 heading-delineated sections | Yes | Wall of text |
| Paragraphs average < 150 words | Yes | Dense blocks > 300 words |
| FAQ-style Q&A patterns present | Bonus | Not required |

**Verdict:** PASS if heading hierarchy is clean and content is well-sectioned. PARTIAL if hierarchy issues but content is sectioned. FAIL if no heading structure or wall-of-text.

**Why it matters for AI visibility:** AI systems extract answers at the passage level. A question in an H2 followed by a concise 2-3 sentence answer is the ideal citation unit. Wall-of-text pages force the AI to do more work to extract a quotable passage, making citation less likely. Clean heading hierarchy also helps AI systems understand the topic structure of your page.

---

### Check 2.5: Machine-Readable Content Ratio [VERIFIABLE]

**What it measures:** The ratio of meaningful text content to HTML/CSS/JS boilerplate.

**Data source:** HTML parsing.

**How to run:**
```bash
curl -s <URL> | python3 -c "
import sys, re
html = sys.stdin.read()
total = len(html)
# Remove scripts, styles, tags
text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
text = re.sub(r'<[^>]+>', '', text)
text = re.sub(r'\s+', ' ', text).strip()
content_len = len(text)
ratio = content_len / total if total > 0 else 0
print(f'Total HTML: {total} bytes')
print(f'Text content: {content_len} bytes')
print(f'Content ratio: {ratio:.1%}')
"
```

**Pass/fail criteria:**
| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| Content ratio | > 25% | > 10% | < 10% |
| Visible text length | > 1,000 chars | > 500 chars | < 500 chars |

**Verdict:** PASS if ratio > 25% and text > 1,000 chars. PARTIAL if ratio > 10%. FAIL if ratio < 10% or text < 500 chars.

**Why it matters for AI visibility:** AI crawlers extract text from HTML. A page that is 95% navigation, ads, and JavaScript with 5% actual content gives the AI almost nothing to cite. Higher content ratios mean more material for AI systems to index and reference.

---

### Check 2.6: Semantic HTML and Accessibility [VERIFIABLE]

**What it measures:** Whether the page uses semantic HTML elements that help machines understand content structure.

**Data source:** HTML parsing.

**How to run:**
```bash
curl -s <URL> | python3 -c "
import sys, re
html = sys.stdin.read()
elements = {
    'article': len(re.findall(r'<article', html, re.I)),
    'main': len(re.findall(r'<main', html, re.I)),
    'nav': len(re.findall(r'<nav', html, re.I)),
    'section': len(re.findall(r'<section', html, re.I)),
    'aside': len(re.findall(r'<aside', html, re.I)),
    'figure': len(re.findall(r'<figure', html, re.I)),
    'time': len(re.findall(r'<time', html, re.I)),
    'img_with_alt': len(re.findall(r'<img[^>]+alt=\"[^\"]+\"', html, re.I)),
    'img_total': len(re.findall(r'<img', html, re.I)),
}
for el, count in elements.items():
    print(f'{el}: {count}')
"
```

**Pass/fail criteria:**
| Check | Pass | Fail |
|-------|------|------|
| Uses `<article>` or `<main>` for primary content | Yes | All `<div>` |
| Uses `<nav>` for navigation | Yes | Navigation in generic divs |
| Images have alt text (>80% coverage) | Yes | < 50% coverage |
| `<time>` elements for dates | Bonus | Not required for pass |

**Verdict:** PASS if semantic elements are used for content and navigation. PARTIAL if some semantic elements present. FAIL if all generic divs.

**Why it matters for AI visibility:** Semantic HTML tells AI systems "this is the article" vs "this is the navigation" vs "this is a sidebar." Without semantic elements, AI crawlers must guess which part of the page is the main content. `<article>` wrapping your content is a direct signal that says "extract from here."

---

## Section 3: Citation Monitoring

These checks measure whether AI search systems are actually citing your content. Unlike Sections 1 and 2, these are point-in-time observations with inherent variability. We label confidence explicitly.

### Check 3.1: Query-Based Citation Test [BEST-EFFORT]

**What it measures:** Whether your site appears in AI-generated responses for queries relevant to your content.

**Methodology:**

1. **Select 20 representative queries.**
   - 5 brand queries ("chudi.dev", "chudi nnorukam", "[your product name]")
   - 5 topic authority queries ("how to [thing you've written about]")
   - 5 long-tail queries (specific questions your content answers)
   - 5 competitor-adjacent queries (topics where you and competitors both have content)

2. **Test across 3 platforms:**
   - ChatGPT (web browsing enabled)
   - Perplexity (default search mode)
   - Google (check for AI Overview panel)

3. **Record results in structured format:**
```
| Query | ChatGPT | Perplexity | Google AIO | Notes |
|-------|---------|------------|------------|-------|
| "how to build AI code guardrails" | NOT_CITED | CITED (link) | NO_AIO | First result was competitor |
```

4. **Compute citation rate:**
   - Total possible citations: 20 queries x 3 platforms = 60
   - Actual citations: count of CITED results
   - Citation rate: actual / total

**Confidence labeling:**
| Sample | Label | Interpretation |
|--------|-------|---------------|
| 60 query-platform pairs | LOW | Directional signal only |
| 180 query-platform pairs (3 rounds) | MODERATE | Trends visible |
| 600+ query-platform pairs (10+ rounds) | HIGH | Statistically meaningful |

**Verdict:**
- Citation rate > 15%: CITED (your content is being picked up)
- Citation rate 1-15%: PARTIALLY_CITED (some visibility, room to grow)
- Citation rate 0%: NOT_CITED (AI systems are not using your content)

**Why confidence matters:** AI responses vary by session, user location, and time. A query that cites you today may not cite you tomorrow. A single round of 20 queries gives you a LOW confidence signal, not a definitive answer. This is a monitoring check, not a measurement.

---

### Check 3.2: Brand Mention Detection [BEST-EFFORT]

**What it measures:** Whether AI systems mention your brand, product, or domain when asked directly.

**Methodology:**

1. **Ask 5 direct questions across 3 platforms:**
   - "What is [brand/product]?"
   - "Who is [your name]?"
   - "Tell me about [your domain]"
   - "What does [brand] do?"
   - "Is [product] any good?"

2. **Record responses:**
   - KNOWN: AI provides accurate information about you
   - PARTIAL: AI mentions you but with inaccurate details
   - UNKNOWN: AI does not know who you are
   - HALLUCINATED: AI invents information about you

**Confidence:** Always LOW for new/small sites. Brand recognition in AI systems requires significant web presence (many backlinks, citations, Wikipedia mention, etc.).

**Verdict:**
- KNOWN on 2+ platforms: Brand is in AI training data
- PARTIAL or UNKNOWN: Brand not yet established in AI knowledge
- HALLUCINATED: Potential reputation risk, needs monitoring

---

### Check 3.3: Retrieval Quality Assessment [BEST-EFFORT]

**What it measures:** When your content IS cited, how accurately is it represented?

**Methodology:** For each citation found in Check 3.1:

1. Read the AI's response containing your citation
2. Compare the cited claim to your actual content
3. Score accuracy:
   - ACCURATE: AI correctly represents your content
   - DISTORTED: AI cites you but misrepresents the content
   - OUTDATED: AI cites old content, not current version

**This check only applies if Check 3.1 found any citations.** If citation rate is 0%, skip this check.

---

## Scoring and Verdicts

### Per-Section Verdicts

Each section receives an independent verdict:

| Section | Verdict | Meaning |
|---------|---------|---------|
| SEO Foundation | PASS / PARTIAL / FAIL | Baseline search infrastructure |
| AI Infrastructure | PASS / PARTIAL / FAIL | AI-specific readiness signals |
| Citation Monitoring | CITED / PARTIALLY_CITED / NOT_CITED | Actual AI search performance |

### Overall Readiness Assessment

We do NOT combine these into a single number. A composite score would mix verifiable metrics with best-effort observations, creating false precision.

Instead, the overall assessment is a status:

| Status | Criteria |
|--------|----------|
| **AI-READY** | SEO: PASS, AI Infra: PASS, Citations: any |
| **FOUNDATION-READY** | SEO: PASS, AI Infra: PARTIAL or FAIL |
| **INFRASTRUCTURE-READY** | SEO: PARTIAL, AI Infra: PASS |
| **NOT-READY** | SEO: FAIL (regardless of other sections) |

**Key insight:** You cannot be AI-READY without SEO PASS. AI visibility is downstream of traditional search visibility. If Section 1 fails, fix it before investing in Section 2 or 3.

### What We Explicitly Do NOT Score

- "AEO Score" or "AI Optimization Score" (no ground truth exists)
- "AI Authority" (no standardized metric)
- "AI Ranking" (AI platforms do not expose ranking data)
- Predicted citation probability (no model has been validated for this)

If a vendor sells you any of these numbers, ask them: "What is the ground truth you validated this against?" If they cannot answer, it is marketing, not measurement.

---

## Methodology Notes

### Reproducibility

Sections 1 and 2 produce identical results when run by different people on the same URL at the same time. Section 3 will produce different results due to AI response variability.

### Update Frequency

- Section 1: Re-run after any site change (deploy, redesign, new content)
- Section 2: Re-run monthly or after AI-specific changes
- Section 3: Re-run monthly to track trends. Single data points are meaningless.

### Limitations

1. This framework cannot predict whether AI systems WILL cite you. It can only measure whether you've removed the barriers to citation.
2. Section 3 is inherently imprecise. We are transparent about this. Anyone claiming precise AI citation measurement in 2026 is overstating their methodology.
3. Domain Authority (DA/DR) is deliberately excluded. These are proprietary estimates from Moz/Ahrefs with closed algorithms. They are predictive, not objective.
4. This framework does not measure content quality or topical authority. Those are subjective assessments that belong in editorial review, not automated auditing.

---

## Version History

- **v1.0.0** (2026-03-31): Initial release. 15 checks across 3 tiers.
