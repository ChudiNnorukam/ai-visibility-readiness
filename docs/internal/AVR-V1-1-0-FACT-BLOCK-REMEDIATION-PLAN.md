# AVR v1.1.0 Fact-Block Density Remediation Plan — chudi.dev

**Authored:** 2026-05-23
**Baseline source:** `sample-audits/audit_chudi.dev_20260523_070001_factblock.json` (root); `sample-audits/audit_chudi.dev_20260523_071102_factblock.json` (/framework)
**Goal:** Lift chudi.dev root + top pages from current scores into the **EXTRACTABLE band (≥75/100, ≥4/5 checks passing)** within the next content-editing arc.

## Current state (baseline)

| Page | Score | Verdict | Pass count |
|---|---|---|---|
| chudi.dev/ (root) | 40/100 | NOT-EXTRACTABLE | 2/5 |
| chudi.dev/framework | 51/100 | PARTIALLY-EXTRACTABLE | 2/5 |

Both pages pass the same two checks (**F1: first-sentence-of-H2 standalone-answer** at 100%, **F2: first-200-tokens direct-answer**) and fail the same three (**F3: 40-60 word direct-answer band**, **F4: H2/H3 question-format rate**, **F5: FAQ section present**). The remediation is therefore the same three fixes on both pages.

## The three failing checks, in priority order

### F3 — 40-60 word direct-answer band (weight 20, currently 0%)

**What the audit measures:** the first paragraph under every `<h2>` should land in the 40-60 word band. Under 40 reads thin to AI extractors; over 60 risks chunk-truncation in the retrieval window.

**What the audit found on chudi.dev/framework:**
- 12 H2 sections audited
- 0 of 12 first paragraphs land in the 40-60 word band
- Most sections currently use either ultra-short one-sentence answers OR multi-paragraph expositions

**Remediation pattern (per H2):**
1. Identify the first paragraph after the H2 heading.
2. Count words. If <40, expand by adding supporting context, primary-source citation, or a follow-up sentence — without crossing 60.
3. If >60, condense by moving the second half to paragraph 2 (supporting evidence per Patel's inverted-pyramid rule). The 40-60 word paragraph becomes the lead, the longer context becomes the supporting block.

**Example rewrite (framework page §1 "SEO Foundation"):**

**Before** (current; ~18 words): "The baseline AI search systems depend on. If organic search cannot find you, AI search never sees you."

**After** (~52 words, in band): "Section 1 of the AVR v1.1.0 audit measures whether traditional search engines can find your site at all. Six checks run against Core Web Vitals, technical crawlability, schema markup, E-E-A-T signals, content depth, and the internal link graph. If organic search cannot find you, AI search never sees you."

### F4 — H2/H3 question-format rate (weight 20, currently 8.3% on /framework)

**What the audit measures:** AI engines extract sections most reliably when headings are phrased as questions a user would actually type. The first-200-tokens of a page get the most weight; question-shaped H2s downstream get the next-most weight.

**What the audit found:**
- chudi.dev/framework: 11 of 12 H2/H3 headings are statements, 1 is a question (8.3%)
- chudi.dev root: similar pattern

**Remediation pattern:**

| Statement heading | Question heading |
|---|---|
| "SEO Foundation" | "What does the SEO foundation audit check?" |
| "AI Infrastructure" | "What AI infrastructure files does my site need?" |
| "Citation Monitoring" | "How does AVR test whether AI engines cite my site?" |
| "AI Visibility" | "Does AI know my site exists?" |
| "Verdict tiers" | "What does each verdict tier mean?" |

The conversion is mechanical: every section name becomes a "What/How/Why/Does" question. Target ≥40% question-rate to PASS F4.

### F5 — FAQ section present (weight 10, currently FAIL on both pages)

**What the audit measures:** a heading matching `/^(faq|frequently asked|q\s*&\s*a|questions and answers)/i` near the article tail (last 30% of sections).

**Remediation:** add an FAQ section near the bottom of each remediation-target page. 3-5 Q/A pairs is sufficient. Each Q matches the user-typed-question pattern (helps F4 too).

## Top 5 chudi.dev pages to remediate first

Priority ordering: traffic potential × Fact-Block lift × content-quality match.

| # | Page | Why first | Estimated lift |
|---|---|---|---|
| 1 | `/framework` | Canonical AVR methodology page. Currently 51/100; getting it to EXTRACTABLE 75+ matters most for the case-study hypothesis ("chudi.dev DEMONSTRATES AVR"). | 51 → 75+ |
| 2 | `/` (root/home) | First impression. 40/100. Currently has no FAQ section + uses statement headings. | 40 → 75+ |
| 3 | `/blog` (index) | Blog hub; not yet audited. Likely has same 3 failures. Run `python3 scripts/run_audit.py chudi.dev/blog --skip-lighthouse --full-v11` to confirm. | unknown → 75+ |
| 4 | `/work` (index) | Project ledger; not yet audited. Run audit first. | unknown → 75+ |
| 5 | `/about` | Author entity page; ties into §2.6 Entity Authority Tier. Likely Q/A friendly. | unknown → 75+ |

The 5 pages above are the publish-velocity layer. After they remediate, audit the top 10 blog posts and apply the same three rules.

## Per-page remediation budget

Each H2 rewrite is 5-15 minutes:
- F3 paragraph rewrite: 5 min × N H2s
- F4 heading rewrite: 2 min × N H2s
- F5 FAQ addition: 15-30 min per page (3-5 Q/A pairs)

For chudi.dev/framework (12 H2s) the budget is ~80-150 minutes. For the root page (~6 H2s) ~30-60 minutes.

## Verification

After remediation, re-run:

```bash
cd ~/Projects/business/ai-visibility-readiness
python3 scripts/run_audit.py chudi.dev --skip-lighthouse --full-v11 \
  -o sample-audits
python3 scripts/run_audit.py chudi.dev/framework --skip-lighthouse --full-v11 \
  -o sample-audits
```

The expected post-remediation report:
- Score ≥75/100
- F3 in-band-rate ≥50%
- F4 question-rate ≥40%
- F5 PASS
- Verdict: EXTRACTABLE

Diff the new audit JSON against the 2026-05-23 baseline to surface the deltas per check.

## Why this is the highest-leverage AVR work

Per the v1.1.0 case-study hypothesis, chudi.dev DEMONSTRATES AVR. The §2.7 Agent Readiness audit already passes 3/3 because the manifests + API routes shipped. The §7 Fact-Block Density audit failing at 40/100 is the load-bearing claim against the hypothesis — the case-study site fails its own content-extractability metric.

Three rules, two pages, ~3 hours of editing. The remediation cost is small. The hypothesis lift is large.

## Ledger trail

- `dc-20260522T220657-ratify-0c8df9` — §7 Fact-Block Density node ratified via empirical contact (2026-05-22)
- `dc-20260523T070000-*` — full 8-section audit produced 2026-05-23 07:00 UTC
- `dc-20260523T071100-*` — /framework-specific audit produced 2026-05-23 07:11 UTC (this baseline)
- `dc-20260523T071058-avr11-publication-arc` — this remediation plan authored

## FAQ implementation gotchas (empirical lessons 2026-05-23)

Two failure modes the audit caught during the 5-page remediation arc. Both cost a follow-up commit each, both are now documented so future authors skip the detour.

### Gotcha #1: Use `<h3>` for Q/A pairs, not `<dt>/<dd>`

**What the audit does:** `section_fact_block_density.py`'s `extract_sections` walks `h1`/`h2`/`h3` tags only. The F4 question-format-rate check counts question-shaped `h2`+`h3` headings as a fraction of all `h2`+`h3` headings. The F5 FAQ check looks for an `h1`/`h2`/`h3` heading whose text matches `^(faq|frequently asked|q\s*&\s*a|questions and answers)` near the tail of the page.

**The trap:** `<dt>` (description-term) is semantically a Q/A label, and `<dd>` (description-detail) is its answer. They render beautifully in a description list. But the audit doesn't see them as headings, so:
- 5 dt-shaped Q/A pairs contribute ZERO question signals to F4
- F5 cannot detect a "Frequently asked" pattern hiding inside a `<dt>`

**The fix:** use `<h3>` for the Q and `<p>` for the A. If the design system wants a description-list visual, recreate it with CSS on `h3` + `p` siblings (e.g., flex column, border-left).

**Empirical contact:** chudi.dev root v1 used `<dt>/<dd>` (commit d3228420). Audit returned F4 16% + F5 FAIL. v2 (commit 1765f0c8) swapped to `<h3>/<p>` — F4 jumped to 26.7% + F5 PASS in the same audit run. The two-commit detour took ~30 minutes and one Vercel cache-bust commit to resolve.

### Gotcha #2: Icons go AFTER the heading text, with `aria-hidden="true"`

**What the audit does:** BeautifulSoup's `get_text(strip=True)` extracts heading content in **document order**, concatenating child element text with whitespace stripping. The F5 regex `^(faq|frequently asked|...)` requires the FIRST word of the extracted text to be one of those terms.

**The trap:** Material Symbols / Material Icons / FontAwesome / similar icon libraries are commonly placed BEFORE the heading text:
```html
<h2>
  <span class="material-symbols-outlined">quiz</span>
  Frequently asked questions
</h2>
```
This renders perfectly visually. But BeautifulSoup extracts: `"quiz Frequently asked questions"`. The F5 regex sees "quiz" as the first word and returns no match. F5 FAILS.

**The fix:** put the icon AFTER the heading text, mark `aria-hidden="true"` so screen readers don't double-read it:
```html
<h2>
  Frequently asked questions
  <span aria-hidden="true" class="material-symbols-outlined">quiz</span>
</h2>
```
Now BeautifulSoup extracts `"Frequently asked questions quiz"` — first word "Frequently" matches. F5 PASSES.

**Empirical contact:** chudi.dev/about v1 of the FAQ section put the `<span>quiz</span>` BEFORE "Frequently asked questions" (commit d378074f). Audit returned 78/100 + F5 FAIL despite F1-F4 looking good. The icon-after-text fix (commit d4dfbba8) lifted /about to 88/100 EXTRACTABLE in one line change.

### Bonus: the broader principle

The audit reads HTML the way an AI extractor would. Anything that visually decorates a heading but doesn't carry semantic answer content (icons, badges, kicker labels) should be marked `aria-hidden="true"` AND placed after the canonical heading text, OR moved outside the heading element entirely. The visual design stays identical; the extraction surface stays clean.

This generalizes beyond FAQ sections: any time the F5 check or the F4 question-format check fails on what looks like a well-shaped heading, suspect a child-element ordering issue first.
