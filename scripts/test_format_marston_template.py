#!/usr/bin/env python3
"""
Smoke test for format_marston_template.py auto-draft pipeline.

Loads the 2026-05-18 and 2026-05-07 Marston audits, runs the full
auto-draft + render pipeline end-to-end with a mocked Anthropic client,
and verifies:

  1. The computed deltas match the hand-written 2026-05-18 paragraph
     (citation rate -15.0pp, brand +23.3pp, topic +16.7pp, recommend +8.3pp).
  2. The user message sent to the model carries every required signal:
     both LOW confidence labels, the "60 to 80" panel-growth tokens,
     the new platform ("anthropic"), the robots_txt + sitemap 403 detail,
     and the verbatim delta tokens.
  3. The system prompt holds the voice rules + hard rules + the few-shot
     example, and is wrapped in a cache_control block.
  4. The response parser correctly splits analysis from recommendations
     on the ---REC--- separator and strips em-dashes.
  5. The full rendered template inserts the *▸ Analysis* section between
     Site infrastructure and Top 5 competitors, replaces the
     "What we'll do next week" placeholders with the recommendations, and
     appends the auto-draft audit-trail footer.

This test does not hit the real API. To run a live API smoke test, export
ANTHROPIC_API_KEY and run format_marston_template.py directly against
the 2026-05-18 audit base.

Usage:
  cd /Users/chudinnorukam/Projects/business/ai-visibility-readiness/scripts
  python3 test_format_marston_template.py
"""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

import format_marston_template as fmt


AUDIT_DIR = "/Users/chudinnorukam/Projects/business/ai-visibility-readiness/sample-audits"
CURR_BASE = "audit_marstonorthodontics.com_20260518_210713"
PREV_BASE = "audit_marstonorthodontics.com_20260507_221506"

# Canned response matching the hand-written 2026-05-18 paragraph shape. The
# real API will generate variations; this shape is the contract the
# response-parser must handle.
MOCK_RESPONSE_TEXT = """The brand-recognition lift is real but the query panel grew (60 to 80 tests) and Claude was added this run, so part of the % delta is methodology, not signal. Audit confidence label: LOW on both runs. Citation rate dropped 15pp. AIs are mentioning the practice more often but linking back less.
---REC---
- SEO foundation (robots.txt and sitemap returning 403) is still the blocker. Fixing those is the highest-leverage move before next week's measurement.
- Add JSON-LD for Dentist, LocalBusiness, and MedicalBusiness schema types to close the vertical-rich schema gap surfaced in 1.3_schema_markup.
"""


def _make_mock_anthropic_response():
    """Build an object that quacks like an anthropic Message."""
    text_block = types.SimpleNamespace(type="text", text=MOCK_RESPONSE_TEXT)
    usage = types.SimpleNamespace(
        input_tokens=850,
        output_tokens=160,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    return types.SimpleNamespace(content=[text_block], usage=usage)


class _MockAnthropic:
    """Stand-in for anthropic.Anthropic with the messages.create interface."""

    captured_call: dict = {}

    def __init__(self, api_key: str):
        self.api_key = api_key

        class _Messages:
            @staticmethod
            def create(**kwargs):
                _MockAnthropic.captured_call = kwargs
                return _make_mock_anthropic_response()

        self.messages = _Messages()


def main() -> int:
    failures: list[str] = []

    # --- 1. Load both audits ---
    curr_loaded = fmt.discover_audit_files(AUDIT_DIR, CURR_BASE)
    prev_loaded = fmt.discover_audit_files(AUDIT_DIR, PREV_BASE)

    for label, loaded in (("current", curr_loaded), ("prior", prev_loaded)):
        for k in ("seo", "ai", "citations", "visibility"):
            if loaded.get(k) is None:
                failures.append(f"{label} audit missing JSON: {k}")

    # --- 2. Verify computed deltas match the hand-written paragraph ---
    deltas = fmt.compute_deltas(curr_loaded, prev_loaded)
    expected_deltas = {
        "citation_rate_delta_pp": "-15.0pp",
        "brand_recog_delta_pp": "+23.3pp",
        "topic_assoc_delta_pp": "+16.7pp",
        "recommend_delta_pp": "+8.3pp",
        "panel_grew": True,
        "curr_confidence": "LOW",
        "prev_confidence": "LOW",
        "curr_total_tests": 80,
        "prev_total_tests": 60,
    }
    for k, want in expected_deltas.items():
        got = deltas.get(k)
        if got != want:
            failures.append(f"delta {k}: got {got!r}, want {want!r}")
    if "anthropic" not in deltas.get("new_platforms", []):
        failures.append(f"new_platforms: expected ['anthropic'], got {deltas.get('new_platforms')}")
    if "robots_txt HTTP 403" not in deltas.get("curr_crawl_blockers", []):
        failures.append(f"crawl_blockers missing robots_txt 403: {deltas.get('curr_crawl_blockers')}")
    if "sitemap HTTP 403" not in deltas.get("curr_crawl_blockers", []):
        failures.append(f"crawl_blockers missing sitemap 403: {deltas.get('curr_crawl_blockers')}")

    # --- 3. Verify the user message carries every signal the model needs ---
    user_msg = fmt._build_user_message(deltas)
    required_user_msg_tokens = [
        "LOW",
        "-15.0pp",
        "+23.3pp",
        "+16.7pp",
        "+8.3pp",
        "anthropic",
        "Citation panel grew between runs: yes",
        "robots_txt HTTP 403",
        "sitemap HTTP 403",
        "current=LOW, prior=LOW",
        "80 total tests",
        "60 total tests",
    ]
    for tok in required_user_msg_tokens:
        if tok not in user_msg:
            failures.append(f"user message missing required signal: {tok!r}")

    # --- 4. Verify the system prompt carries the voice + hard rules ---
    sysp = fmt._AUTO_DRAFT_SYSTEM_PROMPT
    required_system_tokens = [
        "Customer Success Lead",
        "+/-Npp",
        "No apology preamble",
        "No em-dashes",
        "NEVER fabricate metrics",
        "confidence_label is LOW",
        "citation panel grew",
        "---REC---",
        "REFERENCE EXAMPLE",
        "slack-channel-posting-flow",
    ]
    for tok in required_system_tokens:
        if tok not in sysp:
            failures.append(f"system prompt missing token: {tok!r}")

    # --- 5. Exercise the SDK path with a mocked client ---
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-fake-key"}):
        with patch.object(fmt, "_maybe_load_dotenv", lambda *a, **kw: None):
            # Inject the mock into the lazy 'anthropic' module import.
            mock_module = types.ModuleType("anthropic")
            mock_module.Anthropic = _MockAnthropic
            with patch.dict("sys.modules", {"anthropic": mock_module}):
                analysis, recs = fmt.draft_analysis_and_recommendations(
                    curr_loaded, prev_loaded
                )

    if not analysis:
        failures.append("draft returned empty analysis paragraph")
    if not recs:
        failures.append("draft returned empty recommendations block")

    # --- 6. Verify the captured API call ---
    call = _MockAnthropic.captured_call
    if call.get("model") != "claude-haiku-4-5-20251001":
        failures.append(f"model: got {call.get('model')!r}, want 'claude-haiku-4-5-20251001'")
    if call.get("max_tokens") != 800:
        failures.append(f"max_tokens: got {call.get('max_tokens')}, want 800")
    system = call.get("system")
    if not isinstance(system, list) or not system:
        failures.append(f"system not a non-empty list: {type(system).__name__}")
    else:
        block = system[0]
        if block.get("type") != "text":
            failures.append(f"system block type: got {block.get('type')!r}, want 'text'")
        if block.get("cache_control", {}).get("type") != "ephemeral":
            failures.append(f"cache_control missing or wrong: {block.get('cache_control')!r}")
        if block.get("cache_control", {}).get("ttl") != "5m":
            failures.append(f"cache_control ttl: got {block.get('cache_control', {}).get('ttl')!r}, want '5m'")

    # --- 7. Verify response parsing ---
    if analysis and "—" in analysis:
        failures.append("analysis paragraph leaked an em-dash (chudi-frame violation)")
    if recs and "—" in recs:
        failures.append("recommendations leaked an em-dash (chudi-frame violation)")
    if analysis and "LOW" not in analysis:
        failures.append("analysis paragraph does not mention LOW confidence (hard rule violation)")
    if recs and not recs.lstrip().startswith("- "):
        failures.append(f"recommendations do not start with '- ': {recs[:80]!r}")

    # --- 8. Verify the full template render ---
    fields = fmt.extract_fields(curr_loaded)
    rendered = fmt.render_template(
        fields,
        2,
        "2026-05-18",
        "🟢 on-track",
        analysis_paragraph=analysis,
        recommendations_block=recs,
        auto_drafted=True,
    )

    required_rendered_tokens = [
        "*▸ Analysis*",
        "LOW on both runs",
        "60 to 80 tests",
        "Citation rate dropped 15pp",
        "*▸ What we'll do next week*",
        "- SEO foundation",
        "Analysis + recommendations auto-drafted",
    ]
    for tok in required_rendered_tokens:
        if tok not in rendered:
            failures.append(f"rendered template missing token: {tok!r}")

    # The next-week section should NOT carry the placeholder markers when
    # auto-draft populated it. This is the load-bearing voice check: posting
    # a draft with `{{Manual:}}` markers visible to the channel is a voice
    # violation per the ANTI-PATTERNS section of the SKILL.md.
    next_week_start = rendered.find("*▸ What we'll do next week*")
    asks_start = rendered.find("*▸ Asks for Dr. Marston*")
    if next_week_start >= 0 and asks_start > next_week_start:
        next_week_block = rendered[next_week_start:asks_start]
        if "{{Manual:" in next_week_block:
            failures.append("next-week section still carries {{Manual:}} after auto-draft populated it")

    # --- Report ---
    print("=" * 60)
    print("SMOKE TEST: format_marston_template.py auto-draft")
    print("=" * 60)
    print()
    print(f"Current run: {CURR_BASE}")
    print(f"Prior run:   {PREV_BASE}")
    print()
    print("Sample of generated draft (with mock response):")
    print("-" * 60)
    print(rendered[rendered.find("*▸ Analysis*"):rendered.find("*▸ Top 5 competitors")].rstrip())
    print()
    print(rendered[rendered.find("*▸ What we'll do next week*"):rendered.find("*▸ Asks")].rstrip())
    print("-" * 60)
    print()

    if failures:
        print(f"FAILED: {len(failures)} check(s) did not pass:")
        for f in failures:
            print(f"  - {f}")
        return 1
    else:
        print("PASS: all 7 sections of the auto-draft pipeline verified.")
        print()
        print("To exercise the live API (one Haiku call):")
        print("  ANTHROPIC_API_KEY=sk-... python3 format_marston_template.py \\")
        print(f"    --audit-dir {AUDIT_DIR} \\")
        print(f"    --audit-base {CURR_BASE} \\")
        print("    --week 2 --date 2026-05-18 --status on-track")
        return 0


if __name__ == "__main__":
    sys.exit(main())
