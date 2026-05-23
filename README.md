# avr-pipeline

The **AI Visibility Readiness (AVR) Framework** v1.1.0 — a transparent, tiered audit methodology for measuring whether a website is ready for traditional search AND for AI-powered search (Google AI Mode, AI Overviews, Perplexity, ChatGPT, Claude, Gemini, Microsoft Copilot).

Authored by [Chudi Nnorukam](https://chudi.dev). Implemented by [citability.dev](https://citability.dev). Demonstrated on [chudi.dev](https://chudi.dev) as the canonical case study.

## What AVR v1.1.0 measures

AVR runs **eight sections** of audit signals. Every check is labelled `[VERIFIABLE]` (a deterministic HTTP/HTML probe with primary-source evidence) or `[BEST-EFFORT]` (a polled AI engine response subject to sampling variance). The framework never fakes a composite "AI Visibility Score" by averaging signals that measure different things.

| § | Section | Cost | Label | Verdict bands |
|---|---|---|---|---|
| 1 | SEO Foundation | $0 | VERIFIABLE | PASS / PARTIAL / FAIL |
| 2 | AI Infrastructure | $0 | VERIFIABLE | PASS / PARTIAL / FAIL |
| 3 | Citation Monitoring (live) | ~$0.60 | BEST-EFFORT | CITED / PARTIALLY_CITED / NOT_CITED |
| 4 | AI Visibility (live) | ~$0.60 | BEST-EFFORT | HIGHLY / PARTIALLY / BARELY / INVISIBLE |
| 5 | Calibration Receipt | ~$0.10 | VERIFIABLE | PASS / FAIL |
| 6 | **Agent Readiness (§2.7, v1.1.0)** | $0 | VERIFIABLE | AGENT-READY / AGENT-PARTIAL / AGENT-NOT-READY |
| 7 | **Fact-Block Density (v1.1.0)** | $0 | VERIFIABLE | EXTRACTABLE / PARTIALLY-EXTRACTABLE / NOT-EXTRACTABLE |
| 8 | **Citation Decay Rate (v1.1.0, the moat metric)** | $0 | VERIFIABLE | GROWING / STABLE / DECLINING / DATA-INSUFFICIENT |

Sections 6, 7, and 8 are the v1.1.0 additions. No other AI visibility tool (Semrush, BrightEdge, Conductor, Otterly, Profound, Peec AI, LLMrefs, Knowatoa) tracks all three as of 2026-05-22.

## Why v1.1.0 exists

Five things changed in May 2026 that broke v1.0:

1. **Google I/O 2026** disclosed that **AI Mode has surpassed one billion monthly users** with **queries thrice as long as traditional ones and follow-up queries increasing 40% monthly in the U.S.** [Source: [SearchEngineJournal SEO Pulse, May 2026](https://www.searchenginejournal.com/seo-pulse-google-launches-core-update-amid-i-o-ai-search-overhaul/575676/)]
2. **Ahrefs measured a 58% CTR reduction** on queries with AI Overviews across 300,000 keywords (December 2025 data). Position-one CTR for AIO-triggering keywords fell from 0.073% to 0.016%. [Source: [Ahrefs blog](https://ahrefs.com/blog/ai-overviews-reduce-clicks-update/)]
3. **Over 16% of searches are multimodal** (voice, images, video input). [Source: [SearchEngineJournal](https://www.searchenginejournal.com/seo-pulse-google-launches-core-update-amid-i-o-ai-search-overhaul/575676/)]
4. **Google's AI guide reversed the llms.txt recommendation**: "Google's AI guide states llms.txt isn't needed for AI Search." John Mueller: "markdown pages are useful for documentation but not for most websites." Lighthouse 13.3 now flags `llms.txt` as an ERROR by default. [Source: [SearchEngineJournal](https://www.searchenginejournal.com/seo-pulse-google-launches-core-update-amid-i-o-ai-search-overhaul/575676/)]
5. **March 2026 Core Update** raised E-E-A-T cross-platform corroboration as the load-bearing trust signal: "the more places a person's name appears in connection with a subject area, the stronger the E-E-A-T signal for content they author on your domain." [Source: [Evertune, April 8 2026](https://www.evertune.ai/resources/insights-on-ai/googles-march-2026-core-update-a-content-best-practices-guide-for-seo-and-ai-search)]

AVR v1.0 treated Google AI surfaces as secondary, recommended `llms.txt` as a §2 requirement, and audited E-E-A-T at surface level. All three positions are now wrong. v1.1.0 fixes them.

## Quick start

```bash
git clone https://github.com/ChudiNnorukam/avr-pipeline.git
cd avr-pipeline
pip install -r scripts/requirements.txt

# Free 5-section audit (1+2+6+7+8). No API spend.
python3 scripts/run_audit.py YOUR_URL --skip-lighthouse --full-v11

# Full 8-section audit with live AI polling. ~$2 API spend.
python3 scripts/run_audit.py YOUR_URL --skip-lighthouse --live-test --full-v11 \
  --brand "Your Brand" \
  --owner "Owner Name" \
  --topics "topic1" "topic2" \
  --concepts "your unique concepts" \
  --products "your products"
```

Outputs land in `sample-audits/audit_<domain>_<timestamp>.md` plus per-section `.json` files.

## Section 6 — Agent Readiness (WebMCP + A2A AgentCard)

Checks three things:

1. **`/.well-known/webmcp` manifest** exists, validates as JSON, declares ≥1 tool with required fields (name, description). Spec: [WebMCP W3C draft](https://webmachinelearning.github.io/webmcp/), shipping in Chrome 146 Canary behind `chrome://flags` "WebMCP for testing".
2. **`/.well-known/agent.json` AgentCard** (A2A protocol) exists, validates, declares skills. Optional for non-agent sites; absence is not penalized.
3. **Wire-protocol probe** — each endpoint declared in the manifest resolves to a non-404 response on `OPTIONS` or `HEAD`. Tool invocation is not tested (would risk side effects).

Verdict: AGENT-READY requires W1 PASS + (W2 PASS OR optional). AGENT-PARTIAL is W1 OR W2 alone. AGENT-NOT-READY is neither.

## Section 7 — Fact-Block Density + Content Extractability

Scores 0–100 across five weighted checks:

| Check | Weight | What it measures |
|---|---|---|
| F1: First-sentence-of-H2 standalone-answer compliance | 30 | Does each H2 open with a sentence that stands alone? (Patel's rule) |
| F2: First-200-tokens direct-answer | 20 | Does the page opening directly answer the core query? |
| F3: 40-60 word direct-answer band per H2 | 20 | Are H2 opening paragraphs in the AI-extractable length band? |
| F4: H2/H3 question-format rate | 20 | Are headings phrased as questions users type? |
| F5: FAQ section present | 10 | Is there an FAQ near the article tail? |

Verdict: EXTRACTABLE ≥75 + ≥4/5 checks. PARTIALLY-EXTRACTABLE 40-74 + ≥2/5. NOT-EXTRACTABLE otherwise.

## Section 8 — Citation Decay Rate (the moat metric)

Consumes the Bing AI Performance Report CSV exported from `bing.com/webmasters` → AI Performance Report → Export CSV. Computes:

- **Citation Decay Rate**: per-window aggregate decline percentage (early 2 weeks avg vs late 2 weeks avg)
- **Citation half-life**: days from peak week to a sustained 4-week below-50% window. Returns null if undecayed. (Tune ratified 2026-05-22 to suppress false positives on growing data.)
- **Decay slope**: linear regression slope of citations/day
- **Displacement event count**: week-over-week drops > 1.5σ of weekly delta
- **Citation Retention Rate**: latest 30 days / earliest 30 days

First-to-market metric (verified 2026-05-22 across 8 competitor public surfaces).

## Case-study evidence

| Site | §2.7 Agent Readiness | §7 Fact-Block | §8 Citation Decay |
|---|---|---|---|
| chudi.dev | **AGENT-READY 3/3** | 40/100 NOT-EXTRACTABLE | GROWING (retention 1.65) |
| chudi.dev/framework | **AGENT-READY 3/3** | 51/100 PARTIALLY-EXTRACTABLE | (uses Bing data) |
| citability.dev | **AGENT-READY 3/3 (meaningful endpoints)** | 50/100 PARTIALLY-EXTRACTABLE | GROWING |

All verdicts verified on production 2026-05-22 to 2026-05-23. Full reports in `sample-audits/audit_chudi.dev_20260523_070001.md` and `sample-audits/audit_citability.dev_20260523_070001.md`.

## Tests

```bash
pytest tests/ -v
```

`tests/test_section_citation_decay.py` exercises the §8 algorithm with 12 hermetic scenarios covering verdict band transitions + unit-level half-life behavior + ancillary metrics. `tests/test_section5_off_site_authority.py` exercises §2.6 Phase 1 (Wikipedia + Wikidata + sameAs).

## Methodology pin

AVR v1.1.0 first released 2026-05-22. Re-check cadence: monthly for WebMCP / A2A (spec is moving); quarterly for Fact-Block, Multimodal, Topic Cluster (content-quality signals stable); one-shot for llms.txt reclassification (v1.0 → v1.1.0 inversion is settled).

## Repo layout

```
scripts/
  run_audit.py                            # main entry point; --full-v11 flag
  seo_foundation.py                       # Section 1
  ai_readiness.py                         # Section 2
  citation_auto.py                        # Section 3 (live; needs OPENAI_API_KEY)
  visibility_auto.py                      # Section 4 (live)
  calibration.py                          # Section 5
  section5_off_site_authority.py          # §2.6 Phase 1 (separate from main flow)
  section_webmcp_agent_readiness.py       # Section 6 (v1.1.0)
  section_fact_block_density.py           # Section 7 (v1.1.0)
  section_citation_decay.py               # Section 8 (v1.1.0)
  report_generator.py                     # Markdown report renderer
tests/
  test_section_citation_decay.py          # 12 hermetic scenarios
  test_section5_off_site_authority.py     # §2.6 Phase 1 mock-based
sample-audits/
  audit_<domain>_<timestamp>.md           # report deliverable
  audit_<domain>_<timestamp>_*.json       # per-section structured data
```

## License + contact

Contact: [chudi@chudi.dev](mailto:chudi@chudi.dev). Methodology canonical reference: [chudi.dev/framework](https://chudi.dev/framework). Audit deliverable demo: [citability.dev](https://citability.dev).
