"""
Tests for CIT-83: Gemini grounding-redirect unwrap.

Gemini's grounding_chunks return citation URLs on the host
vertexaisearch.cloud.google.com (path /grounding-api-redirect/...) instead of
the real destination page. _domain_match against a target_domain can never
match that wrapper host, producing false NOT_CITED / zero-citation results
even when the target was genuinely cited (measured: strategyn.com scored
0/14 when the true rate was 10/14).

Covers _resolve_redirect_url directly (no google.genai SDK import needed):
- (a) a wrapper URL resolves and _domain_match then hits the target domain
- (b) a non-wrapper URL passes through unchanged with zero HTTP calls
- (c) a resolution failure (exception) falls back to the original URL,
      never raises
- (d) the cache prevents a second HTTP call for the same wrapper

Network calls are mocked: tests are hermetic, no live API spend.

Run with: pytest tests/test_citation_gemini_redirect.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import citation_auto as ca  # noqa: E402

WRAPPER_URL = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AbCdEf"
RESOLVED_URL = "https://strategyn.com/jobs-to-be-done/"


class _FakeResponse:
    def __init__(self, url: str):
        self.url = url


def test_wrapper_resolves_and_domain_match_hits_target():
    cache: dict[str, str] = {}
    with patch("requests.get", return_value=_FakeResponse(RESOLVED_URL)) as mock_get:
        resolved = ca._resolve_redirect_url(WRAPPER_URL, cache)

    assert resolved == RESOLVED_URL
    assert mock_get.call_count == 1
    assert ca._domain_match("strategyn.com", resolved) is True
    # The wrapper itself would never have matched.
    assert ca._domain_match("strategyn.com", WRAPPER_URL) is False


def test_non_wrapper_url_passes_through_with_no_http_call():
    cache: dict[str, str] = {}
    plain_url = "https://example.com/some-page"
    with patch("requests.get") as mock_get:
        resolved = ca._resolve_redirect_url(plain_url, cache)

    assert resolved == plain_url
    mock_get.assert_not_called()


def test_resolution_failure_falls_back_to_original_url():
    cache: dict[str, str] = {}
    with patch("requests.get", side_effect=Exception("connection reset")):
        resolved = ca._resolve_redirect_url(WRAPPER_URL, cache)

    assert resolved == WRAPPER_URL


def test_cache_prevents_second_http_call_for_same_wrapper():
    cache: dict[str, str] = {}
    with patch("requests.get", return_value=_FakeResponse(RESOLVED_URL)) as mock_get:
        first = ca._resolve_redirect_url(WRAPPER_URL, cache)
        second = ca._resolve_redirect_url(WRAPPER_URL, cache)

    assert first == RESOLVED_URL
    assert second == RESOLVED_URL
    assert mock_get.call_count == 1
