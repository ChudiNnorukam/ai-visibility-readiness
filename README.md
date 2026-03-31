# AI Visibility Readiness (AVR) Framework v1.0

[![License: Source-Available](https://img.shields.io/badge/license-Source--Available-blue)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-teal)](https://python.org)
[![Website](https://img.shields.io/badge/website-citability.dev-00d4aa)](https://citability.dev)
[![Take the Assessment](https://img.shields.io/badge/free_assessment-Start_Now-00d4aa)](https://citability.dev/assess)

**Measure whether AI systems can find, recommend, and cite your website.**

Most SEO tools tell you how Google ranks you. None tell you whether ChatGPT, Perplexity, or Claude can find you. The AVR Framework fills that gap with 15 transparent, tiered checks.

> Built by [Chudi Nnorukam](https://chudi.dev) | Powered by [citability.dev](https://citability.dev)

---

## What This Framework Measures

| Tier | What It Checks | Evidence Level |
|------|---------------|----------------|
| **SEO Foundation** | robots.txt, sitemap, schema, Core Web Vitals, mobile, page speed | [VERIFIABLE] |
| **AI Infrastructure** | /llms.txt, /ai.txt, question headings, answer-first content, original data, AI monitoring | [VERIFIABLE] |
| **Citation Monitoring** | Brand recognition, recommendability, URL citations across ChatGPT, Perplexity, Claude | [BEST-EFFORT] |

Every check is labeled `[VERIFIABLE]` or `[BEST-EFFORT]`. We do not combine them into a fake composite score.

---

## Key Findings (March 2026)

From auditing 50+ websites across DA 5 to DA 99:

- **85% of websites** have zero AI-readable surfaces (no /llms.txt, no /ai.txt)
- **Domain authority does not predict AI readiness.** A DA 5 site (chudi.dev) outscored DA 99 sites (reddit.com, x.com) on AI infrastructure
- **Visibility and citations are different problems.** ahrefs.com is 100% AI-visible but only 5% AI-cited
- **Even DA 90+ sites fail basic checks.** Reddit, Medium, and X all score NOT-READY on AI infrastructure

| Site | DA | AI Infrastructure | AI Visibility | AI Citations | Status |
|------|-----|-------------------|---------------|-------------|--------|
| ahrefs.com | 92 | FOUNDATION-READY | 100% HIGH | 5% PARTIAL | Visible, rarely cited |
| chudi.dev | ~5 | AI-READY (9/9) | 29% PARTIAL | 0% NOT CITED | Strong infra, building authority |
| semrush.com | 91 | FOUNDATION-READY | -- | -- | Infrastructure gaps |
| reddit.com | 99 | NOT-READY | -- | -- | Missing basics |
| medium.com | 95 | NOT-READY | -- | -- | Missing basics |
| x.com | 99 | NOT-READY | -- | -- | Missing basics |

---

## Quick Start

### 1. Free Infrastructure Scan (no API keys needed)

```bash
cd scripts
pip install -r requirements.txt
python3 run_audit.py https://yourdomain.com -o ../sample-audits --skip-lighthouse
```

This runs 12 infrastructure checks in ~30 seconds.

### 2. Live AI Visibility Test (requires API keys)

```bash
# Set up your .env file
cp .env.example .env
# Add your API keys (at minimum OPENAI_API_KEY)

# Run visibility test
python3 visibility_auto.py test https://yourdomain.com \
  --brand "Your Brand" \
  --owner "Your Name" \
  --topics seo,marketing,ai \
  -o ../sample-audits
```

### 3. Live AI Citation Test

```bash
python3 citation_auto.py test https://yourdomain.com \
  --topics seo,marketing,ai \
  -o ../sample-audits
```

---

## API Keys

Create a `.env` file in the `scripts/` directory:

```env
OPENAI_API_KEY=sk-...          # Required for ChatGPT queries
PERPLEXITY_API_KEY=pplx-...    # Optional, adds Perplexity platform
ANTHROPIC_API_KEY=sk-ant-...   # Optional, adds Claude platform
```

Cost per audit: ~$0.60 for visibility, ~$0.60 for citations, ~$2 for full audit.

---

## Framework Documentation

See [FRAMEWORK.md](FRAMEWORK.md) for the complete methodology: all 15 checks with pass/fail criteria, data sources, CLI commands, and explanations of why each signal matters for AI visibility.

---

## Scores Explained

| Status | Meaning |
|--------|---------|
| **AI-READY** | All infrastructure checks pass. Ready for live AI testing. |
| **FOUNDATION-READY** | SEO basics in place but missing AI-specific surfaces. |
| **INFRASTRUCTURE-READY** | Some checks pass. Significant gaps remain. |
| **NOT-READY** | Missing fundamental crawlability or SEO signals. |

---

## The Three Pillars

```
1. VISIBILITY     Can AI systems find you?
      |
      v
2. RECOMMENDABILITY   Does AI suggest you?
      |
      v
3. CITABILITY     Does AI link to your URL?
```

Each pillar is tested independently. A site can be 100% visible but 0% cited (like ahrefs.com). The gap between visibility and citation is where the real work happens.

---

## Use Cases

- **Self-audit**: Run the free scan on your own site to identify gaps
- **Consulting**: Use the full audit + report generator for client deliverables
- **Competitive analysis**: Compare your site against competitors
- **LinkedIn prospecting**: Pre-audit a prospect's site, include findings in your outreach

---

## Project Structure

```
scripts/
  run_audit.py          # Main audit runner (all sections)
  seo_foundation.py     # Section 1: SEO Foundation checks
  ai_readiness.py       # Section 2: AI Infrastructure checks
  citation_auto.py      # Section 3: Live AI citation testing
  visibility_auto.py    # Section 4: Live AI visibility testing
  report_generator.py   # Consulting-grade report output
  citation_monitor.py   # Ongoing citation monitoring
  requirements.txt      # Python dependencies

sample-audits/          # Example audit outputs

FRAMEWORK.md            # Complete methodology documentation
```

---

## Data Disclaimer

The `sample-audits/` directory contains real audit outputs for publicly accessible websites.
This data is provided for educational and benchmarking purposes only. All data was collected
from publicly available URLs using standard HTTP requests and public APIs. No private or
authenticated data was accessed.

If you are the owner of an audited website and would like your data removed, contact
hello@citability.dev.

---

## License

**Source-Available License v1.0** (see [LICENSE](LICENSE))

- Free for personal, educational, and non-commercial use
- Attribution required: credit "Chudi Nnorukam / citability.dev"
- Commercial use requires a separate license: hello@citability.dev
- No reselling or rebranding without written permission

---

## About

The AVR Framework powers [citability.dev](https://citability.dev), an AI visibility auditing service. Take the free [AI Visibility Assessment](https://citability.dev/assess) to get your score.

Built by [Chudi Nnorukam](https://chudi.dev).
