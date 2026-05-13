"""
Tests for section5_off_site_authority (AVR Section 5, Phase 1).

Covers:
- JSON shape conformance to spec lines 84-106 (id / label / passed / evidence / signal_hierarchy_rank)
- Section verdict bands: PASS at 3/3, PARTIAL at 1-2/3, FAIL at 0/3
- Recommendations ordered by signal hierarchy rank (lower rank = higher priority)
- All-pass fixture (a fully-equipped imaginary brand)
- Network calls are mocked: tests are hermetic, no live API spend, no flake from
  Wikidata SPARQL endpoint slowness.

Run with: pytest tests/test_section5_off_site_authority.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import section5_off_site_authority as s5  # noqa: E402


def _fake_response(payload: dict, status: int = 200, *, text: str | None = None):
    class R:
        status_code = status
        encoding = "utf-8"

        def __init__(self):
            self._payload = payload
            self._text = text

        def raise_for_status(self):
            if self.status_code >= 400:
                raise s5.requests.HTTPError(f"HTTP {self.status_code}")

        def json(self):
            return self._payload

        @property
        def text(self):
            return self._text if self._text is not None else json.dumps(self._payload)

    return R()


WIKIPEDIA_HIT = {
    "query": {
        "search": [
            {
                "title": "Test Brand",
                "snippet": "Test Brand is a hypothetical company used in citability.dev tests.",
            }
        ]
    }
}

WIKIPEDIA_MISS = {"query": {"search": []}}

SPARQL_HIT = {
    "results": {
        "bindings": [
            {
                "item": {"value": "http://www.wikidata.org/entity/Q12345"},
                "itemLabel": {"value": "Test Brand"},
                "prop": {"value": "P856"},
                "website": {"value": "https://test-brand.example/"},
            }
        ]
    }
}

SPARQL_EMPTY = {"results": {"bindings": []}}

WBSEARCH_HIT = {"search": [{"id": "Q12345", "label": "Test Brand", "description": "test"}]}
WBSEARCH_MISS = {"search": []}

WBGETENTITIES_LINKED = {
    "entities": {
        "Q12345": {
            "claims": {
                "P856": [{"mainsnak": {"datavalue": {"value": "https://test-brand.example/"}}}]
            }
        }
    }
}

WBGETENTITIES_NOT_LINKED = {
    "entities": {
        "Q12345": {
            "claims": {
                "P856": [{"mainsnak": {"datavalue": {"value": "https://other-domain.example/"}}}]
            }
        }
    }
}

HOMEPAGE_FULL_SAMEAS = (
    '<html><head>'
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"Organization","name":"Test Brand",'
    '"sameAs":["https://www.linkedin.com/company/test","https://github.com/test",'
    '"https://en.wikipedia.org/wiki/Test_Brand","https://www.wikidata.org/wiki/Q12345",'
    '"https://twitter.com/test","https://medium.com/@test"]}'
    '</script></head><body>hi</body></html>'
)

HOMEPAGE_PARTIAL_SAMEAS = (
    '<html><head>'
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"Person","name":"Test Operator",'
    '"sameAs":["https://www.linkedin.com/in/test","https://github.com/test"]}'
    '</script></head><body>hi</body></html>'
)

HOMEPAGE_NO_JSONLD = "<html><head><title>no schema here</title></head><body>nope</body></html>"


def _make_dispatcher(routes: dict):
    """Build a callable that maps requests.get(url, ...) to a fake response.

    routes keys are URL substrings; the first matching key wins.
    """
    def fake_get(url, params=None, headers=None, timeout=None, **kw):
        for needle, payload in routes.items():
            if needle in url:
                # Wikipedia + Wikidata APIs are JSON; homepage is HTML.
                if isinstance(payload, str):
                    return _fake_response({}, text=payload)
                return _fake_response(payload)
        raise AssertionError(f"unmocked request: {url}")
    return fake_get


def test_json_shape_conforms_to_spec():
    """Spec lines 84-106: each check has id/label/passed/evidence/signal_hierarchy_rank;
    section emits verdict + score + recommendations."""
    routes = {
        "en.wikipedia.org/w/api.php": WIKIPEDIA_HIT,
        "query.wikidata.org/sparql": SPARQL_HIT,
        "test-brand.example": HOMEPAGE_FULL_SAMEAS,
    }
    with patch.object(s5.requests, "get", side_effect=_make_dispatcher(routes)):
        payload = s5.run_section5("https://test-brand.example", brand="Test Brand")

    assert "section_5_off_site_authority" in payload
    section = payload["section_5_off_site_authority"]

    assert section["phase"] == 1
    assert section["verdict"] in ("PASS", "PARTIAL", "FAIL")
    assert "score" in section
    assert "checks" in section and len(section["checks"]) == 3
    assert isinstance(section["recommendations"], list)

    for c in section["checks"]:
        assert set(c.keys()) >= {"id", "label", "passed", "evidence", "signal_hierarchy_rank"}
        assert c["label"] == "VERIFIABLE"
        assert c["signal_hierarchy_rank"] == 10
        assert isinstance(c["passed"], bool)
        assert isinstance(c["evidence"], list)


def test_all_three_pass_yields_pass_verdict():
    routes = {
        "en.wikipedia.org/w/api.php": WIKIPEDIA_HIT,
        "query.wikidata.org/sparql": SPARQL_HIT,
        "test-brand.example": HOMEPAGE_FULL_SAMEAS,
    }
    with patch.object(s5.requests, "get", side_effect=_make_dispatcher(routes)):
        payload = s5.run_section5("https://test-brand.example", brand="Test Brand")

    section = payload["section_5_off_site_authority"]
    assert section["verdict"] == "PASS"
    assert section["score"] == "3/3"
    assert section["recommendations"] == []
    assert all(c["passed"] for c in section["checks"])


def test_two_of_three_pass_yields_partial():
    routes = {
        "en.wikipedia.org/w/api.php": WIKIPEDIA_HIT,
        "query.wikidata.org/sparql": SPARQL_HIT,
        "test-brand.example": HOMEPAGE_PARTIAL_SAMEAS,  # only 2 sameAs categories
    }
    with patch.object(s5.requests, "get", side_effect=_make_dispatcher(routes)):
        payload = s5.run_section5("https://test-brand.example", brand="Test Brand")

    section = payload["section_5_off_site_authority"]
    assert section["verdict"] == "PARTIAL"
    assert section["score"] == "2/3"
    assert len(section["recommendations"]) == 1
    assert "sameAs" in section["recommendations"][0]


def test_zero_of_three_pass_yields_fail():
    routes = {
        "en.wikipedia.org/w/api.php": WIKIPEDIA_MISS,
        "query.wikidata.org/sparql": SPARQL_EMPTY,
        "wikidata.org/w/api.php": WBSEARCH_MISS,
        "test-brand.example": HOMEPAGE_NO_JSONLD,
    }
    with patch.object(s5.requests, "get", side_effect=_make_dispatcher(routes)):
        payload = s5.run_section5("https://test-brand.example", brand="Unknown Brand")

    section = payload["section_5_off_site_authority"]
    assert section["verdict"] == "FAIL"
    assert section["score"] == "0/3"
    assert len(section["recommendations"]) == 3
    # All three recs are for rank-10 signals; ordering preserved as
    # wikipedia -> wikidata -> sameAs (insertion order through sorted-by-rank).
    assert "Wikipedia" in section["recommendations"][0]


def test_wikidata_sparql_timeout_falls_back_to_wbgetentities():
    """When SPARQL is slow, the wbsearchentities + wbgetentities path verifies P856."""
    def fake_get(url, params=None, headers=None, timeout=None, **kw):
        if "query.wikidata.org/sparql" in url:
            raise s5.requests.exceptions.ReadTimeout("SPARQL took too long")
        if "en.wikipedia.org/w/api.php" in url:
            return _fake_response(WIKIPEDIA_HIT)
        if "wikidata.org/w/api.php" in url:
            action = (params or {}).get("action")
            if action == "wbsearchentities":
                return _fake_response(WBSEARCH_HIT)
            if action == "wbgetentities":
                return _fake_response(WBGETENTITIES_LINKED)
        if "test-brand.example" in url:
            return _fake_response({}, text=HOMEPAGE_FULL_SAMEAS)
        raise AssertionError(f"unmocked request: {url}")

    with patch.object(s5.requests, "get", side_effect=fake_get):
        payload = s5.run_section5("https://test-brand.example", brand="Test Brand")

    section = payload["section_5_off_site_authority"]
    wikidata = next(c for c in section["checks"] if c["id"] == "wikidata-entry-exists")
    assert wikidata["passed"] is True
    methods_used = [e.get("method") for e in wikidata["evidence"] if isinstance(e, dict)]
    assert any("wbgetentities" in (m or "") for m in methods_used)


def test_wbsearch_qid_without_p856_link_does_not_pass():
    """Sanity: a Q-number that doesn't link to the brand domain isn't a pass."""
    def fake_get(url, params=None, headers=None, timeout=None, **kw):
        if "query.wikidata.org/sparql" in url:
            return _fake_response(SPARQL_EMPTY)
        if "en.wikipedia.org/w/api.php" in url:
            return _fake_response(WIKIPEDIA_HIT)
        if "wikidata.org/w/api.php" in url:
            action = (params or {}).get("action")
            if action == "wbsearchentities":
                return _fake_response(WBSEARCH_HIT)
            if action == "wbgetentities":
                return _fake_response(WBGETENTITIES_NOT_LINKED)
        if "test-brand.example" in url:
            return _fake_response({}, text=HOMEPAGE_PARTIAL_SAMEAS)
        raise AssertionError(f"unmocked request: {url}")

    with patch.object(s5.requests, "get", side_effect=fake_get):
        payload = s5.run_section5("https://test-brand.example", brand="Test Brand")

    section = payload["section_5_off_site_authority"]
    wikidata = next(c for c in section["checks"] if c["id"] == "wikidata-entry-exists")
    assert wikidata["passed"] is False
    candidate_notes = [e.get("note", "") for e in wikidata["evidence"] if isinstance(e, dict)]
    assert any("not counted as pass" in n for n in candidate_notes)


def test_sameas_classifies_all_six_target_platforms():
    """Spec line 73: LinkedIn, GitHub, Wikipedia, Wikidata, X/Twitter, Medium."""
    classify = s5._classify_sameas_url
    assert classify("https://www.linkedin.com/in/test") == "linkedin"
    assert classify("https://github.com/test") == "github"
    assert classify("https://en.wikipedia.org/wiki/Test") == "wikipedia"
    assert classify("https://www.wikidata.org/wiki/Q1") == "wikidata"
    assert classify("https://twitter.com/test") == "x_twitter"
    assert classify("https://x.com/test") == "x_twitter"
    assert classify("https://medium.com/@test") == "medium"
    assert classify("https://reddit.com/u/test") is None


def test_recommendations_ordered_by_hierarchy_rank():
    """Lower rank = higher priority. All Phase 1 checks are rank 10, so order
    follows insertion order (wikipedia -> wikidata -> sameAs)."""
    checks = [
        {"id": "wikipedia-entry-exists", "passed": False, "signal_hierarchy_rank": 10, "evidence": []},
        {"id": "wikidata-entry-exists", "passed": False, "signal_hierarchy_rank": 10, "evidence": []},
        {"id": "schema-sameas-completeness", "passed": False, "signal_hierarchy_rank": 10,
         "evidence": [{"matched_count": 1, "min_required": 4}]},
    ]
    recs = s5._build_recommendations(checks)
    assert len(recs) == 3
    assert "Wikipedia" in recs[0]
    assert "Wikidata" in recs[1]
    assert "sameAs" in recs[2]


def test_brand_inference_from_domain():
    assert s5._brand_from_domain("github.com") == "Github"
    assert s5._brand_from_domain("chudi.dev") == "Chudi"
    assert s5._brand_from_domain("www.example.co.uk") == "Co"  # naive SLD pick
    assert s5._domain_root("https://www.github.com/foo") == "github.com"


def test_jsonld_walk_handles_at_graph_nesting():
    """Real-world JSON-LD often uses @graph; the walker must descend into it."""
    nested = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "name": "ignored"},
            {
                "@type": "Organization",
                "sameAs": [
                    "https://linkedin.com/company/x",
                    "https://github.com/x",
                    "https://wikipedia.org/wiki/x",
                    "https://wikidata.org/wiki/Q1",
                ],
            },
        ],
    }
    nodes = s5._walk_jsonld(nested)
    org_nodes = [n for n in nodes if s5._matches_type(n, "Organization")]
    assert len(org_nodes) == 1
    assert len(org_nodes[0]["sameAs"]) == 4


WIKIPEDIA_DISAMBIG = {
    "query": {
        "search": [
            {
                "title": "Apple (disambiguation)",
                "snippet": "Apple may refer to the fruit, the company, or several other meanings.",
            }
        ]
    }
}


def test_wikipedia_disambiguation_does_not_count_as_pass():
    """A disambiguation page is not a real entity entry."""
    routes = {
        "en.wikipedia.org/w/api.php": WIKIPEDIA_DISAMBIG,
        "query.wikidata.org/sparql": SPARQL_EMPTY,
        "wikidata.org/w/api.php": WBSEARCH_MISS,
        "test-brand.example": HOMEPAGE_NO_JSONLD,
    }
    with patch.object(s5.requests, "get", side_effect=_make_dispatcher(routes)):
        payload = s5.run_section5("https://test-brand.example", brand="Apple")

    section = payload["section_5_off_site_authority"]
    wikipedia = next(c for c in section["checks"] if c["id"] == "wikipedia-entry-exists")
    assert wikipedia["passed"] is False
    assert wikipedia["evidence"][0]["disambiguation_suspected"] is True


def test_check_wikidata_refuses_too_broad_host():
    """Empty / too-short host would CONTAINS-match every Wikidata website. Refuse."""
    result = s5.check_wikidata(brand="X", domain_host="x")
    assert result["passed"] is False
    assert any("too-broad host filter" in (e.get("error") or "") for e in result["evidence"])


def test_check_schema_sameas_rejects_non_http_scheme():
    """SSRF guard: refuse file://, ftp://, and other non-http(s) schemes."""
    result = s5.check_schema_sameas("file:///etc/passwd")
    assert result["passed"] is False
    assert any("non-http(s)" in (e.get("error") or "") for e in result["evidence"])


def test_phase_scope_note_references_decision_id():
    """The shipped artifact must trace back to the ratified decision_id."""
    routes = {
        "en.wikipedia.org/w/api.php": WIKIPEDIA_MISS,
        "query.wikidata.org/sparql": SPARQL_EMPTY,
        "wikidata.org/w/api.php": WBSEARCH_MISS,
        "test-brand.example": HOMEPAGE_NO_JSONLD,
    }
    with patch.object(s5.requests, "get", side_effect=_make_dispatcher(routes)):
        payload = s5.run_section5("https://test-brand.example", brand="X")
    note = payload["section_5_off_site_authority"]["phase_scope_note"]
    assert "dc-20260513T180052Z-9409" in note
    assert "Phase 1" in note


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
