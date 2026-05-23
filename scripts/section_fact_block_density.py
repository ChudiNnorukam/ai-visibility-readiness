#!/usr/bin/env python3
"""
AVR §3 Fact-Block Density Audit (Content Extractability)

Implements the Fact-Block Density and Content Extractability Score signals
defined by AVR v1.1.0 per the codex node
[[avr-framework-v1-1-0-upgrade-fact-block-content-architecture-extractability-multimodal]]
and grounded in [[inverted-pyramid-content-discipline]].

Five checks, all [VERIFIABLE]:

  Check F1: First-sentence-of-every-H2 standalone-answer compliance
            (Patel's rule; the load-bearing signal)
  Check F2: First-200-tokens direct-answer compliance
  Check F3: 40-60 word direct-answer-band compliance per H2
  Check F4: H2/H3 question-format rate
            (sections headed as questions users would actually type)
  Check F5: FAQ section presence at article footer

Verdict bands:
  EXTRACTABLE       = >=4/5 checks pass (high citation probability)
  PARTIALLY-EXTRACTABLE = 2-3/5 checks pass
  NOT-EXTRACTABLE   = 0-1/5 checks pass

Content Extractability Score: 0-100 composite, weighted F1=30, F2=20, F3=20,
F4=20, F5=10. Score band map: EXTRACTABLE >= 75, PARTIALLY-EXTRACTABLE 40-74,
NOT-EXTRACTABLE < 40.

Cost: $0 (HTML parse only, no API spend).
"""

import argparse
import json
import re
import sys
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "AVR-citability/1.1 "
    "(Section-FactBlockDensity audit; https://citability.dev; "
    "contact: chudi@chudi.dev)"
)

REQUEST_TIMEOUT_SEC = 8

# Patterns indicating a heading is question-shaped
QUESTION_PATTERNS = (
    r"^\s*(what|how|why|when|where|who|which|is|are|can|do|does|should|will|did)\b",
    r"\?\s*$",
)

# Headings to recognize as FAQ section
FAQ_HEADING_PATTERN = re.compile(r"^(faq|frequently asked|q\s*&\s*a|questions and answers)\b", re.IGNORECASE)

# Direct-answer band per AI SEO Engineering Standards
DIRECT_ANSWER_MIN_WORDS = 40
DIRECT_ANSWER_MAX_WORDS = 60

# First-200-tokens approximation (~ 200 words for English prose)
FIRST_TOKENS_WORD_COUNT = 200


def _fetch_html(url: str) -> tuple[str | None, str | None]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC, allow_redirects=True)
        if resp.status_code >= 400:
            return None, f"http_{resp.status_code}"
        return resp.text, None
    except requests.RequestException as e:
        return None, f"network_error:{type(e).__name__}"


def _is_question(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    for pat in QUESTION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def _first_sentence(paragraph: str) -> str:
    """Return the first sentence of a paragraph (split on . ! ?)."""
    paragraph = paragraph.strip()
    m = re.search(r"^([^.!?]+[.!?])", paragraph)
    return m.group(1).strip() if m else paragraph


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def _is_standalone_answer(sentence: str) -> bool:
    """Heuristic: does this sentence stand alone as an answer?

    Heuristics that mark a sentence as NOT standalone:
      - starts with a pronoun reference (it, this, that, these, those)
      - starts with a conjunction (but, however, also, additionally, moreover)
      - starts with "Like X..." or "Unlike X..." (comparative reference)
    """
    s = sentence.strip().lower()
    if not s:
        return False
    not_standalone_prefixes = (
        "it ", "this ", "that ", "these ", "those ",
        "but ", "however,", "however ", "also,", "also ", "additionally", "moreover",
        "like ", "unlike ", "similarly", "in addition", "furthermore",
    )
    for prefix in not_standalone_prefixes:
        if s.startswith(prefix):
            return False
    return True


def extract_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Return [{heading, level, first_para_text, paragraphs:[...]}] for every h1-h3."""
    sections = []
    headings = soup.find_all(["h1", "h2", "h3"])
    for h in headings:
        heading_text = h.get_text(strip=True)
        level = int(h.name[1])
        # Collect all paragraphs until the next h1/h2/h3.
        paragraphs = []
        sibling = h.find_next_sibling()
        while sibling is not None and sibling.name not in ("h1", "h2", "h3"):
            if sibling.name == "p":
                txt = sibling.get_text(strip=True)
                if txt:
                    paragraphs.append(txt)
            elif sibling.name in ("div", "section", "article"):
                # Walk shallow into div/section to find <p> children
                for p in sibling.find_all("p", recursive=False):
                    txt = p.get_text(strip=True)
                    if txt:
                        paragraphs.append(txt)
            sibling = sibling.find_next_sibling()
        sections.append({
            "heading": heading_text,
            "level": level,
            "paragraphs": paragraphs,
            "first_para": paragraphs[0] if paragraphs else "",
        })
    return sections


def check_first_sentence_standalone(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Check F1: first sentence of every H2 must be a standalone answer."""
    result = {
        "id": "first-sentence-of-h2-standalone-answer",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 10,
    }
    h2s = [s for s in sections if s["level"] == 2 and s["first_para"]]
    if not h2s:
        result["evidence"].append({"error": "no H2 sections with content found"})
        return result

    per_section = []
    compliant_count = 0
    for s in h2s:
        first_sent = _first_sentence(s["first_para"])
        is_standalone = _is_standalone_answer(first_sent)
        if is_standalone:
            compliant_count += 1
        per_section.append({
            "heading": s["heading"][:80],
            "first_sentence": first_sent[:200],
            "is_standalone_answer": is_standalone,
        })

    compliance_rate = compliant_count / len(h2s)
    result["evidence"].append({
        "h2_count": len(h2s),
        "compliant_count": compliant_count,
        "compliance_rate_pct": round(compliance_rate * 100, 1),
        "per_section": per_section[:10],  # cap evidence noise
    })
    # Pass: >=80% of H2 sections have standalone-answer first sentences
    result["passed"] = compliance_rate >= 0.80
    result["compliance_rate"] = compliance_rate
    return result


def check_first_200_tokens_direct_answer(soup: BeautifulSoup) -> dict[str, Any]:
    """Check F2: first 200 words of page body must directly answer core query."""
    result = {
        "id": "first-200-tokens-direct-answer",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 9,
    }
    # Find body text (first 200 words of <main> or <article>, fall back to <body>).
    container = soup.find("main") or soup.find("article") or soup.find("body")
    if not container:
        result["evidence"].append({"error": "no body container found"})
        return result
    # Extract text from first 3 <p> tags (proxy for "first 200 tokens area").
    first_paras = container.find_all("p", limit=5)
    text_blob = " ".join(p.get_text(strip=True) for p in first_paras)
    wc = _word_count(text_blob)
    first_sentence = _first_sentence(text_blob) if text_blob else ""
    is_standalone = _is_standalone_answer(first_sentence)

    result["evidence"].append({
        "first_paragraphs_word_count": wc,
        "first_sentence": first_sentence[:300],
        "first_sentence_is_standalone": is_standalone,
    })
    # Pass: there IS content in the first 200 words AND the first sentence is standalone
    result["passed"] = wc >= 50 and is_standalone
    return result


def check_direct_answer_band(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Check F3: per-H2 direct answer should fall in 40-60 word band."""
    result = {
        "id": "direct-answer-40-60-word-band",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 8,
    }
    h2s = [s for s in sections if s["level"] == 2 and s["first_para"]]
    if not h2s:
        result["evidence"].append({"error": "no H2 sections found"})
        return result
    in_band_count = 0
    per_section = []
    for s in h2s:
        wc = _word_count(s["first_para"])
        in_band = DIRECT_ANSWER_MIN_WORDS <= wc <= DIRECT_ANSWER_MAX_WORDS
        if in_band:
            in_band_count += 1
        per_section.append({
            "heading": s["heading"][:80],
            "first_para_word_count": wc,
            "in_band": in_band,
        })
    rate = in_band_count / len(h2s)
    result["evidence"].append({
        "h2_count": len(h2s),
        "in_band_count": in_band_count,
        "in_band_rate_pct": round(rate * 100, 1),
        "band": f"{DIRECT_ANSWER_MIN_WORDS}-{DIRECT_ANSWER_MAX_WORDS} words",
        "per_section": per_section[:10],
    })
    # Pass: >=50% of H2 first paragraphs land in the 40-60 word band
    # (low bar: shorter is excusable as "lead sentence"; longer is the citation killer)
    result["passed"] = rate >= 0.50
    result["compliance_rate"] = rate
    return result


def check_question_format_headings(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Check F4: H2 and H3 headings should be question-shaped."""
    result = {
        "id": "h2-h3-question-format-rate",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 7,
    }
    sub_headings = [s for s in sections if s["level"] in (2, 3)]
    if not sub_headings:
        result["evidence"].append({"error": "no H2/H3 headings found"})
        return result
    q_count = sum(1 for s in sub_headings if _is_question(s["heading"]))
    rate = q_count / len(sub_headings)
    result["evidence"].append({
        "h2_h3_count": len(sub_headings),
        "question_count": q_count,
        "question_rate_pct": round(rate * 100, 1),
        "sample_questions": [s["heading"][:100] for s in sub_headings if _is_question(s["heading"])][:5],
    })
    # Pass: >=40% of H2/H3 headings are question-shaped
    result["passed"] = rate >= 0.40
    result["compliance_rate"] = rate
    return result


def check_faq_section_present(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Check F5: page contains an FAQ section near the end."""
    result = {
        "id": "faq-section-present",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 5,
    }
    # Look for a heading matching FAQ pattern in the last 30% of sections.
    if not sections:
        result["evidence"].append({"error": "no sections found"})
        return result
    tail_start = max(0, int(len(sections) * 0.7))
    tail_sections = sections[tail_start:]
    faq_match = next((s for s in tail_sections if FAQ_HEADING_PATTERN.match(s["heading"])), None)
    if faq_match:
        result["passed"] = True
        result["evidence"].append({"faq_heading": faq_match["heading"]})
    else:
        # Also accept FAQ anywhere if no tail FAQ found
        any_faq = next((s for s in sections if FAQ_HEADING_PATTERN.match(s["heading"])), None)
        if any_faq:
            result["passed"] = True
            result["evidence"].append({"faq_heading": any_faq["heading"], "note": "FAQ not in tail but present"})
        else:
            result["evidence"].append({"note": "no FAQ-style heading detected"})
    return result


def compute_extractability_score(checks: list[dict[str, Any]]) -> int:
    """0-100 composite. Weights: F1=30, F2=20, F3=20, F4=20, F5=10."""
    weights = {
        "first-sentence-of-h2-standalone-answer": 30,
        "first-200-tokens-direct-answer": 20,
        "direct-answer-40-60-word-band": 20,
        "h2-h3-question-format-rate": 20,
        "faq-section-present": 10,
    }
    score = 0
    for c in checks:
        w = weights.get(c["id"], 0)
        if c["passed"]:
            score += w
        else:
            # Partial credit if compliance_rate is partial (F1, F3, F4)
            rate = c.get("compliance_rate")
            if rate is not None:
                score += int(w * rate)
    return min(100, max(0, score))


def section_verdict(pass_count: int, score: int) -> str:
    if pass_count >= 4 and score >= 75:
        return "EXTRACTABLE"
    if pass_count >= 2 and score >= 40:
        return "PARTIALLY-EXTRACTABLE"
    return "NOT-EXTRACTABLE"


def run_section_fact_block_density(url: str) -> dict[str, Any]:
    """Run the §3 Fact-Block Density audit. Returns section JSON."""
    html, err = _fetch_html(url)
    if err:
        return {
            "section_id": "section_fact_block_density",
            "section_name": "Fact-Block Density + Content Extractability",
            "url_audited": url,
            "error": err,
            "section_verdict": "NOT-EXTRACTABLE",
            "extractability_score": 0,
            "label": "VERIFIABLE",
        }
    soup = BeautifulSoup(html, "lxml")
    sections = extract_sections(soup)

    f1 = check_first_sentence_standalone(sections)
    f2 = check_first_200_tokens_direct_answer(soup)
    f3 = check_direct_answer_band(sections)
    f4 = check_question_format_headings(sections)
    f5 = check_faq_section_present(sections)

    checks = [f1, f2, f3, f4, f5]
    pass_count = sum(1 for c in checks if c["passed"])
    score = compute_extractability_score(checks)
    verdict = section_verdict(pass_count, score)

    recommendations = []
    if not f1["passed"]:
        recommendations.append({
            "id": "rec-rewrite-h2-first-sentences",
            "priority": 1,
            "action": (
                "Rewrite the first sentence of every H2 section to be a standalone answer. "
                "Patel's rule: each opening sentence must make sense without surrounding context, "
                "because AI engines extract chunks in isolation. Current compliance rate: "
                f"{f1.get('compliance_rate', 0) * 100:.0f}%."
            ),
        })
    if not f2["passed"]:
        recommendations.append({
            "id": "rec-rewrite-page-opening",
            "priority": 2,
            "action": (
                "Rewrite the first 200 words of the page to directly answer the core query. "
                "Avoid throat-clearing intros — the first sentence must stand alone as an answer."
            ),
        })
    if not f3["passed"]:
        recommendations.append({
            "id": "rec-tune-direct-answer-band",
            "priority": 3,
            "action": (
                f"Tune H2 opening paragraphs to the {DIRECT_ANSWER_MIN_WORDS}-{DIRECT_ANSWER_MAX_WORDS} word "
                "direct-answer band. Under 40 reads thin; over 60 risks chunk-truncation in AI extraction."
            ),
        })
    if not f4["passed"]:
        recommendations.append({
            "id": "rec-question-format-headings",
            "priority": 4,
            "action": (
                "Reshape H2/H3 headings as questions users would actually type "
                "('What is X', 'How do I X', 'Why does X'). Current question-rate: "
                f"{f4.get('compliance_rate', 0) * 100:.0f}%."
            ),
        })
    if not f5["passed"]:
        recommendations.append({
            "id": "rec-add-faq-section",
            "priority": 5,
            "action": "Add an FAQ section at the bottom of the article. Improves citation surface for follow-up queries.",
        })

    return {
        "section_id": "section_fact_block_density",
        "section_name": "Fact-Block Density + Content Extractability",
        "url_audited": url,
        "checks": checks,
        "section_verdict": verdict,
        "pass_count": pass_count,
        "total_checks": 5,
        "extractability_score": score,
        "recommendations": recommendations,
        "spec_version": "AVR v1.1.0 §3 (Fact-Block Density grounded in inverted-pyramid-content-discipline)",
        "cost_usd": 0.0,
        "label": "VERIFIABLE",
    }


def main():
    parser = argparse.ArgumentParser(
        description="AVR §3 Fact-Block Density + Content Extractability Audit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="URL to audit")
    parser.add_argument("-o", "--output", help="Write JSON result to this path")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress prints")
    args = parser.parse_args()

    if not args.quiet:
        print(f"[section-factblock] auditing {args.url} ...", file=sys.stderr)
    result = run_section_fact_block_density(args.url)
    if not args.quiet:
        print(
            f"[section-factblock] verdict: {result['section_verdict']} "
            f"(score: {result['extractability_score']}/100, {result['pass_count']}/{result['total_checks']} checks pass)",
            file=sys.stderr,
        )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        if not args.quiet:
            print(f"[section-factblock] wrote {args.output}", file=sys.stderr)
    else:
        print(json.dumps(result, indent=2))

    code_map = {"EXTRACTABLE": 0, "PARTIALLY-EXTRACTABLE": 1, "NOT-EXTRACTABLE": 2}
    sys.exit(code_map.get(result["section_verdict"], 2))


if __name__ == "__main__":
    main()
